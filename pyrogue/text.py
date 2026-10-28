"""Colors, and the words and values highlighted in text."""

import curses
import re

# Log lines that contain one of these get a color, so big moments stand out.
LOG_HIGHLIGHTS = [('BOSS', 'red'), ('appeared!', 'red'), ('attacked!', 'red'),
                  ('joined the battle', 'red'), ('fainted...', 'red'),
                  ('grew to level', 'yellow'), ('learned', 'green'), ('You won the battle', 'green')]
# Words and values highlighted inside message, battle, dialogue and log text. The first rule
# that matches a stretch of text wins; a color of None just makes it bold.
TEXT_HIGHLIGHTS = [(re.compile(pattern, flags), color) for pattern, flags, color in [
    (r"super effective|critical hit", re.I, 'yellow'),
    (r"\b(fainted|died|killed|starving|weak with hunger|hungry|can't escape|no running)\b",
     re.I, 'red'),
    (r"\b(burn(s|ed|ing)?|poison(s|ed)?|frozen|freez\w*|paralyz\w*|confus\w*|asleep|"
     r"sleep(ing)?)\b", re.I, 'magenta'),
    (r"\b(heal(s|ed)?|restor\w*|cured?|learned|recovered|grew to level \d+|got away safely|"
     r"won the battle)\b", re.I, 'green'),
    (r"[+-]?\b\d+ (gold( pieces)?|au)\b", re.I, 'yellow'),
    (r"[+-]?\b\d+ (HP|MP|EXP)\b", re.I, 'cyan'),
    (r"\bdepth \d+( of \d+)?", re.I, 'cyan'),
    (r"\b[A-Z][A-Z'-]*[A-Z](?: [A-Z][A-Z'-]*[A-Z])*\b", 0, None),   # MONSTERS, MOVES, BOSSES
    (r"[+-]?\b\d+(-\d+)?\b", 0, None),
]]

COLORS = {}


def init_colors():
    names = {'white': curses.COLOR_WHITE, 'red': curses.COLOR_RED,
             'green': curses.COLOR_GREEN, 'yellow': curses.COLOR_YELLOW,
             'blue': curses.COLOR_BLUE, 'magenta': curses.COLOR_MAGENTA,
             'cyan': curses.COLOR_CYAN}
    has = curses.has_colors()
    if has:
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
    for i, (name, c) in enumerate(names.items(), 1):
        if has:
            curses.init_pair(i, c, bg)
            COLORS[name] = curses.color_pair(i)
        else:
            COLORS[name] = 0


def an(s):
    return ('an ' if s[0] in 'aeiou' else 'a ') + s
