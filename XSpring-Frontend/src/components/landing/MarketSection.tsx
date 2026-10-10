import { useEffect, useMemo, useState } from "react"
import { Search, TrendingDown, TrendingUp } from "lucide-react"
import { API_BASE_URL } from "@/lib/api"

type Props = { onLogin: () => void; onRegister: () => void }

type Row = {
  asset: string
  name: string
  price: number
  change: number
  volume: number // มูลค่าซื้อขาย 24 ชม. (THB)
}

const API_BASE_URL = "https://xspring-api.onrender.com"

const FAV_KEY = "nobodi_favorites"

type Tab = "all" | "up" | "down" | "volume" | "fav"
const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "ทั้งหมด" },
  { key: "up", label: "ขึ้น" },
  { key: "down", label: "ลง" },
  { key: "volume", label: "ปริมาณสูง" },
  { key: "fav", label: "⭐ โปรด" },
]

const thb = (v: number) =>
  `฿${Number(v || 0).toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const compact = (v: number) => {
  if (v >= 1e9) return `฿${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `฿${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `฿${(v / 1e3).toFixed(1)}K`
  return `฿${v.toFixed(0)}`
}

const pct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`

async function fetchMarket(): Promise<{ rows: Row[]; sparks: Record<string, number[]> }> {
  const res = await fetch(`${API_BASE_URL}/api/public/markets`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const body = await res.json()
  const rows: Row[] = (Array.isArray(body?.rows) ? body.rows : []).map((r: any) => ({
    asset: String(r.asset),
    name: String(r.name || r.asset),
    price: Number(r.price || 0),
    change: Number(r.change || 0),
    volume: Number(r.volume || 0),
  }))
  if (rows.length === 0) throw new Error("ไม่พบข้อมูลตลาด")
  return { rows, sparks: body?.sparks || {} }
}

function Spark({ data, up }: { data?: number[]; up: boolean }) {
  if (!data || data.length < 2) return <div className="h-8 w-24" />
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * 96},${30 - ((v - min) / range) * 28 - 1}`)
    .join(" ")
  return (
    <svg viewBox="0 0 96 30" className="h-8 w-24" aria-hidden="true">
      <polyline
        points={pts}
        fill="none"
        strokeWidth={1.8}
        strokeLinejoin="round"
        strokeLinecap="round"
        className={up ? "stroke-emerald-500" : "stroke-red-500"}
      />
    </svg>
  )
}

function Coin({ asset, size = 28 }: { asset: string; size?: number }) {
  const [i, setI] = useState(0)
  const key = asset.toLowerCase()
  const sources = [
    `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/svg/color/${key}.svg`,
    `https://assets.coincap.io/assets/icons/${key}@2x.png`,
  ]
  if (i >= sources.length) {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold"
        style={{ width: size, height: size }}
      >
        {asset.slice(0, 3)}
      </div>
    )
  }
  return (
    <img
      src={sources[i]}
      alt={asset}
      width={size}
      height={size}
      onError={() => setI((n) => n + 1)}
      className="shrink-0 rounded-full bg-muted object-cover"
      style={{ width: size, height: size }}
    />
  )
}

function SummaryCard({
  label, value, sub, tone,
}: { label: string; value: string; sub?: string; tone?: "up" | "down" }) {
  return (
    <div className="min-w-[200px] flex-1 rounded-xl border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-2 text-xl font-bold">{value}</p>
      {sub && (
        <p
          className={`mt-1 text-xs ${
            tone === "up" ? "text-emerald-500" : tone === "down" ? "text-red-500" : "text-muted-foreground"
          }`}
        >
          {sub}
        </p>
      )}
    </div>
  )
}

