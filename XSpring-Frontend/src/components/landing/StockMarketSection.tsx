import { useEffect, useMemo, useState } from "react"
import { Search, TrendingDown, TrendingUp } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"
import MarketStatusBadge from "./MarketStatusBadge"

type Props = {
  onRegister: () => void
  onSelectStock: (symbol: string) => void
}

type Quote = {
  symbol: string
  name: string
  sector: string
  price: number | null
  change: number | null
  changePercent: number | null
  high: number | null
  low: number | null
  timestamp: number | null
}
type Index = { symbol: string; name: string; price: number | null; changePercent: number | null }
type MarketRes = { asOf: number | null; rows: Quote[]; indices?: Index[] }

const API_BASE_URL = "https://xspring-api.onrender.com"
const FAV_KEY = "nobodi_favorites_stocks"
const REFRESH_MS = 90_000 // เซิร์ฟเวอร์ cache ราคา 90 วินาที ถี่กว่านี้ไม่ได้ข้อมูลใหม่

const SECTORS = ["tech", "comm", "consumer", "fin", "health", "energy"]

type Tab = "all" | "up" | "down" | "fav"
const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "mkt.tabAll" },
  { key: "up", label: "mkt.tabUp" },
  { key: "down", label: "mkt.tabDown" },
  { key: "fav", label: "mkt.tabFav" },
]

const usd = (v: number | null, locale: string) =>
  v == null ? "—" : `$${v.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const pct = (v: number | null) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`)

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

