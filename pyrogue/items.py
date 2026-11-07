"""Weapons, armor, potions, scrolls and the other things you can carry."""

# name, damage range, magic power. Physical weapons hit hard and enchant into harder hits.
# Magic weapons barely hurt in melee, but add their power (and enchantment) to every spell.
WEAPONS = [('dagger', 1, 4, 0), ('spear', 2, 6, 0), ('mace', 2, 8, 0),
           ('long sword', 3, 10, 0), ('two-handed sword', 4, 14, 0),
           ('wand', 1, 2, 2), ('oak staff', 1, 4, 3), ('crystal rod', 1, 3, 5),
           ('runed staff', 2, 5, 7)]
# Deeper down, better kinds of weapon turn up more often and come better enchanted (+1 per
# WEAPON_ENCH_EVERY depths). SPELL_SLOT_CHANCE of the magic ones found hold 1-2 extra spells.
WEAPON_ENCH_EVERY = 5
SPELL_SLOT_CHANCE = 0.5
# Rings, worn MAX_RINGS at a time: kind -> (bonus per point of the ring's power, tag, what
# it does, how often it turns up). A ring's power (its ench) grows with depth: 1, plus 1 per
# RING_POWER_EVERY depths, plus 0 or 1. The rare ring of memory is always +1 spell slot.
RINGS = {
    'protection':   (1, 'def', 'adds to your defense', 6),
    'vitality':     (5, 'max HP', 'raises your max HP', 6),
    'wisdom':       (3, 'max MP', 'raises your max MP', 6),
    'power':        (1, 'spell', 'adds to the damage of every attack spell', 6),
    'might':        (1, 'dmg', 'adds to the damage of STRIKE and POWER SMASH', 6),
    'regeneration': (1, 'regen', 'makes your HP come back faster', 6),
    'memory':       (1, 'spell slot', 'lets you hold one more spell', 1),
    'free action':  (35, '% resist', 'may shake off freezing, paralysis, confusion and sleep '
                     '(at 100%, nothing holds you)', 4),
}
MAX_RINGS = 2
RING_POWER_EVERY = 6
ARMORS = [('leather armor', 2), ('studded leather', 3), ('ring mail', 3),
          ('scale mail', 4), ('chain mail', 5), ('splint mail', 6), ('plate mail', 7)]
POTIONS = ['healing', 'extra healing', 'mana', 'strength', 'poison', 'confusion', 'raise level']
POTION_WEIGHTS = [30, 10, 16, 12, 15, 15, 6]
POTION_PRICES = {'healing': 30, 'extra healing': 80, 'mana': 50, 'strength': 120,
                 'poison': 15, 'confusion': 15, 'raise level': 150}
SCROLLS = ['magic mapping', 'teleportation', 'enchant weapon', 'enchant armor',
           'identify', 'aggravate monsters', 'detect traps']
SCROLL_WEIGHTS = [12, 12, 15, 15, 25, 8, 12]
SCROLL_PRICES = {'magic mapping': 50, 'teleportation': 40, 'enchant weapon': 70,
                 'enchant armor': 70, 'identify': 25, 'aggravate monsters': 15,
                 'detect traps': 30}
UNKNOWN_PRICE = 30               # what any potion or scroll you haven't identified is worth
POTION_COLORS = ['red', 'blue', 'green', 'amber', 'violet', 'turquoise', 'black',
                 'pink', 'white', 'orange', 'grey', 'golden']
SYLLABLES = ['ab', 'zok', 'ra', 'nix', 'vel', 'tor', 'um', 'ka', 'zim', 'ol',
             'eth', 'qua', 'bar', 'sno', 'pli', 'xu', 'mor', 'fen', 'gah', 'ip']
ITEM_CHARS = {'potion': '!', 'scroll': '?', 'weapon': ')', 'armor': ']', 'ring': '=',
              'food': ':', 'gold': '*', 'amulet': '"'}
ITEM_COLORS = {'potion': 'magenta', 'scroll': 'cyan', 'weapon': 'cyan', 'armor': 'cyan',
               'ring': 'yellow', 'food': 'yellow', 'gold': 'yellow', 'amulet': 'magenta'}
STACKABLE = {'potion', 'scroll', 'food'}
# the inventory's sections, in order: kind -> heading
CATEGORIES = {'weapon': 'WEAPONS', 'armor': 'ARMOR', 'ring': 'RINGS', 'potion': 'POTIONS',
              'scroll': 'SCROLLS', 'food': 'FOOD'}
# what the inventory says about a potion or scroll once you know what it is
ITEM_NOTES = {
    'healing': 'Heals some HP and cures ailments.',
    'extra healing': 'Heals you fully, cures ailments, restores MP and raises your max HP.',
    'mana': 'Restores all your MP.',
    'strength': 'Makes you permanently stronger.',
    'poison': 'Saps your strength. Best left alone!',
    'confusion': 'Muddles your head for a while. Best left alone!',
    'raise level': 'Lifts you straight to the next level.',
    'magic mapping': 'Shows you the map of this floor.',
    'teleportation': 'Whisks you away to a random room.',
    'enchant weapon': 'Makes your weapon permanently better.',
    'enchant armor': 'Makes your armor permanently better.',
    'identify': 'Tells you what one unknown potion or scroll is.',
    'aggravate monsters': 'Wakes every monster on the floor. Best left alone!',
    'detect traps': 'Reveals every trap on this floor.',
}
HIDDEN_ITEM_CHANCE = 0.06        # chance a search turns up a hidden item (once per room)


class Item:
    slots = 0                        # extra spells a magic weapon lets you hold

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


def ring_bonus(it):
    """How much a ring gives, in the units of its tag."""
    bonus = RINGS[it.sub][0] * it.ench
    return min(100, bonus) if it.sub == 'free action' else bonus


def ring_tag(it):
    """A ring's bonus as shown, like '+2 def' or '+70% resist'."""
    tag = RINGS[it.sub][1]
    return f'+{ring_bonus(it)}{"" if tag.startswith("%") else " "}{tag}'


def make_armor(name, ench=0):
    it = Item('armor', name, ench=ench)
    it.ac = next(ac for n, ac in ARMORS if n == name)
    return it
