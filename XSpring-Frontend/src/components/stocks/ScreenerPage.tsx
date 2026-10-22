import { useEffect, useMemo, useState } from "react"

type Row = { symbol: string; name?: string | null; industry?: string | null; [k: string]: any }

type Resp = {
  updatedAt: string | null
  partial: boolean
  universe: number
  loaded: number
  total: number
  industries: string[]
  rows: Row[]
}

type FieldSpec = {
  id: string
  param: string
  label: string
  ph: string
  mul?: number // คูณก่อนส่ง (เช่น พันล้าน → ล้าน)
  neg?: boolean // กลับเครื่องหมาย (เช่น "ห่างไม่เกิน 5%" → ≥ -5)
}

const GROUPS: { title: string; fields: FieldSpec[] }[] = [
  {
    title: "มูลค่า (ถูกหรือแพง)",
    fields: [
      { id: "pe", param: "pe_max", label: "P/E ไม่เกิน", ph: "เช่น 20" },
      { id: "pb", param: "pb_max", label: "P/B ไม่เกิน", ph: "เช่น 3" },
      { id: "ps", param: "ps_max", label: "P/S ไม่เกิน", ph: "เช่น 5" },
    ],
  },
  {
    title: "คุณภาพกิจการ",
    fields: [
      { id: "roe", param: "roe_min", label: "ROE อย่างน้อย (%)", ph: "เช่น 15" },
      { id: "roa", param: "roa_min", label: "ROA อย่างน้อย (%)", ph: "เช่น 5" },
      { id: "gross", param: "gross_min", label: "Gross margin อย่างน้อย (%)", ph: "เช่น 40" },
      { id: "opm", param: "opm_min", label: "Operating margin อย่างน้อย (%)", ph: "เช่น 15" },
      { id: "margin", param: "margin_min", label: "กำไรสุทธิอย่างน้อย (%)", ph: "เช่น 10" },
    ],
  },
  {
    title: "การเติบโต",
    fields: [
      { id: "rev", param: "rev_min", label: "รายได้โตอย่างน้อย (%)", ph: "เช่น 10" },
      { id: "epsg", param: "eps_g_min", label: "EPS โตอย่างน้อย (%)", ph: "เช่น 10" },
    ],
  },
  {
    title: "ความมั่นคงและความเสี่ยง",
    fields: [
      { id: "de", param: "de_max", label: "หนี้/ทุน (D/E) ไม่เกิน", ph: "เช่น 1" },
      { id: "cr", param: "cr_min", label: "Current ratio อย่างน้อย", ph: "เช่น 1.5" },
      { id: "beta", param: "beta_max", label: "Beta ไม่เกิน", ph: "เช่น 1.2" },
    ],
  },
  {
    title: "ปันผล",
    fields: [{ id: "div", param: "div_min", label: "ปันผลอย่างน้อย (%)", ph: "เช่น 2" }],
  },
  {
    title: "ราคาและโมเมนตัม",
    fields: [
      { id: "near", param: "from_high_min", neg: true, label: "ห่างจากสูงสุด 52 สัปดาห์ไม่เกิน (%)", ph: "เช่น 10" },
      { id: "r13", param: "ret13w_min", label: "ผลตอบแทน 3 เดือนอย่างน้อย (%)", ph: "เช่น 10" },
      { id: "r52", param: "ret52w_min", label: "ผลตอบแทน 1 ปีอย่างน้อย (%)", ph: "เช่น 20" },
    ],
  },
  {
    title: "ขนาดและสภาพคล่อง",
    fields: [
      { id: "mcap", param: "mcap_min", mul: 1000, label: "มูลค่าตลาดอย่างน้อย (พันล้าน USD)", ph: "เช่น 100" },
      { id: "vol", param: "vol_min", label: "วอลุ่มเฉลี่ย 10 วันอย่างน้อย (ล้านหุ้น)", ph: "เช่น 5" },
    ],
  },
]

const ALL_FIELDS = GROUPS.flatMap((g) => g.fields)
type Filters = Record<string, string>
const EMPTY: Filters = {}

