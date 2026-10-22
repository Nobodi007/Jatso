import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import type { PointerEvent as RPointerEvent, ReactNode } from "react";

/* ------------------------------------------------------------------ */
/*  พอร์ตหุ้น Nobodi: การ์ดแบบ Bento + กราฟ SVG ไม่ใช้ไลบรารี           */
/*  ใช้เฉพาะข้อมูลจาก /api/stock-book (ไม่เกี่ยวกับคริปโต)               */
/*  สี/พื้นผิวทั้งหมดมาจากธีมของเว็บ (bg-card, text-foreground ฯลฯ)     */
/* ------------------------------------------------------------------ */

const API = "https://xspring-api.onrender.com/api/stock-book";

type Pos = {
  symbol: string; qty: number; avg_cost: number; last: number;
  market_value: number; unrealized_pnl: number; unrealized_pct: number;
};
type Book = {
  initial_cash: number; cash: number; market_value: number;
  equity: number; pnl: number; pnl_pct: number; positions: Pos[];
};
type Trade = {
  id: number; symbol: string; side: "buy" | "sell"; qty: number; price: number;
  fee: number; realized_pnl: number | null; note: string | null; ts: string;
};
type Tip = { x: number; y: number; title: string; rows: { label: string; value: string; dot?: string }[] } | null;
type SetTip = (t: Tip) => void;

/* ---------------- helpers ---------------- */

const nf = (n: number, d = 0) =>
  n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const usd = (n: number) => `${n < 0 ? "-" : ""}$${nf(Math.abs(n), 2)}`;
const sgn = (n: number) => (n > 0 ? "+" : "");
const sUsd = (n: number) => `${sgn(n)}${usd(n)}`;
const tone = (n: number) => (n > 0 ? "text-emerald-500" : n < 0 ? "text-rose-500" : "text-muted-foreground");
const ease = (t: number) => 1 - Math.pow(1 - t, 3);
const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
const MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];

function useSize() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const w = Math.round(e.contentRect.width), h = Math.round(e.contentRect.height);
      setSize((p) => (p.w === w && p.h === h ? p : { w, h }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

/** ค่า 0..1 ที่เพิ่มขึ้นตามเวลา ใช้ทำแอนิเมชันเข้า เล่นใหม่เมื่อ key เปลี่ยนเท่านั้น */
function useGrow(key: string, ms = 1100) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setT(1); return; }
    let raf = 0;
    const t0 = performance.now();
    const f = (now: number) => {
      const p = Math.min(1, (now - t0) / ms);
      setT(ease(p));
      if (p < 1) raf = requestAnimationFrame(f);
    };
    raf = requestAnimationFrame(f);
    return () => cancelAnimationFrame(raf);
  }, [key, ms]);
  return t;
}

/** เส้นโค้งผ่านทุกจุด (catmull-rom เป็น cubic bezier) */
function smooth(P: [number, number][]) {
  const n = P.length;
  if (n < 2) return "";
  const g = (i: number) => P[Math.max(0, Math.min(n - 1, i))];
  let d = `M${P[0][0]},${P[0][1]}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2), k = 0.18;
    d += `C${p1[0] + (p2[0] - p0[0]) * k},${p1[1] + (p2[1] - p0[1]) * k} ${p2[0] - (p3[0] - p1[0]) * k},${p2[1] - (p3[1] - p1[1]) * k} ${p2[0]},${p2[1]}`;
  }
  return d;
}

function CountUp({ value, prefix = "", decimals = 0 }: { value: number; prefix?: string; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const from = useRef(0);
  const text = (v: number) => `${v < 0 ? "-" : ""}${prefix}${nf(Math.abs(v), decimals)}`;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const a = from.current, b = value, t0 = performance.now();
    let raf = 0;
    const f = (now: number) => {
      const p = Math.min(1, (now - t0) / 900), v = a + (b - a) * ease(p);
      el.textContent = text(v);
      from.current = v;
      if (p < 1) raf = requestAnimationFrame(f);
    };
    raf = requestAnimationFrame(f);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, prefix, decimals]);
  return <span ref={ref}>{text(value)}</span>;
}

/* ---------------- shared bits ---------------- */

const Card = ({ className = "", children, label }: { className?: string; children: ReactNode; label?: string }) => (
  <section aria-label={label} className={`relative min-w-0 overflow-hidden rounded-3xl border border-border bg-card p-5 text-card-foreground sm:p-6 ${className}`}>
    {children}
  </section>
);

function Delta({ v, children }: { v: number; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-[3px] font-semibold ${v >= 0 ? "text-emerald-500" : "text-rose-500"}`}>
      <svg viewBox="0 0 12 12" className={`h-[11px] w-[11px] ${v < 0 ? "rotate-180" : ""}`} aria-hidden="true">
        <path d="M6 10.5V1.5M2 5.5l4-4 4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {children}
    </span>
  );
}

