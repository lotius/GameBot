"""Moderator setup commands and persistent per-server settings."""
import asyncio
import logging
import re
import os
import discord

from database import connect
from bot_store import BotStore
from setup_permissions import can_manage_bot


class GuildSettingsStore(BotStore):
    def __init__(self, connection_factory=connect):
        self.connection_factory = connection_factory

    def _ensure_table(self, cursor):
        cursor.execute("""CREATE TABLE IF NOT EXISTS gamebot_guild_settings (
            guild_id BIGINT UNSIGNED PRIMARY KEY,
            instruction_channel_id BIGINT UNSIGNED NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    def set_instruction_channel(self, guild_id, channel_id, actor_id):
        self.change(guild_id, actor_id, 'instructions', channel_id)

    def get_instruction_channel(self, guild_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                self._ensure_table(cursor)
                cursor.execute('SELECT instruction_channel_id FROM gamebot_guild_settings WHERE guild_id=%s', (guild_id,))
                row = cursor.fetchone()
                return row[0] if row else None

    def instruction_destinations(self):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                self._ensure_table(cursor)
                cursor.execute('SELECT guild_id, instruction_channel_id FROM gamebot_guild_settings '
                               'WHERE instruction_channel_id IS NOT NULL')
                return cursor.fetchall()


async def setup(message, param, store):
    if message.guild is None:
        await message.channel.send('Run setup inside a Discord server.')
        return
    if not await can_manage_bot(message.guild, message.author, store):
        await message.channel.send('You need Manage Server permission or the configured bot administrator role.')
        return
    tokens = param.strip().split()
    if tokens and tokens[0].lower() != 'instructions':
        await configure(message, tokens, store)
        return
    if len(tokens) != 2 or tokens[0].lower() != 'instructions':
        await message.channel.send('Use /setup instructions with action:set and a channel, action:off, or action:status.')
        return
    target = tokens[1].lower()
    channel_id = None
    if target not in ('off', 'status'):
        match = re.fullmatch(r'(?:<#([0-9]+)>|([0-9]+))', target)
        channel = message.guild.get_channel_or_thread(int(match[1] or match[2])) if match else None
        if channel is None or not hasattr(channel, 'send'):
            await message.channel.send('Choose a text, voice, stage, or thread channel in this server using a channel mention or ID.')
            return
        permissions = channel.permissions_for(message.guild.me)
        if not permissions.view_channel or not (permissions.send_messages_in_threads if isinstance(channel, discord.Thread) else permissions.send_messages):
            await message.channel.send('I need View Channel and Send Messages permissions in that channel.')
            return
        channel_id = channel.id
    try:
        if target == 'status':
            current = await asyncio.to_thread(store.get_instruction_channel, message.guild.id)
            await message.channel.send(f'Instruction announcements: <#{current}>.' if current else 'Instruction announcements are off. Choose a channel with /setup instructions action:set channel:#announcements.')
            return
        await asyncio.to_thread(store.set_instruction_channel, message.guild.id, channel_id, message.author.id)
    except Exception:
        logging.exception('Could not save or read server setup.')
        await message.channel.send('The database is unavailable. Your setup was not confirmed; please try again later.')
        return
    await message.channel.send(f'Instruction announcements will go to <#{channel_id}>. Checks run every 15 minutes.' if channel_id else 'Instruction announcements are now off for this server.')


async def configure(message, tokens, store):
    usage = ('Use the private /setup commands: rolls action:on|off channel:#channel; '
             'logging action:on|off; dddice action:<room-slug>|on|off with an optional channel; '
             'dddice action:"default <room-slug>"; spam action:on|off or action:"<count> <seconds>"; '
             'retention action:on|off or action:<days>; /setup status. '
             'Use /dddice-key to enter an API key privately.')
    guild_id, actor = message.guild.id, message.author.id
    kind = tokens[0].lower()
    try:
        if kind == 'status' and len(tokens) == 1:
            policy = await asyncio.to_thread(store.policy, guild_id, message.channel.id)
            await message.channel.send(
                f"This channel: rolls {'on' if policy['rolls_enabled'] else 'off'}, "
                f"dddice {'on' if policy['dddice_enabled'] else 'off'}, "
                f"room {policy['destination'] or policy['default_destination'] or 'unset'}.\n"
                f"Server: logging {'on' if policy['logging_enabled'] else 'off'}, "
                f"dddice {'on' if policy['integration_enabled'] else 'off'}, "
                f"API key {'configured' if policy['encrypted_key'] else ('host fallback' if os.getenv('DDDICE_API_KEY') else 'unset')}.\n"
                f"Spam: {'on' if policy.get('spam_enabled', True) else 'off'}, {policy.get('spam_limit', 5)} commands / {policy.get('spam_window_seconds', 10)} seconds.\n"
                f"Retention: {'on' if policy.get('retention_enabled', False) else 'off'}, {policy.get('retention_days', 90)} days."
            )
            return
        if kind in ('spam', 'retention'):
            if len(tokens) == 2 and tokens[1].lower() in ('on', 'off'):
                await asyncio.to_thread(store.change, guild_id, actor, kind + '-enabled', tokens[1].lower() == 'on')
            elif kind == 'spam' and len(tokens) == 3 and all(re.fullmatch('[0-9]{1,4}', token) for token in tokens[1:]):
                count, seconds = map(int, tokens[1:])
                if not 1 <= count <= 100 or not 1 <= seconds <= 3600:
                    await message.channel.send('Spam limits: 1-100 commands per 1-3600 seconds.')
                    return
                await asyncio.to_thread(store.change, guild_id, actor, 'spam-limit', count)
                await asyncio.to_thread(store.change, guild_id, actor, 'spam-window', seconds)
            elif kind == 'retention' and len(tokens) == 2 and re.fullmatch('[0-9]{1,5}', tokens[1]) and 1 <= int(tokens[1]) <= 36500:
                await asyncio.to_thread(store.change, guild_id, actor, 'retention-days', int(tokens[1]))
            else:
                await message.channel.send('Use /setup spam action:on|off or action:"<count> <seconds>"; /setup retention action:on|off or action:<days>. Set days before enabling: old statistics are permanently deleted.')
                return
        elif kind == 'logging'  and len(tokens) == 2 and tokens[1].lower() in ('on', 'off'):
            await asyncio.to_thread(store.change, guild_id, actor, 'logging', tokens[1].lower() == 'on')
        elif kind == 'dddice' and len(tokens) == 2 and tokens[1].lower() in ('on', 'off'):
            await asyncio.to_thread(store.change, guild_id, actor, 'dddice-enabled', tokens[1].lower() == 'on')
        elif kind == 'dddice' and len(tokens) == 3 and tokens[1].lower() == 'default':
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', tokens[2]):
                await message.channel.send('Enter a dddice room slug, not its URL.')
                return
            await asyncio.to_thread(store.change, guild_id, actor, 'dddice-default', tokens[2])
        elif kind in ('rolls', 'dddice') and len(tokens) == 3:
            match = re.fullmatch(r'(?:<#([0-9]+)>|([0-9]+))', tokens[1])
            channel = message.guild.get_channel_or_thread(int(match[1] or match[2])) if match else None
            if channel is None or not hasattr(channel, 'send'):
                await message.channel.send('Choose a text, voice, stage, or thread channel in this server.')
                return
            permissions = channel.permissions_for(message.guild.me)
            disabling = tokens[2].lower() == 'off'
            if not disabling and (not permissions.view_channel or not (permissions.send_messages_in_threads if isinstance(channel, discord.Thread) else permissions.send_messages)):
                await message.channel.send('I need View Channel and Send Messages permissions there.')
                return
            value = tokens[2].lower()
            if kind == 'rolls':
                if value not in ('on', 'off'):
                    await message.channel.send(usage)
                    return
                await asyncio.to_thread(store.change, guild_id, actor, 'rolls', value == 'on', channel.id)
            elif value == 'off':
                await asyncio.to_thread(store.change, guild_id, actor, 'dddice-channel', False, channel.id)
            else:
                if value != 'on' and not re.fullmatch(r'[A-Za-z0-9_-]{1,255}', tokens[2]):
                    await message.channel.send('Enter a dddice room slug, on, or off.')
                    return
                if value != 'on':
                    await asyncio.to_thread(store.change, guild_id, actor, 'dddice-room', tokens[2], channel.id)
                await asyncio.to_thread(store.change, guild_id, actor, 'dddice-channel', True, channel.id)
        else:
            await message.channel.send(usage)
            return
    except Exception:
        logging.exception('Configuration operation failed.')
        await message.channel.send('The database is unavailable. Setup was not confirmed; please check status before retrying.')
        return
    await message.channel.send('Saved server settings. Use /setup status in the affected channel to review.')
