"""A hero: one player's character, with what that player sees, reads and is fighting."""

from .player import Player


class Battle:
    """A fight: the monsters in it (foes[0] is the target) and the heroes fighting them."""

    def __init__(self, foes, heroes):
        self.foes = foes
        self.heroes = heroes


class Hero:
    """Everything that belongs to one player rather than to the whole dungeon. A game alone
    has one hero; a co-op game has one per player."""

    def __init__(self, name, scr=None, color='yellow'):
        self.name = name
        self.scr = scr               # the screen this player looks at (not saved)
        self.player = Player()
        self.msgs = []
        self.log = []                # event log: [turn, depth, text, times repeated]
        self.visible = set()
        self.battle = None           # the Battle this hero is in, if any
        self.battles = 0             # battles fought (lets a sleeping player notice an attack)
        self.asleep = False          # knocked out by sleeping gas
        self.pending_key = None      # key read while waiting for a second arrow key
        self.shown_hp = [0, 0]       # HP values the battle bars are showing (for animation)
        self.fx = None               # the hit being animated in battle (see damage_fx)
        self.fallen = None           # last foe beaten, still shown while rewards are read out
        # co-op only
        self.color = color           # how the others see this hero's @
        self.state = 'active'        # 'active' | 'stairs' | 'dead' | 'gone'
        self.done = False            # has picked this turn's action
        self.fresh = None            # a battle not yet opened: 'ambush', 'appeared' or 'join'
        self.fighting = False        # inside the battle loop
        self.guarding = self.held = False   # how this battle round's blows land on the hero
        self.feed = []               # battle lines and hits still to be shown to this player
        self.replaying = False       # showing the feed right now
        self.fall = 0                # damage still to take from a trapdoor fall
        self.result = None           # ('died', reason) once fallen
        self.ending = False          # looking at the ending screens
        self.scored = False          # in the hall of fame already

    def __getstate__(self):
        state = dict(vars(self))
        state['scr'] = None
        return state
