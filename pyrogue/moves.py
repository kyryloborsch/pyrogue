"""Battle moves and spells, type effectiveness and battle statuses."""

# Player battle moves. Physical moves (mult) cost no mana, swing the wielded weapon and
# are aimed at a body part (see PARTS); spells cost mana (mp) and roll d6s, plus the
# player's level and the power of a magic weapon. effect: (status,
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
FIELD_EFFECTS = ('heal', 'mana', 'barrier')   # spells with these work outside battle too
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
    ('normal', 'undead'): 0.75, ('normal', 'elemental'): 1.25, ('normal', 'demon'): 1.25,
    ('ice', 'dragon'): 1.5, ('ice', 'elemental'): 1.5, ('ice', 'demon'): 0.5,
    ('storm', 'humanoid'): 1.5, ('storm', 'beast'): 1.25, ('storm', 'elemental'): 0.5,
    ('poison', 'undead'): 0.5, ('poison', 'elemental'): 0.5, ('poison', 'giant'): 0.75,
    ('dark', 'humanoid'): 1.25, ('dark', 'undead'): 0.5, ('dark', 'demon'): 0.5,
}


def field_spell(name):
    """Can this spell be cast while exploring, not just in battle?"""
    return any(key in MOVES[name] for key in FIELD_EFFECTS)


def move_notes(info):
    """Short descriptions of what a move does, for the battle and inventory screens."""
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
# The statuses that can cost a monster its turn. With every foe under one, RUN always works.
DISABLING = ('sleep', 'freeze', 'paralyze', 'confuse')
