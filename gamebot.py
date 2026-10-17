import os
import logging
import asyncio
from setup_commands import GuildSettingsStore
from roll_services import RollServices
from integration_setup import register_key_command
from private_setup import register_setup_commands
from statistics_commands import register_statistics_command
from discord import app_commands
from pathlib import Path

from instructions import InstructionStore, check_instructions, fetch_instructions
from message_router import dispatch_message
from boardgamedice import reload_dice_sets
import discord
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
guild_settings = GuildSettingsStore()
instruction_store = InstructionStore()
roll_services = RollServices(guild_settings)

intents = discord.Intents.default()
intents.message_content = True
class GameBot(discord.Client):
    async def setup_hook(self):
        self.tree = app_commands.CommandTree(self)
        register_key_command(self.tree, guild_settings)
        register_setup_commands(self.tree, guild_settings, roll_services)
        register_statistics_command(self.tree, guild_settings, roll_services)
        # Keep definitions locally for per-guild sync; publish only guild commands.
        # Remove the old global registration without clearing other application commands.
        try:
            for command in await self.tree.fetch_commands():
                if command.name == 'dddice-key':
                    await command.delete()
        except Exception:
            logging.exception('Could not remove the obsolete global dddice-key command.')


client = GameBot(intents=intents, allowed_mentions=discord.AllowedMentions.none())

async def sync_server_commands(guild):
    try:
        client.tree.copy_global_to(guild=guild)
        synced = await client.tree.sync(guild=guild)
        logging.info('Registered %s server commands for guild %s.', len(synced), guild.id)
    except Exception:
        logging.exception('Server slash command registration failed for guild %s.', guild.id)


@client.event
async def on_guild_join(guild):
    await sync_server_commands(guild)

@tasks.loop(hours=1)
async def purge_statistics():
    try:
        deleted = await asyncio.to_thread(guild_settings.purge_expired)
        if deleted:
            logging.info('Purged %s expired roll records.', deleted)
    except Exception:
        logging.exception('Statistics retention unavailable; will retry next hour.')

@tasks.loop(seconds=30)
async def reload_dice_definitions():
    try:
        if reload_dice_sets():
            logging.info('Reloaded dice.json definitions and help.')
    except Exception:
        logging.exception('Dice reload failed; retaining the last working definitions.')

@tasks.loop(minutes=15)
async def new_instructions_available():
    try:
        destinations = await asyncio.to_thread(guild_settings.instruction_destinations)
        fetched = await asyncio.to_thread(fetch_instructions)
        new_entries = await asyncio.to_thread(instruction_store.discover, fetched)
    except Exception:
        logging.exception('Could not load instruction destinations; will retry next poll.')
        return
    for guild_id, channel_id in destinations:
        guild = client.get_guild(guild_id)
        channel = guild.get_channel_or_thread(channel_id) if guild else None
        if channel is None or not hasattr(channel, 'send'):
            continue
        try:
            await check_instructions(channel, instruction_store,
                                     Path(__file__).resolve().parent / 'found_instructions', entries=new_entries)
        except Exception:
            logging.exception('Instruction check failed for guild %s; will retry next poll.', guild_id)


@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')

    print(f'Connected to {len(client.guilds)} Discord servers.')

    for guild in client.guilds:
        await sync_server_commands(guild)

    # Start the scheduled tasks
    if not purge_statistics.is_running():
        purge_statistics.start()
    if not reload_dice_definitions.is_running():
        reload_dice_definitions.start()
    if not new_instructions_available.is_running():
        new_instructions_available.start()
    
@client.event
async def on_message(message):
    await dispatch_message(message, guild_settings, roll_services)


if __name__ == '__main__':
    if not TOKEN:
        raise SystemExit('DISCORD_TOKEN is missing. Configure it before starting the bot.')
    client.run(TOKEN)
