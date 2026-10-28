import { useState } from "react";
import type { PointerEvent as RPointerEvent, ReactNode } from "react";
import { InfoTip } from "./InfoTip";
import { dailyFromCumulative, histogram, labelIndexes, linePath, nearestIndex, niceTicks } from "./chartMath";

/* ───────── types (ตรงกับ /api/stocks/risk/performance และ /metrics) ───────── */
interface M { value: number | null; status: string; unit?: string; n_obs?: number | null; reason?: string | null }
interface SeriesPt { date: string; portfolio: number; benchmark: number | null; active: number | null }
interface MonthRow { period: string; portfolio: number; benchmark: number | null; active: number | null; days: number }
interface RollPt { date: string; volatility: number; beta?: number | null; sharpe?: number | null }
export interface PerfRes {
  meta?: { as_of?: string; benchmark?: { symbol: string; name: string } };
  metrics?: Record<string, M> | null;
  series?: SeriesPt[] | null;
  monthly?: MonthRow[] | null;
  rolling?: { window_trading_days: number; points: RollPt[] } | null;
}
export interface TailLite { var_95?: M; es_95?: M }

/* ───────── helpers ───────── */
const MIN_HIST = 20;
const pctS = (v: number | null | undefined, d = 2, sign = false) =>
  v == null || !Number.isFinite(v) ? "—" : `${sign && v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`;
const ppS = (v: number | null | undefined) =>
  v == null || !Number.isFinite(v) ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)} pp`;
const num2 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(2));
const toneCls = (v: number | null | undefined) =>
  v == null || v === 0 ? "text-foreground" : v > 0 ? "text-emerald-500" : "text-rose-500";

function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-3xl border border-border bg-card p-5">{children}</div>;
}
function Tag({ children, warn = false }: { children: ReactNode; warn?: boolean }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs ${warn ? "bg-amber-500/10 text-amber-500" : "bg-muted text-muted-foreground"}`}>
      {children}
    </span>
  );
}
function Progress({ have, need, unit = "วัน" }: { have: number; need: number; unit?: string }) {
  const w = Math.max(0, Math.min(1, need > 0 ? have / need : 0)) * 100;
  return (
    <div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-muted-foreground/60" style={{ width: `${w}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground tabular-nums">
        มีข้อมูล {have} จาก {need} {unit}
      </p>
    </div>
  );
}
function Stat({ label, value, cls = "", note, help }: { label: string; value: string; cls?: string; note?: string; help?: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">
        {label}
        {help && <InfoTip k={help} />}
      </p>
      <p className={`mt-1 text-xl font-medium tabular-nums ${cls}`}>{value}</p>
      {note && <p className="mt-0.5 text-[11px] text-muted-foreground">{note}</p>}
    </div>
  );
}
const insufficient = (m?: M) => (m && m.value == null ? `ข้อมูลยังไม่พอ${m.n_obs != null ? ` (มี ${m.n_obs} วัน)` : ""}` : undefined);

/* ───────── generic line chart (SVG ล้วน) ───────── */
interface Line { name: string; values: (number | null)[]; stroke: string; swatch: string; fill: string; dashed?: boolean }

