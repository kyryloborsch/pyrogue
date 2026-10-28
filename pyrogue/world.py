"""The four environments, the bosses and the traps."""

from .constants import FINAL_DEPTH

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

# Five levels each. layout: 'rooms', 'crypts' (tombs on a grid, with pillared halls),
# 'caves' or 'glacier' (open caves split by crevasses of icy water).
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
    {'name': 'Frozen Abyss', 'depth': 16, 'layout': 'glacier', 'wall': 'cyan',
     'pool': ('icy water', 'blue', 'The icy water would freeze you solid!',
              'You stumble into the icy water! It is freezing!'), 'pools': (1, 3),
     'traps': ['dart', 'pit', 'teleport', 'sleep', 'frost', 'frost', 'trapdoor'],
     'intro': 'A bitter wind howls up from below as the lava gives way to ice, split by '
              'deep crevasses. Welcome to the Frozen Abyss.'},
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


class Trap:
    def __init__(self, kind):
        self.kind = kind
        self.found = False

    @property
    def name(self):
        return TRAPS[self.kind][0]
