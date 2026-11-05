"""ตัวกลางรับเหตุการณ์จาก TikFinity (หรือปุ่มจำลอง) แล้วแยกเข้า 2 ท่อ

    คอมเมนต์คำสำคัญ / ยอดไลก์ถึงเป้า / รอบตามเวลา / ปุ่มกดเอง  →  ท่อสุ่ม (ฟรีทุกคน)
    ของขวัญ / ติดตาม / แชร์                                     →  ท่อขอบคุณ (ไม่สุ่ม)

รูปแบบข้อความจาก TikFinity: {"event": "gift", "data": {...}}
ชื่อฟิลด์ใน data รองรับทั้งแบบเก่า (uniqueId, nickname อยู่ชั้นนอก)
และแบบใหม่ (data.user.uniqueId) เพราะ schema เปลี่ยนในปี 2026
"""
import threading
import time
from collections import OrderedDict, deque

from thanks import clean_name


def _get(d, *paths, default=None):
    for path in paths:
        cur = d
        ok = True
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur and cur[key] is not None:
                cur = cur[key]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class Hub:
    def __init__(self, engine, thanks, config: dict, clock=time.monotonic):
        self.engine = engine
        self.thanks = thanks
        self.cfg = config
        self.clock = clock
        self.lock = threading.Lock()
        self.draw_queue: deque = deque()
        self.thanks_queue: deque = deque()
        self._seen = OrderedDict()            # กันของขวัญซ้ำ
        self._cooldown: dict[str, float] = {}  # คอมเมนต์ต่อคน
        self._followed: set[str] = set()
        self.total_likes = 0
        self._last_milestone = 0
        self.next_timer_round = clock() + self.cfg["timer_round_minutes"] * 60
        self.stats = {"gifts": 0, "diamonds": 0, "draws": 0, "dropped": 0}

    # ---------- ภายใน ----------
    def _remember(self, key) -> bool:
        """คืน True ถ้าเห็น key นี้แล้ว"""
        if key in self._seen:
            return True
        self._seen[key] = True
        while len(self._seen) > 2000:
            self._seen.popitem(last=False)
        return False

    def _queue_draw(self, trigger, who=None, label=""):
        if len(self.draw_queue) >= self.cfg["max_draw_queue"]:
            self.stats["dropped"] += 1
            return None
        rec = self.engine.draw(trigger, who, label)
        self.draw_queue.append(rec)
        self.stats["draws"] += 1
        return rec

    def _queue_thanks(self, item):
        if len(self.thanks_queue) >= self.cfg["max_thanks_queue"]:
            self.stats["dropped"] += 1
            return None
        self.thanks_queue.append(item)
        return item

    # ---------- รับเหตุการณ์ ----------
    def handle(self, msg: dict):
        event = str(msg.get("event") or msg.get("type") or "").lower()
        data = msg.get("data") or {}
        uid = str(_get(data, "user.uniqueId", "uniqueId", "user.userId", "userId", default="?"))
        name = _get(data, "user.nickname", "nickname", "user.uniqueId", "uniqueId", default="ผู้ชม")
        with self.lock:
            if event == "gift":
                return self._on_gift(data, uid, name)
            if event == "chat":
                return self._on_chat(data, uid, name)
            if event == "like":
                return self._on_like(data)
            if event == "follow":
                if uid in self._followed:
                    return None
                self._followed.add(uid)
                return self._queue_thanks(self.thanks.follow(name))
            if event == "share":
                if self._remember(("share", uid, int(self.clock() // 60))):
                    return None
                return self._queue_thanks(self.thanks.share(name))
        return None

    def _on_gift(self, data, uid, name):
        gift_type = _int(_get(data, "giftType", "giftDetails.giftType", "gift.giftType"), 0)
        repeat_end = bool(_get(data, "repeatEnd", default=False))
        # ของขวัญที่ส่งต่อเนื่องได้ (giftType 1 เช่น Rose) มาหลายครั้งระหว่าง combo
        # นับเฉพาะครั้งสุดท้ายที่ repeatEnd = true
        if gift_type == 1 and not repeat_end:
            return None
        gift_id = _get(data, "giftId", "giftDetails.id", "gift.id", default="?")
        group = _get(data, "groupId", "msgId", "logId", default=None)
        count = max(1, _int(_get(data, "repeatCount", "repeat_count"), 1))
        if group is None:
            group = int(self.clock())  # ไม่มี id ให้ใช้ → กันซ้ำภายในวินาทีเดียวกัน
        if self._remember(("gift", uid, gift_id, group, count)):
            return None
        each = _int(_get(data, "diamondCount", "giftDetails.diamondCount", "gift.diamondCount"), 0)
        diamonds = each * count
        gift_name = _get(data, "giftName", "giftDetails.giftName", "gift.name", default="ของขวัญ")
        self.stats["gifts"] += 1
        self.stats["diamonds"] += diamonds
        return self._queue_thanks(self.thanks.gift(name, gift_name, count, diamonds))

    def _on_chat(self, data, uid, name):
        text = str(_get(data, "comment", "content", default=""))
        if not any(k in text for k in self.cfg["keywords"]):
            return None
        now = self.clock()
        if now < self._cooldown.get(uid, 0):
            return None
        self._cooldown[uid] = now + self.cfg["comment_cooldown_seconds"]
        return self._queue_draw("comment", who=clean_name(name))

    def _on_like(self, data):
        total = _get(data, "totalLikeCount", default=None)
        if total is not None:
            self.total_likes = max(self.total_likes, _int(total))
        else:
            self.total_likes += _int(_get(data, "likeCount", default=1), 1)
        step = self.cfg["like_milestone"]
        reached = (self.total_likes // step) * step
        if reached > self._last_milestone:
            self._last_milestone = reached
            return self._queue_draw("likes", label=f"ครบ {reached:,} ไลก์ · รอบรวมพลัง")
        return None

    # ---------- รอบตามเวลา / กดเอง ----------
    def tick(self):
        with self.lock:
            if self.clock() >= self.next_timer_round:
                self.next_timer_round = self.clock() + self.cfg["timer_round_minutes"] * 60
                return self._queue_draw("timer", label="รอบสุ่มตามเวลา")
        return None

    def manual_draw(self):
        with self.lock:
            return self._queue_draw("manual", label="รอบพิเศษจากแอดมิน")

    def snapshot(self):
        with self.lock:
            step = self.cfg["like_milestone"]
            return {
                "total_likes": self.total_likes,
                "next_like_milestone": (self.total_likes // step + 1) * step,
                "like_milestone": step,
                "timer_in": max(0, int(self.next_timer_round - self.clock())),
                "timer_total": self.cfg["timer_round_minutes"] * 60,
                "draw_queue": len(self.draw_queue),
                "thanks_queue": len(self.thanks_queue),
                "stats": dict(self.stats),
                "keywords": self.cfg["keywords"],
            }