function LineChart({ dates, lines, fmt, zero = false, label }: {
  dates: string[]; lines: Line[]; fmt: (v: number | null) => string; zero?: boolean; label: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const n = dates.length;
  const all = lines.flatMap((l) => l.values).filter((v): v is number => v != null && Number.isFinite(v));
  if (n < 2 || all.length === 0) return null;

  const W = 600, H = 190, PL = 46, PR = 8, PT = 8, PB = 20;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  if (hi - lo < 1e-9) { lo -= 0.005; hi += 0.005; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const ticks = niceTicks(lo, hi, 4);
  const sx = (i: number) => PL + (i / (n - 1)) * (W - PL - PR);
  const sy = (v: number) => PT + (1 - (v - lo) / (hi - lo)) * (H - PT - PB);
  const xl = labelIndexes(n, 4);

  const onMove = (e: RPointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    if (r.width <= 0) return;
    const frac = (((e.clientX - r.left) / r.width) * W - PL) / (W - PL - PR);
    setHover(nearestIndex(frac, n));
  };

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {lines.map((l) => (
          <span key={l.name} className="inline-flex items-center gap-1.5">
            <span className={`inline-block size-2 rounded-full ${l.swatch}`} />
            {l.name}
          </span>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-48 w-full touch-pan-y"
        role="img"
        aria-label={label}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PL} x2={W - PR} y1={sy(t)} y2={sy(t)} className="stroke-border" strokeWidth={0.5} />
            <text x={PL - 6} y={sy(t) + 3} textAnchor="end" fontSize={10} className="fill-muted-foreground">{fmt(t)}</text>
          </g>
        ))}
        {lo < 0 && hi > 0 && (
          <line x1={PL} x2={W - PR} y1={sy(0)} y2={sy(0)} className="stroke-muted-foreground" strokeWidth={0.8} strokeDasharray="3 3" />
        )}
        {xl.map((i) => (
          <text key={i} x={sx(i)} y={H - 5} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} fontSize={10} className="fill-muted-foreground">
            {dates[i]}
          </text>
        ))}
        {lines.map((l) => (
          <path
            key={l.name}
            d={linePath(l.values.map((y, i) => ({ x: i, y })), sx, sy)}
            fill="none"
            className={l.stroke}
            strokeWidth={1.6}
            strokeDasharray={l.dashed ? "5 3" : undefined}
            strokeLinejoin="round"
          />
        ))}
        {hover != null && (
          <g>
            <line x1={sx(hover)} x2={sx(hover)} y1={PT} y2={H - PB} className="stroke-muted-foreground" strokeWidth={0.8} />
            {lines.map((l) => {
              const v = l.values[hover];
              return v == null ? null : <circle key={l.name} cx={sx(hover)} cy={sy(v)} r={3} className={l.fill} />;
            })}
          </g>
        )}
      </svg>
      <p className="mt-1 min-h-4 text-xs text-muted-foreground tabular-nums">
        {hover != null ? `${dates[hover]} · ${lines.map((l) => `${l.name} ${fmt(l.values[hover])}`).join(" · ")}` : `${dates[0]} → ${dates[n - 1]} · เลื่อนเมาส์/นิ้วบนกราฟเพื่อดูค่ารายวัน`}
      </p>
    </div>
  );
}

