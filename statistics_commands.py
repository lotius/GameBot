"""Friendly statistics views, filters, pagination, and CSV export."""
import asyncio
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import re
import shlex

import discord

from boardgamedice import dice_sets, normalize_dice_type, resolve_game
from statistics_store import StatisticsStore

VIEWS = {'overview', 'summary', 'faces', 'values', 'recent', 'leaderboard', 'daily', 'compare', 'export'}
HELP = """**Dice statistics**
!stats | server overview
!stats hqroll | HeroQuest summary
!stats me | your activity across games
!stats faces hqroll | face counts and percentages
!stats values hqroll | symbol totals and averages
!stats compare hqroll | observed vs expected face frequencies
!stats recent | latest recorded results
!stats leaderboard | top 25 rollers by command count
!stats daily | daily activity, newest first (up to 90 dates)
!stats export hqroll | CSV of up to 1,000 individual results

**Combine filters in any order:**
me or @user | #channel or here | today / week / month / 7d / all
since:YYYY-MM-DD | until:YYYY-MM-DD | type:dice-type
Examples:
!stats faces hqroll me week type:white
!stats recent drgroll #games 30d
!stats values oqroll since:2026-10-01 until:2026-10-31

Faces combine matching outcomes across variants; type:black selects black dice.
Double-symbol faces remain distinct. Values totals count all their symbols.
Dates and daily totals use UTC. until includes the selected date.
Only retained, recorded rolls from this server appear; disabled logging and
outages leave gaps. Averages describe the selected records, not luck scores.
"""


def parse_options(param, message, now=None):
    now = now or datetime.now(timezone.utc)
    options = dict(view=None, game=None, user=None, channel=None, dice_type=None,
                   since=None, until=None)
    tokens = shlex.split(param)
    for token in tokens:
        word = token.lower()
        if word in VIEWS:
            if options['view'] is not None:
                raise ValueError('Choose one view, such as faces or recent.')
            options['view'] = word
        elif word in ('roll', 'dice', 'standard') or resolve_game(word):
            if options['game'] is not None:
                raise ValueError('Choose one game.')
            options['game'] = 'standard' if word in ('roll', 'dice', 'standard') else resolve_game(word)
        elif word == 'me' or re.fullmatch(r'<@!?[0-9]+>', word):
            if options['user'] is not None:
                raise ValueError('Choose one player.')
            options['user'] = message.author.id if word == 'me' else int(re.sub(r'[^0-9]', '', word))
        elif word == 'here' or re.fullmatch(r'<#[0-9]+>', word):
            if options['channel'] is not None:
                raise ValueError('Choose one channel.')
            channel_id = message.channel.id if word == 'here' else int(word[2:-1])
            if word != 'here' and message.guild.get_channel_or_thread(channel_id) is None:
                raise ValueError('Choose a channel in this server.')
            options['channel'] = channel_id
        elif word in ('today', 'week', 'month', 'all') or re.fullmatch('[0-9]{1,4}d', word):
            if options['since'] is not None or options['until'] is not None:
                raise ValueError('Choose a duration or explicit dates, not both.')
            if word == 'today':
                options['since'] = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif word != 'all':
                days = {'week': 7, 'month': 30}.get(word, int(word[:-1]) if word.endswith('d') else 1)
                if days < 1:
                    raise ValueError('Use a positive number of days, such as 7d.')
                options['since'] = now - timedelta(days=days)
            if options.get('duration'):
                raise ValueError('Choose one date range.')
            options['duration'] = word
        elif word.startswith(('since:', 'until:')):
            key, value = word.split(':', 1)
            if options.get('duration') or options[key] is not None:
                raise ValueError('Choose one date range.')
            try:
                date = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except ValueError:
                raise ValueError('Use dates like since:2026-10-01.') from None
            options[key] = date + timedelta(days=1) if key == 'until' else date
        elif word.startswith('type:'):
            if options['dice_type'] is not None or not re.fullmatch('[a-z][a-z0-9]{0,63}', word[5:]):
                raise ValueError('Choose one dice type, such as type:white.')
            options['dice_type'] = word[5:]
        else:
            raise ValueError('Unknown filter. Use !stats help for examples; mention users/channels rather than typing their names.')
    if options['since'] and options['until'] and options['since'] >= options['until']:
        raise ValueError('The start date must be on or before the end date.')
    if options['dice_type']:
        if not options['game']:
            raise ValueError('Choose a game with a dice type, such as !stats faces hqroll type:white.')
        if options['game'] != 'standard':
            normalized = normalize_dice_type(options['game'], options['dice_type'])
            if normalized is None:
                raise ValueError('That dice type is not available for the selected game.')
            options['dice_type'] = normalized
        elif not re.fullmatch('d(?:[1-9][0-9]?|100)', options['dice_type']):
            raise ValueError('Standard dice types are d1 through d100.')
    if options['view'] is None:
        options['view'] = 'summary' if options['game'] else 'overview'
    # MariaDB stores UTC DATETIME/TIMESTAMP; pass naive UTC boundaries.
    for key in ('since', 'until'):
        if options[key] is not None:
            options[key] = options[key].astimezone(timezone.utc).replace(tzinfo=None)
    return options


