"""Saving and loading. There is one saved game, kept until its hero dies, wins or gives up."""

import os
import pickle
import random

# Bump this whenever the saved classes change shape, so old saves are refused cleanly
# instead of breaking halfway through a game.
SAVE_VERSION = 1


class SaveError(Exception):
    pass


# the saves folder sits next to the game, beside rogue.py
SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saves')


def save_path():
    """Where the save lives: $PYROGUE_SAVE, or saves/save.pickle next to the game."""
    return os.environ.get('PYROGUE_SAVE') or os.path.join(SAVE_DIR, 'save.pickle')


def snapshot(game):
    """The whole game (but not the screen), with the dice, as bytes ready to write."""
    state = {k: v for k, v in vars(game).items() if k not in ('scr', 'snapshot')}
    return pickle.dumps({'version': SAVE_VERSION, 'state': state, 'random': random.getstate()})


def write(data):
    """Write a snapshot. A half-written file never replaces a good save."""
    path = save_path()
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def exists():
    return os.path.exists(save_path())


def read():
    """The saved state and dice. Raises SaveError if the save can't be used."""
    try:
        with open(save_path(), 'rb') as f:
            data = pickle.load(f)
    except Exception as e:
        raise SaveError(f'the save file is damaged ({e.__class__.__name__})') from e
    if not isinstance(data, dict) or data.get('version') != SAVE_VERSION:
        raise SaveError('the save is from a different version of the game')
    return data['state'], data['random']


def delete():
    try:
        os.remove(save_path())
    except FileNotFoundError:
        pass


def set_aside():
    """Move an unusable save out of the way (keeping it, just in case) so a new game can start."""
    path = save_path()
    try:
        os.replace(path, path + '.bad')
    except OSError:
        delete()
