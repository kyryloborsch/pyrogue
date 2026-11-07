"""The Game: it ties the mixins together and runs the turns, the monsters and the keyboard."""

import curses
import random
import threading
from collections import deque
from contextlib import contextmanager

from . import save, scores
from .actions import ActionsMixin
from .battle import BattleMixin
from .characters import BARD_BY
from .constants import (
    ARROW_CHORDS, ARROWS, CHORD_DELAY, CHORD_STEPS, CORRIDOR, DIRS, DOOR, FLOOR,
    KEYPAD_DIAGONALS, LOG_SIZE, MAP_H, MAP_W, NUMPAD, STAIRS, WALKABLE
)
from .dialogue import TalkMixin
from .dungeon import DungeonMixin
from .hero import Battle, Hero
from .inventory import ItemsMixin
from .items import Item, POTIONS, POTION_COLORS, SCROLLS, SYLLABLES, make_armor, make_weapon
from .monsters import FORGET_DIST, FORGET_TURNS, WANDER_OUT_CHANCE
from .player import xp_needed
from .ui import UIMixin
from .world import ENVIRONMENTS


def hero_field(name):
    """A field of the hero whose turn is being played, as if it belonged to the game."""
    return property(lambda game: getattr(game.hero, name),
                    lambda game, value: setattr(game.hero, name, value))


# what each hero has for themselves, which the old saves kept on the game
HERO_FIELDS = ('player', 'name', 'msgs', 'log', 'visible', 'battles', 'asleep', 'pending_key',
               'shown_hp', 'fx', 'fallen')


