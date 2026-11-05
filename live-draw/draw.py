"""ท่อสุ่มเลข (draw pipeline)

- ใช้ seed ลับ 32 ไบต์จาก `secrets` (CSPRNG) ต่อหนึ่ง session
- เลขแต่ละรอบ = HMAC-SHA256(seed, ลำดับรอบ) mod 10^digits
- ตอนเริ่ม session ประกาศ commit = SHA-256(seed) ไว้ก่อน
  พอจบ session ค่อยเปิดเผย seed ใครก็คำนวณย้อนได้ว่าเลขทุกรอบไม่ได้ถูกแก้ (ดู verify.py)

ไฟล์นี้เป็นที่เดียวที่สร้างเลขสุ่ม ท่อขอบคุณ (thanks.py) ห้าม import ไฟล์นี้
"""
import hashlib
import hmac
import secrets
import threading
import time


def number_from(seed: bytes, index: int, digits: int) -> str:
    mac = hmac.new(seed, str(index).encode(), hashlib.sha256).digest()
    n = int.from_bytes(mac, "big") % (10 ** digits)
    return str(n).zfill(digits)


class DrawEngine:
    def __init__(self, digits: int = 3, log=None):
        self.digits = digits
        self.log = log
        self._lock = threading.Lock()
        self.new_session()

    def new_session(self):
        with self._lock:
            self._seed = secrets.token_bytes(32)
            self.index = 0
            self.commit = hashlib.sha256(self._seed).hexdigest()
            self.session = time.strftime("%Y%m%d-%H%M%S") + "-" + self.commit[:8]
        if self.log:
            self.log.write({"type": "session_start", "session": self.session,
                            "commit": self.commit, "digits": self.digits})

    def draw(self, trigger: str, who: str | None = None, label: str = "") -> dict:
        with self._lock:
            self.index += 1
            idx = self.index
            number = number_from(self._seed, idx, self.digits)
            session = self.session
        rec = {"type": "draw", "session": session, "index": idx, "trigger": trigger,
               "who": who, "label": label, "number": number}
        if self.log:
            rec = self.log.write(rec)
        return rec

    def reveal(self) -> dict:
        """เปิดเผย seed ของ session ปัจจุบัน แล้วเริ่ม session ใหม่ทันที"""
        with self._lock:
            rec = {"type": "reveal", "session": self.session, "seed": self._seed.hex(),
                   "commit": self.commit, "draws": self.index}
        if self.log:
            rec = self.log.write(rec)
        self.new_session()
        return rec
