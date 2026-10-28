"""Building levels: rooms, crypts and caves, what lives on them, and what the player can see."""

import heapq
import random
from collections import deque

from .characters import MERCHANT_EVERY, NPC, NPC_CHANCE, NPC_SPAWNS
from .constants import (
    CAVE_WALL, CORRIDOR, DIRS, DOOR, FLOOR, FOV_RADIUS, HWALL, MAP_H, MAP_W, OPAQUE, PILLAR,
    POOL, ROCK, STAIRS, VWALL, WALKABLE, WALLS
)
from .items import (
    ARMORS, Item, POTIONS, POTION_WEIGHTS, SCROLLS, SCROLL_WEIGHTS, WEAPONS, make_armor,
    make_weapon
)
from .monsters import MONSTERS, Monster
from .moves import SPELLS, SPELL_SCROLL_CHANCE
from .world import Trap, boss_at, environment


class Room:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def overlaps(self, o, margin):
        return (self.x - margin < o.x + o.w and o.x - margin < self.x + self.w and
                self.y - margin < o.y + o.h and o.y - margin < self.y + self.h)

    def corners(self):
        x2, y2 = self.x + self.w - 1, self.y + self.h - 1
        return {(self.x, self.y), (x2, self.y), (self.x, y2), (x2, y2)}


