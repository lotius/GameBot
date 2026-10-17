import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import boardgamedice as board
import commands
from instructions import Instruction, check_instructions
from roll_services import RollServices
from setup_commands import setup


class MetadataTests(unittest.TestCase):
    def test_rejects_invalid_values_mappings_and_reserved_commands(self):
        original = board._loaded_source
        cases = []
        for values in [{'skulls': 'one'}, {'skulls': True}, {'skulls': float('inf')}, []]:
            data = json.loads(original)
            data['hqdice']['diceTypes']['white']['faces'][0]['values'] = values
            cases.append(data)
        data = json.loads(original)
        data['hqdice']['aliases'].append('stats')
        cases.append(data)
        for mapping in [{'type': 'd0', 'theme': 'theme'}, {'type': 'd6', 'theme': ''}, 'theme']:
            data = json.loads(original)
            data['hqdice']['diceTypes']['white']['dddice'] = mapping
            cases.append(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dice.json'
            with patch.object(board, 'DICE_FILE', path):
                for data in cases:
                    path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        board.reload_dice_sets()
                    self.assertEqual(board._loaded_source, original)


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(id=1, guild=SimpleNamespace(id=2),
            channel=SimpleNamespace(id=3, send=AsyncMock()),
            author=SimpleNamespace(id=4, name='Tester', guild_permissions=SimpleNamespace(manage_guild=True)))

    async def test_outage_rolls_without_saving_or_forwarding(self):
        store = Mock()
        store.policy.side_effect = RuntimeError('Offline')
        service = RollServices(store)
        with self.assertLogs(level='WARNING'), patch('roll_services.forward_dddice') as forward:
            await commands.process_command(self.message, 'roll', 'd6', service)
        store.record_roll.assert_not_called()
        forward.assert_not_called()
        self.assertIn('not recorded', self.message.channel.send.call_args.args[0])
        await service.policy(self.message)
        self.assertEqual(store.policy.call_count, 1)

    async def test_outage_preserves_cached_disabled_channel(self):
        service = RollServices(Mock())
        service.cache[(2, 3)] = {'rolls_enabled': False}
        service.retry_after = float('inf')
        await commands.process_command(self.message, 'roll', 'd6', service)
        self.message.channel.send.assert_not_awaited()

    async def test_spam_window_and_off(self):
        service = RollServices(Mock())
        policy = dict(spam_enabled=True, spam_limit=2, spam_window_seconds=10)
        with patch('roll_services.time.monotonic', return_value=100):
            self.assertTrue(service.admit(self.message, policy))
            self.assertTrue(service.admit(self.message, policy))
            self.assertFalse(service.admit(self.message, policy))
        with patch('roll_services.time.monotonic', return_value=110):
            self.assertTrue(service.admit(self.message, policy))
        policy['spam_enabled'] = False
        for _ in range(10):
            self.assertTrue(service.admit(self.message, policy))

    async def test_configuration_bounds_and_retention_stays_separate(self):
        store = Mock()
        for text in ['spam 0 10', 'spam 101 10', 'spam 5 3601', 'retention 0', 'retention -1']:
            await setup(self.message, text, store)
            store.change.assert_not_called()
        await setup(self.message, 'retention 30', store)
        store.change.assert_called_once_with(2, 4, 'retention-days', 30)
        store.change.reset_mock()
        await setup(self.message, 'retention on', store)
        store.change.assert_called_once_with(2, 4, 'retention-enabled', True)

    async def test_instruction_db_failures_prevent_send_or_repeats(self):
        entry = Instruction('test', 'Test', 'https://example.com')
        for failed_method in ['was_sent', 'reserve']:
            store = Mock()
            store.was_sent.return_value = False
            store.discover.return_value = [entry]
            getattr(store, failed_method).side_effect = RuntimeError('Offline')
            with patch('instructions.fetch_instructions', return_value=[entry]):
                with self.assertRaises(RuntimeError):
                    await check_instructions(self.message.channel, store)
            self.message.channel.send.assert_not_awaited()
        store = Mock()
        store.was_sent.return_value = False
        store.discover.return_value = [entry]
        store.reserve.return_value = False
        with patch('instructions.fetch_instructions', return_value=[entry]):
            await check_instructions(self.message.channel, store)
        self.message.channel.send.assert_not_awaited()
