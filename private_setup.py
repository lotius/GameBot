"""Private slash-command adapter for the existing setup handlers."""
import logging
import asyncio
from types import SimpleNamespace

import discord
from discord import app_commands

from setup_commands import setup
from setup_permissions import can_manage_bot


class PrivateChannel:
    def __init__(self, interaction):
        self.interaction = interaction
        self.id = interaction.channel_id

    async def send(self, text):
        await self.interaction.followup.send(text, ephemeral=True,
                                             allowed_mentions=discord.AllowedMentions.none())


def register_setup_commands(tree, store, services):
    group = app_commands.Group(name='setup', description='Privately configure this server',
                               guild_only=True)

    async def run(interaction, command):
        await interaction.response.defer(ephemeral=True)
        if not await can_manage_bot(interaction.guild, interaction.user, store):
            await interaction.followup.send('Manage Server or the configured bot administrator role is required.', ephemeral=True)
            return
        try:
            message = SimpleNamespace(guild=interaction.guild, author=interaction.user,
                                      channel=PrivateChannel(interaction))
            await setup(message, command, store)
            services.invalidate()
        except Exception as error:
            logging.error('Private setup failed (%s).', type(error).__name__)
            await interaction.followup.send('Setup could not be completed. Please try again later.', ephemeral=True)

    def callback_for(setting):
        async def callback(interaction: discord.Interaction, action: str,
                           channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread = None):
            if len(action) > 300:
                await interaction.response.send_message('Setup input is too long.', ephemeral=True)
                return
            if channel is not None and channel.guild.id != interaction.guild_id:
                await interaction.response.send_message('Choose a channel in this server.', ephemeral=True)
                return
            if setting == 'instructions':
                command = f'instructions {channel.id if channel else action}'
            elif channel is not None:
                command = f'{setting} {channel.id} {action}'
            else:
                command = f'{setting} {action}'
            await run(interaction, command)
        return callback

    for setting in ('instructions', 'rolls', 'logging', 'spam', 'retention', 'dddice'):
        callback = callback_for(setting)
        callback = app_commands.describe(action='Setting: on/off, status, limits, room slug, or default <room>',
                                         channel='Channel to configure, where applicable')(callback)
        group.command(name=setting, description=f'Privately configure {setting}')(callback)

    @group.command(name='status', description='Privately inspect this channel and server settings')
    async def status(interaction: discord.Interaction):
        await run(interaction, 'status')

    @group.command(name='admin-role', description='Assign or clear the bot administrator role (Manage Server only)')
    @app_commands.choices(action=[app_commands.Choice(name='Set role', value='set'),
                                 app_commands.Choice(name='Clear role', value='clear'),
                                 app_commands.Choice(name='Show role', value='status')])
    async def admin_role(interaction: discord.Interaction, action: str, role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None or not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send('Only users with Manage Server can assign, clear, or inspect the administrator role.', ephemeral=True)
            return
        try:
            if action == 'status':
                role_id = await asyncio.to_thread(store.get_admin_role, interaction.guild_id)
                text = f'Bot administrator role: <@&{role_id}>.' if role_id else 'No bot administrator role configured.'
            elif action == 'clear':
                await asyncio.to_thread(store.change, interaction.guild_id, interaction.user.id, 'admin-role', None)
                text = 'Bot administrator role cleared. Manage Server users retain access.'
            elif action == 'set':
                if role is None or role.guild.id != interaction.guild_id or role.is_default() or role.managed:
                    await interaction.followup.send('Choose a regular role in this server; @everyone and managed roles cannot be delegated.', ephemeral=True)
                    return
                await asyncio.to_thread(store.change, interaction.guild_id, interaction.user.id, 'admin-role', role.id)
                text = f'Bot administrator role set to {role.mention}. Members can change bot settings and replace dddice credentials.'
            else:
                text = 'Choose set, clear, or status.'
            await interaction.followup.send(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        except Exception as error:
            logging.error('Administrator role setup failed (%s).', type(error).__name__)
            await interaction.followup.send('Could not access the administrator role setting. Please retry later.', ephemeral=True)

    @group.command(name='dddice-test', description='Privately check the dddice key and room without rolling')
    async def connection_test(interaction: discord.Interaction, channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread = None):
        await interaction.response.defer(ephemeral=True)
        if not await can_manage_bot(interaction.guild, interaction.user, store):
            await interaction.followup.send('Manage Server or the bot administrator role is required.', ephemeral=True)
            return
        if channel is not None and channel.guild.id != interaction.guild_id:
            await interaction.followup.send('Choose a channel in this server.', ephemeral=True)
            return
        try:
            from roll_services import test_dddice_connection
            policy = await asyncio.to_thread(store.policy, interaction.guild_id,
                                             channel.id if channel else interaction.channel_id)
            result = await asyncio.to_thread(test_dddice_connection, policy)
            if not policy['integration_enabled'] or not policy['dddice_enabled']:
                result += ' Automatic forwarding is currently disabled for this server or channel.'
            await interaction.followup.send(result, ephemeral=True)
        except Exception as error:
            logging.error('dddice connection test failed (%s).', type(error).__name__)
            await interaction.followup.send('Could not load integration settings. Check database availability.', ephemeral=True)

    tree.add_command(group)
