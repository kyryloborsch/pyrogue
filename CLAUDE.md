# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A terminal roguelike (curses, Python 3.8+, standard library only, no dependencies) with Pokémon-style turn-based battles. `README.md` is the player-facing manual and describes every mechanic in detail. Read it before changing gameplay, and update it in the same change when behavior changes (commits here routinely touch code and README together).

## Commands

```sh
python3 rogue.py               # play (same as python3 -m pyrogue)
python3 rogue.py --seed WORD   # new game from a fixed seed
python3 rogue.py --scores      # print the hall of fame and quit
python3 -m py_compile pyrogue/*.py   # quick syntax check
```

There are no tests, linter or build step. `rogue.py` needs a real interactive TTY of at least 80×24; it fails with `cbreak() returned ERR` when run from a non-TTY (like a tool's subprocess). To exercise logic without a terminal, import the modules directly (data modules have no curses dependency) and build a `Game` around a stub screen:

```python
import curses; curses.napms = lambda ms: None      # skip animation delays
from pyrogue import text
for c in ('white', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan'):
    text.COLORS[c] = 0                             # normally filled by init_colors()
from pyrogue.game import Game

class Scr:                                         # what Game calls on the screen
    def erase(self): pass
    def refresh(self): pass
    def addstr(self, *a): pass
    def getmaxyx(self): return (24, 80)
    def timeout(self, t): pass
    def getch(self): return ord(' ')               # or feed scripted keys

g = Game(Scr(), 'Test', seed='abc')                # g.new_level(), g.battle(m), g.play() ...
```

Write such scratch scripts outside the repo, and run them with `PYROGUE_SAVE` set (see below).

Saves go to `saves/save.pickle` (gitignored) or `$PYROGUE_SAVE`. Set `PYROGUE_SAVE` to a scratch path when testing so the user's real save isn't touched.

## Architecture

- **Data vs. logic.** `constants`, `world`, `monsters`, `moves`, `items`, `characters`, `sprites`, `text` and `player` are mostly data tables and small classes. Adding a monster, spell, item or trap is usually just a table entry; a monster also needs a sprite in `sprites.py`, and a new friendly character needs a `talk_<kind>` method in `dialogue.py`.
- **`Game` is a mixin stack** (`game.py`): `DungeonMixin` (dungeon.py), `ActionsMixin` (actions.py), `ItemsMixin` (inventory.py), `BattleMixin` (battle.py), `TalkMixin` (dialogue.py), `UIMixin` (ui.py). All share state on `self`, so a method in one mixin freely calls methods and attributes defined in another. All game state is plain attributes set in `Game.__init__`.
- **Turn loop.** `Game.play()` snapshots the game each turn, autosaves on reaching a new depth, then `read_key()` → `handle_key()`; `handle_key` returns True when the action used a turn, which triggers `end_turn()` (monsters act, NPCs act, `tick_player` handles hunger/regen/status countdowns, FOV recomputed). Bumping a monster calls `battle()`, which runs its own nested loop until `self.foes` is empty; `battle_world_turn` advances the world during it. `self.foes` being non-empty is how other code knows a battle is on.
- **Input.** Only the arrow keys and numpad move (`read_key()` turns two arrows pressed together into a diagonal); letter keys are commands, so don't map movement onto letters.
- **Moves and spells.** `player.moves` lists move names: the physical moves plus spells in the order learned. Spells cost MP. How many you can use is `player.spell_slots` (`MAX_SPELLS` plus slots on the wielded weapon and rings of memory), and spells past that stay sealed (`ready_spells`).
- **Messages.** `msg()` shows a message and records it in the event log; `record()` only logs.
- **Seeding is load-bearing.** Everything uses the global `random` module. `Game.__init__` seeds it with the run seed, and `new_level()` builds each depth with `random.seed(f'{seed}:{depth}')`, restoring the previous dice state afterwards, so a seed always produces the same 20 levels no matter how earlier levels were played. Keep all level-generation randomness inside `build_level()` and don't add separate `Random` instances or consume level dice elsewhere.
- **Saving** (`save.py`) pickles `vars(game)` (minus `scr`/`snapshot`) plus `random.getstate()`. Any new attribute on `Game` or a saved class changes the save shape: either give `Game.restore()` a default for it (as is done for `legend`, `floor_names`, `seed`) or bump `SAVE_VERSION`, which makes old saves get moved aside as `.bad`. Ctrl-C/hangup writes the snapshot from the start of the current turn.
- **UI.** `ui.py` draws the map, menus, event log panel (side or bottom, depending on terminal size), help and endings; `battle.py` draws its own battle screen and hit animations. `text.py` handles colors and keyword highlighting in messages.

## Style

Comments, docstrings, in-game text and the README are written in plain, short, non-technical English (see existing docstrings like "Go down to the next depth."). Match that tone.
