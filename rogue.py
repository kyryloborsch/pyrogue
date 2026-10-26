#!/usr/bin/env python3
"""
A small dungeon crawler in the spirit of Rogue (1980), with Pokemon-style
battles and friendly characters to talk to.

Descend through 20 levels in four environments: the Dungeons of Doom, the
Sunken Catacombs, the Ember Caverns and the Frozen Abyss. Defeat the Bone King
on depth 10, then the Frost Wyrm on depth 20 to claim the Amulet of Yendor.
Run it in a terminal that is at least 80x24:

    python3 rogue.py

Press ? in the game for the list of commands.
"""
import curses
import heapq
import locale
import math
import os
import random
import textwrap
from collections import deque

MAP_W, MAP_H = 80, 21
MAP_TOP = 2                      # screen row where the map starts
STATUS_ROW = MAP_TOP + MAP_H     # row 23
FOV_RADIUS = 9
FINAL_DEPTH = 20                 # the Frost Wyrm guards the Amulet here
MAX_PACK = 20

ROCK, FLOOR, CORRIDOR, DOOR, STAIRS = ' ', '.', '#', '+', '>'
HWALL, VWALL = '-', '|'
CAVE_WALL, POOL = '%', '~'       # a pool is lava or icy water, depending on the environment
WALKABLE = {FLOOR, CORRIDOR, DOOR, STAIRS}
OPAQUE = {ROCK, HWALL, VWALL, CAVE_WALL}
WALLS = {HWALL, VWALL, CAVE_WALL}

# kind: (name, color). Traps are hidden (^ once found).
TRAPS = {
    'dart':     ('dart trap', 'cyan'),
    'pit':      ('spiked pit', 'yellow'),
    'teleport': ('teleport trap', 'magenta'),
    'sleep':    ('sleeping gas trap', 'green'),
    'alarm':    ('alarm trap', 'white'),
    'trapdoor': ('trapdoor', 'yellow'),
    'fire':     ('fire trap', 'red'),
    'frost':    ('frost trap', 'cyan'),
}

# Five levels each. layout: 'rooms', 'crypts' (many small rooms) or 'caves'.
# pool: (name, color, warning, what happens if you stumble in) for cave pools.
ENVIRONMENTS = [
    {'name': 'Dungeons of Doom', 'depth': 1, 'layout': 'rooms', 'wall': 'yellow',
     'traps': ['dart', 'dart', 'pit', 'teleport', 'sleep', 'alarm', 'trapdoor'],
     'intro': None},
    {'name': 'Sunken Catacombs', 'depth': 6, 'layout': 'crypts', 'wall': 'white',
     'traps': ['dart', 'pit', 'teleport', 'sleep', 'sleep', 'alarm', 'alarm', 'trapdoor'],
     'intro': 'The halls narrow into rows of cold stone tombs. '
              'Welcome to the Sunken Catacombs.'},
    {'name': 'Ember Caverns', 'depth': 11, 'layout': 'caves', 'wall': 'red',
     'pool': ('lava', 'red', 'The lava would burn you to a crisp!',
              'You stumble into the lava! It burns!'), 'pools': (2, 5),
     'traps': ['dart', 'pit', 'teleport', 'sleep', 'fire', 'fire', 'trapdoor'],
     'intro': 'The worked stone gives way to raw caverns glowing with lava. '
              'Welcome to the Ember Caverns.'},
    {'name': 'Frozen Abyss', 'depth': 16, 'layout': 'caves', 'wall': 'cyan',
     'pool': ('icy water', 'blue', 'The icy water would freeze you solid!',
              'You stumble into the icy water! It is freezing!'), 'pools': (4, 7),
     'traps': ['dart', 'pit', 'teleport', 'sleep', 'frost', 'frost', 'trapdoor'],
     'intro': 'A bitter wind howls up from below as the lava gives way to ice. '
              'Welcome to the Frozen Abyss.'},
]

# A boss waits at the end of each half of the game. Its level has no stairs until it
# falls, and the last one guards the Amulet. At half HP a boss changes tactics:
# ('summon', minion) calls two minions into the battle, ('enrage',) attacks twice a round.
BOSSES = {
    'bone king': {
        'depth': 10, 'phase': ('summon', 'skeleton'),
        'arrive': 'The air turns deathly still. The BONE KING holds court on this floor, '
                  'and the way down stays sealed until it falls.',
        'phase_msg': 'The BONE KING raised its scepter! The dead rise to defend it!',
        'defeat': 'The BONE KING crumbles to dust, and a hidden staircase grinds open!'},
    'frost wyrm': {
        'depth': FINAL_DEPTH, 'phase': ('enrage',),
        'arrive': 'Frost creeps across the floor. Somewhere on this level the FROST WYRM '
                  'lies coiled around the Amulet of Yendor...',
        'phase_msg': 'The FROST WYRM roared in fury! It attacks in a wild frenzy!',
        'defeat': 'The FROST WYRM shatters like glass. Something glitters among the shards...'},
}


def environment(depth):
    return next(e for e in reversed(ENVIRONMENTS) if depth >= e['depth'])


def boss_at(depth):
    return next((name for name, b in BOSSES.items() if b['depth'] == depth), None)

DIRS = {
    'h': (-1, 0), 'l': (1, 0), 'k': (0, -1), 'j': (0, 1),
    'y': (-1, -1), 'u': (1, -1), 'b': (-1, 1), 'n': (1, 1),
}
NUMPAD = {'1': 'b', '2': 'j', '3': 'n', '4': 'h', '6': 'l', '7': 'y', '8': 'k', '9': 'u'}
ARROWS = {
    curses.KEY_LEFT: 'h', curses.KEY_RIGHT: 'l', curses.KEY_UP: 'k', curses.KEY_DOWN: 'j',
}
CONFIRM_KEYS = {'\n', '\r', ' ', 'z'}
CANCEL_KEYS = {'\x1b', 'x'}

# ch, name, hp, ac, damage, xp, min depth, max depth, color, flags
MONSTERS = [
    # Dungeons of Doom
    ('r', 'rat',        4, 1, (1, 3),   2, 1, 3,  'yellow',  ''),
    ('B', 'bat',        5, 2, (1, 3),   3, 1, 4,  'magenta', 'erratic confuse'),
    ('k', 'kobold',     6, 2, (1, 4),   4, 1, 4,  'green',   ''),
    ('j', 'jackal',     7, 2, (1, 4),   5, 1, 5,  'yellow',  ''),
    ('g', 'goblin',    10, 3, (1, 6),   8, 2, 6,  'green',   ''),
    ('S', 'snake',     12, 3, (2, 5),  10, 3, 6,  'green',   'poison'),
    ('o', 'orc',       16, 4, (2, 7),  15, 3, 7,  'red',     ''),
    ('H', 'hobgoblin', 20, 5, (3, 8),  25, 4, 8,  'red',     ''),
    # Sunken Catacombs
    ('Z', 'zombie',    22, 3, (2, 8),  20, 5, 10, 'white',   'slow'),
    ('s', 'skeleton',  18, 4, (2, 8),  18, 6, 10, 'white',   ''),
    ('O', 'ogre',      32, 5, (4, 12), 45, 6, 10, 'yellow',  ''),
    ('u', 'ghoul',     26, 4, (3, 9),  30, 7, 11, 'green',   'paralyze'),
    ('T', 'troll',     36, 6, (4, 10), 60, 7, 11, 'green',   'regen'),
    ('W', 'wraith',    28, 7, (3, 9),  55, 7, 12, 'white',   'drain'),
    # Ember Caverns
    ('m', 'magma slug',   42, 5, (3, 10), 70,  11, 13, 'red',     'slow burn'),
    ('x', 'cave spider',  34, 7, (4, 10), 80,  11, 14, 'magenta', 'poison'),
    ('i', 'fire imp',     38, 7, (4, 11), 95,  11, 15, 'yellow',  'erratic burn'),
    ('c', 'basilisk',     50, 7, (5, 12), 120, 12, 15, 'green',   'paralyze'),
    ('D', 'dragon',       55, 8, (4, 12), 150, 12, 15, 'red',     ''),
    ('G', 'lava golem',   75, 8, (6, 14), 180, 13, 16, 'red',     'slow burn'),
    ('U', 'shadow demon', 65, 9, (6, 15), 220, 14, 17, 'magenta', 'drain'),
    # Frozen Abyss
    ('w', 'frost wolf',   50, 7, (5, 12), 150, 16, 19, 'cyan',    'frost'),
    ('Y', 'yeti',         68, 7, (6, 13), 190, 16, 20, 'white',   'frost'),
    ('b', 'banshee',      55, 9, (5, 13), 210, 17, 20, 'magenta', 'drain confuse'),
    ('T', 'ice troll',    72, 8, (6, 14), 240, 17, 20, 'cyan',    'regen frost'),
    ('F', 'frost giant',  85, 9, (7, 15), 280, 18, 20, 'blue',    'slow frost'),
    # bosses (never spawn at random)
    ('K', 'bone king',   150, 6, (5, 12), 600,  10, 10, 'yellow', 'boss drain'),
    ('D', 'frost wyrm',  220, 9, (6, 12), 1500, 20, 20, 'cyan',   'boss frost'),
]

# battle type, normal attack, special attack (30% chance, 1.5x damage)
MONSTER_INFO = {
    'rat':       ('beast',    'BITE',        'GNAW'),
    'bat':       ('beast',    'WING ATTACK', 'SCREECH'),
    'kobold':    ('humanoid', 'SCRATCH',     'DIRTY TRICK'),
    'jackal':    ('beast',    'BITE',        'POUNCE'),
    'goblin':    ('humanoid', 'STAB',        'SNEAK ATTACK'),
    'snake':     ('beast',    'BITE',        'POISON FANG'),
    'orc':       ('humanoid', 'CLUB',        'BERSERK'),
    'zombie':    ('undead',   'CLAW',        'ROTTEN GRASP'),
    'hobgoblin': ('humanoid', 'SLASH',       'CLEAVE'),
    'ogre':      ('giant',    'SMASH',       'BODY SLAM'),
    'troll':     ('giant',    'CLAW',        'REND'),
    'wraith':    ('undead',   'CHILL TOUCH', 'LIFE DRAIN'),
    'dragon':    ('dragon',   'CLAW',        'FIRE BREATH'),
    'magma slug':   ('elemental', 'SLIME',  'MAGMA SPIT'),
    'cave spider':  ('beast',     'BITE',   'VENOM WEB'),
    'fire imp':     ('demon',     'CLAW',   'FIREBALL'),
    'basilisk':     ('beast',     'BITE',   'STONE GAZE'),
    'lava golem':   ('elemental', 'SLAM',   'ERUPTION'),
    'shadow demon': ('demon',     'CLAW',   'SOUL REND'),
    'skeleton':     ('undead',    'BONE CLUB',  'RATTLE'),
    'ghoul':        ('undead',    'CLAW',       'FOUL BITE'),
    'frost wolf':   ('beast',     'BITE',       'ICE FANG'),
    'yeti':         ('giant',     'MAUL',       'AVALANCHE'),
    'banshee':      ('undead',    'WAIL',       'DEATH SHRIEK'),
    'ice troll':    ('giant',     'CLAW',       'GLACIAL REND'),
    'frost giant':  ('giant',     'STOMP',      'ICE HAMMER'),
    'bone king':    ('undead',    'SCEPTER BASH', 'DEATH CURSE'),
    'frost wyrm':   ('dragon',    'CLAW',       'FROST BREATH'),
}

# Player battle moves. Physical moves (mult) cost no mana and swing the wielded weapon;
# spells cost mana (mp) and roll d6s, plus the power of a magic weapon. effect: (status,
# % chance) put on the target by a hit. heal: d8s healed (plus 2 per level). barrier:
# rounds of halved damage. drain: share of the damage healed. mana: MP restored (plus 1
# per 2 levels). all: hits every foe in the battle.
MOVES = {
    'STRIKE':      {'type': 'normal',  'acc': 95,  'mp': 0, 'mult': 1.0},
    'POWER SMASH': {'type': 'normal',  'acc': 70,  'mp': 0, 'mult': 1.5},
    'FIRE BOLT':   {'type': 'fire',    'acc': 90,  'mp': 3, 'dice': 2, 'effect': ('burn', 25)},
    'FROST SHARD': {'type': 'ice',     'acc': 90,  'mp': 3, 'dice': 2, 'effect': ('freeze', 15)},
    'VENOM':       {'type': 'poison',  'acc': 95,  'mp': 3, 'dice': 1, 'effect': ('poison', 80)},
    'BEWILDER':    {'type': 'status',  'acc': 85,  'mp': 3, 'effect': ('confuse', 100)},
    'HEAL':        {'type': 'support', 'acc': 100, 'mp': 5, 'heal': 3},
    'MEDITATE':    {'type': 'support', 'acc': 100, 'mp': 0, 'mana': 4},
    'SLEEP':       {'type': 'status',  'acc': 75,  'mp': 4, 'effect': ('sleep', 100)},
    'HOLY LIGHT':  {'type': 'holy',    'acc': 100, 'mp': 5, 'dice': 3},
    'THUNDER':     {'type': 'storm',   'acc': 80,  'mp': 5, 'dice': 3, 'effect': ('paralyze', 30)},
    'CHAIN LIGHTNING': {'type': 'storm', 'acc': 85, 'mp': 8, 'dice': 2, 'all': True,
                        'effect': ('paralyze', 15)},
    'BARRIER':     {'type': 'support', 'acc': 100, 'mp': 4, 'barrier': 4},
    'DRAIN LIFE':  {'type': 'dark',    'acc': 95,  'mp': 5, 'dice': 2, 'drain': 0.5},
}
MAX_SPELLS = 4                   # spells known at once, on top of STRIKE and POWER SMASH
# Spells are only learned from rare spell scrolls: (first depth the scroll turns up, price)
SPELLS = {
    'FIRE BOLT': (1, 120), 'FROST SHARD': (2, 120), 'VENOM': (2, 100), 'BEWILDER': (3, 130),
    'HEAL': (3, 180), 'MEDITATE': (4, 150), 'SLEEP': (4, 150), 'HOLY LIGHT': (5, 220),
    'THUNDER': (6, 200), 'CHAIN LIGHTNING': (7, 260), 'BARRIER': (8, 200),
    'DRAIN LIFE': (9, 250),
}
SPELL_SCROLL_CHANCE = 0.05
MOVE_NOTES = {'burn': 'may burn', 'freeze': 'may freeze', 'poison': 'poisons',
              'sleep': 'puts to sleep', 'paralyze': 'may paralyze', 'confuse': 'confuses'}
# Super effective hits deal 1.5x (or 1.25x), so no weakness turns a fight into a one-shot.
EFFECTIVENESS = {
    ('fire', 'beast'): 1.5, ('fire', 'giant'): 1.5, ('fire', 'dragon'): 0.5,
    ('holy', 'undead'): 1.5, ('holy', 'dragon'): 1.25,
    ('fire', 'elemental'): 0.5, ('fire', 'demon'): 0.5, ('holy', 'demon'): 1.5,
    ('normal', 'undead'): 0.75,
    ('ice', 'dragon'): 1.5, ('ice', 'elemental'): 1.5, ('ice', 'demon'): 0.5,
    ('storm', 'humanoid'): 1.5, ('storm', 'beast'): 1.25, ('storm', 'elemental'): 0.5,
    ('poison', 'undead'): 0.5, ('poison', 'elemental'): 0.5, ('poison', 'giant'): 0.75,
    ('dark', 'humanoid'): 1.25, ('dark', 'undead'): 0.5, ('dark', 'demon'): 0.5,
}


