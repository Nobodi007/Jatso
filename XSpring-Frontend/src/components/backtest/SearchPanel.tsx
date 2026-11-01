import { useEffect, useMemo, useRef, useState } from "react"

// ค้นหา edge แบบไม่หลอกตัวเอง: Sweep (heatmap) · Walk-forward · เทียบกับกลยุทธ์สุ่ม
// ไฟล์ใหม่ ไม่แตะโค้ด Backtest เดิม (เรียก API ของ Backtest Lab เท่านั้น)
type Props = { runId: string; apiBase: string; getToken: () => string | null }

type Tunable = {
  id: string; kind: string; group: string; integer: boolean; lo: number | null; hi: number | null
  current: number; label: string; suggest: { min: number; max: number; steps: number } | null
}
type TunMeta = { tunables: Tunable[]; metrics: { key: string; label: string }[]; limits: { max_params: number; max_values: number; max_cells: number; max_wf_runs: number } }
type MetricSet = { total_return: number | null; cagr: number | null; max_drawdown: number | null; calmar: number | null; sortino: number | null }
type Axis = { id: string; label: string; values: number[]; current: number }
type Cell = { i: number; j: number; params: Record<string, number>; metrics: MetricSet | null; trades: number | null; time_in_market: number | null; reason: string | null }
type Sweep = {
  metric: string; metric_label: string; axes: Axis[]; cells: Cell[]
  reference: { buy_hold: MetricSet; benchmark: MetricSet }
  best: { i: number; j: number; params: Record<string, number>; metrics: MetricSet } | null
  base: { i: number; j: number } | null
  summary: {
    cells: number; valid_cells: number; scored_cells: number; verdict: string
    best_value?: number; median_value?: number; worst_value?: number
    neighbor_ratio?: number | null; frac_ge_half_best?: number | null; best_on_edge?: boolean
    frac_positive?: number; frac_beat_buy_hold?: number; frac_beat_benchmark?: number
  }
  trials: number; note: string; caveats: string[]
}
type Stitched = { total_return: number; cagr: number | null; max_drawdown: number; calmar: number | null }
type FoldRow = {
  fold: number; train: [string, string]; test: [string, string]; trials: number; skipped?: string
  chosen?: Record<string, number>; is_value?: number | null; oos_value?: number | null
  oos?: MetricSet; fixed_oos?: MetricSet; buy_hold_oos?: MetricSet; benchmark_oos?: MetricSet
}
type WF = {
  metric: string; metric_label: string; anchored: boolean; axes: Axis[]; folds: FoldRow[]
  stitched: Record<"walk_forward" | "fixed_params" | "buy_hold" | "benchmark", Stitched>
  curves: { dates: string[]; walk_forward: number[]; fixed_params: number[]; buy_hold: number[]; benchmark: number[] }
  param_stability: Record<string, { label: string; chosen: number[]; distinct: number; changes: number }>
  summary: {
    folds_used: number; folds: number; trials: number; mean_is: number | null; mean_oos: number | null; oos_vs_is_ratio: number | null
    folds_positive: number; folds_beat_buy_hold: number; folds_beat_fixed: number
  }
  caveats: string[]
}
type StatRow = { actual: number | null; n: number; p5?: number; p25?: number; p50?: number; p75?: number; p95?: number; mean?: number; beats_fraction?: number; p_as_good?: number; p_bonferroni?: number }
type BL = {
  metric: string; metric_label: string; sims: number; seed: number; trials: number; trips: number
  stats: Record<"total_return" | "cagr" | "max_drawdown" | "calmar", StatRow>
  histogram: { edges: number[]; counts: number[] }
  replication: { actual: Stitched; model: Stitched; total_return_diff: number; within_tolerance: boolean }
  time_in_market: number; reading: string[]; notes: string[]; warnings: { code: string; message: string }[]; caveats: string[]
}

const card = "rounded-xl border bg-card p-5"
const num = "w-20 rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-primary"
const sel = "rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-primary"
const btn = "rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`)
const cls = (v: number | null | undefined) => (v == null ? "text-muted-foreground" : v >= 0 ? "text-emerald-500" : "text-red-500")
const isRatio = (m: string) => m === "calmar" || m === "sortino"
const fmt = (m: string, v: number | null | undefined) => (v == null ? "—" : isRatio(m) ? v.toFixed(2) : pct(v))
const short = (l: string) => l.split(" · ")[0] ?? l
const errText = (e: unknown) => (e instanceof Error ? e.message : "เกิดข้อผิดพลาด")