class Game(DungeonMixin, ActionsMixin, ItemsMixin, BattleMixin, TalkMixin, UIMixin):
    """One game, from depth 1 until the player wins, dies or quits."""

    def __init__(self, scr, name, seed=None):
        self.start([Hero(name, scr)], seed)

    def start(self, heroes, seed):
        """Set up a new run for these heroes."""
        self._ctx = threading.local()  # which hero this thread is playing for
        self.heroes = heroes
        # the run's seed: the same seed makes the same dungeon (and, played the same way,
        # the same run)
        self.seed = self.new_seed() if seed is None else str(seed)
        random.seed(self.seed)
        self.depth = 0
        self.turn = 0
        self.known = set()
        self.potion_look = dict(zip(POTIONS, random.sample(POTION_COLORS, len(POTIONS))))
        self.scroll_look = {s: self.random_title() for s in SCROLLS}
        self.game_over = None        # ('died', reason) | ('won',) | ('quit',) | ('saved',)
        self.npcs_met = set()        # kinds that have appeared; only merchants come back
        self.bard_depth = random.randint(2, BARD_BY)   # the bard turns up by this depth
        self.weak_known = set()      # monster names whose weak spot the party has found
        self.saved_depth = 0         # the depth last autosaved
        self.snapshot = None         # the game as it was at the start of this turn (bytes)
        self.traps = {}              # (x, y) -> Trap
        self.env = ENVIRONMENTS[0]   # the environment of the current level
        self.legend = set()          # map symbols seen so far (see LEGEND)
        self.floor_names = {}        # depth -> the name of that floor (a variant's, if it was one)

        for h in heroes:
            p = h.player
            p.weapon = make_weapon('mace', 1)
            p.armor = make_armor('ring mail', 1)
            p.pack = [p.weapon, p.armor, Item('food')]
        self.new_level()
        self.place_party()
        for h in heroes:
            with self.as_hero(h):
                self.msg(f'Welcome to the Dungeons of Doom, {h.name}! '
                         'Someone is waiting to talk to you (&).')
                self.record(f'This run\'s seed is {self.seed}.')

    @classmethod
    def restore(cls, scr, state):
        """A game picked up from a save."""
        game = cls.__new__(cls)
        game._ctx = threading.local()
        game.legend = set()          # saves from before the legend existed don't have one
        game.floor_names = {}        # nor floor names
        if 'heroes' not in state:    # saves from before co-op kept the hero on the game
            state = dict(state)
            hero = Hero(state['name'])
            for f in HERO_FIELDS:
                if f in state:
                    setattr(hero, f, state.pop(f))
            state.pop('foes', None)
            state['heroes'] = [hero]
        vars(game).update(state)
        if 'seed' not in state:      # nor a seed: the levels still to come get a new one
            game.seed = cls.new_seed()
            game.record(f'This run\'s seed is {game.seed}.')
        hero = game.heroes[0]
        hero.scr, hero.battle, hero.fallen, hero.fx, hero.view = scr, None, None, None, None
        game.snapshot = None
        game.msg(f'Welcome back, {game.name}! You are on depth {game.depth}.')
        return game

    # ------------------------------------------------------------- heroes
    @property
    def hero(self):
        """The hero whose turn is being played."""
        return getattr(self._ctx, 'hero', None) or self.heroes[0]

    @contextmanager
    def as_hero(self, hero):
        """Play for another hero for a while: self.player and the rest become theirs."""
        old = getattr(self._ctx, 'hero', None)
        self._ctx.hero = hero
        try:
            yield
        finally:
            self._ctx.hero = old

    @property
    def foes(self):
        """The monsters in the current battle; foes[0] is the target."""
        b = self.hero.battle
        return b.foes if b else []

    @foes.setter
    def foes(self, foes):
        self.hero.battle = Battle(foes, [self.hero]) if foes else None

    def party(self):
        """The heroes on the map."""
        return [h for h in self.heroes if h.state == 'active']

    def hero_at(self, x, y):
        return next((h for h in self.party() if (h.player.x, h.player.y) == (x, y)), None)

    def nearest_hero(self, x, y):
        """The hero on the map nearest to (x, y), and how many steps away."""
        return min(((h, max(abs(h.player.x - x), abs(h.player.y - y))) for h in self.party()),
                   key=lambda pair: pair[1], default=(None, None))

    def party_visible(self):
        """Every square some hero on the map can see."""
        heroes = self.party()
        if len(heroes) == 1:
            return heroes[0].visible
        return set().union(*(h.visible for h in heroes))

    def battle_of(self, m):
        """The battle a monster is in, if any."""
        return next((h.battle for h in self.heroes if h.battle and m in h.battle.foes), None)

    def place_party(self):
        """Put the other heroes on the free squares nearest the first one."""
        if len(self.party()) < 2:
            return
        lead, *others = self.party()
        start = (lead.player.x, lead.player.y)
        seen, q = {start}, deque([start])
        while q and others:
            x, y = q.popleft()
            if ((x, y) != start and not self.occupied(x, y) and not self.item_at(x, y)
                    and (x, y) not in self.traps and self.tiles[y][x] != STAIRS):
                h = others.pop(0)
                h.player.x, h.player.y = x, y
            for dx, dy in DIRS.values():
                n = (x + dx, y + dy)
                if n not in seen and self.walkable(*n):
                    seen.add(n)
                    q.append(n)
        for h in self.party():
            with self.as_hero(h):
                self.compute_fov()

    def pause(self, ms):
        """Hold an animation frame on screen for a moment."""
        curses.napms(ms)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def new_seed():
        """A seed for a run started without one: a random six-digit number."""
        return str(random.randrange(10 ** 5, 10 ** 6))

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
        return self.monster_at(x, y) or self.npc_at(x, y) or self.hero_at(x, y)

    def visible_monsters(self):
        return [m for m in self.monsters if (m.x, m.y) in self.visible]

    # -------------------------------------------------------------- turns
    def end_turn(self):
        if self.game_over:
            return
        self.monsters_act()
        if self.game_over:
            return
        self.npcs_act()
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
            if p.regen >= max(2, 18 - p.level - 3 * p.ring('regeneration')) and p.hp < p.max_hp:
                p.hp += 1
                p.regen = 0
            p.mana_regen += 1
            if p.mana_regen >= max(4, 12 - p.level // 2) and p.mp < p.max_mp:
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
        if p.paralyzed and not self.foes:  # a turn spent resting uses up the lost move too
            p.paralyzed = 0
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
            gain = random.randint(3, 8)
            p.max_hp += gain
            p.hp += gain
            p.max_mp += random.randint(2, 3)
            p.restore_mp()
            self.msg(f'{self.name} grew to level {p.level}!')

    # ------------------------------------------------------------ monsters
    def dist_map(self):
        """Steps from the nearest hero to every square within 30 of one."""
        dist = {(h.player.x, h.player.y): 0 for h in self.party()}
        q = deque(dist)
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
        if not self.party():
            return
        dist = self.dist_map()
        seen = self.party_visible()
        fighting = [h for h in self.party() if h.battle]
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
            if self.battle_of(m):
                continue
            h, near = self.nearest_hero(m.x, m.y)
            if h is None:
                return
            d = dist.get((m.x, m.y))
            if not m.awake:
                noise = any(max(abs(m.x - f.player.x), abs(m.y - f.player.y)) <= 7
                            for f in fighting)
                if ((m.x, m.y) in seen and random.random() < 0.3) or \
                        (noise and random.random() < 0.25):          # battle noise
                    m.alert()
                else:
                    if m.roaming and random.random() < 0.5:
                        self.wander(m)
                    continue
            if 'boss' in m.flags and near > 1:
                continue                 # bosses wait in their lair
            if (m.x, m.y) in seen or (d is not None and d <= FORGET_DIST):
                m.lost = 0
            else:
                m.lost += 1
                if m.lost >= FORGET_TURNS:
                    m.awake, m.roaming = False, True     # it has lost your trail
                    continue
            if 'erratic' in m.flags and random.random() < 0.5:
                self.monster_step(m, *random.choice(list(DIRS.values())))
                continue
            if near == 1:
                if h.battle:
                    h.battle.foes.append(m)
                    self.foe_joined(h, m)
                else:
                    self.ambush(h, m)
                continue
            if d is None:
                if random.random() < 0.5:
                    self.wander(m)
                continue
            steps = [(dx, dy) for dx, dy in DIRS.values()
                     if dist.get((m.x + dx, m.y + dy), 999) < d
                     and not self.occupied(m.x + dx, m.y + dy)]
            if steps:
                random.shuffle(steps)
                dx, dy = min(steps, key=lambda s: dist[(m.x + s[0], m.y + s[1])])
                m.x += dx
                m.y += dy

    def foe_joined(self, h, m):
        """A monster walked up to a hero's battle and joined it."""
        self.msg(f'A {self.called(m)} joined the battle!')

    def ambush(self, h, m):
        """A monster walked up to a hero and attacked."""
        self.battle(m, ambush=True)

    def npcs_act(self):
        """Friendly characters stroll about their room, but hold still while you're beside them."""
        for npc in self.npcs:
            _h, near = self.nearest_hero(npc.x, npc.y)
            if (near is not None and near <= 1) or random.random() < 0.7:
                continue
            dx, dy = random.choice(list(DIRS.values()))
            n = (npc.x + dx, npc.y + dy)
            if (n in npc.area and not self.occupied(*n) and not self.item_at(*n)
                    and n not in self.traps and self.can_block(*n, mover=npc)):
                npc.x, npc.y = n

    def can_block(self, x, y, mover=None):
        """Can a character stand at (x, y) without cutting off any part of the map? True when
        the open squares around it still connect to each other."""
        others = {(n.x, n.y) for n in self.npcs if n is not mover}
        ring = {(x + dx, y + dy) for dx, dy in DIRS.values()}
        free = {c for c in ring if self.walkable(*c) and c not in others}
        if not free:
            return True
        start = free.pop()
        group, q = {start}, [start]
        while q:
            cx, cy = q.pop()
            for c in [(cx + dx, cy + dy) for dx, dy in DIRS.values()]:
                if c in free and c not in group:
                    group.add(c)
                    q.append(c)
        return len(group) == len(free) + 1

    def wander(self, m):
        """A random step for a monster with nowhere in particular to go. One in a room
        rarely strays out of it into a corridor, so monsters mostly keep to the rooms."""
        dx, dy = random.choice(list(DIRS.values()))
        leaving = (self.tiles[m.y][m.x] == FLOOR
                   and self.tiles[m.y + dy][m.x + dx] in (DOOR, CORRIDOR))
        if not leaving or random.random() < WANDER_OUT_CHANCE:
            self.monster_step(m, dx, dy)

    def monster_step(self, m, dx, dy):
        nx, ny = m.x + dx, m.y + dy
        if self.walkable(nx, ny) and not self.occupied(nx, ny):
            m.x, m.y = nx, ny

    # --------------------------------------------------------------- input
    def read_key(self):
        """Read a map command. Two arrow keys pressed together step diagonally."""
        if self.pending_key is not None:
            k, self.pending_key = self.pending_key, None
            return k
        k = self.scr.getch()
        if k not in ARROWS:
            return k
        self.scr.timeout(CHORD_DELAY)
        try:
            k2 = self.scr.getch()
        finally:
            self.scr.timeout(-1)
        diagonal = ARROW_CHORDS.get(frozenset((ARROWS[k], ARROWS.get(k2))))
        if diagonal:
            return diagonal
        if k2 != -1:
            self.pending_key = k2
        return k

    def handle_key(self, k):
        """Perform a command. Returns True if it used up a turn."""
        ch = chr(k) if 0 < k < 256 else ''
        step = (ARROWS.get(k) or KEYPAD_DIAGONALS.get(k) or CHORD_STEPS.get(k)
                or NUMPAD.get(ch))
        if step:
            return self.player_move(*DIRS[step])
        if k == curses.KEY_B2:                        # the numpad's 5 with Num Lock off
            return True
        actions = {
            '>': self.descend, 'i': self.inventory,
        }
        if ch in actions:
            return actions[ch]()
        if ch in ('.', '5'):
            return True
        if ch == 's':
            return self.search()
        if ch == 'z':
            self.rest()
        elif ch == '?':
            self.full_screen(self.help_lines())
        elif ch in ('m', '\x10'):
            self.show_log()
        elif ch == 'Q':
            self.show()
            self.draw(['s) save and quit   a) abandon this run   Esc) keep playing'])
            k = self.scr.getch()
            if k == ord('s'):
                save.write(save.snapshot(self))
                self.game_over = ('saved',)
            elif k == ord('a') and self.confirm('Abandon this run and delete its save? (y/n)'):
                self.game_over = ('quit',)
        return False

    def play(self):
        while not self.game_over:
            new_depth = self.depth != self.saved_depth
            self.saved_depth = self.depth
            self.snapshot = save.snapshot(self)
            if new_depth:
                save.write(self.snapshot)            # autosave on reaching each new depth
            self.show()
            k = self.read_key()
            if k == curses.KEY_RESIZE:
                continue
            if self.handle_key(k):
                self.end_turn()
        if self.game_over[0] == 'saved':
            return
        save.delete()                    # one life: the run is over, and so is its save
        entry = scores.add(self)
        self.show()
        self.wait_key()
        self.ending_screen()
        self.full_screen(scores.table(scores.load(), mark=entry and entry['rank']))


# self.player, self.scr and the rest are the current hero's
for _field in HERO_FIELDS + ('scr',):
    setattr(Game, _field, hero_field(_field))
