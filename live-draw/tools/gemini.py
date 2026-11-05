"""เรียก Gemini API (stdlib ล้วน) — คีย์อ่านจากตัวแปร GEMINI_API_KEY ของเครื่อง ไม่เก็บในไฟล์

  py tools/gemini.py models                         ดูรายชื่อโมเดลที่คีย์นี้ใช้ได้
  py tools/gemini.py image "prompt" out.png [--model M] [--ref in.png ...]
  py tools/gemini.py ask "คำถาม" [--image a.png ...] [--model M]
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "GEMINI_API_KEY")[0]
        except OSError:
            key = None
    if not key:
        sys.exit("ไม่พบ GEMINI_API_KEY ในเครื่อง")
    return key.strip()


def call(method, path, body=None, timeout=180):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-goog-api-key": api_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except Exception:  # noqa: BLE001
            pass
        sys.exit(f"HTTP {e.code}: {detail[:500]}")


def _img_part(path):
    p = Path(path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(p.read_bytes()).decode()}}


def _opt(args, name, default=None, many=False):
    vals, rest, i = [], [], 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            vals.append(args[i + 1]); i += 2
        else:
            rest.append(args[i]); i += 1
    args[:] = rest
    return vals if many else (vals[-1] if vals else default)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "models":
        res = call("GET", "/models?pageSize=200")
        for m in res.get("models", []):
            print(m["name"].removeprefix("models/"), "·", ",".join(m.get("supportedGenerationMethods", [])))
        return
    if cmd == "image":
        model = _opt(args, "--model", "gemini-3-pro-image")
        refs = _opt(args, "--ref", many=True)
        aspect = _opt(args, "--aspect")
        prompt, out = args[0], Path(args[1])
        parts = [_img_part(r) for r in refs] + [{"text": prompt}]
        gen = {"responseModalities": ["TEXT", "IMAGE"]}
        if aspect:
            gen["imageConfig"] = {"aspectRatio": aspect}
        res = call("POST", f"/models/{model}:generateContent",
                   {"contents": [{"parts": parts}], "generationConfig": gen})
        saved = False
        for part in res.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            data = part.get("inline_data") or part.get("inlineData")
            if data:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(base64.b64decode(data["data"]))
                print("saved", out); saved = True
            elif part.get("text"):
                print("text:", part["text"][:400])
        if not saved:
            sys.exit("ไม่ได้ภาพกลับมา: " + json.dumps(res, ensure_ascii=False)[:500])
        return
    if cmd == "ask":
        model = _opt(args, "--model", "gemini-2.5-pro")
        imgs = _opt(args, "--image", many=True)
        parts = [_img_part(p) for p in imgs] + [{"text": args[0]}]
        res = call("POST", f"/models/{model}:generateContent", {"contents": [{"parts": parts}]})
        for part in res.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if part.get("text"):
                print(part["text"])
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
