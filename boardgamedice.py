"""Data-driven board game commands, validation, help, and image rolls."""
import io
import copy
import json
from pathlib import Path
import random
import re
import math

import cv2
import discord
import numpy as np

ROOT = Path(__file__).resolve().parent
DICE_FILE = ROOT / 'dice.json'
dice_sets = {}
_loaded_source = None


def reload_dice_sets():
    """Validate changes before replacing the shared command/help registry."""
    global _loaded_source
    source = DICE_FILE.read_text(encoding='utf-8')
    if source == _loaded_source:
        return False
    updated = json.loads(source)
    if not isinstance(updated, dict) or not updated:
        raise ValueError('Dice definitions must be a nonempty object.')
    commands_seen = {'help', 'roll', 'dice', 'setup', 'stats'}
    for command, game in updated.items():
        for name in [command] + game.get('aliases', []):
            if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9]{0,63}', name) or name in commands_seen:
                raise ValueError(f'Duplicate or invalid command: {name}')
            commands_seen.add(name)
        if not game['name'] or not game['imageDirectory']:
            raise ValueError(f'Missing name or image directory for {command}')
        total = game['maxNumberOfTotalDice']
        if type(total) is not int or total < 1 or not game['diceTypes']:
            raise ValueError(f'Invalid dice limits/types for {command}')
        re.compile(game['regex'])
        types_seen = set()
        for name, die in game['diceTypes'].items():
            for alias in [name] + die.get('aliases', []):
                if not re.fullmatch('[a-z][a-z0-9]{0,63}', alias) or alias in types_seen:
                    raise ValueError(f'Duplicate or invalid dice type/alias: {alias}')
                types_seen.add(alias)
            mapping = die.get('dddice')
            if mapping is not None and (
                not isinstance(mapping, dict)
                or not isinstance(mapping.get('type'), str)
                or not re.fullmatch(r'd[1-9][0-9]*', mapping['type'])
                or not isinstance(mapping.get('theme'), str) or not mapping['theme'].strip()
            ):
                raise ValueError(f'Invalid dddice mapping for {command}/{name}')
            limit = die.get('maxNumberOfDiceType')
            if limit is not None and (type(limit) is not int or limit < 1):
                raise ValueError(f'Invalid limit for {command}/{name}')
            if not die['faces']:
                raise ValueError(f'Missing faces for {command}/{name}')
            for face in die['faces']:
                values = face.get('values', {})
                if not isinstance(values, dict) or any(
                    not isinstance(key, str) or not key or len(key) > 128
                    or type(value) not in (int, float) or not math.isfinite(value)
                    for key, value in values.items()
                ):
                    raise ValueError(f'Invalid statistic values for {command}/{name}')
                if len(face.get('id', face['face'])) > 191:
                    raise ValueError('Face ID is too long')
                if 'dddiceValue' in face and (type(face['dddiceValue']) is not int or face['dddiceValue'] < 1):
                    raise ValueError('dddiceValue must be a positive integer')
                if type(face['numOfFaces']) is not int or face['numOfFaces'] < 1:
                    raise ValueError(f'Invalid face weight for {command}/{name}')
                if not (ROOT / 'images' / game['imageDirectory'] / face['face']).is_file():
                    raise ValueError(f"Missing dice image: {face['face']}")
        for alias in types_seen:
            if not re.fullmatch(game['regex'], '1 ' + alias):
                raise ValueError(f'Dice regex does not accept {command}/{alias}')
        default = game.get('defaultDiceType')
        if default:
            re.compile(default['regex'])
            if default['typeToUse'] not in game['diceTypes']:
                raise ValueError(f'Invalid default dice type for {command}')
    # Keep the object imported by commands.py; do not rebind it.
    dice_sets.clear()
    dice_sets.update(updated)
    _loaded_source = source
    return True


reload_dice_sets()


def resolve_game(command):
    """Resolve canonical commands and aliases declared in dice.json."""
    command = command.strip().lower()
    for name, game in dice_sets.items():
        if command == name or command in game.get('aliases', []):
            return name
    return None


def normalize_dice_type(game, input_type):
    for name, die in dice_sets[game]['diceTypes'].items():
        if input_type.lower() == name or input_type.lower() in die.get('aliases', []):
            return name
    return None


def parse_dice(command, param):
    """Validate an entire request before rolling; never silently reduce counts."""
    game = resolve_game(command)
    if game is None:
        raise ValueError(f"Unsupported game '{command}'.")
    metadata = dice_sets[game]
    param = ' '.join(param.lower().split())
    default = metadata.get('defaultDiceType')
    if default and re.fullmatch(default['regex'], param):
        requests = [(int(param or '1'), default['typeToUse'])]
    elif re.fullmatch(metadata['regex'], param):
        tokens = param.split()
        requests = [(int(tokens[i]), tokens[i + 1]) for i in range(0, len(tokens), 2)]
    else:
        raise ValueError(f'Invalid input format. Use !help {game} for usage.')

    counts = {}
    for count, requested_type in requests:
        die_type = normalize_dice_type(game, requested_type)
        if die_type is None:
            available = ', '.join(metadata['diceTypes'])
            raise ValueError(f"Unknown dice type '{requested_type}'. Available types: {available}.")
        if count < 1:
            raise ValueError('You must roll at least 1 die of each requested type.')
        if die_type in counts:
            raise ValueError(f"Each dice type can only be specified once (including aliases): {die_type}.")
        limit = metadata['diceTypes'][die_type].get('maxNumberOfDiceType')
        if limit is not None and count > limit:
            raise ValueError(f'You cannot roll more than {limit} {die_type} dice.')
        counts[die_type] = count
    if sum(counts.values()) > metadata['maxNumberOfTotalDice']:
        raise ValueError(f"You cannot roll more than {metadata['maxNumberOfTotalDice']} total dice in a single command.")
    return game, counts


