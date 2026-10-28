#!/usr/bin/env python3
"""
A small dungeon crawler in the spirit of Rogue (1980), with Pokemon-style
battles and friendly characters to talk to. The game lives in the pyrogue
package; this script starts it. Run it in a terminal that is at least 80x24:

    python3 rogue.py

Press ? in the game for the list of commands.
"""
from pyrogue.main import run

if __name__ == '__main__':
    run()
