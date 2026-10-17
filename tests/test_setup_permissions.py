from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

import discord
from discord import app_commands

from private_setup import register_setup_commands
from setup_permissions import can_manage_bot


class RoleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = SimpleNamespace(id=12)
        self.user = SimpleNamespace(id=34, roles=[SimpleNamespace(id=56)],
                                    guild_permissions=SimpleNamespace(manage_guild=False))
        self.store = Mock()
        self.store.get_admin_role.return_value = 56

    async def test_matching_role_grants_access(self):
        self.assertTrue(await can_manage_bot(self.guild, self.user, self.store))
        self.store.get_admin_role.assert_called_once_with(12)

    async def test_wrong_role_and_no_role_are_denied(self):
        for role_id in [None, 99]:
            self.store.get_admin_role.return_value = role_id
            self.assertFalse(await can_manage_bot(self.guild, self.user, self.store))

    async def test_manage_server_works_when_database_is_down(self):
        self.user.guild_permissions.manage_guild = True
        self.store.get_admin_role.side_effect = RuntimeError('Offline')
        self.assertTrue(await can_manage_bot(self.guild, self.user, self.store))
        self.store.get_admin_role.assert_not_called()

    async def test_role_lookup_failure_denies_delegated_access(self):
        self.store.get_admin_role.side_effect = RuntimeError('Offline')
        with self.assertLogs(level='WARNING'):
            self.assertFalse(await can_manage_bot(self.guild, self.user, self.store))

    async def test_delegated_admin_cannot_change_delegation(self):
        client = discord.Client(intents=discord.Intents.default())
        tree = app_commands.CommandTree(client)
        register_setup_commands(tree, self.store, Mock())
        interaction = SimpleNamespace(guild=self.guild, guild_id=12, user=self.user,
            response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
        await tree.get_command('setup').get_command('admin-role').callback(interaction, 'clear')
        self.store.change.assert_not_called()
        self.assertTrue(interaction.followup.send.call_args.kwargs['ephemeral'])

    async def test_manage_server_can_assign_role(self):
        self.user.guild_permissions.manage_guild = True
        client = discord.Client(intents=discord.Intents.default())
        tree = app_commands.CommandTree(client)
        register_setup_commands(tree, self.store, Mock())
        interaction = SimpleNamespace(guild=self.guild, guild_id=12, user=self.user,
            response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
        role = SimpleNamespace(id=56, guild=self.guild, managed=False,
                               is_default=lambda: False, mention='<@&56>')
        await tree.get_command('setup').get_command('admin-role').callback(interaction, 'set', role)
        self.store.change.assert_called_once_with(12, 34, 'admin-role', 56)