// แถบช่วงราคาต่ำ-สูงของวัน พร้อมจุดบอกตำแหน่งราคาปัจจุบัน
function DayRange({ low, high, price }: { low: number | null; high: number | null; price: number | null }) {
  if (low == null || high == null || price == null || high <= low) {
    return <span className="text-xs text-muted-foreground">—</span>
  }
  const pos = Math.min(100, Math.max(0, ((price - low) / (high - low)) * 100))
  return (
    <div className="w-full max-w-[140px]">
      <div className="relative h-1.5 rounded-full bg-muted">
        <span
          className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-500"
          style={{ left: `${pos}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] tabular-nums text-muted-foreground">
        <span>{low.toFixed(2)}</span>
        <span>{high.toFixed(2)}</span>
      </div>
    </div>
  )
}

function Avatar({ symbol }: { symbol: string }) {
  return (
    <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold">
      {symbol.slice(0, 2)}
    </div>
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

export default function StockMarketSection({ onRegister, onSelectStock }: Props) {
  const { t, lang } = useLanguage()
  const locale = lang === "th" ? "th-TH" : "en-US"
  const [data, setData] = useState<MarketRes | null>(null)
  const [sparks, setSparks] = useState<Record<string, number[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [search, setSearch] = useState("")
  const [tab, setTab] = useState<Tab>("all")
  const [sector, setSector] = useState("all")
  const [favs, setFavs] = useState<string[]>(() => {
    try {
      const p = JSON.parse(localStorage.getItem(FAV_KEY) || "[]")
      return Array.isArray(p) ? p.map(String) : []
    } catch {
      return []
    }
  })

  // ราคา: โหลดครั้งแรก แล้วรีเฟรชทุก 90 วินาทีเฉพาะตอนแท็บเบราว์เซอร์เปิดอยู่
  useEffect(() => {
    let alive = true
    const run = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/stocks/public/market`)
        if (!res.ok) {
          let code = String(res.status)
          try {
            const j = await res.json()
            if (typeof j?.detail === "string") code = j.detail
          } catch {
            /* ใช้รหัส HTTP แทน */
          }
          throw new Error(code)
        }
        const body: MarketRes = await res.json()
        if (!alive) return
        setData({ asOf: body.asOf ?? null, rows: Array.isArray(body.rows) ? body.rows : [], indices: body.indices ?? [] })
        setError("")
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "load_failed")
      } finally {
        if (alive) setLoading(false)
      }
    }
    run()
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") run()
    }, REFRESH_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  // กราฟ 7 วัน: ดึงครั้งเดียว (เซิร์ฟเวอร์ cache 24 ชม.) ไม่ต้องรีเฟรช
  useEffect(() => {
    const ctrl = new AbortController()
    fetch(`${API_BASE_URL}/api/stocks/public/market/sparks`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setSparks(d?.sparks ?? {}))
      .catch(() => {
        /* ไม่มีกราฟก็ยังใช้ตารางได้ */
      })
    return () => ctrl.abort()
  }, [])

  const rows = data?.rows ?? []

  const toggleFav = (symbol: string) =>
    setFavs((prev) => {
      const next = prev.includes(symbol) ? prev.filter((a) => a !== symbol) : [...prev, symbol]
      try {
        localStorage.setItem(FAV_KEY, JSON.stringify(next))
      } catch {
        /* เก็บไม่ได้ก็ใช้ต่อได้ */
      }
      return next
    })

  const stats = useMemo(() => {
    const withPct = rows.filter((r) => r.changePercent != null)
    const sorted = [...withPct].sort((a, b) => (b.changePercent as number) - (a.changePercent as number))
    return {
      spy: data?.indices?.find((i) => i.symbol === "SPY"),
      qqq: data?.indices?.find((i) => i.symbol === "QQQ"),
      gain: sorted[0],
      lose: sorted[sorted.length - 1],
    }
  }, [rows, data])

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    let list = rows.filter(
      (r) =>
        (!q || r.symbol.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)) &&
        (sector === "all" || r.sector === sector),
    )
    if (tab === "up") list = list.filter((r) => (r.changePercent ?? 0) > 0).sort((a, b) => (b.changePercent ?? 0) - (a.changePercent ?? 0))
    else if (tab === "down") list = list.filter((r) => (r.changePercent ?? 0) < 0).sort((a, b) => (a.changePercent ?? 0) - (b.changePercent ?? 0))
    else if (tab === "fav") list = list.filter((r) => favs.includes(r.symbol))
    return list
  }, [rows, search, tab, sector, favs])

  const asOfText = data?.asOf
    ? new Date(data.asOf * 1000).toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : ""

  const gridCols =
    "grid grid-cols-[24px_minmax(0,1fr)_auto_72px] items-center gap-3 md:grid-cols-[24px_28px_minmax(0,1.6fr)_1.2fr_90px_110px_1fr_88px]"

  return (
    <main className="mx-auto max-w-7xl px-4 py-10">
      {/* หัวหน้า */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">{t("smkt.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("smkt.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <MarketStatusBadge />
          {asOfText && !error && <span>{t("smkt.asOf", { time: asOfText })}</span>}
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {t("mkt.loadFailed")} ({error})
        </div>
      )}

      {/* การ์ดสรุป */}
      <div className="mt-6 flex gap-3 overflow-x-auto pb-1">
        <SummaryCard
          label={t("smkt.spy")}
          value={usd(stats.spy?.price ?? null, locale)}
          sub={stats.spy ? pct(stats.spy.changePercent) : undefined}
          tone={stats.spy ? ((stats.spy.changePercent ?? 0) >= 0 ? "up" : "down") : undefined}
        />
        <SummaryCard
          label={t("smkt.qqq")}
          value={usd(stats.qqq?.price ?? null, locale)}
          sub={stats.qqq ? pct(stats.qqq.changePercent) : undefined}
          tone={stats.qqq ? ((stats.qqq.changePercent ?? 0) >= 0 ? "up" : "down") : undefined}
        />
        <SummaryCard
          label={t("smkt.topGain")}
          value={stats.gain ? stats.gain.symbol : "—"}
          sub={stats.gain ? pct(stats.gain.changePercent) : undefined}
          tone="up"
        />
        <SummaryCard
          label={t("smkt.topLoss")}
          value={stats.lose ? stats.lose.symbol : "—"}
          sub={stats.lose ? pct(stats.lose.changePercent) : undefined}
          tone="down"
        />
      </div>

      {/* ค้นหา + ตัวกรอง */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("smkt.searchPh")}
            className="w-full rounded-lg border bg-card py-2 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {TABS.map((tb) => (
            <button
              key={tb.key}
              type="button"
              onClick={() => setTab(tb.key)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === tb.key
                  ? "bg-emerald-500 text-black"
                  : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {t(tb.label)}
            </button>
          ))}
          <select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            aria-label={t("smkt.sectorAll")}
            className="rounded-full border bg-card px-3 py-1.5 text-xs font-medium outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="all">{t("smkt.sectorAll")}</option>
            {SECTORS.map((s) => (
              <option key={s} value={s}>
                {t(`smkt.sec_${s}`)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ตาราง */}
      <div className="mt-4 overflow-hidden rounded-xl border bg-card">
        <div className={`${gridCols} border-b px-4 py-3 text-xs font-medium text-muted-foreground`}>
          <div />
          <div className="hidden md:block">#</div>
          <div>{t("smkt.colStock")}</div>
          <div className="text-right md:text-left">{t("mkt.colPrice")}</div>
          <div className="text-right md:text-left">{t("smkt.colToday")}</div>
          <div className="hidden md:block">{t("mkt.col7d")}</div>
          <div className="hidden md:block">{t("smkt.colRange")}</div>
          <div className="hidden md:block" />
        </div>

        {loading && rows.length === 0 ? (
          <p className="py-14 text-center text-sm text-muted-foreground">{t("mkt.loading")}</p>
        ) : visible.length === 0 ? (
          <p className="py-14 text-center text-sm text-muted-foreground">
            {tab === "fav" ? t("smkt.emptyFav") : t("smkt.notFound")}
          </p>
        ) : (
          visible.map((r, idx) => {
            const up = (r.changePercent ?? 0) >= 0
            const isFav = favs.includes(r.symbol)
            const sp = sparks[r.symbol]
            return (
              <div
                key={r.symbol}
                onClick={() => onSelectStock(r.symbol)}
                className={`${gridCols} cursor-pointer border-b px-4 py-3 last:border-b-0 hover:bg-accent/50`}
              >
                <button
                  type="button"
                  aria-label={isFav ? t("mkt.favRemove") : t("mkt.favAdd")}
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleFav(r.symbol)
                  }}
                  className={isFav ? "text-yellow-400" : "text-muted-foreground hover:text-yellow-400"}
                >
                  {isFav ? "★" : "☆"}
                </button>
                <div className="hidden text-xs text-muted-foreground md:block">{idx + 1}</div>
                <div className="flex min-w-0 items-center gap-2.5">
                  <Avatar symbol={r.symbol} />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold leading-tight">{r.symbol}</p>
                    <p className="truncate text-[11px] text-muted-foreground">{r.name}</p>
                  </div>
                </div>
                <div className="text-right text-sm font-medium tabular-nums md:text-left">{usd(r.price, locale)}</div>
                <div
                  className={`flex items-center justify-end gap-1 text-sm font-medium tabular-nums md:justify-start ${
                    r.changePercent == null ? "text-muted-foreground" : up ? "text-emerald-500" : "text-red-500"
                  }`}
                >
                  {r.changePercent != null &&
                    (up ? <TrendingUp className="hidden size-3 md:block" /> : <TrendingDown className="hidden size-3 md:block" />)}
                  {pct(r.changePercent)}
                </div>
                <div className="hidden md:block">
                  <Spark data={sp} up={sp && sp.length > 1 ? sp[sp.length - 1] >= sp[0] : up} />
                </div>
                <div className="hidden md:block">
                  <DayRange low={r.low} high={r.high} price={r.price} />
                </div>
                <div className="hidden md:block">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onSelectStock(r.symbol)
                    }}
                    className="rounded-md bg-emerald-500 px-3 py-1 text-xs font-semibold text-black hover:bg-emerald-400"
                  >
                    {t("smkt.practice")}
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>

      <p className="mt-3 text-xs text-muted-foreground">{t("smkt.disclaimer")}</p>

      {/* แบนเนอร์ชวนสมัคร */}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-4 rounded-2xl border bg-card p-6">
        <div>
          <p className="text-lg font-bold">{t("mkt.bannerTitle")}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t("mkt.bannerSub")}</p>
        </div>
        <button
          type="button"
          onClick={onRegister}
          className="rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-bold text-black hover:bg-emerald-400"
        >
          {t("mkt.bannerBtn")}
        </button>
      </div>
    </main>
  )
}
