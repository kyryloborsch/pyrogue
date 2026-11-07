"""Playing over the network: the host's server, the screens it draws for each player, and
the client that shows them in a player's terminal.

The host runs the whole game. Each player's terminal is a plain window onto it: the client
sends the keys pressed and draws the screens it gets back. Messages are lines of JSON."""

import curses
import json
import socket
import threading
import time
from collections import deque

from .coop import CoopGame, Disconnected, Stop
from .hero import Hero

DEFAULT_PORT = 7878
PROTOCOL = 1                     # bump when the messages or the game change in a way that
                                 # host and players must agree on
MAX_PLAYERS = 4
MAX_LINE = 1 << 16               # longest message accepted, in bytes

# attributes travel by meaning, so terminals with different curses libraries agree
FLAGS = [(curses.A_BOLD, 1), (curses.A_REVERSE, 2), (curses.A_DIM, 4), (curses.A_BLINK, 8)]
PAIR_SHIFT = (curses.A_COLOR & -curses.A_COLOR).bit_length() - 1
KEY_NAMES = {getattr(curses, n): n for n in dir(curses) if n.startswith('KEY_')}


def encode_attr(attr):
    code = ((attr & curses.A_COLOR) >> PAIR_SHIFT) << 4
    return code | sum(bit for flag, bit in FLAGS if attr & flag)


def decode_attr(code):
    pair, attr = code >> 4, 0
    if pair and curses.has_colors():
        attr = curses.color_pair(pair)
    return attr | sum(flag for flag, bit in FLAGS if code & bit)


class Link:
    """One end of a connection: JSON messages, one per line."""

    def __init__(self, sock):
        self.sock = sock
        self.rfile = sock.makefile('rb')
        self.wlock = threading.Lock()
        self.closed = False

    def send(self, msg):
        data = json.dumps(msg, separators=(',', ':')).encode() + b'\n'
        try:
            with self.wlock:
                self.sock.sendall(data)
        except OSError:
            self.close()

    def recv(self):
        """The next message, or None once the connection is gone."""
        try:
            line = self.rfile.readline(MAX_LINE)
            msg = json.loads(line) if line.endswith(b'\n') else None
        except (OSError, ValueError):
            msg = None
        if not isinstance(msg, dict):
            self.close()
            return None
        return msg

    def close(self):
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


# ---------------------------------------------------------------------- the server side
class VirtualScreen:
    """Stands in for a curses window on the host: the game draws on it, and it sends what it
    shows to the player's terminal. Its getch() waits for that player's keys, and lets the
    other players play meanwhile, so it must be called with cv held."""

    def __init__(self, link, cv, rows=24, cols=80):
        self.link, self.cv = link, cv
        self.rows, self.cols = rows, cols
        self.keys = deque()
        self.delay = -1
        self.stop_check = None       # raises Stop from getch() when this returns True
        self.closed = False
        self.blank()
        self.frame, self.sent = None, None
        self.frame_ready = threading.Event()
        threading.Thread(target=self.reader, daemon=True).start()
        threading.Thread(target=self.writer, daemon=True).start()

    # curses' window methods, as the game uses them
    def blank(self):
        self.chars = [[' '] * self.cols for _ in range(self.rows)]
        self.attrs = [[0] * self.cols for _ in range(self.rows)]

    def erase(self):
        self.blank()

    def addstr(self, y, x, s, attr=0):
        if not (0 <= y < self.rows and 0 <= x < self.cols):
            raise curses.error('addstr out of bounds')
        code = encode_attr(attr)
        room = self.cols - x
        for i, ch in enumerate(s[:room]):
            self.chars[y][x + i] = ch
            self.attrs[y][x + i] = code
        if len(s) > room:
            raise curses.error('addstr past the edge')

    def getmaxyx(self):
        return self.rows, self.cols

    def keypad(self, flag):
        pass

    def timeout(self, ms):
        self.delay = ms

    def refresh(self):
        frame = [(''.join(c), tuple(a)) for c, a in zip(self.chars, self.attrs)]
        self.frame = (self.rows, self.cols, frame)
        self.frame_ready.set()

    def getch(self):
        deadline = None if self.delay < 0 else time.monotonic() + self.delay / 1000
        while not self.keys:
            self.check()
            if deadline is None:
                self.cv.wait()
            else:
                left = deadline - time.monotonic()
                if left <= 0:
                    return -1
                self.cv.wait(left)
        self.check()
        return self.keys.popleft()

    # extras for co-op
    def check(self):
        if self.closed:
            raise Disconnected()
        if self.stop_check and self.stop_check():
            raise Stop()

    def pause(self, ms):
        """Wait a moment, letting the other players play (cv held)."""
        deadline = time.monotonic() + ms / 1000
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return
            self.cv.wait(left)

    def flush(self):
        self.keys.clear()

    def poke(self):
        """Wake getch() up as if the terminal was resized, so the game looks again."""
        self.keys.append(curses.KEY_RESIZE)
        self.cv.notify_all()

    def bye(self, text):
        """Say goodbye, and close the connection once it's sent."""
        self.refresh()
        self.closed = True
        self.frame_ready.set()
        self.goodbye = text

    # the threads that talk to the player
    def reader(self):
        while True:
            msg = self.link.recv()
            with self.cv:
                if msg is None:
                    self.closed = True
                    self.cv.notify_all()
                    self.frame_ready.set()
                    return
                if msg.get('t') == 'key':
                    k = self.key_of(msg)
                    if k is not None:
                        self.keys.append(k)
                elif msg.get('t') == 'size':
                    try:
                        size = int(msg.get('rows', 24)), int(msg.get('cols', 80))
                    except (TypeError, ValueError):
                        continue
                    self.rows, self.cols = fit(*size)
                    self.blank()
                    self.keys.append(curses.KEY_RESIZE)
                self.cv.notify_all()

    @staticmethod
    def key_of(msg):
        if isinstance(msg.get('k'), int) and 0 <= msg['k'] < 256:
            return msg['k']
        name = msg.get('n')
        if isinstance(name, str) and name.startswith('KEY_'):
            return getattr(curses, name, None)
        return None

    def writer(self):
        while True:
            self.frame_ready.wait()
            self.frame_ready.clear()
            frame = self.frame
            if frame and frame != self.sent:
                self.send_frame(frame)
            if self.closed:
                if getattr(self, 'goodbye', None) is not None:
                    self.link.send({'t': 'bye', 'text': self.goodbye})
                self.link.close()
                return

    def send_frame(self, frame):
        rows, cols, lines = frame
        old = self.sent[2] if self.sent and self.sent[:2] == (rows, cols) else None
        changed = {}
        for y, (text, attrs) in enumerate(lines):
            if old is None or y >= len(old) or old[y] != (text, attrs):
                changed[y] = runs(text, attrs)
        self.sent = frame
        self.link.send({'t': 'frame', 'rows': changed, 'size': [rows, cols]})


