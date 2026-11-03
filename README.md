# คลังผลหวย

ผลหวยลาวพัฒนา ฮานอยปกติ และสลากกินแบ่งรัฐบาล พร้อมสถิติ ปฏิทิน และย้อนดูตามวัน

ข้อมูลผลหวยจาก [ผลหวย.com](https://xn--t3cmiit.com/)

## ทำงานอย่างไร

- `data/<หวย>.json` เก็บทุกงวดที่เคยดึงมาและสถิติ สะสมเพิ่มไปเรื่อยๆ ไม่หาย
- GitHub Actions (`.github/workflows/update-data.yml`) รัน `scripts/update.mjs` หลังเวลาหวยออก
  ดึง API เฉพาะหวยที่ถึงเวลาออกผลแล้ว แล้ว commit ไฟล์ข้อมูลกลับเข้า repo เอง
- หน้าเว็บ (`index.html`) อ่านจากไฟล์ใน `data/` ผู้ชมไม่ได้เรียก API เอง จึงไม่โดนจำกัดความถี่
  ถ้าเปิดหน้าเว็บโดยไม่มีไฟล์ข้อมูล จะใช้ API แทน

## ติดตั้งครั้งแรก (ผ่านหน้าเว็บ GitHub ไม่ต้องลงโปรแกรม)

1. สร้าง repository ใหม่ที่ <https://github.com/new> แนะนำให้เป็น **Public**
   (GitHub Pages ฟรีต้องเป็น public และ Actions ของ public repo ไม่เสียนาที)
2. ในหน้า repo กด **Add file → Upload files** แล้วลากไฟล์/โฟลเดอร์เหล่านี้ขึ้นไป
   - `index.html`, `README.md`, `.nojekyll`
   - โฟลเดอร์ `data`, `scripts`, `.github`
   - ไม่ต้องอัปโหลดโฟลเดอร์ `.claude`
   ถ้าโฟลเดอร์ `.github` ลากไม่ขึ้น ให้กด **Add file → Create new file** พิมพ์ชื่อ
   `.github/workflows/update-data.yml` แล้ววางเนื้อหาไฟล์ลงไปแทน
3. **Settings → Actions → General → Workflow permissions** เลือก **Read and write permissions** แล้ว Save
   (ให้ workflow commit ไฟล์ข้อมูลได้)
4. **Settings → Pages → Build and deployment** เลือก Source = **Deploy from a branch**,
   Branch = `main` / `(root)` แล้ว Save · รอ 1–2 นาที จะได้ลิงก์ `https://<ชื่อผู้ใช้>.github.io/<ชื่อ repo>/`
5. **Actions → อัปเดตผลหวย → Run workflow** ติ๊ก "ดึงทุกหวยทันที" แล้วกด Run
   เพื่อสร้าง/เติมไฟล์ข้อมูลครั้งแรก (โดยเฉพาะ `data/lao-lottery.json`)

## หลังจากนั้น

- workflow รันเองตามเวลาใน `update-data.yml` (เวลา cron เป็น UTC, ไทย = UTC+7)
  GitHub อาจเริ่มช้ากว่าที่ตั้งไว้ 5–30 นาที จึงตั้งรอบสำรองไว้ด้วย
- ดูผลการรันได้ที่แท็บ **Actions** ถ้าขึ้นสีแดงคือดึงไม่สำเร็จทุกหวยในรอบนั้น รอบถัดไปจะลองใหม่เอง
- GitHub จะหยุด workflow ตามเวลาอัตโนมัติถ้า repo ไม่มีความเคลื่อนไหว 60 วัน
  (commit ของ workflow เองช่วยให้ repo ยังมีความเคลื่อนไหว) ถ้าถูกหยุด เข้าแท็บ Actions แล้วกด Enable

## เพิ่มหวยชนิดอื่น

เพิ่มรายการเดียวกันทั้งใน `LOTTERIES` ของ `scripts/update.mjs` และของ `index.html`
(slug ตามรายชื่อใน <https://xn--t3cmiit.com/api/public/readme.md>, วัน/เวลาออกผลเป็นเวลาไทย)
หวยที่ API ไม่มี `/stats` ให้ตั้ง `apiStats: false` สคริปต์จะคำนวณสถิติเลข 2 ตัวจากงวดที่สะสมไว้เอง

## เงื่อนไขของแหล่งข้อมูล

ผลหวย.com ให้ใช้ API ฟรีโดยขอให้ใส่เครดิตลิงก์กลับ (มีอยู่แล้วที่ท้ายหน้าเว็บ)
และไม่อนุญาตให้นำไปใช้ประกอบเว็บพนันออนไลน์ การขึ้นเงินรางวัลให้ยึดประกาศทางการเสมอ
