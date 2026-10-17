import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import cv2
import numpy as np

import boardgamedice as board
import commands


class DiceTests(unittest.TestCase):
    def test_random_color_defaults_to_one_and_rejects_color_selection(self):
        self.assertEqual(board.parse_dice('rollColor', ''), ('rollcolor', {'random': 1}))
        for param in ('red', '1 red', '2', '2 random'):
            with self.subTest(param=param), self.assertRaises(ValueError):
                board.parse_dice('rollcolor', param)
        faces = board.dice_sets['rollcolor']['diceTypes']['random']['faces']
        self.assertEqual(len(faces), 7)
        self.assertTrue(all(face['numOfFaces'] == 1 for face in faces))

    def test_commands_and_type_aliases(self):
        for game, data in board.dice_sets.items():
            for command in [game] + data.get('aliases', []):
                self.assertEqual(board.resolve_game(command.upper()), game)
            for name, die in data['diceTypes'].items():
                for alias in [name] + die.get('aliases', []):
                    self.assertEqual(board.parse_dice(game, f'1 {alias}'), (game, {name: 1}))
        self.assertEqual(board.parse_dice('hqroll', '15'), ('hqdice', {'white': 15}))
        self.assertEqual(board.parse_dice('scroll', '  1 W\t 2 R  ')[1], {'white': 1, 'red': 2})

    def test_invalid_requests_and_limits(self):
        for param in ['', '1', 'red', '1 red extra', '-1 red', '1.5 red',
                      '0 red', '1 unknown', '5 red', '1 red 1 r', '1 r 1 red']:
            with self.subTest(param=param), self.assertRaises(ValueError):
                board.parse_dice('scdice', param)
        for game, data in board.dice_sets.items():
            first = next(iter(data['diceTypes']))
            with self.assertRaises(ValueError):
                board.parse_dice(game, f"{data['maxNumberOfTotalDice'] + 1} {first}")
            for name, die in data['diceTypes'].items():
                maximum = die.get('maxNumberOfDiceType') or data['maxNumberOfTotalDice']
                board.parse_dice(game, f'{maximum} {name}')
                with self.assertRaises(ValueError):
                    board.parse_dice(game, f'{maximum + 1} {name}')
        with self.assertRaises(ValueError):
            board.parse_dice('drgdice', '2 red 2 blue')
        with self.assertRaises(ValueError):
            board.parse_dice('descentdice', '1 gray 1 grey')

    def test_every_configured_face_renders_with_weighting(self):
        for game, data in board.dice_sets.items():
            for name, die in data['diceTypes'].items():
                weighted = [face['face'] for face in die['faces'] for _ in range(face['numOfFaces'])]
                for filename in set(weighted):
                    with self.subTest(game=game, die=name, face=filename):
                        with patch.object(board.random, 'choice', return_value=filename) as choice:
                            stream = board.render_roll(game, {name: 1})
                        choice.assert_called_once_with(weighted)
                        image = cv2.imdecode(np.frombuffer(stream.getvalue(), np.uint8), cv2.IMREAD_UNCHANGED)
                        original = cv2.imread(str(board.ROOT / 'images' / data['imageDirectory'] / filename), cv2.IMREAD_UNCHANGED)
                        self.assertEqual(image.shape, (100, 108, 4))
                        np.testing.assert_array_equal(image[:, :, :3], original[:, :, :3])
                        expected_alpha = original[:, :, 3] if original.shape[2] == 4 else np.full((100, 108), 255)
                        np.testing.assert_array_equal(image[:, :, 3], expected_alpha)

    def test_help_examples_obey_game_limits(self):
        for game, data in board.dice_sets.items():
            for _ in range(20):
                text = board.generate_help(game)
                self.assertIn(f"**{data['name']} Dice Help**", text)
                self.assertIn('Max dice per roll:', text)
                self.assertIn('Available dice types:', text)
                for name, die in data['diceTypes'].items():
                    self.assertIn(name, text)
                    for alias in die.get('aliases', []):
                        self.assertIn(alias, text)
                examples = text.split('**Examples:**\n')[1].splitlines()
                self.assertTrue(2 <= len(examples) <= 4)
                for example in examples:
                    command, param = example[1:].split(' ', 1)
                    board.parse_dice(command, param)
                if data.get('defaultDiceType'):
                    self.assertIn(f"the default '{data['defaultDiceType']['typeToUse']}'", text)
                    self.assertTrue(examples[0].split(' ', 1)[1].isdigit())

    def test_streams_are_independent(self):
        first = board.render_roll('hqdice', {'white': 2})
        saved = first.getvalue()
        second = board.render_roll('hqdice', {'white': 1})
        self.assertIsNot(first, second)
        self.assertEqual(first.getvalue(), saved)
        image = cv2.imdecode(np.frombuffer(saved, np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(image.shape, (100, 216, 4))


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(channel=SimpleNamespace(send=AsyncMock()),
                                       author=SimpleNamespace(name='Tester'))

    async def test_roll_dispatch_and_help_for_every_alias(self):
        for game, data in board.dice_sets.items():
            name = next(iter(data['diceTypes']))
            for command in [game] + data.get('aliases', []):
                self.message.channel.send.reset_mock()
                await commands.process_command(self.message, command, f'1 {name}')
                attachment = self.message.channel.send.call_args.kwargs['file']
                self.assertEqual(attachment.filename, f'{game}-results.png')
                with patch.object(board.random, 'randint', side_effect=lambda low, high: low):
                    with patch.object(board.random, 'sample', side_effect=lambda population, count: population[:count]):
                        await commands.process_command(self.message, 'help', command)
                        self.assertEqual(self.message.channel.send.call_args.args[0], board.generate_help(game))

    async def test_invalid_roll_sends_feedback(self):
        with patch.object(board, 'render_roll') as render:
            await commands.process_command(self.message, 'doomroll', '3 black')
        render.assert_not_called()
        self.assertIn('more than 2 black', self.message.channel.send.call_args.args[0])

    async def test_added_game_automatically_has_dispatch_and_help(self):
        metadata = dict(board.dice_sets['scdice'], name='New Game', aliases=['newroll'])
        with patch.dict(board.dice_sets, {'newdice': metadata}):
            await commands.process_command(self.message, 'help', '')
            overview = self.message.channel.send.call_args.args[0]
            for command in ['!newdice', '!newroll', '!roll']:
                self.assertIn(command, overview)
            self.assertLessEqual(len(overview), 2000)
            await commands.process_command(self.message, 'newroll', '1 red')
            self.assertEqual(self.message.channel.send.call_args.kwargs['file'].filename, 'newdice-results.png')
            await commands.process_command(self.message, 'help', 'newroll')
            self.assertIn('New Game', self.message.channel.send.call_args.args[0])

    async def test_preserved_commands(self):
        await commands.process_command(self.message, 'roll', '2D6')
        self.assertIn('Tester', self.message.channel.send.call_args.args[0])



if __name__ == '__main__':
    unittest.main()