/* ───────── 4.2 Performance & Benchmarking ───────── */
export function PerformanceSection({ p }: { p: PerfRes | null }) {
  const title = <h2 className="text-base font-medium">ผลตอบแทนเทียบดัชนี</h2>;
  const series = p?.series ?? [];
  const days = Math.max(series.length - 1, 0);
  const bench = p?.meta?.benchmark?.name ?? "S&P 500";
  const m = p?.metrics ?? {};
  if (!p || series.length === 0) {
    return (
      <Panel>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">ยังไม่มีข้อมูลผลตอบแทน (ต้องมีราคาปิดอย่างน้อย 2 วัน)</p>
      </Panel>
    );
  }
  const dates = series.map((s) => s.date);
  const hasBench = series.some((s) => s.benchmark != null);
  const monthly = p.monthly ?? [];
  const lastIdx = monthly.length - 1;

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {title}
        <Tag>เทียบ {bench} (ดัชนีราคา ไม่รวมปันผล)</Tag>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-5">
        <Stat label="ผลตอบแทนพอร์ต" value={pctS(m.portfolio_return?.value, 2, true)} cls={toneCls(m.portfolio_return?.value)} help="portfolio_return" />
        <Stat label={`ผลตอบแทน ${bench}`} value={pctS(m.benchmark_return?.value, 2, true)} cls={toneCls(m.benchmark_return?.value)} help="benchmark_return" />
        <Stat label="ส่วนเกินสะสม" value={ppS(m.active_return?.value)} cls={toneCls(m.active_return?.value)} help="active_return" />
        <Stat label="Relative wealth" value={pctS(m.relative_wealth?.value, 2, true)} cls={toneCls(m.relative_wealth?.value)}
          note="(1+Rp)/(1+Rb) − 1" help="relative_wealth" />
        <Stat label="CAGR" value={m.cagr?.value == null ? "—" : pctS(m.cagr.value, 2, true)} cls={toneCls(m.cagr?.value)}
          note={insufficient(m.cagr) ?? "ผลตอบแทนต่อปีแบบทบต้น"} help="cagr" />
      </div>

      <div className="mt-5">
        <p className="mb-2 text-sm text-muted-foreground">ผลตอบแทนสะสม พอร์ตเทียบ {bench}</p>
        {days < 2 ? (
          <div className="rounded-2xl border border-dashed border-border p-4">
            <p className="mb-3 text-sm text-muted-foreground">กราฟจะแสดงเมื่อมีข้อมูลอย่างน้อย 2 วัน</p>
            <Progress have={days} need={2} />
          </div>
        ) : (
          <LineChart
            dates={dates}
            label="กราฟผลตอบแทนสะสมของพอร์ตเทียบดัชนี"
            fmt={(v) => pctS(v, 2)}
            zero
            lines={[
              { name: "พอร์ต", values: series.map((s) => s.portfolio), stroke: "stroke-sky-500", swatch: "bg-sky-500", fill: "fill-sky-500" },
              ...(hasBench ? [{ name: bench, values: series.map((s) => s.benchmark), stroke: "stroke-muted-foreground", swatch: "bg-muted-foreground", fill: "fill-muted-foreground", dashed: true }] : []),
            ]}
          />
        )}
      </div>

      {hasBench && days >= 2 && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-muted-foreground">ส่วนเกินสะสมเทียบดัชนี (จุดเปอร์เซ็นต์)</p>
          <LineChart
            dates={dates}
            label="กราฟส่วนเกินสะสมเทียบดัชนี"
            fmt={(v) => (v == null ? "—" : `${(v * 100).toFixed(2)} pp`)}
            zero
            lines={[{ name: "ส่วนเกิน", values: series.map((s) => s.active), stroke: "stroke-emerald-500", swatch: "bg-emerald-500", fill: "fill-emerald-500" }]}
          />
        </div>
      )}

      <div className="mt-5">
        <p className="mb-2 text-sm text-muted-foreground">ผลตอบแทนรายเดือน</p>
        {monthly.length === 0 ? (
          <p className="text-sm text-muted-foreground">ยังไม่มีข้อมูลรายเดือน</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1 pr-3 font-normal">เดือน</th>
                  <th className="py-1 pr-3 text-right font-normal">พอร์ต</th>
                  <th className="py-1 pr-3 text-right font-normal">{bench}</th>
                  <th className="py-1 pr-3 text-right font-normal">ส่วนเกิน</th>
                  <th className="py-1 text-right font-normal">วัน</th>
                </tr>
              </thead>
              <tbody>
                {monthly.map((r, i) => (
                  <tr key={r.period} className="border-t border-border">
                    <td className="py-1.5 pr-3">
                      {r.period}
                      {(i === 0 || i === lastIdx) && <span className="ml-2"><Tag warn>บางส่วน</Tag></span>}
                    </td>
                    <td className={`py-1.5 pr-3 text-right ${toneCls(r.portfolio)}`}>{pctS(r.portfolio, 2, true)}</td>
                    <td className={`py-1.5 pr-3 text-right ${toneCls(r.benchmark)}`}>{pctS(r.benchmark, 2, true)}</td>
                    <td className={`py-1.5 pr-3 text-right ${toneCls(r.active)}`}>{ppS(r.active)}</td>
                    <td className="py-1.5 text-right text-muted-foreground">{r.days}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted-foreground">เดือนแรกและเดือนล่าสุดอาจมีข้อมูลไม่เต็มเดือน (ดูจำนวนวัน)</p>
          </div>
        )}
      </div>
    </Panel>
  );
}

/* ───────── 4.3 Rolling metrics ───────── */
export function RollingSection({ p }: { p: PerfRes | null }) {
  const title = <h2 className="text-base font-medium">Rolling ความผันผวน / Beta / Sharpe</h2>;
  const w = p?.rolling?.window_trading_days ?? 63;
  const pts = p?.rolling?.points ?? [];
  const days = Math.max((p?.series?.length ?? 0) - 1, 0);
  if (pts.length < 2) {
    return (
      <Panel>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">
          กราฟ rolling ใช้หน้าต่าง {w} วันซื้อขาย จึงต้องมีข้อมูลอย่างน้อย {w + 1} วันจึงจะได้จุดอย่างน้อย 2 จุด
        </p>
        <div className="mt-3"><Progress have={days} need={w + 1} /></div>
      </Panel>
    );
  }
  const dates = pts.map((x) => x.date);
  const has = (k: "beta" | "sharpe") => pts.some((x) => x[k] != null);
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {title}
        <Tag>หน้าต่าง {w} วันซื้อขาย</Tag>
      </div>
      <div className="mt-4">
        <p className="mb-2 text-sm text-muted-foreground">ความผันผวนต่อปี</p>
        <LineChart dates={dates} label="Rolling volatility" fmt={(v) => pctS(v, 1)}
          lines={[{ name: "ความผันผวน", values: pts.map((x) => x.volatility), stroke: "stroke-amber-500", swatch: "bg-amber-500", fill: "fill-amber-500" }]} />
      </div>
      {has("beta") && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-muted-foreground">Beta เทียบดัชนี</p>
          <LineChart dates={dates} label="Rolling beta" fmt={num2}
            lines={[{ name: "Beta", values: pts.map((x) => x.beta ?? null), stroke: "stroke-violet-500", swatch: "bg-violet-500", fill: "fill-violet-500" }]} />
        </div>
      )}
      {has("sharpe") && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-muted-foreground">Sharpe ratio (ต่อปี)</p>
          <LineChart dates={dates} label="Rolling Sharpe" fmt={num2} zero
            lines={[{ name: "Sharpe", values: pts.map((x) => x.sharpe ?? null), stroke: "stroke-sky-500", swatch: "bg-sky-500", fill: "fill-sky-500" }]} />
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        ค่าที่ใช้หน้าต่างสั้นแกว่งตามข้อมูลช่วงนั้นมาก ไม่ควรตีความเป็นแนวโน้มระยะยาว
      </p>
    </Panel>
  );
}

