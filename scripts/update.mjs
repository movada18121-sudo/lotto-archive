// ดึงผลหวยจาก ผลหวย.com เฉพาะหวยที่ถึงเวลาออกผลแล้ว แล้วรวมเก็บลง data/<slug>.json
// รันโดย GitHub Actions (.github/workflows/update-data.yml) — ผู้ชมเว็บอ่านจากไฟล์นี้ ไม่ต้องเรียก API เอง
//   node scripts/update.mjs           ดึงเฉพาะหวยที่ถึงเวลาออกผลและยังไม่มีงวดใหม่
//   node scripts/update.mjs --force   ดึงทุกหวยทันที
import { readFile, writeFile, mkdir } from "node:fs/promises";

const API = "https://xn--t3cmiit.com/api/public";

// ต้องตรงกับ LOTTERIES ใน index.html · เวลาเป็นเวลาไทย · days = วันในสัปดาห์ (0 = อาทิตย์), dates = วันที่ของเดือน
// apiStats = API มี /stats ของหวยนี้ ถ้าไม่มีจะคำนวณสถิติเลขท้าย 2 ตัวเองจากงวดที่เก็บไว้
// backfill = เติมงวดเก่าที่ ผลหวย.com ให้ไม่ได้ (ย้อนได้แค่ 20 งวด) จากแหล่งทางการ
// history = รูปแบบเลขในไฟล์ history/<slug>.txt ที่จดเอง (ดู historyDraw)
const LOTTERIES = [
  { slug: "lao-lottery",     days: [1, 2, 3, 4, 5],          time: "20:30", apiStats: true, history: "four" },
  { slug: "hanoi-normal",    days: [0, 1, 2, 3, 4, 5, 6],    time: "18:30", apiStats: false },
  { slug: "thai-government", dates: [1, 16],                 time: "14:30", apiStats: true, backfill: "glo" },
];

const FORCE = process.argv.includes("--force");
const HOUR = 3600e3;
const sleep = ms => new Promise(r => setTimeout(r, ms));

// เวลาที่งวดถัดไปควรออกผล นับจากงวดล่าสุดที่เก็บไว้
function nextDue(lot, lastIso) {
  let t = Date.parse(lastIso + "T00:00:00Z");
  for (let i = 0; i < 62; i++) {
    t += 24 * HOUR;
    const d = new Date(t);
    const ok = lot.days ? lot.days.includes(d.getUTCDay()) : lot.dates.includes(d.getUTCDate());
    if (ok) return new Date(d.toISOString().slice(0, 10) + "T" + lot.time + ":00+07:00");
  }
  return new Date(0);
}

// โดน 429 (เรียกถี่เกินไป): รอ 30 วินาที แล้ว 60 วินาที แล้วลองใหม่ ก่อนยอมให้รอบนี้พลาด
async function getJson(path, waits = [30, 60]) {
  const res = await fetch(API + path, { headers: { Accept: "application/json" } });
  if (res.status === 429 && waits.length) {
    const sec = Math.max(Number(res.headers.get("retry-after")) || 0, waits[0]);
    console.log(`${path}: โดนจำกัดความถี่ รอ ${sec} วินาทีแล้วลองใหม่`);
    await sleep(sec * 1000);
    return getJson(path, waits.slice(1));
  }
  const json = await res.json().catch(() => null);
  if (!res.ok || !json || json.success === false) {
    throw new Error(`${path} -> ${res.status} ${(json && json.error) || ""}`.trim());
  }
  return json;
}