async function call<T>(apiBase: string, token: string | null, method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  if (!token) throw new Error("กรุณาเข้าสู่ระบบ")
  let res: Response
  try {
    res = await fetch(`${apiBase}/api/backtest-lab${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new Error("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้")
  }
  let data: { message?: string } | null = null
  try { data = await res.json() } catch { data = null }
  if (!res.ok) throw new Error(data?.message ?? `ผิดพลาด (${res.status})`)
  return data as T
}

function Tile({ label, value, c = "" }: { label: string; value: string; c?: string }) {
  return (
    <div className="rounded-lg border bg-muted/20 px-3 py-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold tabular-nums ${c}`}>{value}</div>
    </div>
  )
}

function Caveats({ items }: { items: string[] }) {
  return <ul className="list-disc space-y-0.5 pl-5 text-xs text-amber-500">{items.map((c) => <li key={c}>{c}</li>)}</ul>
}

function ErrBox({ msg }: { msg: string | null }) {
  return msg ? <div className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-red-500">{msg}</div> : null
}

// ------------------------------------------------------------------ เลือกพารามิเตอร์ (ใช้ร่วม Sweep / Walk-forward)
type Row = { id: string; min: string; max: string; steps: string }

function ParamPicker({ meta, rows, setRows }: { meta: TunMeta; rows: Row[]; setRows: (r: Row[]) => void }) {
  const byId = useMemo(() => new Map(meta.tunables.map((t) => [t.id, t])), [meta])
  const patch = (k: number, p: Partial<Row>) => setRows(rows.map((r, i) => (i === k ? { ...r, ...p } : r)))
  const choose = (k: number, id: string) => {
    const s = byId.get(id)?.suggest
    patch(k, { id, min: s ? String(s.min) : "", max: s ? String(s.max) : "", steps: s ? String(s.steps) : "5" })
  }
  return (
    <div className="space-y-2">
      {rows.map((r, k) => {
        const t = byId.get(r.id)
        return (
          <div key={k} className="flex flex-wrap items-end gap-2 text-xs text-muted-foreground">
            <label className="min-w-[220px]">
              พารามิเตอร์ {k + 1}
              <select className={`${sel} ml-2 max-w-[360px]`} value={r.id} onChange={(e) => choose(k, e.target.value)}>
                {meta.tunables.map((x) => <option key={x.id} value={x.id}>{x.label} (ใช้อยู่ {x.current})</option>)}
              </select>
            </label>
            <label>ต่ำสุด<input className={`${num} ml-2 w-16`} inputMode="decimal" value={r.min} onChange={(e) => patch(k, { min: e.target.value })} /></label>
            <label>สูงสุด<input className={`${num} ml-2 w-16`} inputMode="decimal" value={r.max} onChange={(e) => patch(k, { max: e.target.value })} /></label>
            <label>จำนวนค่า<input className={`${num} ml-2 w-12`} inputMode="numeric" value={r.steps} onChange={(e) => patch(k, { steps: e.target.value })} /></label>
            {t && t.lo != null && t.hi != null && <span>ช่วงที่รองรับ {t.lo}–{t.hi}</span>}
            {rows.length > 1 && <button type="button" className="rounded-md border px-2 py-1 hover:bg-accent" onClick={() => setRows(rows.filter((_, i) => i !== k))}>ลบ</button>}
          </div>
        )
      })}
      {rows.length < meta.limits.max_params && (
        <button type="button" className="rounded-md border px-3 py-1 text-xs hover:bg-accent"
          onClick={() => {
            const used = new Set(rows.map((r) => r.id))
            const t = meta.tunables.find((x) => !used.has(x.id))
            if (t) setRows([...rows, { id: t.id, min: String(t.suggest?.min ?? ""), max: String(t.suggest?.max ?? ""), steps: String(t.suggest?.steps ?? 5) }])
          }}>
          + เพิ่มพารามิเตอร์ตัวที่ 2 (heatmap)
        </button>
      )}
    </div>
  )
}

