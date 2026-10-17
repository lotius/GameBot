from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import discord
from discord import app_commands

from statistics_commands import parse_options, show_statistics, register_statistics_command, csv_cell


class StatisticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(author=SimpleNamespace(id=123),
            guild=SimpleNamespace(id=456, me=object(), get_member=Mock(return_value=SimpleNamespace(display_name='Tester')),
                                  get_channel_or_thread=Mock(return_value=object())),
            channel=SimpleNamespace(id=789, send=AsyncMock(), permissions_for=Mock(return_value=SimpleNamespace(attach_files=True))))
        self.store = Mock()

    def test_filters_and_aliases(self):
        options = parse_options('faces hqroll me week type:dew here', self.message,
                                now=datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
        self.assertEqual(options['game'], 'hqdice')
        self.assertEqual(options['dice_type'], 'gen24')
        self.assertEqual(options['user'], 123)
        self.assertEqual(options['channel'], 789)
        self.assertEqual(options['since'], datetime(2026, 10, 6, 12))
        self.assertEqual(parse_options('', self.message)['view'], 'overview')
        self.assertEqual(parse_options('hqroll', self.message)['view'], 'summary')

    def test_invalid_filters(self):
        for text in ['faces recent', 'hqroll doomroll', 'week month', '0d',
                     'since:bad', 'since:2026-10-13 until:2026-10-01',
                     'type:white', 'roll type:purple', 'hqroll type:unknown', '"unterminated',
                     'hqroll me me', 'unknown-filter']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_options(text, self.message)

    async def test_overview_and_help(self):
        with patch('statistics_commands.StatisticsStore.query', return_value=((3, 6, 1, None, None), [('hqdice', 3, 6)])):
            await show_statistics(self.message, '', self.store)
        embed = self.message.channel.send.call_args.kwargs['embed']
        self.assertIn('HeroQuest', embed.description)
        self.assertIn('3 commands', embed.description)
        self.assertNotIn('?', embed.title + embed.description + embed.footer.text)
        await show_statistics(self.message, 'help', self.store)
        self.assertIn('Statistics commands', self.message.channel.send.call_args.kwargs['embed'].title)
        self.assertNotIn('?', self.message.channel.send.call_args.kwargs['embed'].description)

    async def test_leaderboard_fetches_current_name_without_showing_user_id(self):
        user_id = 987654321012345678
        self.message.guild.get_member.return_value = None
        self.message.guild.fetch_member = AsyncMock(return_value=SimpleNamespace(display_name='Current Nickname'))
        with patch('statistics_commands.StatisticsStore.query', return_value=(
                (3, 6, 1, None, None), [(user_id, 3, 6)])):
            await show_statistics(self.message, 'leaderboard', self.store)
        self.message.guild.fetch_member.assert_awaited_once_with(user_id)
        text = self.message.channel.send.call_args.kwargs['embed'].description
        self.assertIn('Current Nickname', text)
        self.assertNotIn(str(user_id), text)

    async def test_recent_filter_and_export_use_names_instead_of_user_ids(self):
        user_id = 987654321012345678
        self.message.author.id = user_id
        self.message.guild.get_member.return_value = None
        self.message.guild.fetch_member = AsyncMock(return_value=SimpleNamespace(display_name='Current Name'))
        rows = [(1, datetime(2026, 10, 13), user_id, 789, 'standard', 0, 0, 'd6', '4', '{"value":4}')]
        with patch('statistics_commands.StatisticsStore.query', return_value=((1, 1, 1, None, None), rows)):
            await show_statistics(self.message, 'recent me', self.store)
        embed = self.message.channel.send.call_args.kwargs['embed']
        self.assertIn('Current Name', embed.description)
        self.assertIn('Current Name', embed.footer.text)
        self.assertNotIn(str(user_id), embed.description + embed.footer.text)
        exports = []
        async def capture(*args, **kwargs):
            if 'file' in kwargs:
                exports.append(kwargs['file'].fp.read().decode('utf-8-sig'))
        self.message.channel.send.side_effect = capture
        with patch('statistics_commands.StatisticsStore.query', return_value=((1, 1, 1, None, None), rows)):
            await show_statistics(self.message, 'export me', self.store)
        self.assertIn('player_name', exports[0])
        self.assertIn('Current Name', exports[0])
        self.assertNotIn(str(user_id), exports[0])
        self.assertNotIn('user_id', exports[0])

    async def test_faces_values_and_expected_comparison(self):
        groups = [('hqdice', 'white', 'skull.png', '{"skulls":1}', 3)]
        for view in ['faces', 'values', 'summary', 'compare']:
            rows = (groups, {('hqdice', 'white', 'skull.png'): 1.5,
                             ('hqdice', 'white', 'whiteshield.png'): 1.0,
                             ('hqdice', 'white', 'blackshield.png'): 0.5}) if view == 'compare' else groups
            with patch('statistics_commands.StatisticsStore.query', return_value=((1, 3, 1, None, None), rows)):
                await show_statistics(self.message, f'{view} hqroll', self.store)
            text = self.message.channel.send.call_args.kwargs['embed'].description
            if view == 'compare':
                self.assertIn('expected 50.0%', text)
                self.assertIn('HeroQuest / whiteshield', text)
            elif view in ('values', 'summary'):
                self.assertIn('3.00 per command', text)

    async def test_variants_combine_faces_and_weight_expected_frequencies(self):
        groups = [('hqdice', 'white', 'skull.png', '{"skulls":1}', 3),
                  ('hqdice', 'black', 'skull-black.png', '{"skulls":1}', 5),
                  ('hqdice', 'black', 'blackshield-black.png', '{"black_shields":1}', 2),
                  ('hqdice', 'orange', 'doubleskull-orange.png', '{"skulls":2}', 2)]
        expected = {('hqdice', 'white', 'skull.png'): 1.5,
                    ('hqdice', 'black', 'skull-black.png'): 3.5,
                    ('hqdice', 'black', 'blackshield-black.png'): 3.5,
                    ('hqdice', 'orange', 'doubleskull-orange.png'): 3.5}
        with patch('statistics_commands.StatisticsStore.query', return_value=(
                (2, 12, 1, None, None), (groups, expected))):
            await show_statistics(self.message, 'compare hqroll', self.store)
        text = self.message.channel.send.call_args.kwargs['embed'].description
        self.assertIn('HeroQuest / skull**: 8 (66.7%) | expected 41.7%', text)
        self.assertIn('HeroQuest / doubleskull**: 2 (16.7%)', text)
        self.assertNotIn('skull black', text)
        with patch('statistics_commands.StatisticsStore.query', return_value=(
                (1, 7, 1, None, None), groups[1:3])):
            await show_statistics(self.message, 'faces hqroll type:black', self.store)
        text = self.message.channel.send.call_args.kwargs['embed'].description
        self.assertIn('HeroQuest / black / skull**: 5 (71.4%)', text)
        self.assertIn('HeroQuest / black / blackshield**: 2 (28.6%)', text)
        self.assertNotIn('blackshield black', text)

    async def test_no_data_and_database_outage_are_clear(self):
        with patch('statistics_commands.StatisticsStore.query', return_value=((0, 0, 0, None, None), [])):
            await show_statistics(self.message, 'hqroll', self.store)
        self.assertIn('No recorded rolls', self.message.channel.send.call_args.kwargs['embed'].title)
        with patch('statistics_commands.StatisticsStore.query', side_effect=RuntimeError('Offline')):
            with self.assertLogs(level='ERROR'):
                await show_statistics(self.message, 'hqroll', self.store)
        self.assertIn('temporarily unavailable', self.message.channel.send.call_args.args[0])

    def test_csv_formula_protection(self):
        self.assertEqual(csv_cell('=SUM(A1)'), "'=SUM(A1)")
        self.assertEqual(csv_cell('skull.png'), 'skull.png')

    async def test_private_slash_statistics(self):
        client = discord.Client(intents=discord.Intents.default())
        tree = app_commands.CommandTree(client)
        register_statistics_command(tree, self.store)
        interaction = SimpleNamespace(guild=self.message.guild, guild_id=456, user=self.message.author,
            channel=self.message.channel, channel_id=789,
            response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
        with patch('statistics_commands.StatisticsStore.query', return_value=((0, 0, 0, None, None), [])):
            await tree.get_command('stats').callback(interaction, private=True)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        self.assertTrue(interaction.followup.send.call_args.kwargs['ephemeral'])
