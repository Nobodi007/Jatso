/** ฟังก์ชันคำนวณล้วน ๆ สำหรับกราฟ Risk Center (ไม่พึ่ง React เพื่อทดสอบได้) */

export interface Pt { x: number; y: number | null }

/** ticks สวย ๆ ครอบ [min, max] */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (max - min < 1e-12) return [min];
  const raw = (max - min) / Math.max(count, 1);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const start = Math.ceil(min / step - 1e-9) * step;
  const out: number[] = [];
  for (let v = start; v <= max + step * 1e-9; v += step) out.push(Number(v.toFixed(12)));
  return out;
}

/** path ของเส้น: ขาดช่วงเมื่อ y เป็น null (ไม่ต่อข้ามช่องว่างข้อมูล) */
export function linePath(points: Pt[], sx: (x: number) => number, sy: (y: number) => number): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p.y == null || !Number.isFinite(p.y)) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`;
    pen = true;
  }
  return d;
}

/** ผลตอบแทนรายวันจากผลตอบแทนสะสม: r_t = (1+c_t)/(1+c_{t-1}) − 1 (จุดแรกเป็นวันฐาน) */
export function dailyFromCumulative(cum: (number | null)[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < cum.length; i++) {
    const a = cum[i - 1], b = cum[i];
    if (a == null || b == null || 1 + a <= 0) continue;
    out.push((1 + b) / (1 + a) - 1);
  }
  return out;
}

export interface Bin { lo: number; hi: number; count: number }

/** histogram ความกว้างเท่ากัน จำนวน bin ≈ √n (5..20) ค่า max ตกใน bin สุดท้าย */
export function histogram(values: number[], maxBins = 20, minBins = 5): Bin[] {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length === 0) return [];
  const lo = Math.min(...v), hi = Math.max(...v);
  if (hi - lo < 1e-12) return [{ lo, hi, count: v.length }];
  const k = Math.min(maxBins, Math.max(minBins, Math.ceil(Math.sqrt(v.length))));
  const w = (hi - lo) / k;
  const bins: Bin[] = Array.from({ length: k }, (_, i) => ({ lo: lo + i * w, hi: lo + (i + 1) * w, count: 0 }));
  for (const x of v) bins[Math.min(k - 1, Math.floor((x - lo) / w))].count++;
  return bins;
}

/** เลือก index ของป้ายแกน x ให้ไม่เกิน max ป้าย (รวมจุดแรกและจุดสุดท้าย) */
export function labelIndexes(n: number, max = 4): number[] {
  if (n <= 0) return [];
  if (n <= max) return Array.from({ length: n }, (_, i) => i);
  const out = new Set<number>([0, n - 1]);
  for (let i = 1; i < max - 1; i++) out.add(Math.round((i * (n - 1)) / (max - 1)));
  return [...out].sort((a, b) => a - b);
}

/** index จุดที่ใกล้ตำแหน่งเมาส์ที่สุด (frac = 0..1 ของความกว้างพื้นที่พล็อต) */
export function nearestIndex(frac: number, n: number): number {
  if (n <= 1) return 0;
  return Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1))));
}
