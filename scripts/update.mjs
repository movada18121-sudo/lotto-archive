// ดึงผลหวยจาก ผลหวย.com เฉพาะหวยที่ถึงเวลาออกผลแล้ว แล้วรวมเก็บลง data/<slug>.json
// รันโดย GitHub Actions (.github/workflows/update-data.yml) — ผู้ชมเว็บอ่านจากไฟล์นี้ ไม่ต้องเรียก API เอง
//   node scripts/update.mjs           ดึงเฉพาะหวยที่ถึงเวลาออกผลและยังไม่มีงวดใหม่
//   node scripts/update.mjs --force   ดึงทุกหวยทันที
import { readFile, writeFile, mkdir } from "node:fs/promises";

const API = "https://xn--t3cmiit.com/api/public";

// ต้องตรงกับ LOTTERIES ใน index.html · เวลาเป็นเวลาไทย · days = วันในสัปดาห์ (0 = อาทิตย์), dates = วันที่ของเดือน
// apiStats = API มี /stats ของหวยนี้ ถ้าไม่มีจะคำนวณสถิติเลขท้าย 2 ตัวเองจากงวดที่เก็บไว้
const LOTTERIES = [
  { slug: "lao-lottery",     days: [1, 2, 3, 4, 5],          time: "20:30", apiStats: true },
  { slug: "hanoi-normal",    days: [0, 1, 2, 3, 4, 5, 6],    time: "18:30", apiStats: false },
  { slug: "thai-government", dates: [1, 16],                 time: "14:30", apiStats: true },
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

async function getJson(path) {
  const res = await fetch(API + path, { headers: { Accept: "application/json" } });
  const json = await res.json().catch(() => null);
  if (!res.ok || !json || json.success === false) {
    throw new Error(`${path} -> ${res.status} ${(json && json.error) || ""}`.trim());
  }
  return json;
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

  // หวยที่คำนวณสถิติเอง: ถ้ายังไม่มีสถิติ คำนวณจากงวดที่มีได้เลยโดยไม่ต้องเรียก API
  if (!lot.apiStats && !data.stats && data.draws.length) {
    data.stats = computeStats(data.draws);
    data.updatedAt = new Date().toISOString();
    await writeFile(file, JSON.stringify(data) + "\n");
  }

  const latest = data.draws[0] && data.draws[0].drawDate;
  if (!FORCE && latest && Date.now() < nextDue(lot, latest).getTime()) {
    console.log(`${lot.slug}: ยังไม่ถึงเวลาออกผลงวดถัดไป (${nextDue(lot, latest).toISOString()})`);
    return false;
  }

  const json = await getJson(`/results?lottery=${lot.slug}&limit=20`);
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

  data.updatedAt = new Date().toISOString();
  await writeFile(file, JSON.stringify(data) + "\n");
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
  await sleep(5000); // เว้นระยะระหว่างหวย กัน API จำกัดความถี่
}
// ล้มเหลวทุกหวย = ให้ workflow ขึ้นสีแดงจะได้เห็น ส่วนพลาดบางหวยรอรอบถัดไปได้
if (failed === LOTTERIES.length) process.exit(1);