def generate_help(command):
    """Generate the original metadata-driven help with randomized examples."""
    game = resolve_game(command)
    if game is None:
        return f"Error: Unsupported game '{command}'"
    game_data = dice_sets[game]
    dice_types = game_data['diceTypes']
    default_dice = game_data.get('defaultDiceType')
    max_total = game_data['maxNumberOfTotalDice']

    help_message = f"**{game_data['name']} Dice Help**\n"
    help_message += f"Max dice per roll: {max_total}\n"
    help_message += 'Commands: ' + ', '.join(
        '!' + name for name in [game] + game_data.get('aliases', [])
    ) + '\n'
    help_message += 'Available dice types: ' + ', '.join(
        f"{color} (max {data['maxNumberOfDiceType']})"
        if data.get('maxNumberOfDiceType') is not None else color
        for color, data in dice_types.items()
    ) + '\n'
    alias_info = [f"{color} ({', '.join(data['aliases'])})"
                  for color, data in dice_types.items() if data.get('aliases')]
    if alias_info:
        help_message += 'Aliases: ' + ', '.join(alias_info) + '\n'
    if default_dice:
        help_message += (
            'This game has a default dice type. If no color is specified, '
            f"the default '{default_dice['typeToUse']}' dice will be used.\n"
        )
        if re.fullmatch(default_dice['regex'], ''):
            help_message += f'Use !{game} without parameters to roll one random face.\n'
    help_message += 'You cannot specify the same dice color more than once in a single roll.\n\n'
    help_message += '**Examples:**\n'

    num_examples = random.randint(2, 4)
    examples = []
    if default_dice:
        default_type = dice_types[default_dice['typeToUse']]
        limit = default_type.get('maxNumberOfDiceType') or max_total
        examples.append(f"!{game} {random.randint(1, min(3, limit, max_total))}")
    for _ in range(num_examples - len(examples)):
        num_colors = random.randint(1, min(5, len(dice_types), max_total))
        selected_colors = random.sample(list(dice_types), num_colors)
        remaining_dice = max_total
        allocations = []
        for color in selected_colors:
            max_per_type = dice_types[color].get('maxNumberOfDiceType') or remaining_dice
            amount = random.randint(1, min(max_per_type, remaining_dice))
            allocations.append(f'{amount} {color}')
            remaining_dice -= amount
            if remaining_dice <= 0:
                break
        examples.append(f"!{game} {' '.join(allocations)}")
    return help_message + '\n'.join(examples)



def render_roll(game, counts, outcomes=None):
    """Render weighted faces into a private in-memory PNG for this request."""
    metadata = dice_sets[game]
    rolled = []
    images = {}
    for die_type, count in counts.items():
        die = metadata['diceTypes'][die_type]
        faces = [(face, offset) for face in die['faces']
                 for offset in range(face['numOfFaces'])]
        for _ in range(count):
            if game == 'rollcolor':
                filename = random.choice([face['face'] for face, _ in faces])
                slot = next(i for i, (face, _) in enumerate(faces) if face['face'] == filename)
            else:
                slot = random.randint(1, len(faces)) - 1
            entry, offset = faces[slot]
            filename = entry['face']
            if outcomes is not None:
                result = {'dice_type': die_type, 'face_id': entry.get('id', filename), 'values': entry.get('values', {})}
                mapping = die.get('dddice')
                if mapping:
                    # Explicit values mark the first physical face in this symbol's run.
                    value = entry['dddiceValue'] + offset if 'dddiceValue' in entry else slot + 1
                    result['dddice'] = dict(mapping, value=value)
                outcomes.append(result)
            if filename not in images:
                path = ROOT / 'images' / metadata['imageDirectory'] / filename
                face = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                if face is None:
                    raise FileNotFoundError(f'Dice face image could not be loaded: {path}')
                if face.ndim == 2:
                    face = cv2.cvtColor(face, cv2.COLOR_GRAY2BGRA)
                elif face.shape[2] == 3:
                    face = cv2.cvtColor(face, cv2.COLOR_BGR2BGRA)
                images[filename] = face
            rolled.append(images[filename])
    height = max(face.shape[0] for face in rolled)
    width = sum(face.shape[1] for face in rolled)
    result = np.zeros((height, width, 4), dtype=np.uint8)
    offset = 0
    for face in rolled:
        h, w = face.shape[:2]
        result[:h, offset:offset + w] = face
        offset += w
    success, encoded = cv2.imencode('.png', result)
    if not success:
        raise RuntimeError('Could not encode dice roll image.')
    return io.BytesIO(encoded.tobytes())


async def roll_board_game_dice(message, command, param):
    try:
        game, counts = parse_dice(command, param)
    except ValueError as error:
        await message.channel.send(str(error))
        return
    definition = copy.deepcopy(dice_sets[game])
    outcomes = []
    image = render_roll(game, counts, outcomes)
    attachment = discord.File(image, filename=f'{game}-results.png')
    try:
        await message.channel.send(file=attachment)
    finally:
        attachment.close()
        image.close()
    return {'game': game, 'command': command, 'modifier': 0, 'definition': definition, 'results': outcomes}
