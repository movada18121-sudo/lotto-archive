"""ตรวจย้อนหลังว่าเลขทุกรอบมาจาก seed ที่ประกาศ commit ไว้จริง
รัน:  py verify.py            (อ่าน logs/draws.jsonl)
      py verify.py path\\to\\draws.jsonl
"""
import hashlib
import json
import sys
from pathlib import Path

from draw import number_from


def verify(lines):
    sessions = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        s = sessions.setdefault(r.get("session"), {"commit": None, "digits": 3, "draws": [], "seed": None})
        if r["type"] == "session_start":
            s["commit"], s["digits"] = r["commit"], r.get("digits", 3)
        elif r["type"] == "draw":
            s["draws"].append(r)
        elif r["type"] == "reveal":
            s["seed"] = r["seed"]
    report, all_ok = [], True
    for sid, s in sessions.items():
        if not s["seed"]:
            report.append(f"{sid}: ยังไม่เปิดเผย seed ({len(s['draws'])} รอบ) — ข้าม")
            continue
        seed = bytes.fromhex(s["seed"])
        ok = hashlib.sha256(seed).hexdigest() == s["commit"]
        bad = [d["index"] for d in s["draws"] if number_from(seed, d["index"], s["digits"]) != d["number"]]
        ok = ok and not bad
        all_ok &= ok
        report.append(f"{sid}: {'ผ่าน' if ok else 'ไม่ผ่าน'} — {len(s['draws'])} รอบ" + (f" รอบที่ผิด {bad}" if bad else ""))
    return all_ok, report


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "logs" / "draws.jsonl"
    ok, report = verify(path.read_text(encoding="utf-8").splitlines())
    print("\n".join(report) or "ไม่มีข้อมูล")
    sys.exit(0 if ok else 1)
