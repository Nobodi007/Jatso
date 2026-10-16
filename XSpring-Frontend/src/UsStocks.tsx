import { useCallback, useEffect, useRef, useState } from "react"
import { RefreshCw } from "lucide-react"

/* =========================================================
   US STOCKS (Webull UAT) — อ่านอย่างเดียว เฉพาะแอดมิน
   ใช้งาน: <UsStocks call={(p, i) => authFetch(`${API_BASE_URL}${p}`, i)} />
========================================================= */

type Fetcher = (path: string, init?: RequestInit) => Promise<Response>
type Row = Record<string, unknown>
type TabId = "overview" | "chart" | "fundamentals" | "etf" | "portfolio"

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "ภาพรวมตลาด" },
  { id: "chart", label: "ราคา & กราฟ" },
  { id: "fundamentals", label: "งบการเงิน / พื้นฐาน" },
  { id: "etf", label: "ETF" },
  { id: "portfolio", label: "พอร์ตทดสอบ" },
]

type Choice = { slug: string; label: string }

const SCREENERS: Choice[] = [
  { slug: "market-sectors", label: "กลุ่มอุตสาหกรรม" },
  { slug: "high-dividend", label: "ปันผลสูง" },
  { slug: "52-week-high-low", label: "สูง/ต่ำสุด 52 สัปดาห์" },
]

const FUNDAMENTALS: Choice[] = [
  { slug: "company-profile", label: "ข้อมูลบริษัท" },
  { slug: "financial-indicators", label: "ตัวชี้วัดการเงิน" },
  { slug: "income-statement", label: "งบกำไรขาดทุน" },
  { slug: "balance-sheet", label: "งบดุล" },
  { slug: "cash-flow", label: "งบกระแสเงินสด" },
  { slug: "financial-alert", label: "เตือนงบการเงิน" },
  { slug: "analyst-rating", label: "เรตติ้งนักวิเคราะห์" },
  { slug: "analyst-target-price", label: "ราคาเป้าหมาย" },
  { slug: "forecast-eps", label: "ประมาณการ EPS" },
  { slug: "earnings-calendar", label: "ปฏิทินประกาศงบ" },
  { slug: "dividend-calendar", label: "ปฏิทินปันผล" },
  { slug: "filings", label: "เอกสารที่ยื่น" },
  { slug: "capital-flow", label: "กระแสเงินทุน" },
  { slug: "industry-comparison", label: "เทียบอุตสาหกรรม" },
]

const ETF_ITEMS: Choice[] = [
  { slug: "fund-brief", label: "ข้อมูลกองทุน" },
  { slug: "fund-performance", label: "ผลตอบแทน" },
  { slug: "fund-net-value", label: "มูลค่าสุทธิ (NAV)" },
  { slug: "fund-holdings", label: "หุ้นที่ถือ" },
  { slug: "fund-allocation", label: "สัดส่วนการลงทุน" },
  { slug: "fund-dividends", label: "ปันผล" },
  { slug: "fund-rating", label: "เรตติ้ง" },
  { slug: "fund-splits", label: "แตกพาร์" },
  { slug: "fund-files", label: "เอกสาร" },
]

const TIMESPANS: { id: string; label: string }[] = [
  { id: "M5", label: "5 นาที" },
  { id: "M15", label: "15 นาที" },
  { id: "M60", label: "1 ชม." },
  { id: "D", label: "รายวัน" },
  { id: "W", label: "รายสัปดาห์" },
  { id: "M", label: "รายเดือน" },
]

const PREFERRED_COLUMNS = [
  "symbol", "ticker", "name", "price", "last_price", "close", "change", "change_ratio",
  "change_percent", "volume", "open", "high", "low", "quantity", "cost_price", "market_value",
  "account_id", "account_type", "account_status",
]

/* งบการเงิน: slug ที่ใช้ตารางงวด และ query ที่ Webull รองรับ (type = ANNUAL | QUARTERLY, count สูงสุด 20) */
const STATEMENT_SLUGS = ["income-statement", "balance-sheet", "cash-flow"]
const STATEMENT_COUNT = 20