function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  const flip = typeof window !== "undefined" && tip.x > window.innerWidth - 220;
  return (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 whitespace-nowrap rounded-xl border border-border bg-card px-2.5 py-2 text-xs text-foreground shadow-lg"
      style={{ left: tip.x, top: tip.y, transform: `translate(${flip ? "calc(-100% - 14px)" : "14px"}, calc(-100% - 12px))` }}
    >
      <div className="mb-1 text-muted-foreground">{tip.title}</div>
      {tip.rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            {r.dot && <i className="inline-block h-2 w-2 rounded-[2px]" style={{ background: r.dot }} />}
            {r.label}
          </span>
          <b className="font-medium tabular-nums">{r.value}</b>
        </div>
      ))}
    </div>
  );
}

const Empty = ({ text, className = "" }: { text: string; className?: string }) => (
  <div className={`grid place-items-center rounded-2xl border border-dashed border-border bg-muted/30 px-4 text-center text-sm text-muted-foreground ${className}`}>
    {text}
  </div>
);

/* ---------------- A: กำไรที่รับรู้สะสม (เส้น) ---------------- */

function LineChart({ points, setTip }: { points: { label: string; value: number }[]; setTip: SetTip }) {
  const [ref, { w: W, h: H }] = useSize();
  const vals = points.map((p) => p.value);
  const t = useGrow(vals.join(","), 1400);
  const [hover, setHover] = useState<number | null>(null);
  const id = useId().replace(/:/g, "");

  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), span = hi - lo || 1;
  const top = 24, bot = 12;
  const Y = (v: number) => top + (1 - (v - lo) / span) * (H - top - bot);
  const P = vals.map((v, i) => [14 + (i / Math.max(vals.length - 1, 1)) * (W - 28), Y(v)] as [number, number]);
  const col = (vals[vals.length - 1] ?? 0) >= 0 ? "#10b981" : "#f43f5e";
  const d = W > 0 && P.length > 1 ? smooth(P) : "";
  const last = P[P.length - 1];

  const move = (e: RPointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    const i = Math.max(0, Math.min(vals.length - 1, Math.round(((e.clientX - r.left - 14) / (W - 28)) * (vals.length - 1))));
    setHover(i);
    setTip({ x: r.left + P[i][0], y: r.top + P[i][1], title: points[i].label, rows: [{ label: "สะสม", value: sUsd(vals[i]), dot: col }] });
  };

  return (
    <div ref={ref} className="relative h-[160px] w-full overflow-hidden rounded-2xl border border-border bg-muted/40">
      <div className="pointer-events-none absolute left-3 top-2.5 text-[11px] text-muted-foreground">กำไรที่รับรู้สะสม</div>
      {W > 0 && d && (
        <svg width={W} height={H} className="block" role="img" aria-label="กราฟกำไรที่รับรู้สะสม">
          <defs>
            <linearGradient id={`${id}a`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={col} stopOpacity="0.2" />
              <stop offset="1" stopColor={col} stopOpacity="0" />
            </linearGradient>
          </defs>
          <line x1={0} x2={W} y1={Y(0)} y2={Y(0)} className="stroke-border" strokeDasharray="3 4" />
          <path d={`${d}L${last[0]},${Y(0)}L${P[0][0]},${Y(0)}Z`} fill={`url(#${id}a)`} opacity={t} />
          <path d={d} pathLength={1} fill="none" stroke={col} strokeWidth={2.5} strokeLinecap="round" style={{ strokeDasharray: 1, strokeDashoffset: 1 - t }} />
          <circle cx={last[0]} cy={last[1]} r={4.5} fill={col} className="stroke-card" strokeWidth={2} opacity={t} />
          {hover !== null && (
            <>
              <line x1={P[hover][0]} x2={P[hover][0]} y1={0} y2={H} className="stroke-muted-foreground/50" />
              <circle cx={P[hover][0]} cy={P[hover][1]} r={4.5} fill={col} className="stroke-card" strokeWidth={2} />
            </>
          )}
          <rect width={W} height={H} fill="transparent" onPointerMove={move} onPointerLeave={() => { setHover(null); setTip(null); }} />
        </svg>
      )}
    </div>
  );
}

/* ---------------- B: ซื้อ vs ขาย 14 วัน (คลื่นสองฝั่ง) ---------------- */

