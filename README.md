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

`python3 -m pyrogue` works too. Options:

- `--seed WORD` starts a new game from a seed (any word or number). The same seed always builds the same 20 levels, with the same monsters, items and unidentified potion colors, however you play the levels before them. Without one, the game picks a random number. Either way, you can find the seed in the event log and the hall of fame.
- `--scores` prints the hall of fame and quits.
- `--name NAME` skips the name prompt.
- `--host` and `--join CODE` play co-op online (see [Co-op](#co-op)).

 Run it directly in a real terminal window. It won't start from an IDE output pane or any other environment without an interactive TTY, because curses fails with `cbreak() returned ERR` there.

## The dungeon

| Depths | Environment       | Layout                                   |
|--------|-------------------|------------------------------------------|
| 1–5    | Dungeons of Doom  | Classic rooms and corridors              |
| 6–10   | Sunken Catacombs  | Tombs laid out on a grid, with rows of pillars in the larger halls. The Bone King waits on depth 10 |
| 11–15  | Ember Caverns     | Open caves with lava pools               |
| 16–20  | Frozen Abyss      | Open ice caves split by crevasses of freezing water, crossed by narrow ice bridges. Now and then, walled chambers are set into the cave walls, each with a single door. The Frost Wyrm guards the Amulet on depth 20 |

Every floor except depth 1 and the last of each environment has a 1 in 4 chance of being that environment's variant. A message says so when you arrive, and the event log names the floor:

| Variant | Instead of | What's different |
|---------|------------|------------------|
| Unlit Halls | Dungeons of Doom | Pitch dark: you see only 2 squares around you |
| Collapsed Catacombs | Sunken Catacombs | More tombs have caved in, fallen rock chokes the rest, and there are more pits and trapdoors |
| Magma Rivers | Ember Caverns | Rivers of lava wind across the caves, crossed only by stone bridges |
| Ice Vaults | Frozen Abyss | Three or four walled vaults cut into the ice, and a single crevasse |

In the Dungeons of Doom and the Catacombs, the stairs down are in a room with a single door, and you have to pass through at least two other rooms to reach it. No room is ever left completely empty.

A boss level has no stairs down until the boss falls. The boss waits in that same far room. At half HP, each boss changes tactics.

## Features

- **Pokémon-style battles.** Bump into a monster to start a battle. Moves have types, accuracy, mana costs and status effects (burn, poison, freeze, sleep, paralyze, confusion). Some types are strong or weak against certain kinds of monsters, but a weak spot only deals 1.5× damage, so it helps without deciding the fight. On a turn you lose to a status (frozen, paralyzed, stumbling while confused or caught asleep), you go limp and take a third less damage. When someone is hit, their sprite jolts and flashes, and the damage floats up beside it (yellow for a critical hit or weak spot, other colors for burns, poison, frost and confusion).
- **Monster modifiers.** About one ordinary monster in seven is born different, and battle shows it before its name: TOUGH (1.25× HP), FIERCE (1.15× damage), ARMORED (+2 defense), SWIFT (hits a little more often and is a little harder to run from) or FEEBLE (a bit weaker all round). The stronger ones give more EXP, and a feeble one gives less. Bosses never get one.
- **Aimed attacks and weak spots.** STRIKE and POWER SMASH are aimed at a body part. The head is harder to hit but hurts more, and wings and tails are harder to hit too. Most monsters have one hidden weak spot that takes 1.5× damage. Once you hit it, the aim menu marks it for that kind of monster for the rest of the run. The undead resist normal blows and have no weak spot at all, while elementals and demons take 1.25× damage from them.
- **Mana.** Every spell costs MP from a single pool. STRIKE and POWER SMASH are free. MP slowly comes back as you explore and rest, refills when you level up, and can be restored with a potion of mana, a healer, or the MEDITATE spell.
- **One inventory (`i`).** Everything you carry is on one screen, sorted into Weapons, Armor, Rings, Potions, Scrolls and Food, with your spells on top. You can carry 30 things (a stack of potions, scrolls or food counts as one). Pick a line, or press an item's letter to jump straight to it, then choose what to do with it: drink, read, eat, wield, wear, put on, take off or drop. The inventory stays open after you use something, with what happened shown at the bottom. Each use still takes a turn, and the inventory closes by itself if a monster comes into view or attacks. The letters skip `i`, `x` and `z`, which close and choose in the inventory, and go on in capitals after `y`. A scroll of identify opens the same screen, showing only what you haven't identified yet. If you back out, you keep the scroll. In battle, BAG opens the same screen with your weapons, potions, scrolls and food, so you can swap weapons mid-fight, and potions can be thrown at the foe as well as drunk. Like using anything else from the BAG, it takes your turn. A thrown potion of poison or confusion works on the foe, healing heals it (but burns the undead), and once you see what a potion does, you know it. The line at the bottom says what the highlighted thing does, once you know.
- **Spells.** Rare spell scrolls teach 12 spells, from Fire Bolt and Heal to Chain Lightning (hits every foe), Bewilder (confuses a foe) and Meditate (restores MP). You can know 2 spells at once. To learn a third, you forget one, or keep the scroll for later. Half the magic weapons you find hold 1 or 2 extra spells while you wield them, and a rare ring of memory holds one more while you wear it. If you put such a weapon or ring away, the spells it held stay known but are sealed (they can't be cast) until you can hold them again. HEAL, MEDITATE and BARRIER also work outside battle: cast them from the inventory, which lists your spells with their MP costs and what they do.
- **Rings (`=`).** Rare rings give a bonus while you wear them, and you can wear two at once: protection (+defense), vitality (+max HP), wisdom (+max MP), power (+spell damage), might (+damage for STRIKE and POWER SMASH) and regeneration (HP comes back faster). The deeper you find one, the stronger it is. A ring of free action gives a 35% chance per point of power to shake off freezing, paralysis, confusion and sleeping gas, and at 100% nothing can hold you. Rarest of all is the ring of memory, which lets you hold one more spell. Rings stay on in battle; you put them on and take them off from the inventory.
- **Physical and magic weapons.** Swords, maces and spears make STRIKE and POWER SMASH hit harder, and those blows also get stronger as you level up (+1 damage, plus 1 more every 2 levels). Wands and staffs barely hurt in melee, but add their power to every attack spell. Enchanting a weapon improves whichever of these it does. The deeper you go, the better the weapons you find: stronger kinds turn up more often, and they come with +1 more enchantment for every 5 depths.
- **Event log.** Every message, including each line of battle text, goes into a scrollable log (`m`, or `M` during a battle), stamped with the turn number and grouped by depth. In a terminal wider than 104 columns or taller than 28 rows, the latest events also stay on screen in a side or bottom panel.
- **Friendly characters (`&`).** Walk into one to talk. They stroll around the room they're in, but hold still while you stand next to them, and they never block a passage.
  - The **sage** gives advice on depth 1.
  - A **merchant** buys and sells on every even depth, a couple of steps from the stairs down. You sell from your inventory screen, with the merchant's price next to each item. On a boss level, the merchant waits where you arrive instead.
  - Everyone else is rare: at most one turns up on a floor, in a room no monsters start in, and each appears only once per game. A **healer** also waits before a boss if you haven't met one yet.
  - **Healers** patch you up.
  - A **bard** always turns up somewhere on depths 2–5. The bard sings and sells a secret, and that secret is always which scroll is the scroll of identify (unless you already know it).
  - **Bram the Smith** improves your weapon and armor once each, for gold.
  - **Mage Oriel** teaches spells and restores your mana.
  - A hungry **hermit** trades a scroll for food.
  - In the Catacombs, a **restless spirit** whispers the weak spots of nearby monsters, then fades away.
- **Getting away.** A monster hunting you loses your trail once you've been out of its sight and more than 10 steps away for a few turns. It then roams the level until it spots you again, keeping mostly to the rooms rather than the corridors. An alarm or a scroll of aggravate monsters keeps them on your trail much longer.
- **Searching (`s`).** Searching can find hidden traps anywhere you can see. In a room it may also turn up a hidden item or some gold, at most once per room. It drops onto the floor somewhere in the room, for you to walk over and pick up.
- **Classic roguelike systems.** Unidentified potions and scrolls, hidden traps, hunger, weapons and armor you can enchant, and a tombstone when you die.

## Controls

Press `?` in the game for the full list.

```
Movement            7 8 9        . or 5               rest one turn
(arrows or numpad)   \|/         z                    rest until HP & MP full
                    4-@-6        s                    search for traps & items
                     /|\         >                    go down stairs
                    1 2 3
```

| Key       | Action                                  |
|-----------|---------------------------------------------------|
| `i`       | inventory: use, wield, wear or drop items, cast spells |
| `m`       | event log                               |
| `?`       | help                                    |
| `Q`       | save & quit, or abandon the run         |

You move with the arrow keys or the numpad; letter keys don't move you. To move diagonally with the arrow keys, press two of them together, like `↑` and `←` for up-left. The numpad's corner keys step diagonally too, with Num Lock on or off. You pick things up by walking onto them.

In menus, the arrow keys move the cursor, `Enter`/`Space`/`z` choose, and `Esc`/`x` go back. In battle, `M` opens the event log.

## Co-op

Up to 4 players can explore the same dungeon together, each from their own terminal, wherever they are. One player hosts, and the others join with the room code the host's lobby shows:

```sh
python3 rogue.py --host                    # opens a room, like K7QX2M
python3 rogue.py --join K7QX2M             # join it from anywhere
```

When everyone is in, the host presses Enter. Games go through the game's relay on Cloudflare (see below), so nobody has to open a port or know anyone's address. Friends on the host's own network can also join by address (`--join 192.168.1.20`, plus `:PORT` if the host used `--host 9000`), and that keeps working if the relay can't be reached. Everyone needs the same version of the game. `--seed` works for the host, and the host's computer keeps the hall of fame for everyone.

- **Nobody waits while exploring.** Every step you take moves the dungeon on, but only by a share of a turn: with three heroes on the map, the monsters take one step for every three steps the heroes take between them. You see the others move as they go. Resting (`z`) goes a turn at a time so the others can watch, and any key stops it.
- **Shared sight.** You see everything any hero can see, and the other heroes show as `@` in their own colors. In a terminal bigger than 80×24, a PARTY panel lists everyone's HP and what they're doing; `p` on the map shows the same.
- **Shared battles.** A battle pulls in every hero standing next to it, and walking into a monster that's already fighting joins its battle. Each hero picks a move every round, and once everyone in the fight has, the foes strike back at random heroes; the top line says who the battle is waiting for. Only the heroes in a battle wait for each other.
- **Tougher monsters.** Monsters are made for the party: each hero past the first gives them 60% more HP, 20% more damage and a better chance to hit. A foe fighting two or more heroes may use its special move on the whole party at once (a splash attack, 1 in 4, or 2 in 5 for a boss), and each hero takes 60% of the blow. Everyone in the fight gets the EXP for each monster beaten; the gold goes to whoever struck the last blow. RUN takes only you out of the fight.
- **Stairs.** A hero who goes down the stairs (or falls through a trapdoor) waits at the bottom until the rest of the party follows, then everyone arrives on the next depth together.
- **Falling.** A hero who dies watches the rest of the party play on. The run ends when the last hero falls, or for everyone when someone picks up the Amulet.
- **Leaving.** `Q` leaves the game. If your connection drops, or you leave while still alive, join again with the same name to take your hero back. Co-op games aren't saved: when the host quits, the game is over.

### The relay

The relay is a small Cloudflare Worker, in `relay/`, at `https://pyrogue-relay.pyrogue.workers.dev`. The host and every player connect out to it with a WebSocket, so it works from behind any home router, and it passes the messages between them. Each game is one room, kept by a [Durable Object](https://developers.cloudflare.com/durable-objects/). The relay never reads the game's messages, and the room closes when the host leaves. To keep play smooth and within Cloudflare's free plan, the host sends only the parts of the screen that changed, bundles what it draws into at most about 30 messages a second per player, and compresses the big ones. Animations, like a hit's shake and its floating damage number, come as one bundle with their timing and play on each player's own terminal, so the network can't make them stutter.

- `--relay off` plays only on your own network.
- `--relay URL` (or `PYROGUE_RELAY`) uses another relay, like your own copy. Deploy one with a free Cloudflare account and [wrangler](https://developers.cloudflare.com/workers/wrangler/): `cd relay`, `npx wrangler login`, then `npx wrangler deploy`, which prints its address. Everyone in the game has to use the same relay.
- To work on the relay, run `npx wrangler dev` in `relay/` and play with `--relay http://localhost:8787`.

## Saving

There is one saved game, and you only get one life. When you start the game with a save, you can continue it or begin a new game, which deletes the save.

- `Q` lets you save and quit, or abandon the run.
- The game also saves itself every time you reach a new depth.
- If you press Ctrl-C or close the terminal, the game saves where you were at the start of that turn.
- When you die, win or abandon the run, the save is deleted.

## Hall of fame

Every run that ends (by dying, winning or giving up) goes into `saves/scores.json`, next to the save. A run scores its gold plus 100 points for each depth reached, and 5000 more for escaping with the Amulet. The best 9 appear after the ending screen, with their dates, turns and seeds, so you can replay a good dungeon with `--seed`. The file keeps the best 100 runs.

The save lives in `saves/save.pickle`, in the game's folder next to `rogue.py`, and git ignores it. Set `PYROGUE_SAVE` to use a different file. A save from an older, incompatible version of the game is moved aside as `save.pickle.bad`, and a new game starts. Saves are Python pickles, so only load save files you made yourself.

## Map symbols

The help screen (`?`) lists the map symbols you've found so far, adding each one the first time it shows up on your map. All of them:

```
@ you      & friend   > stairs   ! potion   ? scroll   ) weapon   ] armor   = ring
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
| `hero.py` | What each player has for themselves: their character, messages, log and battle |
| `game.py` | The `Game` class: turns, monster movement and the keyboard |
| `dungeon.py` | Level generation and field of view |
| `actions.py` | Walking, running, resting, traps and stairs |
| `inventory.py` | The inventory screen, using and naming items, and learning spells |
| `battle.py` | Battles and the battle screen |
| `dialogue.py` | Conversations with the friendly characters |
| `ui.py` | Drawing the map, menus, the event log, help and the ending screen |
| `save.py` | Saving, loading and deleting the saved game |
| `scores.py` | The hall of fame |
| `coop.py` | Co-op: shared turns and battles, the stairs, falling and leaving |
| `net.py` | Co-op over the network: the host's server, each player's screen, the relay connection, and the client |
| `wsock.py` | A small WebSocket client, for reaching the relay with the standard library alone |
| `main.py` | Startup: command-line options, terminal checks, continuing a saved game, and the name prompt |

`relay/` holds the Cloudflare Worker that relays co-op games (`src/index.js`, deployed with `wrangler.toml`).

In co-op, the host runs the game and every player's terminal is just a window onto it. Each hero is played on its own thread, all under one lock, and `self.player`, `self.scr` and the rest belong to whichever hero's turn is being played.

`Game` is built from one mixin class per part of the game (`DungeonMixin`, `ActionsMixin`, `ItemsMixin`, `BattleMixin`, `TalkMixin` and `UIMixin`). Adding a monster, spell or item mostly means adding entries to its data tables (a monster also needs a sprite in `sprites.py`). A new character also needs a `talk_<kind>` method in `dialogue.py`.

## License

[GNU GPL v3](LICENSE)