/* ---------- helpers ---------- */
async function getJson(call: Fetcher, path: string, body?: string): Promise<unknown> {
  const init: RequestInit | undefined = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body }
    : undefined
  const res = await call(path, init)
  let parsed: unknown = null
  try {
    parsed = await res.json()
  } catch {
    parsed = null
  }
  if (!res.ok) {
    const detail = (parsed as { detail?: unknown } | null)?.detail
    let msg = `HTTP ${res.status}`
    if (typeof detail === "string") msg = detail
    else if (detail && typeof detail === "object") {
      const d = detail as { message?: string; error_code?: string }
      msg = [d.error_code, d.message].filter(Boolean).join(" · ") || msg
    }
    throw new Error(res.status === 403 && typeof detail === "string" ? msg : `${res.status}: ${msg}`)
  }
  return parsed
}

function findRows(data: unknown, depth = 0): Row[] {
  if (depth > 4 || data === null || typeof data !== "object") return []
  if (Array.isArray(data)) {
    if (data.length > 0 && data.every((x) => x && typeof x === "object" && !Array.isArray(x))) {
      return data as Row[]
    }
    return []
  }
  for (const value of Object.values(data as Row)) {
    const found = findRows(value, depth + 1)
    if (found.length > 0) return found
  }
  return []
}

function flattenScalars(data: unknown, prefix = "", depth = 0): [string, string][] {
  if (data === null || typeof data !== "object" || Array.isArray(data) || depth > 2) return []
  const out: [string, string][] = []
  for (const [key, value] of Object.entries(data as Row)) {
    const name = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === "object") out.push(...flattenScalars(value, name, depth + 1))
    else out.push([name, String(value ?? "")])
  }
  return out
}

function formatCell(value: unknown, key = ""): string {
  if (value === null || value === undefined) return "—"
  if (/year$/i.test(key)) return String(value)
  if (typeof value === "number") return value.toLocaleString("en-US", { maximumFractionDigits: 4 })
  if (typeof value === "object") return JSON.stringify(value).slice(0, 60)
  return String(value)
}

function pickColumns(rows: Row[]): string[] {
  const keys = Object.keys(rows[0] ?? {})
  const preferred = PREFERRED_COLUMNS.filter((k) => keys.includes(k)).slice(0, 8)
  return preferred.length >= 2 ? preferred : keys.slice(0, 8)
}

function cleanSymbol(raw: string): string {
  return raw.trim().toUpperCase().replace(/[^A-Z0-9.\-]/g, "").slice(0, 12)
}

function useEndpoint(call: Fetcher, path: string | null, body?: string) {
  const callRef = useRef(call)
  callRef.current = call
  const [state, setState] = useState<{ loading: boolean; error: string; data: unknown }>({
    loading: false, error: "", data: null,
  })

  const load = useCallback(async () => {
    if (!path) return
    setState((s) => ({ ...s, loading: true, error: "" }))
    try {
      const data = await getJson(callRef.current, path, body)
      setState({ loading: false, error: "", data })
    } catch (e) {
      setState({ loading: false, error: e instanceof Error ? e.message : "โหลดไม่สำเร็จ", data: null })
    }
  }, [path, body])

  useEffect(() => {
    void load()
  }, [load])

  return { ...state, reload: load }
}

/* ---------- chart data ---------- */
type Bar = { label: string; o: number; h: number; l: number; c: number; sort: number }

function num(v: unknown): number | null {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN
  return Number.isFinite(n) ? n : null
}

function pick(row: Row, keys: string[]): unknown {
  for (const k of keys) if (row[k] !== undefined && row[k] !== null) return row[k]
  return undefined
}