const PRESETS: { label: string; hint: string; f: Filters }[] = [
  { label: "ราคาไม่แพง", hint: "P/E ≤ 15, ROE ≥ 10%", f: { pe: "15", roe: "10" } },
  { label: "คุณภาพสูง", hint: "ROE ≥ 20%, กำไรสุทธิ ≥ 15%", f: { roe: "20", margin: "15" } },
  { label: "เติบโตเร็ว", hint: "รายได้โต ≥ 15%, EPS โต ≥ 15%", f: { rev: "15", epsg: "15" } },
  { label: "ปันผลเด่น", hint: "ปันผล ≥ 3%, Beta ≤ 1", f: { div: "3", beta: "1" } },
  { label: "งบแข็งแรง", hint: "D/E ≤ 0.5, Current ratio ≥ 1.5, ROE ≥ 12%", f: { de: "0.5", cr: "1.5", roe: "12" } },
  { label: "ผันผวนต่ำ", hint: "Beta ≤ 0.8, มูลค่า ≥ 50B", f: { beta: "0.8", mcap: "50" } },
  { label: "ใกล้จุดสูงสุด", hint: "ห่างจาก High ≤ 5%, 3 เดือน ≥ 10%", f: { near: "5", r13: "10" } },
]

type Col = { key: string; label: string; fmt: "usd" | "pct" | "mcap" | "n1" | "n2"; tone?: boolean }
const COLS: Col[] = [
  { key: "price", label: "ราคา", fmt: "usd" },
  { key: "changePercent", label: "วันนี้", fmt: "pct", tone: true },
  { key: "marketCap", label: "มูลค่าตลาด", fmt: "mcap" },
  { key: "pe", label: "P/E", fmt: "n1" },
  { key: "pb", label: "P/B", fmt: "n1" },
  { key: "ps", label: "P/S", fmt: "n1" },
  { key: "roe", label: "ROE %", fmt: "n1" },
  { key: "netMargin", label: "กำไรสุทธิ %", fmt: "n1" },
  { key: "dividendYield", label: "ปันผล %", fmt: "n2" },
  { key: "debtToEquity", label: "D/E", fmt: "n2" },
  { key: "beta", label: "Beta", fmt: "n2" },
  { key: "revenueGrowth", label: "รายได้โต %", fmt: "n1", tone: true },
  { key: "epsGrowth", label: "EPS โต %", fmt: "n1", tone: true },
  { key: "fromHigh52w", label: "ห่างจาก High 52 สัปดาห์ %", fmt: "pct" },
  { key: "return13w", label: "3 เดือน %", fmt: "pct", tone: true },
]

const fmt = (v: any, f: Col["fmt"]) => {
  if (v == null || typeof v !== "number") return "–"
  const L = (d: number) => v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })
  switch (f) {
    case "usd": return `$${L(2)}`
    case "pct": return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`
    case "mcap": return v >= 1e6 ? `${(v / 1e6).toFixed(2)}T` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}B` : `${v.toFixed(0)}M`
    case "n1": return L(1)
    default: return L(2)
  }
}

const tone = (v: any) =>
  typeof v !== "number" || v === 0 ? "" : v > 0 ? "text-emerald-500" : "text-red-500"

function openCompany(symbol: string) {
  try {
    localStorage.setItem("stocks_pending_symbol", symbol)
  } catch {
    // เก็บไม่ได้ก็ยังกดได้ แต่หน้า Company จะไม่เปิดหุ้นตัวนั้นให้
  }
  window.dispatchEvent(new CustomEvent("stocks:open-company", { detail: symbol }))
}

