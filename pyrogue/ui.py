"""Drawing the screen, menus, the event log and the help and ending screens."""

import curses
import textwrap

from .constants import (
    ARROWS, CANCEL_KEYS, CAVE_WALL, CONFIRM_KEYS, CORRIDOR, DIRS, DOOR, FINAL_DEPTH, FLOOR,
    HWALL, MAP_H, MAP_TOP, MAP_W, PILLAR, POOL, ROCK, STAIRS, STATUS_ROW, VWALL
)
from .items import ITEM_CHARS, ITEM_COLORS
from .moves import MAX_SPELLS
from .player import xp_needed
from .text import COLORS, LOG_HIGHLIGHTS, TEXT_HIGHLIGHTS
from .world import TRAPS, environment


class UIMixin:
    """Drawing the screen, menus, the event log and the help and ending screens."""

    def box(self, y, x, h, w):
        self.put(y, x, '┌' + '─' * (w - 2) + '┐')
        for i in range(1, h - 1):
            self.put(y + i, x, '│' + ' ' * (w - 2) + '│')
        self.put(y + h - 1, x, '└' + '─' * (w - 2) + '┘')

    def select(self, draw, n, cols=1, keys=None):
        """Cursor menu: arrows/hjkl move, Enter/space/z pick, Esc/x cancel.
        `keys` maps extra hotkeys to the value select() should return."""
        cur = 0
        rows = (n + cols - 1) // cols
        while True:
            draw(cur)
            k = self.scr.getch()
            ch = ARROWS.get(k) or (chr(k) if 0 < k < 256 else '')
            if ch in ('h', 'l', 'k', 'j'):
                dx, dy = DIRS[ch]
                r, c = divmod(cur, cols)
                nxt = ((r + dy) % rows) * cols + (c + dx) % cols
                if nxt < n:
                    cur = nxt
            elif ch in CONFIRM_KEYS or k == curses.KEY_ENTER:
                return cur
            elif ch in CANCEL_KEYS:
                return None
            elif keys and ch in keys:
                return keys[ch]
            elif ch.isdigit() and 1 <= int(ch) <= n:
                return int(ch) - 1

    # ------------------------------------------------------------- drawing
    def put(self, y, x, s, attr=0):
        try:
            self.scr.addstr(y, x, s, attr)
        except curses.error:
            pass

    def put_rich(self, y, x, text, attr=0):
        """Draw a line of message text with its important words and values highlighted."""
        spans = []
        for rx, color in TEXT_HIGHLIGHTS:
            for found in rx.finditer(text):
                start, end = found.span()
                if all(end <= a or start >= b for a, b, _ in spans):
                    spans.append((start, end, (COLORS[color] if color else attr) | curses.A_BOLD))
        pos = 0
        for start, end, hl in sorted(spans):
            self.put(y, x + pos, text[pos:start], attr)
            self.put(y, x + start, text[start:end], hl)
            pos = end
        self.put(y, x + pos, text[pos:], attr)

    def draw(self, top_lines, more=False, refresh=True):
        scr, p = self.scr, self.player
        scr.erase()
        for i, line in enumerate(top_lines[:2]):
            self.put_rich(i, 0, line)
            if more and i == len(top_lines[:2]) - 1:
                self.put(i, len(line) + 1, '--More--', curses.A_REVERSE)

        wall = self.env['wall']
        tile_colors = {HWALL: wall, VWALL: wall, DOOR: 'yellow',
                       FLOOR: 'white', CORRIDOR: 'white', STAIRS: 'green',
                       CAVE_WALL: wall, PILLAR: wall,
                       POOL: self.env.get('pool', ('', 'red'))[1]}
        for y in range(MAP_H):
            row = self.tiles[y]
            for x in range(MAP_W):
                if not self.explored[y][x] or row[x] == ROCK:
                    continue
                t = row[x]
                if (x, y) in self.visible:
                    attr = COLORS[tile_colors[t]] | (curses.A_BOLD if t in (STAIRS, POOL) else 0)
                else:
                    attr = COLORS['blue']
                self.put(MAP_TOP + y, x, t, attr)

        for (x, y), t in self.traps.items():
            if t.found:
                color = TRAPS[t.kind][1] if (x, y) in self.visible else 'blue'
                self.put(MAP_TOP + y, x, '^', COLORS[color] | curses.A_BOLD)
        for it in self.items:
            if (it.x, it.y) in self.visible:
                it.seen = True
            if it.seen:
                self.put(MAP_TOP + it.y, it.x, ITEM_CHARS[it.kind],
                         COLORS[ITEM_COLORS[it.kind]] | curses.A_BOLD)
        for npc in self.npcs:
            if (npc.x, npc.y) in self.visible:
                self.put(MAP_TOP + npc.y, npc.x, '&', COLORS[npc.color] | curses.A_BOLD)
        for m in self.visible_monsters():
            self.put(MAP_TOP + m.y, m.x, m.ch, COLORS[m.color] | curses.A_BOLD)
        self.put(MAP_TOP + p.y, p.x, '@', COLORS['yellow'] | curses.A_BOLD)

        hunger = ('' if p.food > 300 else 'Hungry' if p.food > 150
                  else 'Weak' if p.food > 0 else 'Starving')
        strength = f'Str:{p.str}' + (f'({p.max_str})' if p.str < p.max_str else '')
        status = (f'Depth:{self.depth} HP:{p.hp}({p.max_hp}) MP:{p.mp}({p.max_mp}) {strength} '
                  f'Def:{p.ac} Lvl:{p.level} Exp:{p.xp}/{xp_needed(p.level)} Gold:{p.gold}')
        self.put(STATUS_ROW, 0, status)
        hp_attr = COLORS['red'] | curses.A_BOLD if p.hp <= p.max_hp // 3 else 0
        self.put(STATUS_ROW, status.index('HP:'), f'HP:{p.hp}', hp_attr)
        flags = ' '.join(f for f in (hunger, 'Confused' if p.confused else '',
                                     'Stuck' if p.stuck else '', 'Burning' if p.burn else '',
                                     'Frozen' if p.frozen else '',
                                     'Paralyzed' if p.paralyzed else '') if f)
        if flags:
            self.put(STATUS_ROW, len(status) + 2, flags, COLORS['red'] | curses.A_BOLD)
        if self.auto_skip:
            self.put(STATUS_ROW, len(status) + 2 + (len(flags) + 1 if flags else 0),
                     'Auto', COLORS['green'] | curses.A_BOLD)
        self.draw_log_panel()
        if refresh:
            scr.refresh()

    def log_lines(self, width, entries, stamps=True):
        """Event log entries as (prefix, text, attr) screen lines wrapped to `width`, oldest
        first. A header marks every change of depth; stamps puts the turn number in front."""
        lines, depth = [], None
        pad = 7 if stamps else 2
        for turn, d, text, n in entries:
            if d != depth:
                depth = d
                lines.append(('', f'-- Depth {d}: {environment(max(1, d))["name"]} --'[:width],
                              COLORS['cyan'] | curses.A_BOLD))
            if n > 1:
                text += f' (x{n})'
            attr = next((COLORS[c] | curses.A_BOLD for key, c in LOG_HIGHLIGHTS if key in text), 0)
            for i, part in enumerate(textwrap.wrap(text, width - pad) or ['']):
                head = (f'{turn:>5}  ' if stamps else '- ') if i == 0 else ' ' * pad
                lines.append((head, part, attr))
        return lines

    def draw_log_panel(self):
        """In a terminal bigger than 80x24, show the latest events beside or below the game."""
        rows, cols = self.scr.getmaxyx()
        if cols >= 104:
            top, left, height, width = 0, 81, rows - 1, cols - 82
        elif rows >= 28:
            top, left, height, width = 25, 0, rows - 26, min(cols - 1, 80)
        else:
            return
        self.put(top, left, ' RECENT EVENTS '.center(width, '─'), COLORS['cyan'])
        lines = self.log_lines(width, self.log[-height:], stamps=False)[-height:]
        for i, (head, line, attr) in enumerate(lines):
            self.put(top + 1 + i, left, head)
            self.put_rich(top + 1 + i, left + len(head), line, attr)

    def show_log(self):
        """Scroll through the event log. It opens at the newest events."""
        rows, cols = self.scr.getmaxyx()
        width, height = min(cols, 120) - 1, rows - 2
        lines = self.log_lines(width, self.log) or [('', 'Nothing has happened yet.', 0)]
        bottom = max(0, len(lines) - height)
        top = bottom
        while True:
            self.scr.erase()
            self.put(0, 0, f' EVENT LOG   (turn {self.turn}, depth {self.depth})'.ljust(width),
                     curses.A_REVERSE)
            for i, (head, line, attr) in enumerate(lines[top:top + height]):
                self.put(1 + i, 0, head, COLORS['blue'])
                self.put_rich(1 + i, len(head), line, attr)
            where = 'end' if top >= bottom else f'{top + height}/{len(lines)}'
            self.put(rows - 1, 0, f' up/down or j/k: scroll   PgUp/PgDn/space: page   '
                     f'g/G: start/end   Esc: close   [{where}] '[:width], curses.A_REVERSE)
            self.scr.refresh()
            k = self.scr.getch()
            ch = chr(k) if 0 < k < 256 else ''
            if k == curses.KEY_UP or ch == 'k':
                top -= 1
            elif k == curses.KEY_DOWN or ch == 'j':
                top += 1
            elif k == curses.KEY_PPAGE or ch == 'b':
                top -= height
            elif k == curses.KEY_NPAGE or ch == ' ':
                top += height
            elif ch == 'g' or k == curses.KEY_HOME:
                top = 0
            elif ch == 'G' or k == curses.KEY_END:
                top = bottom
            elif k == curses.KEY_RESIZE:
                return self.show_log()
            elif ch in CANCEL_KEYS or ch in ('q', 'm', '\n', '\r'):
                return
            top = max(0, min(bottom, top))

    def show(self):
        """Draw the screen, paging through this turn's messages with --More--."""
        if self.foe:
            self.flush_battle_msgs()
            self.draw_battle()
            return
        lines = textwrap.wrap('  '.join(self.msgs), MAP_W - 10) or ['']
        self.msgs = []
        while len(lines) > 2:
            self.draw(lines[:2], more=True)
            self.wait_key()
            lines = lines[2:]
        self.draw(lines)

    def show_pending(self):
        """Page through the messages still waiting to be read, on the map, a key per page."""
        lines = textwrap.wrap('  '.join(self.msgs), MAP_W - 10)
        self.msgs = []
        for i in range(0, len(lines), 2):
            self.draw(lines[i:i + 2], more=True)
            self.wait_key()

    def wait_key(self):
        while self.scr.getch() == curses.KEY_RESIZE:
            pass

    def menu(self, title, entries):
        width = max(len(title), *(len(e) for e in entries)) + 2
        x = max(0, MAP_W - width - 1)
        rows = [title, ''] + entries
        for i, line in enumerate(rows[:22]):
            self.put(1 + i, x, ' ' + line.ljust(width), curses.A_REVERSE if i == 0 else 0)
        self.scr.refresh()
        return self.scr.getch()

    def full_screen(self, lines):
        self.scr.erase()
        for i, line in enumerate(lines[:23]):
            self.put(i, 0, line)
        self.put(23, 0, '-- press any key --', curses.A_REVERSE)
        self.scr.refresh()
        self.wait_key()

    HELP = [
        'COMMANDS                                               y k u',
        '  h j k l y u b n   move (or arrow keys / numpad)       \\|/',
        '  H J K L Y U B N   run in that direction             h-@-l',
        '  . or 5            rest one turn                       /|\\',
        '  z                 rest until HP and MP are full      b j n',
        '  s                 search for traps in sight (and items, in rooms)',
        '  >                 go down stairs (walk onto an item to pick it up)',
        '  i  inventory: use, wield, wear or drop items; cast HEAL, MEDITATE, BARRIER',
        '  m  event log (all that happened)   A  auto-skip easy battles',
        '  ?  help   Q  save & quit',
        '  Press two arrow keys together (like up + left) to move diagonally.',
        'BATTLES, TRAPS & TALKING',
        '  Bump a monster to fight. In battle, S skips easy fights and M opens the log.',
        '  In menus: arrows/hjkl move the cursor, Enter/space/z choose, Esc/x go back.',
        '  Walk into a friendly character (&) to talk to them.',
        '  STRIKE and POWER SMASH are aimed. Hit a monster\'s weak spot for extra damage.',
        '  Traps are hidden and each goes off only once. Known traps (^) warn you first.',
        f'  Spells cost MP and come from spell scrolls. You can know {MAX_SPELLS} at once.',
        'SYMBOLS',
        '  @ you  & friend  > stairs  ! potion  ? scroll  ) weapon  ] armor  ^ trap',
        '  : food  * gold  " Amulet  + door  # corridor  % rock  ~ lava/water  0 pillar',
        '',
        f'Beat the bosses on depths 10 and {FINAL_DEPTH} and claim the Amulet of Yendor.',
    ]

    def confirm(self, question):
        self.show()
        self.draw([question])
        return self.scr.getch() in (ord('y'), ord('Y'))

    def ending_screen(self):
        p = self.player
        kind = self.game_over[0]
        if kind == 'died':
            def c(s):
                return s[:18].center(18)
            stone = [
                '',
                '                     __________',
                '                    /          \\',
                '                   /    REST    \\',
                '                  /      IN      \\',
                '                 /     PEACE      \\',
                '                /                  \\',
                f'                | {c(self.name)} |',
                f'                | {c(f"{p.gold} Au")} |',
                f'                | {c("killed by")} |',
                f'                | {c(self.game_over[1])} |',
                f'                | {c(f"on depth {self.depth}")} |',
                f'                | {c(f"at level {p.level}")} |',
                '               *|     *  *  *        | *',
                "       ________)/\\\\_//(\\/(/\\)/\\//\\/|_)_______",
            ]
            self.full_screen(stone)
        elif kind == 'won':
            self.full_screen([
                '', '',
                '   You pick up the Amulet of Yendor!',
                '',
                '   Its power whisks you up through the dungeon and out into the',
                '   daylight. The Guild of Adventurers will sing of this day.',
                '',
                f'   {self.name} escaped with the Amulet and {p.gold} gold pieces',
                f'   at experience level {p.level} after {self.turn} turns.',
                '', '   Congratulations!',
            ])
        else:
            self.full_screen(['', f'   You quit on depth {self.depth} with {p.gold} gold pieces.'])
