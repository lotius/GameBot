import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from cryptography.fernet import Fernet

import commands
from bot_store import BotStore
from roll_services import RollServices, dddice_payload, encrypt_key, forward_dddice
from setup_commands import setup


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = SimpleNamespace(id=77, guild=SimpleNamespace(id=12),
            author=SimpleNamespace(id=34, name='Tester'), channel=SimpleNamespace(id=56, send=AsyncMock()))
        self.policy = dict(rolls_enabled=True, logging_enabled=True, dddice_enabled=False,
                           integration_enabled=False, destination=None, default_destination=None, encrypted_key=None)
        self.service = Mock(policy=AsyncMock(return_value=self.policy), completed=AsyncMock())

    async def test_standard_roll_records_exact_displayed_values(self):
        with patch.object(commands.random, 'randint', side_effect=[2, 3]):
            await commands.process_command(self.message, 'roll', '2d6-1', self.service)
        result = self.service.completed.call_args.args[1]
        self.assertEqual([die['values']['value'] for die in result['results']], [2, 3])
        self.assertEqual(result['modifier'], -1)
        self.assertIn('**4**', self.message.channel.send.call_args.args[0])

    async def test_board_roll_records_the_displayed_faces_and_definition(self):
        with patch('boardgamedice.random.choice', return_value='skull.png'):
            await commands.process_command(self.message, 'hqroll', '2', self.service)
        roll = self.service.completed.call_args.args[1]
        self.assertEqual([die['values'] for die in roll['results']], [{'skulls': 1}, {'skulls': 1}])
        self.assertEqual(len(roll['definition']['diceTypes']['white']['faces']), 3)
        self.assertEqual(dddice_payload(roll, 'room')['dice'][0]['value'], '1')

    async def test_disabled_channel_and_invalid_input_do_not_record(self):
        self.policy['rolls_enabled'] = False
        await commands.process_command(self.message, 'roll', '2d6', self.service)
        self.message.channel.send.assert_not_awaited()
        self.service.completed.assert_not_awaited()
        self.policy['rolls_enabled'] = True
        await commands.process_command(self.message, 'roll', 'bad', self.service)
        self.service.completed.assert_not_awaited()

    async def test_failed_send_does_not_record(self):
        self.message.channel.send.side_effect = RuntimeError('Discord failed')
        with self.assertRaises(RuntimeError):
            await commands.process_command(self.message, 'roll', 'd6', self.service)
        self.service.completed.assert_not_awaited()

    async def test_disabled_logging_and_forwarding(self):
        store = Mock()
        self.policy['logging_enabled'] = False
        with patch('roll_services.forward_dddice') as forward:
            await RollServices(store).completed(self.message, {}, self.policy)
        store.record_roll.assert_not_called()
        forward.assert_not_called()

    async def test_new_configuration_commands(self):
        self.message.author.guild_permissions = SimpleNamespace(manage_guild=True)
        target = SimpleNamespace(id=56, send=AsyncMock(), permissions_for=Mock(
            return_value=SimpleNamespace(view_channel=True, send_messages=True)))
        self.message.guild.me = object()
        self.message.guild.get_channel_or_thread = Mock(return_value=target)
        store = Mock()
        for request, setting, value, channel in [
            ('logging off', 'logging', False, None),
            ('rolls <#56> off', 'rolls', False, 56),
            ('dddice on', 'dddice-enabled', True, None),
            ('dddice default room', 'dddice-default', 'room', None),
            ('dddice <#56> off', 'dddice-channel', False, 56),
        ]:
            await setup(self.message, request, store)
            expected = (12, 34, setting, value) + ((channel,) if channel is not None else ())
            self.assertEqual(store.change.call_args.args, expected)


class EncryptionTests(unittest.TestCase):
    def test_host_key_fallback_does_not_require_an_encrypted_server_key(self):
        with patch.dict(os.environ, {'DDDICE_API_KEY': 'host-test-key'}):
            policy = dict(destination='room', default_destination=None, encrypted_key=None)
            roll = dict(game='test', modifier=0, results=[dict(
                dice_type='red', dddice=dict(type='d6', theme='test-theme', value=2))])
            with patch('roll_services.requests.post', return_value=SimpleNamespace(ok=True)) as post:
                forward_dddice(policy, roll)
            self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer host-test-key')

    def test_encryption_and_exact_outcome_forwarding(self):
        with patch.dict(os.environ, {'INTEGRATION_ENCRYPTION_KEY': Fernet.generate_key().decode()}):
            ciphertext = encrypt_key('private-test-key')
            self.assertNotIn('private-test-key', ciphertext)
            policy = dict(destination='room', default_destination=None, encrypted_key=ciphertext)
            roll = dict(game='test', modifier=0, results=[dict(dice_type='red', dddice=dict(type='d6', theme='test-theme', value=4))])
            with patch('roll_services.requests.post', return_value=SimpleNamespace(ok=True)) as post:
                forward_dddice(policy, roll)
            self.assertEqual(post.call_args.kwargs['json']['dice'][0]['value'], '4')
            self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer private-test-key')

    def test_unmapped_dice_do_not_send_incorrect_results(self):
        with self.assertRaises(ValueError):
            dddice_payload({'results': [{'dice_type': 'other'}], 'modifier': 0}, 'room')

    def test_duplicate_roll_does_not_append_new_results(self):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        cursor = Mock(rowcount=0)
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection.cursor.return_value = cursor
        message = SimpleNamespace(id=77, guild=SimpleNamespace(id=12), channel=SimpleNamespace(id=56), author=SimpleNamespace(id=34))
        roll = dict(game='standard', command='roll', results=[{}], modifier=0, definition={})
        BotStore(lambda: connection).record_roll(message, roll)
        cursor.executemany.assert_not_called()
        connection.rollback.assert_called_once()
