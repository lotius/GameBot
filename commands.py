import random
import standard_roll
import re
import discord
import logging
import asyncio

from boardgamedice import dice_sets, generate_help, resolve_game, roll_board_game_dice

MAX_ROLL_DICE = 10
MAX_ROLL_SIDES = 100
def roll_help():
    return (
        '**Roll help** - `!roll` or `!dice`\n'
        '`NdS` means N dice with S sides: `2d6` rolls two six-sided dice; `d20` rolls one d20. '
        f'Limits: 1-{MAX_ROLL_DICE} dice total, 1-{MAX_ROLL_SIDES} sides each.\n\n'
        '**Add/subtract** - `!roll 2d6 + 3` adds 3 to the total once; `2d6 - 2` subtracts 2.\n'
        '**Mixed dice** - `!roll 2d6 + d8 + 3` sums both d6, one d8, and 3. '
        '`d20 - d4` subtracts the d4 result.\n'
        '**Advantage/disadvantage** - `!roll d20+5 adv` rolls two d20, keeps the higher, then adds 5. '
        '`d20 dis` keeps the lower. Use only with a single d20; no keep/explosion rules.\n'
        '**Keep dice** - `!roll 4d6kh3` keeps the highest 3 of 4 dice and sums them. '
        '`4d6kl2` keeps the lowest 2. `kh` = keep highest; `kl` = keep lowest. '
        'Keep at least 1, up to the number rolled. Crossed-out dice do not count.\n'
        '**Successes** - `!roll 6d6>=5` counts kept dice showing 5 or higher instead of summing. '
        'For [2, 5, 6], that is 2 successes. No +/- modifiers or subtraction.\n'
        '**Explosions** - `!roll 3d6!` rolls an extra d6 for every 6, repeating on more 6s; '
        'all results add up. Maximum 20 extra dice per command; d1 cannot explode. '
        'With `4d6kh3!`, keep the 3 highest whole explosion chains by their sums.\n'
        '**Labels** - `!roll d20+5 adv Stealth` names the roll. Put the label last; '
        'start with a letter, maximum 80 characters.\n\n'
        '**Order:** dice with `khN`/`klN`, then `!`; +/- terms; `adv`/`dis`; `>=target`; label. '
        'Example: `!roll 4d6kh3!>=5 Attack`. Spaces around +/- are optional. '
        'Natural d20 rolls of 1 and 20 are bold.'
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
                 '!roll (or !dice) - Roll dice with modifiers, mixed dice, advantage, keep rules, successes, explosions, and labels. Use !help roll for details.']
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
    try:
        groups, modifier, modifiers, threshold, label = standard_roll.parse(param, MAX_ROLL_DICE, MAX_ROLL_SIDES)
    except ValueError as error:
        await message.channel.send(f'{error} Use !help roll for details.')
        return
    total, detail, results, discarded, capped = standard_roll.evaluate(groups, threshold)
    for sign, value in modifiers:
        detail += f" {'+' if sign > 0 else '-'} {value}"
    name = discord.utils.escape_markdown(getattr(message.author, 'display_name', message.author.name))
    label_text = f' ({discord.utils.escape_markdown(label)})' if label else ''
    unit = ' successes' if threshold is not None else ''
    if threshold is not None:
        detail += f' >= {threshold}'
    notice = ' Explosion limit reached (20 extra dice).' if capped else ''
    await message.channel.send(f'**{name}** rolled **{total + modifier}{unit}**{label_text}: {detail}.{notice}')
    definition = {'sides': groups[0]['sides'], 'groups': groups, 'threshold': threshold,
                  'label': label, 'discarded': discarded}
    return {'game': 'standard', 'command': 'roll', 'modifier': modifier,
            'definition': definition, 'results': results}