/* ---------- เติมงวดเก่าหวยรัฐบาลจาก API ของสำนักงานสลากกินแบ่งรัฐบาล (glo.or.th) ---------- */
const GLO = "https://www.glo.or.th/api/lottery/getLotteryResult";
const BACKFILL_PER_RUN = 48;   // งวดต่อรอบ เติมย้อนหลังทีละช่วง ไม่ยิงหนักในครั้งเดียว
// [คีย์ของ GLO, slug แบบ ผลหวย.com, ชื่อรางวัล] เก็บเฉพาะรางวัลที่หน้าเว็บใช้ ไฟล์จะได้ไม่ใหญ่
const GLO_PRIZES = [
  ["first",  "first-prize",       "รางวัลที่ 1"],
  ["near1",  "near-first-prize",  "รางวัลข้างเคียงรางวัลที่ 1"],
  ["last3f", "front-three-digit", "เลขหน้า 3 ตัว"],
  ["last3b", "last-three-digit",  "เลขท้าย 3 ตัว"],
  ["last2",  "last-two-digit",    "เลขท้าย 2 ตัว"],
];
const thaiDisplay = iso => "งวดวันที่ " + new Date(iso + "T00:00:00Z")
  .toLocaleDateString("th-TH", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

// ผลของวันที่ iso หรือ null ถ้าวันนั้นไม่มีการออกรางวัล
async function gloDraw(iso) {
  const [year, month, date] = iso.split("-");
  const res = await fetch(GLO, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ date, month, year }),
  });
  if (!res.ok) throw new Error(`GLO ${iso} -> ${res.status}`);
  const json = await res.json().catch(() => null);
  const r = json && json.response;
  const data = r && r.data;
  if (!data || !data.first || !(data.first.number || []).length) return null;
  const drawDate = r.date || iso;
  return {
    drawDate,
    displayName: thaiDisplay(drawDate),
    prizes: GLO_PRIZES.filter(([k]) => data[k] && data[k].number)
      .map(([k, slug, name]) => ({ slug, name, numbers: data[k].number.map(n => n.value) })),
  };
}

// งวดรัฐบาลตามกำหนดคือวันที่ 1 และ 16 แต่บางงวดเลื่อน (เช่น 30 ธ.ค., 17 ม.ค., 2 พ.ค.)
const isoUTC = t => new Date(t).toISOString().slice(0, 10);
function nominalPeriod(iso) {
  const t = Date.parse(iso + "T00:00:00Z");
  const d = new Date(t);
  const y = d.getUTCFullYear(), m = d.getUTCMonth();
  const options = [Date.UTC(y, m, 1), Date.UTC(y, m, 16), Date.UTC(y, m + 1, 1)];
  return options.reduce((a, b) => Math.abs(b - t) < Math.abs(a - t) ? b : a);
}
function previousPeriod(t) {
  const d = new Date(t);
  return d.getUTCDate() === 16
    ? Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)
    : Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - 1, 16);
}

// ย้อนจากงวดเก่าสุดที่มีไปทีละงวด หาไม่เจอติดกัน 4 งวด = ถึงต้นคลังของ GLO แล้ว
async function backfillGlo(data) {
  const have = new Set(data.draws.map(d => d.drawDate));
  let period = previousPeriod(nominalPeriod(data.draws[data.draws.length - 1].drawDate));
  let added = 0, misses = 0;
  for (let i = 0; i < BACKFILL_PER_RUN && misses < 4; i++) {
    let found = null;
    for (const offset of [0, 1, -1, -2, 2, -3]) {
      const iso = isoUTC(period + offset * 24 * HOUR);
      if (have.has(iso)) { found = "have"; break; }
      found = await gloDraw(iso);
      await sleep(1500);
      if (found) break;
    }
    if (found && found !== "have") {
      data.draws.push(found);
      have.add(found.drawDate);
      added++;
    }
    misses = found ? 0 : misses + 1;
    period = previousPeriod(period);
  }
  if (misses >= 4) data.backfillDone = true;
  data.draws.sort((a, b) => b.drawDate.localeCompare(a.drawDate));
  return added;
}

/* ---------- งวดย้อนหลังที่จดเอง (history/<slug>.txt) ----------
   บรรทัดละงวด: "2023-03-03 4268" · ปี พ.ศ. ก็ได้ · บรรทัดที่ขึ้นต้นด้วย # ถูกข้าม */
const TH_MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
  "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];

