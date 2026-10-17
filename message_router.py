"""Filter Discord events before dispatching supported prefix commands."""
import logging
import re

import discord

import commands
from boardgamedice import resolve_game

MAX_COMMAND_LENGTH = 1000


def parse_message(message):
    if (message.guild is None or message.author.bot or message.webhook_id is not None
            or message.is_system() or message.attachments):
        return None
    content = message.content
    if not content.startswith('!'):
        return None
    match = re.fullmatch(r'!([A-Za-z][A-Za-z0-9]*)(?:\s+(.*))?', content, re.DOTALL)
    if match is None:
        return None
    command = match[1].lower()
    if command not in {'help', 'roll', 'dice', 'stats'} and resolve_game(command) is None:
        return None
    return command, (match[2] or '').strip()


async def dispatch_message(message, store, services):
    parsed = parse_message(message)
    if parsed is None:
        return
    command, param = parsed
    permissions = message.channel.permissions_for(message.guild.me)
    if not permissions.view_channel or not (permissions.send_messages_in_threads if isinstance(message.channel, discord.Thread) else permissions.send_messages):
        return
    try:
        if len(message.content) > MAX_COMMAND_LENGTH:
            await message.channel.send('Command is too long. Use !help for supported formats.')
            return
        if resolve_game(command) is not None and not permissions.attach_files:
            await message.channel.send('I need Attach Files permission in this channel for that command.')
            return
        policy = await services.policy(message)
        if not services.admit(message, policy):
            return
        await commands.process_command(message, command, param, services, policy_override=policy)
    except (discord.Forbidden, discord.NotFound):
        # Permissions or the channel may change while a command is running.
        logging.warning('Could not deliver command response for message %s.', message.id)
    except Exception:
        # Do not log command text: a user might accidentally enter a secret.
        logging.exception('Command %s failed for message %s.', command, message.id)
        try:
            await message.channel.send('That command could not be completed. Please try again later.')
        except discord.HTTPException:
            logging.warning('Could not deliver command failure notice for message %s.', message.id)