function WaveChart({ labels, buy, sell, setTip }: { labels: string[]; buy: number[]; sell: number[]; setTip: SetTip }) {
  const [ref, { w: W, h: H }] = useSize();
  const t = useGrow(buy.join(",") + "|" + sell.join(","), 1300);
  const [hover, setHover] = useState<number | null>(null);
  const n = buy.length;
  const max = Math.max(1, ...buy, ...sell);
  const mid = H / 2, amp = H / 2 - 16, pad = 20;
  const X = (i: number) => pad + (i / (n - 1)) * (W - 2 * pad);
  const line = (a: number[], dir: number) =>
    smooth(a.map((v, i) => [X(i), mid + dir * (2 + (v / max) * amp * t)] as [number, number]));
  const area = (a: number[], dir: number) => `${line(a, dir)}L${X(n - 1)},${mid}L${X(0)},${mid}Z`;

  const move = (e: RPointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((e.clientX - r.left - pad) / (W - 2 * pad)) * (n - 1))));
    setHover(i);
    setTip({
      x: r.left + X(i), y: r.top + 14, title: labels[i],
      rows: [
        { label: "ซื้อ", value: usd(buy[i]), dot: "#10b981" },
        { label: "ขาย", value: usd(sell[i]), dot: "#f43f5e" },
      ],
    });
  };

  return (
    <div ref={ref} className="relative h-[160px] w-full overflow-hidden rounded-2xl border border-border bg-muted/40">
      {W > 0 && (
        <svg width={W} height={H} className="block" role="img" aria-label="มูลค่าซื้อและขายรายวัน 14 วันล่าสุด">
          <line x1={pad} x2={W - pad} y1={mid} y2={mid} className="stroke-border" />
          <path d={area(buy, -1)} fill="#10b981" opacity={0.12} />
          <path d={area(sell, 1)} fill="#f43f5e" opacity={0.12} />
          <path d={line(buy, -1)} fill="none" stroke="#10b981" strokeWidth={2.5} strokeLinecap="round" />
          <path d={line(sell, 1)} fill="none" stroke="#f43f5e" strokeWidth={2.5} strokeLinecap="round" />
          {hover !== null && <line x1={X(hover)} x2={X(hover)} y1={4} y2={H - 4} className="stroke-muted-foreground/60" />}
          <rect width={W} height={H} fill="transparent" onPointerMove={move} onPointerLeave={() => { setHover(null); setTip(null); }} />
        </svg>
      )}
    </div>
  );
}

/* ---------------- C: สัดส่วนพอร์ต (treemap) ---------------- */

type GroupId = "gain" | "loss" | "cash";
type TItem = { name: string; group: GroupId; v: number; sub: string };
type Tile = TItem & { x: number; y: number; w: number; h: number };

const GROUPS: Record<GroupId, { name: string; cls: string; dot: string }> = {
  gain: { name: "กำไร", cls: "bg-emerald-400 text-neutral-950", dot: "#34d399" },
  loss: { name: "ขาดทุน", cls: "bg-rose-400 text-neutral-950", dot: "#fb7185" },
  cash: { name: "เงินสด", cls: "bg-muted text-foreground", dot: "#a1a1aa" },
};

function squarify(items: TItem[], x: number, y: number, w: number, h: number): Tile[] {
  const total = items.reduce((a, b) => a + b.v, 0) || 1, scale = (w * h) / total, out: Tile[] = [];
  let rest = items.map((i) => ({ ...i, a: i.v * scale }));
  const worst = (row: typeof rest, len: number) => {
    const s = row.reduce((a, b) => a + b.a, 0), mx = Math.max(...row.map((r) => r.a)), mn = Math.min(...row.map((r) => r.a));
    return Math.max((len * len * mx) / (s * s), (s * s) / (len * len * mn));
  };
  while (rest.length) {
    const len = Math.min(w, h);
    const row = [rest[0]];
    let i = 1;
    while (i < rest.length && worst([...row, rest[i]], len) <= worst(row, len)) row.push(rest[i++]);
    rest = rest.slice(i);
    const s = row.reduce((a, b) => a + b.a, 0);
    if (w >= h) {
      const cw = s / h; let cy = y;
      for (const r of row) { const rh = r.a / cw; out.push({ ...r, x, y: cy, w: cw, h: rh }); cy += rh; }
      x += cw; w -= cw;
    } else {
      const rh = s / w; let cx = x;
      for (const r of row) { const rw = r.a / rh; out.push({ ...r, x: cx, y, w: rw, h: rh }); cx += rw; }
      y += rh; h -= rh;
    }
  }
  return out;
}

