"""A small WebSocket client (RFC 6455), just enough to talk to the co-op relay with the
standard library alone: text messages, pings and closing."""

import base64
import hashlib
import os
import socket
import ssl
import struct
import threading
import time
from urllib.parse import urlsplit

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
MAX_MESSAGE = 1 << 20


class WebSocketError(Exception):
    pass


def unmask(mask, data):
    """XOR data with a 4-byte mask, repeated (masking and unmasking are the same)."""
    n = len(data)
    key = int.from_bytes((mask * (n // 4 + 1))[:n], 'big')
    return (int.from_bytes(data, 'big') ^ key).to_bytes(n, 'big')


class WebSocket:
    """A client WebSocket. send() may be called from any thread; recv() from one at a time."""

    def __init__(self, url, timeout=10):
        parts = urlsplit(url)
        if parts.scheme not in ('ws', 'wss'):
            raise WebSocketError(f'{url} is not a ws:// or wss:// address')
        secure = parts.scheme == 'wss'
        host, port = parts.hostname, parts.port or (443 if secure else 80)
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            if secure:
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        except ssl.SSLCertVerificationError as e:
            raise WebSocketError(
                f'could not check {host}\'s certificate ({e.verify_message}). With Python from '
                'python.org on a Mac, run "Install Certificates.command" in its folder') from e
        except OSError as e:
            raise WebSocketError(f'could not reach {host} ({e.strerror or e})') from e
        self.sock = sock
        self.wlock = threading.Lock()
        self.closed = False
        self.reason = ''
        path = (parts.path or '/') + (f'?{parts.query}' if parts.query else '')
        self.handshake(host if parts.port is None else f'{host}:{port}', path)
        sock.settimeout(None)

    def handshake(self, host, path):
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n'
                           f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                           'Sec-WebSocket-Version: 13\r\nUser-Agent: pyrogue\r\n\r\n').encode())
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = self.sock.recv(4096)
            if not chunk or len(head) > 65536:
                raise WebSocketError('the server hung up during the handshake')
            head += chunk
        head, self.buf = head.split(b'\r\n\r\n', 1)
        status, *lines = head.decode('latin-1').split('\r\n')
        headers = {k.strip().lower(): v.strip() for k, _, v in (h.partition(':') for h in lines)}
        if status.split()[1:2] != ['101']:
            raise WebSocketError(self.refusal(headers) or status)
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if headers.get('sec-websocket-accept') != accept:
            raise WebSocketError('the server answered with a bad handshake')

    def refusal(self, headers):
        """The text of the answer when the server turned the connection down."""
        body = self.buf
        try:
            if 'content-length' in headers:
                body = self.read(min(int(headers['content-length']), 4096))
            else:
                self.sock.settimeout(2)
                while len(body) < 4096 and (chunk := self.sock.recv(4096)):
                    body += chunk
        except (OSError, EOFError, ValueError):
            pass
        if headers.get('transfer-encoding') == 'chunked':     # size lines around each chunk
            body = b''.join(part for i, part in enumerate(body.split(b'\r\n')) if i % 2)
        return body.decode(errors='replace').strip()

    # ------------------------------------------------------------- frames
    def send_frame(self, opcode, payload):
        n = len(payload)
        if n < 126:
            head = struct.pack('!BB', 0x80 | opcode, 0x80 | n)
        elif n < 1 << 16:
            head = struct.pack('!BBH', 0x80 | opcode, 0x80 | 126, n)
        else:
            head = struct.pack('!BBQ', 0x80 | opcode, 0x80 | 127, n)
        mask = os.urandom(4)
        try:
            with self.wlock:
                self.sock.sendall(head + mask + unmask(mask, payload))
        except OSError:
            self.closed = True

    def send(self, text):
        if not self.closed:
            self.send_frame(0x1, text.encode())

    def read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError()
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def recv(self):
        """The next text message, or None once the connection is closed (see reason)."""
        message, kind = b'', None
        try:
            while True:
                b1, b2 = self.read(2)
                fin, opcode, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
                if n == 126:
                    n, = struct.unpack('!H', self.read(2))
                elif n == 127:
                    n, = struct.unpack('!Q', self.read(8))
                if n > MAX_MESSAGE:
                    raise WebSocketError('message too long')
                mask = self.read(4) if b2 & 0x80 else None
                payload = self.read(n)
                if mask:
                    payload = unmask(mask, payload)
                if opcode == 0x8:                               # close
                    if len(payload) > 2:
                        self.reason = payload[2:].decode(errors='replace')
                    self.send_frame(0x8, payload[:2])
                    break
                if opcode == 0x9:                               # ping
                    self.send_frame(0xA, payload)
                    continue
                if opcode == 0xA:                               # pong
                    continue
                if opcode in (0x1, 0x2):
                    kind, message = opcode, payload
                elif opcode == 0x0 and kind:
                    message += payload
                if fin and kind:
                    return message.decode(errors='replace')
        except (OSError, EOFError, ValueError, WebSocketError):
            pass
        self.close()
        return None

    def keep_alive(self, every=30):
        """Ping now and then, so a quiet connection isn't dropped along the way."""
        def ping():
            while not self.closed:
                time.sleep(every)
                if not self.closed:
                    self.send_frame(0x9, b'')
        threading.Thread(target=ping, daemon=True).start()

    def close(self):
        if not self.closed:
            self.send_frame(0x8, struct.pack('!H', 1000))
            self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
