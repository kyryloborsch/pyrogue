"""Playing over the network: the host's server, the screens it draws for each player, and
the client that shows them in a player's terminal.

The host runs the whole game. Each player's terminal is a plain window onto it: the client
sends the keys pressed and draws the screens it gets back. Messages are JSON.

Players connect straight to the host over TCP, or through the relay (a Cloudflare Worker,
see relay/) when the host can't open a port: then the host and every player connect out to
the relay with a WebSocket, and it passes the messages along."""

import base64
import curses
import json
import queue
import secrets
import socket
import threading
import time
import zlib
from collections import deque
from urllib.parse import urlsplit, urlunsplit

from .wsock import WebSocket, WebSocketError

from .coop import CoopGame, Disconnected, Stop
from .hero import Hero

DEFAULT_PORT = 7878
DEFAULT_RELAY = 'https://pyrogue-relay.pyrogue.workers.dev'   # the game's own relay (relay/)
PROTOCOL = 2                     # bump when the messages or the game change in a way that
                                 # host and players must agree on
MAX_PLAYERS = 4
MAX_LINE = 1 << 16               # longest message accepted, in bytes
RELAY_GAP = 0.03                 # seconds between messages sent through the relay (its quota)
SQUEEZE_OVER = 1024              # messages longer than this (in bytes) are sent compressed
CODE_LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   # room codes skip look-alikes (0/O, 1/I)

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
    """One end of a TCP connection: JSON messages, one per line. Every kind of link has
    send(msg), recv() (None once closed), ready() (the hello has arrived) and close()."""

    gap = 0                          # seconds to leave between screens

    def __init__(self, sock):
        self.sock = sock
        self.rfile = sock.makefile('rb')
        self.wlock = threading.Lock()
        self.closed = False

    def ready(self):
        self.sock.settimeout(None)

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


class WsLink:
    """A player's connection to the host through the relay."""

    gap = 0

    def __init__(self, ws):
        self.ws = ws
        self.closed = False

    def send(self, msg):
        self.ws.send(json.dumps(msg, separators=(',', ':')))

    def recv(self):
        text = self.ws.recv()
        if text is None:                # the relay may say why, like the host leaving
            self.closed = True
            return {'t': 'bye', 'text': self.ws.reason} if self.ws.reason else None
        try:
            msg = json.loads(text)
        except ValueError:
            msg = None
        if not isinstance(msg, dict):
            self.close()
            return None
        return msg

    def ready(self):
        pass

    def close(self):
        self.closed = True
        self.ws.close()


class RelayLink:
    """A player who joined through the relay, as the host sees them."""

    gap = RELAY_GAP

    def __init__(self, relay, pid):
        self.relay, self.pid = relay, pid
        self.inbox = queue.Queue()
        self.timeout = 10            # for the hello
        self.closed = False

    def feed(self, text):
        self.inbox.put(text)

    def send(self, msg):
        if not self.closed:
            self.relay.ws.send(f'{self.pid}|{json.dumps(msg, separators=(",", ":"))}')

    def recv(self):
        try:
            text = self.inbox.get(timeout=self.timeout)
            msg = json.loads(text) if text is not None else None
        except (queue.Empty, ValueError):
            msg = None
        if not isinstance(msg, dict):
            self.close()
            return None
        return msg

    def ready(self):
        self.timeout = None

    def close(self):
        if not self.closed:
            self.closed = True
            self.relay.ws.send(f'{self.pid}|-')
            self.relay.links.pop(self.pid, None)
            self.inbox.put(None)


def relay_url(base, code, role):
    """The relay's WebSocket address for a room. base is the Worker's address, as
    https://... (or http://... for wrangler dev)."""
    parts = urlsplit(base if '://' in base else f'https://{base}')
    scheme = {'https': 'wss', 'http': 'ws'}.get(parts.scheme, parts.scheme)
    path = f'{parts.path.rstrip("/")}/room/{code}'
    return urlunsplit((scheme, parts.netloc, path, f'role={role}', ''))


class Relay:
    """The host's connection to the relay: one WebSocket that carries every player who
    joined through it."""

    def __init__(self, server, base):
        self.server, self.base = server, base
        self.links = {}
        for _ in range(3):                     # a code someone else is using: pick another
            self.code = ''.join(secrets.choice(CODE_LETTERS) for _ in range(6))
            try:
                self.ws = WebSocket(relay_url(base, self.code, 'host'))
                break
            except WebSocketError as e:
                if 'already taken' not in str(e):
                    raise
        else:
            raise WebSocketError('could not get a room code')
        self.ws.keep_alive()
        self.lost = None                       # why the relay connection ended, if it did
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        while True:
            text = self.ws.recv()
            if text is None:
                self.lost = self.ws.reason or 'the connection to the relay was lost'
                for link in list(self.links.values()):
                    link.closed = True
                    link.feed(None)
                return
            pid, _, payload = text.partition('|')
            if payload == '+':
                link = self.links[pid] = RelayLink(self, pid)
                threading.Thread(target=self.server.greet, args=(link,), daemon=True).start()
            elif pid in self.links:
                link = self.links[pid]
                if payload == '-':
                    link.closed = True
                    self.links.pop(pid, None)
                    link.feed(None)
                else:
                    link.feed(payload)