export default function ScreenerPage({ apiBase }: { apiBase: string }) {
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [industry, setIndustry] = useState("")
  const [sort, setSort] = useState("marketCap")
  const [desc, setDesc] = useState(true)
  const [data, setData] = useState<Resp | null>(null)
  const [industries, setIndustries] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [tick, setTick] = useState(0)

  const activeCount = useMemo(
    () => ALL_FIELDS.filter((f) => (filters[f.id] ?? "").trim() !== "").length + (industry ? 1 : 0),
    [filters, industry]
  )

  useEffect(() => {
    let off = false
    const id = window.setTimeout(async () => {
      const qs = new URLSearchParams()
      for (const f of ALL_FIELDS) {
        const raw = (filters[f.id] ?? "").trim()
        const n = Number(raw)
        if (raw !== "" && Number.isFinite(n)) qs.set(f.param, String(n * (f.mul ?? 1) * (f.neg ? -1 : 1)))
      }
      if (industry) qs.set("industry", industry)
      qs.set("sort", sort)
      qs.set("desc", String(desc))
      qs.set("limit", "200")

      setLoading(true)
      try {
        const r = await fetch(`${apiBase}/api/stocks/screener?${qs.toString()}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = (await r.json()) as Resp
        if (!off) {
          setData(j)
          if (j.industries?.length) setIndustries(j.industries)
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
      window.clearTimeout(id)
    }
  }, [apiBase, filters, industry, sort, desc, tick])

  // ระหว่างที่ backend ยังดึงข้อมูลไม่ครบ โหลดซ้ำเองทุก 20 วินาที
  useEffect(() => {
    if (!data?.partial && data?.loaded !== 0) return
    const id = window.setTimeout(() => setTick((t) => t + 1), 20000)
    return () => window.clearTimeout(id)
  }, [data])

  const setField = (id: string) => (v: string) => setFilters((f) => ({ ...f, [id]: v }))
  const clickSort = (k: string) => {
    if (k === sort) setDesc((d) => !d)
    else {
      setSort(k)
      setDesc(true)
    }
  }

  const rows = data?.rows ?? []
  const building = data != null && (data.partial || data.loaded === 0)

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Screener</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          กรองหุ้นสหรัฐตามอัตราส่วนการเงิน จากชุดหุ้นใหญ่ที่ระบบสแกนไว้ ({data?.universe ?? "–"} ตัว)
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
              onClick={() => {
                setFilters(p.f)
                setIndustry("")
              }}
              className="rounded-full border px-3 py-1 text-xs hover:bg-accent"
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              setFilters(EMPTY)
              setIndustry("")
            }}
            className="rounded-full px-3 py-1 text-xs text-muted-foreground hover:bg-accent"
          >
            ล้างเงื่อนไข{activeCount > 0 ? ` (${activeCount})` : ""}
          </button>
        </div>

        <div className="mb-5 max-w-xs">
          <label className="mb-1 block text-xs text-muted-foreground">กลุ่มอุตสาหกรรม</label>
          <select
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">ทั้งหมด</option>
            {industries.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </div>

        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {GROUPS.map((g) => (
            <div key={g.title} className="rounded-lg border bg-muted/20 p-4">
              <div className="mb-3 text-sm font-semibold">{g.title}</div>
              <div className="space-y-3">
                {g.fields.map((f) => (
                  <div key={f.id}>
                    <label className="mb-1 block text-xs text-muted-foreground">{f.label}</label>
                    <input
                      value={filters[f.id] ?? ""}
                      onChange={(e) => setField(f.id)(e.target.value)}
                      inputMode="decimal"
                      placeholder={f.ph}
                      className="w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          โหลดข้อมูลไม่สำเร็จ ({error}) ถ้า backend เพิ่งตื่นจากการหลับ ลองใหม่อีกครั้งใน 30 วินาที
        </div>
      )}

      {building && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 px-4 py-3 text-sm">
          ระบบกำลังดึงข้อมูลหุ้น ({data?.loaded ?? 0} / {data?.universe ?? "–"} ตัว) รอบแรกใช้เวลาประมาณครึ่งชั่วโมง
          ผลลัพธ์จะเพิ่มขึ้นเอง ไม่ต้องรีเฟรช
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
          <table className="w-full min-w-[1400px] text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="sticky left-0 bg-card px-4 py-3 text-left font-medium">หุ้น</th>
                {COLS.map((c) => (
                  <th key={c.key} className="whitespace-nowrap px-3 py-3 text-right font-medium">
                    <button type="button" onClick={() => clickSort(c.key)} className="hover:text-foreground">
                      {c.label}
                      {sort === c.key ? (desc ? " ▼" : " ▲") : ""}
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
                  className="cursor-pointer border-b last:border-0 hover:bg-accent/40"
                >
                  <td className="sticky left-0 bg-card px-4 py-3">
                    <div className="font-semibold">{r.symbol}</div>
                    <div className="max-w-[200px] truncate text-xs text-muted-foreground">{r.name || r.industry || ""}</div>
                  </td>
                  {COLS.map((c) => (
                    <td
                      key={c.key}
                      className={`whitespace-nowrap px-3 py-3 text-right tabular-nums ${c.tone ? tone(r[c.key]) : ""}`}
                    >
                      {fmt(r[c.key], c.fmt)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && rows.length === 0 && !building && (
          <p className="py-12 text-center text-sm text-muted-foreground">ไม่มีหุ้นที่ตรงเงื่อนไข ลองผ่อนเงื่อนไขลง</p>
        )}
      </div>

      <p className="text-xs leading-5 text-muted-foreground">
        กดชื่อคอลัมน์เพื่อเรียงลำดับ กดแถวเพื่อดูข้อมูลบริษัท · ตัวเลขเป็นค่า TTM จาก Finnhub
        ครอบคลุมเฉพาะชุดหุ้นที่ระบบสแกน ไม่ใช่ทั้งตลาด · ถ้าตัวกรองไหนเว้นว่างไว้จะไม่ถูกใช้
        หุ้นที่ไม่มีข้อมูลตัวนั้นจะถูกตัดออกเมื่อใช้ตัวกรองนั้น · ใช้เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน
      </p>
    </div>
  )
}
