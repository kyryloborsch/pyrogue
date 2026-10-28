"""The friendly characters (&): who they are, where they turn up, and what the bard sings."""

from .sprites import sprite

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
    'smith': ('BRAM THE SMITH', 'red', sprite(r'''
   _____
  ( o o )
  ( === )  _
  /|[ ]|\|=|
   |___|  |
''')),
    'arcanist': ('MAGE ORIEL', 'blue', sprite(r'''
     /\
    /**\    *
   ( o o)  /
    \_~/  /
   /|##|\/
''')),
    'ghost': ('A RESTLESS SPIRIT', 'white', sprite(r'''
   .---.
  ( O O )
  |  o  |
  |     |
  'v'v'v'
''')),
}
# The sage waits on depth 1 and a merchant near the stairs of every even depth (in the
# starting room on a boss level, which has no stairs yet). A bard always turns up by depth
# BARD_BY, and the healer waits before a boss if she hasn't shown up yet. Anyone else turns
# up only now and then, and only once per game.
MERCHANT_EVERY = 2               # a merchant on every 2nd depth
BARD_BY = 5                      # the deepest floor the bard can first turn up on
NPC_CHANCE = 0.35                # chance that one other character turns up on an ordinary level
# who that may be: kind -> (weight, first depth, only in this layout)
NPC_SPAWNS = {
    'healer': (3, 2, None), 'bard': (3, 2, None), 'hermit': (2, 2, None),
    'arcanist': (2, 2, None), 'smith': (2, 3, None),
    'ghost': (6, 1, 'crypts'),
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
    'Ogres and trolls stand on weak knees. Aim low and they topple!',
    'A bat with torn WINGS is just a rat. Aim for the wings.',
    'The Bone King wears his whole kingdom in that crown. Strike at his HEAD.',
    'Every creature has a weak spot. Hit it once and you will never forget where it is.',
    'Giants of the Frozen Abyss hate fire. A FIRE BOLT melts them like snow.',
    'Never linger in a fight near a crowd. The whole room will come to the party.',
]


class NPC:
    def __init__(self, kind, x, y):
        self.kind, self.x, self.y = kind, x, y
        self.name, self.color, self.portrait = NPC_INFO[kind]
        self.talked = 0
        self.done = False
        self.stock = []              # a merchant's wares, or the spells a mage teaches
        self.used = set()            # services already given (the smith works on each once)
        self.area = set()            # floor tiles the character may wander over
