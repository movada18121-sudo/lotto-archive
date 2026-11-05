"""รัน:  py -m unittest -v   (ในโฟลเดอร์ live-draw)"""
import ast
import json
import unittest
from pathlib import Path

from draw import DrawEngine, number_from
from hub import Hub
from thanks import ThanksBuilder, clean_name
from verify import verify

HERE = Path(__file__).parent
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class NoDrawEngine:
    """ถ้าท่อของขวัญเผลอเรียกสุ่ม test จะพังทันที"""
    def draw(self, *a, **k):
        raise AssertionError("ท่อของขวัญห้ามเรียกการสุ่ม")


class MemLog:
    def __init__(self):
        self.lines = []

    def write(self, rec):
        self.lines.append(json.dumps(rec, ensure_ascii=False))
        return rec


def gift(uid, name, gift_type=2, count=1, end=True, group="g1", diamonds=1, gift_name="Rose"):
    return {"event": "gift", "data": {"uniqueId": uid, "nickname": name, "giftType": gift_type,
            "repeatCount": count, "repeatEnd": end, "groupId": group, "giftId": gift_name,
            "giftName": gift_name, "diamondCount": diamonds}}


class SeparationTests(unittest.TestCase):
    def test_gift_follow_share_never_draw(self):
        hub = Hub(NoDrawEngine(), ThanksBuilder(), CFG, FakeClock())
        for i in range(50):
            hub.handle(gift(f"u{i}", f"คน{i}", group=f"g{i}", diamonds=29999))
        hub.handle({"event": "follow", "data": {"uniqueId": "a", "nickname": "A"}})
        hub.handle({"event": "share", "data": {"uniqueId": "a", "nickname": "A"}})
        self.assertEqual(len(hub.draw_queue), 0)
        self.assertEqual(len(hub.thanks_queue), 52)

    def test_thanks_module_has_no_rng_import(self):
        tree = ast.parse((HERE / "thanks.py").read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertFalse(names & {"draw", "secrets", "random", "hub"}, names)

    def test_gift_size_only_changes_tier(self):
        tb = ThanksBuilder({"gold": 100, "grand": 1000})
        small = tb.gift("ก", "Rose", 1, 1)
        big = tb.gift("ก", "Lion", 1, 29999)
        self.assertEqual((small["tier"], big["tier"]), ("normal", "grand"))
        self.assertNotIn("number", big)


class GiftStreakTests(unittest.TestCase):
    def setUp(self):
        self.hub = Hub(NoDrawEngine(), ThanksBuilder(), CFG, FakeClock())

    def test_streak_counts_once_at_end(self):
        for c in range(1, 6):
            self.hub.handle(gift("u", "ก", gift_type=1, count=c, end=False))
        self.assertEqual(len(self.hub.thanks_queue), 0)
        self.hub.handle(gift("u", "ก", gift_type=1, count=5, end=True))
        self.hub.handle(gift("u", "ก", gift_type=1, count=5, end=True))  # ซ้ำ
        self.assertEqual(len(self.hub.thanks_queue), 1)
        self.assertEqual(self.hub.stats["diamonds"], 5)
        self.assertIn("x5", self.hub.thanks_queue[0]["text"])

    def test_new_schema_nested_user(self):
        self.hub.handle({"event": "gift", "data": {"user": {"uniqueId": "z", "nickname": "ใหม่"},
                         "giftDetails": {"giftType": 2, "diamondCount": 30, "giftName": "Doughnut", "id": 5},
                         "groupId": "x"}})
        self.assertEqual(self.hub.thanks_queue[0]["name"], "ใหม่")
        self.assertEqual(self.hub.stats["diamonds"], 30)


class DrawTriggerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.engine = DrawEngine(3, MemLog())
        self.hub = Hub(self.engine, ThanksBuilder(), CFG, self.clock)

    def chat(self, uid, text):
        return self.hub.handle({"event": "chat", "data": {"uniqueId": uid, "nickname": uid, "comment": text}})

    def test_keyword_and_cooldown(self):
        self.assertIsNone(self.chat("a", "สวัสดี"))
        self.assertIsNotNone(self.chat("a", "สาธุค่ะ"))
        self.assertIsNone(self.chat("a", "สาธุ"))            # ยังติด cooldown
        self.clock.t += CFG["comment_cooldown_seconds"] + 1
        self.assertIsNotNone(self.chat("a", "สาธุ"))
        self.assertEqual(len(self.hub.draw_queue), 2)

    def test_like_milestone(self):
        step = CFG["like_milestone"]
        self.hub.handle({"event": "like", "data": {"likeCount": step - 1}})
        self.assertEqual(len(self.hub.draw_queue), 0)
        self.hub.handle({"event": "like", "data": {"likeCount": 1}})
        self.hub.handle({"event": "like", "data": {"likeCount": 1}})
        self.assertEqual(len(self.hub.draw_queue), 1)

    def test_timer_round(self):
        self.assertIsNone(self.hub.tick())
        self.clock.t += CFG["timer_round_minutes"] * 60
        self.assertIsNotNone(self.hub.tick())

    def test_queue_cap(self):
        for i in range(CFG["max_draw_queue"] + 5):
            self.chat(f"u{i}", "สาธุ")
        self.assertEqual(len(self.hub.draw_queue), CFG["max_draw_queue"])
        self.assertEqual(self.hub.stats["dropped"], 5)


class RngTests(unittest.TestCase):
    def test_number_format(self):
        seed = bytes(32)
        self.assertEqual(number_from(seed, 1, 3), number_from(seed, 1, 3))
        for i in range(200):
            n = number_from(seed, i, 3)
            self.assertEqual(len(n), 3)
            self.assertTrue(n.isdigit())

    def test_commit_reveal_verifies(self):
        log = MemLog()
        e = DrawEngine(3, log)
        for _ in range(20):
            e.draw("manual")
        e.reveal()
        ok, report = verify(log.lines)
        self.assertTrue(ok, report)

    def test_tampered_log_fails(self):
        log = MemLog()
        e = DrawEngine(3, log)
        e.draw("manual")
        e.reveal()
        lines = [l.replace('"number": "', '"number": "x') if '"type": "draw"' in l else l for l in log.lines]
        ok, _ = verify(lines)
        self.assertFalse(ok)


class NameTests(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(clean_name("ป้าแดง 🌸"), "ป้าแดง")
        self.assertEqual(clean_name(""), "ผู้ชม")
        self.assertTrue(clean_name("ก" * 50).endswith("…"))
        self.assertEqual(clean_name("สมชาย​\n"), "สมชาย")


if __name__ == "__main__":
    unittest.main()
