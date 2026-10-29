"""The hall of fame: every finished run, kept in scores.json beside the saved game."""

import json
import os
import time

from . import save

KEEP = 100                       # runs kept in the file
SHOWN = 9                        # runs shown in the hall of fame (two lines each)


def scores_path():
    return os.path.join(os.path.dirname(save.save_path()) or '.', 'scores.json')


def score(entry):
    """Gold, plus a bonus for every depth reached and for a win."""
    return entry['gold'] + 100 * entry['depth'] + (5000 if entry['result'] == 'won' else 0)


def load():
    """Every recorded run, best first. A missing or damaged file is just an empty hall."""
    try:
        with open(scores_path()) as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    return sorted((e for e in entries if isinstance(e, dict) and 'score' in e),
                  key=lambda e: -e['score'])


def add(game):
    """Record a finished run. Returns the new entry (with its 'rank'), or None if the file
    couldn't be written."""
    p = game.player
    result, *why = game.game_over
    entry = {
        'name': game.name, 'result': result, 'reason': why[0] if why else '',
        'depth': game.depth, 'level': p.level, 'gold': p.gold, 'turns': game.turn,
        'seed': game.seed, 'date': time.strftime('%Y-%m-%d'),
    }
    entry['score'] = score(entry)
    entries = load() + [entry]
    entries.sort(key=lambda e: -e['score'])
    del entries[KEEP:]
    path = scores_path()
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path + '.tmp', 'w') as f:
            json.dump(entries, f, indent=1)
        os.replace(path + '.tmp', path)
    except OSError:
        return None
    entry['rank'] = next((i for i, e in enumerate(entries, 1) if e is entry), None)
    return entry


def describe(e):
    if e['result'] == 'won':
        return 'escaped with the Amulet'
    if e['result'] == 'died':
        return f'killed by {e["reason"]} on depth {e["depth"]}'
    return f'gave up on depth {e["depth"]}'


def table(entries, mark=None):
    """Lines of the hall of fame. mark is the rank to highlight with an arrow."""
    lines = ['HALL OF FAME', '', ' #  SCORE  NAME                LV  FATE']
    for i, e in enumerate(entries[:SHOWN], 1):
        arrow = '>' if i == mark else ' '
        lines.append(f'{arrow}{i:>2} {e["score"]:>6}  {e["name"][:18]:<18}  {e["level"]:>2}  '
                     f'{describe(e)}')
        lines.append(f'              {e["date"]}, {e["turns"]} turns, seed {e["seed"]}')
    if not entries:
        lines.append('   No finished runs yet.')
    elif mark and mark > SHOWN:
        lines += ['', f'   This run placed #{mark}.']
    return lines
