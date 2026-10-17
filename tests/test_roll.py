import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import commands


class RollTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(author=SimpleNamespace(name='Tester'),
                                       channel=SimpleNamespace(send=AsyncMock()))

    async def test_modifiers_and_whitespace(self):
        for expression, expected in [
            ('2d6+3', '**Tester** rolled **12**: 2d6 [4, 5] + 3.'),
            (' 2 D 6 + 3\t', '**Tester** rolled **12**: 2d6 [4, 5] + 3.'),
            ('2d6 - 12', '**Tester** rolled **-3**: 2d6 [4, 5] - 12.'),
            ('2d6', '**Tester** rolled **9**: 2d6 [4, 5].'),
            ('2d6+0', '**Tester** rolled **9**: 2d6 [4, 5] + 0.'),
        ]:
            with self.subTest(expression=expression):
                with patch.object(commands.random, 'randint', side_effect=[4, 5]) as rng:
                    await commands.process_command(self.message, 'roll', expression)
                self.assertEqual(rng.call_count, 2)
                rng.assert_called_with(1, 6)
                self.assertEqual(self.message.channel.send.call_args.args[0], expected)

    async def test_default_count_alias_and_boundary(self):
        with patch.object(commands.random, 'randint', return_value=20) as rng:
            await commands.process_command(self.message, 'dice', ' d20 - 1 ')
        rng.assert_called_once_with(1, 20)
        self.assertEqual(self.message.channel.send.call_args.args[0],
                         '**Tester** rolled **19**: 1d20 [**20**] - 1.')
        with patch.object(commands.random, 'randint', return_value=100) as rng:
            await commands.roll(self.message, '10d100')
        self.assertEqual(rng.call_count, 10)
        self.assertIn('**1000**', self.message.channel.send.call_args.args[0])

    async def test_invalid_input_does_not_roll(self):
        for expression in ['', '0d6', '11d6', 'd0', 'd101', '-2d6', '2d6+',
                           '2d6+-3', 'd20 adv dis', '4d6kh0', '4d6kh5', 'd1!', '6d6+1>=5', '10d6+d8',
                           '1 0d6', 'd1 00', 'd6+1 2', '__import__("os")']:
            with self.subTest(expression=expression):
                with patch.object(commands.random, 'randint') as rng:
                    await commands.roll(self.message, expression)
                rng.assert_not_called()
                self.assertIn('!help roll', self.message.channel.send.call_args.args[0])

    async def test_help_uses_configured_limits(self):
        with patch.object(commands, 'MAX_ROLL_DICE', 12), patch.object(commands, 'MAX_ROLL_SIDES', 200):
            for alias in ['roll', 'dice']:
                self.message.channel.send.reset_mock()
                await commands.help(self.message, alias)
                self.message.channel.send.assert_awaited_once()
                text = self.message.channel.send.call_args.args[0]
                self.assertLessEqual(len(text), 2000)
                self.assertIn('1-12 dice', text)
                self.assertIn('1-200 sides', text)
                self.assertIn('2d6 + 3', text)


class AdvancedRollTests(unittest.IsolatedAsyncioTestCase):
    async def run_roll(self, expression, values):
        message = SimpleNamespace(author=SimpleNamespace(name='Tester'), channel=SimpleNamespace(send=AsyncMock()))
        with patch.object(commands.random, 'randint', side_effect=values):
            result = await commands.roll(message, expression)
        return message.channel.send.call_args.args[0], result

    async def test_mixed_dice_and_labels(self):
        text, result = await self.run_roll('2d6 + d8 + 3 Sneak', [2, 4, 7])
        self.assertIn('**16** (Sneak)', text)
        self.assertEqual([r['dice_type'] for r in result['results']], ['d6', 'd6', 'd8'])

    async def test_keep_and_advantage(self):
        text, result = await self.run_roll('4d6kh3 Ability', [1, 6, 4, 5])
        self.assertIn('**15**', text)
        self.assertIn('~~1~~', text)
        self.assertEqual(len(result['results']), 3)
        text, result = await self.run_roll('d20+5 adv Stealth', [1, 20])
        self.assertIn('**25**', text)
        self.assertIn('~~**1**~~', text)
        text, result = await self.run_roll('d20 dis', [18, 3])
        self.assertIn('**3**', text)
        text, result = await self.run_roll('4d6kl2', [6, 2, 2, 5])
        self.assertIn('**4**', text)
        self.assertEqual(len(result['results']), 2)

    async def test_successes_and_explosion_chains(self):
        text, result = await self.run_roll('6d6>=5 Attack', [1, 5, 6, 2, 5, 3])
        self.assertIn('**3 successes**', text)
        self.assertEqual(sum(r['values']['value'] for r in result['results']), 3)
        text, result = await self.run_roll('2d6kh1!>=5', [6, 5, 4])
        self.assertIn('**2 successes**', text)
        self.assertIn('~~4~~', text)
        self.assertEqual(len(result['results']), 2)

    async def test_explosion_limit(self):
        text, result = await self.run_roll('d6!', [6] * 21)
        self.assertEqual(len(result['results']), 21)
        self.assertIn('Explosion limit reached', text)

    async def test_subtraction_and_escaped_label(self):
        text, result = await self.run_roll('d6 - d4 + 2 Test_*', [5, 3])
        self.assertIn('**4**', text)
        self.assertIn('Test\\_\\*', text)
        self.assertEqual(result['results'][1]['values']['value'], -3)