def game_name(key):
    return 'Standard dice' if key == 'standard' else dice_sets.get(key, {}).get('name', key)


async def current_player_name(message, user_id, escape=True):
    member = message.guild.get_member(user_id)
    if member is None:
        try:
            member = await message.guild.fetch_member(user_id)
        except discord.NotFound:
            return 'Former member'
        except discord.HTTPException:
            return 'Unavailable member'
    return discord.utils.escape_markdown(member.display_name) if escape else member.display_name


def pretty(value):
    return str(value).removesuffix('.png').replace('_', ' ').replace('-', ' ')


def result_face(kind, face):
    """Remove the variant suffix from a face without changing its outcome."""
    face = str(face).removesuffix('.png')
    for separator in ('-', '_', ' '):
        suffix = separator + kind
        if face.endswith(suffix):
            return face[:-len(suffix)]
    return face


def face_group(game, kind, face, by_type):
    # Numeric dice of different sizes have different outcome distributions.
    return (game, kind if by_type or game == 'standard' else '', result_face(kind, face))


class StatPages(discord.ui.View):
    def __init__(self, user_id, pages):
        super().__init__(timeout=180)
        self.user_id, self.pages, self.index = user_id, pages, 0
        self.previous.disabled = True
        self.next.disabled = len(pages) <= 1

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Run !stats to browse your own report.', ephemeral=True)
            return False
        return True

    async def turn(self, interaction, step):
        self.index = max(0, min(len(self.pages) - 1, self.index + step))
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label='Previous', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        await self.turn(interaction, -1)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        await self.turn(interaction, 1)


async def send_pages(message, title, lines, filters):
    chunks, chunk = [], ''
    for line in lines:
        if len(chunk) + len(line) > 3300:
            chunks.append(chunk)
            chunk = ''
        chunk += line[:1000] + '\n'
    chunks.append(chunk or 'No records yet.')
    pages = []
    for index, text in enumerate(chunks):
        embed = discord.Embed(title=title, description=text, color=0x4C9BD6)
        embed.set_footer(text=f'{filters[:500]} | Page {index + 1}/{len(chunks)} | !stats help')
        pages.append(embed)
    if not getattr(message.channel.permissions_for(message.guild.me), 'embed_links', True):
        for text in chunks:
            for offset in range(0, len(text), 1900):
                await message.channel.send(text[offset:offset + 1900])
        return
    view = StatPages(message.author.id, pages) if len(pages) > 1 else None
    await message.channel.send(embed=pages[0], view=view)


def csv_cell(value):
    text = str(value)
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text


