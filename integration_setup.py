"""Private Discord modal for per-server dddice credentials."""
import asyncio
import logging

import discord
from discord import app_commands

from roll_services import encrypt_key
from setup_permissions import can_manage_bot


class DddiceKeyModal(discord.ui.Modal, title='Configure dddice API key'):
    api_key = discord.ui.TextInput(label='API key', min_length=1, max_length=1000)

    def __init__(self, store, guild_id):
        super().__init__()
        self.store = store
        self.guild_id = guild_id

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id != self.guild_id or not await can_manage_bot(interaction.guild, interaction.user, self.store):
            await interaction.followup.send('Manage Server or the configured bot administrator role is required.', ephemeral=True)
            return
        try:
            encrypted = encrypt_key(str(self.api_key).strip())
            await asyncio.to_thread(self.store.change, self.guild_id, interaction.user.id, 'dddice-key', encrypted)
        except Exception as error:
            logging.error('Credential configuration failed (%s).', type(error).__name__)
            await interaction.followup.send('Could not save the key. Check host encryption and database settings.', ephemeral=True)
            return
        await interaction.followup.send('API key saved securely. Configure a room/channel and enable dddice with /setup.', ephemeral=True)


def register_key_command(tree, store):
    @tree.command(name='dddice-key', description="Privately configure this server's dddice API key")
    @app_commands.guild_only()
    async def key_command(interaction: discord.Interaction):
        if await can_manage_bot(interaction.guild, interaction.user, store):
            await interaction.response.send_modal(DddiceKeyModal(store, interaction.guild_id))
        else:
            await interaction.response.send_message('Manage Server or the configured bot administrator role is required.', ephemeral=True)
