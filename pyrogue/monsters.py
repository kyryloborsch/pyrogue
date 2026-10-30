"""Monsters: their stats, body parts and weak spots."""

import random

from .moves import EFFECTIVENESS

# Difficulty: monster HP and damage are scaled by these, and grow a little more for every
# depth a monster lives below its home levels.
MONSTER_HP_SCALE = 1.25
MONSTER_DMG_SCALE = 1.2
# A monster loses track of you after FORGET_TURNS turns out of sight and more than
# FORGET_DIST steps away, and goes back to roaming the level.
FORGET_DIST = 10
FORGET_TURNS = 6
NOISE_MEMORY = 20               # extra turns a monster keeps the trail after a loud noise
# Now and then a monster is born different: MODIFIER_CHANCE that it gets one of these, shown
# before its name in battle. hp, dmg and xp multiply its own; ac, power (to hit) and level
# (which makes running away harder) are added. Bosses never get one.
MODIFIER_CHANCE = 0.15
MODIFIERS = {
    'TOUGH':   {'color': 'green',  'hp': 1.25, 'xp': 1.15},
    'FIERCE':  {'color': 'red',    'dmg': 1.15, 'xp': 1.15},
    'ARMORED': {'color': 'cyan',   'ac': 2, 'xp': 1.1},
    'SWIFT':   {'color': 'yellow', 'power': 2, 'level': 1, 'xp': 1.1},
    'FEEBLE':  {'color': 'white',  'hp': 0.85, 'dmg': 0.9, 'xp': 0.85},
}

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

# Where a physical move can be aimed: accuracy change, damage multiplier.
PARTS = {
    'BODY':  (0, 1.0),
    'HEAD':  (-20, 1.25),
    'ARMS':  (-10, 1.0),
    'LEGS':  (-5, 1.0),
    'WINGS': (-15, 1.0),
    'TAIL':  (-10, 1.0),
}
WEAK_SPOT_MULT = 1.5             # extra damage when a blow lands on a monster's weak spot
# Body parts by battle type, and for monsters built differently from the rest of their type.
BODY_PLANS = {
    'humanoid': ['BODY', 'HEAD', 'ARMS', 'LEGS'], 'undead': ['BODY', 'HEAD', 'ARMS', 'LEGS'],
    'giant': ['BODY', 'HEAD', 'ARMS', 'LEGS'], 'demon': ['BODY', 'HEAD', 'ARMS', 'LEGS'],
    'beast': ['BODY', 'HEAD', 'LEGS'], 'dragon': ['BODY', 'HEAD', 'WINGS', 'TAIL'],
    'elemental': ['BODY', 'HEAD', 'ARMS', 'LEGS'],
    'bat': ['BODY', 'HEAD', 'WINGS'], 'snake': ['BODY', 'HEAD', 'TAIL'],
    'basilisk': ['BODY', 'HEAD', 'LEGS', 'TAIL'], 'magma slug': ['BODY', 'HEAD', 'TAIL'],
    'fire imp': ['BODY', 'HEAD', 'ARMS', 'WINGS'], 'wraith': ['BODY', 'HEAD', 'ARMS'],
    'banshee': ['BODY', 'HEAD', 'ARMS'],
}
# A monster's one weak spot (never its BODY). The player learns it by hitting it. Monsters
# that resist normal blows (the undead) have none; see NO_WEAK_SPOT below.
WEAK_SPOTS = {
    'rat': 'HEAD', 'bat': 'WINGS', 'kobold': 'LEGS', 'jackal': 'LEGS', 'goblin': 'HEAD',
    'snake': 'HEAD', 'orc': 'LEGS', 'hobgoblin': 'ARMS', 'ogre': 'LEGS', 'troll': 'LEGS',
    'magma slug': 'TAIL', 'cave spider': 'LEGS', 'fire imp': 'WINGS', 'basilisk': 'TAIL',
    'dragon': 'WINGS', 'lava golem': 'HEAD', 'shadow demon': 'ARMS', 'frost wolf': 'LEGS',
    'yeti': 'HEAD', 'ice troll': 'LEGS', 'frost giant': 'LEGS', 'frost wyrm': 'TAIL',
}

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

# Battle types that shrug off normal blows have no weak spot, so a type that starts
# resisting them in EFFECTIVENESS loses its weak spots too.
NO_WEAK_SPOT = {kind for (move, kind), eff in EFFECTIVENESS.items()
                if move == 'normal' and eff < 1}
WEAK_SPOTS = {name: part for name, part in WEAK_SPOTS.items()
              if MONSTER_INFO[name][0] not in NO_WEAK_SPOT}


class Monster:
    mod = None                       # its MODIFIERS key, if it has one

    def __init__(self, tpl, x, y, depth=0):
        ch, name, hp, ac, dmg, xp, lo, _hi, color, flags = tpl
        self.ch, self.name, self.ac, self.xp = ch, name, ac, xp
        self.type, *self.moves = MONSTER_INFO[name]
        self.parts = BODY_PLANS.get(name) or BODY_PLANS[self.type]
        self.weak = WEAK_SPOTS.get(name)         # None: it has no weak spot
        self.power = lo * 2 + 2
        self.level = max(1, lo * 2 - 1 + random.randint(0, 2))
        deeper = max(0, depth - lo)                           # tougher the deeper they live
        hp = int(hp * MONSTER_HP_SCALE * (1 + 0.08 * deeper))
        self.hp = self.max_hp = hp + random.randint(0, hp // 3)
        scale = MONSTER_DMG_SCALE * (1 + 0.04 * deeper)
        self.dmg = (max(1, round(dmg[0] * scale)), max(2, round(dmg[1] * scale)))
        self.color = color
        self.flags = flags.split()
        self.x, self.y = x, y
        self.awake = random.random() < 0.6
        self.roaming = False         # lost track of the player and wanders about
        self.lost = 0                # turns since it last knew where the player was
        self.stun = 0
        self.phased = False          # a boss has switched tactics at half HP
        self.status = {}             # battle status -> turns left (see STATUSES)
        if 'boss' not in self.flags and random.random() < MODIFIER_CHANCE:
            self.modify(random.choice(list(MODIFIERS)))

    def modify(self, mod):
        """Give the monster a stat modifier (see MODIFIERS)."""
        self.mod, m = mod, MODIFIERS[mod]
        self.hp = self.max_hp = max(1, round(self.max_hp * m.get('hp', 1)))
        self.dmg = tuple(max(1, round(d * m.get('dmg', 1))) for d in self.dmg)
        self.ac += m.get('ac', 0)
        self.power += m.get('power', 0)
        self.level += m.get('level', 0)
        self.xp = max(1, round(self.xp * m.get('xp', 1)))

    @property
    def title(self):
        """Its name with its modifier, like 'tough orc'."""
        return f'{self.mod.lower()} {self.name}' if self.mod else self.name

    def alert(self, memory=0):
        """Wake up knowing where the player is, and keep the trail memory turns longer."""
        self.awake, self.roaming, self.lost = True, False, -memory