export default function MarketSection({ onLogin, onRegister }: Props) {
  const [rows, setRows] = useState<Row[]>([])
  const [sparks, setSparks] = useState<Record<string, number[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [updated, setUpdated] = useState("")
  const [search, setSearch] = useState("")
  const [tab, setTab] = useState<Tab>("all")
  const [favs, setFavs] = useState<string[]>(() => {
    try {
      const p = JSON.parse(localStorage.getItem(FAV_KEY) || "[]")
      return Array.isArray(p) ? p.map(String) : []
    } catch {
      return []
    }
  })

  // ราคา รีเฟรชทุก 15 วินาที
  useEffect(() => {
    let alive = true
    const run = async () => {
      try {
        const { rows: r, sparks: s } = await fetchMarket()
        if (!alive) return
        setRows(r)
        if (Object.keys(s).length > 0) setSparks(s)
        setError("")
        setUpdated(new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" }))
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "โหลดข้อมูลตลาดไม่สำเร็จ")
      } finally {
        if (alive) setLoading(false)
      }
    }
    run()
    const t = setInterval(() => {
      if (document.visibilityState === "visible") run()
    }, 15000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

    
  
  const toggleFav = (asset: string) =>
    setFavs((prev) => {
      const next = prev.includes(asset) ? prev.filter((a) => a !== asset) : [...prev, asset]
      try {
        localStorage.setItem(FAV_KEY, JSON.stringify(next))
      } catch {
        // เก็บไม่ได้ก็ใช้ต่อได้
      }
      return next
    })

  const stats = useMemo(() => {
    const btc = rows.find((r) => r.asset === "BTC")
    const gain = [...rows].sort((a, b) => b.change - a.change)[0]
    const lose = [...rows].sort((a, b) => a.change - b.change)[0]
    const total = rows.reduce((s, r) => s + r.volume, 0)
    return { btc, gain, lose, total }
  }, [rows])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    let list = rows.filter((r) => !q || r.asset.toLowerCase().includes(q) || r.name.toLowerCase().includes(q))
    if (tab === "up") list = list.filter((r) => r.change > 0).sort((a, b) => b.change - a.change)
    else if (tab === "down") list = list.filter((r) => r.change < 0).sort((a, b) => a.change - b.change)
    else if (tab === "fav") list = list.filter((r) => favs.includes(r.asset))
    else list = [...list].sort((a, b) => b.volume - a.volume)
    return list
  }, [rows, search, tab, favs])

  const gridCols =
    "grid grid-cols-[24px_minmax(0,1fr)_auto_72px] items-center gap-3 md:grid-cols-[24px_28px_minmax(0,1.6fr)_1.2fr_90px_110px_1fr_72px]"

  return (
    <main className="mx-auto max-w-7xl px-4 py-10">
      {/* หัวหน้า */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">ตลาดคริปโต</h1>
          <p className="mt-1 text-sm text-muted-foreground">ราคาสดจาก Bitkub เป็นสกุลเงินบาท</p>
        </div>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className={`size-2 rounded-full ${error ? "bg-red-500" : "animate-pulse bg-emerald-500"}`} />
          {error ? "ข้อมูลไม่พร้อมใช้งาน" : `Live${updated ? ` · ${updated}` : ""}`}
        </span>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          โหลดข้อมูลตลาดไม่สำเร็จ ({error})
        </div>
      )}

      {/* การ์ดสรุป */}
      <div className="mt-6 flex gap-3 overflow-x-auto pb-1">
        <SummaryCard
          label="Bitcoin (BTC)"
          value={stats.btc ? thb(stats.btc.price) : "—"}
          sub={stats.btc ? pct(stats.btc.change) : undefined}
          tone={stats.btc ? (stats.btc.change >= 0 ? "up" : "down") : undefined}
        />
        <SummaryCard
          label="ขึ้นแรงสุด 24 ชม."
          value={stats.gain ? stats.gain.asset : "—"}
          sub={stats.gain ? pct(stats.gain.change) : undefined}
          tone="up"
        />
        <SummaryCard
          label="ลงแรงสุด 24 ชม."
          value={stats.lose ? stats.lose.asset : "—"}
          sub={stats.lose ? pct(stats.lose.change) : undefined}
          tone="down"
        />
        <SummaryCard
          label="มูลค่าซื้อขาย 24 ชม."
          value={rows.length ? compact(stats.total) : "—"}
          sub={`${rows.length} เหรียญ`}
        />
      </div>

      {/* ค้นหา + ตัวกรอง */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ค้นหาเหรียญ"
            className="w-full rounded-lg border bg-card py-2 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.key
                  ? "bg-emerald-500 text-black"
                  : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ตาราง */}
      <div className="mt-4 overflow-hidden rounded-xl border bg-card">
        <div className={`${gridCols} border-b px-4 py-3 text-xs font-medium text-muted-foreground`}>
          <div />
          <div className="hidden md:block">#</div>
          <div>เหรียญ</div>
          <div className="text-right md:text-left">ราคา</div>
          <div className="text-right md:text-left">24 ชม.</div>
          <div className="hidden md:block">7 วัน</div>
          <div className="hidden md:block">ปริมาณ</div>
          <div className="hidden md:block" />
        </div>

        {loading && rows.length === 0 ? (
          <p className="py-14 text-center text-sm text-muted-foreground">กำลังโหลดตลาด...</p>
        ) : visible.length === 0 ? (
          <p className="py-14 text-center text-sm text-muted-foreground">
            {tab === "fav" ? "ยังไม่มีเหรียญโปรด กดดาวที่เหรียญเพื่อเพิ่ม" : "ไม่พบเหรียญ"}
          </p>
        ) : (
          visible.map((r, idx) => {
            const up = r.change >= 0
            const isFav = favs.includes(r.asset)
            return (
              <div
                key={r.asset}
                onClick={onLogin}
                className={`${gridCols} cursor-pointer border-b px-4 py-3 last:border-b-0 hover:bg-accent/50`}
              >
                <button
                  type="button"
                  aria-label={isFav ? "เอาออกจากรายการโปรด" : "เพิ่มในรายการโปรด"}
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleFav(r.asset)
                  }}
                  className={isFav ? "text-yellow-400" : "text-muted-foreground hover:text-yellow-400"}
                >
                  {isFav ? "★" : "☆"}
                </button>
                <div className="hidden text-xs text-muted-foreground md:block">{idx + 1}</div>
                <div className="flex min-w-0 items-center gap-2.5">
                  <Coin asset={r.asset} />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-tight">{r.asset}</p>
                    <p className="truncate text-[11px] text-muted-foreground">{r.name}</p>
                  </div>
                </div>
                <div className="text-right text-sm font-medium tabular-nums md:text-left">{thb(r.price)}</div>
                <div
                  className={`flex items-center justify-end gap-1 text-sm font-medium tabular-nums md:justify-start ${
                    up ? "text-emerald-500" : "text-red-500"
                  }`}
                >
                  {up ? <TrendingUp className="hidden size-3 md:block" /> : <TrendingDown className="hidden size-3 md:block" />}
                  {pct(r.change)}
                </div>
                <div className="hidden md:block">
                  <Spark data={sparks[r.asset]} up={up} />
                </div>
                <div className="hidden text-sm tabular-nums text-muted-foreground md:block">{compact(r.volume)}</div>
                <div className="hidden md:block">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onRegister()
                    }}
                    className="rounded-md bg-emerald-500 px-3 py-1 text-xs font-semibold text-black hover:bg-emerald-400"
                  >
                    ซื้อ
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* แบนเนอร์ชวนสมัคร */}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-4 rounded-2xl border bg-card p-6">
        <div>
          <p className="text-lg font-bold">อยากลองซื้อขายก่อนใช้เงินจริง?</p>
          <p className="mt-1 text-sm text-muted-foreground">สมัครบัญชีจำลองฟรี ฝึกซื้อขายด้วยราคาตลาดจริง</p>
        </div>
        <button
          type="button"
          onClick={onRegister}
          className="rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-bold text-black hover:bg-emerald-400"
        >
          สมัครบัญชีจำลองฟรี
        </button>
      </div>
    </main>
  )
}
