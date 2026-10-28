"""Weapons, armor, potions, scrolls and the other things you can carry."""

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
HIDDEN_ITEM_CHANCE = 0.06        # chance a search turns up a hidden item (once per room)


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
