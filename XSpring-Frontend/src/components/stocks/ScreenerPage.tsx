import { useEffect, useMemo, useState } from "react"

type Unit = "usd" | "pct" | "x" | "mcap" | "vol" | "num" | "flag" | "days" | "score"
type Tier = "core" | "adv" | "quant" | "tech"
type Metric = { id: string; label: string; group: string; tier: Tier; unit: Unit; ph: string; tip?: string }
type TechInfo = { asOf: string | null; count: number; mode: string; phase: string; done: number; total: number; error: string | null }
type Meta = {
  groups: { id: string; title: string }[]
  metrics: Metric[]
  industries: string[]
  exchanges: string[]
}
type Row = { symbol: string; name?: string | null; industry?: string | null; [k: string]: any }
type Resp = {
  updatedAt: string | null
  partial: boolean
  universe: number
  loaded: number
  total: number
  coverage: Record<string, number>
  tech?: TechInfo
  rows: Row[]
}
type Range = { min: string; max: string }
type Filters = Record<string, Range>

const TIERS: { id: Tier; label: string }[] = [
  { id: "core", label: "หลัก" },
  { id: "adv", label: "Advanced" },
  { id: "quant", label: "Quant" },
  { id: "tech", label: "Technicals" },
]

const BASE_COLS = ["price", "changePercent", "marketCap"]

const PRESETS: { label: string; hint: string; f: Filters }[] = [
  { label: "ราคาไม่แพง", hint: "P/E ≤ 15, ROE ≥ 10%", f: { pe: { min: "", max: "15" }, roe: { min: "10", max: "" } } },
  { label: "คุณภาพสูง", hint: "ROE ≥ 20%, Net margin ≥ 15%", f: { roe: { min: "20", max: "" }, netMargin: { min: "15", max: "" } } },
  { label: "เติบโตเร็ว", hint: "รายได้โต ≥ 15%, EPS โต ≥ 15%", f: { revenueGrowth: { min: "15", max: "" }, epsGrowth: { min: "15", max: "" } } },
  { label: "ปันผลเด่น", hint: "ปันผล ≥ 3%, Payout ≤ 70%", f: { dividendYield: { min: "3", max: "" }, payoutRatio: { min: "", max: "70" } } },
  { label: "งบแข็งแรง", hint: "D/E ≤ 0.5, Current ratio ≥ 1.5, ROE ≥ 12%", f: { debtToEquity: { min: "", max: "0.5" }, currentRatio: { min: "1.5", max: "" }, roe: { min: "12", max: "" } } },
  { label: "ใกล้จุดสูงสุด", hint: "ห่างจาก High 52 สัปดาห์ไม่เกิน 5%", f: { fromHigh52w: { min: "-5", max: "" } } },
  { label: "RSI Oversold", hint: "RSI(14) ≤ 30", f: { rsi: { min: "", max: "30" } } },
  { label: "Golden Cross ใหม่", hint: "SMA50 ตัดขึ้น SMA200 ภายใน 10 วัน", f: { goldenCrossDays: { min: "", max: "10" } } },
  { label: "เทรนด์ขึ้นชัด", hint: "ราคาเหนือ SMA50 และ SMA200, ADX ≥ 25", f: { distSma50: { min: "0", max: "" }, distSma200: { min: "0", max: "" }, adx: { min: "25", max: "" } } },
  { label: "เบรกเอาต์ + วอลุ่ม", hint: "ใกล้สูงสุด 20 วัน และวอลุ่ม ≥ 1.5 เท่า", f: { donchianPos: { min: "95", max: "" }, relVolume: { min: "1.5", max: "" } } },
  { label: "Bollinger บีบตัว", hint: "Bandwidth ≤ 6%", f: { bbWidth: { min: "", max: "6" } } },
  { label: "Technical Buy", hint: "Technical Rating ≥ 0.1", f: { techRating: { min: "0.1", max: "" } } },
  { label: "ใหญ่และคล่อง", hint: "มูลค่าตลาด ≥ 100,000 ล้าน, วอลุ่ม ≥ 5 ล้านหุ้น", f: { marketCap: { min: "100000", max: "" }, avgVolume: { min: "5", max: "" } } },
]

