"""WebSocket client ขนาดเล็ก (stdlib ล้วน) สำหรับต่อ TikFinity ที่ ws://127.0.0.1:21213/

TikFinity desktop เป็นตัวต่อกับ TikTok แล้วกระจายเหตุการณ์ออกมาในเครื่อง
ถ้า TikFinity ปิดอยู่ ตัวนี้จะลองต่อใหม่ทุก 5 วินาทีเอง
"""
import base64
import json
import os
import socket
import struct
import threading
import time
from urllib.parse import urlparse


class _Reader:
    def __init__(self, sock, buf=b""):
        self.sock, self.buf = sock, buf

    def read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("ปิดการเชื่อมต่อ")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out


def _send(sock, opcode, payload=b""):
    mask = os.urandom(4)
    head = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def _connect(url):
    u = urlparse(url)
    host, port, path = u.hostname, u.port or 80, u.path or "/"
    sock = socket.create_connection((host, port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                  f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("handshake ล้มเหลว")
        resp += chunk
    head, rest = resp.split(b"\r\n\r\n", 1)
    if b" 101" not in head.split(b"\r\n", 1)[0]:
        raise ConnectionError(head.split(b"\r\n", 1)[0].decode(errors="replace"))
    sock.settimeout(90)
    return sock, _Reader(sock, rest)


class TikFinityClient(threading.Thread):
    def __init__(self, url, on_message, on_status=None):
        super().__init__(daemon=True)
        self.url, self.on_message = url, on_message
        self.on_status = on_status or (lambda s: None)
        self.connected = False
        self.last_error = ""

    def run(self):
        while True:
            try:
                sock, reader = _connect(self.url)
                self.connected, self.last_error = True, ""
                self.on_status("connected")
                self._loop(sock, reader)
            except Exception as e:  # noqa: BLE001 — ต่อใหม่เสมอ
                self.last_error = str(e)
            if self.connected:
                self.connected = False
                self.on_status("disconnected")
            time.sleep(5)

    def _loop(self, sock, r):
        parts, msg_op = [], None
        while True:
            b1, b2 = r.read(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", r.read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", r.read(8))[0]
            mask = r.read(4) if b2 & 0x80 else None
            data = r.read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 0x8:
                raise ConnectionError("server ปิดการเชื่อมต่อ")
            if op == 0x9:
                _send(sock, 0xA, data)
                continue
            if op == 0xA:
                continue
            if op in (0x1, 0x2):
                parts, msg_op = [data], op
            elif op == 0x0:
                parts.append(data)
            if fin and msg_op == 0x1:
                text = b"".join(parts).decode("utf-8", errors="replace")
                parts, msg_op = [], None
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict):
                    self.on_message(msg)
