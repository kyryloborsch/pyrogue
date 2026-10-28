"""The player character."""

from .moves import SPELLS


def xp_needed(level):
    return 10 * 2 ** (level - 1)


class Player:
    def __init__(self):
        self.x = self.y = 0
        self.hp = self.max_hp = 16
        self.str = self.max_str = 16
        self.level = 1
        self.xp = 0
        self.gold = 0
        self.food = 1500
        self.pack = []
        self.weapon = None
        self.armor = None
        self.confused = 0
        self.stuck = 0               # turns left climbing out of a pit
        self.burn = 0                # turns left burning (hurts every turn)
        self.frozen = 0              # turns left frozen solid (can't act)
        self.paralyzed = 0           # turns left paralyzed (30% chance to lose each action)
        self.barrier = 0             # turns left of halved damage
        self.regen = 0
        self.mp = self.max_mp = 10   # mana that spells cost
        self.mana_regen = 0
        self.moves = ['STRIKE', 'POWER SMASH']    # plus up to MAX_SPELLS spells

    def cure(self):
        self.confused = self.burn = self.frozen = self.paralyzed = 0

    @property
    def ac(self):
        return self.armor.ac + self.armor.ench if self.armor else 0

    @property
    def str_bonus(self):
        return max(-3, (self.str - 16) // 2)

    @property
    def spells(self):
        return [m for m in self.moves if m in SPELLS]

    @property
    def weapon_dmg(self):
        """Damage range of a weapon blow before strength. Enchanting a magic weapon adds to
        its spell power instead."""
        w = self.weapon
        if not w:
            return 1, 3
        bonus = 0 if w.magic else w.ench
        return w.dmg[0] + bonus, w.dmg[1] + bonus

    @property
    def spell_power(self):
        """Extra damage a magic weapon adds to every attack spell."""
        w = self.weapon
        return w.magic + w.ench if w and w.magic else 0

    def restore_mp(self, amount=None):
        self.mp = self.max_mp if amount is None else min(self.max_mp, self.mp + amount)