# ---------------------------------------------------------------------- the server side
class VirtualScreen:
    """Stands in for a curses window on the host: the game draws on it, and it sends what it
    shows to the player's terminal. Its getch() waits for that player's keys, and lets the
    other players play meanwhile, so it must be called with cv held.

    Animations are played by the player's terminal, not here: pause() doesn't wait, it just
    tells the terminal how long to hold the frame before the next. The frames go out in order,
    as many as are ready in one message, with only the rows that changed."""

    def __init__(self, link, cv, rows=24, cols=80):
        self.link, self.cv = link, cv
        self.rows, self.cols = rows, cols
        self.keys = deque()
        self.delay = -1
        self.stop_check = None       # raises Stop from getch() when this returns True
        self.closed = False
        self.stale = False           # the game changed since this screen was drawn
        self.refreshable = False     # getch() should return KEY_RESIZE when it goes stale
        self.blank()
        self.shown = None            # (rows, cols, lines) as last queued for the terminal
        self.wait = 0                # ms the terminal should hold the last frame
        self.outbox = []             # frames to send: {'wait', 'rows', 'size'}
        self.olock = threading.Lock()
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
        lines = [(''.join(c), tuple(a)) for c, a in zip(self.chars, self.attrs)]
        size = (self.rows, self.cols)
        old = self.shown[2] if self.shown and self.shown[:2] == size else None
        rows = {y: runs(*line) for y, line in enumerate(lines) if old is None or old[y] != line}
        self.shown = (*size, lines)
        if not rows and not self.wait:
            return
        with self.olock:
            last = self.outbox[-1] if self.outbox else None
            if last and not self.wait and last['size'] == list(size):
                last['rows'].update(rows)            # nothing to see in between: one frame
            else:
                self.outbox.append({'wait': self.wait, 'rows': rows, 'size': list(size)})
            self.wait = 0
        self.frame_ready.set()

    def getch(self):
        deadline = None if self.delay < 0 else time.monotonic() + self.delay / 1000
        while not self.keys:
            self.check()
            if self.refreshable and self.stale:
                self.stale = False
                return curses.KEY_RESIZE
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
        """Hold the frame on screen for a moment: the player's terminal does the waiting."""
        self.wait += ms

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
                    self.shown = None
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
            with self.olock:
                frames, self.outbox = self.outbox, []
            if frames:
                self.link.send(squeeze({'t': 'frames', 'list': frames}))
                time.sleep(self.link.gap)           # what's drawn meanwhile goes out together
            if self.closed:
                if getattr(self, 'goodbye', None) is not None:
                    self.link.send({'t': 'bye', 'text': self.goodbye})
                self.link.close()
                return


def squeeze(msg):
    """A long message, compressed (the frames of a battle animation shrink a lot)."""
    data = json.dumps(msg, separators=(',', ':')).encode()
    if len(data) <= SQUEEZE_OVER:
        return msg
    return {'t': 'z', 'd': base64.b64encode(zlib.compress(data)).decode()}


