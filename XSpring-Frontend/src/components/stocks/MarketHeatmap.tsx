import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

/* ------------------------------------------------------------------ */
/*  Heatmap ตลาดหุ้นสหรัฐ ขนาด = มูลค่าตลาด, สี = เปลี่ยนแปลงวันนี้        */
/*  ดึงจาก GET /api/stocks/heatmap?index=sp500|dow|ndx                   */
/*  (ไม่ผูกกับคริปโต) สี/พื้นผิวมาจากธีมของเว็บ                           */
/* ------------------------------------------------------------------ */

type Api = (path: string, opts?: { method?: string; body?: unknown }) => Promise<any>;
type IndexId = "sp500" | "dow" | "ndx";
type Item = { symbol: string; name: string; sector: string; marketCap: number; price: number; changePercent: number };
type Resp = { index: IndexId; total: number; ready: number; updatedAt: string | null; items: Item[] };
type Q = { symbol: string; price: number; changePercent: number };
type Tip = { x: number; y: number; item: Item } | null;

const INDEXES: { id: IndexId; name: string; proxy: string; count: number }[] = [
  { id: "sp500", name: "S&P 500", proxy: "SPY", count: 500 },
  { id: "dow", name: "Dow Jones 30", proxy: "DIA", count: 30 },
  { id: "ndx", name: "Nasdaq 100", proxy: "QQQ", count: 100 },
];

const SECTOR_TH: Record<string, string> = {
  "Information Technology": "เทคโนโลยี",
  "Health Care": "สุขภาพ",
  Financials: "การเงิน",
  "Consumer Discretionary": "สินค้าฟุ่มเฟือย",
  "Communication Services": "สื่อสาร",
  Industrials: "อุตสาหกรรม",
  "Consumer Staples": "สินค้าจำเป็น",
  Energy: "พลังงาน",
  Utilities: "สาธารณูปโภค",
  "Real Estate": "อสังหาฯ",
  Materials: "วัตถุดิบ",
};

/* ---------------- helpers ---------------- */

const usd = (n: number) => "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
const tone = (n: number) => (n > 0 ? "text-emerald-500" : n < 0 ? "text-rose-500" : "text-muted-foreground");
/** marketCap จาก API เป็นหน่วยล้านดอลลาร์ */
const capText = (m: number) => (m >= 1e6 ? `$${(m / 1e6).toFixed(2)}T` : m >= 1e3 ? `$${(m / 1e3).toFixed(1)}B` : `$${m.toFixed(0)}M`);

const NEUTRAL = [63, 63, 70];
const UP = [5, 150, 105];
const DOWN = [225, 29, 72];
const FULL = 3; // ±3% = สีเข้มสุด
function heat(c: number) {
  const t = Math.min(1, Math.abs(c) / FULL), to = c >= 0 ? UP : DOWN;
  const m = (i: number) => Math.round(NEUTRAL[i] + (to[i] - NEUTRAL[i]) * t);
  return `rgb(${m(0)},${m(1)},${m(2)})`;
}

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

type Rect = { x: number; y: number; w: number; h: number };
function squarify<T extends { v: number }>(items: T[], x: number, y: number, w: number, h: number): (T & Rect)[] {
  if (w <= 0 || h <= 0 || !items.length) return [];
  const total = items.reduce((a, b) => a + b.v, 0) || 1, scale = (w * h) / total;
  const out: (T & Rect)[] = [];
  let rest = items.map((item) => ({ item, a: Math.max(item.v * scale, 1e-6) }));
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
      const cw = s / h;
      let cy = y;
      for (const r of row) { const rh = r.a / cw; out.push({ ...r.item, x, y: cy, w: cw, h: rh }); cy += rh; }
      x += cw; w -= cw;
    } else {
      const rh = s / w;
      let cx = x;
      for (const r of row) { const rw = r.a / rh; out.push({ ...r.item, x: cx, y, w: rw, h: rh }); cx += rw; }
      y += rh; h -= rh;
    }
  }
  return out;
}

/* ---------------- ชิ้นส่วนร่วม ---------------- */