const UNIT_HINT: Partial<Record<Unit, string>> = { pct: "%", x: "เท่า", usd: "USD", mcap: "ล้าน USD", vol: "ล้านหุ้น", days: "วันทำการ", score: "−1 ถึง +1" }

const fmt = (v: any, u: Unit) => {
  if (v == null || typeof v !== "number") return "–"
  const L = (d: number) => v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })
  switch (u) {
    case "usd": return `$${L(2)}`
    case "pct": return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`
    case "mcap": {
      const a = Math.abs(v)
      return a >= 1e6 ? `${(v / 1e6).toFixed(2)}T` : a >= 1e3 ? `${(v / 1e3).toFixed(1)}B` : `${v.toFixed(0)}M`
    }
    case "vol": return `${L(2)}M`
    case "flag": return v ? "✓" : "–"
    case "days": return `${v.toFixed(0)} วัน`
    case "score": return `${v > 0 ? "+" : ""}${v.toFixed(2)}`
    case "x": return L(2)
    default: return L(2)
  }
}

const tone = (v: any) =>
  typeof v !== "number" || v === 0 ? "" : v > 0 ? "text-emerald-500" : "text-red-500"
const isToned = (m: Metric) =>
  m.id === "changePercent" || /Growth$/.test(m.id) || m.unit === "score" || /^(perf|dist|gapPct|sarDist|roc$)/.test(m.id)

// "" → undefined (ไม่ใช้), ตัวเลขไม่ถูกต้อง → NaN
const parse = (s: string): number | undefined => {
  const t = (s ?? "").trim().replace(/,/g, "")
  if (t === "") return undefined
  const n = Number(t)
  return Number.isFinite(n) ? n : NaN
}

function openCompany(symbol: string) {
  try {
    localStorage.setItem("stocks_pending_symbol", symbol)
  } catch {
    // เก็บไม่ได้ก็ยังกดได้ แต่หน้า Company จะไม่เปิดหุ้นตัวนั้นให้
  }
  window.dispatchEvent(new CustomEvent("stocks:open-company", { detail: symbol }))
}

export default function ScreenerPage({ apiBase }: { apiBase: string }) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [active, setActive] = useState<string[]>([])
  const [filters, setFilters] = useState<Filters>({})
  const [industry, setIndustry] = useState("")
  const [exchange, setExchange] = useState("")
  const [sort, setSort] = useState("marketCap")
  const [desc, setDesc] = useState(true)
  const [data, setData] = useState<Resp | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [tick, setTick] = useState(0)
  const [picker, setPicker] = useState(false)
  const [tier, setTier] = useState<Tier>("core")
  const [q, setQ] = useState("")
  const [limit, setLimit] = useState(200)

  const byId = useMemo(() => new Map((meta?.metrics ?? []).map((m) => [m.id, m])), [meta])

  // โหลดรายการตัวชี้วัด (ซ้ำเมื่อ backend ยังไม่มีข้อมูลอุตสาหกรรม/ตลาด)
  useEffect(() => {
    if (meta && meta.industries.length) return
    let off = false
    fetch(`${apiBase}/api/stocks/screener/meta`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j: Meta) => !off && setMeta(j))
      .catch((e) => !off && setError(e instanceof Error ? e.message : "โหลดไม่สำเร็จ"))
    return () => {
      off = true
    }
  }, [apiBase, meta, tick])

  const activeCount = active.length + (industry ? 1 : 0) + (exchange ? 1 : 0)
  const invalid = (id: string) => {
    const r = filters[id]
    return !!r && (Number.isNaN(parse(r.min)) || Number.isNaN(parse(r.max)))
  }

  useEffect(() => {
    let off = false
    const timer = window.setTimeout(async () => {
      const qs = new URLSearchParams()
      for (const id of active) {
        const r = filters[id]
        if (!r) continue
        const lo = parse(r.min)
        const hi = parse(r.max)
        if (lo !== undefined && !Number.isNaN(lo)) qs.set(`${id}_min`, String(lo))
        if (hi !== undefined && !Number.isNaN(hi)) qs.set(`${id}_max`, String(hi))
      }
      if (industry) qs.set("industry", industry)
      if (exchange) qs.set("exchange", exchange)
      qs.set("sort", sort)
      qs.set("desc", String(desc))
      qs.set("limit", String(limit))

      setLoading(true)
      try {
        const r = await fetch(`${apiBase}/api/stocks/screener?${qs.toString()}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = (await r.json()) as Resp
        if (!off) {
          setData(j)
          setError("")
        }
      } catch (e) {
        if (!off) setError(e instanceof Error ? e.message : "โหลดไม่สำเร็จ")
      } finally {
        if (!off) setLoading(false)
      }
    }, 400)
    return () => {
      off = true
      window.clearTimeout(timer)
    }
  }, [apiBase, active, filters, industry, exchange, sort, desc, tick, limit])

  // ระหว่างที่ backend ยังดึงข้อมูลไม่ครบ โหลดซ้ำเองทุก 20 วินาที
  useEffect(() => {
    if (!data?.partial && data?.loaded !== 0) return
    const id = window.setTimeout(() => setTick((t) => t + 1), 20000)
    return () => window.clearTimeout(id)
  }, [data])

  const addFilter = (id: string) => {
    setActive((a) => (a.includes(id) ? a : [...a, id]))
    const flag = byId.get(id)?.unit === "flag"
    setFilters((f) => (f[id] ? f : { ...f, [id]: { min: flag ? "1" : "", max: "" } }))
  }
  const removeFilter = (id: string) => setActive((a) => a.filter((x) => x !== id))
  const setRange = (id: string, k: keyof Range, v: string) =>
    setFilters((f) => ({ ...f, [id]: { ...(f[id] ?? { min: "", max: "" }), [k]: v } }))
  const applyPreset = (f: Filters) => {
    setLimit(200)
    setFilters(f)
    setActive(Object.keys(f))
    setIndustry("")
    setExchange("")
  }
  const clearAll = () => {
    setLimit(200)
    setFilters({})
    setActive([])
    setIndustry("")
    setExchange("")
  }
  const clickSort = (k: string) => {
    if (k === sort) setDesc((d) => !d)
    else {
      setSort(k)
      setDesc(true)
    }
  }

  // ตารางแสดงคอลัมน์พื้นฐาน + ทุกตัวที่ใช้กรอง เพื่อให้เห็นว่าทำไมหุ้นตัวนั้นผ่านเกณฑ์
  const cols = useMemo(
    () =>
      [...new Set([...BASE_COLS, ...active])]
        .map((id) => byId.get(id))
        .filter((m): m is Metric => !!m),
    [active, byId]
  )

  const rows = data?.rows ?? []
  const building = data != null && (data.partial || data.loaded === 0)
  const noData = (id: string) => !!data && data.loaded >= 20 && (data.coverage?.[id] ?? 0) === 0

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Screener</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          เลือกเฉพาะตัวกรองที่สนใจ แล้วกรองหุ้นสหรัฐจากชุดหุ้นใหญ่ที่ระบบสแกนไว้ ({data?.universe ?? "–"} ตัว)
        </p>
      </div>

      <div className="rounded-xl border bg-card p-5">
        <div className="mb-5 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">ชุดสำเร็จรูป</span>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              title={p.hint}
              onClick={() => applyPreset(p.f)}
              className="rounded-full border px-3 py-1 text-xs hover:bg-accent"
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={clearAll}
            className="rounded-full px-3 py-1 text-xs text-muted-foreground hover:bg-accent"
          >
            ล้างเงื่อนไข{activeCount > 0 ? ` (${activeCount})` : ""}
          </button>
        </div>

        <div className="mb-5 grid max-w-xl gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">กลุ่มอุตสาหกรรม</label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">ทั้งหมด</option>
              {(meta?.industries ?? []).map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">ตลาดที่จดทะเบียน</label>
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">ทั้งหมด</option>
              {(meta?.exchanges ?? []).map((i) => (
                <option key={i} value={i}>{i}</option>
              ))}
            </select>
          </div>
        </div>

        {active.length > 0 && (
          <div className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {active.map((id) => {
              const m = byId.get(id)
              if (!m) return null
              const r = filters[id] ?? { min: "", max: "" }
              const bad = invalid(id)
              const hint = UNIT_HINT[m.unit]
              return (
                <div key={id} className="rounded-lg border bg-muted/20 p-3">
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div className="text-sm font-semibold">{m.label}</div>
                    <button
                      type="button"
                      onClick={() => removeFilter(id)}
                      aria-label={`เอา ${m.label} ออก`}
                      className="text-xs text-muted-foreground hover:text-foreground"
                    >
                      ลบ
                    </button>
                  </div>
                  {m.unit === "flag" ? (
                    <div className="text-xs text-muted-foreground">ต้องพบแพทเทิร์นนี้ที่แท่งล่าสุด</div>
                  ) : (
                  <div className="flex items-center gap-2">
                    {(["min", "max"] as const).map((k) => (
                      <div key={k} className="flex-1">
                        <label className="mb-1 block text-[11px] text-muted-foreground">
                          {k === "min" ? "ตั้งแต่" : "ไม่เกิน"}
                        </label>
                        <input
                          value={r[k]}
                          onChange={(e) => setRange(id, k, e.target.value)}
                          inputMode="decimal"
                          placeholder={k === "min" ? m.ph : ""}
                          className={`w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary ${
                            Number.isNaN(parse(r[k])) ? "border-red-500" : ""
                          }`}
                        />
                      </div>
                    ))}
                  </div>
                  )}
                  {m.tip && <div className="mt-1 text-[11px] leading-4 text-muted-foreground">{m.tip}</div>}
                  {bad ? (
                    <div className="mt-1 text-[11px] text-red-500">กรอกเป็นตัวเลขเท่านั้น</div>
                  ) : hint ? (
                    <div className="mt-1 text-[11px] text-muted-foreground">หน่วย: {hint}</div>
                  ) : null}
                </div>
              )
            })}
          </div>
        )}

        <button
          type="button"
          onClick={() => setPicker((v) => !v)}
          className="rounded-lg border px-3 py-2 text-sm hover:bg-accent"
        >
          {picker ? "ปิดรายการตัวกรอง" : "+ เพิ่มตัวกรอง"}
        </button>

        {picker && meta && (
          <div className="mt-4 rounded-lg border bg-muted/20 p-4">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="ค้นหาตัวกรอง เช่น RSI, MACD, Hammer, P/E"
              className="mb-3 w-full max-w-sm rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
            />
            <div className={`mb-4 flex flex-wrap gap-1 ${q.trim() ? "opacity-40" : ""}`}>
              {TIERS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTier(t.id)}
                  className={`rounded-full px-3 py-1 text-xs ${
                    tier === t.id ? "bg-primary text-primary-foreground" : "border hover:bg-accent"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="space-y-4">
              {meta.groups.map((g) => {
                const needle = q.trim().toLowerCase()
                const ms = meta.metrics.filter((m) =>
                  m.group === g.id &&
                  (needle ? `${m.label} ${m.id}`.toLowerCase().includes(needle) : m.tier === tier)
                )
                if (!ms.length) return null
                return (
                  <div key={g.id}>
                    <div className="mb-2 text-xs font-semibold">{g.title}</div>
                    <div className="flex flex-wrap gap-2">
                      {ms.map((m) => {
                        const on = active.includes(m.id)
                        const empty = noData(m.id)
                        return (
                          <button
                            key={m.id}
                            type="button"
                            disabled={on || empty}
                            title={empty ? (m.tier === "tech" ? "ยังไม่มีข้อมูลราคาย้อนหลัง (กำลังสร้าง)" : "ยังไม่มีข้อมูลตัวนี้จากแหล่งข้อมูล") : m.tip}
                            onClick={() => addFilter(m.id)}
                            className={`rounded-full border px-3 py-1 text-xs ${
                              on ? "bg-accent text-muted-foreground" : empty ? "opacity-40" : "hover:bg-accent"
                            }`}
                          >
                            {m.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
              {!q.trim() && !meta.metrics.some((m) => m.tier === tier) && (
                <p className="text-xs text-muted-foreground">ยังไม่มีตัวชี้วัดในหมวดนี้</p>
              )}
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          โหลดข้อมูลไม่สำเร็จ ({error}) ถ้า backend เพิ่งตื่นจากการหลับ ลองใหม่อีกครั้งใน 30 วินาที
        </div>
      )}

      {building && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 px-4 py-3 text-sm">
          ระบบกำลังดึงข้อมูลหุ้น ({data?.loaded ?? 0} / {data?.universe ?? "–"} ตัว) รอบแรกใช้เวลานาน (หลายสิบนาที ถึงหนึ่งชั่วโมงกว่าตามจำนวนหุ้น)
          ผลลัพธ์จะเพิ่มขึ้นเอง ไม่ต้องรีเฟรช
        </div>
      )}

      {data?.tech && data.tech.phase !== "idle" && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 px-4 py-3 text-sm">
          กำลังอัปเดตราคาย้อนหลังสำหรับ Technicals ({data.tech.done} / {data.tech.total}) ครั้งแรกใช้เวลาประมาณ 1 ชั่วโมง
          ระหว่างนี้ตัวกรอง Technicals อาจยังไม่ครบ
        </div>
      )}
      {data?.tech?.error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          ดึงราคาย้อนหลังไม่สำเร็จ ({data.tech.error}) ระบบจะลองใหม่เอง
        </div>
      )}

      <div className="rounded-xl border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3">
          <div className="text-sm font-semibold">
            ผลลัพธ์ {data ? `${data.total} ตัว` : ""}
            {data && data.total > rows.length ? (
              <span className="ml-2 text-xs font-normal text-muted-foreground">(แสดง {rows.length} ตัวแรก)</span>
            ) : null}
          </div>
          <div className="text-xs text-muted-foreground">
            {loading ? "กำลังโหลด..." : data?.updatedAt ? `ข้อมูลอัปเดต ${new Date(data.updatedAt).toLocaleString("th-TH")}` : ""}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm" style={{ minWidth: 220 + cols.length * 120 }}>
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="sticky left-0 bg-card px-4 py-3 text-left font-medium">หุ้น</th>
                {cols.map((c) => (
                  <th key={c.id} className="whitespace-nowrap px-3 py-3 text-right font-medium">
                    <button type="button" onClick={() => clickSort(c.id)} className="hover:text-foreground">
                      {c.label}
                      {sort === c.id ? (desc ? " ▼" : " ▲") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.symbol}
                  onClick={() => openCompany(r.symbol)}
                  className="group cursor-pointer border-b last:border-0 hover:bg-accent/40"
                >
                  <td className="sticky left-0 bg-card px-4 py-3 group-hover:bg-muted">
                    <div className="font-semibold">{r.symbol}</div>
                    <div className="max-w-[200px] truncate text-xs text-muted-foreground">
                      {r.name || r.industry || ""}
                    </div>
                  </td>
                  {cols.map((c) => (
                    <td
                      key={c.id}
                      className={`whitespace-nowrap px-3 py-3 text-right tabular-nums ${isToned(c) ? tone(r[c.id]) : ""}`}
                    >
                      {fmt(r[c.id], c.unit)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data && data.total > rows.length && limit < 1000 && (
          <div className="border-t px-5 py-3 text-center">
            <button
              type="button"
              onClick={() => setLimit((l) => Math.min(l + 200, 1000))}
              className="rounded-lg border px-4 py-2 text-sm hover:bg-accent"
            >
              แสดงเพิ่มอีก 200 ตัว
            </button>
          </div>
        )}

        {!loading && rows.length === 0 && !building && (
          <p className="py-12 text-center text-sm text-muted-foreground">ไม่มีหุ้นที่ตรงเงื่อนไข ลองผ่อนเงื่อนไขลง</p>
        )}
      </div>

      <p className="text-xs leading-5 text-muted-foreground">
        กดชื่อคอลัมน์เพื่อเรียงลำดับ กดแถวเพื่อดูข้อมูลบริษัท · ตัวเลขพื้นฐานเป็นค่า TTM จาก Finnhub · Technicals คำนวณจากราคาปิดรายวัน{data?.tech?.asOf ? ` (ล่าสุด ${data.tech.asOf})` : ""} ไม่ใช่ real-time
        ครอบคลุมเฉพาะชุดหุ้นที่ระบบสแกน ไม่ใช่ทั้งตลาด · ช่องที่เว้นว่างไม่ถูกใช้
        หุ้นที่ไม่มีข้อมูลตัวนั้นจะถูกตัดออกเมื่อใช้ตัวกรองนั้น · ใช้เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน
      </p>
    </div>
  )
}