def fit(rows, cols):
    """A terminal size kept within reason."""
    return max(24, min(rows, 200)), max(80, min(cols, 400))


def runs(text, attrs):
    """A screen line as [text, attribute] runs, without the blank space at its end."""
    end = len(text)
    while end and text[end - 1] == ' ' and attrs[end - 1] == 0:
        end -= 1
    out, start = [], 0
    for i in range(1, end + 1):
        if i == end or attrs[i] != attrs[start]:
            out.append([text[start:i], attrs[start]])
            start = i
    return out


class Seat:
    """A player connected to the server."""

    def __init__(self, name, scr):
        self.name, self.scr = name, scr
        self.hero = None


class Server:
    """The host's game: a lobby until the host starts, then the co-op game."""

    def __init__(self, port=DEFAULT_PORT, seed=None):
        self.port, self.seed = port, seed
        self.cv = threading.Condition(threading.Lock())
        self.seats = []
        self.game = None
        self.sock = None

    def start(self):
        """Start listening. Raises OSError if the port can't be used."""
        self.sock = socket.create_server(('', self.port), reuse_port=False)
        threading.Thread(target=self.accept_loop, daemon=True).start()

    def accept_loop(self):
        while True:
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self.greet, args=(conn,), daemon=True).start()

    def greet(self, conn):
        conn.settimeout(10)
        link = Link(conn)
        hello = link.recv()
        if not hello or hello.get('t') != 'hello':
            link.close()
            return
        conn.settimeout(None)
        name = str(hello.get('name') or 'Rogue').strip()[:18] or 'Rogue'
        if hello.get('version') != PROTOCOL:
            return refuse(link, 'You and the host have different versions of the game. '
                                'Update both to the same one.')
        try:
            rows, cols = int(hello.get('rows', 24)), int(hello.get('cols', 80))
        except (TypeError, ValueError):
            rows, cols = 24, 80
        with self.cv:
            scr = VirtualScreen(link, self.cv, *fit(rows, cols))
            if self.game is None:
                if len(self.seats) >= MAX_PLAYERS:
                    return scr.bye(f'The game is full ({MAX_PLAYERS} players).')
                if any(s.name.lower() == name.lower() for s in self.seats):
                    return scr.bye(f'Someone called {name} is already here. Pick another name.')
                seat = Seat(name, scr)
                self.seats.append(seat)
            else:
                hero = next((h for h in self.game.heroes if h.name.lower() == name.lower()
                             and h.state == 'gone' and h.player.hp > 0), None)
                if hero is None or self.game.game_over:
                    return scr.bye('That game has already started. To get back in, join '
                                   'with the name your hero had.')
                seat = Seat(hero.name, scr)
                seat.hero = hero
                hero.scr = scr
                self.game.rejoin(hero)
            self.cv.notify_all()
            self.play(seat)

    def play(self, seat):
        """A player's thread: the lobby, then the game (cv held)."""
        try:
            while self.game is None:
                self.lobby(seat)
        except Disconnected:
            if self.game is None:
                self.seats.remove(seat)
                self.cv.notify_all()
                return
        if seat.hero is None:
            seat.hero = next(h for h in self.game.heroes if h.name == seat.name)
            seat.hero.scr = seat.scr
        hero = seat.hero
        seat.scr.stop_check = lambda: bool(self.game.game_over) and not hero.ending
        try:
            self.game.hero_loop(hero)
        except Exception as e:          # a bug: drop this player rather than stall the rest
            seat.scr.bye(f'Something went wrong in the game ({e.__class__.__name__}: {e}).')
            self.game.leave(hero)
            raise

    def lobby(self, seat):
        scr = seat.scr
        host = seat is self.seats[0]
        scr.erase()
        scr.addstr(2, 4, 'ROGUE-LIKE: co-op lobby', curses.A_BOLD)
        if host:
            scr.addstr(4, 4, f'Your friends can join with:  python3 rogue.py --join '
                             f'{local_ip()}:{self.port}'[:75])
        scr.addstr(6, 4, f'Players ({len(self.seats)}/{MAX_PLAYERS}):')
        for i, s in enumerate(self.seats):
            scr.addstr(8 + i, 6, f'{s.name}{"  (host)" if i == 0 else ""}')
        scr.addstr(14, 4, 'Press Enter to begin the adventure, or q to leave.' if host else
                   'Waiting for the host to begin... (q to leave)')
        scr.refresh()
        scr.timeout(1000)
        try:
            k = scr.getch()
        finally:
            scr.timeout(-1)
        if k in (ord('q'), ord('Q'), 27):
            scr.bye('You left the lobby.')
            raise Disconnected()
        if host and k in (10, 13, curses.KEY_ENTER):
            self.begin()

    def begin(self):
        heroes = [Hero(s.name, s.scr) for s in self.seats]
        for s, h in zip(self.seats, heroes):
            s.hero = h
        self.game = CoopGame(heroes, self.seed, self.cv)
        self.cv.notify_all()

    def players(self):
        """How many players are still connected."""
        with self.cv:
            return sum(1 for s in self.seats if not s.scr.closed) if self.game is None else \
                sum(1 for h in self.game.heroes if h.scr is not None and not h.scr.closed)


