"""Starting the game: the terminal checks, the saved game and the name prompt."""

import argparse
import curses
import locale
import os
import random
import signal

from . import net, save, scores
from .game import Game
from .text import init_colors

TITLE = 'ROGUE-LIKE: the Dungeons of Doom'


class Hangup(Exception):
    """The terminal was closed, or the game was told to stop."""


def on_hangup(signum, frame):
    raise Hangup()


def ask_name(scr):
    curses.echo()
    curses.curs_set(1)
    scr.erase()
    scr.addstr(2, 4, TITLE, curses.A_BOLD)
    scr.addstr(4, 4, 'What is your name, adventurer? ')
    scr.refresh()
    try:
        name = scr.getstr(4, 35, 18).decode(errors='ignore').strip()
    except curses.error:
        name = ''
    curses.noecho()
    curses.curs_set(0)
    return name or 'Rogue'


def title_screen(scr, lines):
    scr.erase()
    scr.addstr(2, 4, TITLE, curses.A_BOLD)
    for i, line in enumerate(lines):
        scr.addstr(4 + i, 4, line)
    scr.refresh()
    return scr.getch()


def load_or_new(scr, seed=None, name=None):
    """Offer to continue the saved game. Returns a Game, or None to leave. A new game uses
    seed and name, if they were given."""
    if save.exists():
        try:
            state, dice = save.read()
        except save.SaveError as e:
            save.set_aside()
            title_screen(scr, [f'Your saved game could not be loaded: {e}.',
                               'It was moved aside, so a new game will begin.', '',
                               'Press any key.'])
        else:
            name, level, depth = save.summary(state)
            note = [] if seed is None else [f'The seed {seed} is only used for a new game.', '']
            while True:
                k = title_screen(scr, [
                    f'Saved game: {name}, level {level}, on depth {depth}.', '',
                    *note,
                    '  c) continue', '  n) new game (the saved game is lost)', '  q) leave'])
                if k in (ord('c'), ord('C'), 10, 13, ord(' ')):
                    random.setstate(dice)
                    return Game.restore(scr, state)
                if k in (ord('q'), ord('Q'), 27):
                    return None
                if k in (ord('n'), ord('N')):
                    k = title_screen(scr, [f'Really give up {name} for good? (y/n)'])
                    if k in (ord('y'), ord('Y')):
                        save.delete()
                        break
    return Game(scr, name or ask_name(scr), seed)


def main(scr, args):
    lines, cols = scr.getmaxyx()
    if lines < 24 or cols < 80:
        return f'Your terminal is {cols}x{lines}; please make it at least 80x24.'
    curses.curs_set(0)
    scr.keypad(True)
    init_colors()
    if args.host or args.join:
        return play_online(scr, args)
    game = load_or_new(scr, args.seed, args.name)
    if game is None:
        return None
    try:
        game.play()
    except (KeyboardInterrupt, Hangup):
        if not game.game_over and game.snapshot:
            save.write(game.snapshot)
            return 'Interrupted. Your game was saved as it was at the start of that turn.'
        if game.game_over and game.game_over[0] != 'saved':
            save.delete()
        return None
    if game.game_over[0] == 'saved':
        return f'Game saved. See you soon, {game.name}! Start the game again to continue.'
    return None


def coop_save_choice(scr, name):
    """Offer to continue the co-op save. Returns (saved state and dice or None, the name to
    play as), or None to leave."""
    if not save.exists(save.coop_path()):
        return None, name
    try:
        state, dice = save.read(save.coop_path())
    except save.SaveError as e:
        save.set_aside(save.coop_path())
        title_screen(scr, [f'Your saved co-op game could not be loaded: {e}.',
                           'It was moved aside, so a new game will begin.', '',
                           'Press any key.'])
        return None, name
    heroes = [h for h in state['heroes'] if h.state != 'dead' and h.player.hp > 0]
    party = ', '.join(f'{h.name} (level {h.player.level})' for h in heroes)
    while True:
        k = title_screen(scr, [f'Saved co-op game on depth {state["depth"]}:', f'  {party}', '',
                               '  c) continue', '  n) new game (the saved game is lost)',
                               '  q) leave'])
        if k in (ord('q'), ord('Q'), 27):
            return None
        if k in (ord('n'), ord('N')):
            k = title_screen(scr, ['Really give up the saved co-op game for good? (y/n)'])
            if k in (ord('y'), ord('Y')):
                save.delete(save.coop_path())
                return None, name
            continue
        if k not in (ord('c'), ord('C'), 10, 13, ord(' ')):
            continue
        mine = next((h for h in heroes if name and h.name.lower() == name.lower()), None)
        if mine:
            return (state, dice), mine.name
        if len(heroes) == 1:
            return (state, dice), heroes[0].name
        letters = 'abcd'
        k = title_screen(scr, ['Which hero are you?', ''] +
                         [f'  {c}) {h.name}' for c, h in zip(letters, heroes)])
        if 0 < k < 256 and chr(k).lower() in letters[:len(heroes)]:
            return (state, dice), heroes[letters.index(chr(k).lower())].name