/* ───────── 4.4 Loss distribution ───────── */
export function LossDistributionSection({ p, tail }: { p: PerfRes | null; tail?: TailLite | null }) {
  const title = <h2 className="text-base font-medium">การกระจายผลตอบแทนรายวัน</h2>;
  const rets = dailyFromCumulative((p?.series ?? []).map((s) => s.portfolio));
  const n = rets.length;
  if (n < MIN_HIST) {
    return (
      <Panel>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">
          กราฟการกระจายต้องมีผลตอบแทนรายวันอย่างน้อย {MIN_HIST} วัน ไม่เช่นนั้นรูปร่างของกราฟไม่น่าเชื่อถือ
        </p>
        <div className="mt-3"><Progress have={n} need={MIN_HIST} /></div>
      </Panel>
    );
  }
  const bins = histogram(rets);
  const varV = tail?.var_95?.value != null ? -tail.var_95.value : null;
  const esV = tail?.es_95?.value != null ? -tail.es_95.value : null;
  const W = 600, H = 170, PL = 8, PR = 8, PT = 14, PB = 22;
  const lo = Math.min(bins[0].lo, varV ?? Infinity, esV ?? Infinity);
  const hi = Math.max(bins[bins.length - 1].hi, 1e-9);
  const span = Math.max(hi - lo, 1e-9);
  const sx = (v: number) => PL + ((v - lo) / span) * (W - PL - PR);
  const maxC = Math.max(...bins.map((b) => b.count), 1);
  const sy = (c: number) => H - PB - (c / maxC) * (H - PB - PT);
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {title}
        <Tag warn={n < 60}>{n} วัน{n < 60 ? " · ตัวอย่างน้อย" : ""}</Tag>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-44 w-full" role="img" aria-label="ฮิสโตแกรมผลตอบแทนรายวันของพอร์ต">
        {bins.map((b, i) => (
          <rect key={i} x={sx(b.lo) + 0.5} y={sy(b.count)} width={Math.max(sx(b.hi) - sx(b.lo) - 1, 1)} height={H - PB - sy(b.count)}
            className={(b.lo + b.hi) / 2 < 0 ? "fill-rose-500/60" : "fill-emerald-500/60"}>
            <title>{`${pctS(b.lo, 2, true)} ถึง ${pctS(b.hi, 2, true)}: ${b.count} วัน`}</title>
          </rect>
        ))}
        {lo < 0 && hi > 0 && <line x1={sx(0)} x2={sx(0)} y1={PT} y2={H - PB} className="stroke-muted-foreground" strokeWidth={0.8} strokeDasharray="3 3" />}
        {varV != null && (
          <g>
            <line x1={sx(varV)} x2={sx(varV)} y1={PT - 4} y2={H - PB} className="stroke-rose-500" strokeWidth={1.2} />
            <text x={sx(varV)} y={PT - 5} textAnchor="middle" fontSize={10} className="fill-rose-500">VaR 95%</text>
          </g>
        )}
        {esV != null && (
          <g>
            <line x1={sx(esV)} x2={sx(esV)} y1={PT - 4} y2={H - PB} className="stroke-amber-500" strokeWidth={1.2} strokeDasharray="4 2" />
            <text x={sx(esV)} y={PT - 5} textAnchor="middle" fontSize={10} className="fill-amber-500">ES</text>
          </g>
        )}
        <text x={PL} y={H - 6} fontSize={10} className="fill-muted-foreground">{pctS(lo, 2, true)}</text>
        <text x={W - PR} y={H - 6} textAnchor="end" fontSize={10} className="fill-muted-foreground">{pctS(hi, 2, true)}</text>
      </svg>
      <p className="mt-2 text-xs text-muted-foreground">
        แกนนอน = ผลตอบแทนรายวัน · แกนตั้ง = จำนวนวัน · VaR/ES 95% เป็นค่าประวัติศาสตร์ 1 วัน (ไม่ใช่การพยากรณ์)
        {varV == null && " · VaR/ES ยังไม่แสดงเพราะข้อมูลไม่พอ"}
      </p>
    </Panel>
  );
}
