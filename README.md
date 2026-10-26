# pyrogue

A small terminal dungeon crawler in the spirit of *Rogue* (1980), with Pokémon-style turn-based battles and friendly characters to talk to. It's one Python file that only uses the standard library.

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

Run it directly in a real terminal window. It won't start from an IDE output pane or any other environment without an interactive TTY, because curses fails with `cbreak() returned ERR` there.

## The dungeon

| Depths | Environment       | Layout                                   |
|--------|-------------------|------------------------------------------|
| 1–5    | Dungeons of Doom  | Classic rooms and corridors              |
| 6–10   | Sunken Catacombs  | Many small tomb rooms. The Bone King waits on depth 10 |
| 11–15  | Ember Caverns     | Open caves with lava pools               |
| 16–20  | Frozen Abyss      | Icy caves with freezing water. The Frost Wyrm guards the Amulet on depth 20 |

A boss level has no stairs down until the boss falls. At half HP, each boss changes tactics.

## Features

- **Pokémon-style battles.** Bump into a monster to start a battle. Moves have types, accuracy, PP and status effects (burn, poison, freeze, sleep, paralyze), and some types are strong or weak against certain kinds of monsters. Easy fights can be skipped.
- **Spells.** Rare spell scrolls teach new moves such as Fire Bolt, Heal, Thunder or Drain Life. You can know up to 6 moves.
- **Friendly characters (`&`).** Walk into one to talk. The sage gives advice, merchants sell items for gold, healers patch you up, and bards play for you.
- **Classic roguelike systems.** Unidentified potions and scrolls, hidden traps, hunger, weapons and armor you can enchant, and a tombstone when you die.

## Controls

Press `?` in the game for the full list.

```
Movement            y k u        Shift + direction    run
(or arrows/numpad)   \|/         . or 5               rest one turn
                    h-@-l        z                    rest until healed
                     /|\         s                    search for traps
                    b j n        >                    go down stairs
```

| Key       | Action             | Key | Action                          |
|-----------|--------------------|-----|---------------------------------|
| `,` / `g` | pick up item       | `i` | inventory                       |
| `q`       | quaff a potion     | `m` | message history                 |
| `r`       | read a scroll      | `A` | toggle auto-skip of easy battles |
| `e`       | eat food           | `?` | help                            |
| `w`       | wield a weapon     | `Q` | quit                            |
| `W`       | wear armor         |     |                                 |
| `d`       | drop an item       |     |                                 |

In menus, arrows or `hjkl` move the cursor, `Enter`/`Space`/`z` choose, and `Esc`/`x` go back. In battle, `S` skips an easy fight.

## Map symbols

```
@ you      & friend   > stairs   ! potion   ? scroll   ) weapon   ] armor
^ trap     : food     * gold     " Amulet   + door     # corridor
% cave wall           ~ lava / icy water
```

## License

[GNU GPL v3](LICENSE)
