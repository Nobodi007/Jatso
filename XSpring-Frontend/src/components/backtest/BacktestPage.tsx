import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ApiError, createRun, deleteRun, fetchMeta, getRun, listRuns } from "./api"
import type { Brief, Meta, Metric, Result, Run, Spec, RebalanceFreq, RebalanceMode } from "./types"
import { DonutChart } from "../ui/donut-chart"
import type { DonutChartSegment } from "../ui/donut-chart"
import TickerInput from "./TickerInput"
import type { TickerHit } from "./TickerInput"

// หน้า Backtest Lab (หุ้นสหรัฐ) — คอมโพเนนต์ใหม่ทั้งหมด ไม่ import/ไม่แตะโค้ด Backtest เดิม
type Props = { getToken: () => string | null; apiBase: string }
type Row = { symbol: string; weightPct: string }

const card = "rounded-xl border bg-card p-5"
const input = "w-full rounded-lg border bg-background px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary"
const numInput = "w-24 shrink-0 rounded-lg border bg-background px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary"
const cashLabel = "min-w-0 flex-1 rounded-lg border bg-background px-3 py-2.5 text-sm text-muted-foreground"
const label = "mb-2 block text-xs text-muted-foreground"

const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`)
const usd = (v: number) => v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })
const signCls = (v: number | null | undefined) => (v == null ? "text-muted-foreground" : v >= 0 ? "text-emerald-500" : "text-red-500")

const ymd = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`

function today(): string {
  return ymd(new Date())
}

const dateInput = `${input} [color-scheme:dark] cursor-pointer`
const chip = "rounded-md border px-2.5 py-1 text-xs hover:bg-accent"
const openPicker = (e: React.MouseEvent<HTMLInputElement>) => {
  try { e.currentTarget.showPicker() } catch { /* เบราว์เซอร์ที่ไม่รองรับ ใช้พิมพ์ตามปกติ */ }
}
const colorOf = (i: number) => `hsl(${(i * 137.508 + 210) % 360} 70% 55%)`
const CASH_COLOR = "hsl(0 0% 55%)"

// ปรับน้ำหนักของแถว idx ให้รวมเป็น target พอดี (คงสัดส่วนเดิม ถ้ารวมเดิมเป็น 0 จะแบ่งเท่ากัน)
function scaleRows(rs: Row[], idx: number[], target: number): Row[] {
  if (idx.length === 0) return rs
  const cur = idx.reduce((a, i) => a + wnum(rs[i].weightPct), 0)
  const next = idx.map((i) => r2(cur > 0 ? (wnum(rs[i].weightPct) / cur) * target : target / idx.length))
  const diff = r2(target - next.reduce((a, b) => a + b, 0))
  const big = next.indexOf(Math.max(...next))
  next[big] = r2(next[big] + diff)
  const out = rs.slice()
  idx.forEach((i, k) => {
    out[i] = { ...out[i], weightPct: String(next[k]) }
  })
  return out
}

function MetricCell({ m, kind }: { m: Metric; kind: "pct" | "ratio" }) {
  if (m.value == null) {
    return (
      <span className="text-muted-foreground" title={m.reason ?? m.status}>
        {m.status === "insufficient_data" ? "ข้อมูลไม่พอ" : "ไม่มีค่า"}
      </span>
    )
  }
  const text = kind === "pct" ? pct(m.value) : m.value.toFixed(2)
  return (
    <span className={kind === "pct" ? signCls(m.value) : "text-foreground"} title={m.formula}>
      {text}
      {m.status === "limited_sample" && <span className="ml-1 text-[10px] text-amber-400">ตัวอย่างน้อย</span>}
    </span>
  )
}