def refuse(link, text):
    link.send({'t': 'bye', 'text': text})
    link.close()


def local_ip():
    """This computer's address on the local network (no packets are sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
    except OSError:
        return socket.gethostname()


# ---------------------------------------------------------------------- the client side
def parse_address(text, default_port=DEFAULT_PORT):
    host, _, port = text.rpartition(':') if text.count(':') == 1 else (text, '', '')
    return host or text, int(port) if port else default_port


class Client:
    """A player's terminal: it shows what the host draws and sends the keys pressed."""

    def __init__(self, scr, host, port, name):
        self.scr, self.host, self.port, self.name = scr, host, port, name
        self.inbox = deque()
        self.lock = threading.Lock()

    def run(self):
        """Play until the game ends or the connection drops. Returns a message for the
        terminal, once curses is done."""
        try:
            sock = socket.create_connection((self.host, self.port), timeout=5)
        except OSError as e:
            return f'Could not reach a game at {self.host}:{self.port} ({e.strerror or e}).'
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        link = Link(sock)
        rows, cols = self.scr.getmaxyx()
        link.send({'t': 'hello', 'name': self.name, 'version': PROTOCOL,
                   'rows': rows, 'cols': cols})
        threading.Thread(target=self.read, args=(link,), daemon=True).start()
        self.scr.erase()
        self.scr.addstr(2, 4, f'Connecting to {self.host}:{self.port}...')
        self.scr.refresh()
        self.scr.timeout(30)
        try:
            while True:
                k = self.scr.getch()
                if k == curses.KEY_RESIZE:
                    self.scr.clear()
                    rows, cols = self.scr.getmaxyx()
                    link.send({'t': 'size', 'rows': rows, 'cols': cols})
                elif 0 <= k < 256:
                    link.send({'t': 'key', 'k': k})
                elif k in KEY_NAMES:
                    link.send({'t': 'key', 'n': KEY_NAMES[k]})
                while self.inbox:
                    with self.lock:
                        msg = self.inbox.popleft()
                    if msg is None:
                        return 'The connection to the game was lost.'
                    if msg.get('t') == 'bye':
                        return msg.get('text')
                    if msg.get('t') == 'frame':
                        self.draw(msg)
        finally:
            link.close()

    def read(self, link):
        while True:
            msg = link.recv()
            with self.lock:
                self.inbox.append(msg)
            if msg is None or msg.get('t') == 'bye':
                return

    def draw(self, msg):
        rows, cols = self.scr.getmaxyx()
        for y, line in msg.get('rows', {}).items():
            y = int(y)
            if y >= rows:
                continue
            self.scr.move(y, 0)
            self.scr.clrtoeol()
            x = 0
            for text, code in line:
                try:
                    self.scr.addstr(y, x, text[:max(0, cols - x)], decode_attr(code))
                except curses.error:
                    pass
                x += len(text)
        self.scr.refresh()