const Card = ({ children, className = "" }: { children: ReactNode; className?: string }) => (
  <section className={`rounded-2xl border border-border bg-card p-5 text-card-foreground ${className}`}>{children}</section>
);
const Pill = ({ on, children, onClick }: { on: boolean; children: ReactNode; onClick: () => void }) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded-full px-4 py-1.5 text-sm transition ${on ? "bg-emerald-500 font-medium text-black" : "border border-border bg-card text-foreground/80 hover:bg-accent"}`}
  >
    {children}
  </button>
);

/* ---------------- Heatmap ---------------- */

function Heatmap({ items, onOpen, setTip }: { items: Item[]; onOpen: (s: string) => void; setTip: (t: Tip) => void }) {
  const [ref, { w: W, h: H }] = useSize();
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const r = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(r);
  }, []);

  const sectors = useMemo(() => {
    if (!W || !H || !items.length) return [];
    const by: Record<string, Item[]> = {};
    for (const it of items) (by[it.sector || "อื่นๆ"] ||= []).push(it);
    const secs = Object.entries(by)
      .map(([name, list]) => ({ name, v: list.reduce((a, b) => a + b.marketCap, 0), list }))
      .sort((a, b) => b.v - a.v);
    return squarify(secs, 0, 0, W, H).map((s) => {
      const pad = 2, head = s.w > 70 && s.h > 46 ? 18 : 0;
      const tiles = squarify(
        s.list.map((i) => ({ ...i, v: i.marketCap })).sort((a, b) => b.v - a.v),
        s.x + pad, s.y + pad + head, s.w - pad * 2, s.h - pad * 2 - head,
      );
      return { ...s, head, tiles };
    });
  }, [items, W, H]);

  return (
    <div
      ref={ref}
      className={`relative h-[480px] w-full overflow-hidden rounded-xl bg-muted/40 transition-opacity duration-700 sm:h-[560px] lg:h-[640px] ${shown ? "opacity-100" : "opacity-0"}`}
      role="img"
      aria-label="Heatmap ตลาดหุ้น ขนาดตามมูลค่าตลาด สีตามการเปลี่ยนแปลงวันนี้"
    >
      {sectors.map((s) => (
        <div key={s.name}>
          <div className="absolute rounded-lg border border-border/60" style={{ left: s.x, top: s.y, width: s.w, height: s.h }} />
          {s.head > 0 && (
            <div
              className="absolute truncate px-2 pt-[3px] text-[11px] font-semibold text-muted-foreground"
              style={{ left: s.x, top: s.y, width: s.w, height: s.head + 2 }}
            >
              {SECTOR_TH[s.name] ?? s.name}
            </div>
          )}
          {s.tiles.map((t) => {
            const m = Math.min(t.w, t.h), fs = Math.max(9, Math.min(26, m / 3.4));
            const showSym = t.w > 30 && t.h > 20, showPct = t.w > 46 && t.h > 36;
            return (
              <button
                key={t.symbol}
                type="button"
                onClick={() => onOpen(t.symbol)}
                onPointerMove={(e) => setTip({ x: e.clientX, y: e.clientY, item: t })}
                onPointerLeave={() => setTip(null)}
                aria-label={`${t.symbol} ${pct(t.changePercent)}`}
                className="absolute flex flex-col items-center justify-center overflow-hidden rounded-[5px] text-white outline-none transition-[filter] hover:brightness-125 focus-visible:ring-2 focus-visible:ring-white"
                style={{ left: t.x, top: t.y, width: Math.max(t.w - 1.5, 0), height: Math.max(t.h - 1.5, 0), background: heat(t.changePercent) }}
              >
                {showSym && <span className="font-semibold leading-none" style={{ fontSize: fs }}>{t.symbol}</span>}
                {showPct && <span className="mt-1 leading-none tabular-nums opacity-90" style={{ fontSize: Math.max(9, fs * 0.62) }}>{pct(t.changePercent)}</span>}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  const { item: i } = tip;
  const flip = typeof window !== "undefined" && tip.x > window.innerWidth - 240;
  return (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 min-w-[190px] rounded-xl border border-border bg-card px-3 py-2 text-xs text-foreground shadow-xl"
      style={{ left: tip.x, top: tip.y, transform: `translate(${flip ? "calc(-100% - 14px)" : "14px"}, 14px)` }}
    >
      <div className="text-sm font-semibold">{i.symbol}</div>
      <div className="mb-1.5 text-muted-foreground">{i.name} · {SECTOR_TH[i.sector] ?? i.sector}</div>
      <div className="flex justify-between gap-4"><span className="text-muted-foreground">ราคา</span><b className="tabular-nums">{usd(i.price)}</b></div>
      <div className="flex justify-between gap-4"><span className="text-muted-foreground">วันนี้</span><b className={`tabular-nums ${tone(i.changePercent)}`}>{pct(i.changePercent)}</b></div>
      <div className="flex justify-between gap-4"><span className="text-muted-foreground">มูลค่าตลาด</span><b className="tabular-nums">{capText(i.marketCap)}</b></div>
    </div>
  );
}

/* ---------------- หน้าหลัก ---------------- */

export default function MarketHeatmap({ api, open }: { api: Api; open: (symbol: string) => void }) {
  const [index, setIndex] = useState<IndexId>("sp500");
  const [data, setData] = useState<Resp | null>(null);
  const [error, setError] = useState("");
  const [quotes, setQuotes] = useState<Record<string, Q>>({});
  const [kind, setKind] = useState<"gainers" | "losers" | "cap">("gainers");
  const [tip, setTip] = useState<Tip>(null);

  /* heatmap: โหลดใหม่เมื่อเปลี่ยนดัชนี และทุก 60 วินาที */
  useEffect(() => {
    let off = false;
    setData(null);
    setError("");
    const load = () =>
      api(`/heatmap?index=${index}`)
        .then((d: Resp) => { if (!off) { setData(d); setError(""); } })
        .catch((e: Error) => { if (!off) setError(e.message || "error"); });
    load();
    const id = setInterval(load, 60000);
    return () => { off = true; clearInterval(id); };
  }, [api, index]);

  /* ราคา SPY / DIA / QQQ สำหรับการ์ดดัชนี (ใช้ endpoint เดิม) */
  useEffect(() => {
    let off = false;
    const load = () =>
      api("/market/overview")
        .then((d: Q[]) => {
          if (off || !Array.isArray(d)) return;
          setQuotes(Object.fromEntries(d.map((q) => [q.symbol, q])));
        })
        .catch(() => {});
    load();
    const id = setInterval(load, 60000);
    return () => { off = true; clearInterval(id); };
  }, [api]);

  const items = data?.items ?? [];
  const cur = INDEXES.find((i) => i.id === index)!;

  const movers = useMemo(() => {
    const a = [...items];
    if (kind === "gainers") a.sort((x, y) => y.changePercent - x.changePercent);
    else if (kind === "losers") a.sort((x, y) => x.changePercent - y.changePercent);
    else a.sort((x, y) => y.marketCap - x.marketCap);
    return a.slice(0, 10);
  }, [items, kind]);

  const breadth = useMemo(() => {
    const up = items.filter((i) => i.changePercent > 0).length;
    const down = items.filter((i) => i.changePercent < 0).length;
    return { up, down, flat: items.length - up - down };
  }, [items]);

  const progress = data && data.total ? Math.round((data.ready / data.total) * 100) : 0;

  return (
    <div className="space-y-5">
      {/* เลือกดัชนี */}
      <div className="grid gap-4 md:grid-cols-3">
        {INDEXES.map((x) => {
          const q = quotes[x.proxy];
          const on = x.id === index;
          return (
            <button
              key={x.id}
              type="button"
              aria-pressed={on}
              onClick={() => setIndex(x.id)}
              className={`rounded-2xl border bg-card p-5 text-left transition hover:bg-accent/40 ${on ? "border-emerald-500" : "border-border"}`}
            >
              <div className="flex items-center justify-between">
                <div className={`flex h-10 min-w-10 items-center justify-center rounded-xl px-2 text-sm font-semibold ${on ? "bg-emerald-500 text-black" : "bg-muted text-emerald-400"}`}>{x.count}</div>
                <span className="text-xs text-muted-foreground">{x.proxy}</span>
              </div>
              <div className="mt-4 text-sm text-muted-foreground">{x.name}</div>
              <div className="mt-1 flex items-end justify-between gap-2">
                <div className="text-2xl font-bold text-foreground tabular-nums">{q ? usd(q.price) : "–"}</div>
                {q && (
                  <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium tabular-nums ${q.changePercent >= 0 ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"}`}>
                    {q.changePercent >= 0 ? "↑" : "↓"} {pct(q.changePercent)}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Heatmap */}
      <Card>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-foreground">Heatmap {cur.name}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">ขนาดตามมูลค่าตลาด · สีตามการเปลี่ยนแปลงวันนี้ · กดที่หุ้นเพื่อดูข้อมูลบริษัท</p>
          </div>
          {items.length > 0 && (
            <div className="flex items-center gap-3 text-xs tabular-nums">
              <span className="text-emerald-500">↑ {breadth.up}</span>
              <span className="text-rose-500">↓ {breadth.down}</span>
              <span className="text-muted-foreground">– {breadth.flat}</span>
            </div>
          )}
        </div>

        {error && (
          <p className="rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-400">
            โหลด Heatmap ไม่ได้: {error}
            {error.toLowerCase().includes("not found") && " (backend ยังไม่มี /api/stocks/heatmap ตรวจว่า include_router แล้วและ deploy ใหม่)"}
          </p>
        )}

        {data && data.ready < data.total && (
          <div className="mb-4 rounded-xl bg-muted/50 px-3 py-2.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{data.total === 0 ? "กำลังเตรียมรายชื่อหุ้น…" : `กำลังรวบรวมราคา ${data.ready}/${data.total} ตัว (ดึงทีละตัว ครั้งแรกอาจใช้เวลาหลายนาที)`}</span>
              <span className="tabular-nums">{progress}%</span>
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-700" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        {!data && !error && <div className="h-[480px] animate-pulse rounded-xl bg-muted/50 sm:h-[560px] lg:h-[640px]" />}
        {data && items.length > 0 && <Heatmap key={index} items={items} onOpen={open} setTip={setTip} />}
        {data && items.length === 0 && !error && (
          <div className="grid h-[240px] place-items-center rounded-xl border border-dashed border-border text-center text-sm text-muted-foreground">
            ยังไม่มีข้อมูลราคา backend กำลังเริ่มดึง รอสักครู่แล้วหน้านี้จะอัปเดตเอง
          </div>
        )}

        {items.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <span className="tabular-nums">-{FULL}%</span>
              <div className="h-2 w-40 rounded-full" style={{ background: `linear-gradient(90deg, rgb(${DOWN.join(",")}), rgb(${NEUTRAL.join(",")}), rgb(${UP.join(",")}))` }} />
              <span className="tabular-nums">+{FULL}%</span>
            </div>
            {data?.updatedAt && <span>อัปเดตล่าสุด {new Date(data.updatedAt).toLocaleString("th-TH")}</span>}
          </div>
        )}
      </Card>

      {/* หุ้นเคลื่อนไหวเด่น (ภายในดัชนีที่เลือก) */}
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-foreground">หุ้นเคลื่อนไหวเด่น</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">เฉพาะหุ้นใน {cur.name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Pill on={kind === "gainers"} onClick={() => setKind("gainers")}>ขึ้นแรง</Pill>
            <Pill on={kind === "losers"} onClick={() => setKind("losers")}>ลงแรง</Pill>
            <Pill on={kind === "cap"} onClick={() => setKind("cap")}>มูลค่าตลาดสูงสุด</Pill>
          </div>
        </div>
        {movers.length === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">ยังไม่มีข้อมูล</p>
        ) : (
          <div className="divide-y divide-border">
            {movers.map((r) => (
              <button
                key={r.symbol}
                type="button"
                onClick={() => open(r.symbol)}
                className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-4 py-2.5 text-sm hover:bg-muted/50 sm:grid-cols-[88px_1fr_auto_88px_96px]"
              >
                <span className="text-left font-semibold text-foreground">{r.symbol}</span>
                <span className="hidden truncate text-left text-muted-foreground sm:block">{r.name}</span>
                <span className="text-right tabular-nums text-foreground/80">{usd(r.price)}</span>
                <span className={`text-right tabular-nums ${tone(r.changePercent)}`}>{pct(r.changePercent)}</span>
                <span className="hidden text-right tabular-nums text-muted-foreground sm:block">{capText(r.marketCap)}</span>
              </button>
            ))}
          </div>
        )}
      </Card>

      <Tooltip tip={tip} />
    </div>
  );
}
