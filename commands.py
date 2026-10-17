import random
import re
import discord
import logging
import asyncio

from boardgamedice import dice_sets, generate_help, resolve_game, roll_board_game_dice

MAX_ROLL_DICE = 10
MAX_ROLL_SIDES = 100
ROLL_PATTERN = re.compile(
    r'\s*(?P<count>[0-9]*)\s*[dD]\s*(?P<sides>[0-9]+)'
    r'(?:\s*(?P<sign>[+-])\s*(?P<modifier>[0-9]+))?\s*'
)


def roll_help():
    return (
        '**Roll dice**:\n'
        'Use !roll (or !dice) #d# with an optional + or - modifier. '
        'Omit the dice count to roll one die. Spaces around the dice notation '
        'and modifier are accepted.\n'
        f'Roll 1-{MAX_ROLL_DICE} dice with 1-{MAX_ROLL_SIDES} sides each.\n'
        'Examples: !roll 2d6, !roll d20, !roll 2d6 + 3, !roll d20-1'
    )


async def process_command(message, command, param, services=None, policy_override=None):
    command = command.lower()
    is_roll = command in ('roll', 'dice') or resolve_game(command) is not None
    policy = None
    if is_roll and services is not None:
        try:
            policy = policy_override if policy_override is not None else await services.policy(message)
        except Exception:
            logging.exception('Could not load roll settings.')
            await message.channel.send('The database is unavailable; please try rolling again shortly.')
            return
        if not policy['rolls_enabled']:
            return
    result = None
    if command == 'stats' and services is not None:
        await stats(message, param, services.store)
    elif command == 'help':
        await help(message, param)
    elif command in ('roll', 'dice'):
        result = await roll(message, param)
    elif resolve_game(command) is not None:
        result = await roll_board_game_dice(message, command, param)
    if result is not None and services is not None:
        await services.completed(message, result, policy)


async def send_text(message, text):
    """Keep growing help/statistics within Discord's message limit."""
    for offset in range(0, len(text), 1900):
        await message.channel.send(text[offset:offset + 1900])


async def help(message, param):
    param = param.strip().lower()
    if not param:
        lines = ['Command List:',
                 '!roll (or !dice) - Roll standard dice with optional + or - modifiers (e.g. !roll 2d6 + 3). Use !help roll for details.']
        for command, game in dice_sets.items():
            names = ' or '.join('!' + name for name in [command] + game.get('aliases', []))
            lines.append(f'{names} - Roll {game["name"]} dice. Use !help {command} for details.')
        lines.extend(['!stats - Server roll overview. Use !stats help for filters and reports.',
                      'Use !help command for specific command information.'])
        await send_text(message, '\n'.join(lines))
    elif param in ('roll', 'dice'):
        await message.channel.send(roll_help())
    elif resolve_game(param) is not None:
        await send_text(message, generate_help(param))
    elif param == 'stats':
        await message.channel.send('Use !stats for a server overview or !stats help for game/player filters, face breakdowns, history, and CSV exports.')
    elif param != 'setup':
        await message.channel.send('No help is available for that command. Use !help for the command list.')

async def roll(message, param):
    match = ROLL_PATTERN.fullmatch(param)
    if match is None:
        await message.channel.send(
            'Proper roll format is #d# or d#, optionally followed by +# or -#. '
            'Examples: !roll 2d6 + 3 or !roll d20-1. Use !help roll for details.'
        )
        return
    try:
        count = int(match['count'] or '1')
        sides = int(match['sides'])
        modifier = int(match['modifier'] or '0')
    except ValueError:
        await message.channel.send('The numbers in your roll are too large. Use !help roll for details.')
        return
    if not 1 <= count <= MAX_ROLL_DICE or not 1 <= sides <= MAX_ROLL_SIDES:
        await message.channel.send(
            f'Roll 1-{MAX_ROLL_DICE} dice with 1-{MAX_ROLL_SIDES} sides each. '
            'Use !help roll for examples.'
        )
        return
    if modifier > 9223372036854775807:
        await message.channel.send('Modifier is too large. Use a smaller whole number.')
        return
    if match['sign'] == '-':
        modifier = -modifier
    results = [random.randint(1, sides) for _ in range(count)]
    detail = f'{count}d{sides} {results}'
    if match['sign']:
        detail += f" {match['sign']} {abs(modifier)}"
    name = discord.utils.escape_markdown(getattr(message.author, 'display_name', message.author.name))
    await message.channel.send(
        f'**{name}** rolled **{sum(results) + modifier}**: {detail}.'
    )
    return {'game': 'standard', 'command': 'roll', 'modifier': modifier,
            'definition': {'sides': sides},
            'results': [{'dice_type': f'd{sides}', 'face_id': str(value), 'values': {'value': value}}
                        for value in results]}
