from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import commands
from message_router import dispatch_message, parse_message


class RouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.permissions = SimpleNamespace(view_channel=True, send_messages=True, attach_files=True)
        self.message = SimpleNamespace(id=1, guild=SimpleNamespace(id=2, me=object()),
            author=SimpleNamespace(bot=False), webhook_id=None, is_system=Mock(return_value=False),
            attachments=[], content='!roll 3d4-3',
            channel=SimpleNamespace(send=AsyncMock(), permissions_for=Mock(return_value=self.permissions)))

    async def test_ignores_unrelated_messages_without_dispatch(self):
        for content in ['', 'hello', '!', '!!roll 2d6', '! roll 2d6', '!unknown', '!terry', '!disappointed', '<@123> roll', '!roll2d6']:
            self.message.content = content
            with patch('message_router.commands.process_command', new_callable=AsyncMock) as process:
                await dispatch_message(self.message, Mock(), SimpleNamespace(policy=AsyncMock(return_value={}), admit=Mock(return_value=True)))
                process.assert_not_awaited()
        self.message.channel.send.assert_not_awaited()

    async def test_ignores_dm_bot_webhook_system_and_attachment(self):
        for field, value in [('guild', None), ('webhook_id', 123), ('attachments', [object()])]:
            original = getattr(self.message, field)
            setattr(self.message, field, value)
            self.assertIsNone(parse_message(self.message))
            setattr(self.message, field, original)
        self.message.author.bot = True
        self.assertIsNone(parse_message(self.message))
        self.message.author.bot = False
        self.message.is_system.return_value = True
        self.assertIsNone(parse_message(self.message))

    async def test_case_whitespace_and_board_alias(self):
        for content, expected in [('!ROLL\t 3d4-3 ', ('roll', '3d4-3')),
                                  ('!hqroll\n2 pink', ('hqroll', '2 pink'))]:
            self.message.content = content
            self.assertEqual(parse_message(self.message), expected)

    async def test_missing_permissions_and_oversized_input(self):
        self.permissions.send_messages = False
        await dispatch_message(self.message, Mock(), SimpleNamespace(policy=AsyncMock(return_value={}), admit=Mock(return_value=True)))
        self.message.channel.send.assert_not_awaited()
        self.permissions.send_messages = True
        self.message.content = '!roll ' + '9' * 2000
        await dispatch_message(self.message, Mock(), SimpleNamespace(policy=AsyncMock(return_value={}), admit=Mock(return_value=True)))
        self.assertIn('too long', self.message.channel.send.call_args.args[0])
        self.message.content = '!hqroll 3'
        self.permissions.attach_files = False
        await dispatch_message(self.message, Mock(), SimpleNamespace(policy=AsyncMock(return_value={}), admit=Mock(return_value=True)))
        self.assertIn('Attach Files', self.message.channel.send.call_args.args[0])

    async def test_unexpected_handler_failure_is_contained(self):
        with patch('message_router.commands.process_command', new_callable=AsyncMock,
                   side_effect=RuntimeError('Failure')):
            with self.assertLogs(level='ERROR'):
                await dispatch_message(self.message, Mock(), SimpleNamespace(policy=AsyncMock(return_value={}), admit=Mock(return_value=True)))
        self.assertIn('could not be completed', self.message.channel.send.call_args.args[0])

    async def test_long_help(self):
        await commands.send_text(self.message, 'x' * 4500)
        texts = [call.args[0] for call in self.message.channel.send.call_args_list]
        self.assertTrue(all(len(text) <= 1900 for text in texts))
        self.assertEqual(''.join(texts), 'x' * 4500)

    async def test_stats_dispatches_to_statistics_handler(self):
        self.message.content = '!stats help'
        store = Mock()
        services = SimpleNamespace(store=store, policy=AsyncMock(return_value={}),
                                   admit=Mock(return_value=True))
        await dispatch_message(self.message, store, services)
        embed = self.message.channel.send.call_args.kwargs['embed']
        self.assertEqual(embed.title, 'Statistics commands')