def unsqueeze(msg):
    if msg and msg.get('t') == 'z':
        try:
            msg = json.loads(zlib.decompress(base64.b64decode(msg.get('d', ''))))
        except (ValueError, zlib.error):
            return None
    return msg if isinstance(msg, dict) else None


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

    def __init__(self, port=DEFAULT_PORT, seed=None, relay=None):
        self.port, self.seed, self.relay_base = port, seed, relay
        self.cv = threading.Condition(threading.Lock())
        self.seats = []
        self.game = None
        self.sock = None
        self.relay = None
        self.offline = None              # why there's no room on the relay, if there isn't

    def start(self):
        """Start listening, and open a room on the relay if there is one. Raises OSError if
        the port can't be used. Without the relay, the game is still open on this network."""
        self.sock = socket.create_server(('', self.port), reuse_port=False)
        threading.Thread(target=self.accept_loop, daemon=True).start()
        if self.relay_base:
            try:
                self.relay = Relay(self, self.relay_base)
            except WebSocketError as e:
                self.offline = str(e)

    def accept_loop(self):
        while True:
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.settimeout(10)                     # for the hello
            threading.Thread(target=self.greet, args=(Link(conn),), daemon=True).start()

    def greet(self, link):
        hello = link.recv()
        if not hello or hello.get('t') != 'hello':
            link.close()
            return
        link.ready()
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
        width = scr.getmaxyx()[1] - 6
        scr.addstr(2, 4, 'ROGUE-LIKE: co-op lobby', curses.A_BOLD)
        if self.relay:
            scr.addstr(3, 4, f'Room code: {self.relay.code}', curses.A_BOLD)
        if host:
            scr.addstr(4, 4, 'Your friends can join with:')
            scr.addstr(5, 6, f'python3 rogue.py --join {local_ip()}:{self.port}'
                             f'{"   (same network)" if self.relay else ""}'[:width])
            if self.relay:
                other = '' if self.relay_base == DEFAULT_RELAY else f' --relay {self.relay_base}'
                scr.addstr(6, 6, f'python3 rogue.py --join {self.relay.code}{other}'
                                 f'   (anywhere)'[:width])
            problem = self.offline or (self.relay and self.relay.lost)
            if problem:
                scr.addstr(7, 6, f'Online play is unavailable ({problem}); friends on this '
                                 f'network can still join.'[:width], curses.A_BOLD)
        scr.addstr(8, 4, f'Players ({len(self.seats)}/{MAX_PLAYERS}):')
        for i, s in enumerate(self.seats):
            scr.addstr(10 + i, 6, f'{s.name}{"  (host)" if i == 0 else ""}')
        scr.addstr(15, 4, 'Press Enter to begin the adventure, or q to leave.' if host else
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


def is_room_code(text):
    """A room code, rather than an address like 192.168.1.20 or localhost:7878."""
    return 4 <= len(text) <= 12 and text.isalnum() and text.lower() != 'localhost'


def connect_tcp(host, port):
    """A link straight to the host's game. Raises ConnectionError."""
    try:
        sock = socket.create_connection((host, port), timeout=5)
    except OSError as e:
        raise ConnectionError(f'Could not reach a game at {host}:{port} '
                              f'({e.strerror or e}).') from e
    sock.settimeout(None)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return Link(sock)


def connect_relay(base, code):
    """A link to the game in a room on the relay. Raises ConnectionError."""
    code = code.strip().upper()
    try:
        ws = WebSocket(relay_url(base, code, 'player'))
    except WebSocketError as e:
        raise ConnectionError(f'Could not join room {code} on the relay: {e}') from e
    ws.keep_alive()
    return WsLink(ws)


class Client:
    """A player's terminal: it shows what the host draws and sends the keys pressed.
    connect() opens the link to the game."""

    def __init__(self, scr, connect, where, name):
        self.scr, self.connect, self.where, self.name = scr, connect, where, name
        self.inbox = deque()
        self.lock = threading.Lock()
        self.frames = deque()        # frames to show, each after its wait
        self.drawn = 0               # when the last frame was shown (time.monotonic)

    def run(self):
        """Play until the game ends or the connection drops. Returns a message for the
        terminal, once curses is done."""
        self.scr.erase()
        self.scr.addstr(2, 4, f'Connecting to {self.where}...')
        self.scr.refresh()
        try:
            link = self.connect()
        except ConnectionError as e:
            return str(e)
        rows, cols = self.scr.getmaxyx()
        link.send({'t': 'hello', 'name': self.name, 'version': PROTOCOL,
                   'rows': rows, 'cols': cols})
        threading.Thread(target=self.read, args=(link,), daemon=True).start()
        goodbye = None
        try:
            while True:
                self.scr.timeout(self.next_frame_in())
                k = self.scr.getch()
                if k == curses.KEY_RESIZE:
                    self.scr.clear()
                    rows, cols = self.scr.getmaxyx()
                    link.send({'t': 'size', 'rows': rows, 'cols': cols})
                elif 0 <= k < 256:
                    link.send({'t': 'key', 'k': k})
                elif k in KEY_NAMES:
                    link.send({'t': 'key', 'n': KEY_NAMES[k]})
                while self.inbox and goodbye is None:
                    with self.lock:
                        msg = self.inbox.popleft()
                    if msg is None:
                        goodbye = 'The connection to the game was lost.'
                    elif msg.get('t') == 'bye':
                        goodbye = msg.get('text') or ''
                    elif msg.get('t') == 'frames':
                        self.frames.extend(f for f in msg.get('list', []) if isinstance(f, dict))
                self.play()
                if goodbye is not None and not self.frames:      # let the last frames show
                    return goodbye or None
        finally:
            link.close()

    def next_frame_in(self):
        """How long getch() may wait (ms) before the next frame is due."""
        if not self.frames:
            return 30
        due = self.drawn + self.frames[0].get('wait', 0) / 1000
        return max(0, min(30, int((due - time.monotonic()) * 1000)))

    def play(self):
        """Show the frames whose time has come: animations play here, at their own pace,
        however the messages happened to arrive."""
        shown = False
        while self.frames:
            now = time.monotonic()
            if now < self.drawn + self.frames[0].get('wait', 0) / 1000:
                break
            self.draw(self.frames.popleft())
            self.drawn, shown = now, True
        if shown:
            self.scr.refresh()

    def read(self, link):
        while True:
            msg = link.recv()
            if msg is not None and msg.get('t') == 'z':
                msg = unsqueeze(msg)
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
