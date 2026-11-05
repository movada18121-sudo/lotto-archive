"""ท่อขอบคุณ (thanks pipeline)

ของขวัญ / การติดตาม / การแชร์ → ได้แค่คำขอบคุณกับเอฟเฟกต์
ไฟล์นี้ห้าม import draw.py, secrets หรือ random เด็ดขาด (มี test ตรวจ)
ขนาดของขวัญเปลี่ยนได้แค่ "ความอลังการ" ของการ์ดขอบคุณ ไม่มีผลกับเลขใดๆ
"""
import unicodedata

DROP_CATEGORIES = {"So", "Sk", "Cs", "Cc", "Cf", "Co", "Cn"}


def clean_name(name, maxlen: int = 20) -> str:
    """ตัด emoji/อักขระควบคุม ย่อให้สั้น เพื่อให้ TTS อ่านได้และกันชื่อยาวล้นจอ"""
    s = "".join(ch for ch in str(name or "") if unicodedata.category(ch) not in DROP_CATEGORIES)
    s = " ".join(s.split())
    if len(s) > maxlen:
        s = s[:maxlen].rstrip() + "…"
    return s or "ผู้ชม"


class ThanksBuilder:
    def __init__(self, tiers: dict | None = None):
        # tiers = {"gold": 100, "grand": 1000} หน่วยเป็น diamond รวมของ streak
        self.tiers = sorted((tiers or {"gold": 100, "grand": 1000}).items(), key=lambda kv: kv[1])

    def tier_for(self, diamonds: int) -> str:
        tier = "normal"
        for name, minimum in self.tiers:
            if diamonds >= minimum:
                tier = name
        return tier

    def gift(self, name, gift_name, count: int, diamonds: int) -> dict:
        n = clean_name(name)
        g = clean_name(gift_name, 24) if gift_name else "ของขวัญ"
        qty = f" x{count}" if count > 1 else ""
        return {"type": "thanks", "kind": "gift", "name": n, "tier": self.tier_for(diamonds),
                "text": f"ขอบคุณคุณ {n} ที่ส่ง {g}{qty}",
                "speech": f"ขอบคุณคุณ {n} ที่ส่ง {g} นะคะ สาธุ ขอให้มีความสุขค่ะ",
                "diamonds": diamonds}

    def follow(self, name) -> dict:
        n = clean_name(name)
        return {"type": "thanks", "kind": "follow", "name": n, "tier": "normal",
                "text": f"ขอบคุณคุณ {n} ที่กดติดตาม", "speech": f"ขอบคุณคุณ {n} ที่กดติดตามค่ะ"}

    def share(self, name) -> dict:
        n = clean_name(name)
        return {"type": "thanks", "kind": "share", "name": n, "tier": "normal",
                "text": f"ขอบคุณคุณ {n} ที่แชร์ไลฟ์", "speech": f"ขอบคุณคุณ {n} ที่แชร์ไลฟ์ค่ะ"}
