"""Pokemon-style battles: moves, aimed blows, statuses, bosses and the battle screen."""

import curses
import math
import random
import textwrap

from .constants import DIRS, FINAL_DEPTH, STAIRS
from .items import Item
from .monsters import MONSTERS, Monster, PARTS, WEAK_SPOT_MULT
from .moves import EFFECTIVENESS, MOVES, STATUSES, move_notes
from .player import xp_needed
from .sprites import SPRITES
from .text import COLORS, an
from .world import BOSSES


class BattleMixin:
    """Pokemon-style battles: moves, aimed blows, statuses, bosses and the battle screen."""

    @property
    def foe(self):
        """The monster we're currently targeting in battle."""
        return self.foes[0] if self.foes else None

    @staticmethod
    def called(m):
        """How battle text names a monster: 'wild RAT', or just 'BONE KING' for a boss."""
        return m.name.upper() if 'boss' in m.flags else f'wild {m.name.upper()}'

    def battle(self, m, ambush=False):
        p = self.player
        m.awake = True
        self.foes = [m]
        self.battles += 1
        caught, self.asleep = self.asleep, False
        if 'boss' in m.flags:
            intro = f'BOSS BATTLE! The {m.name.upper()} blocks the way!'
        else:
            intro = f'A wild {m.name.upper()} {"attacked" if ambush else "appeared"}!'
        if self.auto_skip and not caught and self.easy_win():
            if self.skip_battle(quiet=True):
                self.end_battle(None)
                return
            intro = None              # someone joined and the fight got serious
        self.shown_hp = [self.foe.hp, p.hp]
        self.battle_transition()
        if intro:
            self.say(intro)
        self.flush_battle_msgs()
        if caught:
            self.say(f'{self.name} was caught asleep!')
            self.foes_attack(False)
            self.flush_battle_msgs()
        skippable = self.easy_win()   # only fights that start out easy can be skipped
        outcome = None
        while self.foes and not self.game_over:
            m = self.foe
            guarding = False
            held = self.player_held()
            choice = None if held else self.battle_menu(skippable)
            if held:                                          # lost the turn to a status
                if self.game_over:
                    break
            elif choice == 0:                                 # FIGHT
                mv = self.fight_menu()
                if mv is None:
                    continue
                if MOVES[mv]['mp'] > p.mp:
                    self.say(f'Not enough MP! {mv} costs {MOVES[mv]["mp"]} MP.', log=False)
                    continue
                part = self.aim_menu(m, mv) if 'mult' in MOVES[mv] else None
                if 'mult' in MOVES[mv] and not part:
                    continue
                self.use_move(m, mv, part=part)
            elif choice == 1:                                 # BAG
                it = self.choose('use', lambda i: i.kind in ('potion', 'scroll', 'food'))
                if not it:
                    self.flush_battle_msgs()
                    continue
                {'potion': self.drink, 'scroll': self.read_scroll, 'food': self.eat_food}[it.kind](it)
                self.animate_hp()
                self.flush_battle_msgs()
                if all(max(abs(f.x - p.x), abs(f.y - p.y)) > 1 for f in self.foes):
                    self.say(f'{self.name} vanished from the battle!')
                    outcome = self.escape()
                    break
            elif choice == 2:                                 # GUARD
                guarding = True
                self.say(f'{self.name} braced for the attack!')
            elif choice == 3:                                 # RUN
                boss = next((f for f in self.foes if 'boss' in f.flags), None)
                if boss:
                    self.say(f'There is no running from the {boss.name.upper()}!')
                    continue
                lvl = max(f.level for f in self.foes)
                chance = min(0.8, max(0.1, 0.4 + 0.07 * (p.level - lvl) - 0.1 * (len(self.foes) - 1)))
                if random.random() < chance:
                    self.say('Got away safely!')
                    outcome = self.escape()
                    break
                self.say("Can't escape!")
            elif choice == 4:                                 # SKIP (easy win)
                if self.skip_battle():
                    break
                skippable = False
                continue
            elif choice == 5:                                 # event log
                self.show_log()
                continue
            else:
                continue

            if self.clear_fainted():          # the target, or every foe a spell hit
                break
            self.foes_attack(guarding)
            if self.game_over or self.clear_fainted():
                break
            self.battle_world_turn()
            self.animate_hp()
            self.flush_battle_msgs()
        if self.game_over and self.game_over[0] == 'died':
            self.say(f'{self.name} fainted...')
        elif not self.foes and not self.game_over:
            outcome = 'You won the battle!'
        self.end_battle(outcome)

    def end_battle(self, outcome):
        self.foes = []
        self.compute_fov()
        if outcome:
            self.msg(outcome)

    def escape(self):
        for f in self.foes:
            f.stun = 4
            f.status = {}
        return 'You escaped from the battle.'

    def player_held(self):
        """Statuses that can cost the player their turn. True if the turn is lost."""
        p = self.player
        if p.frozen:
            p.frozen -= 1
            self.say(f'{self.name} is frozen solid!')
        elif p.paralyzed and random.random() < 0.3:
            self.say(f"{self.name} is paralyzed! {self.name} can't move!")
        elif p.confused and random.random() < 1 / 3:
            self.say(f'{self.name} is confused! {self.name} stumbled and got hurt!')
            self.hurt(random.randint(1, 4) + p.level // 2, 'confusion')
            self.animate_hp()
        else:
            return False
        return True

    def clear_fainted(self):
        """Reward and remove foes that have fainted. True if none are left."""
        target = self.foe
        for f in [f for f in self.foes if f.hp <= 0]:
            self.win_battle(f)
        if self.foes and self.foe is not target:
            self.shown_hp[0] = self.foe.hp
            self.say(f'{self.name} turned to face the {self.called(self.foe)}!')
        return not self.foes

    def foes_attack(self, guarding, quiet=False):
        for f in list(self.foes):
            if f.hp > 0:
                self.foe_turn(f, guarding, quiet)
            if self.game_over:
                return

    def inflict(self, m, status, say):
        """Put a status on a monster unless it's immune. Returns True if it took hold."""
        immune = (status in m.status
                  or (status == 'burn' and ('burn' in m.flags or m.type == 'elemental'))
                  or (status == 'poison' and m.type in ('undead', 'elemental'))
                  or (status == 'freeze' and ('frost' in m.flags or 'boss' in m.flags))
                  or (status == 'sleep' and ('boss' in m.flags or m.type == 'undead'))
                  or (status == 'confuse' and ('boss' in m.flags or m.type == 'elemental')))
        if immune:
            return False
        _tag, turns, text = STATUSES[status]
        m.status[status] = random.randint(*turns)
        say(f'The {self.called(m)} {text}')
        return True

    def foe_held(self, m, say, quiet=False):
        """Sleep, freezing, paralysis and confusion can cost a monster its turn. True if
        it does."""
        who = f'The {self.called(m)}'
        for status, held, ends in (('sleep', 'is fast asleep.', 'woke up!'),
                                   ('freeze', 'is frozen solid!', 'thawed out!')):
            if status in m.status:
                if m.status[status] <= 0:
                    del m.status[status]
                    say(f'{who} {ends}')
                else:
                    m.status[status] -= 1
                    say(f'{who} {held}')
                    return True
        if 'paralyze' in m.status:
            m.status['paralyze'] -= 1
            if m.status['paralyze'] <= 0:
                del m.status['paralyze']
                say(f'{who} is no longer paralyzed.')
            elif random.random() < 0.3:
                say(f"{who} is paralyzed! It can't move!")
                return True
        if 'confuse' in m.status:
            m.status['confuse'] -= 1
            if m.status['confuse'] <= 0:
                del m.status['confuse']
                say(f'{who} snapped out of its confusion!')
            elif random.random() < 1 / 3:
                m.hp = max(0, m.hp - max(1, random.randint(*m.dmg) // 2))
                if not quiet:
                    self.animate_hp()
                say(f'{who} is confused! It hurt itself in its confusion!')
                return True
        return False

    def status_damage(self, m, say, quiet):
        """Burns and poison hurt a monster at the end of its turn."""
        for status, what in (('burn', 'its burn'), ('poison', 'poison')):
            if status not in m.status or m.hp <= 0:
                continue
            dmg = max(2, min(m.max_hp // (12 if status == 'burn' else 10), 3 + self.depth // 2))
            m.hp = max(0, m.hp - dmg)
            if not quiet:
                self.animate_hp()
            say(f'The {self.called(m)} was hurt by {what}!')
            m.status[status] -= 1
            if m.status[status] <= 0:
                del m.status[status]

    def boss_phase(self, m, say):
        """At half HP a boss changes tactics: it calls in minions or flies into a rage."""
        m.phased = True
        say(BOSSES[m.name]['phase_msg'])
        tactic, *minion = BOSSES[m.name]['phase']
        if tactic == 'enrage':
            m.flags.append('enraged')
            return
        p = self.player
        tpl = next(t for t in MONSTERS if t[1] == minion[0])
        spots = [(p.x + dx, p.y + dy) for dx, dy in DIRS.values()
                 if self.walkable(p.x + dx, p.y + dy) and not self.occupied(p.x + dx, p.y + dy)]
        for x, y in random.sample(spots, min(2, len(spots))):
            s = Monster(tpl, x, y, self.depth)
            s.awake = True
            self.monsters.append(s)
            self.foes.append(s)
            say(f'A {self.called(s)} joined the battle!')

    def battle_world_turn(self):
        """A battle round is a dungeon turn too: hunger ticks and other monsters close in."""
        self.tick_player()
        self.turn += 1
        self.monsters_act()

    @staticmethod
    def effectiveness(kind, m):
        eff = EFFECTIVENESS.get((kind, m.type), 1.0)
        if (kind == 'fire' and 'burn' in m.flags) or (kind == 'ice' and 'frost' in m.flags):
            eff = min(eff, 0.5)                # fire creatures shrug off fire, frost ones ice
        return eff

    def use_move(self, m, name, quiet=False, part=None):
        """part: the body part a physical move is aimed at (None hits wherever it lands)."""
        p = self.player
        info = MOVES[name]
        say = self.msg if quiet else self.say
        p.mp -= info['mp']
        if not quiet:
            self.say(f"{self.name} used {name} on the {self.called(m)}'s {part}!" if part else
                     f'{self.name} used {name}!')
        if 'heal' in info:
            p.hp = min(p.max_hp, p.hp + sum(random.randint(1, 8) for _ in range(info['heal']))
                       + 2 * p.level)
            p.cure()
            if not quiet:
                self.animate_hp()
            say(f'{self.name} was healed, and every ailment faded away!')
            return
        if 'barrier' in info:
            p.barrier = info['barrier']
            say(f'A shimmering barrier surrounds {self.name}!')
            return
        if 'mana' in info:
            gained = min(p.max_mp - p.mp, info['mana'] + p.level // 2)
            p.mp += gained
            say(f'{self.name} focused and recovered {gained} MP!' if gained else
                f'{self.name} focused, but is already brimming with mana.')
            return
        targets = list(self.foes) if info.get('all') else [m]
        for t in targets:
            self.hit_foe(t, info, say, quiet, many=len(targets) > 1, part=part)

    def hit_chance(self, m, info, part=None):
        acc = info['acc'] + self.player.level * 2 - m.ac * 3 + (PARTS[part][0] if part else 0)
        return max(0, min(100, acc))

    def hit_foe(self, m, info, say, quiet, many, part=None):
        """One target of an attacking move: roll to hit, deal damage and apply effects.
        many: the move hits several foes, so each one is named in the battle text."""
        p = self.player
        if random.randint(1, 100) > self.hit_chance(m, info, part):
            if not quiet:
                self.say(f'The {self.called(m)} avoided the attack!')
            return
        effect = info.get('effect')
        if 'mult' not in info and 'dice' not in info:          # pure status move
            if not self.inflict(m, effect[0], say):
                say('But it failed!')
            return
        weak = part is not None and part == m.weak
        if 'mult' in info:
            dmg = (random.randint(*p.weapon_dmg) + p.str_bonus) * info['mult']
            if part:
                dmg *= PARTS[part][1] * (WEAK_SPOT_MULT if weak else 1)
        else:
            dmg = (sum(random.randint(1, 6) for _ in range(info['dice'])) + p.level
                   + p.spell_power)
        eff = self.effectiveness(info['type'], m)
        crit = random.random() < 1 / 16
        dmg = max(1, int(dmg * eff * (1.5 if crit else 1)))
        m.hp = max(0, m.hp - dmg)
        if 'drain' in info:
            p.hp = min(p.max_hp, p.hp + max(1, int(dmg * info['drain'])))
        if not quiet:
            if m is self.foe:
                self.flash('enemy')
                self.animate_hp()
            notes = ['A critical hit!'] if crit else []
            if weak and m.name in self.weak_known:
                notes.append('A hit to its weak spot!')
            elif weak:
                notes.append(f"{self.name} found the {m.name.upper()}'s weak spot: its {part}!")
            if eff > 1:
                notes.append("It's super effective!")
            elif eff < 1:
                notes.append("It's not very effective...")
            if many:
                self.say(' '.join([f'The {self.called(m)} was hit!'] + notes))
            else:
                for note in notes:
                    self.say(note)
            if 'drain' in info:
                self.say(f'{self.name} drained the life from the {self.called(m)}!')
        if weak:
            self.weak_known.add(m.name)
        if m.hp <= 0:
            return
        if 'sleep' in m.status and random.random() < 1 / 3:
            del m.status['sleep']
            say(f'The {self.called(m)} woke up!')
        if info['type'] == 'fire' and 'freeze' in m.status:
            del m.status['freeze']
            say(f'The fire thawed out the {self.called(m)}!')
        if effect and random.randint(1, 100) <= effect[1]:
            self.inflict(m, effect[0], say)

    def foe_turn(self, m, guarding, quiet=False):
        say = self.msg if quiet else self.say     # quiet: only status effects get reported later
        if 'boss' in m.flags and not m.phased and m.hp <= m.max_hp // 2:
            self.boss_phase(m, say)
        if not self.foe_held(m, say, quiet):
            for _ in range(2 if 'enraged' in m.flags else 1):
                self.foe_attack(m, guarding, quiet)
                if self.game_over:
                    return
        self.status_damage(m, say, quiet)

    def foe_attack(self, m, guarding, quiet=False):
        p = self.player
        say = self.msg if quiet else self.say
        special = random.random() < 0.3
        if not quiet:
            self.say(f'The {self.called(m)} used {m.moves[1] if special else m.moves[0]}!')
        if random.randint(1, 20) + m.power < 10 + p.ac:
            if not quiet:
                self.say('But it missed!' if random.random() < 0.5 else 'It glanced off your armor!')
            return
        dmg = random.randint(*m.dmg)
        if special:
            dmg = int(dmg * 1.5)
        if guarding:
            dmg = max(1, dmg // 2)
        if p.barrier:
            dmg = max(1, dmg // 2)
        p.hp = max(0, p.hp - dmg)
        if not quiet:
            self.flash('player')
            self.animate_hp()
        if guarding:
            self.say('Your guard softened the blow!')
        if special and 'poison' in m.flags and p.str > 3:
            p.str -= 1
            say('You were poisoned! You feel weaker.')
        if special and 'drain' in m.flags and p.max_hp > 5:
            p.max_hp -= random.randint(1, 3)
            p.hp = min(p.hp, p.max_hp)
            say('You feel your life force draining away!')
        if special and 'burn' in m.flags and not p.burn:
            p.burn = random.randint(3, 5)
            say('You were burned!')
        if special and 'frost' in m.flags:
            if random.random() < 0.3 and not p.frozen:
                p.frozen = 1
                say('You were frozen solid!')
            else:
                p.hp = max(0, p.hp - random.randint(2, 5))
                say('You were chilled to the bone!')
        if special and 'paralyze' in m.flags and not p.paralyzed:
            p.paralyzed = random.randint(4, 6)
            say('You are paralyzed! You may be unable to move!')
        if special and 'confuse' in m.flags and not p.confused:
            p.confused = random.randint(3, 6)
            say('You became confused!')
        if p.hp <= 0:
            self.die(an(m.name))

    def easy_win(self):
        """True if STRIKE alone beats every foe even with bad rolls and each one hitting
        hard every round until it falls."""
        p = self.player
        lo = p.weapon_dmg[0]
        elapsed = worst = 0
        for m in self.foes:
            if 'boss' in m.flags:
                return False
            eff = EFFECTIVENESS.get(('normal', m.type), 1.0)
            min_dmg = max(1, int((lo + p.str_bonus) * eff))
            hit = min(100, MOVES['STRIKE']['acc'] + p.level * 2 - m.ac * 3) / 100
            if hit <= 0.5:
                return False
            worst_hit = (int(m.dmg[1] * 1.5) + (3 if 'drain' in m.flags else 0)
                         + (5 if 'burn' in m.flags or 'frost' in m.flags else 0))
            if min_dmg >= m.hp:        # one STRIKE ends it (we still allow for one miss)
                elapsed += 1
            else:                      # pessimistic, with misses
                elapsed += math.ceil(math.ceil(m.hp / min_dmg) / hit) + 1
            worst += worst_hit * elapsed
        return worst < p.hp

    def skip_battle(self, quiet=False):
        """Resolve the fight instantly with STRIKEs, no animations. Returns False if it
        had to stop because a monster joined and the win was no longer obvious.
        quiet: report on the map instead of the battle screen (auto-skip)."""
        p = self.player
        hp_before, rounds, beaten = p.hp, 0, []
        finished = True
        while self.foes and not self.game_over:
            rounds += 1
            m = self.foe
            self.use_move(m, 'STRIKE', quiet=True)
            if m.hp <= 0:
                self.drop_foe(m)
                beaten.append(m)
                if not self.foes:
                    break
            self.foes_attack(False, quiet=True)
            if self.game_over:
                break
            for f in [f for f in self.foes if f.hp <= 0]:     # burns and poison
                self.drop_foe(f)
                beaten.append(f)
            if not self.foes:
                break
            n = len(self.foes)
            self.battle_world_turn()
            if len(self.foes) > n and not self.easy_win():
                finished = False
                break
        self.shown_hp = [self.foe.hp if self.foe else 0, p.hp]
        lost = hp_before - p.hp
        how = f'losing {lost} HP' if lost > 0 else 'unscathed'
        n_rounds = f'{rounds} round{"s" if rounds != 1 else ""}'
        names = ' and '.join(m.name for m in beaten)
        if quiet:
            self.msg(f'You beat the {names} in {n_rounds}, {how}.' if finished else
                     f'You fought for {n_rounds}, {how}, but now the battle is getting serious!')
        elif finished:
            self.say(f'{self.name} made short work of the wild {names.upper()} in {n_rounds}'
                     + (f', losing {lost} HP.' if lost > 0 else ' without a scratch!'))
        else:
            self.say(f'{self.name} fought for {n_rounds}, {how}... '
                     'but now the battle is getting serious!')
        for m in beaten:
            self.reward(m, quiet)
        if not quiet:
            self.flush_battle_msgs()
        return finished

    def drop_foe(self, m):
        self.monsters.remove(m)
        self.foes.remove(m)
        self.fallen = m              # keeps the battle screen drawable after the last foe

    def win_battle(self, m, quiet=False):
        self.reward(m, quiet)
        self.drop_foe(m)

    def reward(self, m, quiet=False):
        p = self.player
        gold = random.randint(0, m.xp // 4)
        p.gold += gold
        if quiet:
            self.msg(f'+{m.xp} exp' + (f', +{gold} gold.' if gold else '.'))
            self.gain_xp(m.xp)
        else:
            self.say(f'The {self.called(m)} fainted!')
            self.say(f'{self.name} gained {m.xp} EXP. Points!')
            self.gain_xp(m.xp)
            self.flush_battle_msgs()
            if gold:
                self.say(f'{self.name} picked up {gold} gold from the battle.')
        if 'boss' in m.flags:
            (self.msg if quiet else self.say)(BOSSES[m.name]['defeat'])
            if self.depth < FINAL_DEPTH:
                self.tiles[m.y][m.x] = STAIRS
                it = self.spell_scroll()
                it.x, it.y = m.x, m.y
                self.items.append(it)
                (self.msg if quiet else self.say)(
                    f'The {m.name.upper()} left behind {self.item_name(it)}!')
            else:
                it = Item('amulet')
                it.x, it.y = m.x, m.y
                self.items.append(it)
        elif random.random() < 0.2 and not self.item_at(m.x, m.y):
            it = self.random_item()
            it.x, it.y = m.x, m.y
            self.items.append(it)
            (self.msg if quiet else self.say)(f'The {m.name} dropped something!')

    def battle_menu(self, skippable):
        opts = ['FIGHT', 'BAG', 'GUARD', 'RUN']
        easy = skippable and self.easy_win()

        def extra(cur):
            if easy:
                self.put(22, 3, '[S] SKIP - easy win', COLORS['green'] | curses.A_BOLD)
            self.put(22, 30, '[M] LOG', COLORS['cyan'])
            self.box(16, 46, 8, 34)
            self.put(16, 46, '┬')
            self.put(23, 46, '┴')
            for i, o in enumerate(opts):
                r, c = divmod(i, 2)
                self.put(18 + r * 2, 50 + c * 14, ('▶' if i == cur else ' ') + o,
                         curses.A_BOLD if i == cur else 0)
        keys = {'m': 5, 'M': 5}
        if easy:
            keys.update({'s': 4, 'S': 4})
        return self.select(lambda cur: self.draw_battle(['What will', f'{self.name} do?'],
                                                        extra=lambda: extra(cur)), 4, cols=2,
                           keys=keys)

    def fight_menu(self):
        p = self.player
        moves = p.moves

        def extra(cur):
            self.box(16, 0, 8, 56)
            for i, name in enumerate(moves):
                r, c = divmod(i, 2)
                y, x = 17 + r * 2, 3 + c * 26
                self.put(y, x, ('▶' if i == cur else ' ') + name, curses.A_BOLD if i == cur else 0)
                cost = MOVES[name]['mp']
                if cost:
                    self.put(y, x + 18, f'{cost:>2}MP', COLORS['red'] if cost > p.mp else 0)
            self.box(16, 56, 8, 24)
            info = MOVES[moves[cur]]
            short = info['mp'] > p.mp
            self.put(17, 59, f'COST  {info["mp"]} MP' if info['mp'] else 'COST  free',
                     COLORS['red'] | curses.A_BOLD if short else 0)
            self.put(18, 59, f'HAVE  {p.mp}/{p.max_mp} MP')
            self.put(19, 59, f'TYPE/{info["type"].upper()}')
            for i, note in enumerate(move_notes(info)[:2]):
                self.put(21 + i, 59, note[:20], COLORS['cyan'])
        i = self.select(lambda cur: self.draw_battle(extra=lambda: extra(cur)), len(moves), cols=2)
        return None if i is None else moves[i]

    def aim_menu(self, m, move):
        """Pick the body part a physical move aims at. Returns the part, or None to go back."""
        parts, info = m.parts, MOVES[move]
        known = m.name in self.weak_known

        def extra(cur):
            self.box(16, 0, 8, 56)
            self.put(16, 3, f' AIM {move} AT... ', curses.A_BOLD)
            for i, part in enumerate(parts):
                r, c = divmod(i, 2)
                y, x = 17 + r * 2, 3 + c * 26
                self.put(y, x, ('▶' if i == cur else ' ') + part, curses.A_BOLD if i == cur else 0)
                if known and part == m.weak:
                    self.put(y, x + 8, 'WEAK SPOT', COLORS['yellow'] | curses.A_BOLD)
            self.box(16, 56, 8, 24)
            part = parts[cur]
            weak = known and part == m.weak
            mult = PARTS[part][1] * (WEAK_SPOT_MULT if weak else 1)
            self.put(17, 59, f'HIT     {self.hit_chance(m, info, part)}%')
            self.put(18, 59, f'DAMAGE  x{mult:g}', COLORS['yellow'] | curses.A_BOLD if weak else 0)
            self.put(20, 59, 'its weak spot!' if weak else 'weak spot: ???' if not known else '',
                     COLORS['cyan'])
        i = self.select(lambda cur: self.draw_battle(extra=lambda: extra(cur)), len(parts), cols=2)
        return None if i is None else parts[i]

    def battle_transition(self):
        for y in range(24):
            self.put(y, 0, '▓' * (79 if y == 23 else 80), COLORS['white'])
            if y % 2:
                self.scr.refresh()
                curses.napms(12)
        self.draw_battle()
        curses.napms(150)

    def flash(self, who):
        for _ in range(2):
            self.draw_battle(hide=who)
            curses.napms(70)
            self.draw_battle()
            curses.napms(70)

    def animate_hp(self):
        if not self.foe:
            return
        targets = [self.foe.hp, self.player.hp]
        for _ in range(40):
            if self.shown_hp == targets:
                break
            for i in (0, 1):
                diff = targets[i] - self.shown_hp[i]
                if diff:
                    step = max(1, abs(diff) // 6)
                    self.shown_hp[i] += step if diff > 0 else -step
            self.draw_battle()
            curses.napms(25)
        self.shown_hp = targets

    def say(self, text, log=True):
        """Show a line in the battle text box and wait for a key."""
        if log:
            self.record(text)
        lines = textwrap.wrap(text, 72) or ['']
        for i in range(0, len(lines), 2):
            self.draw_battle(lines[i:i + 2], more=True)
            self.wait_key()

    def flush_battle_msgs(self):
        msgs, self.msgs = self.msgs, []
        for t in msgs:
            self.say(t, log=False)

    def draw_battle(self, text=None, more=False, hide=None, extra=None):
        m, p = self.foe or self.fallen, self.player
        self.scr.erase()
        # enemy panel
        self.box(1, 2, 4, 36)
        self.put(2, 4, m.name.upper(), curses.A_BOLD)
        if 'boss' in m.flags:
            self.put(2, 22, 'BOSS', COLORS['red'] | curses.A_BOLD | curses.A_REVERSE)
        self.put(2, 30, f'Lv{m.level}')
        self.hp_bar(3, 4, self.shown_hp[0], m.max_hp, 20)
        self.put(3, 28, f'{max(0, self.shown_hp[0]):>3}/{m.max_hp:>3}', curses.A_BOLD)
        if m.status and m.hp > 0:
            tags = ' '.join(STATUSES[s][0] for s in m.status)
            self.put(4, 5, f' {tags} ', COLORS['magenta'] | curses.A_BOLD)
        for i, f in enumerate(self.foes[1:4]):
            self.put(5 + i, 4, f'+ {f.name.upper()} Lv{f.level}  HP {f.hp}/{f.max_hp}',
                     COLORS[f.color] | curses.A_BOLD)
        if len(self.foes) > 4:
            self.put(8, 4, f'+ {len(self.foes) - 4} more...')
        art = SPRITES[m.name]
        if hide != 'enemy':
            for i, line in enumerate(art):
                self.put(8 - len(art) + i, 48, line, COLORS[m.color] | curses.A_BOLD)
        self.put(8, 46, '`~~~~~~~~~~~~~~~~~~~~~~~~~~\'', COLORS['green'])
        # player panel
        if hide != 'player':
            for i, line in enumerate(SPRITES['player']):
                self.put(9 + i, 6, line, COLORS['yellow'] | curses.A_BOLD)
        self.put(15, 2, '`~~~~~~~~~~~~~~~~~~~~~~~\'', COLORS['green'])
        self.box(9, 42, 7, 36)
        self.put(10, 44, self.name.upper()[:18], curses.A_BOLD)
        self.put(10, 64, f'Lv{p.level}')
        flags = [tag for tag, on in (('FRZ', p.frozen), ('PAR', p.paralyzed), ('BRN', p.burn),
                                     ('CNF', p.confused), ('BAR', p.barrier),
                                     ('PSN', p.str < p.max_str)) if on]
        if flags:
            self.put(12, 44, ' '.join(flags[:3]), COLORS['magenta'] | curses.A_BOLD)
        self.hp_bar(11, 44, self.shown_hp[1], p.max_hp, 26)
        self.put(12, 58, f'{max(0, self.shown_hp[1]):>3}/{p.max_hp:>3}', curses.A_BOLD)
        prev = xp_needed(p.level - 1) if p.level > 1 else 0
        frac = (p.xp - prev) / (xp_needed(p.level) - prev)
        filled = int(min(1, max(0, frac)) * 26)
        self.put(14, 44, 'EXP')
        self.put(14, 48, '█' * filled, COLORS['cyan'])
        self.put(14, 48 + filled, '░' * (26 - filled))
        filled = int(round(p.mp / p.max_mp * 20))
        self.put(13, 44, 'MP', curses.A_BOLD)
        self.put(13, 47, '█' * filled, COLORS['blue'] | curses.A_BOLD)
        self.put(13, 47 + filled, '░' * (20 - filled))
        self.put(13, 68, f'{p.mp:>2}/{p.max_mp:>2}')
        # text box
        self.box(16, 0, 8, 80)
        for i, line in enumerate(text or []):
            self.put_rich(18 + i * 2, 3, line)
        if more:
            self.put(21, 76, '▼', curses.A_BOLD | curses.A_BLINK)
        if extra:
            extra()
        self.draw_log_panel()
        self.scr.refresh()

    def hp_bar(self, y, x, hp, max_hp, width):
        frac = max(0, hp) / max_hp
        filled = int(round(frac * width))
        if hp > 0:
            filled = max(1, filled)
        color = 'green' if frac > 0.5 else 'yellow' if frac > 0.2 else 'red'
        self.put(y, x, 'HP', curses.A_BOLD)
        self.put(y, x + 3, '█' * filled, COLORS[color] | curses.A_BOLD)
        self.put(y, x + 3 + filled, '░' * (width - filled))
