"""Co-op: several heroes in one dungeon, each played over the network from their own
terminal.

Every hero is played on its own thread, and all of them share one lock: the game code runs
for one hero at a time. A hero's screen lets go of the lock while it waits for a key, so each
player can sit in their own menu while the others play on.

Nobody waits for anybody while exploring: every step a hero takes moves the dungeon on, but
only by a share of a turn. With three heroes on the map, the monsters take one step for every
three steps the heroes take between them. Battles still go round by round: a round ends once
every hero in that battle has acted, and then the foes strike back."""

import curses
import random
import threading

from . import save, scores
from .battle import BattleMixin
from .constants import DIRS, STAIRS
from .game import Game
from .hero import Battle
from .moves import DISABLING, MOVES
from .world import BOSSES

HERO_COLORS = ['cyan', 'magenta', 'green', 'red']   # how each hero looks to the others
# monsters are tougher for a bigger party: each hero past the first adds this much
HP_PER_HERO = 0.6                # of their HP
DMG_PER_HERO = 0.2               # of their damage
POWER_PER_HERO = 1               # to their chance to hit
# a foe fighting two or more heroes may strike them all at once with its special move
SPLASH_CHANCE = 0.25
BOSS_SPLASH_CHANCE = 0.4


class Stop(Exception):
    """Leave whatever this hero is doing and go back to the hero's main loop: the turn ended
    without them (they fell, went downstairs or were dragged into a battle), or the game is
    over."""


class Disconnected(Stop):
    """The player is gone: they left, or their connection dropped."""


