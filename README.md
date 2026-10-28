# pyrogue

A small terminal dungeon crawler in the spirit of *Rogue* (1980), with Pokémon-style turn-based battles and friendly characters to talk to. It's written in plain Python and only uses the standard library.

Descend through 20 procedurally generated levels across four environments, defeat the **Bone King** on depth 10 and the **Frost Wyrm** on depth 20, and escape with the **Amulet of Yendor**.

## Requirements

- Python 3.8+
- A terminal at least **80×24** characters
- `curses`: built in on macOS and Linux. On Windows, install it first with `pip install windows-curses`.

## Running

```sh
git clone https://github.com/kyryloborsch/pyrogue.git
cd pyrogue
python3 rogue.py
```

`python3 -m pyrogue` works too. Run it directly in a real terminal window. It won't start from an IDE output pane or any other environment without an interactive TTY, because curses fails with `cbreak() returned ERR` there.

## The dungeon

| Depths | Environment       | Layout                                   |
|--------|-------------------|------------------------------------------|
| 1–5    | Dungeons of Doom  | Classic rooms and corridors              |
| 6–10   | Sunken Catacombs  | Tombs laid out on a grid, with rows of pillars in the larger halls. The Bone King waits on depth 10 |
| 11–15  | Ember Caverns     | Open caves with lava pools               |
| 16–20  | Frozen Abyss      | Open ice caves split by crevasses of freezing water, crossed by narrow ice bridges. The Frost Wyrm guards the Amulet on depth 20 |

A boss level has no stairs down until the boss falls. At half HP, each boss changes tactics.

## Features

- **Pokémon-style battles.** Bump into a monster to start a battle. Moves have types, accuracy, mana costs and status effects (burn, poison, freeze, sleep, paralyze, confusion). Some types are strong or weak against certain kinds of monsters, but a weak spot only deals 1.5× damage, so it helps without deciding the fight. Easy fights can be skipped.
- **Aimed attacks and weak spots.** STRIKE and POWER SMASH are aimed at a body part. The head is harder to hit but hurts more, and wings and tails are harder to hit too. Every monster has one hidden weak spot that takes 1.5× damage. Once you hit it, the aim menu marks it for that kind of monster for the rest of the run.
- **Mana.** Every spell costs MP from a single pool. STRIKE and POWER SMASH are free. MP slowly comes back as you explore and rest, refills when you level up, and can be restored with a potion of mana, a healer, or the MEDITATE spell.
- **Spells.** Rare spell scrolls teach 12 spells, from Fire Bolt and Heal to Chain Lightning (hits every foe), Bewilder (confuses a foe) and Meditate (restores MP). You can know 4 spells at once. To learn a fifth, you forget one, or keep the scroll for later. `S` shows your moves and what your weapon adds to them.
- **Physical and magic weapons.** Swords, maces and spears make STRIKE and POWER SMASH hit harder. Wands and staffs barely hurt in melee, but add their power to every attack spell. Enchanting a weapon improves whichever of these it does.
- **Event log.** Every message, including each line of battle text, goes into a scrollable log (`m`, or `M` during a battle), stamped with the turn number and grouped by depth. In a terminal wider than 104 columns or taller than 28 rows, the latest events also stay on screen in a side or bottom panel.
- **Friendly characters (`&`).** Walk into one to talk. They stroll around the room they're in, but hold still while you stand next to them, and they never block a passage.
  - The **sage** gives advice on depth 1.
  - A **merchant** buys and sells on every even depth, a couple of steps from the stairs down. On a boss level, the merchant waits where you arrive instead.
  - Everyone else is rare: at most one turns up on a floor, in a room no monsters start in, and each appears only once per game. A **healer** also waits before a boss if you haven't met one yet.
  - **Healers** patch you up.
  - A **bard** always turns up somewhere on depths 2–5. The bard sings and sells a secret, and that secret is always which scroll is the scroll of identify (unless you already know it).
  - **Bram the Smith** improves your weapon and armor once each, for gold.
  - **Mage Oriel** teaches spells and restores your mana.
  - A hungry **hermit** trades a scroll for food.
  - In the Catacombs, a **restless spirit** whispers the weak spots of nearby monsters, then fades away.
- **Getting away.** A monster hunting you loses your trail once you've been out of its sight and more than 10 steps away for a few turns. It then roams the level until it spots you again. An alarm or a scroll of aggravate monsters keeps them on your trail much longer.
- **Searching (`s`).** Searching finds hidden traps nearby. In a room it may also turn up a hidden item or some gold, at most once per room.
- **Classic roguelike systems.** Unidentified potions and scrolls, hidden traps, hunger, weapons and armor you can enchant, and a tombstone when you die.

## Controls

Press `?` in the game for the full list.

```
Movement            y k u        Shift + direction    run
(or arrows/numpad)   \|/         . or 5               rest one turn
                    h-@-l        z                    rest until HP & MP full
                     /|\         s                    search for traps & items
                    b j n        >                    go down stairs
```

| Key       | Action             | Key | Action                          |
|-----------|--------------------|-----|---------------------------------|
| `,` / `g` | pick up item       | `i` | inventory                       |
| `q`       | quaff a potion     | `m` | event log                       |
| `r`       | read a scroll      | `A` | toggle auto-skip of easy battles |
| `e`       | eat food           | `?` | help                            |
| `w`       | wield a weapon     | `Q` | quit                            |
| `W`       | wear armor         | `S` | spells & weapon bonuses         |
| `d`       | drop an item       |     |                                 |

To move diagonally with the arrow keys, press two of them together, like `↑` and `←` for up-left.

In menus, arrows or `hjkl` move the cursor, `Enter`/`Space`/`z` choose, and `Esc`/`x` go back. In battle, `S` skips an easy fight and `M` opens the event log.

## Map symbols

```
@ you      & friend   > stairs   ! potion   ? scroll   ) weapon   ] armor
^ trap     : food     * gold     " Amulet   + door     # corridor
% cave wall           ~ lava / icy water   0 pillar
```

## Project layout

`rogue.py` just starts the game. The code lives in the `pyrogue` package:

| Module | What's in it |
|--------|--------------|
| `constants.py` | Map size, map tiles and keys |
| `world.py` | The four environments, the bosses and the traps |
| `monsters.py` | Monster stats, body parts and weak spots |
| `moves.py` | Battle moves, spells, type effectiveness and statuses |
| `items.py` | Weapons, armor, potions, scrolls and food |
| `characters.py` | The friendly characters, where they turn up, songs and lore |
| `sprites.py` | ASCII art for the battle screen |
| `text.py` | Colors and the highlighting of important words |
| `player.py` | The player character |
| `game.py` | The `Game` class: turns, monster movement and the keyboard |
| `dungeon.py` | Level generation and field of view |
| `actions.py` | Walking, running, resting, traps and stairs |
| `inventory.py` | Using, wielding and naming items, and the spellbook |
| `battle.py` | Battles and the battle screen |
| `dialogue.py` | Conversations with the friendly characters |
| `ui.py` | Drawing the map, menus, the event log, help and the ending screen |
| `main.py` | Startup: terminal checks and the name prompt |

`Game` is built from one mixin class per part of the game (`DungeonMixin`, `ActionsMixin`, `ItemsMixin`, `BattleMixin`, `TalkMixin` and `UIMixin`). Adding a monster, spell or item mostly means adding entries to its data tables (a monster also needs a sprite in `sprites.py`). A new character also needs a `talk_<kind>` method in `dialogue.py`.

## License

[GNU GPL v3](LICENSE)