function findSeries(data: unknown, depth = 0): Row[] {
  if (depth > 5 || data === null || typeof data !== "object") return []
  if (Array.isArray(data)) {
    const objs = data.filter((x) => x && typeof x === "object" && !Array.isArray(x)) as Row[]
    if (objs.length > 0 && objs.some((r) => "close" in r || "c" in r)) return objs
    for (const item of data) {
      const found = findSeries(item, depth + 1)
      if (found.length > 0) return found
    }
    return []
  }
  for (const value of Object.values(data as Row)) {
    const found = findSeries(value, depth + 1)
    if (found.length > 0) return found
  }
  return []
}

function timeInfo(t: unknown, index: number): { label: string; sort: number } {
  const n = num(t)
  if (n !== null) {
    const ms = n < 1e12 ? n * 1000 : n
    return { label: new Date(ms).toISOString().slice(0, 16).replace("T", " "), sort: ms }
  }
  if (typeof t === "string" && t) {
    const parsed = Date.parse(t)
    return { label: t.slice(0, 16), sort: Number.isNaN(parsed) ? index : parsed }
  }
  return { label: String(index + 1), sort: index }
}

function toBars(data: unknown): Bar[] {
  const bars: Bar[] = []
  findSeries(data).forEach((r, i) => {
    const c = num(pick(r, ["close", "c", "last", "price"]))
    if (c === null) return
    const o = num(pick(r, ["open", "o"])) ?? c
    const h = num(pick(r, ["high", "h"])) ?? Math.max(o, c)
    const l = num(pick(r, ["low", "l"])) ?? Math.min(o, c)
    const { label, sort } = timeInfo(pick(r, ["time", "t", "timestamp", "date", "datetime", "trade_time"]), i)
    bars.push({ label, o, h, l, c, sort })
  })
  return bars.sort((a, b) => a.sort - b.sort)
}

function PriceChart({ bars, mode }: { bars: Bar[]; mode: "candle" | "line" }) {
  const W = 800
  const H = 300
  const PX = 10
  const PY = 18
  const lo = Math.min(...bars.map((b) => b.l))
  const hi = Math.max(...bars.map((b) => b.h))
  const span = hi - lo || 1
  const step = (W - PX * 2) / bars.length
  const y = (v: number) => PY + (H - PY * 2) * (1 - (v - lo) / span)
  const x = (i: number) => PX + step * i + step / 2
  const points = bars.map((b, i) => `${x(i).toFixed(1)},${y(b.c).toFixed(1)}`).join(" ")
  const bodyW = Math.max(1, Math.min(10, step * 0.65))

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-72 w-full" role="img" aria-label="กราฟราคา">
      {[0, 0.25, 0.5, 0.75, 1].map((g) => {
        const v = lo + span * g
        return (
          <g key={g}>
            <line x1={PX} x2={W - PX} y1={y(v)} y2={y(v)} stroke="currentColor" strokeOpacity="0.1" />
            <text x={W - PX} y={y(v) - 3} textAnchor="end" fontSize="10" fill="currentColor" fillOpacity="0.5">
              {v.toLocaleString("en-US", { maximumFractionDigits: 2 })}
            </text>
          </g>
        )
      })}
      {mode === "line" ? (
        <polyline points={points} fill="none" stroke="#10b981" strokeWidth="1.8" />
      ) : (
        bars.map((b, i) => {
          const up = b.c >= b.o
          const color = up ? "#10b981" : "#ef4444"
          const top = y(Math.max(b.o, b.c))
          const height = Math.max(1, Math.abs(y(b.o) - y(b.c)))
          return (
            <g key={i}>
              <line x1={x(i)} x2={x(i)} y1={y(b.h)} y2={y(b.l)} stroke={color} />
              <rect x={x(i) - bodyW / 2} y={top} width={bodyW} height={height} fill={color} />
            </g>
          )
        })
      )}
    </svg>
  )
}