class CoopGame(Game):
    """A game with several heroes, each on their own thread. cv is the condition (and lock)
    every thread plays under."""

    def __init__(self, heroes, seed, cv):
        self.cv = cv
        self.busy = False            # in the middle of a battle round, a turn or a new level
        self.clock = 0               # hero actions since the monsters last moved
        self.returning = {}          # a saved game's heroes not back yet: name -> where they were
        for h, color in zip(heroes, HERO_COLORS):
            h.color = color
        self.start(heroes, seed)
        self.toughen()

    # ------------------------------------------------------------- saving
    @classmethod
    def load(cls, state, dice, cv):
        """A co-op game picked up from its save. Every hero still standing waits for their
        player to join again (see rejoin)."""
        game = cls.__new__(cls)
        vars(game).update(state)
        random.setstate(dice)
        game.cv, game._ctx = cv, threading.local()
        game.busy, game.game_over, game.snapshot = False, None, None
        game.returning = {}
        for h in game.heroes:
            if h.state in ('active', 'stairs'):
                game.returning[h.name] = h.state
                h.state = 'gone'
            h.battle = h.fresh = h.fallen = h.fx = h.view = h.pending_key = None
            h.feed = []
            h.done = h.fighting = h.guarding = h.held = h.ending = False
        return game

    def resumable(self):
        """Can this run be picked up again? Not once it's won, or everyone has fallen."""
        return self.game_over != ('won',) and any(
            h.state != 'dead' and h.player.hp > 0 for h in self.heroes)

    def save_party(self):
        """Keep the run in the co-op save, or drop the save once the run is over for good."""
        if self.resumable():
            save.write(save.snapshot(self), save.coop_path())
        else:
            save.delete(save.coop_path())

    def toughen(self):
        """Make the monsters that are new on the level a match for the party."""
        n = max(1, sum(1 for h in self.heroes if h.state in ('active', 'stairs')))
        for m in self.monsters:
            if m.party:
                continue
            m.party = n
            m.hp = m.max_hp = round(m.max_hp * (1 + HP_PER_HERO * (n - 1)))
            m.dmg = tuple(max(1, round(d * (1 + DMG_PER_HERO * (n - 1)))) for d in m.dmg)
            m.power += POWER_PER_HERO * (n - 1)

    def pause(self, ms):
        """Hold an animation frame, letting the others play meanwhile."""
        self.scr.pause(ms)

    # ------------------------------------------------------------- turns
    def end_turn(self):
        """This hero has acted. Exploring, the dungeon moves on by a share of a turn right
        away. In battle, wait for the others in it to act, and for the foes to strike back."""
        h = self.hero
        self.check_out()
        b = h.battle
        if not b:
            self.tick_player()
            self.advance(1)
            self.compute_fov()
            self.changed()
            self.check_out()
            return
        rounds, shown = b.rounds, None
        h.done = True
        self.check_round(b)
        while b.rounds == rounds and h.battle is b and h.state == 'active' and not self.game_over:
            names = ', '.join(x.name for x in b.heroes if not x.done and x.state == 'active')
            if names != shown:
                shown = names
                self.draw_battle([f'Waiting for {names}...'])
            self.cv.wait()
            self.scr.flush()                 # what was typed while waiting isn't meant for now
            self.scr.check()
        self.check_out()

    def check_out(self):
        """Stop if this hero can't go on with what they were doing."""
        h = self.hero
        if self.game_over or h.state != 'active' or (h.battle and not h.fighting):
            raise Stop()

    def advance(self, actions):
        """Heroes took this many actions: the monsters move once per action of each hero on
        the map."""
        self.clock += actions
        while self.clock >= max(1, len(self.party())):
            self.clock -= max(1, len(self.party()))
            self.world_turn()

    def world_turn(self):
        """The monsters and the friendly characters take a step."""
        busy, self.busy = self.busy, True
        try:
            self.toughen()                       # anything an alarm or a boss called in
            self.monsters_act()
            self.npcs_act()
            self.turn += 1
            for h in self.party():
                with self.as_hero(h):
                    self.compute_fov()
        finally:
            self.busy = busy

    def changed(self):
        """Something moved: every player's map should show it."""
        for h in self.heroes:
            if h.scr:
                h.scr.stale = True
        self.cv.notify_all()

    def check_round(self, b):
        """End a battle round once everyone in it has acted: the foes strike back, and each
        hero's round counts as an action that moves the dungeon on."""
        heroes = [h for h in b.heroes if h.state == 'active']
        if self.busy or not heroes or not all(h.done for h in heroes):
            return
        self.busy = True
        try:
            for h in heroes:
                h.done = False
            if b.foes:
                self.battle_round(b)
            for h in heroes:
                if h.state == 'active':
                    with self.as_hero(h):
                        hp = h.player.hp
                        self.tick_player()
                        if h.battle and h.player.hp < hp:          # burns, or starving
                            self.damage_fx('player', hp - h.player.hp)
            b.rounds += 1
            self.advance(len(heroes))
        finally:
            self.busy = False
        self.check_state()
        self.changed()

    def check_state(self):
        """Regroup the party once all are on the stairs, and end the game once nobody is
        left."""
        if self.busy:
            return
        living = [h for h in self.heroes if h.state in ('active', 'stairs')]
        if living and all(h.state == 'stairs' for h in living):
            self.regroup(living)
        if not living and not self.game_over:
            fallen = [h for h in self.heroes if h.result]
            self.game_over = fallen[-1].result if fallen else ('quit',)
        self.changed()

    def rest(self):
        """Rest a turn at a time, letting the others see the dungeon go by. Any key stops."""
        p = self.player
        if self.visible_monsters():
            self.msg('You cannot rest with monsters nearby!')
            return
        for _ in range(500):
            if (p.hp >= p.max_hp and p.mp >= p.max_mp) or self.msgs or self.visible_monsters():
                break
            self.end_turn()
            self.draw(['Resting... (press any key to stop)'])
            self.scr.timeout(60)
            try:
                if self.scr.getch() not in (-1, curses.KEY_RESIZE):
                    break
            finally:
                self.scr.timeout(-1)

    def die(self, reason):
        h = self.hero
        h.player.hp = 0
        if h.state not in ('active', 'stairs'):
            return
        h.state, h.result, h.done = 'dead', ('died', reason), False
        if h.battle:
            self.say(f'{h.name} fainted...')
        self.leave_battle(h, quiet=True)
        self.broadcast(f'{h.name} has fallen, killed by {reason}.', skip=h)
        self.check_state()

    def broadcast(self, text, skip=None):
        """Party news, for every hero but skip."""
        for h in self.heroes:
            if h is not skip and h.state != 'gone':
                with self.as_hero(h):
                    self.msg(text)

    # -------------------------------------------------------------- stairs
    def descend(self):
        if self.tiles[self.player.y][self.player.x] != STAIRS:
            return super().descend()
        self.to_stairs(f'{self.name} went down the stairs.')
        return False

    def fall_through(self):
        self.hero.fall = random.randint(2, 8) + (self.depth + 1) // 3
        self.player.x = self.player.y = -1
        self.to_stairs(f'{self.name} fell through a trapdoor!')

    def to_stairs(self, news):
        """Leave the map and wait for the party below."""
        h = self.hero
        self.leave_battle(h)                     # pulled into one on the way down
        h.state, h.done = 'stairs', False
        self.broadcast(news, skip=h)
        if any(x.state == 'active' for x in self.heroes):
            self.msg('You wait for the others at the bottom of the stairs.')
        self.check_state()

    def regroup(self, heroes):
        """Everyone is on the stairs: the party arrives on the next depth together."""
        self.busy = True
        try:
            heroes[0].state = 'active'          # the others join once the level is built
            with self.as_hero(heroes[0]):
                self.new_level()
            for h in heroes:
                h.state, h.done = 'active', False
            self.toughen()
            self.place_party()
            for h in heroes:
                with self.as_hero(h):
                    if h.fall:
                        self.hurt(h.fall, 'a fall')
                        h.fall = 0
                    self.arrive()
            self.returning = {}                 # where the missing stood is on the old depth
        finally:
            self.busy = False
        self.check_state()
        if not self.game_over:
            self.save_party()

    def rejoin(self, h):
        """A player who dropped out takes their hero back, next to someone still playing.
        A hero from a saved game comes back where they stood."""
        p = h.player
        if p.hp <= 0:
            h.state = 'dead'
            return
        was = self.returning.pop(h.name, None)
        if was == 'stairs':
            h.state = 'stairs'
            self.check_state()
            return
        if was != 'active' or not self.walkable(p.x, p.y) or self.occupied(p.x, p.y):
            friend = next(iter(self.party()), None)
            if friend is None:
                h.state = 'stairs'
                self.check_state()
                return
            p.x, p.y = friend.player.x, friend.player.y
            spots = [(friend.player.x + dx, friend.player.y + dy) for dx, dy in DIRS.values()]
            spots = [s for s in spots if self.walkable(*s) and not self.occupied(*s)]
            if spots:
                p.x, p.y = random.choice(spots)
        h.state, h.done = 'active', False
        with self.as_hero(h):
            self.compute_fov()
            self.msg(f'Welcome back, {h.name}! You are on depth {self.depth}.')
        self.broadcast(f'{h.name} is back.', skip=h)
        self.changed()

    def leave(self, h):
        """The player left or lost their connection. A hero who is still standing waits
        to be taken back (see rejoin)."""
        if h.state == 'dead' and not h.scored:
            with self.as_hero(h):
                self.add_score(h.result)
        if h.state in ('active', 'stairs'):
            self.leave_battle(h)
            h.state, h.done = 'gone', False
            self.broadcast(f'{h.name} left the game.', skip=h)
        h.scr = None
        self.check_state()

    # ----------------------------------------------------- the hero's loop
    def hero_loop(self, h):
        """The thread body for one hero. Runs under the lock until the game is over or the
        player leaves."""
        self._ctx.hero = h
        try:
            while not self.game_over:
                try:
                    if h.state == 'stairs':
                        self.wait_screen(['You wait at the bottom of the stairs for the '
                                          'rest of the party...'])
                    elif h.state == 'dead':
                        self.wait_screen([f'You have fallen. You watch over the rest of the '
                                          f'party.  m: log  p: party  Q: leave'])
                    elif h.battle:
                        self.coop_battle()
                    else:
                        self.show()
                        h.scr.stale = False
                        h.scr.refreshable = True     # redraw whenever something moves
                        try:
                            k = self.read_key()
                        finally:
                            h.scr.refreshable = False
                        if k == curses.KEY_RESIZE or h.battle or h.state != 'active':
                            continue
                        if self.handle_key(k):
                            self.end_turn()
                except Disconnected:
                    raise
                except Stop:
                    continue
            self.cv.notify_all()             # wake the others: the run is over
            self.finish(h)
        except Disconnected:
            self.leave(h)

    def wait_screen(self, lines):
        """The map with a note on top, while there's nothing for this hero to do. A fallen
        hero watches a teammate's battle instead, while there is one."""
        friend = self.watched() if self.hero.state == 'dead' else None
        if friend:
            self.watch(friend)
        else:
            self.draw(lines)
        self.scr.timeout(500)
        self.scr.stale, self.scr.refreshable = False, True
        try:
            k = self.scr.getch()
        finally:
            self.scr.timeout(-1)
            self.scr.refreshable = False
        ch = chr(k) if 0 < k < 256 else ''
        if ch in ('m', 'p', 'Q'):
            self.handle_key(k)
        elif ch == 'n' and friend:                   # watch the next teammate's battle
            friends = self.fighting_friends()
            self._ctx.watching = friends[(friends.index(friend) + 1) % len(friends)].name

    # ------------------------------------------------------------ watching
    @property
    def scr(self):
        """The screen being drawn on: this hero's own, even while drawing another's battle
        for them to watch."""
        return getattr(self._ctx, 'screen', None) or self.hero.scr

    @scr.setter
    def scr(self, value):
        self.hero.scr = value

    def fighting_friends(self):
        return [h for h in self.party() if h.battle and h.battle.foes]

    def watched(self):
        """The teammate whose battle a fallen hero is watching, if anyone is fighting."""
        friends = self.fighting_friends()
        if not friends:
            return None
        name = getattr(self._ctx, 'watching', None)
        friend = next((h for h in friends if h.name == name), friends[0])
        self._ctx.watching = friend.name
        return friend

    def watch(self, friend):
        """Show this hero friend's battle, as friend sees it, with their latest battle line."""
        fx, self._ctx.screen = friend.fx, self.scr
        more = '  n: next battle' if len(self.fighting_friends()) > 1 else ''
        try:
            with self.as_hero(friend):
                self.fx = dict(fx) if fx else None     # drawing moves its number up a step
                last = self.log[-1][2] if self.log else ''
                self.draw_battle([last[:74], f'Watching {friend.name}.{more}  m: log  '
                                             f'p: party  Q: leave'])
        finally:
            friend.fx, self._ctx.screen = fx, None

    def handle_key(self, k):
        ch = chr(k) if 0 < k < 256 else ''
        if ch == 'Q':
            self.show()
            if self.confirm('Leave this game for good? (y/n)'):
                self.scr.bye('You left the game.')
                raise Disconnected()
            return False
        if ch == 'p':
            self.full_screen(self.party_screen())
            return False
        if self.hero.state != 'active':
            if ch == 'm':
                self.show_log()
            return False
        return super().handle_key(k)

    def finish(self, h):
        """The run is over: this hero's ending, then the hall of fame."""
        h.ending = True
        over = h.result or self.game_over
        entry = self.add_score(over)
        try:
            self.show()
            self.wait_key()
            self.ending_screen(over)
            self.full_screen(scores.table(scores.load(), mark=entry and entry['rank']))
            self.scr.bye('Thanks for playing!')
        except Disconnected:
            pass

    def add_score(self, over):
        h = self.hero
        if h.scored:
            return None
        h.scored = True
        return scores.add(self, over)

    # ------------------------------------------------------------- the panel
    STATES = {'stairs': 'on the stairs', 'dead': 'fallen', 'gone': 'left'}

    def hero_state(self, h):
        if h.state != 'active':
            return self.STATES[h.state]
        return 'fighting' if h.battle else 'exploring'

    def party_lines(self, width):
        lines = []
        for h in self.heroes:
            p = h.player
            text = f'{h.name[:12]:<12} HP {p.hp:>3}/{p.max_hp:<3} L{p.level:<2} {self.hero_state(h)}'
            attr = curses.A_BOLD if h is self.hero else 0
            lines.append((text[:width], attr))
        return lines

    def party_screen(self):
        lines = ['THE PARTY', '']
        for h in self.heroes:
            p = h.player
            lines.append(f'  {h.name[:18]:<18} level {p.level:<2}  HP {p.hp}/{p.max_hp}  '
                         f'MP {p.mp}/{p.max_mp}  gold {p.gold}  {self.hero_state(h)}')
        return lines + ['', f'  Depth {self.depth}, turn {self.turn}, seed {self.seed}.']

    # -------------------------------------------------------------- battles
    def battle(self, m, ambush=False):
        """Bumping into a monster: join the battle it's in, or start one."""
        h = self.hero
        b = self.battle_of(m)
        if b:
            self.join_battle(h, b, 'join')
        else:
            self.start_battle(h, m, 'appeared')
        self.coop_battle()

    def ambush(self, h, m):
        self.start_battle(h, m, 'ambush')
        h.scr.poke()

    def start_battle(self, h, m, how):
        m.awake = True
        h.battle, h.fresh, h.fallen = Battle([m], [h]), how, m
        h.battles += 1
        for o in self.party():                       # friends beside the fight join in
            if o is not h and not o.battle and any(
                    max(abs(o.player.x - x), abs(o.player.y - y)) <= 1
                    for x, y in ((h.player.x, h.player.y), (m.x, m.y))):
                self.join_battle(o, h.battle, 'join')
                o.scr.poke()

    def join_battle(self, h, b, how):
        h.battle, h.fresh, h.fallen = b, how, b.foes[0]
        h.battles += 1
        with self.as_hero(b.heroes[0]):
            self.say(f'{h.name.upper()} joined the battle!')
        b.heroes.append(h)

    def leave_battle(self, h, escaped=False, quiet=False):
        """Take a hero out of their battle. The foes are stunned only if the last hero
        escaped from them."""
        b = h.battle
        if not b:
            return
        h.battle, h.fresh, h.done = None, None, False
        b.heroes.remove(h)
        if b.heroes and not quiet:
            with self.as_hero(b.heroes[0]):
                self.say(f'{h.name.upper()} left the battle!')
        if b.heroes:
            self.check_round(b)                  # the rest may have been waiting on them
        elif escaped:
            for f in b.foes:
                f.stun = 4
                f.status = {}

    def foe_attack(self, m, guarding, held=False, splash=False):
        """Against two or more heroes, a foe sometimes uses its special move on them all."""
        b = self.hero.battle
        heroes = [h for h in b.heroes if h.state == 'active'] if b else []
        chance = BOSS_SPLASH_CHANCE if 'boss' in m.flags else SPLASH_CHANCE
        if splash or len(heroes) < 2 or random.random() >= chance:
            return super().foe_attack(m, guarding, held, splash)
        self.say(f'The {self.called(m)} used {m.moves[1]}! It hits the whole party!')
        for h in heroes:
            if h.state == 'active':
                with self.as_hero(h):
                    super().foe_attack(m, h.guarding, h.held, splash=True)

    def foe_joined(self, h, m):
        with self.as_hero(h):
            self.say(f'A {self.called(m)} joined the battle!')

    def battle_round(self, b):
        """The foes' turn in a battle, once its heroes have acted: each strikes one of them."""
        self.toughen()
        for f in list(b.foes):
            heroes = [h for h in b.heroes if h.state == 'active']
            if not heroes:
                break
            if f.hp <= 0 or f not in b.foes:
                continue
            h = self.next_target(b, heroes)
            with self.as_hero(h):
                self.foe_turn(f, h.guarding, h.held)
        for h in b.heroes:
            h.guarding = h.held = False
        if b.heroes:
            with self.as_hero(b.heroes[0]):
                self.clear_fainted()

    def next_target(self, b, heroes):
        """The hero a foe strikes next. Blows are dealt out in a shuffled order, so every
        hero in the fight takes as many as the others."""
        b.targets = [h for h in b.targets if h in heroes]
        if not b.targets:
            b.targets = random.sample(heroes, len(heroes))
        return b.targets.pop()

    def coop_battle(self):
        """This hero's side of a battle: pick a move each round, then wait for the foes."""
        h = self.hero
        b = h.battle
        h.fighting = True
        outcome = None
        try:
            caught = self.open_battle(h)
            while h.battle is b and b.foes:
                self.play_feed()
                if h.battle is not b or not b.foes:
                    break
                if h.state != 'active':
                    raise Stop()
                guarding = False
                held = caught or self.player_held()
                caught = False
                self.play_feed()
                if h.state != 'active':
                    raise Stop()
                if not held:
                    guarding, outcome = self.battle_choice(b)
                    if guarding is None:            # backed out to the event log and so on
                        continue
                self.play_feed()
                if h.battle is b:
                    self.clear_fainted()
                    self.play_feed()
                    h.guarding, h.held = guarding, held
                self.end_turn()
            self.play_feed()
            if h.battle is b and not b.foes:
                outcome = 'You won the battle!'
        finally:
            h.fighting = False
            h.feed = []
        if h.battle is b:
            self.leave_battle(h)
        self.compute_fov()
        if outcome:
            self.msg(outcome)

    def open_battle(self, h):
        """Show the start of a battle this hero hasn't seen yet. True if they were caught
        asleep, and lose their first move."""
        how, h.fresh = h.fresh, None
        if not how or not self.foe:         # nothing new, or it was over before they got there
            return False
        m = self.foe
        if how == 'join':
            intro = f'{self.name} joined the battle against the {self.called(m)}!'
        elif 'boss' in m.flags:
            intro = f'BOSS BATTLE! The {m.name.upper()} blocks the way!'
        else:
            intro = f'A {self.called(m)} {"attacked" if how == "ambush" else "appeared"}!'
        if self.msgs:
            self.show_pending()
        self.shown_hp = [m.hp, self.player.hp]
        self.battle_transition()
        BattleMixin.say(self, intro)
        caught, h.asleep = h.asleep, False
        if caught:
            BattleMixin.say(self, f'{self.name} was caught asleep!')
        return caught

    def battle_choice(self, b):
        """Pick and do this round's action. Returns (guarding, outcome), with guarding None
        when nothing was done yet."""
        h, p = self.hero, self.player
        m = self.foe or self.fallen
        choice = self.battle_menu()
        if not b.foes or h.battle is not b:               # won by the others meanwhile
            return None, None
        if choice == 0:                                   # FIGHT
            mv = self.fight_menu()
            if mv is None:
                return None, None
            if MOVES[mv]['mp'] > p.mp:
                self.say(f'Not enough MP! {mv} costs {MOVES[mv]["mp"]} MP.', log=False)
                return None, None
            part = self.aim_menu(m, mv) if 'mult' in MOVES[mv] else None
            if 'mult' in MOVES[mv] and not part:
                return None, None
            self.use_move(m, mv, part=part)
        elif choice == 1:                                 # BAG
            if not self.inventory(in_battle=True):
                return None, None
            self.play_feed()
            if all(max(abs(f.x - p.x), abs(f.y - p.y)) > 1 for f in b.foes):
                self.say(f'{self.name} vanished from the battle!')
                self.leave_battle(h, escaped=True)
                return False, 'You escaped from the battle.'
        elif choice == 2:                                 # GUARD
            self.say(f'{self.name} braced for the attack!')
            return True, None
        elif choice == 3:                                 # RUN
            boss = next((f for f in b.foes if 'boss' in f.flags), None)
            if boss:
                self.say(f'There is no running from the {boss.name.upper()}!', log=False)
                return None, None
            lvl = max(f.level for f in b.foes)
            chance = min(0.8, max(0.1, 0.4 + 0.07 * (p.level - lvl) - 0.1 * (len(b.foes) - 1)))
            if all(any(s in f.status for s in DISABLING) for f in b.foes):
                chance = 1
            if random.random() < chance:
                self.say(f'{self.name} got away safely!')
                self.play_feed()
                self.leave_battle(h, escaped=True)
                return False, 'You escaped from the battle.'
            self.say("Can't escape!")
        elif choice == 5:                                 # event log
            self.show_log()
            return None, None
        else:
            return None, None
        return False, None

    # ------------------------------------------------- what the party sees
    def replaying(self):
        """Is this thread showing its player their feed (play_feed)? It's the thread that
        counts, not the hero: another hero's thread may be acting for this one meanwhile, and
        must not draw on their screen or wait for their keys."""
        return getattr(self._ctx, 'replaying', False)

    def say(self, text, log=True):
        """A battle line, for everyone in the battle (or just this hero if log is False). It
        shows when each player's own thread gets to it (play_feed)."""
        h = self.hero
        if self.replaying():
            return super().say(text, log)
        if not h.battle:
            if log:
                self.msg(text)
            return
        for x in (h.battle.heroes if log else [h]):
            if log:
                with self.as_hero(x):
                    self.record(text)
            x.feed.append(('say', text, h, self.hp_now()))

    def hp_now(self):
        """The battle as it stands: (foe, its HP, each hero's HP). The feed keeps this with
        each line, so the bars a player sees match the line they're reading."""
        m = self.foe or self.fallen
        return m, m.hp if m else 0, {x: x.player.hp for x in self.hero.battle.heroes}

    def damage_fx(self, who, dmg, color='red', note=''):
        h = self.hero
        if self.replaying():
            return super().damage_fx(who, dmg, color, note)
        if h.battle:
            for x in ([h] if who == 'player' else h.battle.heroes):
                x.feed.append(('fx', who, dmg, color, note, self.hp_now()))

    def animate_hp(self):
        h = self.hero
        if self.replaying():
            if h.view:
                _, hp, heroes = h.view
                return super().animate_hp([hp, heroes.get(h, self.player.hp)])
            return super().animate_hp()
        if h.battle:
            for x in h.battle.heroes:
                x.feed.append(('hp', self.hp_now()))

    def play_feed(self):
        """Show this player what happened in their battle since they last looked."""
        h = self.hero
        h.feed += [('say', t, h, None) for t in h.msgs]
        h.msgs = []
        if not (self.foe or self.fallen):
            h.feed = []
            return
        self._ctx.replaying = True
        try:
            while h.feed:
                kind, *args, view = h.feed.pop(0)
                if view:
                    if h.view and view[0] is not h.view[0]:      # a new foe to look at
                        self.shown_hp[0] = view[1]
                    h.view = view
                if kind == 'say':
                    text, who = args
                    if who is not h and text.startswith(('You ', 'Your ')):
                        text = f'{who.name.upper()}: {text}'
                    BattleMixin.say(self, text, log=False)
                elif kind == 'fx':
                    BattleMixin.damage_fx(self, *args)
                else:
                    self.animate_hp()
        finally:
            self._ctx.replaying = False
            h.view = None
        if self.foe:
            self.shown_hp = [self.foe.hp, self.player.hp]

    def throw_potion(self, it):
        if not self.foe:                # someone else won the battle while you chose
            return False
        return super().throw_potion(it)

    def drop_foe(self, m):
        b = self.hero.battle
        if m in self.monsters:
            self.monsters.remove(m)
        if m in b.foes:
            b.foes.remove(m)
        for x in b.heroes:
            x.fallen = m

    def share_xp(self, m):
        """Everyone in the battle gains the EXP; the gold goes to whoever struck it down."""
        for x in list(self.hero.battle.heroes):
            with self.as_hero(x):
                self.say(f'{self.name} gained {m.xp} EXP. Points!')
                self.gain_xp(m.xp)
                for t in self.msgs:
                    self.say(t, log=False)
                self.msgs = []

    def reward(self, m):
        super().reward(m)
        if 'boss' in m.flags:                  # news for those who weren't in the fight
            fighters = self.hero.battle.heroes
            for x in self.heroes:
                if x not in fighters and x.state != 'gone':
                    with self.as_hero(x):
                        self.msg(BOSSES[m.name]['defeat'])