async def show_statistics(message, param, store):
    if param.strip().lower() in ('help', '?'):
        await send_pages(message, 'Statistics commands', HELP.splitlines(), 'Server-only records')
        return
    try:
        options = parse_options(param, message)
    except ValueError as error:
        await message.channel.send(f'{error} Use !stats help.')
        return
    try:
        summary, rows = await asyncio.to_thread(StatisticsStore(store.connection_factory).query, message.guild.id, options)
    except ValueError as error:
        await message.channel.send(str(error))
        return
    except Exception:
        logging.exception('Statistics query failed.')
        await message.channel.send('Statistics are temporarily unavailable. Your regular rolls can still continue.')
        return
    count, dice, players, first, last = summary
    view = options['view']
    names = {}
    async def name_for(user_id, escape=True):
        if user_id not in names:
            names[user_id] = await current_player_name(message, user_id, escape=False)
        return discord.utils.escape_markdown(names[user_id]) if escape else names[user_id]
    scope = [game_name(options['game']) if options['game'] else 'All games']
    if options['user']: scope.append(await name_for(options['user']))
    if options['channel']: scope.append(f'Channel {options["channel"]}')
    if options['dice_type']: scope.append(options['dice_type'])
    for name in ('since', 'until'):
        if options[name]: scope.append(f'{name} {options[name]:%Y-%m-%d %H:%M} UTC')
    filters = ' | '.join(scope)
    if not count:
        await send_pages(message, 'No recorded rolls yet', [
            'No rolls match these filters.',
            'Try !stats, a longer date range, or roll some dice first.',
            'Only successful rolls recorded while logging/database access was available appear. Purged records are excluded.'], filters)
        return
    lines = [f'**{count:,} commands | {dice:,} dice | {players:,} players**',
             f'Average: **{dice / count:.2f} dice per command**', '']
    if first and last:
        start_stamp = int(first.replace(tzinfo=timezone.utc).timestamp())
        end_stamp = int(last.replace(tzinfo=timezone.utc).timestamp())
        lines.append(f'Recorded range: <t:{start_stamp}:f> to <t:{end_stamp}:f>')
        lines.append('')
    if view == 'export':
        if not message.channel.permissions_for(message.guild.me).attach_files:
            await message.channel.send('I need Attach Files permission to export statistics.')
            return
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['roll_id', 'time_utc', 'player_name', 'channel_id', 'game', 'modifier', 'die_index', 'dice_type', 'face', 'values_json'])
        for row in rows:
            exported = list(row)
            exported[2] = await name_for(row[2], escape=False)
            writer.writerow([csv_cell(cell) for cell in exported])
        stream = io.BytesIO(output.getvalue().encode('utf-8-sig'))
        attachment = discord.File(stream, filename='dice-statistics.csv')
        try:
            await message.channel.send(f'Exported {len(rows):,} individual dice results, newest first (maximum 1,000). Narrow filters for a smaller export.', file=attachment)
        finally:
            attachment.close()
            stream.close()
        return
    if view == 'overview':
        for game, rolls, amount in rows:
            lines.append(f'**{game_name(game)}** | {rolls:,} commands, {amount:,} dice')
        lines += ['', 'Explore: !stats hqroll | !stats me | !stats leaderboard | !stats help']
    elif view == 'leaderboard':
        lines.append('**Most active rollers (up to 25)**')
        for index, (user, rolls, amount) in enumerate(rows, 1):
            name = await name_for(user)
            lines.append(f'{index}. **{name}** | {rolls:,} commands, {amount:,} dice')
    elif view == 'daily':
        lines.append('**Daily activity (UTC; newest first, up to 90 dates)**')
        for day, rolls, amount in rows:
            lines.append(f'{day}: {rolls:,} commands | {amount:,} dice')
    elif view == 'recent':
        lines.append('**Latest individual dice results (up to 20)**')
        for roll_id, date, user, channel, game, modifier, index, kind, face, values in rows:
            stamp = int(date.replace(tzinfo=timezone.utc).timestamp())
            name = await name_for(user)
            lines.append(f'<t:{stamp}:f> | **{name}** | {game_name(game)} | {pretty(kind)}: **{pretty(result_face(kind, face))}** (die {index + 1}, modifier {modifier:+d})')
    else:
        groups, expected = rows if view == 'compare' else (rows, {})
        observed, totals, type_totals = defaultdict(int), defaultdict(float), defaultdict(int)
        by_type = bool(options['dice_type'])
        combined_expected = defaultdict(float)
        for (game, kind, face), amount in expected.items():
            combined_expected[face_group(game, kind, face, by_type)] += amount
        expected = combined_expected
        for game, kind, face, values, amount in groups:
            key = face_group(game, kind, face, by_type)
            observed[key] += amount
            type_totals[key[:2]] += amount
            for key, value in json.loads(values).items():
                if type(value) in (int, float): totals[key] += value * amount
        if view in ('values', 'summary'):
            lines.append('**Result totals and averages**')
            if not totals: lines.append('No numeric result values were recorded for these rolls.')
            for key, value in sorted(totals.items()):
                lines.append(f'**{pretty(key)}**: {value:,.2f} total | {value / count:.2f} per command | {value / dice:.2f} per die')
            if view == 'summary': lines += ['', 'More detail: !stats faces ' + (options['game'] or '') + ' | !stats compare ' + (options['game'] or '')]
        else:
            lines.append('**Faces by dice type**' if by_type else '**Faces across dice variants**')
            for game, kind, face in sorted(set(observed) | set(expected)):
                key = (game, kind, face)
                amount, total = observed[key], type_totals[(game, kind)]
                label = ' / '.join([game_name(game)] + ([pretty(kind)] if kind else []) + [pretty(face)])
                line = f'**{label}**: {amount:,} ({amount / total:.1%})'
                if view == 'compare':
                    probability = expected.get(key, 0) / total
                    line += f' | expected {probability:.1%} | difference {(amount / total - probability) * 100:+.1f} percentage points'
                lines.append(line)
            if view == 'compare':
                lines += ['', 'Expected frequencies use the definitions saved with each roll. Small samples naturally vary; this is not a fairness or luck test.']
    await send_pages(message, f'Dice statistics | {view.title()}', lines, filters)


