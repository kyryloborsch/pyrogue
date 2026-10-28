"""Starting the game: the terminal checks, the saved game and the name prompt."""

import curses
import locale
import os
import random
import signal

from . import save
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


def load_or_new(scr):
    """Offer to continue the saved game. Returns a Game, or None to leave."""
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
            while True:
                k = title_screen(scr, [
                    f'Saved game: {state["name"]}, level {p.level}, on depth {state["depth"]}.', '',
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
    return Game(scr, ask_name(scr))


def main(scr):
    lines, cols = scr.getmaxyx()
    if lines < 24 or cols < 80:
        return f'Your terminal is {cols}x{lines}; please make it at least 80x24.'
    curses.curs_set(0)
    scr.keypad(True)
    init_colors()
    game = load_or_new(scr)
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


def run():
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')
    for name in ('SIGHUP', 'SIGTERM'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), on_hangup)
    try:
        message = curses.wrapper(main)
    except (KeyboardInterrupt, Hangup):
        message = None
    if message:
        print(message)
