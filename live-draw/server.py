"""draw server — รัน:  py server.py
แล้วเปิด http://127.0.0.1:5181/control (แผงควบคุม)  และใส่ http://127.0.0.1:5181/overlay ใน OBS
"""
import json
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from draw import DrawEngine
from hub import Hub
from thanks import ThanksBuilder
from tikfinity import TikFinityClient

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


class JsonlLog:
    """log แบบต่อท้ายอย่างเดียว 1 บรรทัด = 1 เหตุการณ์"""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.lock = path, threading.Lock()

    def write(self, rec: dict) -> dict:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **rec}
        with self.lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


log = JsonlLog(ROOT / "logs" / "draws.jsonl")
engine = DrawEngine(CFG["digits"], log)
hub = Hub(engine, ThanksBuilder(CFG["gift_tiers"]), CFG)
recent: list = []          # รายการล่าสุดที่ขึ้นจอ (ให้แผงควบคุมดู)
clients: list[queue.Queue] = []
clients_lock = threading.Lock()


def broadcast(payload: dict):
    with clients_lock:
        for q in list(clients):
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass


def on_tiktok(msg):
    hub.handle(msg)


tik = TikFinityClient(CFG["tikfinity_url"], on_tiktok,
                      lambda s: broadcast({"type": "status", "tikfinity": s}))


def scheduler():
    """ปล่อยการ์ดขึ้นจอทีละใบตามจังหวะ ท่อสุ่มกับท่อขอบคุณมีคิวแยกกัน"""
    next_draw = next_thanks = next_state = 0.0
    while True:
        now = time.monotonic()
        hub.tick()
        if now >= next_draw and hub.draw_queue:
            with hub.lock:
                item = hub.draw_queue.popleft()
            broadcast(item)
            recent.insert(0, item); del recent[30:]
            next_draw = now + CFG["draw_display_seconds"]
        if now >= next_thanks and hub.thanks_queue:
            with hub.lock:
                item = hub.thanks_queue.popleft()
            broadcast(item)
            recent.insert(0, item); del recent[30:]
            next_thanks = now + CFG["thanks_display_seconds"]
        if now >= next_state:
            broadcast({"type": "state", **state()})
            next_state = now + 1
        time.sleep(0.1)


def state():
    return {**hub.snapshot(), "tikfinity": "connected" if tik.connected else "disconnected",
            "tikfinity_error": tik.last_error, "commit": engine.commit, "session": engine.session,
            "draw_index": engine.index, "disclaimer": CFG["disclaimer"]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/control"):
            return self._send(200, (ROOT / "control.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/overlay":
            return self._send(200, (ROOT / "overlay.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/state":
            return self._json({**state(), "recent": recent})
        if path == "/events":
            return self._sse()
        self._json({"error": "not found"}, 404)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q: queue.Queue = queue.Queue(maxsize=200)
        with clients_lock:
            clients.append(q)
        try:
            q.put_nowait({"type": "state", **state()})
            while True:
                try:
                    item = q.get(timeout=15)
                    data = json.dumps(item, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            with clients_lock:
                if q in clients:
                    clients.remove(q)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        if self.path == "/api/simulate":   # ปุ่มจำลองเหตุการณ์ ใช้ซ้อมโดยไม่ต้องไลฟ์จริง
            return self._json({"result": hub.handle(body)})
        if self.path == "/api/manual-draw":
            return self._json({"result": hub.manual_draw()})
        if self.path == "/api/reveal":
            rec = engine.reveal()
            broadcast({"type": "state", **state()})
            return self._json({"result": rec})
        self._json({"error": "not found"}, 404)


def main():
    port = CFG["port"]
    tik.start()
    threading.Thread(target=scheduler, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    print(f"draw server พร้อม  แผงควบคุม: http://127.0.0.1:{port}/control   overlay: http://127.0.0.1:{port}/overlay")
    print(f"commit ของ session นี้: {engine.commit}")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