def play_online(scr, args):
    """Host a co-op game (and play in it), or join one."""
    name = args.name
    saved = None
    if args.host:
        choice = coop_save_choice(scr, name)
        if choice is None:
            return None
        saved, name = choice
    name = name or ask_name(scr)
    if args.join and args.relay and net.is_room_code(args.join):
        return net.Client(scr, lambda: net.connect_relay(args.relay, args.join),
                          f'room {args.join.upper()} on the relay', name).run()
    if args.join:
        try:
            host, port = net.parse_address(args.join)
        except ValueError:
            return f'"{args.join}" is not an address. Try something like 192.168.1.20:7878.'
        return net.Client(scr, lambda: net.connect_tcp(host, port), f'{host}:{port}',
                          name).run()
    server = net.Server(args.host, args.seed, args.relay, saved)
    try:
        server.start()
    except OSError as e:
        return f'Could not host a game on port {args.host} ({e.strerror or e}).'
    try:
        message = net.Client(scr, lambda: net.connect_tcp('127.0.0.1', args.host),
                             'your game', name).run()
        # the game lives in this process: keep it going while the others read their endings
        scr.timeout(500)
        while server.game and server.players():
            k = title_screen(scr, ['Waiting for the other players to finish...',
                                   '(press q to close the game for everyone now)'])
            if k in (ord('q'), ord('Q')):
                break
    finally:
        server.close()
    if server.game and server.game.resumable():
        message = (message + '\n' if message else '') + \
            'The co-op game was saved. Host again with --host to pick it up.'
    return message


def parse_args():
    parser = argparse.ArgumentParser(prog='rogue.py', description=TITLE)
    parser.add_argument('--seed', help='start a new game from this seed (any word or number); '
                        'the same seed makes the same dungeon')
    parser.add_argument('--scores', action='store_true', help='show the hall of fame and quit')
    parser.add_argument('--host', nargs='?', type=int, const=net.DEFAULT_PORT, metavar='PORT',
                        help=f'host a co-op game for up to {net.MAX_PLAYERS} players '
                        f'(port {net.DEFAULT_PORT} unless you give one)')
    parser.add_argument('--join', metavar='HOST[:PORT] or CODE',
                        help='join a co-op game: by its room code, or at its address on your '
                        'network')
    parser.add_argument('--relay', metavar='URL',
                        default=os.environ.get('PYROGUE_RELAY') or net.DEFAULT_RELAY,
                        help='the co-op relay (a Cloudflare Worker, see relay/) that online games '
                        'go through, instead of the game\'s own; "off" plays only on your network')
    parser.add_argument('--name', help='your name, instead of being asked')
    args = parser.parse_args()
    if args.relay.lower() in ('off', 'none', 'no'):
        args.relay = None
    if args.host and args.join:
        parser.error('--host and --join can\'t be used together')
    return args


def run():
    args = parse_args()
    if args.scores:
        print('\n'.join(scores.table(scores.load())))
        return
    locale.setlocale(locale.LC_ALL, '')
    os.environ.setdefault('ESCDELAY', '25')
    for name in ('SIGHUP', 'SIGTERM'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), on_hangup)
    try:
        message = curses.wrapper(main, args)
    except (KeyboardInterrupt, Hangup):
        message = None
    if message:
        print(message)
