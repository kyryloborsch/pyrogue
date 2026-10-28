"""Items in the pack: naming, prices, using them, and the spellbook."""

import curses
import random

from .constants import MAP_H, MAP_W, MAX_PACK, ROCK, STAIRS
from .items import POTION_PRICES, SCROLL_PRICES, STACKABLE
from .monsters import NOISE_MEMORY
from .moves import MAX_SPELLS, MOVES, SPELLS, move_notes
from .player import xp_needed
from .text import COLORS, an


class ItemsMixin:
    """Items in the pack: naming, prices, using them, and the spellbook."""

    def item_name(self, it, reveal=False):
        n = it.count
        if it.kind == 'gold':
            return f'{n} gold pieces'
        if it.kind == 'amulet':
            return 'the Amulet of Yendor'
        if it.kind == 'food':
            return 'a food ration' if n == 1 else f'{n} food rations'
        # enchantment is already counted in the stats shown, so it isn't listed separately
        if it.kind == 'weapon' and it.magic:
            return an(f'{it.sub} (hits {it.dmg[0]}-{it.dmg[1]}, spells +{it.magic + it.ench})')
        if it.kind == 'weapon':
            return an(f'{it.sub} (hits {it.dmg[0] + it.ench}-{it.dmg[1] + it.ench})')
        if it.kind == 'armor':
            return an(f'{it.sub} (defense {it.ac + it.ench})')
        noun = it.kind if n == 1 else it.kind + 's'
        if it.sub in SPELLS:                       # spell scrolls are always recognized
            base = f'spell {noun} of {it.sub}'
        elif reveal or it.sub in self.known:
            base = f'{noun} of {it.sub}'
        elif it.kind == 'potion':
            base = f'{self.potion_look[it.sub]} {noun}'
        else:
            base = f'{noun} titled "{self.scroll_look[it.sub]}"'
        return an(base) if n == 1 else f'{n} {base}'

    def describe(self, it):
        s = self.item_name(it)
        if it is self.player.weapon:
            s += ' (in hand)'
        if it is self.player.armor:
            s += ' (being worn)'
        return s

    def price(self, it):
        if it.kind == 'potion':
            base = POTION_PRICES[it.sub]
        elif it.sub in SPELLS:
            base = SPELLS[it.sub][1]
        elif it.kind == 'scroll':
            base = SCROLL_PRICES[it.sub]
        elif it.kind == 'food':
            base = 15
        elif it.kind == 'weapon':
            base = (it.dmg[0] + it.dmg[1]) * 6 + it.magic * 25 + it.ench * 30
        else:
            base = it.ac * 18 + it.ench * 30
        return max(5, base)

    def add_to_pack(self, it):
        pack = self.player.pack
        if it.kind in STACKABLE:
            for other in pack:
                if other.kind == it.kind and other.sub == it.sub:
                    other.count += it.count
                    return other
        if len(pack) >= MAX_PACK:
            return None
        pack.append(it)
        return it

    def pickup(self, auto):
        p = self.player
        it = self.item_at(p.x, p.y)
        if not it:
            if not auto:
                self.msg('There is nothing here to pick up.')
            return False
        if it.kind == 'gold':
            p.gold += it.count
            self.items.remove(it)
            self.msg(f'You found {it.count} gold pieces.')
            return True
        if it.kind == 'amulet':
            self.items.remove(it)
            self.game_over = ('won',)
            return True
        name = self.item_name(it)
        stacked = self.add_to_pack(it)
        if not stacked:
            self.msg(f'Your pack is too full to pick up {name}.')
            return not auto
        self.items.remove(it)
        letter = chr(ord('a') + p.pack.index(stacked))
        self.msg(f'You now have {self.item_name(stacked)} ({letter}).')
        return True

    def use_up(self, it):
        it.count -= 1
        if it.count <= 0:
            self.player.pack.remove(it)

    # --------------------------------------------------------------- items
    def choose(self, verb, pred):
        opts = [(chr(ord('a') + i), it) for i, it in enumerate(self.player.pack) if pred(it)]
        if not opts:
            self.msg(f'You have nothing to {verb}.')
            return None
        self.show()
        k = self.menu(f'{verb.capitalize()} what? (Esc to cancel)',
                      [f'{l}) {self.describe(it)}' for l, it in opts])
        ch = chr(k) if 0 < k < 256 else ''
        return next((it for l, it in opts if l == ch), None)

    def quaff(self):
        it = self.choose('quaff', lambda i: i.kind == 'potion')
        return self.drink(it) if it else False

    def read(self):
        it = self.choose('read', lambda i: i.kind == 'scroll')
        return self.read_scroll(it) if it else False

    def eat(self):
        it = self.choose('eat', lambda i: i.kind == 'food')
        return self.eat_food(it) if it else False

    def drink(self, it):
        p = self.player
        kind = it.sub
        self.use_up(it)
        self.known.add(kind)
        if kind == 'healing':
            p.hp = min(p.max_hp, p.hp + random.randint(6, 11) + p.level * 2)
            p.cure()
            self.msg('You begin to feel better.')
        elif kind == 'extra healing':
            p.max_hp += 2
            p.hp = p.max_hp
            p.str = p.max_str
            p.cure()
            p.restore_mp()
            self.msg('You feel much better.')
        elif kind == 'mana':
            p.restore_mp()
            self.msg('Your mind clears as magic surges through you.')
        elif kind == 'strength':
            p.max_str += 1
            p.str = p.max_str
            self.msg('You feel stronger, now. What bulging muscles!')
        elif kind == 'poison':
            p.str = max(3, p.str - random.randint(1, 3))
            self.msg('You feel very sick now.')
        elif kind == 'confusion':
            p.confused += random.randint(8, 16)
            self.msg("Wait, what's going on here? Huh? What? Who?")
        elif kind == 'raise level':
            p.xp = max(p.xp, xp_needed(p.level))
            self.msg('You suddenly feel much more skillful.')
            self.gain_xp(0)
        return True

    def learn_spell(self, it):
        """Read a spell scroll. With MAX_SPELLS known, the player must forget one first.
        Returns False if the player kept the scroll after all."""
        p = self.player
        spell = it.sub
        if spell in p.moves:
            self.use_up(it)
            p.restore_mp()
            self.msg(f'You already know {spell}. The scroll crumbles away, restoring your mana.')
            return True
        if len(p.spells) >= MAX_SPELLS:
            old = self.pick_forget(spell)
            if not old:
                self.msg(f'You put the spell scroll of {spell} away for now.')
                return False
            p.moves.remove(old)
            self.msg(f'1, 2 and... poof! {self.name} forgot {old}.')
        p.moves.append(spell)
        self.use_up(it)
        self.msg(f'The scroll glows and crumbles to dust. {self.name} learned {spell}!')
        return True

    # ----------------------------------------------------------- spellbook
    def spellbook(self):
        """Show every move the player knows and what the wielded weapon adds to them."""
        p = self.player
        lo, hi = p.weapon_dmg
        w = p.weapon
        if w and w.magic:
            weapon = [f'Weapon: {self.item_name(w)}, a magic weapon',
                      f'Attack spells deal +{p.spell_power} damage. STRIKE and POWER SMASH hit '
                      f'for only {lo}-{hi}.']
        else:
            weapon = [f'Weapon: {self.item_name(w) + ", a physical weapon" if w else "bare hands"}',
                      f'STRIKE and POWER SMASH hit for {lo}-{hi} (plus strength). Spells get no '
                      'bonus.']
        self.draw_spells('SPELLBOOK', p.moves, None, 'press any key', weapon + [
            '', f'You know {len(p.spells)} of {MAX_SPELLS} spells. Learning another means '
            'forgetting one.'])
        self.wait_key()

    def pick_forget(self, spell):
        """Ask which known spell to forget for `spell`. None keeps things as they are."""
        options = self.player.spells
        i = self.select(lambda c: self.draw_spells(
            f'You know {MAX_SPELLS} spells already! Forget which one for {spell}?',
            options, c, f'Enter: forget it   Esc: keep the scroll of {spell} for later'),
            len(options))
        return None if i is None else options[i]

    def draw_spells(self, title, names, cur, footer, notes=()):
        p = self.player
        self.scr.erase()
        self.put(0, 0, f' {title}', curses.A_BOLD)
        self.put(0, 66, f'MP {p.mp}/{p.max_mp}', COLORS['blue'] | curses.A_BOLD)
        self.put(2, 2, '  MOVE              TYPE      COST  EFFECT', curses.A_UNDERLINE)
        for i, name in enumerate(names):
            info = MOVES[name]
            cost = f'{info["mp"]:>2} MP' if info['mp'] else 'free'
            line = (f'{"▶" if i == cur else " "} {name:<17} {info["type"].upper():<9} '
                    f'{cost:<5} {", ".join(move_notes(info))}')
            self.put(3 + i, 2, line[:77], curses.A_BOLD if i == cur else 0)
        for i, note in enumerate(notes):
            self.put(11 + i, 2, note[:77], COLORS['cyan'])
        self.put(23, 0, f' {footer} '[:79], curses.A_REVERSE)
        self.scr.refresh()

    def map_level(self):
        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.tiles[y][x] != ROCK:
                    self.explored[y][x] = True

    def weapon_note(self):
        """What the wielded weapon now does, after it was improved."""
        p = self.player
        if p.weapon.magic:
            return f'Your spells now get +{p.spell_power}.'
        return f'It now hits for {p.weapon_dmg[0]}-{p.weapon_dmg[1]}.'

    def read_scroll(self, it):
        p = self.player
        kind = it.sub
        if kind in SPELLS:
            return self.learn_spell(it)
        self.use_up(it)
        self.known.add(kind)
        if kind == 'magic mapping':
            self.map_level()
            self.msg('Oh, now this scroll has a map on it.')
        elif kind == 'teleportation':
            p.x, p.y = self.free_spot(random.choice(self.rooms))
            self.compute_fov()
            self.msg('You feel very disoriented.')
        elif kind == 'enchant weapon':
            if p.weapon:
                p.weapon.ench += 1
                self.msg(f'Your {p.weapon.sub} glows blue for a moment. {self.weapon_note()}')
            else:
                self.msg('Your hands tingle.')
        elif kind == 'enchant armor':
            if p.armor:
                p.armor.ench += 1
                self.msg(f'Your armor glows silver for a moment. Your defense is now {p.ac}.')
            else:
                self.msg('Your skin crawls.')
        elif kind == 'detect traps':
            for t in self.traps.values():
                t.found = True
            n = len(self.traps)
            self.msg(f'Your feet tingle. You sense {n} trap{"s" if n != 1 else ""} on this level.'
                     if n else 'Your feet tingle, but you sense no traps here.')
        elif kind == 'identify':
            self.msg('This is a scroll of identify.')
            target = self.choose('identify', lambda i: i.kind in ('potion', 'scroll')
                                 and i.sub not in self.known and i.sub not in SPELLS)
            if target:
                self.known.add(target.sub)
                self.msg(f'That is {self.item_name(target)}.')
        elif kind == 'aggravate monsters':
            for m in self.monsters:
                m.alert(NOISE_MEMORY)
            self.msg('You hear a high-pitched humming noise.')
        return True

    def eat_food(self, it):
        p = self.player
        self.use_up(it)
        p.food = min(2000, max(p.food, 0) + 1100)
        self.msg(random.choice(['Yum, that tasted good.',
                                'This food tastes awful, but you eat it anyway.']))
        return True

    def wield(self):
        p = self.player
        it = self.choose('wield', lambda i: i.kind == 'weapon')
        if not it:
            return False
        if it is p.weapon:
            self.msg('You are already wielding that.')
            return False
        p.weapon = it
        self.msg(f'You are now wielding {self.item_name(it)}.')
        return True

    def wear(self):
        p = self.player
        it = self.choose('wear', lambda i: i.kind == 'armor')
        if not it:
            return False
        if it is p.armor:
            self.msg('You are already wearing that.')
            return False
        p.armor = it
        self.msg(f'You are now wearing {self.item_name(it)}.')
        return True

    def drop(self):
        p = self.player
        it = self.choose('drop', lambda i: True)
        if not it:
            return False
        if self.item_at(p.x, p.y) or self.tiles[p.y][p.x] == STAIRS:
            self.msg('There is already something there.')
            return False
        if it is p.weapon:
            p.weapon = None
        if it is p.armor:
            p.armor = None
        p.pack.remove(it)
        it.x, it.y, it.seen = p.x, p.y, True
        self.items.append(it)
        self.msg(f'You dropped {self.item_name(it)}.')
        return True
