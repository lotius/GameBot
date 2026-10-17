"""Parse and evaluate bounded standard dice expressions without eval."""
import random
import re

DIE = re.compile(r"([0-9]*)\s*[dD]\s*([0-9]+)(?:\s*(kh|kl)\s*([0-9]+))?\s*(!)?", re.I)
NUMBER = re.compile(r"[0-9]+")
MAX_EXTRA_DICE = 20


def parse(expression, max_dice, max_sides):
    text = expression.strip()
    groups, modifier, modifiers = [], 0, []
    pos, sign = 0, 1
    while True:
        match = DIE.match(text, pos)
        if match:
            count = int(match[1] or '1')
            sides = int(match[2])
            keep = int(match[4]) if match[4] else count
            if not 1 <= count <= max_dice or not 1 <= sides <= max_sides:
                raise ValueError(f'Roll 1-{max_dice} dice with 1-{max_sides} sides each.')
            if not 1 <= keep <= count:
                raise ValueError('Keep count must be between 1 and the number of dice.')
            if match[5] and sides == 1:
                raise ValueError('Exploding dice require at least two sides.')
            groups.append(dict(count=count, sides=sides, keep=keep,
                               mode=(match[3] or '').lower(), explode=bool(match[5]), sign=sign))
        else:
            match = NUMBER.match(text, pos)
            if not match or not groups:
                raise ValueError('Start with dice notation, such as 2d6 + d8 + 3.')
            value = int(match[0])
            if value > 9223372036854775807 or abs(modifier + sign * value) > 9223372036854775807:
                raise ValueError('Modifier is too large.')
            modifier += sign * value
            modifiers.append((sign, value))
        pos = match.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos < len(text) and text[pos] in '+-':
            sign = 1 if text[pos] == '+' else -1
            pos += 1
            while pos < len(text) and text[pos].isspace():
                pos += 1
            continue
        break
    if sum(g['count'] for g in groups) > max_dice:
        raise ValueError(f'Roll at most {max_dice} starting dice in total.')
    tail = text[pos:].strip()
    advantage = re.match(r'^(adv|dis)\b', tail, re.I)
    if advantage:
        if len(groups) != 1 or groups[0]['count'] != 1 or groups[0]['sides'] != 20 or groups[0]['mode'] or groups[0]['explode']:
            raise ValueError('Use adv/dis with one d20, optionally with a modifier.')
        groups[0].update(count=2, keep=1, mode='kh' if advantage[1].lower() == 'adv' else 'kl')
        tail = tail[advantage.end():].strip()
    target = re.match(r'^>=\s*([0-9]+)', tail)
    threshold = int(target[1]) if target else None
    if target:
        tail = tail[target.end():].strip()
        if modifiers or any(g['sign'] < 0 for g in groups):
            raise ValueError('Success counting cannot use modifiers or subtraction.')
        if not 1 <= threshold <= max_sides:
            raise ValueError(f'Success threshold must be between 1 and {max_sides}.')
    if tail and (not tail[0].isalpha() or re.match(r'^(adv|dis|kh|kl)\b', tail, re.I)):
        raise ValueError('Invalid dice expression or label.')
    if len(tail) > 80:
        raise ValueError('Roll labels must be 80 characters or fewer.')
    return groups, modifier, modifiers, threshold, tail


def evaluate(groups, threshold):
    details, results, discarded, total = [], [], [], 0
    extra, capped = 0, False
    for group in groups:
        sides = group['sides']
        chains = []
        for _ in range(group['count']):
            chain = [random.randint(1, sides)]
            while group['explode'] and chain[-1] == sides:
                if extra >= MAX_EXTRA_DICE:
                    capped = True
                    break
                chain.append(random.randint(1, sides))
                extra += 1
            chains.append(chain)
        order = sorted(range(len(chains)), key=lambda i: sum(chains[i]), reverse=group['mode'] != 'kl')
        kept = set(order[:group['keep']])
        rendered = []
        for index, chain in enumerate(chains):
            values = []
            for value in chain:
                face = str(value)
                if sides == 20 and value in (1, 20):
                    face = f'**{value}**'
                values.append(face)
                contribution = int(value >= threshold) if threshold is not None else group['sign'] * value
                result = {'dice_type': f'd{sides}', 'face_id': str(value), 'values': {'value': contribution}}
                if index in kept:
                    results.append(result)
                    total += contribution
                else:
                    discarded.append(result)
            shown = ' + '.join(values)
            if index not in kept:
                shown = f'~~{shown}~~'
            rendered.append(shown)
        notation = f"{group['count']}d{sides}"
        if group['mode']:
            notation += f"{group['mode']}{group['keep']}"
        if group['explode']:
            notation += '!'
        prefix = ('- ' if group['sign'] < 0 else '+ ') if details else ''
        details.append(prefix + notation + ' [' + ', '.join(rendered) + ']')
    return total, ' '.join(details), results, discarded, capped
