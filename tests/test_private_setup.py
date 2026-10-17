from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

import discord
from discord import app_commands

from message_router import parse_message
from private_setup import register_setup_commands


class PrivateSetupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Mock()
        self.services = Mock()
        client = discord.Client(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(client)
        register_setup_commands(self.tree, self.store, self.services)
        self.interaction = SimpleNamespace(guild=SimpleNamespace(id=12), guild_id=12,
            channel_id=34, user=SimpleNamespace(id=56, guild_permissions=SimpleNamespace(manage_guild=True)),
            response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()))

    async def test_success_and_status_are_private(self):
        command = self.tree.get_command('setup').get_command('logging')
        await command.callback(self.interaction, 'off')
        self.store.change.assert_called_once_with(12, 56, 'logging', False)
        self.interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        for call in self.interaction.followup.send.call_args_list:
            self.assertTrue(call.kwargs['ephemeral'])

    async def test_permission_denial_is_private_and_does_not_write(self):
        self.interaction.user.guild_permissions.manage_guild = False
        command = self.tree.get_command('setup').get_command('logging')
        await command.callback(self.interaction, 'on')
        self.store.change.assert_not_called()
        self.assertTrue(self.interaction.followup.send.call_args.kwargs['ephemeral'])

    async def test_database_failure_reply_is_private(self):
        self.store.change.side_effect = RuntimeError('Offline')
        command = self.tree.get_command('setup').get_command('logging')
        with self.assertLogs(level='ERROR'):
            await command.callback(self.interaction, 'on')
        self.assertTrue(self.interaction.followup.send.call_args.kwargs['ephemeral'])

    def test_public_setup_is_ignored(self):
        message = SimpleNamespace(guild=object(), author=SimpleNamespace(bot=False),
            webhook_id=None, attachments=[], is_system=lambda: False,
            content='!setup logging on')
        self.assertIsNone(parse_message(message))