// แปลงบรรทัดเป็นงวดในรูปแบบเดียวกับ ผลหวย.com หรือคืนข้อความบอกว่าผิดตรงไหน
function historyDraw(lot, line) {
  const m = line.match(/^(\d{4})-(\d{2})-(\d{2})[\s,;]+(\d+)\s*$/);
  if (!m) return "รูปแบบไม่ถูกต้อง";
  const year = +m[1] > 2400 ? +m[1] - 543 : +m[1];
  const iso = `${year}-${m[2]}-${m[3]}`;
  const d = new Date(iso + "T00:00:00Z");
  if (isNaN(d) || isoUTC(d.getTime()) !== iso) return "วันที่ไม่มีจริง";
  if (lot.history === "four") {
    const n = m[4];
    if (n.length !== 4) return "ต้องเป็นเลข 4 ตัว";
    return {
      drawDate: iso,
      displayName: `งวดวันที่ ${d.getUTCDate()} ${TH_MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear() + 543}`,
      prizes: [
        { slug: "last-four-digit", name: "เลขท้าย 4 ตัว", numbers: [n] },
        { slug: "last-three-digit", name: "เลขท้าย 3 ตัว", numbers: [n.slice(1)] },
        { slug: "last-two-digit", name: "เลขท้าย 2 ตัว", numbers: [n.slice(2)] },
      ],
    };
  }
  return "หวยนี้ยังไม่รองรับไฟล์ history";
}

// เพิ่มเฉพาะวันที่ยังไม่มี · ถ้าวันเดียวกันเลขไม่ตรงกับข้อมูลเดิมจะเตือน แต่ไม่ทับ
async function mergeHistory(lot, data) {
  let text;
  try { text = await readFile(`history/${lot.slug}.txt`, "utf8"); } catch { return 0; }
  const byDate = new Map(data.draws.map(d => [d.drawDate, d]));
  let added = 0;
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;
    const draw = historyDraw(lot, line);
    if (typeof draw === "string") {
      console.warn(`history/${lot.slug}.txt บรรทัด ${i + 1}: ${draw} — "${line}"`);
      return;
    }
    const old = byDate.get(draw.drawDate);
    if (!old) {
      byDate.set(draw.drawDate, draw);
      added++;
    } else if (old.prizes[0] && old.prizes[0].numbers[0] !== draw.prizes[0].numbers[0]) {
      console.warn(`history/${lot.slug}.txt บรรทัด ${i + 1}: ${draw.drawDate} เลขไม่ตรงกับข้อมูลเดิม (${old.prizes[0].numbers[0]}) ใช้ของเดิม`);
    }
  });
  data.draws = [...byDate.values()].sort((a, b) => b.drawDate.localeCompare(a.drawDate));
  return added;
}

const slim = d => ({
  drawDate: d.drawDate,
  displayName: d.displayName,
  prizes: (d.prizes || []).map(p => ({ slug: p.slug, name: p.name, numbers: p.numbers })),
});

// สถิติเลขท้าย 2 ตัวในรูปแบบเดียวกับ /stats ของ API (draws เรียงใหม่ไปเก่า)
function computeStats(draws) {
  const map = new Map();
  draws.forEach((d, i) => {
    // ลาว/รัฐบาลใช้ last-two-digit ส่วนฮานอยเป็น two-digit-bottom (2 ตัวล่าง) จึงหาตามความยาวเลขสำรองไว้
    const prizes = d.prizes || [];
    const prize = prizes.find(p => p.slug === "last-two-digit")
      || prizes.find(p => (p.numbers || []).some(n => String(n).length === 2));
    const nums = prize ? prize.numbers : [];
    for (const n of nums) {
      const e = map.get(n);
      if (e) e.count++;
      else map.set(n, { number: n, count: 1, lastDate: d.drawDate, drawsSince: i });
    }
  });
  return {
    computed: true,
    dataset: {
      draws: draws.length,
      firstDate: draws.length ? draws[draws.length - 1].drawDate : null,
      lastDate: draws.length ? draws[0].drawDate : null,
    },
    prizes: [{
      prize: "last-two-digit",
      prizeName: "เลขท้าย 2 ตัว",
      draws: draws.length,
      numbers: [...map.values()].sort((a, b) => b.count - a.count || a.number.localeCompare(b.number)),
    }],
  };
}

