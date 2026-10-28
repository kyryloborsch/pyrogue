"""The player moving around the map: walking, running, resting, traps and stairs."""

import random

from .constants import DIRS, DOOR, FINAL_DEPTH, FLOOR, POOL, STAIRS
from .items import HIDDEN_ITEM_CHANCE, Item
from .monsters import Monster, NOISE_MEMORY
from .text import an
from .world import BOSSES, boss_at


class ActionsMixin:
    """The player moving around the map: walking, running, resting, traps and stairs."""

    def player_move(self, dx, dy):
        p = self.player
        if p.frozen:
            self.msg('You are frozen solid and cannot move!')
            return True
        if p.paralyzed and random.random() < 0.3:
            self.msg('Your muscles lock up! You cannot move.')
            return True
        if p.confused and random.random() < 0.5:
            dx, dy = random.choice(list(DIRS.values()))
        nx, ny = p.x + dx, p.y + dy
        m = self.monster_at(nx, ny)
        if m:
            self.battle(m)
            return True
        npc = self.npc_at(nx, ny)
        if npc:
            self.talk(npc)
            return False
        if p.stuck:
            p.stuck -= 1
            self.msg('You are still climbing out of the pit.' if p.stuck else
                     'You climb out of the pit.')
            return True
        if not self.walkable(nx, ny):
            if self.tiles[ny][nx] == POOL:
                name, _color, warning, stumble = self.env['pool']
                if not p.confused:
                    self.msg(warning)
                    return False
                self.msg(stumble)
                self.hurt(sum(random.randint(1, 6) for _ in range(2)), name)
                if name == 'lava':
                    p.burn = max(p.burn, random.randint(3, 5))
                else:
                    p.frozen = max(p.frozen, random.randint(1, 3))
            return bool(p.confused)     # stumbling into a wall still costs a turn
        trap = self.traps.get((nx, ny))
        if trap and trap.found and not p.confused:
            if not self.confirm(f'Really step onto the {trap.name}? (y/n)'):
                return False
        p.x, p.y = nx, ny
        if trap:
            depth = self.depth
            self.spring_trap(trap)
            if self.game_over or (p.x, p.y) != (nx, ny):
                return self.depth == depth       # a fall to a new level costs no turn
        else:
            self.find_traps(1, min(0.35, 0.1 + 0.02 * p.level))
        if self.item_at(nx, ny):
            self.pickup(auto=True)
        elif self.tiles[ny][nx] == STAIRS:
            self.msg('There is a staircase down here.')
        return True

    # ---------------------------------------------------------------- traps
    def find_traps(self, radius, chance):
        p = self.player
        found = 0
        for (x, y), t in self.traps.items():
            if not t.found and max(abs(x - p.x), abs(y - p.y)) <= radius and random.random() < chance:
                t.found = True
                found += 1
                self.msg(f'You found {an(t.name)}!')
        return found

    def search(self):
        found = self.find_traps(2, min(0.9, 0.5 + 0.04 * self.player.level))
        if not self.find_hidden_item() and not found:
            self.msg('You search the area but find nothing.')
        return True

    def find_hidden_item(self):
        """Searching a room may turn up something tucked away, once per room."""
        p = self.player
        room = next((r for r in self.rooms if r.x < p.x < r.x + r.w - 1
                     and r.y < p.y < r.y + r.h - 1), None)
        if (room is None or self.tiles[p.y][p.x] != FLOOR or id(room) in self.searched
                or random.random() >= HIDDEN_ITEM_CHANCE):
            return False
        if random.random() < 0.3:
            it = Item('gold', count=random.randint(10, 20 + self.depth * 6))
        else:
            it = self.random_item()
        spots = [(x, y) for x, y in [(p.x + dx, p.y + dy) for dx, dy in [(0, 0), *DIRS.values()]]
                 if self.tiles[y][x] == FLOOR and not self.item_at(x, y)
                 and not self.monster_at(x, y) and not self.npc_at(x, y)]
        if not spots:
            return False
        self.searched.add(id(room))
        it.x, it.y = spots[0]
        self.items.append(it)
        self.msg('You find something hidden behind a loose stone!')
        if spots[0] == (p.x, p.y):
            self.pickup(auto=True)
        return True

    def hurt(self, dmg, cause):
        p = self.player
        p.hp = max(0, p.hp - dmg)
        if p.hp <= 0:
            self.die(cause)

    def spring_trap(self, trap):
        p = self.player
        careful = trap.found
        trap.found = True
        if random.random() < (0.6 if careful else min(0.3, 0.05 + 0.02 * p.level)):
            self.msg(f'You carefully step over the {trap.name}.' if careful else
                     f'You notice {an(trap.name)} just in time and leap aside!')
            return
        del self.traps[(p.x, p.y)]          # a trap that goes off is used up
        kind = trap.kind
        if kind == 'dart':
            self.msg('A small dart shoots out and hits you!')
            self.hurt(random.randint(2, 6) + self.depth // 2, 'a dart trap')
            if not self.game_over and random.random() < 0.6 and p.str > 3:
                p.str = max(3, p.str - random.randint(1, 2))
                self.msg('The dart was poisoned! You feel weaker.')
        elif kind == 'pit':
            self.msg('You fall into a spiked pit!')
            self.hurt(random.randint(3, 8) + self.depth // 2, 'a spiked pit')
            p.stuck = random.randint(2, 4)
        elif kind == 'fire':
            self.msg('A jet of flame bursts from the floor! You catch fire!')
            self.hurt(random.randint(3, 10) + self.depth // 2, 'a fire trap')
            p.burn = max(p.burn, random.randint(3, 6))
            scrolls = [i for i in p.pack if i.kind == 'scroll']
            if scrolls and not self.game_over:
                self.use_up(random.choice(scrolls))
                self.msg('One of your scrolls burns to ash!')
        elif kind == 'frost':
            self.msg('A blast of freezing air engulfs you!')
            self.hurt(random.randint(4, 12) + self.depth // 2, 'a frost trap')
            if not self.game_over:
                p.frozen = max(p.frozen, random.randint(2, 4))
                self.msg('You are frozen in place!')
        elif kind == 'teleport':
            p.x, p.y = self.free_spot(random.choice(self.rooms))
            p.confused += random.randint(4, 8)
            self.compute_fov()
            self.msg('You step on a teleport trap! The world blurs and spins around you.')
        elif kind == 'alarm':
            for m in self.monsters:
                m.alert(NOISE_MEMORY)
            eligible = self.eligible_monsters()
            for _ in range(random.randint(1, 2)):
                m = Monster(random.choice(eligible), *self.free_spot(random.choice(self.rooms)),
                            self.depth)
                m.alert(NOISE_MEMORY)
                self.monsters.append(m)
            self.msg('A loud alarm rings out! Monsters come running from all over the level.')
        elif kind == 'sleep':
            self.msg('A cloud of sleeping gas engulfs you. You fall asleep...')
            self.asleep, battles = True, self.battles
            for _ in range(random.randint(5, 10)):
                if self.game_over or self.battles != battles:   # attacked in your sleep
                    break
                self.end_turn()
            self.asleep = False
            if not self.game_over and self.battles == battles:
                self.msg('You wake up.')
        elif kind == 'trapdoor':
            self.msg('A trapdoor opens beneath you! You fall through...')
            self.new_level()
            self.hurt(random.randint(2, 8) + self.depth // 3, 'a fall')
            self.arrive()

    def run(self, dx, dy):
        p = self.player
        for step in range(80):
            if self.game_over or (step and (self.visible_monsters() or self.msgs)):
                break
            nx, ny = p.x + dx, p.y + dy
            if step and (self.monster_at(nx, ny) or self.npc_at(nx, ny)):
                break
            trap = self.traps.get((nx, ny))
            if trap and trap.found:
                if not step:
                    self.msg(f'There is {an(trap.name)} in the way.')
                break
            if not self.player_move(dx, dy):
                break
            self.end_turn()
            if self.tiles[p.y][p.x] in (DOOR, STAIRS):
                break

    def rest(self):
        p = self.player
        if self.visible_monsters():
            self.msg('You cannot rest with monsters nearby!')
            return
        for _ in range(500):
            if (p.hp >= p.max_hp and p.mp >= p.max_mp) or self.game_over or self.msgs \
                    or self.visible_monsters():
                break
            self.end_turn()

    def descend(self):
        p = self.player
        if self.tiles[p.y][p.x] != STAIRS:
            self.msg("I see no way down.")
            return False
        self.new_level()
        self.arrive()
        return False

    def arrive(self):
        self.msg(f'You are now on depth {self.depth} of {FINAL_DEPTH}.')
        if self.depth == self.env['depth'] and self.env['intro']:
            self.msg(self.env['intro'])
        boss = boss_at(self.depth)
        if boss:
            self.msg(BOSSES[boss]['arrive'])
        if self.npcs:
            self.msg('You sense a friendly presence on this floor (&).')