def register_statistics_command(tree, store, services=None):
    from discord import app_commands

    @tree.command(name='stats', description="Explore this server's dice statistics")
    @app_commands.guild_only()
    @app_commands.choices(view=[app_commands.Choice(name=name.title(), value=name)
                               for name in ['overview', 'summary', 'faces', 'values', 'compare', 'recent', 'leaderboard', 'daily', 'export', 'help']])
    @app_commands.describe(game='Game command, such as hqroll, or roll for standard dice',
                          days='Last N days; omit for all retained history',
                          dice_type='Dice type or alias, such as white')
    async def stats_command(interaction: discord.Interaction, view: str = 'overview',
                            game: str = None, player: discord.Member = None,
                            channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread = None,
                            days: app_commands.Range[int, 1, 9999] = None,
                            dice_type: str = None, private: bool = False):
        await interaction.response.defer(ephemeral=private)
        class ResponseChannel:
            id = interaction.channel_id
            def permissions_for(self, member):
                return interaction.channel.permissions_for(member)
            async def send(self, content=None, **kwargs):
                return await interaction.followup.send(content, ephemeral=private,
                    allowed_mentions=discord.AllowedMentions.none(), **kwargs)
        from types import SimpleNamespace
        message = SimpleNamespace(author=interaction.user, guild=interaction.guild,
                                  channel=ResponseChannel())
        if services is not None:
            policy = await services.policy(message)
            if not services.admit(message, policy):
                await interaction.followup.send('You are requesting reports too quickly. Please wait before trying again.', ephemeral=True)
                return
        if view == 'help':
            await show_statistics(message, 'help', store)
            return
        if days is not None and not 1 <= days <= 9999:
            await message.channel.send('Choose a positive number of days up to 9999.')
            return
        if channel is not None and channel.guild.id != interaction.guild_id:
            await message.channel.send('Choose a channel in this server.')
            return
        parts = [view]
        if game is not None:
            if len(game) > 64 or not re.fullmatch('[A-Za-z][A-Za-z0-9]*', game):
                await message.channel.send('Choose a game command such as hqroll.')
                return
            parts.append(game)
        if player: parts.append(f'<@{player.id}>')
        if channel: parts.append(f'<#{channel.id}>')
        if days: parts.append(f'{days}d')
        if dice_type:
            if not re.fullmatch('[A-Za-z][A-Za-z0-9]{0,63}', dice_type):
                await message.channel.send('Choose one dice type, such as white.')
                return
            parts.append('type:' + dice_type)
        if view == 'overview' and game: parts[0] = 'summary'
        try:
            await show_statistics(message, ' '.join(parts), store)
        except Exception as error:
            logging.error('Slash statistics response failed (%s).', type(error).__name__)
            await message.channel.send('Statistics could not be displayed. Please try again later.')