function Treemap({ items, setTip }: { items: TItem[]; setTip: SetTip }) {
  const [ref, { w: W, h: H }] = useSize();
  const [placed, setPlaced] = useState(false);
  useEffect(() => {
    if (!W) return;
    const r = requestAnimationFrame(() => requestAnimationFrame(() => setPlaced(true)));
    return () => cancelAnimationFrame(r);
  }, [W]);
  const G = 6;
  const sorted = useMemo(() => items.filter((i) => i.v > 0).sort((a, b) => b.v - a.v), [items]);
  const total = sorted.reduce((a, b) => a + b.v, 0) || 1;
  const tiles = W && H && sorted.length ? squarify(sorted, 0, 0, W + G, H + G) : [];

  return (
    <div ref={ref} className="relative mt-1.5 h-[280px] sm:h-[320px]" role="img" aria-label="สัดส่วนพอร์ตตามมูลค่า">
      {tiles.map((r) => {
        const w = r.w - G, h = r.h - G, share = ((r.v / total) * 100).toFixed(1) + "%";
        const showName = h >= 56 && w >= 70, showVal = h >= 70 && w >= 90;
        const fs = Math.max(13, Math.min(24, w / 7));
        return (
          <div
            key={r.name}
            className={`absolute flex flex-col justify-between overflow-hidden rounded-2xl p-3 transition-[left,top,width,height,filter] duration-700 hover:brightness-110 motion-reduce:transition-none ${GROUPS[r.group].cls}`}
            style={{
              left: placed ? r.x : W / 2, top: placed ? r.y : H / 2,
              width: placed ? w : 0, height: placed ? h : 0,
              transitionTimingFunction: "cubic-bezier(.2,.9,.25,1)",
            }}
            onPointerMove={(e) =>
              setTip({
                x: e.clientX, y: e.clientY, title: `${r.name} · ${GROUPS[r.group].name}`,
                rows: [
                  { label: "มูลค่า", value: usd(r.v), dot: GROUPS[r.group].dot },
                  { label: "สัดส่วน", value: share },
                  ...(r.sub ? [{ label: "รายละเอียด", value: r.sub }] : []),
                ],
              })
            }
            onPointerLeave={() => setTip(null)}
          >
            <div className="truncate text-[11px] font-semibold">{showName || w >= 40 ? r.name : ""}</div>
            {showVal && (
              <div className="flex items-end justify-between gap-1.5">
                <span className="font-medium leading-none tabular-nums" style={{ fontSize: fs }}>${nf(r.v)}</span>
                <span className="rounded-md bg-black/75 px-[5px] py-[3px] text-[10px] font-medium text-white">{share}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ---------------- D: กำไรที่รับรู้รายเดือน (เรดาร์) ---------------- */

function Radar({ values, year, setTip }: { values: number[]; year: number; setTip: SetTip }) {
  const [ref, { w }] = useSize();
  const line = useRef<SVGPathElement>(null);
  const cur = useRef<number[] | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const N = values.length, S = Math.min(w, 400), R = S / 2 - 34, C = S / 2;
  const ang = (i: number) => -Math.PI / 2 + (i / N) * Math.PI * 2;
  const color = "#10b981";

  /* ปรับค่าเป็นสัดส่วนแล้ว fit ด้วย Fourier อันดับต่ำ ให้กลีบโค้งมนสม่ำเสมอ */
  const norm = (v: number[]) => { const lo = Math.min(...v), hi = Math.max(...v); return v.map((x) => 0.42 + ((x - lo) / (hi - lo || 1)) * 0.58); };
  const fit = (v: number[]) => {
    const K = Math.min(5, Math.floor(N / 2)), co: [number, number][] = [];
    for (let k = 0; k <= K; k++) {
      let a = 0, b = 0;
      v.forEach((x, i) => { const th = (i / N) * Math.PI * 2; a += x * Math.cos(k * th); b += x * Math.sin(k * th); });
      co.push([(a * (k ? 2 : 1)) / N, (b * (k ? 2 : 1)) / N]);
    }
    return (th: number) => co.reduce((r, [a, b], k) => r + a * Math.cos(k * th) + b * Math.sin(k * th), 0);
  };
  const at = (f: (t: number) => number, th: number): [number, number] => {
    const v = Math.max(0.05, f(th)), a = -Math.PI / 2 + th;
    return [C + Math.cos(a) * (R * 0.2 + v * R * 0.8), C + Math.sin(a) * (R * 0.2 + v * R * 0.8)];
  };
  const shape = (v: number[]) => {
    const f = fit(norm(v));
    let d = "";
    for (let j = 0; j <= 180; j++) { const p = at(f, (j / 180) * Math.PI * 2); d += (j ? "L" : "M") + p[0].toFixed(2) + "," + p[1].toFixed(2); }
    return d + "Z";
  };
  const point = (v: number[], i: number) => at(fit(norm(v)), (i / N) * Math.PI * 2);

  useEffect(() => {
    if (!S) return;
    const from = cur.current ?? values.map(() => Math.min(...values)), to = values, t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const t = ease(Math.min(1, (now - t0) / 900));
      cur.current = from.map((v, i) => v + (to[i] - v) * t);
      line.current?.setAttribute("d", shape(cur.current));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values.join(","), S]);

  const move = (e: RPointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.ownerSVGElement!.getBoundingClientRect(), x = e.clientX - r.left - C, y = e.clientY - r.top - C;
    if (Math.hypot(x, y) < R * 0.2) { setHover(null); setTip(null); return; }
    let a = Math.atan2(y, x) + Math.PI / 2;
    if (a < 0) a += Math.PI * 2;
    const i = Math.round((a / (Math.PI * 2)) * N) % N, p = point(values, i);
    setHover(i);
    setTip({ x: r.left + p[0], y: r.top + p[1], title: `${MONTHS[i]} ${year}`, rows: [{ label: "กำไรที่รับรู้", value: sUsd(values[i]), dot: color }] });
  };
  const hp = hover !== null ? point(values, hover) : null;

  return (
    <div ref={ref} className="mx-auto mt-1.5 w-full max-w-[400px]" style={{ height: S || 300 }}>
      {S > 0 && (
        <svg width={S} height={S} className="mx-auto block" role="img" aria-label={`กำไรที่รับรู้รายเดือน ปี ${year}`}>
          {[0.33, 0.66, 1].map((k) => <circle key={k} cx={C} cy={C} r={R * k} fill="none" className="stroke-border" />)}
          {MONTHS.map((m, i) => (
            <g key={m}>
              <line x1={C + Math.cos(ang(i)) * R * 0.2} y1={C + Math.sin(ang(i)) * R * 0.2} x2={C + Math.cos(ang(i)) * R} y2={C + Math.sin(ang(i)) * R} className="stroke-border" />
              <text x={C + Math.cos(ang(i)) * (R + 18)} y={C + Math.sin(ang(i)) * (R + 18)} textAnchor="middle" dominantBaseline="central" fontSize={11} className="fill-muted-foreground">{m}</text>
            </g>
          ))}
          <path ref={line} fill="none" strokeWidth={2.5} strokeLinejoin="round" stroke={color} />
          <circle cx={C} cy={C} r={R * 0.2} className="fill-card stroke-border" />
          {hp && <circle cx={hp[0]} cy={hp[1]} r={4.5} fill={color} className="stroke-card" strokeWidth={2} />}
          <rect width={S} height={S} fill="transparent" onPointerMove={move} onPointerLeave={() => { setHover(null); setTip(null); }} />
        </svg>
      )}
    </div>
  );
}

/* ---------------- tables ---------------- */

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="text-xs text-muted-foreground">
            {head.map((h, i) => <th key={h} className={`px-3 py-2.5 font-medium ${i < 1 ? "text-left" : "text-right"}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/* ---------------- หน้าหลัก ---------------- */

export default function StockPortfolioPage({
  getToken,
  view,
}: {
  getToken: () => Promise<string | null> | string | null;
  view: "portfolio" | "orders" | "positions";
}) {
  const [book, setBook] = useState<Book | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [tip, setTip] = useState<Tip>(null);
  const [year, setYear] = useState<number | null>(null);
  const [f, setF] = useState({ symbol: "", side: "buy", qty: "", price: "", fee: "", note: "" });

  const call = useCallback(
    async (path: string, init?: RequestInit) => {
      const token = await getToken();
      const r = await fetch(`${API}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      });
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new Error(typeof j?.detail === "string" ? j.detail : `HTTP ${r.status}`);
      return j;
    },
    [getToken],
  );

  const load = useCallback(async () => {
    try {
      const [b, t] = await Promise.all([call("/portfolio"), call("/trades")]);
      setBook(b);
      setTrades(Array.isArray(t) ? t : []);
      setErr("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "โหลดไม่สำเร็จ");
    }
  }, [call]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 30000);
    return () => clearInterval(id);
  }, [load]);

  const submit = async () => {
    setBusy(true);
    try {
      setErr("");
      await call("/trade", {
        method: "POST",
        body: JSON.stringify({
          symbol: f.symbol.trim().toUpperCase(),
          side: f.side,
          qty: Number(f.qty),
          price: f.price ? Number(f.price) : null,
          fee: f.fee ? Number(f.fee) : 0,
          note: f.note || null,
        }),
      });
      setF({ ...f, qty: "", price: "", fee: "", note: "" });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ส่งคำสั่งไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  };

  /* ----- ข้อมูลที่คำนวณจากรายการซื้อขายจริง ----- */
  const asc = useMemo(() => [...trades].reverse(), [trades]); // API ส่งใหม่สุดก่อน

  const realizedSeries = useMemo(() => {
    const out = [{ label: "เริ่มต้น", value: 0 }];
    let c = 0;
    for (const t of asc) {
      if (t.realized_pnl != null) {
        c += t.realized_pnl;
        out.push({ label: `${new Date(t.ts).toLocaleDateString("th-TH", { day: "numeric", month: "short" })} · ${t.symbol}`, value: c });
      }
    }
    return out.length > 1 ? out : [];
  }, [asc]);
  const totalRealized = realizedSeries.length ? realizedSeries[realizedSeries.length - 1].value : 0;

  const activity = useMemo(() => {
    const keys: string[] = [], labels: string[] = [];
    const now = new Date();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
      keys.push(dayKey(d));
      labels.push(d.toLocaleDateString("th-TH", { day: "numeric", month: "short" }));
    }
    const buy = keys.map(() => 0), sell = keys.map(() => 0);
    for (const t of trades) {
      const i = keys.indexOf(dayKey(new Date(t.ts)));
      if (i < 0) continue;
      if (t.side === "buy") buy[i] += t.qty * t.price; else sell[i] += t.qty * t.price;
    }
    return { labels, buy, sell, has: buy.some((x) => x > 0) || sell.some((x) => x > 0) };
  }, [trades]);

  const years = useMemo(() => {
    const s = new Set<number>([new Date().getFullYear()]);
    trades.forEach((t) => s.add(new Date(t.ts).getFullYear()));
    return Array.from(s).sort((a, b) => b - a);
  }, [trades]);
  const yr = year ?? years[0];

  const season = useMemo(() => {
    const values = MONTHS.map(() => 0);
    const bySym: Record<string, number> = {};
    let count = 0, realized = 0;
    for (const t of trades) {
      const d = new Date(t.ts);
      if (d.getFullYear() !== yr) continue;
      count++;
      if (t.realized_pnl != null) {
        values[d.getMonth()] += t.realized_pnl;
        realized += t.realized_pnl;
        bySym[t.symbol] = (bySym[t.symbol] ?? 0) + t.realized_pnl;
      }
    }
    const rows = Object.entries(bySym).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3);
    return { values, count, realized, rows, has: values.some((v) => v !== 0) };
  }, [trades, yr]);

  const treeItems: TItem[] = useMemo(() => {
    if (!book) return [];
    const items: TItem[] = book.positions.map((p) => ({
      name: p.symbol,
      group: p.unrealized_pnl >= 0 ? "gain" : "loss",
      v: p.market_value,
      sub: `${nf(p.qty, 0)} หุ้น · ${sgn(p.unrealized_pct)}${nf(p.unrealized_pct, 2)}%`,
    }));
    if (book.cash > 0) items.push({ name: "เงินสด", group: "cash", v: book.cash, sub: "" });
    return items;
  }, [book]);

  const unrealized = book ? book.positions.reduce((a, p) => a + p.unrealized_pnl, 0) : 0;
  const inp = "h-10 rounded-xl border border-border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring";

  /* ----- ชิ้นส่วนที่ใช้ซ้ำ ----- */
  const allocation = (
    <Card className="col-span-12 lg:col-span-7" label="สัดส่วนพอร์ต">
      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <h2 className="text-[17px] font-semibold tracking-tight">สัดส่วนพอร์ต</h2>
        <div className="flex flex-wrap gap-x-3.5 gap-y-1.5 text-xs text-muted-foreground">
          {(Object.keys(GROUPS) as GroupId[]).map((g) => (
            <span key={g} className="inline-flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-[2px]" style={{ background: GROUPS[g].dot }} />{GROUPS[g].name}
            </span>
          ))}
        </div>
      </div>
      {book && (
        <div className="my-[18px] grid grid-cols-3 gap-3">
          <div>
            <div className="text-[13px] text-muted-foreground">เงินสด</div>
            <div className="mt-1.5 text-xl font-medium leading-none tabular-nums sm:text-[26px]"><CountUp value={book.cash} prefix="$" decimals={0} /></div>
          </div>
          <div>
            <div className="text-[13px] text-muted-foreground">กำไร/ขาดทุนที่ยังไม่รับรู้</div>
            <div className={`mt-1.5 text-xl font-medium leading-none tabular-nums sm:text-[26px] ${tone(unrealized)}`}><CountUp value={unrealized} prefix="$" decimals={0} /></div>
          </div>
          <div>
            <div className="text-[13px] text-muted-foreground">จำนวนหุ้นที่ถือ</div>
            <div className="mt-1.5 text-xl font-medium leading-none tabular-nums sm:text-[26px]"><CountUp value={book.positions.length} /></div>
          </div>
        </div>
      )}
      {treeItems.some((i) => i.v > 0) ? <Treemap items={treeItems} setTip={setTip} /> : <Empty text="ยังไม่มีข้อมูลในพอร์ต" className="mt-3 h-[240px]" />}
    </Card>
  );

  const positionsTable = book && (
    <Card label="หุ้นที่ถือ">
      <h2 className="mb-3 text-[17px] font-semibold tracking-tight">หุ้นที่ถือ</h2>
      <Table head={["Symbol", "จำนวน", "ต้นทุนเฉลี่ย", "ราคาล่าสุด", "มูลค่า", "P/L", "%"]}>
        {book.positions.length === 0 && (
          <tr><td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">ยังไม่มีหุ้นในพอร์ต</td></tr>
        )}
        {book.positions.map((p) => (
          <tr key={p.symbol} className="border-t border-border">
            <td className="px-3 py-3 font-semibold">{p.symbol}</td>
            <td className="px-3 py-3 text-right tabular-nums">{nf(p.qty, 0)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{usd(p.avg_cost)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{usd(p.last)}</td>
            <td className="px-3 py-3 text-right tabular-nums">{usd(p.market_value)}</td>
            <td className={`px-3 py-3 text-right tabular-nums ${tone(p.unrealized_pnl)}`}>{sUsd(p.unrealized_pnl)}</td>
            <td className={`px-3 py-3 text-right tabular-nums ${tone(p.unrealized_pct)}`}>{sgn(p.unrealized_pct)}{nf(p.unrealized_pct, 2)}%</td>
          </tr>
        ))}
      </Table>
    </Card>
  );

  return (
    <div className="space-y-5 text-foreground">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {view === "portfolio" ? "พอร์ตหุ้นของฉัน" : view === "orders" ? "ประวัติการซื้อขาย" : "Positions หุ้น"}
        </h1>
        <p className="text-sm text-muted-foreground">พอร์ตหุ้นสหรัฐ แยกจากคริปโตทั้งหมด</p>
      </div>

      {err && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-400">{err}</div>}
      {!book && !err && <Empty text="กำลังโหลดพอร์ต…" className="h-40" />}

      {/* ฟอร์มบันทึกรายการ */}
      {view === "portfolio" && (
        <Card label="บันทึกรายการซื้อขาย">
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-7">
            <input className={inp} placeholder="Symbol เช่น AAPL" value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })} />
            <select className={inp} value={f.side} onChange={(e) => setF({ ...f, side: e.target.value })}>
              <option value="buy">ซื้อ</option>
              <option value="sell">ขาย</option>
            </select>
            <input className={inp} inputMode="numeric" placeholder="จำนวน" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} />
            <input className={inp} inputMode="decimal" placeholder="ราคา (ว่าง = ราคาตลาด)" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} />
            <input className={inp} inputMode="decimal" placeholder="ค่าธรรมเนียม" value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} />
            <input className={inp} placeholder="โน้ต" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
            <button
              disabled={busy || !f.symbol || !f.qty}
              onClick={() => void submit()}
              className={`h-10 rounded-xl px-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40 ${f.side === "buy" ? "bg-emerald-500 hover:bg-emerald-600" : "bg-rose-500 hover:bg-rose-600"}`}
            >
              {busy ? "กำลังบันทึก…" : f.side === "buy" ? "บันทึกซื้อ" : "บันทึกขาย"}
            </button>
          </div>
        </Card>
      )}

      {/* Bento หน้า Portfolio */}
      {book && view === "portfolio" && (
        <div className="grid grid-cols-12 gap-4">
          <Card className="col-span-12 lg:col-span-5" label="Equity">
            <div className="text-[13px] text-muted-foreground">Equity (มูลค่าพอร์ตรวม)</div>
            <div className="mt-2.5 text-[34px] font-medium leading-none tabular-nums sm:text-[40px]">
              <CountUp value={book.equity} prefix="$" decimals={2} />
            </div>
            <div className="mt-2 flex items-center gap-2 text-sm">
              <Delta v={book.pnl}>{nf(Math.abs(book.pnl_pct), 2)}%</Delta>
              <span className={`tabular-nums ${tone(book.pnl)}`}>{sUsd(book.pnl)}</span>
              <span className="text-muted-foreground">จากเงินต้น {usd(book.initial_cash)}</span>
            </div>
            <div className="mt-4">
              {realizedSeries.length ? (
                <LineChart points={realizedSeries} setTip={setTip} />
              ) : (
                <Empty text="ยังไม่มีกำไรที่รับรู้ ขายหุ้นครั้งแรกแล้วกราฟจะขึ้น" className="h-[160px]" />
              )}
            </div>
          </Card>

          <Card className="col-span-12 lg:col-span-7" label="กิจกรรมซื้อขาย">
            <div className="text-[13px] text-muted-foreground">มูลค่าหุ้นที่ถือ</div>
            <div className="mt-2.5 text-[34px] font-medium leading-none tabular-nums sm:text-[40px]">
              <CountUp value={book.market_value} prefix="$" decimals={2} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>ซื้อขาย 14 วันล่าสุด</span>
              <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-3.5 rounded-sm bg-emerald-500" />ซื้อ</span>
              <span className="inline-flex items-center gap-1.5"><i className="h-0.5 w-3.5 rounded-sm bg-rose-500" />ขาย</span>
            </div>
            <div className="mt-4">
              {activity.has ? (
                <WaveChart labels={activity.labels} buy={activity.buy} sell={activity.sell} setTip={setTip} />
              ) : (
                <Empty text="ยังไม่มีรายการซื้อขายใน 14 วันที่ผ่านมา" className="h-[160px]" />
              )}
            </div>
          </Card>

          {allocation}

          <Card className="col-span-12 lg:col-span-5" label="กำไรที่รับรู้รายเดือน">
            <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
              <h2 className="text-[17px] font-semibold tracking-tight">กำไรที่รับรู้รายเดือน</h2>
              <div role="tablist" aria-label="ปี" className="inline-flex rounded-[10px] bg-muted p-[2px]">
                {years.map((y) => (
                  <button
                    key={y}
                    role="tab"
                    type="button"
                    aria-selected={y === yr}
                    onClick={() => setYear(y)}
                    className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${y === yr ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    {y}
                  </button>
                ))}
              </div>
            </div>
            {season.has ? (
              <Radar values={season.values} year={yr} setTip={setTip} />
            ) : (
              <Empty text={`ปี ${yr} ยังไม่มีกำไรที่รับรู้`} className="mt-3 h-[260px]" />
            )}
            <div className="mt-2 grid grid-cols-2 gap-3">
              <div>
                <div className="text-[13px] text-muted-foreground">กำไรที่รับรู้ปี {yr}</div>
                <div className={`mt-1.5 text-[24px] font-medium leading-none tabular-nums ${tone(season.realized)}`}><CountUp value={season.realized} prefix="$" decimals={2} /></div>
              </div>
              <div>
                <div className="text-[13px] text-muted-foreground">กำไรรับรู้สะสมทั้งหมด</div>
                <div className={`mt-1.5 text-[24px] font-medium leading-none tabular-nums ${tone(totalRealized)}`}><CountUp value={totalRealized} prefix="$" decimals={2} /></div>
              </div>
            </div>
            <div className="mt-3.5">
              <div className="flex justify-between border-t border-border py-[11px] text-sm">
                <span className="text-muted-foreground">รายการซื้อขายปี {yr}</span>
                <span className="tabular-nums">{season.count}</span>
              </div>
              {season.rows.map(([sym, v]) => (
                <div key={sym} className="flex justify-between border-t border-border py-[11px] text-sm">
                  <span className="text-muted-foreground">{sym}</span>
                  <span className={`tabular-nums ${tone(v)}`}>{sUsd(v)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {book && view === "portfolio" && positionsTable}

      {book && view === "positions" && (
        <>
          <div className="grid grid-cols-12 gap-4">{allocation}</div>
          {positionsTable}
        </>
      )}

      {view === "orders" && (
        <Card label="ประวัติการซื้อขาย">
          <Table head={["เวลา", "Symbol", "ฝั่ง", "จำนวน", "ราคา", "ค่าธรรมเนียม", "กำไรที่รับรู้", "โน้ต"]}>
            {trades.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">ยังไม่มีรายการ</td></tr>
            )}
            {trades.map((t) => (
              <tr key={t.id} className="border-t border-border">
                <td className="px-3 py-3 text-xs tabular-nums text-muted-foreground">
                  {new Date(t.ts).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" })}
                </td>
                <td className="px-3 py-3 text-right font-semibold">{t.symbol}</td>
                <td className={`px-3 py-3 text-right font-medium ${t.side === "buy" ? "text-emerald-500" : "text-rose-500"}`}>{t.side === "buy" ? "ซื้อ" : "ขาย"}</td>
                <td className="px-3 py-3 text-right tabular-nums">{nf(t.qty, 0)}</td>
                <td className="px-3 py-3 text-right tabular-nums">{usd(t.price)}</td>
                <td className="px-3 py-3 text-right tabular-nums">{usd(t.fee)}</td>
                <td className={`px-3 py-3 text-right tabular-nums ${t.realized_pnl == null ? "" : tone(t.realized_pnl)}`}>
                  {t.realized_pnl == null ? "-" : sUsd(t.realized_pnl)}
                </td>
                <td className="px-3 py-3 text-right text-muted-foreground">{t.note ?? ""}</td>
              </tr>
            ))}
          </Table>
        </Card>
      )}

      <Tooltip tip={tip} />
    </div>
  );
}
