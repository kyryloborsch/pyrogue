"""Map size, map tiles, keys and other fixed numbers."""

import curses

MAP_W, MAP_H = 80, 21
MAP_TOP = 2                      # screen row where the map starts
STATUS_ROW = MAP_TOP + MAP_H     # row 23
FOV_RADIUS = 9
FINAL_DEPTH = 20                 # the Frost Wyrm guards the Amulet here
MAX_PACK = 30

ROCK, FLOOR, CORRIDOR, DOOR, STAIRS = ' ', '.', '#', '+', '>'
HWALL, VWALL = '-', '|'
CAVE_WALL, POOL = '%', '~'       # a pool is lava or icy water, depending on the environment
PILLAR = '0'                     # stone pillars in the halls of the Catacombs
WALKABLE = {FLOOR, CORRIDOR, DOOR, STAIRS}
OPAQUE = {ROCK, HWALL, VWALL, CAVE_WALL, PILLAR}
WALLS = {HWALL, VWALL, CAVE_WALL, PILLAR}

DIRS = {
    'h': (-1, 0), 'l': (1, 0), 'k': (0, -1), 'j': (0, 1),
    'y': (-1, -1), 'u': (1, -1), 'b': (-1, 1), 'n': (1, 1),
}
# You move with the arrow keys or the numpad (letters don't move you). The numpad's digits
# work with Num Lock on; with it off, its corner keys come through as Home, PgUp, End and
# PgDn (or the A1/A3/C1/C3 keypad codes).
NUMPAD = {'1': 'b', '2': 'j', '3': 'n', '4': 'h', '6': 'l', '7': 'y', '8': 'k', '9': 'u'}
ARROWS = {
    curses.KEY_LEFT: 'h', curses.KEY_RIGHT: 'l', curses.KEY_UP: 'k', curses.KEY_DOWN: 'j',
}
KEYPAD_DIAGONALS = {
    curses.KEY_HOME: 'y', curses.KEY_PPAGE: 'u', curses.KEY_END: 'b', curses.KEY_NPAGE: 'n',
    curses.KEY_A1: 'y', curses.KEY_A3: 'u', curses.KEY_C1: 'b', curses.KEY_C3: 'n',
}
# Two arrow keys pressed together step diagonally, e.g. up + left. read_key turns such a
# chord into one of these made-up key codes (getch never returns them).
ARROW_CHORDS = {frozenset('kh'): -2, frozenset('kl'): -3, frozenset('jh'): -4, frozenset('jl'): -5}
CHORD_STEPS = {-2: 'y', -3: 'u', -4: 'b', -5: 'n'}
CHORD_DELAY = 80                 # ms to wait for the second arrow of a chord
CONFIRM_KEYS = {'\n', '\r', ' ', 'z'}
CANCEL_KEYS = {'\x1b', 'x'}
# inventory letters skip the keys that close or choose in the inventory, then go on in capitals
ITEM_LETTERS = ([c for c in 'abcdefghijklmnopqrstuvwxyz' if c not in 'ixz']
                + list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))

LOG_SIZE = 100                  # events kept for the event log (m)