async function update(lot) {
  const file = `data/${lot.slug}.json`;
  let data = { slug: lot.slug, updatedAt: null, draws: [], stats: null };
  try { data = JSON.parse(await readFile(file, "utf8")); } catch { /* ยังไม่มีไฟล์ */ }

  const save = async () => {
    data.updatedAt = new Date().toISOString();
    await writeFile(file, JSON.stringify(data) + "\n");
  };

  // หวยที่คำนวณสถิติเอง: ถ้ายังไม่มีสถิติ คำนวณจากงวดที่มีได้เลยโดยไม่ต้องเรียก API
  if (!lot.apiStats && !data.stats && data.draws.length) {
    data.stats = computeStats(data.draws);
    await save();
  }

  // รวมงวดที่จดเองใน history/ ทุกรอบ (ไม่เรียก API) แก้ไฟล์เมื่อไรก็เข้าในรอบถัดไป
  if (lot.history) {
    const n = await mergeHistory(lot, data);
    if (n) {
      console.log(`${lot.slug}: เพิ่มจาก history ${n} งวด · รวม ${data.draws.length} งวด`);
      await save();
    }
  }

  // เติมงวดเก่าทุกรอบจนครบ ไม่ขึ้นกับเวลาออกผล และไม่ใช้โควตาของ ผลหวย.com
  if (lot.backfill === "glo" && !data.backfillDone && data.draws.length) {
    try {
      const n = await backfillGlo(data);
      console.log(`${lot.slug}: เติมงวดเก่าจาก GLO ${n} งวด · รวม ${data.draws.length} งวด${data.backfillDone ? " · ครบแล้ว" : ""}`);
      await save();
    } catch (err) {
      console.warn(`${lot.slug}: เติมงวดเก่าไม่สำเร็จ — ${err.message}`);
    }
  }

  const latest = data.draws[0] && data.draws[0].drawDate;
  if (!FORCE && latest && Date.now() < nextDue(lot, latest).getTime()) {
    console.log(`${lot.slug}: ยังไม่ถึงเวลาออกผลงวดถัดไป (${nextDue(lot, latest).toISOString()})`);
    return false;
  }

  // ลำดับพารามิเตอร์นี้ตั้งใจ: URL แบบ ?lottery=…&limit=20 ของลาวพัฒนาเคยโดน 429 ค้างทั้งที่แบบนี้ยังใช้ได้
  const json = await getJson(`/results?limit=20&lottery=${lot.slug}`);
  const byDate = new Map(data.draws.map(d => [d.drawDate, d]));
  let added = 0;
  for (const d of json.data || []) {
    if (!d || !d.drawDate) continue;
    if (!byDate.has(d.drawDate)) added++;
    byDate.set(d.drawDate, slim(d));
  }
  if (!added && data.stats && !FORCE) {
    console.log(`${lot.slug}: ยังไม่มีงวดใหม่`);
    return false;
  }
  data.draws = [...byDate.values()].sort((a, b) => b.drawDate.localeCompare(a.drawDate));

  if (lot.apiStats) {
    await sleep(5000);
    try {
      const { attribution, ...stats } = await getJson(`/stats?lottery=${lot.slug}`);
      data.stats = stats;
    } catch (err) {
      console.warn(`${lot.slug}: ดึงสถิติไม่สำเร็จ ใช้ของเดิม — ${err.message}`);
    }
  } else {
    data.stats = computeStats(data.draws);
  }

  await save();
  console.log(`${lot.slug}: งวดใหม่ ${added} งวด · รวม ${data.draws.length} งวด`);
  return true;
}

await mkdir("data", { recursive: true });
let failed = 0;
for (const lot of LOTTERIES) {
  try {
    await update(lot);
  } catch (err) {
    failed++;
    console.error(`${lot.slug}: ${err.message}`);
  }
  await sleep(15000); // เว้นระยะระหว่างหวย กัน API จำกัดความถี่
}
// ล้มเหลวทุกหวย = ให้ workflow ขึ้นสีแดงจะได้เห็น ส่วนพลาดบางหวยรอรอบถัดไปได้
if (failed === LOTTERIES.length) process.exit(1);
