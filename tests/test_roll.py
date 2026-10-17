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
                         '**Tester** rolled **19**: 1d20 [20] - 1.')
        with patch.object(commands.random, 'randint', return_value=100) as rng:
            await commands.roll(self.message, '10d100')
        self.assertEqual(rng.call_count, 10)
        self.assertIn('**1000**', self.message.channel.send.call_args.args[0])

    async def test_invalid_input_does_not_roll(self):
        for expression in ['', '0d6', '11d6', 'd0', 'd101', '-2d6', '2d6+',
                           '2d6+-3', '2d6+1d8', '2d6+3+4', '2d6 trailing',
                           '1 0d6', 'd1 00', 'd6+1 2', '__import__("os")']:
            with self.subTest(expression=expression):
                with patch.object(commands.random, 'randint') as rng:
                    await commands.roll(self.message, expression)
                rng.assert_not_called()
                self.assertIn('!help roll', self.message.channel.send.call_args.args[0])

    async def test_help_uses_configured_limits(self):
        with patch.object(commands, 'MAX_ROLL_DICE', 12), patch.object(commands, 'MAX_ROLL_SIDES', 200):
            for alias in ['roll', 'dice']:
                await commands.help(self.message, alias)
                text = self.message.channel.send.call_args.args[0]
                self.assertIn('1-12 dice', text)
                self.assertIn('1-200 sides', text)
                self.assertIn('2d6 + 3', text)
