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
# Caves may also have open_chance: how open the caves are (0.56 otherwise), crevasses:
# (fewest, most) rivers of pool cut across the map, and chambers: choices for how many
# walled rooms are set into the rock.
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
     'open_chance': 0.6, 'crevasses': (1, 2), 'chambers': (0, 0, 1, 1, 2),
     'traps': ['dart', 'pit', 'teleport', 'sleep', 'frost', 'frost', 'trapdoor'],
     'intro': 'A bitter wind howls up from below as the lava gives way to ice, split by '
              'deep crevasses. Welcome to the Frozen Abyss.'},
]

# Any floor but depth 1 and the last of its environment has VARIANT_CHANCE of being that
# environment's variant instead: these settings laid over the environment's own. arrive is said every
# time you reach one. sight: how far you can see (FOV_RADIUS otherwise). collapse: the
# chance each tomb of the Catacombs has caved in. rubble: (fewest, most) heaps of fallen
# rock in the tombs.
VARIANT_CHANCE = 0.25
VARIANTS = {
    'Dungeons of Doom': {
        'name': 'Unlit Halls', 'sight': 2,
        'arrive': 'No torch has burned on this floor for ages. You can barely see past your '
                  'nose, and neither can anything else.'},
    'Sunken Catacombs': {
        'name': 'Collapsed Catacombs', 'collapse': 0.35, 'rubble': (4, 8),
        'traps': ['dart', 'pit', 'pit', 'teleport', 'sleep', 'alarm', 'trapdoor', 'trapdoor'],
        'arrive': 'Half the tombs on this floor have caved in, and fallen rock chokes the rest.'},
    'Ember Caverns': {
        'name': 'Magma Rivers', 'crevasses': (1, 2), 'pools': (1, 2),
        'arrive': 'Rivers of molten rock wind through these caves. Cross them only where '
                  'the stone bridges them.'},
    'Frozen Abyss': {
        'name': 'Ice Vaults', 'open_chance': 0.53, 'crevasses': (1, 1), 'chambers': (3, 3, 4),
        'arrive': 'Old vaults have been cut deep into the ice walls here. Who sealed them, '
                  'and what did they leave behind?'},
}

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


def last_floor(env):
    """The deepest floor of an environment."""
    later = [e['depth'] for e in ENVIRONMENTS if e['depth'] > env['depth']]
    return min(later) - 1 if later else FINAL_DEPTH


def floor_env(depth, roll):
    """The settings a floor is built with: its environment's, or, when roll (0-1) comes in
    under VARIANT_CHANCE and it's neither depth 1 nor the environment's last floor, its
    variant's."""
    env = environment(depth)
    if 1 < depth < last_floor(env) and roll < VARIANT_CHANCE:
        return {**env, **VARIANTS[env['name']]}
    return env


def boss_at(depth):
    return next((name for name, b in BOSSES.items() if b['depth'] == depth), None)


class Trap:
    def __init__(self, kind):
        self.kind = kind
        self.found = False

    @property
    def name(self):
        return TRAPS[self.kind][0]