/* ---------- UI blocks ---------- */
const STATEMENT_LABELS: Record<string, string> = {
  total_revenue: "รายได้รวม",
  revenue: "รายได้",
  cost_of_revenue: "ต้นทุนขาย",
  gross_profit: "กำไรขั้นต้น",
  opex: "ค่าใช้จ่ายในการดำเนินงาน",
  sga_exp: "ค่าใช้จ่ายขายและบริหาร",
  rnd_exp: "ค่าใช้จ่ายวิจัยและพัฒนา",
  op_income: "กำไรจากการดำเนินงาน",
  op_profit: "กำไรจากการดำเนินงาน (op_profit)",
  other_net_income: "รายได้อื่นสุทธิ",
  unusual_expense_income: "รายการผิดปกติ",
  gain_loss_on_sale_of_assets: "กำไร(ขาดทุน)จากการขายสินทรัพย์",
  ebt: "กำไรก่อนภาษี",
  income_tax: "ภาษีเงินได้",
  eat: "กำไรหลังภาษี",
  extra_items: "รายการพิเศษ",
  minority_interest: "ส่วนได้เสียที่ไม่มีอำนาจควบคุม",
  net_income: "กำไรสุทธิ",
  diluted_avg_shares: "หุ้นเฉลี่ย (diluted)",
  diluted_eps_excl_extra: "EPS diluted (ไม่รวมรายการพิเศษ)",
  diluted_eps_incl_extra: "EPS diluted (รวมรายการพิเศษ)",
  dps: "ปันผลต่อหุ้น",
}
// ฟิลด์ที่ไม่แสดงเป็นแถว: ข้อมูลหัวคอลัมน์ + ฟิลด์ที่ซ้ำกัน/ไม่อยู่ในเอกสาร Webull (inter_expse_inc_net_oper)
const STATEMENT_META = new Set([
  "fiscal_year", "fiscal_period", "end_date", "currency", "publish_date",
  "inter_expse_inc_net_oper", "other_oper_expse_total",
])
const STATEMENT_BOLD = new Set(["total_revenue", "gross_profit", "op_income", "net_income"])

function fmtMoney(v: unknown): string {
  if (v === null || v === undefined || v === "") return "–"
  const n = Number(v)
  if (!Number.isFinite(n)) return typeof v === "object" ? "–" : String(v)
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (a >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 })
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 })
}

function yoyPct(periods: Row[], i: number, k: string): number | null {
  const cur = periods[i]
  const prev = periods.find(
    (p) => Number(p.fiscal_year) === Number(cur.fiscal_year) - 1 && String(p.fiscal_period) === String(cur.fiscal_period),
  )
  if (!prev) return null
  const a = Number(cur[k])
  const b = Number(prev[k])
  if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null
  return ((a - b) / Math.abs(b)) * 100
}

// fiscal_period: 0 = ทั้งปี (FY), 1-4 = ไตรมาส
function periodHead(r: Row): string {
  const p = String(r.fiscal_period ?? "")
  const label = p === "0" ? "FY" : /^[1-4]$/.test(p) ? `Q${p}` : p
  return `${r.fiscal_year ?? ""} ${label}`.trim()
}

