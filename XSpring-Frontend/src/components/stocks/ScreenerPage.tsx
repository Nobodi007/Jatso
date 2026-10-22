import { useEffect, useState } from "react"

type ScreenerRow = {
  symbol: string
  name?: string | null
  industry?: string | null
  price: number
  changePercent: number | null
  marketCap: number | null
  pe: number | null
  pb: number | null
  roe: number | null
  netMargin: number | null
  dividendYield: number | null
  beta: number | null
  revenueGrowth: number | null
}

type ScreenerResponse = {
  updatedAt: string | null
  partial: boolean
  universe: number
  loaded: number
  total: number
  rows: ScreenerRow[]
}

type Filters = {
  peMax: string
  roeMin: string
  marginMin: string
  divMin: string
  betaMax: string
  mcapMinB: string
}

const EMPTY: Filters = { peMax: "", roeMin: "", marginMin: "", divMin: "", betaMax: "", mcapMinB: "" }

const PRESETS: { label: string; hint: string; f: Partial<Filters> }[] = [
  { label: "ราคาไม่แพง", hint: "P/E ≤ 15, ROE ≥ 10%", f: { peMax: "15", roeMin: "10" } },
  { label: "คุณภาพสูง", hint: "ROE ≥ 20%, กำไรสุทธิ ≥ 15%", f: { roeMin: "20", marginMin: "15" } },
  { label: "ปันผลเด่น", hint: "ปันผล ≥ 3%, Beta ≤ 1", f: { divMin: "3", betaMax: "1" } },
  { label: "ผันผวนต่ำ", hint: "Beta ≤ 0.8, มูลค่า ≥ 50B", f: { betaMax: "0.8", mcapMinB: "50" } },
]

const COLUMNS: { key: keyof ScreenerRow; label: string }[] = [
  { key: "price", label: "ราคา" },
  { key: "changePercent", label: "วันนี้" },
  { key: "marketCap", label: "มูลค่าตลาด" },
  { key: "pe", label: "P/E" },
  { key: "pb", label: "P/B" },
  { key: "roe", label: "ROE %" },
  { key: "netMargin", label: "กำไรสุทธิ %" },
  { key: "dividendYield", label: "ปันผล %" },
  { key: "beta", label: "Beta" },
  { key: "revenueGrowth", label: "รายได้โต %" },
]

const num = (v: number | null | undefined, d = 2) =>
  v == null ? "–" : v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })

const mcap = (v: number | null) => {
  if (v == null) return "–"
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}T`
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}B`
  return `${v.toFixed(0)}M`
}

const tone = (v: number | null) =>
  v == null || v === 0 ? "text-muted-foreground" : v > 0 ? "text-emerald-500" : "text-red-500"

function openCompany(symbol: string) {
  try {
    localStorage.setItem("stocks_pending_symbol", symbol)
  } catch {
    // เก็บไม่ได้ก็ยังกดได้ แต่หน้า Company จะไม่เปิดหุ้นตัวนั้นให้
  }
  window.dispatchEvent(new CustomEvent("stocks:open-company", { detail: symbol }))
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder: string
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-muted-foreground">{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        inputMode="decimal"
        placeholder={placeholder}
        className="w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
      />
    </div>
  )
}

