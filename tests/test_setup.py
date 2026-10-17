import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from setup_commands import setup


class SetupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.target = SimpleNamespace(id=456, send=AsyncMock(),
            permissions_for=Mock(return_value=SimpleNamespace(view_channel=True, send_messages=True)))
        self.guild = SimpleNamespace(id=123, me=object(), get_channel_or_thread=Mock(return_value=self.target))
        self.message = SimpleNamespace(guild=self.guild, channel=SimpleNamespace(send=AsyncMock()),
            author=SimpleNamespace(id=789, guild_permissions=SimpleNamespace(manage_guild=True)))
        self.store = Mock()

    async def test_save_server_and_channel(self):
        await setup(self.message, 'instructions <#456>', self.store)
        self.guild.get_channel_or_thread.assert_called_once_with(456)
        self.store.set_instruction_channel.assert_called_once_with(123, 456, 789)
        self.assertIn('<#456>', self.message.channel.send.call_args.args[0])

    async def test_off_and_status(self):
        await setup(self.message, 'instructions off', self.store)
        self.store.set_instruction_channel.assert_called_once_with(123, None, 789)
        self.store.get_instruction_channel.return_value = 456
        await setup(self.message, 'instructions status', self.store)
        self.store.get_instruction_channel.assert_called_once_with(123)
        self.assertIn('<#456>', self.message.channel.send.call_args.args[0])

    async def test_permissions_and_foreign_channel(self):
        self.message.author.guild_permissions.manage_guild = False
        await setup(self.message, 'instructions <#456>', self.store)
        self.store.set_instruction_channel.assert_not_called()
        self.message.author.guild_permissions.manage_guild = True
        self.guild.get_channel_or_thread.return_value = None
        await setup(self.message, 'instructions <#999>', self.store)
        self.store.set_instruction_channel.assert_not_called()
        self.guild.get_channel_or_thread.return_value = self.target
        self.target.permissions_for.return_value.send_messages = False
        await setup(self.message, 'instructions <#456>', self.store)
        self.store.set_instruction_channel.assert_not_called()

    async def test_database_failure_does_not_confirm_save(self):
        self.store.set_instruction_channel.side_effect = RuntimeError('Offline')
        with self.assertLogs(level='ERROR'):
            await setup(self.message, 'instructions <#456>', self.store)
        self.assertIn('not confirmed', self.message.channel.send.call_args.args[0])

    async def test_dm_and_bad_syntax(self):
        await setup(self.message, 'instructions arbitrary', self.store)
        self.store.set_instruction_channel.assert_not_called()
        self.message.guild = None
        await setup(self.message, 'instructions off', self.store)
        self.store.set_instruction_channel.assert_not_called()
