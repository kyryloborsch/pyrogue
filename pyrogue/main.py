"""Starting the game: the terminal checks and the name prompt."""

import curses
import locale
import os

from .game import Game
from .text import init_colors


def ask_name(scr):
    curses.echo()
    curses.curs_set(1)
    scr.erase()
    scr.addstr(2, 4, 'ROGUE-LIKE: the Dungeons of Doom', curses.A_BOLD)
    scr.addstr(4, 4, 'What is your name, adventurer? ')
    scr.refresh()
    try:
        name = scr.getstr(4, 35, 18).decode(errors='ignore').strip()
    except curses.error:
        name = ''
    curses.noecho()
    curses.curs_set(0)
    return name or 'Rogue'


def main(scr):
    lines, cols = scr.getmaxyx()
    if lines < 24 or cols < 80:
        return f'Your terminal is {cols}x{lines}; please make it at least 80x24.'
    curses.curs_set(0)
    scr.keypad(True)
    init_colors()
    Game(scr, ask_name(scr)).play()
    return None


def run():
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')
    error = curses.wrapper(main)
    if error:
        print(error)