def move_notes(info):
    """Short descriptions of what a move does, for the battle and spellbook screens."""
    notes = []
    if info.get('mult', 1) > 1:
        notes.append(f'weapon hit x{info["mult"]}')
    if info.get('all'):
        notes.append('hits every foe')
    for key, note in (('heal', 'heals, cures status'), ('barrier', 'halves damage taken'),
                      ('mana', 'restores MP'), ('drain', 'heals you as it hits')):
        if key in info:
            notes.append(note)
    if 'effect' in info:
        notes.append(MOVE_NOTES[info['effect'][0]])
    if notes:
        return notes
    return ['basic weapon attack'] if 'mult' in info else [f'{info["dice"]}d6 magic damage']


# Statuses a monster can suffer in battle: tag, turns, message. Burn and poison hurt every
# turn; sleep and freeze cost turns; paralysis has a 30% chance to each turn, and confusion
# a 1 in 3 chance that the monster hurts itself instead.
STATUSES = {
    'burn':     ('BRN', (3, 4), 'was burned!'),
    'poison':   ('PSN', (4, 6), 'was badly poisoned!'),
    'freeze':   ('FRZ', (1, 2), 'was frozen solid!'),
    'sleep':    ('SLP', (2, 4), 'fell asleep!'),
    'paralyze': ('PAR', (3, 5), 'is paralyzed! It may be unable to move!'),
    'confuse':  ('CNF', (2, 4), 'became confused!'),
}

LOG_SIZE = 1000                  # events kept for the event log (m)
# Log lines that contain one of these get a color, so big moments stand out.
LOG_HIGHLIGHTS = [('BOSS', 'red'), ('appeared!', 'red'), ('attacked!', 'red'),
                  ('joined the battle', 'red'), ('fainted...', 'red'),
                  ('grew to level', 'yellow'), ('learned', 'green'), ('You won the battle', 'green')]

# name, damage range, magic power. Physical weapons hit hard and enchant into harder hits.
# Magic weapons barely hurt in melee, but add their power (and enchantment) to every spell.
WEAPONS = [('dagger', 1, 4, 0), ('spear', 2, 6, 0), ('mace', 2, 8, 0),
           ('long sword', 3, 10, 0), ('two-handed sword', 4, 14, 0),
           ('wand', 1, 2, 2), ('oak staff', 1, 4, 3), ('crystal rod', 1, 3, 5),
           ('runed staff', 2, 5, 7)]
ARMORS = [('leather armor', 2), ('studded leather', 3), ('ring mail', 3),
          ('scale mail', 4), ('chain mail', 5), ('splint mail', 6), ('plate mail', 7)]
POTIONS = ['healing', 'extra healing', 'mana', 'strength', 'poison', 'confusion', 'raise level']
POTION_WEIGHTS = [30, 10, 16, 12, 15, 15, 6]
POTION_PRICES = {'healing': 30, 'extra healing': 80, 'mana': 50, 'strength': 120,
                 'poison': 5, 'confusion': 5, 'raise level': 150}
SCROLLS = ['magic mapping', 'teleportation', 'enchant weapon', 'enchant armor',
           'identify', 'aggravate monsters', 'detect traps']
SCROLL_WEIGHTS = [12, 12, 15, 15, 25, 8, 12]
SCROLL_PRICES = {'magic mapping': 50, 'teleportation': 40, 'enchant weapon': 70,
                 'enchant armor': 70, 'identify': 25, 'aggravate monsters': 5,
                 'detect traps': 30}
POTION_COLORS = ['red', 'blue', 'green', 'amber', 'violet', 'turquoise', 'black',
                 'pink', 'white', 'orange', 'grey', 'golden']
SYLLABLES = ['ab', 'zok', 'ra', 'nix', 'vel', 'tor', 'um', 'ka', 'zim', 'ol',
             'eth', 'qua', 'bar', 'sno', 'pli', 'xu', 'mor', 'fen', 'gah', 'ip']
ITEM_CHARS = {'potion': '!', 'scroll': '?', 'weapon': ')', 'armor': ']',
              'food': ':', 'gold': '*', 'amulet': '"'}
ITEM_COLORS = {'potion': 'magenta', 'scroll': 'cyan', 'weapon': 'cyan', 'armor': 'cyan',
               'food': 'yellow', 'gold': 'yellow', 'amulet': 'magenta'}
STACKABLE = {'potion', 'scroll', 'food'}


def sprite(art):
    return art.strip('\n').split('\n')


SPRITES = {
    'player': sprite(r'''
       ___
      /   \
     | /^\ |
    /|=====|\
   / |     | \
     |__|__|
'''),
    'rat': sprite(r'''
     __     __
    /  \___/  \
    \ (o) (o) /
     \   v   /____~~~
      '-----'
'''),
    'bat': sprite(r'''
 /\                 /\
/ \'._   (\_/)   _.'/ \
|.''._'--(o.o)--'_.''.|
 \_ / `;=/ " \=;` \ _/
   `\__| \___/ |__/`
'''),
    'kobold': sprite(r'''
    /\___/\
   ( o   o )
    \  ^  /  _/
   /|'---'|\/
    |_____|
    /     \
'''),
    'jackal': sprite(r'''
     /\    /\
    /  \__/  \
   |  o    o  |
    \   /\   /___
     \  \/  /    \~
      '----'
'''),
    'goblin': sprite(r'''
  ,         ,
  \`-.___.-`/
   \ (o) (o)/
    |  ^^  |
    | \__/ |
     `----`
'''),
    'snake': sprite(r'''
       ____
      / o o\
      \  __/~<
       \ \
    ___/ /
   (____/
'''),
    'orc': sprite(r'''
    _______
   / ^   ^ \
  |  O   O  |
  |  \___/  |
   \ |   | /
    `-----`
'''),
    'zombie': sprite(r'''
     .----.
    ( x  x )
     \ ~~ /
  ---|    |---
     |    |
     /    \
'''),
    'hobgoblin': sprite(r'''
   /\_____/\
  /  o   o  \
 |    ___    |
  \  |VVV|  /
   \_|___|_/
'''),
    'ogre': sprite(r'''
    .-------.
   /  O   O  \
  |    (_)    |
  |  \_____/  |
   \_________/
    |       |
'''),
    'troll': sprite(r'''
    ,/~~~~\,
   / o    o \
  |   ,--,   |
  |  /VVVV\  |
   \________/
   /|      |\
'''),
    'wraith': sprite(r'''
     .-~~~-.
    /  o o  \
   |    ^    |
    \  ~~~  /
     )     (
    /_/\_/\_\
'''),
    'dragon': sprite(r'''
     __    __
    /  \~~/  \    /\
   | O      O |__/  \
    \  ^^^^  /  ~~~  >
     \_/\/\_/ \__/\_/
       /  \
'''),
    'magma slug': sprite(r'''
        .-~~~-.
     .-' o   o '-.
    (   ~~~~~~~   )
   (~~~~~~~~~~~~~~~)
    `~-~-~-~-~-~-~`
'''),
    'cave spider': sprite(r'''
   \  \   ___   /  /
    \__\ (o o) /__/
    /  / (_v_) \  \
   /  /   `-`   \  \
'''),
    'fire imp': sprite(r'''
     (       )
    /\ )   ( /\
   / (o) (o)  \
   \    \_/   /
    `-._____.-'
      /|   |\
'''),
    'basilisk': sprite(r'''
       _____
    .-' o o '-.___
   <  ===         `>
    `-.____.--'~~
      //     \\
'''),
    'lava golem': sprite(r'''
    ._________.
    |[o]   [o]|
   /|  ~~~~~  |\
  | |_________| |
     |  | |  |
     |__| |__|
'''),
    'shadow demon': sprite(r'''
   /\         /\
  /  \_______/  \
  \  ( >   < )  /
   \  \ VVV /  /
    \_ `---' _/
      \_____/
'''),
    'skeleton': sprite(r'''
      .---.
     / x x \
     \  ^  /
   ,--`|||`--,
      /|||\
     _/   \_
'''),
    'ghoul': sprite(r'''
     ,----.
    ( o  o )
    |  ww  |
  __/`----'\__
 /  |      |  \
    /_/  \_\
'''),
    'frost wolf': sprite(r'''
    /\     /\
   /  \___/  \
  |  *     *  |
   \    ^    /____
    \  ===  /  *  \~
     `-----'
'''),
    'yeti': sprite(r'''
     .-"""-.
    / o   o \
   |  .---.  |
   | ( www ) |
  /|\ `---' /|\
 / |_______| \
'''),
    'banshee': sprite(r'''
     .-~~~-.
    / O   O \
   |    o    |
    \       /
   ~ )~~~~~( ~
  ~ /_~ ~ ~_\ ~
'''),
    'ice troll': sprite(r'''
   *,/~~~~\,*
   / *    * \
  |   ,--,   |
  |  /VVVV\  |
   \________/
   /|  **  |\
'''),
    'frost giant': sprite(r'''
     _[^^^^^]_
    /  o   o  \
   |    ___    |
   |   /VVV\   |
  /|\_________/|\
   | |   |   | |
'''),
    'bone king': sprite(r'''
       _/\_/\_/\_
       \________/
       /  ___   \
      | (X) (X) |
       \   ^   /
        |VVVVV|
   ____/|_____|\____
  (____|  |||  |____)
'''),
    'frost wyrm': sprite(r'''
          __/\__/\__
    /\   / *      * \   /\
   /  \_|   ____    |_/  \
   \    |  /VVVV\   |    /
    \__/ \ \^^^^/  / \__/
          \ `--'  /
     ~*~~~~\/~~~~\/~~~~*~
'''),
}

# kind: (display name, color, portrait)
NPC_INFO = {
    'sage': ('ELDER MOSS', 'green', sprite(r'''
   .---.
  / ~ ~ \
  | o o |
  | \_/ |
  /|||||\
''')),
    'merchant': ('PIP THE PEDDLER', 'yellow', sprite(r'''
   _____
  |_____|
  ( o o )
   ( $ )
  /|___|\
''')),
    'healer': ('SISTER WREN', 'cyan', sprite(r'''
   .---.
  ( ^ ^ )
   \ - /
  /|_+_|\
   |   |
''')),
    'bard': ('FINCH THE BARD', 'magenta', sprite(r'''
    __/~
   ( o o)
    \ o/ _
   /|__|/#|
    |  |
''')),
    'hermit': ('OLD GRUB', 'white', sprite(r'''
   ~~~~~
  ( - - )
  (  o  )
  ~~|||~~
   /   \
''')),
}

SONGS = [
    ['~ Down in the dark where the kobolds creep,',
     '  the brave go down and the wise stay asleep! ~'],
    ['~ Past the halls of stone where the caverns burn,',
     '  lies the Amulet... and heroes who never return! ~'],
    ['~ A rat, a bat, a jackal or three,',
     '  none are a match for the likes of thee! ~'],
    ['~ Feed the hermit, pay the priest,',
     '  and you just might survive the beast! ~'],
]
LORE = [
    'Trolls heal themselves as they fight. Finish them quickly, or burn them!',
    'Wraiths drain your very life. HOLY light sends them back to the grave.',
    'Dragons laugh at fire, but a FROST SHARD bites deep. Unless the dragon is made of frost!',
    'The undead never sleep, and poison means nothing to them. Plan your spells accordingly.',
    'THUNDER rattles orcs and goblins worst of all. Golems hardly notice it.',
    'Ghouls and basilisks can paralyze you. Keep a potion of healing handy to shake it off.',
    'Bosses cannot be put to sleep or frozen, but burns and paralysis still work on them.',
    'Zombies are slow, but they hit hard. Strike first.',
    'If you feel lost, a scroll of magic mapping is worth its weight in gold.',
    'Not every floor tile is what it seems. Search (s) before you walk where others fell.',
    'Below the dungeon lie the Ember Caverns. Fire does little to imps and golems there.',
    'Shadow demons and fire imps fear HOLY light above all else.',
    'The Bone King rules the Catacombs from depth 10. Wound it and it calls its skeletons.',
    'The Frost Wyrm guards the Amulet on depth 20. Fire barely warms it, but HOLY light does.',
    'Nobody runs from a boss. Bring healing potions and save your mana for the fight.',
    'Out of mana? MEDITATE costs nothing, and a potion of mana fills you right up.',
    'Golems and slugs have no minds to BEWILDER. Bosses are far too proud to be fooled.',
    'A sword makes your STRIKEs hurt, but a staff or wand makes every spell burn brighter.',
    'Giants of the Frozen Abyss hate fire. A FIRE BOLT melts them like snow.',
    'Never linger in a fight near a crowd. The whole room will come to the party.',
]

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


def xp_needed(level):
    return 10 * 2 ** (level - 1)


class Room:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def overlaps(self, o, margin):
        return (self.x - margin < o.x + o.w and o.x - margin < self.x + self.w and
                self.y - margin < o.y + o.h and o.y - margin < self.y + self.h)

    def corners(self):
        x2, y2 = self.x + self.w - 1, self.y + self.h - 1
        return {(self.x, self.y), (x2, self.y), (self.x, y2), (x2, y2)}


class Item:
    def __init__(self, kind, sub=None, count=1, ench=0):
        self.kind, self.sub, self.count, self.ench = kind, sub, count, ench
        self.x = self.y = 0
        self.seen = False
        self.dmg = (1, 3)
        self.magic = 0               # spell power of a magic weapon
        self.ac = 0


def make_weapon(name, ench=0):
    lo, hi, magic = next((lo, hi, magic) for n, lo, hi, magic in WEAPONS if n == name)
    it = Item('weapon', name, ench=ench)
    it.dmg, it.magic = (lo, hi), magic
    return it


def make_armor(name, ench=0):
    it = Item('armor', name, ench=ench)
    it.ac = next(ac for n, ac in ARMORS if n == name)
    return it


class Trap:
    def __init__(self, kind):
        self.kind = kind
        self.found = False

    @property
    def name(self):
        return TRAPS[self.kind][0]