const toParams = (rows: Row[]) => rows.map((r) => ({ id: r.id, min: Number(r.min), max: Number(r.max), steps: Number(r.steps) }))

// ------------------------------------------------------------------ Sweep
const VERDICT: Record<string, { text: string; c: string }> = {
  plateau: { text: "ที่ราบ — ผลดีทั้งย่านค่า (น่าเชื่อกว่า)", c: "border-emerald-500/40 bg-emerald-500/10 text-emerald-500" },
  spike: { text: "จุดแหลม — ดีเฉพาะจุดเดียว (น่าจะ overfit)", c: "border-rose-500/40 bg-rose-500/10 text-red-500" },
  edge: { text: "ค่าที่ดีที่สุดอยู่ขอบตาราง — ขยายช่วงแล้วดูใหม่", c: "border-amber-500/40 bg-amber-500/10 text-amber-500" },
  mixed: { text: "ผสม — ไม่ชัดว่าเป็นที่ราบหรือจุดแหลม", c: "border-amber-500/40 bg-amber-500/10 text-amber-500" },
  no_profit: { text: "ไม่มีชุดค่าที่ให้ผลบวกในเกณฑ์ที่เลือก", c: "border-rose-500/40 bg-rose-500/10 text-red-500" },
  no_metric: { text: "คำนวณ metric นี้ไม่ได้ (ช่วงสั้นกว่า 1 ปี?) ลองเลือกผลตอบแทนรวม", c: "border-amber-500/40 bg-amber-500/10 text-amber-500" },
}