function Comparison({ r }: { r: Result }) {
  const cols: { key: keyof Brief; name: string; kind: "pct" | "ratio" }[] = [
    { key: "total_return", name: "ผลตอบแทนรวม", kind: "pct" },
    { key: "cagr", name: "CAGR", kind: "pct" },
    { key: "volatility", name: "ความผันผวน/ปี", kind: "pct" },
    { key: "max_drawdown", name: "Max Drawdown", kind: "pct" },
    { key: "sharpe", name: "Sharpe", kind: "ratio" },
    { key: "sortino", name: "Sortino", kind: "ratio" },
    { key: "calmar", name: "Calmar", kind: "ratio" },
  ]
  const rows: { name: string; b: Brief }[] = [
    { name: "พอร์ตที่ทดสอบ", b: r.comparison.portfolio },
    { name: "Buy-and-Hold (หุ้นชุดเดียวกัน)", b: r.comparison.buy_hold },
    { name: "S&P 500 Price Index", b: r.comparison.benchmark },
  ]
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="py-1 pr-3 font-normal" />
            {cols.map((c) => (
              <th key={c.key} className="px-2 py-1 text-right font-normal">
                {c.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className="border-t border-border">
              <td className="py-1.5 pr-3 text-muted-foreground">{row.name}</td>
              {cols.map((c) => (
                <td key={c.key} className="px-2 py-1.5 text-right tabular-nums">
                  <MetricCell m={row.b[c.key]} kind={c.kind} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EquityChart({ series }: { series: Result["series"] }) {
  const W = 800
  const H = 260
  const P = { l: 48, r: 12, t: 10, b: 22 }
  const { paths, y0, ticks, first, last } = useMemo(() => {
    const keys = ["portfolio", "buy_hold", "benchmark"] as const
    let lo = 0
    let hi = 0
    for (const s of series) for (const k of keys) {
      lo = Math.min(lo, s[k])
      hi = Math.max(hi, s[k])
    }
    const span = hi - lo || 1
    const x = (i: number) => P.l + (i / Math.max(series.length - 1, 1)) * (W - P.l - P.r)
    const y = (v: number) => P.t + (1 - (v - lo) / span) * (H - P.t - P.b)
    const mk = (k: (typeof keys)[number]) => series.map((s, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(s[k]).toFixed(1)}`).join(" ")
    const t = [0, 1, 2, 3, 4].map((n) => lo + (span * n) / 4)
    return {
      paths: { portfolio: mk("portfolio"), buy_hold: mk("buy_hold"), benchmark: mk("benchmark") },
      y0: y(0),
      ticks: t.map((v) => ({ v, y: y(v) })),
      first: series[0]?.date ?? "",
      last: series[series.length - 1]?.date ?? "",
    }
  }, [series])
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full text-muted-foreground" role="img" aria-label="ผลตอบแทนสะสม พอร์ต เทียบ Buy-and-Hold และ S&P 500">
        {ticks.map((t) => (
          <g key={t.v}>
            <line x1={P.l} x2={W - P.r} y1={t.y} y2={t.y} stroke="currentColor" strokeOpacity="0.15" />
            <text x={P.l - 6} y={t.y + 3} textAnchor="end" fontSize="10" fill="currentColor">
              {(t.v * 100).toFixed(0)}%
            </text>
          </g>
        ))}
        <line x1={P.l} x2={W - P.r} y1={y0} y2={y0} stroke="currentColor" strokeOpacity="0.5" strokeDasharray="4 3" />
        <path d={paths.benchmark} fill="none" stroke="#a1a1aa" strokeWidth="1.5" strokeDasharray="5 3" />
        <path d={paths.buy_hold} fill="none" stroke="#f59e0b" strokeWidth="1.5" />
        <path d={paths.portfolio} fill="none" stroke="#38bdf8" strokeWidth="2" />
        <text x={P.l} y={H - 6} fontSize="10" fill="currentColor">{first}</text>
        <text x={W - P.r} y={H - 6} textAnchor="end" fontSize="10" fill="currentColor">{last}</text>
      </svg>
      <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span><i className="mr-1 inline-block h-0.5 w-4 bg-sky-400 align-middle" />พอร์ต</span>
        <span><i className="mr-1 inline-block h-0.5 w-4 bg-amber-500 align-middle" />Buy-and-Hold</span>
        <span><i className="mr-1 inline-block h-0.5 w-4 bg-zinc-400 align-middle" />S&P 500 (Price)</span>
      </div>
    </div>
  )
}

function Results({ run }: { run: Run }) {
  const r = run.result
  const [showTrades, setShowTrades] = useState(false)
  if (!r) return null
  const s = r.stats
  const sev: Record<string, string> = {
    high: "border-rose-500/40 bg-rose-500/10 text-red-500",
    medium: "border-amber-500/40 bg-amber-500/10 text-amber-500",
    low: "border-border bg-muted/50 text-muted-foreground",
    info: "border-border bg-muted/50 text-muted-foreground",
  }
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-500">
        ผลจำลองย้อนหลัง (Hypothetical Backtest) ไม่ใช่ผลงานจริงและไม่ใช่การพยากรณ์ · Price Return ไม่รวมปันผล ·
        ช่วง {r.period.first_trade_date} → {r.period.last_date} ({r.period.trading_days} วันทำการ) · engine {r.engine_version}
      </div>
      <div className="space-y-1.5">
        {r.warnings.map((w, i) => (
          <div key={`${w.code}-${i}`} className={`rounded-lg border px-3 py-1.5 text-xs ${sev[w.severity] ?? sev.info}`}>
            {w.message}
          </div>
        ))}
      </div>

      <div className={card}>
        <h3 className="mb-2 text-sm font-medium text-foreground">เปรียบเทียบ</h3>
        <Comparison r={r} />
        <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div><div className="text-xs text-muted-foreground">มูลค่าสุดท้าย</div><div className="tabular-nums">{usd(s.final_value)}</div></div>
          <div><div className="text-xs text-muted-foreground">Buy-and-Hold</div><div className="tabular-nums">{usd(s.buy_hold_final_value)}</div></div>
          <div><div className="text-xs text-muted-foreground">ต้นทุนรวม</div><div className="tabular-nums">{usd(s.total_cost)} ({pct(s.total_cost_pct_of_initial)})</div></div>
          <div><div className="text-xs text-muted-foreground">Turnover/ปี (ฝั่งเดียว)</div><div className="tabular-nums">{pct(s.turnover_annual_one_way, 1)}</div></div>
          <div><div className="text-xs text-muted-foreground">จำนวนครั้ง Rebalance</div><div>{s.rebalance_count}</div></div>
          <div><div className="text-xs text-muted-foreground">จำนวนคำสั่งหลังซื้อเริ่มต้น</div><div>{s.trade_count}</div></div>
          <div><div className="text-xs text-muted-foreground">เวลาที่ลงทุนในหุ้น</div><div className="tabular-nums">{pct(s.time_in_market, 1)}</div></div>
        </div>
      </div>

      <div className={card}>
        <h3 className="mb-2 text-sm font-medium text-foreground">ผลตอบแทนสะสม</h3>
        <EquityChart series={r.series} />
      </div>

      <div className={card}>
        <h3 className="mb-2 text-sm font-medium text-foreground">วันที่พอร์ตบวก/ลบมากที่สุด เทียบ S&P 500 ในวันเดียวกัน</h3>
        <div className="grid gap-4 md:grid-cols-2">
          {([["บวกสุด", r.extremes.days.best], ["ลบสุด", r.extremes.days.worst]] as const).map(([title, rows]) => (
            <table key={title} className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1 font-normal">{title}</th>
                  <th className="text-right font-normal">พอร์ต</th>
                  <th className="text-right font-normal">S&P 500</th>
                  <th className="text-right font-normal">ส่วนต่าง</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.date} className="border-t border-border tabular-nums">
                    <td className="py-1 text-muted-foreground">{d.date}</td>
                    <td className={`text-right ${signCls(d.portfolio)}`}>{pct(d.portfolio)}</td>
                    <td className={`text-right ${signCls(d.benchmark)}`}>{pct(d.benchmark)}</td>
                    <td className={`text-right ${signCls(d.active)}`}>{pct(d.active)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          สัปดาห์ที่ดี/แย่สุด: {r.extremes.weeks.best.period} ({pct(r.extremes.weeks.best.portfolio)}) / {r.extremes.weeks.worst.period} ({pct(r.extremes.weeks.worst.portfolio)}) ·
          เดือนที่ดี/แย่สุด: {r.extremes.months.best.period} ({pct(r.extremes.months.best.portfolio)}) / {r.extremes.months.worst.period} ({pct(r.extremes.months.worst.portfolio)}) ·
          งวดแรก/ท้ายอาจไม่เต็ม
        </p>
      </div>

      <div className={card}>
        <h3 className="mb-2 text-sm font-medium text-foreground">ผลรายปีปฏิทิน</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1 font-normal">ปี</th>
              <th className="text-right font-normal">พอร์ต</th>
              <th className="text-right font-normal">Buy-and-Hold</th>
              <th className="text-right font-normal">S&P 500</th>
              <th className="text-right font-normal">วัน</th>
            </tr>
          </thead>
          <tbody>
            {r.calendar_years.map((y) => (
              <tr key={y.year} className="border-t border-border tabular-nums">
                <td className="py-1 text-muted-foreground">{y.year}</td>
                <td className={`text-right ${signCls(y.portfolio)}`}>{pct(y.portfolio)}</td>
                <td className={`text-right ${signCls(y.buy_hold)}`}>{pct(y.buy_hold)}</td>
                <td className={`text-right ${signCls(y.benchmark)}`}>{pct(y.benchmark)}</td>
                <td className="text-right text-muted-foreground">{y.days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className={card}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-foreground">รายการซื้อขาย ({r.trades.length}{r.trades_truncated ? "+" : ""})</h3>
          <button type="button" className="text-xs text-primary hover:underline" onClick={() => setShowTrades((v) => !v)}>
            {showTrades ? "ซ่อน" : "แสดง"}
          </button>
        </div>
        {showTrades && (
          <div className="mt-2 max-h-80 overflow-auto">
            <table className="w-full min-w-[560px] text-xs tabular-nums">
              <thead className="sticky top-0 bg-zinc-900 text-left text-muted-foreground">
                <tr><th className="py-1 font-normal">วันที่</th><th className="font-normal">หุ้น</th><th className="font-normal">ด้าน</th>
                  <th className="text-right font-normal">จำนวน</th><th className="text-right font-normal">ราคา</th>
                  <th className="text-right font-normal">มูลค่า</th><th className="text-right font-normal">ค่าคอม</th><th className="pl-3 font-normal">เหตุผล</th></tr>
              </thead>
              <tbody>
                {r.trades.map((t, i) => (
                  <tr key={`${t.date}-${t.symbol}-${i}`} className="border-t border-border">
                    <td className="py-1">{t.date}</td><td>{t.symbol}</td>
                    <td className={t.side === "buy" ? "text-emerald-500" : "text-red-500"}>{t.side === "buy" ? "ซื้อ" : "ขาย"}</td>
                    <td className="text-right">{t.shares.toFixed(4)}</td><td className="text-right">{t.price.toFixed(2)}</td>
                    <td className="text-right">{t.notional.toFixed(0)}</td><td className="text-right">{t.commission.toFixed(2)}</td>
                    <td className="pl-3 text-muted-foreground">{t.reason === "initial" ? "ซื้อเริ่มต้น" : "ปรับสัดส่วน"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className={card}>
        <h3 className="mb-2 text-sm font-medium text-foreground">แหล่งข้อมูลที่ใช้</h3>
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          {r.data_snapshot.map((d) => (
            <li key={d.symbol}>
              {d.symbol} · {d.source} · ข้อมูล {d.first_date} → {d.last_date} · ดึงเมื่อ {d.fetched_at.slice(0, 16).replace("T", " ")} UTC
              {d.stale ? " · ใช้ cache เก่า" : ""}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default function BacktestPage({ getToken, apiBase }: Props) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [rows, setRows] = useState<Row[]>([{ symbol: "AAPL", weightPct: "40" }, { symbol: "MSFT", weightPct: "30" }, { symbol: "NVDA", weightPct: "30" }])
  const [start, setStart] = useState("2016-01-04")
  const [end, setEnd] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 1)
    return ymd(d)
  })
  const [capital, setCapital] = useState("100000")
  const [mode, setMode] = useState<RebalanceMode>("none")
  const [freq, setFreq] = useState<RebalanceFreq>("quarterly")
  const [thr, setThr] = useState("5")
  const [comm, setComm] = useState("0")
  const [slip, setSlip] = useState("5")
  const [rf, setRf] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [history, setHistory] = useState<Run[]>([])
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      if (timer.current) clearTimeout(timer.current)
    }
  }, [])

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : "เกิดข้อผิดพลาดที่ไม่คาดคิด")
  }, [])

  const refreshHistory = useCallback(async () => {
    try {
      setHistory((await listRuns(apiBase, getToken())).runs)
    } catch {
      /* ประวัติโหลดไม่ได้ไม่ใช่เรื่องร้ายแรง */
    }
  }, [apiBase, getToken])

  useEffect(() => {
    fetchMeta(apiBase, getToken()).then((m) => {
      if (!alive.current) return
      setMeta(m)
      setComm(String(m.defaults.commission_bps))
      setSlip(String(m.defaults.slippage_bps))
    }).catch(fail)
    void refreshHistory()
  }, [apiBase, getToken, fail, refreshHistory])

  const poll = useCallback((id: string, tries = 0) => {
    timer.current = setTimeout(async () => {
      try {
        const r = await getRun(apiBase, getToken(), id)
        if (!alive.current) return
        setRun(r)
        if ((r.status === "queued" || r.status === "running") && tries < 120) {
          poll(id, tries + 1)
        } else {
          setBusy(false)
          void refreshHistory()
        }
      } catch (e) {
        if (alive.current) {
          fail(e)
          setBusy(false)
        }
      }
    }, 1500)
  }, [apiBase, getToken, fail, refreshHistory])

  const totalPct = rows.reduce((a, r) => a + (Number(r.weightPct) || 0), 0)
  const cashPct = Math.max(0, r2(100 - totalPct))
  const [cashDraft, setCashDraft] = useState<string | null>(null)
  const [hoverLabel, setHoverLabel] = useState<string | null>(null)

  const donutData: DonutChartSegment[] = [
    ...rows
      .map((r, i) => ({ label: r.symbol.trim() || `#${i + 1}`, value: wnum(r.weightPct), color: colorOf(i) }))
      .filter((s) => s.value > 0),
    ...(cashPct > 0 ? [{ label: "เงินสด", value: cashPct, color: CASH_COLOR }] : []),
  ]
  const hoverSeg = donutData.find((s) => s.label === hoverLabel)

  // ⚠️ ต้องแก้ให้ตรงกับ endpoint ที่ช่องค้นหาหุ้นด้านบนใช้จริง (ดูหมายเหตุด้านล่าง)
  const searchTickers = useCallback(async (q: string): Promise<TickerHit[]> => {
    const res = await fetch(`${apiBase}/api/stocks/search?q=${encodeURIComponent(q)}`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    })
    if (!res.ok) return []
    const data = await res.json()
    const list: any[] = Array.isArray(data) ? data : data.results ?? data.items ?? []
    return list
      .map((x) => ({ symbol: String(x.symbol ?? x.ticker ?? ""), name: String(x.name ?? x.company ?? x.title ?? "") }))
      .filter((x) => x.symbol)
  }, [apiBase, getToken])

  const buildSpec = (): Spec | string => {
    const positions = rows.filter((r) => r.symbol.trim() !== "").map((r) => ({ symbol: r.symbol.trim().toUpperCase(), weight: Number(r.weightPct) / 100 }))
    if (positions.length === 0) return "ใส่หุ้นอย่างน้อย 1 ตัว"
    if (!start || !end) return "เลือกวันเริ่มต้นและวันสิ้นสุด"
    if (start >= end) return "วันเริ่มต้นต้องมาก่อนวันสิ้นสุด"
    if (positions.some((p) => !Number.isFinite(p.weight) || p.weight <= 0)) return "น้ำหนักของทุกตัวต้องมากกว่า 0"
    if (totalPct > 100.0001) return `น้ำหนักรวม ${totalPct.toFixed(2)}% เกิน 100%`
    const spec: Spec = {
      version: 1, start, end, initial_capital: Number(capital), positions,
      rebalance: mode === "none" ? { mode } : {
        mode,
        ...(mode === "calendar" || mode === "hybrid" ? { frequency: freq } : {}),
        ...(mode === "threshold" || mode === "hybrid" ? { threshold_pct: Number(thr) } : {}),
      },
      costs: { commission_bps: Number(comm), slippage_bps: Number(slip) },
      risk_free_annual: rf.trim() === "" ? null : Number(rf) / 100,
    }
    return spec
  }

  const submit = async () => {
    setError(null)
    const spec = buildSpec()
    if (typeof spec === "string") return setError(spec)
    setBusy(true)
    setRun(null)
    try {
      const { id } = await createRun(apiBase, getToken(), spec)
      poll(id)
    } catch (e) {
      fail(e)
      setBusy(false)
    }
  }

  const setRow = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const maxSymbols = meta?.limits.max_symbols ?? 30
    // ออกจากช่อง/กด Enter แล้วปรับให้รวมไม่เกิน 100% (ส่วนที่เกินจะถูกหักจากตัวอื่นตามสัดส่วน)
  const balanceFrom = (i: number) =>
    setRows((rs) => {
      if (!rs[i]) return rs
      const v = Math.min(100, wnum(rs[i].weightPct))
      const others = rs.map((_, j) => j).filter((j) => j !== i)
      const othersSum = others.reduce((a, j) => a + wnum(rs[j].weightPct), 0)
      const next = rs.map((r, j) => (j === i ? { ...r, weightPct: v > 0 ? String(v) : "" } : r))
      return v + othersSum > 100 ? scaleRows(next, others, r2(100 - v)) : next
    })

  // แก้ช่องเงินสด แล้วหุ้นทุกตัวถูกปรับตามสัดส่วนให้รวมกับเงินสดได้ 100 พอดี
  const applyCash = (raw: string) => {
    setRows((rs) => scaleRows(rs, rs.map((_, j) => j), r2(100 - Math.min(100, wnum(raw)))))
    setCashDraft(null)
  }
  const equalWeight = () => setRows((rs) => scaleRows(rs.map((r) => ({ ...r, weightPct: "1" })), rs.map((_, j) => j), 100))
  const fillTo100 = () => setRows((rs) => scaleRows(rs, rs.map((_, j) => j), 100))
  const onStartChange = (v: string) => {
  setStart(v)
  if (v && end && v > end) setEnd(v) // ถ้าเริ่มเลยวันสิ้นสุด ดันวันสิ้นสุดตาม
}
const onEndChange = (v: string) => {
  setEnd(v)
  if (v && start && v < start) setStart(v)
}
const applyRange = (years: number | "ytd") => {
  const e = new Date()
  e.setDate(e.getDate() - 1)
  const s = years === "ytd" ? new Date(e.getFullYear(), 0, 1) : new Date(e)
  if (years !== "ytd") s.setFullYear(e.getFullYear() - years)
  setStart(ymd(s))
  setEnd(ymd(e))
}
const rangeText = (() => {
  if (!start || !end || start > end) return null
  const days = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 1
  const y = Math.floor(days / 365.25)
  const m = Math.floor((days - y * 365.25) / 30.44)
  return `ช่วงทดสอบ ${y > 0 ? `${y} ปี ` : ""}${m > 0 ? `${m} เดือน` : y === 0 ? `${days} วัน` : ""}`.trim()
})()

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold">Backtest Lab · หุ้นสหรัฐ</h2>
        <p className="mt-1 text-sm text-muted-foreground">{meta?.notice ?? "ผลจำลองย้อนหลัง ไม่ใช่ผลงานจริงและไม่ใช่การพยากรณ์"}</p>
      </div>

      <div className={card}>
        <div className="grid gap-4 md:grid-cols-2">
            <div>
            <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
              <span>หุ้นและสัดส่วน (เงินสด {cashPct.toFixed(2)}%)</span>
              <span>{rows.length}/{maxSymbols}</span>
            </div>
            <div className="space-y-2">
              {rows.map((r, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colorOf(i) }} />
                  <TickerInput
                    className={input}
                    placeholder="พิมพ์ชื่อย่อหรือชื่อบริษัท"
                    value={r.symbol}
                    onChange={(v) => setRow(i, { symbol: v })}
                    search={searchTickers}
                  />
                  <input
                    className={numInput}
                    inputMode="decimal"
                    value={r.weightPct}
                    aria-label="น้ำหนัก %"
                    onChange={(e) => setRow(i, { weightPct: e.target.value })}
                    onBlur={() => balanceFrom(i)}
                    onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur() }}
                  />
                  <span className="text-xs text-muted-foreground">%</span>
                  <button type="button" className="px-2 text-muted-foreground hover:text-red-500"
                    onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} aria-label="ลบ">✕</button>
                </div>
              ))}

              <div className="flex items-center gap-2">
                <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: CASH_COLOR }} />
                <div className={cashLabel}>เงินสด</div>
                <input
                  className={numInput}
                  inputMode="decimal"
                  aria-label="เงินสด %"
                  value={cashDraft ?? String(cashPct)}
                  onChange={(e) => setCashDraft(e.target.value)}
                  onBlur={(e) => { if (cashDraft !== null) applyCash(e.target.value) }}
                  onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur() }}
                />
                <span className="text-xs text-muted-foreground">%</span>
                <span className="px-2 opacity-0" aria-hidden>✕</span>
              </div>
            </div>

            {totalPct > 100.0001 && (
              <p className="mt-1 text-xs text-red-500">
                รวม {totalPct.toFixed(2)}% เกิน 100% — กด Enter หรือคลิกออกจากช่อง ระบบจะปรับให้อัตโนมัติ
              </p>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <button type="button" disabled={rows.length >= maxSymbols} className="rounded-md border px-2.5 py-1 hover:bg-accent disabled:opacity-40"
                onClick={() => setRows((rs) => [...rs, { symbol: "", weightPct: "" }])}>+ เพิ่มหุ้น</button>
              <button type="button" className="rounded-md border px-2.5 py-1 hover:bg-accent" onClick={equalWeight}>เฉลี่ยเท่ากัน</button>
              <button type="button" className="rounded-md border px-2.5 py-1 hover:bg-accent" onClick={fillTo100}>ปรับให้ครบ 100% (ไม่เหลือเงินสด)</button>
            </div>

            {donutData.length > 0 && (
              <div className="mt-5 flex justify-center">
                <DonutChart
                  data={donutData}
                  size={190}
                  strokeWidth={24}
                  onSegmentHover={(s) => setHoverLabel(s ? s.label : null)}
                  centerContent={
                    <div className="text-center">
                      <p className="max-w-[90px] truncate text-xs text-muted-foreground">{hoverSeg ? hoverSeg.label : "รวม"}</p>
                      <p className="text-xl font-bold">
                        {hoverSeg ? hoverSeg.value.toFixed(2) : Math.max(100, totalPct).toFixed(0)}%
                      </p>
                    </div>
                  }
                />
              </div>
            )}
          </div>
          <div className="space-y-3">
            <div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={label}>วันเริ่มต้น</label>
                  <input type="date" className={dateInput} value={start} max={end || today()}
                    onClick={openPicker} onChange={(e) => onStartChange(e.target.value)} />
                </div>
                <div>
                  <label className={label}>วันสิ้นสุด</label>
                  <input type="date" className={dateInput} value={end} min={start || undefined} max={today()}
                    onClick={openPicker} onChange={(e) => onEndChange(e.target.value)} />
                </div>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {([1, 3, 5, 10] as const).map((y) => (
                  <button key={y} type="button" className={chip} onClick={() => applyRange(y)}>{y} ปี</button>
                ))}
                <button type="button" className={chip} onClick={() => applyRange("ytd")}>ปีนี้</button>
                {rangeText && <span className="ml-auto text-xs text-muted-foreground">{rangeText}</span>}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className={label}>เงินทุนเริ่มต้น (USD)</label><input className={input} inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} /></div>
              <div><label className={label}>Risk-free ต่อปี % (เว้นว่าง = 0)</label><input className={input} inputMode="decimal" value={rf} onChange={(e) => setRf(e.target.value)} /></div>
            </div>
            <div><label className={label}>โหมด Rebalance</label>
              <select className={input} value={mode} onChange={(e) => setMode(e.target.value as RebalanceMode)}>
                <option value="none">ไม่ปรับสัดส่วน (Buy-and-Hold)</option>
                <option value="calendar">ตามรอบเวลา</option>
                <option value="threshold">ตามเกณฑ์เบี่ยง</option>
                <option value="hybrid">ผสม (เวลา + เกณฑ์)</option>
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {(mode === "calendar" || mode === "hybrid") && (
                <div><label className={label}>ความถี่</label>
                  <select className={input} value={freq} onChange={(e) => setFreq(e.target.value as RebalanceFreq)}>
                    <option value="monthly">รายเดือน</option><option value="quarterly">รายไตรมาส</option><option value="annual">รายปี</option>
                  </select></div>
              )}
              {(mode === "threshold" || mode === "hybrid") && (
                <div><label className={label}>เกณฑ์เบี่ยง (pp)</label><input className={input} inputMode="decimal" value={thr} onChange={(e) => setThr(e.target.value)} /></div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
            <div><label className={label}>ค่าคอมมิชชัน (bps)</label><input className={input} inputMode="decimal" value={comm} onChange={(e) => setComm(e.target.value)} /></div>
            <div><label className={label}>Slippage (bps)</label><input className={input} inputMode="decimal" value={slip} onChange={(e) => setSlip(e.target.value)} /></div>
            </div>
          </div>
        </div>

        <p className="mt-3 text-xs text-muted-foreground">
          คำสั่งซื้อขายจับคู่ที่ราคาเปิดวันทำการถัดไป · เงินสดไม่ได้ดอกเบี้ย · ข้อมูลไม่รวมหุ้นที่ถูกถอนจากตลาด (ผลอาจดีกว่าความจริง) · Benchmark = S&P 500 Price Index (^GSPC)
        </p>
        <div className="mt-3 flex items-center gap-3">
          <button type="button" disabled={busy} onClick={() => void submit()}
            className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {busy ? "กำลังรัน…" : "รัน Backtest"}
          </button>
          {run && (run.status === "queued" || run.status === "running") && <span className="text-xs text-muted-foreground">สถานะ: {run.status === "queued" ? "รอคิว" : "กำลังคำนวณ"}</span>}
        </div>
        {error && <div className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-red-500">{error}</div>}
        {run?.status === "failed" && run.error && (
          <div className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-red-500">{run.error.message}</div>
        )}
      </div>

      {run?.status === "done" && <Results run={run} />}

      {history.length > 0 && (
        <div className={card}>
          <h3 className="mb-2 text-sm font-medium">ประวัติการรัน</h3>
          <ul className="divide-y divide-border text-xs">
            {history.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-2 py-1.5">
                <button type="button" className="truncate text-left text-primary hover:underline"
                  onClick={async () => { try { setError(null); setRun(await getRun(apiBase, getToken(), h.id)) } catch (e) { fail(e) } }}>
                  {h.created_at.slice(0, 16).replace("T", " ")} · {h.spec.positions.map((p) => p.symbol).join(", ")} · {h.spec.start} → {h.spec.end}
                </button>
                <span className="flex shrink-0 items-center gap-3">
                  <span className={h.status === "done" ? "text-emerald-500" : h.status === "failed" ? "text-red-500" : "text-muted-foreground"}>{h.status}</span>
                  <button type="button" className="text-muted-foreground hover:text-red-500"
                    onClick={async () => { try { await deleteRun(apiBase, getToken(), h.id); if (run?.id === h.id) setRun(null); await refreshHistory() } catch (e) { fail(e) } }}>ลบ</button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