class Monster:
    def __init__(self, tpl, x, y, depth=0):
        ch, name, hp, ac, dmg, xp, lo, _hi, color, flags = tpl
        self.ch, self.name, self.ac, self.dmg, self.xp = ch, name, ac, dmg, xp
        self.type, *self.moves = MONSTER_INFO[name]
        self.power = lo * 2 + 1
        self.level = max(1, lo * 2 - 1 + random.randint(0, 2))
        hp = int(hp * (1 + 0.06 * max(0, depth - lo)))      # tougher the deeper they live
        self.hp = self.max_hp = hp + random.randint(0, hp // 3)
        self.color = color
        self.flags = flags.split()
        self.x, self.y = x, y
        self.awake = random.random() < 0.5
        self.stun = 0
        self.phased = False          # a boss has switched tactics at half HP
        self.status = {}             # battle status -> turns left (see STATUSES)


class NPC:
    def __init__(self, kind, x, y):
        self.kind, self.x, self.y = kind, x, y
        self.name, self.color, self.portrait = NPC_INFO[kind]
        self.talked = 0
        self.done = False
        self.stock = []


class Player:
    def __init__(self):
        self.x = self.y = 0
        self.hp = self.max_hp = 16
        self.str = self.max_str = 16
        self.level = 1
        self.xp = 0
        self.gold = 0
        self.food = 1500
        self.pack = []
        self.weapon = None
        self.armor = None
        self.confused = 0
        self.stuck = 0               # turns left climbing out of a pit
        self.burn = 0                # turns left burning (hurts every turn)
        self.frozen = 0              # turns left frozen solid (can't act)
        self.paralyzed = 0           # turns left paralyzed (30% chance to lose each action)
        self.barrier = 0             # turns left of halved damage
        self.regen = 0
        self.mp = self.max_mp = 10   # mana that spells cost
        self.mana_regen = 0
        self.moves = ['STRIKE', 'POWER SMASH']    # plus up to MAX_SPELLS spells

    def cure(self):
        self.confused = self.burn = self.frozen = self.paralyzed = 0

    @property
    def ac(self):
        return self.armor.ac + self.armor.ench if self.armor else 0

    @property
    def str_bonus(self):
        return max(-3, (self.str - 16) // 2)

    @property
    def spells(self):
        return [m for m in self.moves if m in SPELLS]

    @property
    def weapon_dmg(self):
        """Damage range of a weapon blow before strength. Enchanting a magic weapon adds to
        its spell power instead."""
        w = self.weapon
        if not w:
            return 1, 3
        bonus = 0 if w.magic else w.ench
        return w.dmg[0] + bonus, w.dmg[1] + bonus

    @property
    def spell_power(self):
        """Extra damage a magic weapon adds to every attack spell."""
        w = self.weapon
        return w.magic + w.ench if w and w.magic else 0

    def restore_mp(self, amount=None):
        self.mp = self.max_mp if amount is None else min(self.max_mp, self.mp + amount)


class Game:
    def __init__(self, scr, name):
        self.scr = scr
        self.name = name
        self.player = Player()
        self.depth = 0
        self.turn = 0
        self.msgs = []
        self.log = []                # event log: [turn, depth, text, times repeated]
        self.known = set()
        self.potion_look = dict(zip(POTIONS, random.sample(POTION_COLORS, len(POTIONS))))
        self.scroll_look = {s: self.random_title() for s in SCROLLS}
        self.game_over = None        # ('died', reason) | ('won',) | ('quit',)
        self.visible = set()
        self.foes = []               # monsters in the current battle; foes[0] is the target
        self.battles = 0             # battles fought (lets a sleeping player notice an attack)
        self.asleep = False          # knocked out by sleeping gas
        self.fallen = None           # last foe beaten, still shown while rewards are read out
        self.shown_hp = [0, 0]       # HP values the battle bars are showing (for animation)
        self.hermit_spawned = False
        self.auto_skip = False       # resolve easy battles without the battle screen
        self.traps = {}              # (x, y) -> Trap
        self.env = ENVIRONMENTS[0]   # the environment of the current level

        p = self.player
        p.weapon = make_weapon('mace', 1)
        p.armor = make_armor('ring mail', 1)
        p.pack = [p.weapon, p.armor, Item('food')]
        self.new_level()
        self.msg(f'Welcome to the Dungeons of Doom, {name}! Someone is waiting to talk to you (&).')

    # ------------------------------------------------------------ helpers
    @staticmethod
    def random_title():
        words = [''.join(random.sample(SYLLABLES, random.randint(1, 3)))
                 for _ in range(random.randint(2, 3))]
        return ' '.join(words)

    def msg(self, text):
        self.msgs.append(text)
        self.record(text)

    def record(self, text):
        """Add an event to the log. A repeat of the last event just bumps its count."""
        last = self.log[-1] if self.log else None
        if last and last[2] == text and last[1] == self.depth:
            last[0], last[3] = self.turn, last[3] + 1
            return
        self.log.append([self.turn, self.depth, text, 1])
        del self.log[:-LOG_SIZE]

    def walkable(self, x, y):
        return 0 <= x < MAP_W and 0 <= y < MAP_H and self.tiles[y][x] in WALKABLE

    def monster_at(self, x, y):
        return next((m for m in self.monsters if m.x == x and m.y == y), None)

    def npc_at(self, x, y):
        return next((n for n in self.npcs if n.x == x and n.y == y), None)

    def item_at(self, x, y):
        return next((i for i in self.items if i.x == x and i.y == y), None)

    def occupied(self, x, y):
        return (self.monster_at(x, y) or self.npc_at(x, y)
                or (x, y) == (self.player.x, self.player.y))

    def visible_monsters(self):
        return [m for m in self.monsters if (m.x, m.y) in self.visible]

    def item_name(self, it, reveal=False):
        n = it.count
        if it.kind == 'gold':
            return f'{n} gold pieces'
        if it.kind == 'amulet':
            return 'the Amulet of Yendor'
        if it.kind == 'food':
            return 'a food ration' if n == 1 else f'{n} food rations'
        # enchantment is already counted in the stats shown, so it isn't listed separately
        if it.kind == 'weapon' and it.magic:
            return an(f'{it.sub} (hits {it.dmg[0]}-{it.dmg[1]}, spells +{it.magic + it.ench})')
        if it.kind == 'weapon':
            return an(f'{it.sub} (hits {it.dmg[0] + it.ench}-{it.dmg[1] + it.ench})')
        if it.kind == 'armor':
            return an(f'{it.sub} (defense {it.ac + it.ench})')
        noun = it.kind if n == 1 else it.kind + 's'
        if it.sub in SPELLS:                       # spell scrolls are always recognized
            base = f'spell {noun} of {it.sub}'
        elif reveal or it.sub in self.known:
            base = f'{noun} of {it.sub}'
        elif it.kind == 'potion':
            base = f'{self.potion_look[it.sub]} {noun}'
        else:
            base = f'{noun} titled "{self.scroll_look[it.sub]}"'
        return an(base) if n == 1 else f'{n} {base}'

    def describe(self, it):
        s = self.item_name(it)
        if it is self.player.weapon:
            s += ' (in hand)'
        if it is self.player.armor:
            s += ' (being worn)'
        return s

    def price(self, it):
        if it.kind == 'potion':
            base = POTION_PRICES[it.sub]
        elif it.sub in SPELLS:
            base = SPELLS[it.sub][1]
        elif it.kind == 'scroll':
            base = SCROLL_PRICES[it.sub]
        elif it.kind == 'food':
            base = 15
        elif it.kind == 'weapon':
            base = (it.dmg[0] + it.dmg[1]) * 6 + it.magic * 25 + it.ench * 30
        else:
            base = it.ac * 18 + it.ench * 30
        return max(5, base)

    # ------------------------------------------------------- level creation
    def new_level(self):
        self.depth += 1
        env = self.env = environment(self.depth)
        while True:
            self.tiles = [[ROCK] * MAP_W for _ in range(MAP_H)]
            if env['layout'] == 'caves':
                rooms = self.make_caves(env['pools'])
            elif env['layout'] == 'crypts':
                rooms = self.make_rooms(12, (5, 10), (5, 7))
            else:
                rooms = self.make_rooms()
            if len(rooms) >= 4:
                break
        self.rooms = rooms
        self.explored = [[False] * MAP_W for _ in range(MAP_H)]
        self.monsters, self.items, self.npcs = [], [], []
        p = self.player
        p.x, p.y = self.free_spot(rooms[0])

        others = rooms[1:]
        boss = boss_at(self.depth)
        if boss:
            # the boss waits in the room farthest from the start; no stairs until it falls
            sx, sy = rooms[0].center()
            lair = max(others, key=lambda r: abs(r.center()[0] - sx) + abs(r.center()[1] - sy))
            tpl = next(t for t in MONSTERS if t[1] == boss)
            m = Monster(tpl, *self.free_spot(lair), self.depth)
            m.awake = True
            self.monsters.append(m)
            others = [r for r in others if r is not lair] or others
        else:
            sx, sy = self.free_spot(random.choice(others))
            self.tiles[sy][sx] = STAIRS

        if self.depth == 1:
            self.add_npc('sage', rooms[0])
        elif boss:
            self.add_npc('healer', rooms[0])     # one last chance to patch up first
        else:
            for kind, chance in (('merchant', 0.5), ('healer', 0.35), ('bard', 0.3)):
                if random.random() < chance:
                    self.add_npc(kind, random.choice(rooms))
            if not self.hermit_spawned and (random.random() < 0.3 or self.depth == 6):
                self.hermit_spawned = True
                self.add_npc('hermit', random.choice(rooms))

        eligible = self.eligible_monsters()
        for _ in range(4 + self.depth // 2 + random.randint(0, 3)):
            x, y = self.free_spot(random.choice(others))
            self.monsters.append(Monster(random.choice(eligible), x, y, self.depth))

        for _ in range(random.randint(3, 6)):
            self.place_item(self.random_item(), random.choice(rooms))
        if self.depth == env['depth'] and self.depth > 1:
            # every new environment hides one spell scroll; the Catacombs offer the light
            # that undoes the Bone King
            it = Item('scroll', 'HOLY LIGHT') if env['layout'] == 'crypts' else self.spell_scroll()
            self.place_item(it, random.choice(others))
        for _ in range(random.randint(1, 3)):
            gold = Item('gold', count=random.randint(3, 8 + self.depth * 4))
            self.place_item(gold, random.choice(rooms))
        self.place_traps()
        self.compute_fov()

    def eligible_monsters(self):
        return [t for t in MONSTERS if t[6] <= self.depth <= t[7] and 'boss' not in t[9]]

    def place_traps(self):
        p = self.player
        self.traps = {}
        kinds = self.env['traps']
        if boss_at(self.depth):
            kinds = [k for k in kinds if k != 'trapdoor']     # no falling past a boss
        spots = [(x, y) for y in range(MAP_H) for x in range(MAP_W)
                 if self.tiles[y][x] in (FLOOR, CORRIDOR) and not self.occupied(x, y)
                 and not self.item_at(x, y) and max(abs(x - p.x), abs(y - p.y)) > 3]
        n = self.depth // 3 + random.randint(0, 2)
        for pos in random.sample(spots, min(n, len(spots))):
            self.traps[pos] = Trap(random.choice(kinds))

    def add_npc(self, kind, room):
        npc = NPC(kind, *self.free_spot(room))
        if kind == 'merchant':
            npc.stock = [self.shop_item() for _ in range(random.randint(4, 6))]
        self.npcs.append(npc)

    def shop_item(self):
        while True:
            it = self.random_item()
            if it.sub not in ('poison', 'confusion', 'aggravate monsters'):
                return it

    def make_rooms(self, max_rooms=9, widths=(6, 16), heights=(5, 8)):
        rooms = []
        for _ in range(300):
            if len(rooms) >= max_rooms:
                break
            w, h = random.randint(*widths), random.randint(*heights)
            x, y = random.randint(0, MAP_W - w - 1), random.randint(0, MAP_H - h - 1)
            r = Room(x, y, w, h)
            if any(r.overlaps(o, 2) for o in rooms):
                continue
            rooms.append(r)
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    if yy in (y, y + h - 1):
                        self.tiles[yy][xx] = HWALL
                    elif xx in (x, x + w - 1):
                        self.tiles[yy][xx] = VWALL
                    else:
                        self.tiles[yy][xx] = FLOOR
        self.corners = set().union(*(r.corners() for r in rooms)) if rooms else set()
        rooms.sort(key=lambda r: r.center()[0])
        for a, b in zip(rooms, rooms[1:]):
            self.tunnel(a, b)
        for _ in range(2):
            if len(rooms) > 2:
                self.tunnel(*random.sample(rooms, 2))
        return rooms

    def make_caves(self, pools):
        """Cellular-automaton caves dotted with pools (lava or icy water).
        Returns zones of the map that the rest of the code uses like rooms."""
        W, H = MAP_W, MAP_H
        cave = [[0 < x < W - 1 and 0 < y < H - 1 and random.random() < 0.56
                 for x in range(W)] for y in range(H)]
        for _ in range(5):
            cave = [[0 < x < W - 1 and 0 < y < H - 1 and
                     sum(not cave[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) < 5
                     for x in range(W)] for y in range(H)]
        pool_cells = set()
        open_cells = [(x, y) for y in range(H) for x in range(W) if cave[y][x]]
        for _ in range(random.randint(*pools)):
            x, y = random.choice(open_cells)
            for _ in range(random.randint(4, 14)):
                if cave[y][x]:
                    cave[y][x] = False
                    pool_cells.add((x, y))
                dx, dy = random.choice(list(DIRS.values()))
                if 0 < x + dx < W - 1 and 0 < y + dy < H - 1:
                    x, y = x + dx, y + dy
        # keep only the biggest connected cave so everything is reachable
        best, seen = set(), set()
        for start in open_cells:
            if start in seen or not cave[start[1]][start[0]]:
                continue
            region, q = {start}, deque([start])
            while q:
                x, y = q.popleft()
                for dx, dy in DIRS.values():
                    n = (x + dx, y + dy)
                    if n not in region and cave[n[1]][n[0]]:
                        region.add(n)
                        q.append(n)
            seen |= region
            if len(region) > len(best):
                best = region
        if len(best) < 650:
            return []
        near = lambda x, y: any((x + dx, y + dy) in best for dx, dy in DIRS.values())
        for y in range(H):
            for x in range(W):
                if (x, y) in best:
                    self.tiles[y][x] = FLOOR
                elif near(x, y):
                    self.tiles[y][x] = POOL if (x, y) in pool_cells else CAVE_WALL
        self.corners = set()
        zones = []
        for zx in range(0, W, 20):
            for zy in (0, 10):
                z = Room(zx, zy, 20, 11)
                cells = sum(self.tiles[y][x] == FLOOR for y in range(zy + 1, zy + 10)
                            for x in range(zx + 1, zx + 19))
                if cells >= 25:
                    zones.append(z)
        zones.sort(key=lambda r: r.center()[0])
        return zones

    def tunnel(self, a, b):
        """Dig a corridor between two rooms. Walls are expensive and may only be
        crossed head-on, so corridors make clean doorways instead of running
        along a wall."""
        start, goal = a.center(), b.center()
        dist, prev = {start: 0}, {}
        heap = [(0, start)]
        while heap:
            d, (x, y) = heapq.heappop(heap)
            if (x, y) == goal:
                break
            if d > dist[(x, y)]:
                continue
            here = self.tiles[y][x]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 < nx < MAP_W - 1 and 0 < ny < MAP_H - 1) or (nx, ny) in self.corners:
                    continue
                t = self.tiles[ny][nx]
                horizontal = dy == 0
                if (HWALL in (t, here) and horizontal) or (VWALL in (t, here) and not horizontal):
                    continue
                cost = 30 if t in (HWALL, VWALL) else 2 if t == ROCK else 1
                nd = d + cost + random.random() * 0.5
                if nd < dist.get((nx, ny), float('inf')):
                    dist[(nx, ny)] = nd
                    prev[(nx, ny)] = (x, y)
                    heapq.heappush(heap, (nd, (nx, ny)))
        node = goal
        while node in prev:
            x, y = node
            t = self.tiles[y][x]
            if t == ROCK:
                self.tiles[y][x] = CORRIDOR
            elif t in (HWALL, VWALL):
                self.tiles[y][x] = DOOR
            node = prev[node]

    def free_spot(self, room):
        for _ in range(500):
            x = random.randint(room.x + 1, room.x + room.w - 2)
            y = random.randint(room.y + 1, room.y + room.h - 2)
            if self.tiles[y][x] == FLOOR and not self.occupied(x, y) and not self.item_at(x, y):
                return x, y
        for y in range(room.y + 1, room.y + room.h - 1):
            for x in range(room.x + 1, room.x + room.w - 1):
                if self.tiles[y][x] == FLOOR and not self.occupied(x, y):
                    return x, y
        return room.center()

    def place_item(self, it, room):
        it.x, it.y = self.free_spot(room)
        self.items.append(it)

    def spell_scroll(self):
        """A rare scroll that teaches a spell, favoring spells the player doesn't know yet."""
        known = set(self.player.moves)
        spells =[s for s, (depth, _price) in SPELLS.items() if depth <= self.depth]
        return Item('scroll', random.choices(spells, [1 if s in known else 4 for s in spells])[0])

    def random_item(self):
        if random.random() < SPELL_SCROLL_CHANCE:
            return self.spell_scroll()
        roll = random.randint(1, 100)
        if roll <= 30:
            return Item('potion', random.choices(POTIONS, POTION_WEIGHTS)[0])
        if roll <= 58:
            return Item('scroll', random.choices(SCROLLS, SCROLL_WEIGHTS)[0])
        if roll <= 72:
            return Item('food')
        ench = random.choices([-1, 0, 1, 2], [2, 5, 3, 1])[0]
        if roll <= 86:
            return make_weapon(random.choice(WEAPONS)[0], ench)
        return make_armor(random.choice(ARMORS)[0], ench)

    # ------------------------------------------------------------------ fov
    def compute_fov(self):
        p, r = self.player, FOV_RADIUS
        self.visible = {(p.x, p.y)}
        for i in range(-r, r + 1):
            for tx, ty in ((p.x + i, p.y - r), (p.x + i, p.y + r),
                           (p.x - r, p.y + i), (p.x + r, p.y + i)):
                self.cast_ray(p.x, p.y, tx, ty)
        # light up walls next to visible floor so rooms look complete
        for x, y in list(self.visible):
            if self.tiles[y][x] in WALKABLE:
                for dx, dy in DIRS.values():
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < MAP_W and 0 <= ny < MAP_H and self.tiles[ny][nx] in WALLS:
                        self.visible.add((nx, ny))
        for x, y in self.visible:
            self.explored[y][x] = True

    def cast_ray(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
        err, x, y = dx + dy, x0, y0
        r2 = FOV_RADIUS * FOV_RADIUS + FOV_RADIUS
        while True:
            if not (0 <= x < MAP_W and 0 <= y < MAP_H):
                return
            if (x - x0) ** 2 + (y - y0) ** 2 > r2:
                return
            self.visible.add((x, y))
            if (x, y) != (x0, y0) and self.tiles[y][x] in OPAQUE:
                return
            if (x, y) == (x1, y1):
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    # -------------------------------------------------------------- turns
    def end_turn(self):
        if self.game_over:
            return
        self.monsters_act()
        if self.game_over:
            return
        self.tick_player()
        self.turn += 1
        self.compute_fov()

    def tick_player(self):
        p = self.player
        p.food -= 1
        if p.food == 300:
            self.msg('You are starting to get hungry.')
        elif p.food == 150:
            self.msg('You feel weak with hunger.')
        elif p.food == 0:
            self.msg('You are starving to death!')
        if p.food <= 0:
            p.hp -= 1
            if p.hp <= 0:
                self.die('starvation')
                return
        else:
            p.regen += 1
            if p.regen >= max(3, 14 - p.level) and p.hp < p.max_hp:
                p.hp += 1
                p.regen = 0
            p.mana_regen += 1
            if p.mana_regen >= max(3, 10 - p.level // 2) and p.mp < p.max_mp:
                p.mp += 1
                p.mana_regen = 0
        if p.confused:
            p.confused -= 1
            if not p.confused:
                self.msg('You feel less confused now.')
        if p.burn:
            p.burn -= 1
            if self.foes:
                self.msg(f'{self.name} was hurt by the burn!')
            elif not p.burn:
                self.msg('Your burns stop smarting.')
            self.hurt(random.randint(1, 3) + self.depth // 6, 'burns')
        if p.frozen and not self.foes:    # in battle, frozen counts lost actions instead
            p.frozen -= 1
            if not p.frozen:
                self.msg('You thaw out.')
        if p.paralyzed:
            p.paralyzed -= 1
            if not p.paralyzed:
                self.msg('You can move freely again.')
        if p.barrier:
            p.barrier -= 1
            if not p.barrier:
                self.msg('Your barrier fades away.')

    def die(self, reason):
        self.player.hp = 0
        self.game_over = ('died', reason)

    def gain_xp(self, amount):
        p = self.player
        p.xp += amount
        while p.xp >= xp_needed(p.level):
            p.level += 1
            gain = random.randint(4, 9)
            p.max_hp += gain
            p.hp += gain
            p.max_mp += random.randint(2, 4)
            p.restore_mp()
            self.msg(f'{self.name} grew to level {p.level}!')

    # ------------------------------------------------------------ monsters
    def dist_map(self):
        p = self.player
        dist = {(p.x, p.y): 0}
        q = deque([(p.x, p.y)])
        while q:
            x, y = q.popleft()
            d = dist[(x, y)]
            if d >= 30:
                continue
            for dx, dy in DIRS.values():
                n = (x + dx, y + dy)
                if n not in dist and self.walkable(*n):
                    dist[n] = d + 1
                    q.append(n)
        return dist

    def monsters_act(self):
        p = self.player
        dist = self.dist_map()
        for m in list(self.monsters):
            if self.game_over:
                return
            if m not in self.monsters:
                continue
            if m.stun:
                m.stun -= 1
                continue
            if 'slow' in m.flags and self.turn % 2:
                continue
            if 'regen' in m.flags and m.hp < m.max_hp:
                m.hp += 1
            if m in self.foes:
                continue
            near = max(abs(m.x - p.x), abs(m.y - p.y))
            if not m.awake:
                if ((m.x, m.y) in self.visible and random.random() < 0.3) or \
                        (self.foes and near <= 7 and random.random() < 0.25):   # battle noise
                    m.awake = True
                else:
                    continue
            if 'boss' in m.flags and near > 1:
                continue                 # bosses wait in their lair
            if 'erratic' in m.flags and random.random() < 0.5:
                self.monster_step(m, *random.choice(list(DIRS.values())))
                continue
            if near == 1:
                if self.foes:
                    self.foes.append(m)
                    self.msg(f'A {self.called(m)} joined the battle!')
                else:
                    self.battle(m, ambush=True)
                continue
            d = dist.get((m.x, m.y))
            if d is None:
                if random.random() < 0.5:
                    self.monster_step(m, *random.choice(list(DIRS.values())))
                continue
            steps = [(dx, dy) for dx, dy in DIRS.values()
                     if dist.get((m.x + dx, m.y + dy), 999) < d
                     and not self.occupied(m.x + dx, m.y + dy)]
            if steps:
                random.shuffle(steps)
                dx, dy = min(steps, key=lambda s: dist[(m.x + s[0], m.y + s[1])])
                m.x += dx
                m.y += dy

    def monster_step(self, m, dx, dy):
        nx, ny = m.x + dx, m.y + dy
        if self.walkable(nx, ny) and not self.occupied(nx, ny):
            m.x, m.y = nx, ny

    # -------------------------------------------------------------- battle
    @property
    def foe(self):
        """The monster we're currently targeting in battle."""
        return self.foes[0] if self.foes else None

    @staticmethod
    def called(m):
        """How battle text names a monster: 'wild RAT', or just 'BONE KING' for a boss."""
        return m.name.upper() if 'boss' in m.flags else f'wild {m.name.upper()}'

    def battle(self, m, ambush=False):
        p = self.player
        m.awake = True
        self.foes = [m]
        self.battles += 1
        caught, self.asleep = self.asleep, False
        if 'boss' in m.flags:
            intro = f'BOSS BATTLE! The {m.name.upper()} blocks the way!'
        else:
            intro = f'A wild {m.name.upper()} {"attacked" if ambush else "appeared"}!'
        if self.auto_skip and not caught and self.easy_win():
            if self.skip_battle(quiet=True):
                self.end_battle(None)
                return
            intro = None              # someone joined and the fight got serious
        self.shown_hp = [self.foe.hp, p.hp]
        self.battle_transition()
        if intro:
            self.say(intro)
        self.flush_battle_msgs()
        if caught:
            self.say(f'{self.name} was caught asleep!')
            self.foes_attack(False)
            self.flush_battle_msgs()
        skippable = self.easy_win()   # only fights that start out easy can be skipped
        outcome = None
        while self.foes and not self.game_over:
            m = self.foe
            guarding = False
            held = self.player_held()
            choice = None if held else self.battle_menu(skippable)
            if held:                                          # lost the turn to a status
                if self.game_over:
                    break
            elif choice == 0:                                 # FIGHT
                mv = self.fight_menu()
                if mv is None:
                    continue
                if MOVES[mv]['mp'] > p.mp:
                    self.say(f'Not enough MP! {mv} costs {MOVES[mv]["mp"]} MP.', log=False)
                    continue
                self.use_move(m, mv)
            elif choice == 1:                                 # BAG
                it = self.choose('use', lambda i: i.kind in ('potion', 'scroll', 'food'))
                if not it:
                    self.flush_battle_msgs()
                    continue
                {'potion': self.drink, 'scroll': self.read_scroll, 'food': self.eat_food}[it.kind](it)
                self.animate_hp()
                self.flush_battle_msgs()
                if all(max(abs(f.x - p.x), abs(f.y - p.y)) > 1 for f in self.foes):
                    self.say(f'{self.name} vanished from the battle!')
                    outcome = self.escape()
                    break
            elif choice == 2:                                 # GUARD
                guarding = True
                self.say(f'{self.name} braced for the attack!')
            elif choice == 3:                                 # RUN
                boss = next((f for f in self.foes if 'boss' in f.flags), None)
                if boss:
                    self.say(f'There is no running from the {boss.name.upper()}!')
                    continue
                lvl = max(f.level for f in self.foes)
                chance = min(0.9, max(0.1, 0.5 + 0.07 * (p.level - lvl) - 0.1 * (len(self.foes) - 1)))
                if random.random() < chance:
                    self.say('Got away safely!')
                    outcome = self.escape()
                    break
                self.say("Can't escape!")
            elif choice == 4:                                 # SKIP (easy win)
                if self.skip_battle():
                    break
                skippable = False
                continue
            elif choice == 5:                                 # event log
                self.show_log()
                continue
            else:
                continue

            if self.clear_fainted():          # the target, or every foe a spell hit
                break
            self.foes_attack(guarding)
            if self.game_over or self.clear_fainted():
                break
            self.battle_world_turn()
            self.animate_hp()
            self.flush_battle_msgs()
        if self.game_over and self.game_over[0] == 'died':
            self.say(f'{self.name} fainted...')
        elif not self.foes and not self.game_over:
            outcome = 'You won the battle!'
        self.end_battle(outcome)

    def end_battle(self, outcome):
        self.foes = []
        self.compute_fov()
        if outcome:
            self.msg(outcome)

    def escape(self):
        for f in self.foes:
            f.stun = 4
            f.status = {}
        return 'You escaped from the battle.'

    def player_held(self):
        """Statuses that can cost the player their turn. True if the turn is lost."""
        p = self.player
        if p.frozen:
            p.frozen -= 1
            self.say(f'{self.name} is frozen solid!')
        elif p.paralyzed and random.random() < 0.3:
            self.say(f"{self.name} is paralyzed! {self.name} can't move!")
        elif p.confused and random.random() < 1 / 3:
            self.say(f'{self.name} is confused! {self.name} stumbled and got hurt!')
            self.hurt(random.randint(1, 4) + p.level // 2, 'confusion')
            self.animate_hp()
        else:
            return False
        return True

    def clear_fainted(self):
        """Reward and remove foes that have fainted. True if none are left."""
        target = self.foe
        for f in [f for f in self.foes if f.hp <= 0]:
            self.win_battle(f)
        if self.foes and self.foe is not target:
            self.shown_hp[0] = self.foe.hp
            self.say(f'{self.name} turned to face the {self.called(self.foe)}!')
        return not self.foes

    def foes_attack(self, guarding, quiet=False):
        for f in list(self.foes):
            if f.hp > 0:
                self.foe_turn(f, guarding, quiet)
            if self.game_over:
                return

    def inflict(self, m, status, say):
        """Put a status on a monster unless it's immune. Returns True if it took hold."""
        immune = (status in m.status
                  or (status == 'burn' and ('burn' in m.flags or m.type == 'elemental'))
                  or (status == 'poison' and m.type in ('undead', 'elemental'))
                  or (status == 'freeze' and ('frost' in m.flags or 'boss' in m.flags))
                  or (status == 'sleep' and ('boss' in m.flags or m.type == 'undead'))
                  or (status == 'confuse' and ('boss' in m.flags or m.type == 'elemental')))
        if immune:
            return False
        _tag, turns, text = STATUSES[status]
        m.status[status] = random.randint(*turns)
        say(f'The {self.called(m)} {text}')
        return True

    def foe_held(self, m, say, quiet=False):
        """Sleep, freezing, paralysis and confusion can cost a monster its turn. True if
        it does."""
        who = f'The {self.called(m)}'
        for status, held, ends in (('sleep', 'is fast asleep.', 'woke up!'),
                                   ('freeze', 'is frozen solid!', 'thawed out!')):
            if status in m.status:
                if m.status[status] <= 0:
                    del m.status[status]
                    say(f'{who} {ends}')
                else:
                    m.status[status] -= 1
                    say(f'{who} {held}')
                    return True
        if 'paralyze' in m.status:
            m.status['paralyze'] -= 1
            if m.status['paralyze'] <= 0:
                del m.status['paralyze']
                say(f'{who} is no longer paralyzed.')
            elif random.random() < 0.3:
                say(f"{who} is paralyzed! It can't move!")
                return True
        if 'confuse' in m.status:
            m.status['confuse'] -= 1
            if m.status['confuse'] <= 0:
                del m.status['confuse']
                say(f'{who} snapped out of its confusion!')
            elif random.random() < 1 / 3:
                m.hp = max(0, m.hp - max(1, random.randint(*m.dmg) // 2))
                if not quiet:
                    self.animate_hp()
                say(f'{who} is confused! It hurt itself in its confusion!')
                return True
        return False

    def status_damage(self, m, say, quiet):
        """Burns and poison hurt a monster at the end of its turn."""
        for status, what in (('burn', 'its burn'), ('poison', 'poison')):
            if status not in m.status or m.hp <= 0:
                continue
            dmg = max(2, min(m.max_hp // (12 if status == 'burn' else 10), 3 + self.depth // 2))
            m.hp = max(0, m.hp - dmg)
            if not quiet:
                self.animate_hp()
            say(f'The {self.called(m)} was hurt by {what}!')
            m.status[status] -= 1
            if m.status[status] <= 0:
                del m.status[status]

    def boss_phase(self, m, say):
        """At half HP a boss changes tactics: it calls in minions or flies into a rage."""
        m.phased = True
        say(BOSSES[m.name]['phase_msg'])
        tactic, *minion = BOSSES[m.name]['phase']
        if tactic == 'enrage':
            m.flags.append('enraged')
            return
        p = self.player
        tpl = next(t for t in MONSTERS if t[1] == minion[0])
        spots = [(p.x + dx, p.y + dy) for dx, dy in DIRS.values()
                 if self.walkable(p.x + dx, p.y + dy) and not self.occupied(p.x + dx, p.y + dy)]
        for x, y in random.sample(spots, min(2, len(spots))):
            s = Monster(tpl, x, y, self.depth)
            s.awake = True
            self.monsters.append(s)
            self.foes.append(s)
            say(f'A {self.called(s)} joined the battle!')

    def battle_world_turn(self):
        """A battle round is a dungeon turn too: hunger ticks and other monsters close in."""
        self.tick_player()
        self.turn += 1
        self.monsters_act()

    @staticmethod
    def effectiveness(kind, m):
        eff = EFFECTIVENESS.get((kind, m.type), 1.0)
        if (kind == 'fire' and 'burn' in m.flags) or (kind == 'ice' and 'frost' in m.flags):
            eff = min(eff, 0.5)                # fire creatures shrug off fire, frost ones ice
        return eff

    def use_move(self, m, name, quiet=False):
        p = self.player
        info = MOVES[name]
        say = self.msg if quiet else self.say
        p.mp -= info['mp']
        if not quiet:
            self.say(f'{self.name} used {name}!')
        if 'heal' in info:
            p.hp = min(p.max_hp, p.hp + sum(random.randint(1, 8) for _ in range(info['heal']))
                       + 2 * p.level)
            p.cure()
            if not quiet:
                self.animate_hp()
            say(f'{self.name} was healed, and every ailment faded away!')
            return
        if 'barrier' in info:
            p.barrier = info['barrier']
            say(f'A shimmering barrier surrounds {self.name}!')
            return
        if 'mana' in info:
            gained = min(p.max_mp - p.mp, info['mana'] + p.level // 2)
            p.mp += gained
            say(f'{self.name} focused and recovered {gained} MP!' if gained else
                f'{self.name} focused, but is already brimming with mana.')
            return
        targets = list(self.foes) if info.get('all') else [m]
        for t in targets:
            self.hit_foe(t, info, say, quiet, many=len(targets) > 1)

    def hit_foe(self, m, info, say, quiet, many):
        """One target of an attacking move: roll to hit, deal damage and apply effects.
        many: the move hits several foes, so each one is named in the battle text."""
        p = self.player
        if random.randint(1, 100) > info['acc'] + p.level * 2 - m.ac * 3:
            if not quiet:
                self.say(f'The {self.called(m)} avoided the attack!')
            return
        effect = info.get('effect')
        if 'mult' not in info and 'dice' not in info:          # pure status move
            if not self.inflict(m, effect[0], say):
                say('But it failed!')
            return
        if 'mult' in info:
            dmg = (random.randint(*p.weapon_dmg) + p.str_bonus) * info['mult']
        else:
            dmg = (sum(random.randint(1, 6) for _ in range(info['dice'])) + 2 * p.level
                   + p.spell_power)
        eff = self.effectiveness(info['type'], m)
        crit = random.random() < 1 / 16
        dmg = max(1, int(dmg * eff * (1.5 if crit else 1)))
        m.hp = max(0, m.hp - dmg)
        if 'drain' in info:
            p.hp = min(p.max_hp, p.hp + max(1, int(dmg * info['drain'])))
        if not quiet:
            if m is self.foe:
                self.flash('enemy')
                self.animate_hp()
            notes = ['A critical hit!'] if crit else []
            if eff > 1:
                notes.append("It's super effective!")
            elif eff < 1:
                notes.append("It's not very effective...")
            if many:
                self.say(' '.join([f'The {self.called(m)} was hit!'] + notes))
            else:
                for note in notes:
                    self.say(note)
            if 'drain' in info:
                self.say(f'{self.name} drained the life from the {self.called(m)}!')
        if m.hp <= 0:
            return
        if 'sleep' in m.status and random.random() < 1 / 3:
            del m.status['sleep']
            say(f'The {self.called(m)} woke up!')
        if info['type'] == 'fire' and 'freeze' in m.status:
            del m.status['freeze']
            say(f'The fire thawed out the {self.called(m)}!')
        if effect and random.randint(1, 100) <= effect[1]:
            self.inflict(m, effect[0], say)

    def foe_turn(self, m, guarding, quiet=False):
        say = self.msg if quiet else self.say     # quiet: only status effects get reported later
        if 'boss' in m.flags and not m.phased and m.hp <= m.max_hp // 2:
            self.boss_phase(m, say)
        if not self.foe_held(m, say, quiet):
            for _ in range(2 if 'enraged' in m.flags else 1):
                self.foe_attack(m, guarding, quiet)
                if self.game_over:
                    return
        self.status_damage(m, say, quiet)

    def foe_attack(self, m, guarding, quiet=False):
        p = self.player
        say = self.msg if quiet else self.say
        special = random.random() < 0.3
        if not quiet:
            self.say(f'The {self.called(m)} used {m.moves[1] if special else m.moves[0]}!')
        if random.randint(1, 20) + m.power < 10 + p.ac:
            if not quiet:
                self.say('But it missed!' if random.random() < 0.5 else 'It glanced off your armor!')
            return
        dmg = random.randint(*m.dmg)
        if special:
            dmg = int(dmg * 1.5)
        if guarding:
            dmg = max(1, dmg // 2)
        if p.barrier:
            dmg = max(1, dmg // 2)
        p.hp = max(0, p.hp - dmg)
        if not quiet:
            self.flash('player')
            self.animate_hp()
        if guarding:
            self.say('Your guard softened the blow!')
        if special and 'poison' in m.flags and p.str > 3:
            p.str -= 1
            say('You were poisoned! You feel weaker.')
        if special and 'drain' in m.flags and p.max_hp > 5:
            p.max_hp -= random.randint(1, 3)
            p.hp = min(p.hp, p.max_hp)
            say('You feel your life force draining away!')
        if special and 'burn' in m.flags and not p.burn:
            p.burn = random.randint(3, 5)
            say('You were burned!')
        if special and 'frost' in m.flags:
            if random.random() < 0.3 and not p.frozen:
                p.frozen = 1
                say('You were frozen solid!')
            else:
                p.hp = max(0, p.hp - random.randint(2, 5))
                say('You were chilled to the bone!')
        if special and 'paralyze' in m.flags and not p.paralyzed:
            p.paralyzed = random.randint(4, 6)
            say('You are paralyzed! You may be unable to move!')
        if special and 'confuse' in m.flags and not p.confused:
            p.confused = random.randint(3, 6)
            say('You became confused!')
        if p.hp <= 0:
            self.die(an(m.name))

    def easy_win(self):
        """True if STRIKE alone beats every foe even with bad rolls and each one hitting
        hard every round until it falls."""
        p = self.player
        lo = p.weapon_dmg[0]
        elapsed = worst = 0
        for m in self.foes:
            if 'boss' in m.flags:
                return False
            eff = EFFECTIVENESS.get(('normal', m.type), 1.0)
            min_dmg = max(1, int((lo + p.str_bonus) * eff))
            hit = min(100, MOVES['STRIKE']['acc'] + p.level * 2 - m.ac * 3) / 100
            if hit <= 0.5:
                return False
            worst_hit = (int(m.dmg[1] * 1.5) + (3 if 'drain' in m.flags else 0)
                         + (5 if 'burn' in m.flags or 'frost' in m.flags else 0))
            if min_dmg >= m.hp:        # one STRIKE ends it (we still allow for one miss)
                elapsed += 1
            else:                      # pessimistic, with misses
                elapsed += math.ceil(math.ceil(m.hp / min_dmg) / hit) + 1
            worst += worst_hit * elapsed
        return worst < p.hp

    def skip_battle(self, quiet=False):
        """Resolve the fight instantly with STRIKEs, no animations. Returns False if it
        had to stop because a monster joined and the win was no longer obvious.
        quiet: report on the map instead of the battle screen (auto-skip)."""
        p = self.player
        hp_before, rounds, beaten = p.hp, 0, []
        finished = True
        while self.foes and not self.game_over:
            rounds += 1
            m = self.foe
            self.use_move(m, 'STRIKE', quiet=True)
            if m.hp <= 0:
                self.drop_foe(m)
                beaten.append(m)
                if not self.foes:
                    break
            self.foes_attack(False, quiet=True)
            if self.game_over:
                break
            for f in [f for f in self.foes if f.hp <= 0]:     # burns and poison
                self.drop_foe(f)
                beaten.append(f)
            if not self.foes:
                break
            n = len(self.foes)
            self.battle_world_turn()
            if len(self.foes) > n and not self.easy_win():
                finished = False
                break
        self.shown_hp = [self.foe.hp if self.foe else 0, p.hp]
        lost = hp_before - p.hp
        how = f'losing {lost} HP' if lost > 0 else 'unscathed'
        n_rounds = f'{rounds} round{"s" if rounds != 1 else ""}'
        names = ' and '.join(m.name for m in beaten)
        if quiet:
            self.msg(f'You beat the {names} in {n_rounds}, {how}.' if finished else
                     f'You fought for {n_rounds}, {how}, but now the battle is getting serious!')
        elif finished:
            self.say(f'{self.name} made short work of the wild {names.upper()} in {n_rounds}'
                     + (f', losing {lost} HP.' if lost > 0 else ' without a scratch!'))
        else:
            self.say(f'{self.name} fought for {n_rounds}, {how}... '
                     'but now the battle is getting serious!')
        for m in beaten:
            self.reward(m, quiet)
        if not quiet:
            self.flush_battle_msgs()
        return finished

    def drop_foe(self, m):
        self.monsters.remove(m)
        self.foes.remove(m)
        self.fallen = m              # keeps the battle screen drawable after the last foe

    def win_battle(self, m, quiet=False):
        self.reward(m, quiet)
        self.drop_foe(m)

    def reward(self, m, quiet=False):
        p = self.player
        gold = random.randint(0, m.xp // 4)
        p.gold += gold
        if quiet:
            self.msg(f'+{m.xp} exp' + (f', +{gold} gold.' if gold else '.'))
            self.gain_xp(m.xp)
        else:
            self.say(f'The {self.called(m)} fainted!')
            self.say(f'{self.name} gained {m.xp} EXP. Points!')
            self.gain_xp(m.xp)
            self.flush_battle_msgs()
            if gold:
                self.say(f'{self.name} picked up {gold} gold from the battle.')
        if 'boss' in m.flags:
            (self.msg if quiet else self.say)(BOSSES[m.name]['defeat'])
            if self.depth < FINAL_DEPTH:
                self.tiles[m.y][m.x] = STAIRS
                it = self.spell_scroll()
                it.x, it.y = m.x, m.y
                self.items.append(it)
                (self.msg if quiet else self.say)(
                    f'The {m.name.upper()} left behind {self.item_name(it)}!')
            else:
                it = Item('amulet')
                it.x, it.y = m.x, m.y
                self.items.append(it)
        elif random.random() < 0.25 and not self.item_at(m.x, m.y):
            it = self.random_item()
            it.x, it.y = m.x, m.y
            self.items.append(it)
            (self.msg if quiet else self.say)(f'The {m.name} dropped something!')

    def battle_menu(self, skippable):
        opts = ['FIGHT', 'BAG', 'GUARD', 'RUN']
        easy = skippable and self.easy_win()

        def extra(cur):
            if easy:
                self.put(22, 3, '[S] SKIP - easy win', COLORS['green'] | curses.A_BOLD)
            self.put(22, 30, '[M] LOG', COLORS['cyan'])
            self.box(16, 46, 8, 34)
            self.put(16, 46, '┬')
            self.put(23, 46, '┴')
            for i, o in enumerate(opts):
                r, c = divmod(i, 2)
                self.put(18 + r * 2, 50 + c * 14, ('▶' if i == cur else ' ') + o,
                         curses.A_BOLD if i == cur else 0)
        keys = {'m': 5, 'M': 5}
        if easy:
            keys.update({'s': 4, 'S': 4})
        return self.select(lambda cur: self.draw_battle(['What will', f'{self.name} do?'],
                                                        extra=lambda: extra(cur)), 4, cols=2,
                           keys=keys)

    def fight_menu(self):
        p = self.player
        moves = p.moves

        def extra(cur):
            self.box(16, 0, 8, 56)
            for i, name in enumerate(moves):
                r, c = divmod(i, 2)
                y, x = 17 + r * 2, 3 + c * 26
                self.put(y, x, ('▶' if i == cur else ' ') + name, curses.A_BOLD if i == cur else 0)
                cost = MOVES[name]['mp']
                if cost:
                    self.put(y, x + 18, f'{cost:>2}MP', COLORS['red'] if cost > p.mp else 0)
            self.box(16, 56, 8, 24)
            info = MOVES[moves[cur]]
            short = info['mp'] > p.mp
            self.put(17, 59, f'COST  {info["mp"]} MP' if info['mp'] else 'COST  free',
                     COLORS['red'] | curses.A_BOLD if short else 0)
            self.put(18, 59, f'HAVE  {p.mp}/{p.max_mp} MP')
            self.put(19, 59, f'TYPE/{info["type"].upper()}')
            for i, note in enumerate(move_notes(info)[:2]):
                self.put(21 + i, 59, note[:20], COLORS['cyan'])
        i = self.select(lambda cur: self.draw_battle(extra=lambda: extra(cur)), len(moves), cols=2)
        return None if i is None else moves[i]

    def battle_transition(self):
        for y in range(24):
            self.put(y, 0, '▓' * (79 if y == 23 else 80), COLORS['white'])
            if y % 2:
                self.scr.refresh()
                curses.napms(12)
        self.draw_battle()
        curses.napms(150)

    def flash(self, who):
        for _ in range(2):
            self.draw_battle(hide=who)
            curses.napms(70)
            self.draw_battle()
            curses.napms(70)

    def animate_hp(self):
        if not self.foe:
            return
        targets = [self.foe.hp, self.player.hp]
        for _ in range(40):
            if self.shown_hp == targets:
                break
            for i in (0, 1):
                diff = targets[i] - self.shown_hp[i]
                if diff:
                    step = max(1, abs(diff) // 6)
                    self.shown_hp[i] += step if diff > 0 else -step
            self.draw_battle()
            curses.napms(25)
        self.shown_hp = targets

    def say(self, text, log=True):
        """Show a line in the battle text box and wait for a key."""
        if log:
            self.record(text)
        lines = textwrap.wrap(text, 72) or ['']
        for i in range(0, len(lines), 2):
            self.draw_battle(lines[i:i + 2], more=True)
            self.wait_key()

    def flush_battle_msgs(self):
        msgs, self.msgs = self.msgs, []
        for t in msgs:
            self.say(t, log=False)

    def draw_battle(self, text=None, more=False, hide=None, extra=None):
        m, p = self.foe or self.fallen, self.player
        self.scr.erase()
        # enemy panel
        self.box(1, 2, 4, 36)
        self.put(2, 4, m.name.upper(), curses.A_BOLD)
        if 'boss' in m.flags:
            self.put(2, 22, 'BOSS', COLORS['red'] | curses.A_BOLD | curses.A_REVERSE)
        self.put(2, 30, f'Lv{m.level}')
        self.hp_bar(3, 4, self.shown_hp[0], m.max_hp, 26)
        if m.status and m.hp > 0:
            tags = ' '.join(STATUSES[s][0] for s in m.status)
            self.put(4, 5, f' {tags} ', COLORS['magenta'] | curses.A_BOLD)
        for i, f in enumerate(self.foes[1:4]):
            self.put(5 + i, 4, f'+ {f.name.upper()} Lv{f.level}  HP {f.hp}/{f.max_hp}',
                     COLORS[f.color] | curses.A_BOLD)
        if len(self.foes) > 4:
            self.put(8, 4, f'+ {len(self.foes) - 4} more...')
        art = SPRITES[m.name]
        if hide != 'enemy':
            for i, line in enumerate(art):
                self.put(8 - len(art) + i, 48, line, COLORS[m.color] | curses.A_BOLD)
        self.put(8, 46, '`~~~~~~~~~~~~~~~~~~~~~~~~~~\'', COLORS['green'])
        # player panel
        if hide != 'player':
            for i, line in enumerate(SPRITES['player']):
                self.put(9 + i, 6, line, COLORS['yellow'] | curses.A_BOLD)
        self.put(15, 2, '`~~~~~~~~~~~~~~~~~~~~~~~\'', COLORS['green'])
        self.box(9, 42, 7, 36)
        self.put(10, 44, self.name.upper()[:18], curses.A_BOLD)
        self.put(10, 64, f'Lv{p.level}')
        flags = [tag for tag, on in (('FRZ', p.frozen), ('PAR', p.paralyzed), ('BRN', p.burn),
                                     ('CNF', p.confused), ('BAR', p.barrier),
                                     ('PSN', p.str < p.max_str)) if on]
        if flags:
            self.put(12, 44, ' '.join(flags[:3]), COLORS['magenta'] | curses.A_BOLD)
        self.hp_bar(11, 44, self.shown_hp[1], p.max_hp, 26)
        self.put(12, 58, f'{max(0, self.shown_hp[1]):>3}/{p.max_hp:>3}', curses.A_BOLD)
        prev = xp_needed(p.level - 1) if p.level > 1 else 0
        frac = (p.xp - prev) / (xp_needed(p.level) - prev)
        filled = int(min(1, max(0, frac)) * 26)
        self.put(14, 44, 'EXP')
        self.put(14, 48, '█' * filled, COLORS['cyan'])
        self.put(14, 48 + filled, '░' * (26 - filled))
        filled = int(round(p.mp / p.max_mp * 20))
        self.put(13, 44, 'MP', curses.A_BOLD)
        self.put(13, 47, '█' * filled, COLORS['blue'] | curses.A_BOLD)
        self.put(13, 47 + filled, '░' * (20 - filled))
        self.put(13, 68, f'{p.mp:>2}/{p.max_mp:>2}')
        # text box
        self.box(16, 0, 8, 80)
        for i, line in enumerate(text or []):
            self.put(18 + i * 2, 3, line)
        if more:
            self.put(21, 76, '▼', curses.A_BOLD | curses.A_BLINK)
        if extra:
            extra()
        self.draw_log_panel()
        self.scr.refresh()

    def hp_bar(self, y, x, hp, max_hp, width):
        frac = max(0, hp) / max_hp
        filled = int(round(frac * width))
        if hp > 0:
            filled = max(1, filled)
        color = 'green' if frac > 0.5 else 'yellow' if frac > 0.2 else 'red'
        self.put(y, x, 'HP', curses.A_BOLD)
        self.put(y, x + 3, '█' * filled, COLORS[color] | curses.A_BOLD)
        self.put(y, x + 3 + filled, '░' * (width - filled))

    def box(self, y, x, h, w):
        self.put(y, x, '┌' + '─' * (w - 2) + '┐')
        for i in range(1, h - 1):
            self.put(y + i, x, '│' + ' ' * (w - 2) + '│')
        self.put(y + h - 1, x, '└' + '─' * (w - 2) + '┘')

    def select(self, draw, n, cols=1, keys=None):
        """Cursor menu: arrows/hjkl move, Enter/space/z pick, Esc/x cancel.
        `keys` maps extra hotkeys to the value select() should return."""
        cur = 0
        rows = (n + cols - 1) // cols
        while True:
            draw(cur)
            k = self.scr.getch()
            ch = ARROWS.get(k) or (chr(k) if 0 < k < 256 else '')
            if ch in ('h', 'l', 'k', 'j'):
                dx, dy = DIRS[ch]
                r, c = divmod(cur, cols)
                nxt = ((r + dy) % rows) * cols + (c + dx) % cols
                if nxt < n:
                    cur = nxt
            elif ch in CONFIRM_KEYS or k == curses.KEY_ENTER:
                return cur
            elif ch in CANCEL_KEYS:
                return None
            elif keys and ch in keys:
                return keys[ch]
            elif ch.isdigit() and 1 <= int(ch) <= n:
                return int(ch) - 1

    # ------------------------------------------------------------- talking
    def talk(self, npc):
        getattr(self, 'talk_' + npc.kind)(npc)
        npc.talked += 1
        self.compute_fov()

    def npc_say(self, npc, text):
        lines = textwrap.wrap(text, 72) or ['']
        for i in range(0, len(lines), 2):
            self.draw_dialog(npc, lines[i:i + 2], more=True)
            self.wait_key()

    def npc_ask(self, npc, text, options):
        """Ask a question with a cursor menu. Esc picks the last option."""
        lines = textwrap.wrap(text, 72)[:2]
        i = self.select(lambda cur: self.draw_dialog(npc, lines, options=options, cur=cur),
                        len(options))
        return len(options) - 1 if i is None else i

    def draw_dialog(self, npc, text, more=False, options=None, cur=0):
        self.draw([], refresh=False)
        self.box(9, 1, 7, 18)
        for i, line in enumerate(npc.portrait):
            self.put(10 + i, 3, line, COLORS[npc.color] | curses.A_BOLD)
        self.box(16, 0, 8, 80)
        self.put(16, 3, f' {npc.name} ', COLORS[npc.color] | curses.A_BOLD | curses.A_REVERSE)
        for i, line in enumerate(text):
            self.put(18 + i * 2, 3, line)
        if more:
            self.put(21, 76, '▼', curses.A_BOLD | curses.A_BLINK)
        if options:
            w = max(len(o) for o in options) + 5
            top = 16 - len(options) - 2
            self.box(top, 79 - w, len(options) + 2, w)
            for i, o in enumerate(options):
                self.put(top + 1 + i, 81 - w, ('▶' if i == cur else ' ') + o,
                         curses.A_BOLD if i == cur else 0)
        self.scr.refresh()

    def give_item(self, npc, it):
        if it.sub:
            self.known.add(it.sub)
        name = self.item_name(it)
        if self.add_to_pack(it):
            self.npc_say(npc, f'{self.name} received {name}!')
        else:
            p = self.player
            it.x, it.y, it.seen = p.x, p.y, True
            self.items.append(it)
            self.npc_say(npc, f'Your pack is full, so {name} was put on the floor.')

    def talk_sage(self, npc):
        say = lambda t: self.npc_say(npc, t)
        if not npc.talked:
            say(f'Ah, a new face! Welcome, {self.name}. Few adventurers come down here anymore.')
            say('Monsters lurk in these halls. Walk into one, or let one catch you, '
                'and you will be drawn into BATTLE!')
            say(f'Somewhere far below, on depth {FINAL_DEPTH}, the Frost Wyrm guards the '
                'Amulet of Yendor. Bring it back and you will be a legend.')
            say('And mind your step! Hidden traps lurk in these halls. Search (s) and you '
                'may spot them before they spot you.')
            say('Here, take these. You will need them more than I do.')
            self.give_item(npc, Item('potion', 'healing'))
            self.give_item(npc, Item('scroll', 'FIRE BOLT'))
            say('Read that spell scroll (r) and you will learn FIRE BOLT. Spell scrolls are '
                'rare, so treasure any you find!')
        while True:
            c = self.npc_ask(npc, 'Is there anything else you wish to know?',
                             ['Battles', 'Moves & types', 'The road ahead', 'Friendly folk',
                              'Goodbye'])
            if c == 0:
                say('In battle you may FIGHT, open your BAG, GUARD to halve the next blow, '
                    'or try to RUN. Running works best against weaker foes.')
                say('A monster you escape from is dazed for a few turns. Use them well!')
                say('Battles are noisy, and every round is a turn in the dungeon. Fight too '
                    'long and other monsters will join in!')
            elif c == 1:
                say('You know STRIKE and POWER SMASH. New spells come only from rare spell '
                    f'scrolls, and you can hold {MAX_SPELLS} spells at most. Learn another and '
                    'you must forget one.')
                say('Swords and maces make your STRIKEs hit harder. Wands and staffs barely '
                    'scratch a foe, but they make every spell you cast hit harder.')
                say('FIRE scorches beasts and giants, but dragons shrug it off. HOLY light '
                    'sears the undead. Weak spots hurt, but they will not win a fight alone.')
                say('Every spell costs mana (MP). It slowly returns as you walk and rest, '
                    'and comes back in full when you grow a level.')
                say('Many spells leave a mark: burns and poison hurt every turn, while sleep, '
                    'frost and paralysis can make a foe lose its turn.')
                say('Monsters can do the same to you! A potion of healing or a healer will '
                    'cure what ails you.')
            elif c == 2:
                say(f'The way down is {FINAL_DEPTH} levels deep, through four lands: the Dungeons '
                    'of Doom, the Sunken Catacombs, the Ember Caverns and the Frozen Abyss.')
                say('At depth 10 the BONE KING seals the way down. At the very bottom the FROST '
                    'WYRM coils around the Amulet. Neither will let you run away!')
                say('Bosses grow desperate when wounded. Save your mana and potions for them.')
            elif c == 3:
                say('Look for the & sign on deeper floors. Merchants trade for gold, healers '
                    'mend wounds, and bards know many secrets.')
            else:
                say('Good luck down there!')
                return

    def talk_merchant(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        say('Welcome, welcome! Pip has the finest wares in all the dungeon!' if not npc.talked
            else 'Back again, friend? Wonderful!')
        while True:
            c = self.npc_ask(npc, f'What will it be? (You have {p.gold} gold.)',
                             ['Buy', 'Sell', 'Goodbye'])
            if c == 0:
                if not npc.stock:
                    say("I'm all sold out! Come back... well, never, I suppose.")
                    continue
                opts = [f'{self.item_name(it, reveal=True)[:38]:<38} {self.price(it):>4}g'
                        for it in npc.stock] + ['Back']
                i = self.npc_ask(npc, f'Take a look! (You have {p.gold} gold.)', opts)
                if i == len(npc.stock):
                    continue
                it = npc.stock[i]
                cost = self.price(it)
                if p.gold < cost:
                    say("Ah, you can't afford that, I'm afraid.")
                elif len(p.pack) >= MAX_PACK:
                    say('Your pack is full! Sell me something first.')
                else:
                    p.gold -= cost
                    npc.stock.remove(it)
                    self.give_item(npc, it)
                    say('Pleasure doing business!')
            elif c == 1:
                it = self.choose('sell', lambda i: i is not p.weapon and i is not p.armor)
                self.msgs = []
                if not it:
                    continue
                offer = max(1, self.price(it) // 3)
                n = it.count
                if n > 1:
                    i = self.npc_ask(npc, f'I pay {offer} gold apiece for {self.item_name(it)}. '
                                     'How many will you sell?',
                                     [f'One ({offer}g)', f'All {n} ({offer * n}g)', 'Never mind'])
                    qty = {0: 1, 1: n}.get(i)
                elif self.npc_ask(npc, f'I can give you {offer} gold for {self.item_name(it)}. Deal?',
                                  ['Yes', 'No']) == 0:
                    qty = 1
                else:
                    qty = None
                if qty:
                    p.gold += offer * qty
                    for _ in range(qty):
                        self.use_up(it)
                    say('Done and done!')
            else:
                say('Come back anytime!')
                return

    def talk_healer(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        cost = 0 if not npc.done else 10 + self.depth * 5
        if not npc.talked:
            say('Peace be with you, traveler. You look weary from the road.')
        price = 'free, this once' if cost == 0 else f'{cost} gold'
        if self.npc_ask(npc, f'Shall I tend to your wounds? ({price})',
                        ['Yes, please', 'No, thank you']) != 0:
            say('Then go with care.')
            return
        if p.gold < cost:
            say(f'I am sorry, child. The temple asks {cost} gold for its blessings.')
            return
        p.gold -= cost
        npc.done = True
        p.hp, p.str = p.max_hp, p.max_str
        p.cure()
        p.restore_mp()
        say('A warm light surrounds you... HP and MP fully restored!')

    def talk_bard(self, npc):
        p = self.player
        say = lambda t: self.npc_say(npc, t)
        if not npc.talked:
            say('Ho there! Finch the Bard, at your service. I collect songs and secrets.')
        cost = 40 + self.depth * 5
        while True:
            c = self.npc_ask(npc, 'What would you like to hear?',
                             ['A song', 'Some advice', f'A secret ({cost}g)', 'Goodbye'])
            if c == 0:
                for line in random.choice(SONGS):
                    say(line)
            elif c == 1:
                say(random.choice(LORE))
            elif c == 2:
                unknown = [k for k in POTIONS + SCROLLS if k not in self.known]
                if npc.done:
                    say("I've told you my best secret already. A bard must keep some mystery!")
                elif not unknown:
                    say('You already know every secret I have!')
                elif p.gold < cost:
                    say(f'Secrets cost coin, friend. Come back with {cost} gold.')
                else:
                    p.gold -= cost
                    npc.done = True
                    kind = random.choice(unknown)
                    self.known.add(kind)
                    if kind in POTIONS:
                        say(f'Psst... the {self.potion_look[kind]} potions? '
                            f'Those are potions of {kind}.')
                    else:
                        say(f'Psst... scrolls titled "{self.scroll_look[kind]}"? '
                            f'Those are scrolls of {kind}.')
            else:
                say('Farewell! May your tale be worth a song.')
                return

    def talk_hermit(self, npc):
        say = lambda t: self.npc_say(npc, t)
        if npc.done:
            say('Bless you for the food, friend. My belly still sings your praises.')
            return
        say('Food... have you any food? I have not eaten in days...')
        food = next((i for i in self.player.pack if i.kind == 'food'), None)
        if not food:
            say('No? Ah, well. Come back if you find some...')
            return
        if self.npc_ask(npc, 'Will you share a food ration?', ['Give food', 'Sorry, no']) != 0:
            say('*sigh* I understand. Times are hard.')
            return
        self.use_up(food)
        npc.done = True
        say('Oh, thank you, thank you! Here, I found this long ago. It is no use to an old man.')
        self.give_item(npc, Item('scroll', random.choice(['enchant weapon', 'enchant armor'])))

    # -------------------------------------------------------------- player
    def player_move(self, dx, dy):
        p = self.player
        if p.frozen:
            self.msg('You are frozen solid and cannot move!')
            return True
        if p.paralyzed and random.random() < 0.3:
            self.msg('Your muscles lock up! You cannot move.')
            return True
        if p.confused and random.random() < 0.5:
            dx, dy = random.choice(list(DIRS.values()))
        nx, ny = p.x + dx, p.y + dy
        m = self.monster_at(nx, ny)
        if m:
            self.battle(m)
            return True
        npc = self.npc_at(nx, ny)
        if npc:
            self.talk(npc)
            return False
        if p.stuck:
            p.stuck -= 1
            self.msg('You are still climbing out of the pit.' if p.stuck else
                     'You climb out of the pit.')
            return True
        if not self.walkable(nx, ny):
            if self.tiles[ny][nx] == POOL:
                name, _color, warning, stumble = self.env['pool']
                if not p.confused:
                    self.msg(warning)
                    return False
                self.msg(stumble)
                self.hurt(sum(random.randint(1, 6) for _ in range(2)), name)
                if name == 'lava':
                    p.burn = max(p.burn, random.randint(3, 5))
                else:
                    p.frozen = max(p.frozen, random.randint(1, 3))
            return bool(p.confused)     # stumbling into a wall still costs a turn
        trap = self.traps.get((nx, ny))
        if trap and trap.found and not p.confused:
            if not self.confirm(f'Really step onto the {trap.name}? (y/n)'):
                return False
        p.x, p.y = nx, ny
        if trap:
            depth = self.depth
            self.spring_trap(trap)
            if self.game_over or (p.x, p.y) != (nx, ny):
                return self.depth == depth       # a fall to a new level costs no turn
        else:
            self.find_traps(1, min(0.35, 0.1 + 0.02 * p.level))
        if self.item_at(nx, ny):
            self.pickup(auto=True)
        elif self.tiles[ny][nx] == STAIRS:
            self.msg('There is a staircase down here.')
        return True

    # ---------------------------------------------------------------- traps
    def find_traps(self, radius, chance):
        p = self.player
        found = 0
        for (x, y), t in self.traps.items():
            if not t.found and max(abs(x - p.x), abs(y - p.y)) <= radius and random.random() < chance:
                t.found = True
                found += 1
                self.msg(f'You found {an(t.name)}!')
        return found

    def search(self):
        if not self.find_traps(2, min(0.9, 0.5 + 0.04 * self.player.level)):
            self.msg('You search the area but find nothing.')
        return True

    def hurt(self, dmg, cause):
        p = self.player
        p.hp = max(0, p.hp - dmg)
        if p.hp <= 0:
            self.die(cause)

    def spring_trap(self, trap):
        p = self.player
        careful = trap.found
        trap.found = True
        if random.random() < (0.6 if careful else min(0.3, 0.05 + 0.02 * p.level)):
            self.msg(f'You carefully step over the {trap.name}.' if careful else
                     f'You notice {an(trap.name)} just in time and leap aside!')
            return
        kind = trap.kind
        if kind == 'dart':
            self.msg('A small dart shoots out and hits you!')
            self.hurt(random.randint(2, 6) + self.depth // 2, 'a dart trap')
            if not self.game_over and random.random() < 0.6 and p.str > 3:
                p.str = max(3, p.str - random.randint(1, 2))
                self.msg('The dart was poisoned! You feel weaker.')
        elif kind == 'pit':
            self.msg('You fall into a spiked pit!')
            self.hurt(random.randint(3, 8) + self.depth // 2, 'a spiked pit')
            p.stuck = random.randint(2, 4)
        elif kind == 'fire':
            self.msg('A jet of flame bursts from the floor! You catch fire!')
            self.hurt(random.randint(3, 10) + self.depth // 2, 'a fire trap')
            p.burn = max(p.burn, random.randint(3, 6))
            scrolls = [i for i in p.pack if i.kind == 'scroll']
            if scrolls and not self.game_over:
                self.use_up(random.choice(scrolls))
                self.msg('One of your scrolls burns to ash!')
        elif kind == 'frost':
            self.msg('A blast of freezing air engulfs you!')
            self.hurt(random.randint(4, 12) + self.depth // 2, 'a frost trap')
            if not self.game_over:
                p.frozen = max(p.frozen, random.randint(2, 4))
                self.msg('You are frozen in place!')
        elif kind == 'teleport':
            p.x, p.y = self.free_spot(random.choice(self.rooms))
            p.confused += random.randint(4, 8)
            self.compute_fov()
            self.msg('You step on a teleport trap! The world blurs and spins around you.')
        elif kind == 'alarm':
            for m in self.monsters:
                m.awake = True
            eligible = self.eligible_monsters()
            for _ in range(random.randint(1, 2)):
                m = Monster(random.choice(eligible), *self.free_spot(random.choice(self.rooms)),
                            self.depth)
                m.awake = True
                self.monsters.append(m)
            self.msg('A loud alarm rings out! Monsters come running from all over the level.')
        elif kind == 'sleep':
            self.msg('A cloud of sleeping gas engulfs you. You fall asleep...')
            self.asleep, battles = True, self.battles
            for _ in range(random.randint(5, 10)):
                if self.game_over or self.battles != battles:   # attacked in your sleep
                    break
                self.end_turn()
            self.asleep = False
            if not self.game_over and self.battles == battles:
                self.msg('You wake up.')
        elif kind == 'trapdoor':
            self.msg('A trapdoor opens beneath you! You fall through...')
            self.new_level()
            self.hurt(random.randint(2, 8) + self.depth // 3, 'a fall')
            self.arrive()

    def run(self, dx, dy):
        p = self.player
        for step in range(80):
            if self.game_over or (step and (self.visible_monsters() or self.msgs)):
                break
            nx, ny = p.x + dx, p.y + dy
            if step and (self.monster_at(nx, ny) or self.npc_at(nx, ny)):
                break
            trap = self.traps.get((nx, ny))
            if trap and trap.found:
                if not step:
                    self.msg(f'There is {an(trap.name)} in the way.')
                break
            if not self.player_move(dx, dy):
                break
            self.end_turn()
            if self.tiles[p.y][p.x] in (DOOR, STAIRS):
                break

    def rest(self):
        p = self.player
        if self.visible_monsters():
            self.msg('You cannot rest with monsters nearby!')
            return
        for _ in range(500):
            if (p.hp >= p.max_hp and p.mp >= p.max_mp) or self.game_over or self.msgs \
                    or self.visible_monsters():
                break
            self.end_turn()

    def add_to_pack(self, it):
        pack = self.player.pack
        if it.kind in STACKABLE:
            for other in pack:
                if other.kind == it.kind and other.sub == it.sub:
                    other.count += it.count
                    return other
        if len(pack) >= MAX_PACK:
            return None
        pack.append(it)
        return it

    def pickup(self, auto):
        p = self.player
        it = self.item_at(p.x, p.y)
        if not it:
            if not auto:
                self.msg('There is nothing here to pick up.')
            return False
        if it.kind == 'gold':
            p.gold += it.count
            self.items.remove(it)
            self.msg(f'You found {it.count} gold pieces.')
            return True
        if it.kind == 'amulet':
            self.items.remove(it)
            self.game_over = ('won',)
            return True
        name = self.item_name(it)
        stacked = self.add_to_pack(it)
        if not stacked:
            self.msg(f'Your pack is too full to pick up {name}.')
            return not auto
        self.items.remove(it)
        letter = chr(ord('a') + p.pack.index(stacked))
        self.msg(f'You now have {self.item_name(stacked)} ({letter}).')
        return True

    def use_up(self, it):
        it.count -= 1
        if it.count <= 0:
            self.player.pack.remove(it)

    def descend(self):
        p = self.player
        if self.tiles[p.y][p.x] != STAIRS:
            self.msg("I see no way down.")
            return False
        self.new_level()
        self.arrive()
        return False

    def arrive(self):
        self.msg(f'You are now on depth {self.depth} of {FINAL_DEPTH}.')
        if self.depth == self.env['depth'] and self.env['intro']:
            self.msg(self.env['intro'])
        boss = boss_at(self.depth)
        if boss:
            self.msg(BOSSES[boss]['arrive'])
        if self.npcs:
            self.msg('You sense a friendly presence on this floor (&).')

    # --------------------------------------------------------------- items
    def choose(self, verb, pred):
        opts = [(chr(ord('a') + i), it) for i, it in enumerate(self.player.pack) if pred(it)]
        if not opts:
            self.msg(f'You have nothing to {verb}.')
            return None
        self.show()
        k = self.menu(f'{verb.capitalize()} what? (Esc to cancel)',
                      [f'{l}) {self.describe(it)}' for l, it in opts])
        ch = chr(k) if 0 < k < 256 else ''
        return next((it for l, it in opts if l == ch), None)

    def quaff(self):
        it = self.choose('quaff', lambda i: i.kind == 'potion')
        return self.drink(it) if it else False

    def read(self):
        it = self.choose('read', lambda i: i.kind == 'scroll')
        return self.read_scroll(it) if it else False

    def eat(self):
        it = self.choose('eat', lambda i: i.kind == 'food')
        return self.eat_food(it) if it else False

    def drink(self, it):
        p = self.player
        kind = it.sub
        self.use_up(it)
        self.known.add(kind)
        if kind == 'healing':
            p.hp = min(p.max_hp, p.hp + random.randint(8, 14) + p.level * 2)
            p.cure()
            self.msg('You begin to feel better.')
        elif kind == 'extra healing':
            p.max_hp += 2
            p.hp = p.max_hp
            p.str = p.max_str
            p.cure()
            p.restore_mp()
            self.msg('You feel much better.')
        elif kind == 'mana':
            p.restore_mp()
            self.msg('Your mind clears as magic surges through you.')
        elif kind == 'strength':
            p.max_str += 1
            p.str = p.max_str
            self.msg('You feel stronger, now. What bulging muscles!')
        elif kind == 'poison':
            p.str = max(3, p.str - random.randint(1, 3))
            self.msg('You feel very sick now.')
        elif kind == 'confusion':
            p.confused += random.randint(8, 16)
            self.msg("Wait, what's going on here? Huh? What? Who?")
        elif kind == 'raise level':
            p.xp = max(p.xp, xp_needed(p.level))
            self.msg('You suddenly feel much more skillful.')
            self.gain_xp(0)
        return True

    def learn_spell(self, it):
        """Read a spell scroll. With MAX_SPELLS known, the player must forget one first.
        Returns False if the player kept the scroll after all."""
        p = self.player
        spell = it.sub
        if spell in p.moves:
            self.use_up(it)
            p.restore_mp()
            self.msg(f'You already know {spell}. The scroll crumbles away, restoring your mana.')
            return True
        if len(p.spells) >= MAX_SPELLS:
            old = self.pick_forget(spell)
            if not old:
                self.msg(f'You put the spell scroll of {spell} away for now.')
                return False
            p.moves.remove(old)
            self.msg(f'1, 2 and... poof! {self.name} forgot {old}.')
        p.moves.append(spell)
        self.use_up(it)
        self.msg(f'The scroll glows and crumbles to dust. {self.name} learned {spell}!')
        return True

    # ----------------------------------------------------------- spellbook
    def spellbook(self):
        """Show every move the player knows and what the wielded weapon adds to them."""
        p = self.player
        lo, hi = p.weapon_dmg
        w = p.weapon
        if w and w.magic:
            weapon = [f'Weapon: {self.item_name(w)}, a magic weapon',
                      f'Attack spells deal +{p.spell_power} damage. STRIKE and POWER SMASH hit '
                      f'for only {lo}-{hi}.']
        else:
            weapon = [f'Weapon: {self.item_name(w) + ", a physical weapon" if w else "bare hands"}',
                      f'STRIKE and POWER SMASH hit for {lo}-{hi} (plus strength). Spells get no '
                      'bonus.']
        self.draw_spells('SPELLBOOK', p.moves, None, 'press any key', weapon + [
            '', f'You know {len(p.spells)} of {MAX_SPELLS} spells. Learning another means '
            'forgetting one.'])
        self.wait_key()

    def pick_forget(self, spell):
        """Ask which known spell to forget for `spell`. None keeps things as they are."""
        options = self.player.spells
        i = self.select(lambda c: self.draw_spells(
            f'You know {MAX_SPELLS} spells already! Forget which one for {spell}?',
            options, c, f'Enter: forget it   Esc: keep the scroll of {spell} for later'),
            len(options))
        return None if i is None else options[i]

    def draw_spells(self, title, names, cur, footer, notes=()):
        p = self.player
        self.scr.erase()
        self.put(0, 0, f' {title}', curses.A_BOLD)
        self.put(0, 66, f'MP {p.mp}/{p.max_mp}', COLORS['blue'] | curses.A_BOLD)
        self.put(2, 2, '  MOVE              TYPE      COST  EFFECT', curses.A_UNDERLINE)
        for i, name in enumerate(names):
            info = MOVES[name]
            cost = f'{info["mp"]:>2} MP' if info['mp'] else 'free'
            line = (f'{"▶" if i == cur else " "} {name:<17} {info["type"].upper():<9} '
                    f'{cost:<5} {", ".join(move_notes(info))}')
            self.put(3 + i, 2, line[:77], curses.A_BOLD if i == cur else 0)
        for i, note in enumerate(notes):
            self.put(11 + i, 2, note[:77], COLORS['cyan'])
        self.put(23, 0, f' {footer} '[:79], curses.A_REVERSE)
        self.scr.refresh()

    def read_scroll(self, it):
        p = self.player
        kind = it.sub
        if kind in SPELLS:
            return self.learn_spell(it)
        self.use_up(it)
        self.known.add(kind)
        if kind == 'magic mapping':
            for y in range(MAP_H):
                for x in range(MAP_W):
                    if self.tiles[y][x] != ROCK:
                        self.explored[y][x] = True
            self.msg('Oh, now this scroll has a map on it.')
        elif kind == 'teleportation':
            p.x, p.y = self.free_spot(random.choice(self.rooms))
            self.compute_fov()
            self.msg('You feel very disoriented.')
        elif kind == 'enchant weapon':
            if p.weapon:
                p.weapon.ench += 1
                w = p.weapon
                self.msg(f'Your {w.sub} glows blue for a moment. ' +
                         (f'Your spells now get +{p.spell_power}.' if w.magic else
                          f'It now hits for {p.weapon_dmg[0]}-{p.weapon_dmg[1]}.'))
            else:
                self.msg('Your hands tingle.')
        elif kind == 'enchant armor':
            if p.armor:
                p.armor.ench += 1
                self.msg(f'Your armor glows silver for a moment. Your defense is now {p.ac}.')
            else:
                self.msg('Your skin crawls.')
        elif kind == 'detect traps':
            for t in self.traps.values():
                t.found = True
            n = len(self.traps)
            self.msg(f'Your feet tingle. You sense {n} trap{"s" if n != 1 else ""} on this level.'
                     if n else 'Your feet tingle, but you sense no traps here.')
        elif kind == 'identify':
            self.msg('This is a scroll of identify.')
            target = self.choose('identify', lambda i: i.kind in ('potion', 'scroll')
                                 and i.sub not in self.known and i.sub not in SPELLS)
            if target:
                self.known.add(target.sub)
                self.msg(f'That is {self.item_name(target)}.')
        elif kind == 'aggravate monsters':
            for m in self.monsters:
                m.awake = True
            self.msg('You hear a high-pitched humming noise.')
        return True

    def eat_food(self, it):
        p = self.player
        self.use_up(it)
        p.food = min(2000, max(p.food, 0) + 1100)
        self.msg(random.choice(['Yum, that tasted good.',
                                'This food tastes awful, but you eat it anyway.']))
        return True

    def wield(self):
        p = self.player
        it = self.choose('wield', lambda i: i.kind == 'weapon')
        if not it:
            return False
        if it is p.weapon:
            self.msg('You are already wielding that.')
            return False
        p.weapon = it
        self.msg(f'You are now wielding {self.item_name(it)}.')
        return True

    def wear(self):
        p = self.player
        it = self.choose('wear', lambda i: i.kind == 'armor')
        if not it:
            return False
        if it is p.armor:
            self.msg('You are already wearing that.')
            return False
        p.armor = it
        self.msg(f'You are now wearing {self.item_name(it)}.')
        return True

    def drop(self):
        p = self.player
        it = self.choose('drop', lambda i: True)
        if not it:
            return False
        if self.item_at(p.x, p.y) or self.tiles[p.y][p.x] == STAIRS:
            self.msg('There is already something there.')
            return False
        if it is p.weapon:
            p.weapon = None
        if it is p.armor:
            p.armor = None
        p.pack.remove(it)
        it.x, it.y, it.seen = p.x, p.y, True
        self.items.append(it)
        self.msg(f'You dropped {self.item_name(it)}.')
        return True

    # ------------------------------------------------------------- drawing
    def put(self, y, x, s, attr=0):
        try:
            self.scr.addstr(y, x, s, attr)
        except curses.error:
            pass

    def draw(self, top_lines, more=False, refresh=True):
        scr, p = self.scr, self.player
        scr.erase()
        for i, line in enumerate(top_lines[:2]):
            if more and i == len(top_lines[:2]) - 1:
                line += ' --More--'
            self.put(i, 0, line)

        wall = self.env['wall']
        tile_colors = {HWALL: wall, VWALL: wall, DOOR: 'yellow',
                       FLOOR: 'white', CORRIDOR: 'white', STAIRS: 'green',
                       CAVE_WALL: wall, POOL: self.env.get('pool', ('', 'red'))[1]}
        for y in range(MAP_H):
            row = self.tiles[y]
            for x in range(MAP_W):
                if not self.explored[y][x] or row[x] == ROCK:
                    continue
                t = row[x]
                if (x, y) in self.visible:
                    attr = COLORS[tile_colors[t]] | (curses.A_BOLD if t in (STAIRS, POOL) else 0)
                else:
                    attr = COLORS['blue']
                self.put(MAP_TOP + y, x, t, attr)

        for (x, y), t in self.traps.items():
            if t.found:
                color = TRAPS[t.kind][1] if (x, y) in self.visible else 'blue'
                self.put(MAP_TOP + y, x, '^', COLORS[color] | curses.A_BOLD)
        for it in self.items:
            if (it.x, it.y) in self.visible:
                it.seen = True
            if it.seen:
                self.put(MAP_TOP + it.y, it.x, ITEM_CHARS[it.kind],
                         COLORS[ITEM_COLORS[it.kind]] | curses.A_BOLD)
        for npc in self.npcs:
            if (npc.x, npc.y) in self.visible:
                self.put(MAP_TOP + npc.y, npc.x, '&', COLORS[npc.color] | curses.A_BOLD)
        for m in self.visible_monsters():
            self.put(MAP_TOP + m.y, m.x, m.ch, COLORS[m.color] | curses.A_BOLD)
        self.put(MAP_TOP + p.y, p.x, '@', COLORS['yellow'] | curses.A_BOLD)

        hunger = ('' if p.food > 300 else 'Hungry' if p.food > 150
                  else 'Weak' if p.food > 0 else 'Starving')
        strength = f'Str:{p.str}' + (f'({p.max_str})' if p.str < p.max_str else '')
        status = (f'Depth:{self.depth} HP:{p.hp}({p.max_hp}) MP:{p.mp}({p.max_mp}) {strength} '
                  f'Def:{p.ac} Lvl:{p.level} Exp:{p.xp}/{xp_needed(p.level)} Gold:{p.gold}')
        self.put(STATUS_ROW, 0, status)
        hp_attr = COLORS['red'] | curses.A_BOLD if p.hp <= p.max_hp // 3 else 0
        self.put(STATUS_ROW, status.index('HP:'), f'HP:{p.hp}', hp_attr)
        flags = ' '.join(f for f in (hunger, 'Confused' if p.confused else '',
                                     'Stuck' if p.stuck else '', 'Burning' if p.burn else '',
                                     'Frozen' if p.frozen else '',
                                     'Paralyzed' if p.paralyzed else '') if f)
        if flags:
            self.put(STATUS_ROW, len(status) + 2, flags, COLORS['red'] | curses.A_BOLD)
        if self.auto_skip:
            self.put(STATUS_ROW, len(status) + 2 + (len(flags) + 1 if flags else 0),
                     'Auto', COLORS['green'] | curses.A_BOLD)
        self.draw_log_panel()
        if refresh:
            scr.refresh()

    def log_lines(self, width, entries, stamps=True):
        """Event log entries as (text, attr) screen lines wrapped to `width`, oldest first.
        A header marks every change of depth; stamps puts the turn number in front."""
        lines, depth = [], None
        pad = 7 if stamps else 2
        for turn, d, text, n in entries:
            if d != depth:
                depth = d
                lines.append((f'-- Depth {d}: {environment(max(1, d))["name"]} --'[:width],
                              COLORS['cyan'] | curses.A_BOLD))
            if n > 1:
                text += f' (x{n})'
            attr = next((COLORS[c] | curses.A_BOLD for key, c in LOG_HIGHLIGHTS if key in text), 0)
            for i, part in enumerate(textwrap.wrap(text, width - pad) or ['']):
                head = (f'{turn:>5}  ' if stamps else '- ') if i == 0 else ' ' * pad
                lines.append((head + part, attr))
        return lines

    def draw_log_panel(self):
        """In a terminal bigger than 80x24, show the latest events beside or below the game."""
        rows, cols = self.scr.getmaxyx()
        if cols >= 104:
            top, left, height, width = 0, 81, rows - 1, cols - 82
        elif rows >= 28:
            top, left, height, width = 25, 0, rows - 26, min(cols - 1, 80)
        else:
            return
        self.put(top, left, ' RECENT EVENTS '.center(width, '─'), COLORS['cyan'])
        lines = self.log_lines(width, self.log[-height:], stamps=False)[-height:]
        for i, (line, attr) in enumerate(lines):
            self.put(top + 1 + i, left, line, attr)

    def show_log(self):
        """Scroll through the event log. It opens at the newest events."""
        rows, cols = self.scr.getmaxyx()
        width, height = min(cols, 120) - 1, rows - 2
        lines = self.log_lines(width, self.log) or [('Nothing has happened yet.', 0)]
        bottom = max(0, len(lines) - height)
        top = bottom
        while True:
            self.scr.erase()
            self.put(0, 0, f' EVENT LOG   (turn {self.turn}, depth {self.depth})'.ljust(width),
                     curses.A_REVERSE)
            for i, (line, attr) in enumerate(lines[top:top + height]):
                self.put(1 + i, 0, line, attr)
            where = 'end' if top >= bottom else f'{top + height}/{len(lines)}'
            self.put(rows - 1, 0, f' up/down or j/k: scroll   PgUp/PgDn/space: page   '
                     f'g/G: start/end   Esc: close   [{where}] '[:width], curses.A_REVERSE)
            self.scr.refresh()
            k = self.scr.getch()
            ch = chr(k) if 0 < k < 256 else ''
            if k == curses.KEY_UP or ch == 'k':
                top -= 1
            elif k == curses.KEY_DOWN or ch == 'j':
                top += 1
            elif k == curses.KEY_PPAGE or ch == 'b':
                top -= height
            elif k == curses.KEY_NPAGE or ch == ' ':
                top += height
            elif ch == 'g' or k == curses.KEY_HOME:
                top = 0
            elif ch == 'G' or k == curses.KEY_END:
                top = bottom
            elif k == curses.KEY_RESIZE:
                return self.show_log()
            elif ch in CANCEL_KEYS or ch in ('q', 'm', '\n', '\r'):
                return
            top = max(0, min(bottom, top))

    def show(self):
        """Draw the screen, paging through this turn's messages with --More--."""
        if self.foe:
            self.flush_battle_msgs()
            self.draw_battle()
            return
        lines = textwrap.wrap('  '.join(self.msgs), MAP_W - 10) or ['']
        self.msgs = []
        while len(lines) > 2:
            self.draw(lines[:2], more=True)
            self.wait_key()
            lines = lines[2:]
        self.draw(lines)

    def wait_key(self):
        while self.scr.getch() == curses.KEY_RESIZE:
            pass

    def menu(self, title, entries):
        width = max(len(title), *(len(e) for e in entries)) + 2
        x = max(0, MAP_W - width - 1)
        rows = [title, ''] + entries
        for i, line in enumerate(rows[:22]):
            self.put(1 + i, x, ' ' + line.ljust(width), curses.A_REVERSE if i == 0 else 0)
        self.scr.refresh()
        return self.scr.getch()

    def full_screen(self, lines):
        self.scr.erase()
        for i, line in enumerate(lines[:23]):
            self.put(i, 0, line)
        self.put(23, 0, '-- press any key --', curses.A_REVERSE)
        self.scr.refresh()
        self.wait_key()

    def show_inventory(self):
        p = self.player
        if not p.pack:
            self.msg('You are empty-handed.')
            return
        self.show()
        self.menu(f'Inventory ({len(p.pack)}/{MAX_PACK})',
                  [f'{chr(ord("a") + i)}) {self.describe(it)}' for i, it in enumerate(p.pack)])

    HELP = [
        'COMMANDS                                               y k u',
        '  h j k l y u b n   move (or arrow keys / numpad)       \\|/',
        '  H J K L Y U B N   run in that direction             h-@-l',
        '  . or 5            rest one turn                       /|\\',
        '  z                 rest until HP and MP are full      b j n',
        '  s                 search nearby for hidden traps',
        '  , or g            pick up item         >  go down stairs',
        '  i  inventory      m  event log (all that happened)   ?  help     Q  quit',
        '  q  quaff potion   r  read scroll   e  eat food       S  spells & weapon',
        '  w  wield weapon   W  wear armor    d  drop item',
        '  A  toggle auto-skip of easy battles',
        '',
        'BATTLES, TRAPS & TALKING',
        '  Bump a monster to fight. In battle, S skips easy fights and M opens the log.',
        '  In menus: arrows/hjkl move the cursor, Enter/space/z choose, Esc/x go back.',
        '  Walk into a friendly character (&) to talk to them.',
        '  Traps are hidden until found; known traps (^) ask before you step on them.',
        f'  Spells cost MP and come from spell scrolls (r). You can know {MAX_SPELLS} at once.',
        'SYMBOLS',
        '  @ you  & friend  > stairs  ! potion  ? scroll  ) weapon  ] armor  ^ trap',
        '  : food  * gold  " Amulet  + door  # corridor  % cave wall  ~ lava / icy water',
        '',
        f'Beat the bosses on depths 10 and {FINAL_DEPTH} and claim the Amulet of Yendor.',
    ]

    # --------------------------------------------------------------- input
    def handle_key(self, k):
        """Perform a command. Returns True if it used up a turn."""
        ch = ARROWS.get(k) or (chr(k) if 0 < k < 256 else '')
        ch = NUMPAD.get(ch, ch)
        if ch in DIRS:
            return self.player_move(*DIRS[ch])
        if ch.lower() in DIRS and ch.isupper():
            self.run(*DIRS[ch.lower()])
            return False
        actions = {
            ',': lambda: self.pickup(auto=False), 'g': lambda: self.pickup(auto=False),
            '>': self.descend, 'q': self.quaff, 'r': self.read, 'e': self.eat,
            'w': self.wield, 'W': self.wear, 'd': self.drop,
        }
        if ch in actions:
            return actions[ch]()
        if ch in ('.', '5'):
            return True
        if ch == 's':
            return self.search()
        if ch == 'z':
            self.rest()
        elif ch == 'i':
            self.show_inventory()
        elif ch == '?':
            self.full_screen(self.HELP)
        elif ch in ('m', '\x10'):
            self.show_log()
        elif ch == 'S':
            self.spellbook()
        elif ch == 'A':
            self.auto_skip = not self.auto_skip
            self.msg(f'Auto-skip easy battles: {"ON" if self.auto_skip else "OFF"}.')
        elif ch == 'Q':
            if self.confirm('Really quit? (y/n)'):
                self.game_over = ('quit',)
        return False

    def confirm(self, question):
        self.show()
        self.draw([question])
        return self.scr.getch() in (ord('y'), ord('Y'))

    def play(self):
        while not self.game_over:
            self.show()
            k = self.scr.getch()
            if k == curses.KEY_RESIZE:
                continue
            if self.handle_key(k):
                self.end_turn()
        self.show()
        self.wait_key()
        self.ending_screen()

    def ending_screen(self):
        p = self.player
        kind = self.game_over[0]
        if kind == 'died':
            def c(s):
                return s[:18].center(18)
            stone = [
                '',
                '                     __________',
                '                    /          \\',
                '                   /    REST    \\',
                '                  /      IN      \\',
                '                 /     PEACE      \\',
                '                /                  \\',
                f'                | {c(self.name)} |',
                f'                | {c(f"{p.gold} Au")} |',
                f'                | {c("killed by")} |',
                f'                | {c(self.game_over[1])} |',
                f'                | {c(f"on depth {self.depth}")} |',
                f'                | {c(f"at level {p.level}")} |',
                '               *|     *  *  *        | *',
                "       ________)/\\\\_//(\\/(/\\)/\\//\\/|_)_______",
            ]
            self.full_screen(stone)
        elif kind == 'won':
            self.full_screen([
                '', '',
                '   You pick up the Amulet of Yendor!',
                '',
                '   Its power whisks you up through the dungeon and out into the',
                '   daylight. The Guild of Adventurers will sing of this day.',
                '',
                f'   {self.name} escaped with the Amulet and {p.gold} gold pieces',
                f'   at experience level {p.level} after {self.turn} turns.',
                '', '   Congratulations!',
            ])
        else:
            self.full_screen(['', f'   You quit on depth {self.depth} with {p.gold} gold pieces.'])


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


if __name__ == '__main__':
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')
    error = curses.wrapper(main)
    if error:
        print(error)
