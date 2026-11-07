"""
A small dungeon crawler in the spirit of Rogue (1980), with Pokemon-style
battles and friendly characters to talk to.

Descend through 20 levels in four environments: the Dungeons of Doom, the
Sunken Catacombs, the Ember Caverns and the Frozen Abyss. Defeat the Bone King
on depth 10, then the Frost Wyrm on depth 20 to claim the Amulet of Yendor.

Data modules: constants, world, monsters, moves, items, characters, sprites, text, player.
The Game class (game.py) is built from one mixin per part of the game: dungeon, actions,
inventory, battle, dialogue and ui. save.py saves and loads games; main.py starts one.
Co-op: hero.py holds what each player has, coop.py plays several heroes in one dungeon,
and net.py carries it between the host and the players' terminals.
"""