export default function ScreenerPage({ apiBase }: { apiBase: string }) {
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [sort, setSort] = useState<keyof ScreenerRow>("marketCap")
  const [desc, setDesc] = useState(true)
  const [data, setData] = useState<ScreenerResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let off = false
    const id = window.setTimeout(async () => {
      const qs = new URLSearchParams()
      const add = (k: string, v: string, mul = 1) => {
        const n = Number(v)
        if (v.trim() !== "" && Number.isFinite(n)) qs.set(k, String(n * mul))
      }
      add("pe_max", filters.peMax)
      add("roe_min", filters.roeMin)
      add("margin_min", filters.marginMin)
      add("div_min", filters.divMin)
      add("beta_max", filters.betaMax)
      add("mcap_min", filters.mcapMinB, 1000) // ผู้ใช้กรอกเป็นพันล้าน → ส่งเป็นล้าน
      qs.set("sort", sort)
      qs.set("desc", String(desc))
      qs.set("limit", "100")

      setLoading(true)
      try {
        const r = await fetch(`${apiBase}/api/stocks/screener?${qs.toString()}`)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = (await r.json()) as ScreenerResponse
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
      window.clearTimeout(id)
    }
  }, [apiBase, filters, sort, desc, tick])

  // ระหว่างที่ backend ยังดึงข้อมูลไม่ครบ ให้โหลดซ้ำเองทุก 20 วินาที
  useEffect(() => {
    if (!data?.partial && data?.loaded !== 0) return
    const id = window.setTimeout(() => setTick((t) => t + 1), 20000)
    return () => window.clearTimeout(id)
  }, [data])

  const set = (k: keyof Filters) => (v: string) => setFilters((f) => ({ ...f, [k]: v }))
  const clickSort = (k: keyof ScreenerRow) => {
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
          กรองหุ้นสหรัฐตามอัตราส่วนการเงิน จากชุดหุ้นใหญ่ที่ระบบสแกนไว้
        </p>
      </div>

      <div className="rounded-xl border bg-card p-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">ชุดสำเร็จรูป</span>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              title={p.hint}
              onClick={() => setFilters({ ...EMPTY, ...p.f })}
              className="rounded-full border px-3 py-1 text-xs hover:bg-accent"
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setFilters(EMPTY)}
            className="rounded-full px-3 py-1 text-xs text-muted-foreground hover:bg-accent"
          >
            ล้างเงื่อนไข
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Field label="P/E ไม่เกิน" value={filters.peMax} onChange={set("peMax")} placeholder="เช่น 20" />
          <Field label="ROE อย่างน้อย (%)" value={filters.roeMin} onChange={set("roeMin")} placeholder="เช่น 15" />
          <Field label="กำไรสุทธิอย่างน้อย (%)" value={filters.marginMin} onChange={set("marginMin")} placeholder="เช่น 10" />
          <Field label="ปันผลอย่างน้อย (%)" value={filters.divMin} onChange={set("divMin")} placeholder="เช่น 2" />
          <Field label="Beta ไม่เกิน" value={filters.betaMax} onChange={set("betaMax")} placeholder="เช่น 1.2" />
          <Field label="มูลค่าตลาดอย่างน้อย (พันล้าน USD)" value={filters.mcapMinB} onChange={set("mcapMinB")} placeholder="เช่น 100" />
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          โหลดข้อมูลไม่สำเร็จ ({error}) ถ้า backend เพิ่งตื่นจากการหลับ ลองใหม่อีกครั้งใน 30 วินาที
        </div>
      )}

      {building && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 px-4 py-3 text-sm">
          ระบบกำลังดึงข้อมูลหุ้น ({data?.loaded ?? 0} / {data?.universe ?? "–"} ตัว) รอบแรกใช้เวลาหลายนาที
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
          <table className="w-full min-w-[960px] text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="px-4 py-3 text-left font-medium">หุ้น</th>
                {COLUMNS.map((c) => (
                  <th key={c.key} className="px-3 py-3 text-right font-medium">
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
                  <td className="px-4 py-3">
                    <div className="font-semibold">{r.symbol}</div>
                    <div className="max-w-[200px] truncate text-xs text-muted-foreground">{r.name || r.industry || ""}</div>
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">${num(r.price)}</td>
                  <td className={`px-3 py-3 text-right tabular-nums ${tone(r.changePercent)}`}>
                    {r.changePercent == null ? "–" : `${r.changePercent > 0 ? "+" : ""}${r.changePercent.toFixed(2)}%`}
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">{mcap(r.marketCap)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{num(r.pe, 1)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{num(r.pb, 1)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{num(r.roe, 1)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{num(r.netMargin, 1)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{num(r.dividendYield, 2)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{num(r.beta, 2)}</td>
                  <td className={`px-3 py-3 text-right tabular-nums ${tone(r.revenueGrowth)}`}>{num(r.revenueGrowth, 1)}</td>
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
        ครอบคลุมเฉพาะชุดหุ้นที่ระบบสแกน ไม่ใช่ทั้งตลาด · ใช้เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน
      </p>
    </div>
  )
}