class DungeonMixin:
    """Building levels: rooms, crypts and caves, what lives on them, and what the player can see."""

    def new_level(self):
        self.depth += 1
        env = self.env = environment(self.depth)
        while True:
            self.tiles = [[ROCK] * MAP_W for _ in range(MAP_H)]
            if env['layout'] == 'caves':
                rooms = self.make_caves(env['pools'])
            elif env['layout'] == 'glacier':
                rooms = self.make_caves(env['pools'], open_chance=0.6,
                                        crevasses=random.randint(1, 2))
            elif env['layout'] == 'crypts':
                rooms = self.make_crypts()
            else:
                rooms = self.make_rooms()
            if len(rooms) >= 4:
                break
        self.rooms = rooms
        self.explored = [[False] * MAP_W for _ in range(MAP_H)]
        self.monsters, self.items, self.npcs = [], [], []
        self.searched = set()                         # rooms that gave up their hidden item
        p = self.player
        p.x, p.y = self.free_spot(rooms[0])

        others = rooms[1:]
        boss = boss_at(self.depth)
        if boss:
            # the boss waits in the room farthest from the start; no stairs until it falls
            sx, sy = rooms[0].center()
            lair = max(others, key=lambda r: abs(r.center()[0] - sx) + abs(r.center()[1] - sy))
            tpl = next(t for t in MONSTERS if t[1] == boss)
            m = Monster(tpl, *self.free_spot(lair), self.depth)
            m.awake = True
            self.monsters.append(m)
            others = [r for r in others if r is not lair] or others
        else:
            sx, sy = self.free_spot(random.choice(others))
            self.tiles[sy][sx] = STAIRS

        if self.depth % MERCHANT_EVERY == 0:
            if boss:
                self.add_npc('merchant', rooms[0])
            else:
                self.add_npc('merchant', spot=self.spot_near_stairs(sx, sy),
                             box=(sx - 3, sy - 3, sx + 3, sy + 3))
        quiet = []                                   # rooms kept free of monsters
        if self.depth == 1:
            self.add_npc('sage', rooms[0])
        elif boss:
            if 'healer' not in self.npcs_met:
                self.add_npc('healer', rooms[0])     # one last chance to patch up first
        elif 'bard' not in self.npcs_met and self.depth >= self.bard_depth:
            quiet.append(random.choice(rooms))
            self.add_npc('bard', quiet[-1])
        elif random.random() < NPC_CHANCE:
            kinds = [k for k, (weight, first, layout) in NPC_SPAWNS.items()
                     if self.depth >= first and layout in (None, env['layout'])
                     and k not in self.npcs_met]
            if kinds:
                kind = random.choices(kinds, [NPC_SPAWNS[k][0] for k in kinds])[0]
                quiet.append(random.choice(rooms))
                self.add_npc(kind, quiet[-1])

        others = [r for r in others if r not in quiet] or others
        eligible = self.eligible_monsters()
        for _ in range(5 + self.depth // 2 + random.randint(0, 3)):
            x, y = self.free_spot(random.choice(others))
            self.monsters.append(Monster(random.choice(eligible), x, y, self.depth))

        for _ in range(random.randint(3, 6)):
            self.place_item(self.random_item(), random.choice(rooms))
        if self.depth == env['depth'] and self.depth > 1:
            # every new environment hides one spell scroll; the Catacombs offer the light
            # that undoes the Bone King
            it = Item('scroll', 'HOLY LIGHT') if env['layout'] == 'crypts' else self.spell_scroll()
            self.place_item(it, random.choice(others))
        for _ in range(random.randint(1, 3)):
            gold = Item('gold', count=random.randint(3, 8 + self.depth * 4))
            self.place_item(gold, random.choice(rooms))
        self.place_traps()
        self.compute_fov()

    def eligible_monsters(self):
        return [t for t in MONSTERS if t[6] <= self.depth <= t[7] and 'boss' not in t[9]]

    def place_traps(self):
        p = self.player
        self.traps = {}
        kinds = self.env['traps']
        if boss_at(self.depth):
            kinds = [k for k in kinds if k != 'trapdoor']     # no falling past a boss
        spots = [(x, y) for y in range(MAP_H) for x in range(MAP_W)
                 if self.tiles[y][x] in (FLOOR, CORRIDOR) and not self.occupied(x, y)
                 and not self.item_at(x, y) and max(abs(x - p.x), abs(y - p.y)) > 3]
        n = self.depth // 3 + random.randint(0, 2)
        for pos in random.sample(spots, min(n, len(spots))):
            self.traps[pos] = Trap(random.choice(kinds))

    def add_npc(self, kind, room=None, spot=None, box=None):
        """Put a friendly character in a room, or on a spot with the box it may wander in."""
        if spot is None:
            spot = self.npc_spot(room)
            box = (room.x + 1, room.y + 1, room.x + room.w - 2, room.y + room.h - 2)
        npc = NPC(kind, *spot)
        npc.area = self.floor_area(spot, box)
        self.npcs_met.add(kind)
        if kind == 'merchant':
            npc.stock = [self.shop_item() for _ in range(random.randint(4, 6))]
        elif kind == 'arcanist':
            spells = [s for s, (depth, _price) in SPELLS.items() if depth <= self.depth + 1]
            npc.stock = random.sample(spells, min(3, len(spells)))
        self.npcs.append(npc)

    def spot_near_stairs(self, sx, sy):
        """A free floor tile a few steps from the stairs that doesn't cut off the way there."""
        dist = {(sx, sy): 0}
        q = deque([(sx, sy)])
        while q:
            x, y = q.popleft()
            if dist[(x, y)] >= 4:
                continue
            for dx, dy in DIRS.values():
                n = (x + dx, y + dy)
                if n not in dist and self.walkable(*n):
                    dist[n] = dist[(x, y)] + 1
                    q.append(n)
        spots = [(x, y) for (x, y), d in dist.items()
                 if d and self.tiles[y][x] == FLOOR and not self.occupied(x, y)]
        # two or three steps away is best; right next to the stairs only as a last resort
        spots.sort(key=lambda s: (dist[s] == 1, dist[s], random.random()))
        return next((s for s in spots if self.can_block(*s)), spots[0] if spots else (sx, sy))

    def npc_spot(self, room):
        """A free floor tile in the room where a character won't cut off the way past."""
        for _ in range(50):
            x, y = self.free_spot(room)
            if self.tiles[y][x] == FLOOR and self.can_block(x, y):
                return x, y
        return self.free_spot(room)

    def floor_area(self, start, box):
        """The floor tiles inside box (x0, y0, x1, y1) you can walk to from start without
        leaving the floor: where a character may wander."""
        x0, y0, x1, y1 = box
        area, q = {start}, deque([start])
        while q:
            x, y = q.popleft()
            for dx, dy in DIRS.values():
                n = (x + dx, y + dy)
                if (n not in area and x0 <= n[0] <= x1 and y0 <= n[1] <= y1
                        and self.walkable(*n) and self.tiles[n[1]][n[0]] == FLOOR):
                    area.add(n)
                    q.append(n)
        return area

    def shop_item(self):
        while True:
            it = self.random_item()
            if it.sub not in ('poison', 'confusion', 'aggravate monsters'):
                return it

    def make_rooms(self, max_rooms=9, widths=(6, 16), heights=(5, 8)):
        rooms = []
        for _ in range(300):
            if len(rooms) >= max_rooms:
                break
            w, h = random.randint(*widths), random.randint(*heights)
            x, y = random.randint(0, MAP_W - w - 1), random.randint(0, MAP_H - h - 1)
            r = Room(x, y, w, h)
            if any(r.overlaps(o, 2) for o in rooms):
                continue
            rooms.append(r)
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    if yy in (y, y + h - 1):
                        self.tiles[yy][xx] = HWALL
                    elif xx in (x, x + w - 1):
                        self.tiles[yy][xx] = VWALL
                    else:
                        self.tiles[yy][xx] = FLOOR
        self.corners = set().union(*(r.corners() for r in rooms)) if rooms else set()
        rooms.sort(key=lambda r: r.center()[0])
        for a, b in zip(rooms, rooms[1:]):
            self.tunnel(a, b)
        for _ in range(2):
            if len(rooms) > 2:
                self.tunnel(*random.sample(rooms, 2))
        return rooms

    def make_crypts(self):
        """The Catacombs: tombs laid out on a 5x2 grid, each joined to its neighbors along
        the row, with a couple of passages between the rows. Big halls get rows of pillars."""
        grid = {}
        for gx in range(5):
            for gy in range(2):
                if random.random() < 0.15:
                    continue                          # an empty cell: a collapsed tomb
                w, h = random.randint(6, 13), random.randint(5, 8)
                x = gx * 16 + random.randint(1, 15 - w)
                y = random.randint(0, 9 - h) if gy == 0 else random.randint(11, 20 - h)
                grid[gx, gy] = Room(x, y, w, h)
        for r in grid.values():
            for yy in range(r.y, r.y + r.h):
                for xx in range(r.x, r.x + r.w):
                    self.tiles[yy][xx] = (HWALL if yy in (r.y, r.y + r.h - 1) else
                                          VWALL if xx in (r.x, r.x + r.w - 1) else FLOOR)
        rooms = list(grid.values())
        self.corners = set().union(*(r.corners() for r in rooms)) if rooms else set()
        rows = [[grid[gx, gy] for gx in range(5) if (gx, gy) in grid] for gy in (0, 1)]
        for row in rows:
            for a, b in zip(row, row[1:]):
                self.tunnel(a, b)
        if all(rows):
            for a in random.sample(rows[0], min(2, len(rows[0]))):
                b = min(rows[1], key=lambda r: abs(r.center()[0] - a.center()[0]))
                self.tunnel(a, b)
        for r in rooms:
            if r.w >= 9 and r.h >= 7:                 # rows of pillars, clear of the doors
                for py in (r.y + 2, r.y + r.h - 3):
                    for px in range(r.x + 2, r.x + r.w - 2, 2):
                        if self.tiles[py][px] == FLOOR:
                            self.tiles[py][px] = PILLAR
        rooms.sort(key=lambda r: r.center()[0])
        return rooms

    def make_caves(self, pools, open_chance=0.56, crevasses=0):
        """Cellular-automaton caves dotted with pools (lava or icy water), optionally split
        by crevasses of icy water. Returns zones of the map that the rest of the code uses
        like rooms."""
        W, H = MAP_W, MAP_H
        cave = [[0 < x < W - 1 and 0 < y < H - 1 and random.random() < open_chance
                 for x in range(W)] for y in range(H)]
        for _ in range(5):
            cave = [[0 < x < W - 1 and 0 < y < H - 1 and
                     sum(not cave[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) < 5
                     for x in range(W)] for y in range(H)]
        pool_cells = set()
        for _ in range(crevasses):
            self.carve_crevasse(cave, pool_cells)
        open_cells = [(x, y) for y in range(H) for x in range(W) if cave[y][x]]
        for _ in range(random.randint(*pools)):
            x, y = random.choice(open_cells)
            for _ in range(random.randint(4, 14)):
                if cave[y][x]:
                    cave[y][x] = False
                    pool_cells.add((x, y))
                dx, dy = random.choice(list(DIRS.values()))
                if 0 < x + dx < W - 1 and 0 < y + dy < H - 1:
                    x, y = x + dx, y + dy
        # keep only the biggest connected cave so everything is reachable
        best, seen = set(), set()
        for start in open_cells:
            if start in seen or not cave[start[1]][start[0]]:
                continue
            region, q = {start}, deque([start])
            while q:
                x, y = q.popleft()
                for dx, dy in DIRS.values():
                    n = (x + dx, y + dy)
                    if n not in region and cave[n[1]][n[0]]:
                        region.add(n)
                        q.append(n)
            seen |= region
            if len(region) > len(best):
                best = region
        if len(best) < 650:
            return []
        near = lambda x, y: any((x + dx, y + dy) in best for dx, dy in DIRS.values())
        for y in range(H):
            for x in range(W):
                if (x, y) in best:
                    self.tiles[y][x] = FLOOR
                elif near(x, y):
                    self.tiles[y][x] = POOL if (x, y) in pool_cells else CAVE_WALL
        self.corners = set()
        zones = []
        for zx in range(0, W, 20):
            for zy in (0, 10):
                z = Room(zx, zy, 20, 11)
                cells = sum(self.tiles[y][x] == FLOOR for y in range(zy + 1, zy + 10)
                            for x in range(zx + 1, zx + 19))
                if cells >= 25:
                    zones.append(z)
        zones.sort(key=lambda r: r.center()[0])
        return zones

    def carve_crevasse(self, cave, pool_cells):
        """Cut a winding, two-wide crevasse from the top of the map to the bottom, crossed by
        a few narrow ice bridges."""
        W, H = MAP_W, MAP_H
        x = random.randint(14, W - 16)
        bridges = random.sample(range(2, H - 2), 3)
        for y in range(1, H - 1):
            if y in bridges:
                for bx in range(x - 3, x + 5):        # the bridge and solid ground at each end
                    cave[y][bx] = True
            else:
                for cx in (x, x + 1):
                    cave[y][cx] = False
                    pool_cells.add((cx, y))
            x = max(6, min(W - 8, x + random.choice((-1, 0, 0, 1))))

    def tunnel(self, a, b):
        """Dig a corridor between two rooms. Walls are expensive and may only be
        crossed head-on, so corridors make clean doorways instead of running
        along a wall."""
        start, goal = a.center(), b.center()
        dist, prev = {start: 0}, {}
        heap = [(0, start)]
        while heap:
            d, (x, y) = heapq.heappop(heap)
            if (x, y) == goal:
                break
            if d > dist[(x, y)]:
                continue
            here = self.tiles[y][x]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 < nx < MAP_W - 1 and 0 < ny < MAP_H - 1) or (nx, ny) in self.corners:
                    continue
                t = self.tiles[ny][nx]
                horizontal = dy == 0
                if (HWALL in (t, here) and horizontal) or (VWALL in (t, here) and not horizontal):
                    continue
                cost = 30 if t in (HWALL, VWALL) else 2 if t == ROCK else 1
                nd = d + cost + random.random() * 0.5
                if nd < dist.get((nx, ny), float('inf')):
                    dist[(nx, ny)] = nd
                    prev[(nx, ny)] = (x, y)
                    heapq.heappush(heap, (nd, (nx, ny)))
        node = goal
        while node in prev:
            x, y = node
            t = self.tiles[y][x]
            if t == ROCK:
                self.tiles[y][x] = CORRIDOR
            elif t in (HWALL, VWALL):
                self.tiles[y][x] = DOOR
            node = prev[node]

    def free_spot(self, room):
        for _ in range(500):
            x = random.randint(room.x + 1, room.x + room.w - 2)
            y = random.randint(room.y + 1, room.y + room.h - 2)
            if self.tiles[y][x] == FLOOR and not self.occupied(x, y) and not self.item_at(x, y):
                return x, y
        for y in range(room.y + 1, room.y + room.h - 1):
            for x in range(room.x + 1, room.x + room.w - 1):
                if self.tiles[y][x] == FLOOR and not self.occupied(x, y):
                    return x, y
        return room.center()

    def place_item(self, it, room):
        it.x, it.y = self.free_spot(room)
        self.items.append(it)

    def spell_scroll(self):
        """A rare scroll that teaches a spell, favoring spells the player doesn't know yet."""
        known = set(self.player.moves)
        spells =[s for s, (depth, _price) in SPELLS.items() if depth <= self.depth]
        return Item('scroll', random.choices(spells, [1 if s in known else 4 for s in spells])[0])

    def random_item(self):
        if random.random() < SPELL_SCROLL_CHANCE:
            return self.spell_scroll()
        roll = random.randint(1, 100)
        if roll <= 30:
            return Item('potion', random.choices(POTIONS, POTION_WEIGHTS)[0])
        if roll <= 58:
            return Item('scroll', random.choices(SCROLLS, SCROLL_WEIGHTS)[0])
        if roll <= 72:
            return Item('food')
        ench = random.choices([-1, 0, 1, 2], [2, 5, 3, 1])[0]
        if roll <= 86:
            return make_weapon(random.choice(WEAPONS)[0], ench)
        return make_armor(random.choice(ARMORS)[0], ench)

    # ------------------------------------------------------------------ fov
    def compute_fov(self):
        p, r = self.player, FOV_RADIUS
        self.visible = {(p.x, p.y)}
        for i in range(-r, r + 1):
            for tx, ty in ((p.x + i, p.y - r), (p.x + i, p.y + r),
                           (p.x - r, p.y + i), (p.x + r, p.y + i)):
                self.cast_ray(p.x, p.y, tx, ty)
        # light up walls next to visible floor so rooms look complete
        for x, y in list(self.visible):
            if self.tiles[y][x] in WALKABLE:
                for dx, dy in DIRS.values():
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < MAP_W and 0 <= ny < MAP_H and self.tiles[ny][nx] in WALLS:
                        self.visible.add((nx, ny))
        for x, y in self.visible:
            self.explored[y][x] = True

    def cast_ray(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
        err, x, y = dx + dy, x0, y0
        r2 = FOV_RADIUS * FOV_RADIUS + FOV_RADIUS
        while True:
            if not (0 <= x < MAP_W and 0 <= y < MAP_H):
                return
            if (x - x0) ** 2 + (y - y0) ** 2 > r2:
                return
            self.visible.add((x, y))
            if (x, y) != (x0, y0) and self.tiles[y][x] in OPAQUE:
                return
            if (x, y) == (x1, y1):
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