function Heatmap({ r }: { r: Sweep }) {
  const ax = r.axes, ni = ax[0]?.values.length ?? 0, nj = ax[1]?.values.length ?? 1
  const metric = r.metric
  const get = (c: Cell) => c.metrics?.[metric as keyof MetricSet] ?? null
  const maxAbs = Math.max(1e-9, ...r.cells.map((c) => Math.abs(get(c) ?? 0)))
  const byKey = new Map(r.cells.map((c) => [`${c.i}:${c.j}`, c]))
  const bg = (v: number | null) => {
    if (v == null) return undefined
    const a = 0.12 + 0.5 * Math.min(1, Math.abs(v) / maxAbs)
    return v >= 0 ? `rgba(16,185,129,${a.toFixed(2)})` : `rgba(239,68,68,${a.toFixed(2)})`
  }
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-1 text-xs tabular-nums">
        <thead>
          <tr>
            <th className="px-1 text-left font-normal text-muted-foreground">{ax[1] ? `${short(ax[1].label)} ↓ / ${short(ax[0]?.label ?? "")} →` : short(ax[0]?.label ?? "")}</th>
            {ax[0]?.values.map((v, i) => <th key={i} className={`px-2 py-1 font-medium ${v === ax[0]?.current ? "text-primary" : ""}`}>{v}</th>)}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: nj }, (_, j) => (
            <tr key={j}>
              <th className={`px-2 text-right font-medium ${ax[1] && ax[1].values[j] === ax[1].current ? "text-primary" : ""}`}>{ax[1] ? ax[1].values[j] : ""}</th>
              {Array.from({ length: ni }, (_, i) => {
                const c = byKey.get(`${i}:${j}`)
                const v = c ? get(c) : null
                const best = r.best?.i === i && r.best?.j === j
                const base = r.base?.i === i && r.base?.j === j
                return (
                  <td key={i} title={c?.reason ?? (c ? `${c.trades ?? 0} ออเดอร์` : "")}
                    className={`min-w-[64px] rounded-md px-2 py-2 text-center ${best ? "ring-2 ring-primary" : ""}`} style={{ background: bg(v) }}>
                    <div className="font-medium">{fmt(metric, v)}</div>
                    <div className="text-[10px] text-muted-foreground">{base ? "● ค่าที่ใช้" : best ? "★ สูงสุด" : c?.trades != null ? `${c.trades} ออเดอร์` : ""}</div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SweepView({ r }: { r: Sweep }) {
  const s = r.summary, v = VERDICT[s.verdict]
  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {v && <span className={`rounded-md border px-2 py-1 ${v.c}`}>{v.text}</span>}
        <span className="text-muted-foreground">วัดด้วย {r.metric_label} · ลอง {r.trials} ชุด (ใช้ได้ {s.valid_cells})</span>
      </div>
      <Heatmap r={r} />
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Tile label="ค่าสูงสุด (เลือกจากทุกเซลล์)" value={fmt(r.metric, s.best_value)} />
        <Tile label="มัธยฐานทุกเซลล์" value={fmt(r.metric, s.median_value)} />
        <Tile label="เซลล์ที่ผลเป็นบวก" value={pct(s.frac_positive, 0)} />
        <Tile label="เพื่อนบ้านของค่าสูงสุด ÷ ค่าสูงสุด" value={s.neighbor_ratio == null ? "—" : pct(s.neighbor_ratio, 0)} />
        <Tile label="ชนะ Buy-and-Hold" value={pct(s.frac_beat_buy_hold, 0)} />
        <Tile label="ชนะ S&P 500" value={pct(s.frac_beat_benchmark, 0)} />
        <Tile label="Buy-and-Hold (ผลรวม)" value={pct(r.reference.buy_hold?.total_return)} c={cls(r.reference.buy_hold?.total_return)} />
        <Tile label="S&P 500 (ผลรวม)" value={pct(r.reference.benchmark?.total_return)} c={cls(r.reference.benchmark?.total_return)} />
      </div>
      <p className="text-xs text-muted-foreground">{r.note}</p>
      <Caveats items={r.caveats} />
    </div>
  )
}

// ------------------------------------------------------------------ Walk-forward
const SERIES: { key: "walk_forward" | "fixed_params" | "buy_hold" | "benchmark"; label: string; color: string; w: number }[] = [
  { key: "walk_forward", label: "Walk-forward (out-of-sample)", color: "#38bdf8", w: 2.4 },
  { key: "fixed_params", label: "พารามิเตอร์เดิมที่ใช้อยู่", color: "#f59e0b", w: 1.4 },
  { key: "buy_hold", label: "Buy-and-Hold", color: "#a78bfa", w: 1.4 },
  { key: "benchmark", label: "S&P 500", color: "#9ca3af", w: 1.4 },
]

function Curves({ c }: { c: WF["curves"] }) {
  const W = 800, H = 260, P = { l: 52, r: 12, t: 10, b: 24 }
  const g = useMemo(() => {
    const all = [0, ...SERIES.flatMap((s) => c[s.key])]
    const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1
    const n = Math.max(c.dates.length - 1, 1)
    const x = (i: number) => P.l + (i / n) * (W - P.l - P.r)
    const y = (v: number) => P.t + (1 - (v - lo) / span) * (H - P.t - P.b)
    const line = (a: number[]) => a.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")
    return {
      lines: SERIES.map((s) => ({ ...s, d: line(c[s.key]) })), y0: y(0),
      ticks: [0, 1, 2, 3, 4].map((k) => { const v = lo + (span * k) / 4; return { v, y: y(v) } }),
    }
  }, [c])
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full text-muted-foreground" role="img" aria-label="ผลสะสม out-of-sample เทียบ Buy-and-Hold และ S&P 500">
        {g.ticks.map((t) => (
          <g key={t.v}>
            <line x1={P.l} x2={W - P.r} y1={t.y} y2={t.y} stroke="currentColor" strokeOpacity="0.15" />
            <text x={P.l - 6} y={t.y + 3} textAnchor="end" fontSize="10" fill="currentColor">{(t.v * 100).toFixed(0)}%</text>
          </g>
        ))}
        <line x1={P.l} x2={W - P.r} y1={g.y0} y2={g.y0} stroke="currentColor" strokeOpacity="0.5" strokeDasharray="4 3" />
        {g.lines.map((l) => <path key={l.key} d={l.d} fill="none" stroke={l.color} strokeWidth={l.w} />)}
        <text x={P.l} y={H - 6} fontSize="10" fill="currentColor">{c.dates[0]}</text>
        <text x={W - P.r} y={H - 6} textAnchor="end" fontSize="10" fill="currentColor">{c.dates[c.dates.length - 1]}</text>
      </svg>
      <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted-foreground">
        {SERIES.map((s) => <span key={s.key}><i className="mr-1 inline-block h-0.5 w-4 align-middle" style={{ background: s.color }} />{s.label}</span>)}
      </div>
    </div>
  )
}

function WFView({ r }: { r: WF }) {
  const s = r.summary
  const label = (id: string) => short(r.axes.find((a) => a.id === id)?.label ?? id)
  return (
    <div className="mt-4 space-y-4">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {SERIES.map((x) => (
          <div key={x.key} className="rounded-lg border bg-muted/20 px-3 py-2.5">
            <div className="text-[11px] text-muted-foreground"><i className="mr-1 inline-block h-0.5 w-3 align-middle" style={{ background: x.color }} />{x.label}</div>
            <div className={`mt-0.5 text-lg font-semibold tabular-nums ${cls(r.stitched[x.key].total_return)}`}>{pct(r.stitched[x.key].total_return)}</div>
            <div className="text-[11px] text-muted-foreground tabular-nums">CAGR {pct(r.stitched[x.key].cagr)} · DD {pct(r.stitched[x.key].max_drawdown)}</div>
          </div>
        ))}
      </div>
      <Curves c={r.curves} />
      <div className="text-xs text-muted-foreground">
        ช่วงฝึกเฉลี่ย ({r.metric_label}) {fmt(r.metric, s.mean_is)} → ช่วงทดสอบเฉลี่ย {fmt(r.metric, s.mean_oos)}
        {s.oos_vs_is_ratio != null && <> · เหลือ {pct(s.oos_vs_is_ratio, 0)} ของที่เห็นตอนฝึก</>}
        {" · "}ช่วงทดสอบที่บวก {s.folds_positive}/{s.folds_used} · ชนะ Buy-and-Hold {s.folds_beat_buy_hold}/{s.folds_used} · ชนะพารามิเตอร์เดิม {s.folds_beat_fixed}/{s.folds_used}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-xs tabular-nums">
          <thead className="text-left text-muted-foreground">
            <tr>
              <th className="py-1 font-normal">fold</th><th className="font-normal">ช่วงฝึก → ช่วงทดสอบ</th><th className="font-normal">ค่าที่เลือก (จากช่วงฝึก)</th>
              <th className="text-right font-normal">ช่วงฝึก</th><th className="text-right font-normal">ช่วงทดสอบ</th>
              <th className="text-right font-normal">ผลรวมช่วงทดสอบ</th><th className="text-right font-normal">พารามิเตอร์เดิม</th><th className="text-right font-normal">Buy-and-Hold</th>
            </tr>
          </thead>
          <tbody>
            {r.folds.map((f) => (
              <tr key={f.fold} className="border-t border-border">
                <td className="py-1">{f.fold}</td>
                <td>{f.train[0]}…{f.train[1]} → {f.test[0]}…{f.test[1]}</td>
                {f.chosen ? (
                  <>
                    <td>{Object.entries(f.chosen).map(([id, v]) => `${label(id)}=${v}`).join(", ")}</td>
                    <td className="text-right">{fmt(r.metric, f.is_value)}</td>
                    <td className="text-right">{fmt(r.metric, f.oos_value)}</td>
                    <td className={`text-right ${cls(f.oos?.total_return)}`}>{pct(f.oos?.total_return)}</td>
                    <td className={`text-right ${cls(f.fixed_oos?.total_return)}`}>{pct(f.fixed_oos?.total_return)}</td>
                    <td className={`text-right ${cls(f.buy_hold_oos?.total_return)}`}>{pct(f.buy_hold_oos?.total_return)}</td>
                  </>
                ) : <td colSpan={6} className="text-amber-500">ข้าม: {f.skipped}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-xs text-muted-foreground">
        {Object.values(r.param_stability).map((p) => (
          <div key={p.label}>{short(p.label)}: เลือก {p.chosen.join(" → ")} (เปลี่ยน {p.changes} ครั้ง จาก {Math.max(p.chosen.length - 1, 0)}) {p.changes >= 2 && <span className="text-amber-500">— ค่าที่ดีที่สุดไม่นิ่งระหว่างช่วง</span>}</div>
        ))}
        <div className="mt-1">ลองทั้งหมด {s.trials} ชุด ({s.folds} fold, {r.anchored ? "ช่วงฝึกขยายต่อเนื่องจากวันเริ่ม" : "ช่วงฝึกเลื่อนทีละบล็อก"})</div>
      </div>
      <Caveats items={r.caveats} />
    </div>
  )
}

// ------------------------------------------------------------------ เทียบกับสุ่ม
function Hist({ h, actual, metric }: { h: BL["histogram"]; actual: number | null; metric: string }) {
  const W = 800, H = 200, P = { l: 12, r: 12, t: 12, b: 28 }
  const lo = h.edges[0] ?? 0, hi = h.edges[h.edges.length - 1] ?? 1, span = hi - lo || 1
  const mx = Math.max(1, ...h.counts)
  const x = (v: number) => P.l + ((v - lo) / span) * (W - P.l - P.r)
  const bw = (W - P.l - P.r) / h.counts.length
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full text-muted-foreground" role="img" aria-label="การแจกแจงผลของกลยุทธ์สุ่มจังหวะ เทียบกับผลจริง">
      {h.counts.map((n, i) => {
        const hh = (n / mx) * (H - P.t - P.b)
        return <rect key={i} x={P.l + i * bw + 1} y={H - P.b - hh} width={Math.max(bw - 2, 1)} height={hh} fill="currentColor" fillOpacity="0.35" />
      })}
      <line x1={P.l} x2={W - P.r} y1={H - P.b} y2={H - P.b} stroke="currentColor" strokeOpacity="0.5" />
      {actual != null && (
        <>
          <line x1={x(actual)} x2={x(actual)} y1={P.t} y2={H - P.b} stroke="#38bdf8" strokeWidth="2.4" />
          <text x={Math.min(Math.max(x(actual), 60), W - 60)} y={P.t + 8} textAnchor="middle" fontSize="11" fill="#38bdf8">ผลจริง {fmt(metric, actual)}</text>
        </>
      )}
      <text x={P.l} y={H - 8} fontSize="10" fill="currentColor">{fmt(metric, lo)}</text>
      <text x={W - P.r} y={H - 8} textAnchor="end" fontSize="10" fill="currentColor">{fmt(metric, hi)}</text>
    </svg>
  )
}

function BaselineView({ r }: { r: BL }) {
  const rows: { k: keyof BL["stats"]; label: string; ratio: boolean }[] = [
    { k: "total_return", label: "ผลตอบแทนรวม", ratio: false }, { k: "cagr", label: "CAGR", ratio: false },
    { k: "max_drawdown", label: "Max Drawdown", ratio: false }, { k: "calmar", label: "Calmar", ratio: true },
  ]
  const f = (ratio: boolean, v: number | null | undefined) => (v == null ? "—" : ratio ? v.toFixed(2) : pct(v))
  const head = r.stats[r.metric as keyof BL["stats"]]
  return (
    <div className="mt-4 space-y-4">
      <div className="space-y-1">{r.reading.map((t) => <p key={t} className="text-sm">{t}</p>)}</div>
      <Hist h={r.histogram} actual={head?.actual ?? null} metric={r.metric} />
      <p className="text-xs text-muted-foreground">แท่ง = การแจกแจงของพอร์ตที่สุ่มจังหวะเข้า-ออก {r.sims.toLocaleString()} ครั้ง (จำนวนรอบ {r.trips} และระยะถือเท่าของจริง) · เส้นฟ้า = ผลจริง · seed {r.seed}</p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs tabular-nums">
          <thead className="text-left text-muted-foreground">
            <tr><th className="py-1 font-normal">metric</th><th className="text-right font-normal">ผลจริง</th><th className="text-right font-normal">สุ่ม (มัธยฐาน)</th>
              <th className="text-right font-normal">สุ่ม 5%–95%</th><th className="text-right font-normal">ดีกว่าสุ่ม</th><th className="text-right font-normal">p (สุ่มดีเท่ากัน/กว่า)</th>
              {r.trials > 1 && <th className="text-right font-normal">p ปรับ {r.trials} ชุด</th>}</tr>
          </thead>
          <tbody>
            {rows.map((x) => {
              const s = r.stats[x.k]
              return (
                <tr key={x.k} className={`border-t border-border ${x.k === r.metric ? "bg-primary/5 font-medium" : ""}`}>
                  <td className="py-1">{x.label}</td>
                  <td className="text-right">{f(x.ratio, s.actual)}</td>
                  <td className="text-right">{f(x.ratio, s.p50)}</td>
                  <td className="text-right">{f(x.ratio, s.p5)} ถึง {f(x.ratio, s.p95)}</td>
                  <td className="text-right">{s.beats_fraction == null ? "—" : pct(s.beats_fraction, 0)}</td>
                  <td className="text-right">{s.p_as_good == null ? "—" : pct(s.p_as_good, 1)}</td>
                  {r.trials > 1 && <td className="text-right">{s.p_bonferroni == null ? "—" : pct(s.p_bonferroni, 1)}</td>}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        ความคลาดเคลื่อนของแบบจำลอง: ใช้รอบจริงซ้ำได้ผลรวม {pct(r.replication.model.total_return)} เทียบผลจริง {pct(r.replication.actual.total_return)}
        ({r.replication.total_return_diff >= 0 ? "+" : ""}{(r.replication.total_return_diff * 100).toFixed(1)} จุด) · อยู่ในเวลา {pct(r.time_in_market, 0)} ของวัน
      </p>
      {r.notes.length > 0 && <Caveats items={r.notes} />}
      {r.warnings.length > 0 && <Caveats items={r.warnings.map((w) => w.message)} />}
      <Caveats items={r.caveats} />
    </div>
  )
}

// ------------------------------------------------------------------ หน้าหลัก
type Tab = "sweep" | "wf" | "baseline"
const TABS: { k: Tab; label: string }[] = [
  { k: "sweep", label: "Sweep (heatmap)" }, { k: "wf", label: "Walk-forward" }, { k: "baseline", label: "เทียบกับสุ่ม" },
]

export default function SearchPanel({ runId, apiBase, getToken }: Props) {
  const [meta, setMeta] = useState<TunMeta | null>(null)
  const [metaErr, setMetaErr] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("sweep")
  const [rows, setRows] = useState<Row[]>([])
  const [metric, setMetric] = useState("calmar")
  const [folds, setFolds] = useState("4")
  const [anchored, setAnchored] = useState(true)
  const [sims, setSims] = useState("1000")
  const [trials, setTrials] = useState("1")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [sw, setSw] = useState<Sweep | null>(null)
  const [wf, setWf] = useState<WF | null>(null)
  const [bl, setBl] = useState<BL | null>(null)

  // getToken อาจเป็นฟังก์ชันใหม่ทุกครั้งที่หน้าแม่ render — เก็บใน ref กันไม่ให้ effect รันซ้ำและล้างผลที่แสดงอยู่
  const tokenRef = useRef(getToken)
  tokenRef.current = getToken

  useEffect(() => {
    let alive = true
    setMeta(null); setMetaErr(null); setSw(null); setWf(null); setBl(null)
    call<TunMeta>(apiBase, tokenRef.current(), "GET", `/runs/${encodeURIComponent(runId)}/tunables`)
      .then((m) => {
        if (!alive) return
        setMeta(m)
        const t = m.tunables[0]
        if (t) setRows([{ id: t.id, min: String(t.suggest?.min ?? ""), max: String(t.suggest?.max ?? ""), steps: String(t.suggest?.steps ?? 5) }])
      })
      .catch((e: unknown) => { if (alive) setMetaErr(errText(e)) })
    return () => { alive = false }
  }, [runId, apiBase])

  const run = async <T,>(path: string, body: unknown, done: (r: T) => void) => {
    setBusy(true); setErr(null)
    try {
      done(await call<T>(apiBase, tokenRef.current(), "POST", `/runs/${encodeURIComponent(runId)}${path}`, body))
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const hasParams = !!meta && meta.tunables.length > 0
  const metricOpts = meta?.metrics ?? []
  return (
    <div className={card}>
      <h3 className="text-sm font-medium">ค้นหา edge อย่างไม่หลอกตัวเอง</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        การปรับพารามิเตอร์ให้ผลย้อนหลังดีที่สุด <b>ไม่ใช่การหา edge</b> — ลองหลายชุดย่อมมีชุดที่ดูดีโดยบังเอิญ เครื่องมือชุดนี้ใช้ตรวจว่าผลเกาะอยู่ที่จุดเดียวหรือไม่ (Sweep),
        ทดสอบกับช่วงเวลาที่ไม่เคยเห็นจริง ๆ (Walk-forward) และเทียบกับการสุ่มจังหวะ (เทียบกับสุ่ม)
      </p>
      {metaErr && <ErrBox msg={metaErr} />}
      {meta && !hasParams && <p className="mt-3 text-xs text-amber-500">รันนี้ไม่มีกลยุทธ์ที่มีพารามิเตอร์ให้ค้นหา (ต้องเป็นรันแบบกลยุทธ์)</p>}
      {meta && hasParams && (
        <>
          <div className="mt-3 inline-flex overflow-hidden rounded-md border text-xs">
            {TABS.map((t) => (
              <button key={t.k} type="button" onClick={() => { setTab(t.k); setErr(null) }} className={`px-3 py-1.5 ${tab === t.k ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{t.label}</button>
            ))}
          </div>

          {tab !== "baseline" && (
            <div className="mt-3 space-y-3">
              <ParamPicker meta={meta} rows={rows} setRows={setRows} />
              <div className="flex flex-wrap items-end gap-3 text-xs text-muted-foreground">
                <label>วัดผลด้วย
                  <select className={`${sel} ml-2`} value={metric} onChange={(e) => setMetric(e.target.value)}>
                    {metricOpts.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
                  </select>
                </label>
                {tab === "wf" && (
                  <>
                    <label>จำนวน fold<input className={`${num} ml-2 w-12`} inputMode="numeric" value={folds} onChange={(e) => setFolds(e.target.value)} /></label>
                    <label className="flex items-center gap-1.5"><input type="checkbox" checked={anchored} onChange={(e) => setAnchored(e.target.checked)} />ช่วงฝึกขยายต่อเนื่องจากวันเริ่ม</label>
                  </>
                )}
                <button type="button" disabled={busy || rows.length === 0} className={btn}
                  onClick={() => void (tab === "sweep"
                    ? run<Sweep>("/sweep", { params: toParams(rows), metric }, (r) => { setSw(r); setTrials(String(r.trials)) })
                    : run<WF>("/walkforward", { params: toParams(rows), metric, folds: Number(folds), anchored }, (r) => { setWf(r); setTrials(String(r.summary.trials)) }))}>
                  {busy ? "กำลังคำนวณ…" : tab === "sweep" ? "รัน Sweep" : "รัน Walk-forward"}
                </button>
                <span>ใช้เวลาประมาณครึ่งนาที หรือมากกว่าถ้าลองหลายชุด · สูงสุด {meta.limits.max_cells} เซลล์</span>
              </div>
            </div>
          )}

          {tab === "baseline" && (
            <div className="mt-3 flex flex-wrap items-end gap-3 text-xs text-muted-foreground">
              <label>วัดผลด้วย
                <select className={`${sel} ml-2`} value={metric === "sortino" ? "calmar" : metric} onChange={(e) => setMetric(e.target.value)}>
                  {metricOpts.filter((m) => m.key !== "sortino").map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
              </label>
              <label>จำนวนครั้งที่สุ่ม<input className={`${num} ml-2`} inputMode="numeric" value={sims} onChange={(e) => setSims(e.target.value)} /></label>
              <label title="จำนวนชุดกฎ/พารามิเตอร์ที่เคยลองก่อนได้กฎนี้ (รวมที่ลองเองนอกระบบ) ใช้ปรับค่า p">ลองมาแล้วกี่ชุด<input className={`${num} ml-2 w-16`} inputMode="numeric" value={trials} onChange={(e) => setTrials(e.target.value)} /></label>
              <button type="button" disabled={busy} className={btn}
                onClick={() => void run<BL>("/randombaseline", { metric: metric === "sortino" ? "calmar" : metric, sims: Number(sims), trials: Number(trials) }, setBl)}>
                {busy ? "กำลังสุ่ม…" : "เทียบกับการสุ่ม"}
              </button>
            </div>
          )}
          <ErrBox msg={err} />
          {tab === "sweep" && sw && <SweepView r={sw} />}
          {tab === "wf" && wf && <WFView r={wf} />}
          {tab === "baseline" && bl && <BaselineView r={bl} />}
        </>
      )}
    </div>
  )
}
