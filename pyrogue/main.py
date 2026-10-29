"""Starting the game: the terminal checks, the saved game and the name prompt."""

import argparse
import curses
import locale
import os
import random
import signal

from . import save, scores
from .game import Game
from .text import init_colors

TITLE = 'ROGUE-LIKE: the Dungeons of Doom'


class Hangup(Exception):
    """The terminal was closed, or the game was told to stop."""


def on_hangup(signum, frame):
    raise Hangup()


def ask_name(scr):
    curses.echo()
    curses.curs_set(1)
    scr.erase()
    scr.addstr(2, 4, TITLE, curses.A_BOLD)
    scr.addstr(4, 4, 'What is your name, adventurer? ')
    scr.refresh()
    try:
        name = scr.getstr(4, 35, 18).decode(errors='ignore').strip()
    except curses.error:
        name = ''
    curses.noecho()
    curses.curs_set(0)
    return name or 'Rogue'


def title_screen(scr, lines):
    scr.erase()
    scr.addstr(2, 4, TITLE, curses.A_BOLD)
    for i, line in enumerate(lines):
        scr.addstr(4 + i, 4, line)
    scr.refresh()
    return scr.getch()


def load_or_new(scr, seed=None):
    """Offer to continue the saved game. Returns a Game, or None to leave. A new game uses
    seed, if one was given."""
    if save.exists():
        try:
            state, dice = save.read()
        except save.SaveError as e:
            save.set_aside()
            title_screen(scr, [f'Your saved game could not be loaded: {e}.',
                               'It was moved aside, so a new game will begin.', '',
                               'Press any key.'])
        else:
            p = state['player']
            note = [] if seed is None else [f'The seed {seed} is only used for a new game.', '']
            while True:
                k = title_screen(scr, [
                    f'Saved game: {state["name"]}, level {p.level}, on depth {state["depth"]}.', '',
                    *note,
                    '  c) continue', '  n) new game (the saved game is lost)', '  q) leave'])
                if k in (ord('c'), ord('C'), 10, 13, ord(' ')):
                    random.setstate(dice)
                    return Game.restore(scr, state)
                if k in (ord('q'), ord('Q'), 27):
                    return None
                if k in (ord('n'), ord('N')):
                    k = title_screen(scr, [f'Really give up {state["name"]} for good? (y/n)'])
                    if k in (ord('y'), ord('Y')):
                        save.delete()
                        break
    return Game(scr, ask_name(scr), seed)


def main(scr, seed=None):
    lines, cols = scr.getmaxyx()
    if lines < 24 or cols < 80:
        return f'Your terminal is {cols}x{lines}; please make it at least 80x24.'
    curses.curs_set(0)
    scr.keypad(True)
    init_colors()
    game = load_or_new(scr, seed)
    if game is None:
        return None
    try:
        game.play()
    except (KeyboardInterrupt, Hangup):
        if not game.game_over and game.snapshot:
            save.write(game.snapshot)
            return 'Interrupted. Your game was saved as it was at the start of that turn.'
        if game.game_over and game.game_over[0] != 'saved':
            save.delete()
        return None
    if game.game_over[0] == 'saved':
        return f'Game saved. See you soon, {game.name}! Start the game again to continue.'
    return None


def parse_args():
    parser = argparse.ArgumentParser(prog='rogue.py', description=TITLE)
    parser.add_argument('--seed', help='start a new game from this seed (any word or number); '
                        'the same seed makes the same dungeon')
    parser.add_argument('--scores', action='store_true', help='show the hall of fame and quit')
    return parser.parse_args()


def run():
    args = parse_args()
    if args.scores:
        print('\n'.join(scores.table(scores.load())))
        return
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')
    for name in ('SIGHUP', 'SIGTERM'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), on_hangup)
    try:
        message = curses.wrapper(main, args.seed)
    except (KeyboardInterrupt, Hangup):
        message = None
    if message:
        print(message)
