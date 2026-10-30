"""Items in the pack: naming, prices, the inventory screen and using things."""

import curses
import random
import textwrap

from .constants import (
    ARROWS, CANCEL_KEYS, CONFIRM_KEYS, ITEM_LETTERS, MAP_H, MAP_W, MAX_PACK, ROCK, STAIRS
)
from .items import CATEGORIES, ITEM_NOTES, Item, POTION_PRICES, SCROLL_PRICES, STACKABLE
from .monsters import NOISE_MEMORY
from .moves import MAX_SPELLS, MOVES, SPELLS, field_spell, move_notes
from .player import xp_needed
from .text import COLORS, an


class ItemsMixin:
    """Items in the pack: naming, prices, the inventory screen and using things."""

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

    def pickup(self):
        """Pick up whatever is underfoot: done for you whenever you step onto something."""
        p = self.player
        it = self.item_at(p.x, p.y)
        if not it:
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
            self.msg(f'Your pack is full, so you leave {name} where it lies.')
            return False
        self.items.remove(it)
        letter = self.letter(stacked)
        self.msg(f'You now have {self.item_name(stacked)} ({letter}).')
        return True

    def use_up(self, it):
        it.count -= 1
        if it.count <= 0:
            self.player.pack.remove(it)

    # ----------------------------------------------------------- inventory
    def pack_order(self):
        """The pack as the inventory shows it: grouped by kind, then in the order picked up."""
        kinds = list(CATEGORIES)
        return sorted(self.player.pack, key=lambda it: kinds.index(it.kind))

    def letter(self, it):
        """The letter an item goes by in the inventory; press it there to pick the item."""
        return ITEM_LETTERS[self.pack_order().index(it)]

    def inventory_rows(self, in_battle, only=None, tag=None):
        """The inventory's lines: (text, what picking it does, color). Headings pick nothing.
        With only, just the items that suit it (and no spells); tag(item) adds a note on the
        right, like a price."""
        p = self.player
        rows = []
        if not in_battle and not only and p.spells:
            rows.append((f'SPELLS   MP {p.mp}/{p.max_mp}', None, 'blue'))
            for name in p.spells:
                info = MOVES[name]
                cost = f'{info["mp"]} MP' if info['mp'] else 'free'
                where = cost if field_spell(name) else 'battle only'
                rows.append((f'   {name:<17} {where}', ('spell', name),
                             None if field_spell(name) else 'dim'))
        for kind, heading in CATEGORIES.items():
            items = [it for it in self.pack_order() if it.kind == kind and (not only or only(it))]
            if in_battle and kind == 'armor':      # no changing armor mid-fight
                continue
            if items:
                rows.append((heading, None, 'yellow'))
                for it in items:
                    text = f'{self.letter(it)}) {self.describe(it)}'
                    if tag:
                        text = f'{text[:56]:<57}{tag(it):>13}'
                    rows.append((text, ('item', it), None))
        return rows

    def note(self, kind, obj):
        """The line under the inventory about the thing the cursor is on."""
        p = self.player
        if kind == 'spell':
            notes = ', '.join(move_notes(MOVES[obj])).capitalize()
            return f'{notes}.' if field_spell(obj) else f'{notes}. Cast it in battle (FIGHT).'
        it = obj
        if it.kind == 'weapon':
            if it.magic:
                return (f'Magic weapon: adds +{it.magic + it.ench} to every attack spell, '
                        'but barely hurts in melee.')
            return 'Physical weapon: STRIKE and POWER SMASH hit harder with it.'
        if it.kind == 'armor':
            return f'Armor: each point of defense makes you harder to hit. You have {p.ac}.'
        if it.kind == 'food':
            return 'Eat when you get hungry. Starving hurts!'
        if it.sub in SPELLS:
            notes = ', '.join(move_notes(MOVES[it.sub]))
            return f'Read it to learn the spell {it.sub} ({notes}).'
        if it.sub in self.known:
            return ITEM_NOTES[it.sub]
        return f'You don\'t know what this {it.kind} does yet. Try it, or read identify.'

    def item_actions(self, it, in_battle):
        """What can be done with an item: [(label, action)]."""
        use = {'potion': ('Drink', self.drink), 'scroll': ('Read', self.read_scroll),
               'food': ('Eat', self.eat_food), 'weapon': ('Wield', self.wield_item),
               'armor': ('Wear', self.wear_item)}[it.kind]
        acts = [use]
        if it is self.player.weapon or it is self.player.armor:
            acts = []
        if not in_battle:
            acts.append(('Drop', self.drop_item))
        return acts

    def inventory(self, in_battle=False):
        """Everything you carry in one place, grouped by kind, with your spells on top. Pick
        a line to use, cast or drop it. In battle, using something closes the BAG and returns
        True. On the map the inventory stays open, and each use passes its turn right away,
        until you close it or something needs your attention; it returns False, as those
        turns have already gone by."""
        def pick(choice, view):
            kind, obj = choice
            in_sight = self.visible_monsters()
            done, note = (self.cast_from_pack(obj) if kind == 'spell'
                          else self.use_from_pack(obj, view, in_battle))
            if in_battle:
                return done, done, note
            if not done:                              # say why here, not after closing
                news, self.msgs = '  '.join(self.msgs), []
                return False, None, note or news or None
            return self.pass_turn_in_pack(in_sight)
        footer = ' up/down: move   letter/Enter: use' + ('' if in_battle else ', cast or drop')
        used = self.browse(lambda: self.inventory_rows(in_battle), pick,
                           ' BAG' if in_battle else ' INVENTORY', footer + '   Esc/i: close')
        if used is None:
            if not self.inventory_rows(in_battle):
                self.msg('You have nothing to use.' if in_battle else 'You are empty-handed.')
            return False
        return in_battle

    def pass_turn_in_pack(self, in_sight):
        """End the turn an item or spell took, with the inventory still open. It closes if
        the game ends, a battle broke out, a new monster came into view or the pack is empty,
        leaving the news for the map; otherwise the news shows at the bottom of the inventory.
        Returns what pick() returns to browse()."""
        battles = self.battles
        self.end_turn()
        if (self.game_over or self.battles != battles or not self.inventory_rows(False)
                or any(m not in in_sight for m in self.visible_monsters())):
            return True, False, None
        news, self.msgs = '  '.join(self.msgs), []
        return False, None, news

    def pick_item(self, title, pred, note):
        """The inventory screen, showing only the items that suit pred, to pick one of them.
        None if you back out."""
        return self.browse(lambda: self.inventory_rows(False, pred), lambda choice, view:
                           (True, choice[1], None), f' {title}',
                           ' up/down: move   letter/Enter: pick   Esc: back', note)

    def browse(self, rows_of, pick, title, footer, note=None):
        """The inventory's cursor. rows_of() gives the rows to show; pick(choice, view)
        returns (finished, result, note to show). Returns the result, or None if closed."""
        cur, top, shown, jump = 0, 0, None, False
        while True:
            rows = rows_of()
            picks = [i for i, row in enumerate(rows) if row[1]]
            if not picks:
                return None
            cur = max(0, min(cur, len(picks) - 1))
            sel = picks[cur]
            height = 19
            if sel - 1 < top:
                top = max(0, sel - 1)                 # keep the heading above in view
            elif sel >= top + height:
                top = sel - height + 1
            view = (rows, sel, top, height, title)
            if shown and len(shown) > 78:             # page through a long message
                lines = textwrap.wrap(shown, 69)
                for line in lines[:-1]:
                    self.draw_inventory(*view, footer, f'{line} --More--')
                    self.wait_key()
                shown = lines[-1]
            self.draw_inventory(*view, footer, shown or note or self.note(*rows[sel][1]))
            shown = None
            if jump:
                jump = False
                finished, result, shown = pick(rows[sel][1], view)
                if finished:
                    return result
                continue
            k = self.scr.getch()
            ch = ARROWS.get(k) or (chr(k) if 0 < k < 256 else '')
            lettered = {self.letter(rows[i][1][1]): n for n, i in enumerate(picks)
                        if rows[i][1][0] == 'item'}
            if ch in lettered:                        # an item's letter picks it at once
                cur, jump = lettered[ch], True
            elif ch == 'k':
                cur = (cur - 1) % len(picks)
            elif ch == 'j':
                cur = (cur + 1) % len(picks)
            elif ch in CANCEL_KEYS or ch == 'i':
                return None
            elif ch in CONFIRM_KEYS or k == curses.KEY_ENTER:
                jump = True

    def cast_from_pack(self, name):
        """Cast a spell outside battle. Returns (turn spent, note to show)."""
        p = self.player
        cost = MOVES[name]['mp']
        if not field_spell(name):
            return False, f'{name} only works in battle.'
        if cost > p.mp:
            return False, f'Not enough MP! {name} costs {cost} MP.'
        self.use_move(None, name, quiet=True)
        return True, None

    def use_from_pack(self, it, view, in_battle):
        """Choose what to do with an item and do it. Returns (turn spent, note)."""
        acts = self.item_actions(it, in_battle)
        if not acts:
            worn = 'in your hand' if it is self.player.weapon else 'being worn'
            return False, f'That is already {worn}.'
        labels = [label for label, _ in acts] + ['Back']
        i = self.select(lambda c: self.draw_inventory(
            *view, ' up/down: choose   Enter: pick   Esc: back', self.note('item', it),
            actions=(labels, c)), len(labels))
        if i is None or i == len(acts):
            return False, None
        return acts[i][1](it), None

    def draw_inventory(self, rows, sel, top, height, title, footer, note, actions=None):
        p = self.player
        self.scr.erase()
        self.put(0, 0, title, curses.A_BOLD)
        self.put(0, 40, f'{len(p.pack)}/{MAX_PACK} items   {p.gold} gold'.rjust(39),
                 COLORS['yellow'])
        for i, (text, pick, color) in enumerate(rows[top:top + height]):
            y, row = 2 + i, top + i
            if not pick:
                self.put(y, 1, f' {text} ', COLORS[color] | curses.A_BOLD | curses.A_UNDERLINE)
                continue
            attr = curses.A_DIM if color == 'dim' else 0
            if row == sel:
                attr |= curses.A_REVERSE if not actions else curses.A_BOLD
            self.put(y, 2, ('▶ ' if row == sel else '  ') + text[:72], attr)
        if top > 0:
            self.put(2, 76, '▲', COLORS['blue'])
        if top + height < len(rows):
            self.put(2 + height - 1, 76, '▼', COLORS['blue'])
        if actions:
            labels, c = actions
            y = min(2 + sel - top, 22 - len(labels) - 2)     # beside the item, on screen
            w = max(16, max(map(len, labels)) + 6)
            self.box(y, 76 - w, len(labels) + 2, w)
            for j, label in enumerate(labels):
                self.put(y + 1 + j, 78 - w, ('▶ ' if j == c else '  ') + label,
                         curses.A_BOLD if j == c else 0)
        self.put_rich(22, 1, note[:78], COLORS['cyan'])
        self.put(23, 0, footer.ljust(80)[:79], curses.A_REVERSE)
        self.scr.refresh()

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

    # ---------------------------------------------------- forgetting spells
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
            unknown = (lambda i: i.kind in ('potion', 'scroll') and i.sub not in self.known
                       and i.sub not in SPELLS)
            target = self.pick_item('IDENTIFY: which one?', unknown,
                                    'This is a scroll of identify! Pick a potion or scroll to '
                                    'learn what it is.') if any(map(unknown, p.pack)) else None
            if not target:
                self.add_to_pack(Item('scroll', 'identify'))    # nothing read after all
                self.msg('This is a scroll of identify. '
                         + ('You roll it back up for later.' if any(map(unknown, p.pack)) else
                            'You know everything you carry, so you keep it for later.'))
                return False
            self.known.add(target.sub)
            self.msg(f'This is a scroll of identify. That is {self.item_name(target)}.')
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

    def wield_item(self, it):
        self.player.weapon = it
        self.msg(f'You are now wielding {self.item_name(it)}.')
        return True

    def wear_item(self, it):
        self.player.armor = it
        self.msg(f'You are now wearing {self.item_name(it)}.')
        return True

    def drop_item(self, it):
        p = self.player
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