function StatementTable({ rows }: { rows: Row[] }) {
  const periods = [...rows].sort((a, b) => String(b.end_date ?? "").localeCompare(String(a.end_date ?? "")))
  const keys = Array.from(new Set(periods.flatMap((r) => Object.keys(r))))
    .filter((k) => !STATEMENT_META.has(k))
    .filter((k) => periods.some((r) => r[k] !== null && r[k] !== undefined && r[k] !== "" && typeof r[k] !== "object"))
    .sort((a, b) => (a in STATEMENT_LABELS ? 0 : 1) - (b in STATEMENT_LABELS ? 0 : 1))

  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="sticky left-0 whitespace-nowrap bg-card px-3 py-2 font-medium">
              รายการ ({String(periods[0]?.currency ?? "")})
            </th>
            {periods.map((p, i) => (
              <th key={i} className="whitespace-nowrap px-3 py-2 text-right font-medium">
                {periodHead(p)}
                <div className="text-[10px] font-normal opacity-70">{String(p.end_date ?? "")}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k} className={`border-b last:border-0 ${STATEMENT_BOLD.has(k) ? "bg-muted/40 font-semibold" : ""}`}>
              <td className="sticky left-0 whitespace-nowrap bg-card px-3 py-2">
                {STATEMENT_LABELS[k] ?? k.replace(/_/g, " ")}
              </td>
              {periods.map((p, i) => {
                const g = yoyPct(periods, i, k)
                return (
                  <td key={i} className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {fmtMoney(p[k])}
                    {g !== null && (
                      <div className={`text-[10px] ${g >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                        {g >= 0 ? "+" : ""}{g.toFixed(2)}%
                      </div>
                    )}
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

function Panel({
  title, subtitle, call, path, body, statement,
}: {
  title: string
  subtitle?: string
  call: Fetcher
  path: string | null
  body?: string
  statement?: boolean
}) {
  const { loading, error, data, reload } = useEndpoint(call, path, body)
  const rows = findRows(data)
  const columns = rows.length > 0 ? pickColumns(rows) : []
  const scalars = rows.length === 0 && data ? flattenScalars(data) : []

  return (
    <section className="rounded-xl border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">{title}</h3>
          {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => void reload()}
          disabled={loading || !path}
          className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          {loading ? "กำลังโหลด" : "รีเฟรช"}
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-4 py-3 text-sm">{error}</div>
      )}

      {!error && rows.length > 0 && statement && <StatementTable rows={rows} />}

      {!error && rows.length > 0 && !statement && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                {columns.map((c) => (
                  <th key={c} className="whitespace-nowrap px-3 py-2 font-medium">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 50).map((row, i) => (
                <tr key={i} className="border-b last:border-0">
                  {columns.map((c) => (
                    <td key={c} className="whitespace-nowrap px-3 py-2">{formatCell(row[c], c)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!error && rows.length === 0 && scalars.length > 0 && (
        <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {scalars.slice(0, 40).map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 border-b py-1.5">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="truncate font-medium">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      {!error && !loading && data !== null && rows.length === 0 && scalars.length === 0 && (
        <p className="mt-4 text-sm text-muted-foreground">ไม่มีข้อมูล</p>
      )}

      {data !== null && !error && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-muted-foreground">ดูข้อมูลดิบ (JSON)</summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted/50 p-3 text-xs">
            {JSON.stringify(data, null, 2).slice(0, 8000)}
          </pre>
        </details>
      )}
    </section>
  )
}

function Chips({
  items, value, onChange,
}: {
  items: Choice[]
  value: string
  onChange: (slug: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((it) => (
        <button
          key={it.slug}
          type="button"
          onClick={() => onChange(it.slug)}
          className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
            value === it.slug ? "bg-primary text-primary-foreground" : "hover:bg-accent"
          }`}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}

function SymbolBar({
  value, onSubmit, placeholder,
}: {
  value: string
  onSubmit: (symbol: string) => void
  placeholder: string
}) {
  const [input, setInput] = useState(value)
  return (
    <form
      className="flex flex-wrap items-center gap-3"
      onSubmit={(e) => {
        e.preventDefault()
        const s = cleanSymbol(input)
        if (s) onSubmit(s)
      }}
    >
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={placeholder}
        className="w-48 rounded-lg border bg-background px-3 py-2 text-sm uppercase"
      />
      <button type="submit" className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent">
        ค้นหา
      </button>
    </form>
  )
}

/* ---------- tabs ---------- */
function OverviewTab({ call }: { call: Fetcher }) {
  const [more, setMore] = useState(SCREENERS[0].slug)
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="ซื้อขายคึกคักที่สุด" subtitle="Top active" call={call} path="/api/webull/screener/top-active" />
        <Panel title="ขึ้น/ลงแรงที่สุด" subtitle="Gainers & losers" call={call} path="/api/webull/screener/gainers-losers" />
      </div>
      <Chips items={SCREENERS} value={more} onChange={setMore} />
      <Panel
        title={SCREENERS.find((s) => s.slug === more)?.label ?? more}
        call={call}
        path={`/api/webull/screener/${more}`}
      />
    </div>
  )
}

function ChartTab({ call }: { call: Fetcher }) {
  const [symbol, setSymbol] = useState("AAPL")
  const [timespan, setTimespan] = useState("D")
  const [mode, setMode] = useState<"candle" | "line">("candle")
  const body = JSON.stringify({
    symbols: [symbol], category: "US_STOCK", timespan, count: 120, real_time_required: false,
  })
  const bars = useEndpoint(call, "/api/webull/stocks/bars", body)
  const series = bars.data ? toBars(bars.data) : []
  const last = series[series.length - 1]
  const first = series[0]
  const hi = series.length > 0 ? Math.max(...series.map((b) => b.h)) : 0
  const lo = series.length > 0 ? Math.min(...series.map((b) => b.l)) : 0
  const changePct = first && last && first.c !== 0 ? ((last.c - first.c) / first.c) * 100 : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SymbolBar value={symbol} onSubmit={setSymbol} placeholder="สัญลักษณ์ เช่น AAPL" />
        <div className="flex flex-wrap gap-2">
          {TIMESPANS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTimespan(t.id)}
              className={`rounded-full border px-3 py-1.5 text-xs ${
                timespan === t.id ? "bg-primary text-primary-foreground" : "hover:bg-accent"
              }`}
            >
              {t.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setMode(mode === "candle" ? "line" : "candle")}
            className="rounded-full border px-3 py-1.5 text-xs hover:bg-accent"
          >
            {mode === "candle" ? "แท่งเทียน" : "เส้น"}
          </button>
        </div>
      </div>

      <section className="rounded-xl border bg-card p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h3 className="text-base font-semibold">{symbol}</h3>
          {last && (
            <p className="text-sm text-muted-foreground">
              ล่าสุด <span className="font-semibold text-foreground">{last.c.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
              {changePct !== null && (
                <span className={changePct >= 0 ? "ml-2 text-emerald-500" : "ml-2 text-red-500"}>
                  {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}% ในช่วงที่แสดง
                </span>
              )}
              <span className="ml-3">สูง {hi.toLocaleString("en-US", { maximumFractionDigits: 2 })} · ต่ำ {lo.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
            </p>
          )}
        </div>
        {bars.loading && <p className="mt-4 text-sm text-muted-foreground">กำลังโหลดกราฟ...</p>}
        {bars.error && (
          <div className="mt-4 rounded-lg border border-yellow-500/30 bg-yellow-500/5 px-4 py-3 text-sm">{bars.error}</div>
        )}
        {!bars.loading && !bars.error && series.length === 0 && bars.data !== null && (
          <p className="mt-4 text-sm text-muted-foreground">
            ไม่พบข้อมูลแท่งราคาในผลที่ได้ (ดูข้อมูลดิบด้านล่างเพื่อตรวจโครงสร้าง)
          </p>
        )}
        {series.length > 0 && (
          <div className="mt-3">
            <PriceChart bars={series} mode={mode} />
            <p className="mt-1 text-xs text-muted-foreground">
              {first?.label} → {last?.label} · {series.length} แท่ง
            </p>
          </div>
        )}
        {bars.data !== null && (
          <details className="mt-4">
            <summary className="cursor-pointer text-xs text-muted-foreground">ดูข้อมูลดิบ (JSON)</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted/50 p-3 text-xs">
              {JSON.stringify(bars.data, null, 2).slice(0, 6000)}
            </pre>
          </details>
        )}
      </section>

      <Panel
        title="ราคาปัจจุบัน (Snapshot)"
        subtitle="US_STOCK · ข้อมูลจาก Webull UAT"
        call={call}
        path={`/api/webull/stocks/snapshots?symbols=${encodeURIComponent(symbol)}&category=US_STOCK`}
      />
    </div>
  )
}

function FundamentalsTab({ call, items, defaultSymbol, title }: {
  call: Fetcher
  items: Choice[]
  defaultSymbol: string
  title: string
}) {
  const [symbol, setSymbol] = useState(defaultSymbol)
  const [slug, setSlug] = useState(items[0].slug)
  const [period, setPeriod] = useState<"QUARTERLY" | "ANNUAL">("QUARTERLY")
  const current = items.find((i) => i.slug === slug)
  const isStatement = STATEMENT_SLUGS.includes(slug)
  const extra = isStatement ? `&type=${period}&count=${STATEMENT_COUNT}` : ""

  return (
    <div className="space-y-4">
      <SymbolBar value={symbol} onSubmit={setSymbol} placeholder={`สัญลักษณ์ เช่น ${defaultSymbol}`} />
      <Chips items={items} value={slug} onChange={setSlug} />
      {isStatement && (
        <div className="flex flex-wrap gap-2">
          {([
            { id: "QUARTERLY", label: "รายไตรมาส" },
            { id: "ANNUAL", label: "รายปี" },
          ] as const).map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setPeriod(p.id)}
              className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                period === p.id ? "bg-primary text-primary-foreground" : "hover:bg-accent"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      <Panel
        title={`${current?.label ?? slug} · ${symbol}`}
        subtitle={isStatement ? `${title} · ${period === "ANNUAL" ? "รายปี" : "รายไตรมาส"} สูงสุด ${STATEMENT_COUNT} งวด` : title}
        call={call}
        path={`/api/webull/fundamentals/${slug}?symbol=${encodeURIComponent(symbol)}${extra}`}
        statement={isStatement}
      />
    </div>
  )
}

function PortfolioTab({ call }: { call: Fetcher }) {
  const accounts = useEndpoint(call, "/api/webull/accounts")
  const accountRows = findRows(accounts.data)
  const ids = accountRows.map((r) => String(r.account_id ?? "")).filter(Boolean)
  const [picked, setPicked] = useState("")
  const accountId = picked || ids[0] || ""
  const q = accountId ? `account_id=${encodeURIComponent(accountId)}` : ""

  return (
    <div className="space-y-4">
      <Panel title="บัญชี" subtitle="บัญชีทดสอบสาธารณะของ Webull UAT" call={call} path="/api/webull/accounts" />
      {ids.length > 1 && (
        <select
          value={accountId}
          onChange={(e) => setPicked(e.target.value)}
          className="rounded-lg border bg-background px-3 py-2 text-sm"
        >
          {ids.map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
      )}
      <Panel title="สถานะเงิน (Balance)" call={call} path={q ? `/api/webull/account/balance?${q}` : null} />
      <Panel title="หุ้นที่ถือ (Positions)" call={call} path={q ? `/api/webull/positions?${q}` : null} />
      <Panel title="คำสั่งที่ค้างอยู่" call={call} path={q ? `/api/webull/orders/open?${q}` : null} />
      <Panel title="ประวัติคำสั่ง" call={call} path={q ? `/api/webull/orders/history?${q}` : null} />
    </div>
  )
}

export default function UsStocks({ call }: { call: Fetcher }) {
  const [tab, setTab] = useState<TabId>("overview")

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">หุ้นสหรัฐ</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          โหมดทดสอบ (Webull UAT) · อ่านข้อมูลอย่างเดียว ไม่มีการส่งคำสั่งซื้อขาย · เห็นเฉพาะแอดมิน
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-full border px-4 py-2 text-sm transition-colors ${
              tab === t.id ? "bg-primary text-primary-foreground" : "hover:bg-accent"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab call={call} />}
      {tab === "chart" && <ChartTab call={call} />}
      {tab === "fundamentals" && (
        <FundamentalsTab call={call} items={FUNDAMENTALS} defaultSymbol="AAPL" title="หุ้นสหรัฐ (US_STOCK)" />
      )}
      {tab === "etf" && <FundamentalsTab call={call} items={ETF_ITEMS} defaultSymbol="SPY" title="กองทุน ETF (US_ETF)" />}
      {tab === "portfolio" && <PortfolioTab call={call} />}
    </div>
  )
}
