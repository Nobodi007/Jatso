import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import { ArrowLeft, ChevronDown, ExternalLink, Star } from "lucide-react"
import PriceChart from "./PriceChart"
import {
  ApiError,
  RANGES,
  fetchChart,
  fetchNews,
  fetchSummary,
  type Bar,
  type NewsItem,
  type RangeKey,
  type StockSummary,
} from "./stockApi"
import { fmt, fmtAsOf, fmtCompact, fmtDate, fmtInt, marketStateLabel, signed, timeAgo } from "./format"

type Props = {
  symbol: string
  onBack?: () => void
  onTrade?: (symbol: string) => void
  onSignup?: () => void
}

const WATCH_KEY = "stock_watchlist"

function usePageVisible() {
  const [visible, setVisible] = useState(() => !document.hidden)
  useEffect(() => {
    const f = () => setVisible(!document.hidden)
    document.addEventListener("visibilitychange", f)
    return () => document.removeEventListener("visibilitychange", f)
  }, [])
  return visible
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-dashed py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-semibold tabular-nums">{value}</span>
    </div>
  )
}

const changeColor = (n: number | null | undefined) => ((n ?? 0) >= 0 ? "text-emerald-500" : "text-red-500")

export default function StockDetailPage({ symbol, onBack, onTrade, onSignup }: Props) {
  const sym = symbol.toUpperCase()
  const visible = usePageVisible()

  const [range, setRange] = useState<RangeKey>("1d")
  const [quote, setQuote] = useState<StockSummary | null>(null)
  const [bars, setBars] = useState<Bar[]>([])
  const [news, setNews] = useState<NewsItem[]>([])
  const [loadingQuote, setLoadingQuote] = useState(true)
  const [loadingChart, setLoadingChart] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showOverview, setShowOverview] = useState(false)
  const [logoOk, setLogoOk] = useState(true)
  const [watch, setWatch] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(WATCH_KEY) || "[]")
    } catch {
      return []
    }
  })

  const symRef = useRef(sym)
  symRef.current = sym
  const chartReq = useRef(0)

  const starred = watch.includes(sym)
  const toggleWatch = () => {
    const next = starred ? watch.filter((s) => s !== sym) : [...watch, sym]
    setWatch(next)
    localStorage.setItem(WATCH_KEY, JSON.stringify(next))
  }

  /* ---------- loaders ---------- */
  const loadSummary = useCallback(async () => {
    try {
      const data = await fetchSummary(sym)
      if (symRef.current !== sym) return
      setQuote(data)
      setError(null)
    } catch (e) {
      if (symRef.current !== sym) return
      const status = e instanceof ApiError ? e.status : 0
      setError(
        status === 503
          ? "ผู้ใช้งานเยอะ กรุณาลองใหม่อีกครั้ง"
          : status === 404
            ? `ไม่พบหุ้น ${sym}`
            : "โหลดข้อมูลหุ้นไม่สำเร็จ",
      )
    } finally {
      if (symRef.current === sym) setLoadingQuote(false)
    }
  }, [sym])

  const loadChart = useCallback(
    async (rg: RangeKey, silent = false) => {
      const id = ++chartReq.current
      if (!silent) setLoadingChart(true)
      try {
        const b = await fetchChart(sym, rg)
        if (id === chartReq.current) setBars(b)
      } catch {
        if (id === chartReq.current && !silent) setBars([])
      } finally {
        if (id === chartReq.current) setLoadingChart(false)
      }
    },
    [sym],
  )

  /* ---------- effects ---------- */
  useEffect(() => {
    setQuote(null)
    setNews([])
    setError(null)
    setLoadingQuote(true)
    setLogoOk(true)
    setShowOverview(false)
    loadSummary()
    fetchNews(sym)
      .then((n) => symRef.current === sym && setNews(n))
      .catch(() => {})
  }, [sym, loadSummary])

  useEffect(() => {
    loadChart(range)
  }, [range, loadChart])

  // Live refresh (หยุดเมื่อสลับแท็บ): quote 15s, กราฟ 1D 60s
  useEffect(() => {
    if (!visible) return
    const q = setInterval(loadSummary, 15_000)
    const c = range === "1d" ? setInterval(() => loadChart("1d", true), 60_000) : undefined
    return () => {
      clearInterval(q)
      if (c) clearInterval(c)
    }
  }, [visible, range, loadSummary, loadChart])

  useEffect(() => {
    document.title = quote ? `${sym} ${fmt(quote.price)} | Nobodi` : `${sym} | Nobodi`
  }, [sym, quote])

  /* ---------- derived ---------- */
  const baseline = range === "1d" ? (quote?.previousClose ?? bars[0]?.c ?? 0) : (bars[0]?.c ?? 0)

  const rangeChange = useMemo(() => {
    if (range === "1d" || bars.length < 2) return null
    const first = bars[0].c
    const last = bars[bars.length - 1].c
    return { abs: last - first, pct: ((last - first) / first) * 100 }
  }, [bars, range])

  const ext = useMemo(() => {
    if (!quote || quote.marketState === "REGULAR") return null
    if (quote.postMarketPrice && quote.marketState !== "PRE" && quote.marketState !== "PREPRE")
      return {
        label: "หลังตลาดปิด",
        p: quote.postMarketPrice,
        c: quote.postMarketChange ?? 0,
        pc: quote.postMarketChangePercent ?? 0,
      }
    if (quote.preMarketPrice)
      return {
        label: "ก่อนตลาดเปิด",
        p: quote.preMarketPrice,
        c: quote.preMarketChange ?? 0,
        pc: quote.preMarketChangePercent ?? 0,
      }
    return null
  }, [quote])

  /* ---------- render ---------- */
  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8">
      {onBack && (
        <button
          onClick={onBack}
          className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> กลับ
        </button>
      )}

      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4 border-b pb-5">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">
            {quote ? `${quote.exchange} · ราคาเรียลไทม์ · ${quote.currency}` : "\u00a0"}
          </p>

          <div className="mt-1 flex items-center gap-3">
            {quote?.logo && logoOk && (
              <img
                src={quote.logo}
                alt=""
                className="h-9 w-9 rounded-md bg-white object-contain p-0.5"
                onError={() => setLogoOk(false)}
              />
            )}
            <h1 className="truncate text-2xl font-bold">
              {quote?.name ?? sym} <span className="text-muted-foreground">({sym})</span>
            </h1>
            <button
              onClick={toggleWatch}
              aria-label={starred ? "ลบออกจาก Watchlist" : "เพิ่มใน Watchlist"}
              className="rounded p-1 hover:bg-muted"
            >
              <Star className={`h-5 w-5 ${starred ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"}`} />
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-end gap-x-8 gap-y-2">
            <div>
              {loadingQuote && !quote ? (
                <div className="h-10 w-56 animate-pulse rounded bg-muted" />
              ) : (
                <div className="flex items-baseline gap-3">
                  <span className="text-4xl font-bold tabular-nums">{quote ? fmt(quote.price) : "--"}</span>
                  {quote && (
                    <span className={`text-lg font-semibold tabular-nums ${changeColor(quote.change)}`}>
                      {signed(quote.change)} ({signed(quote.changePercent)}%)
                    </span>
                  )}
                </div>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                {quote && `ณ ${fmtAsOf(quote.time)} · ${marketStateLabel(quote.marketState)}`}
              </p>
            </div>

            {ext && (
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-semibold tabular-nums">{fmt(ext.p)}</span>
                  <span className={`text-sm font-semibold tabular-nums ${changeColor(ext.c)}`}>
                    {signed(ext.c)} ({signed(ext.pc)}%)
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{ext.label}</p>
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => onTrade?.(sym)}
            className="rounded-lg border px-5 py-3 text-sm font-semibold transition hover:bg-muted"
          >
            ซื้อขาย {sym}
          </button>
          {onSignup && (
          <button
            onClick={onSignup}
            className="rounded-lg bg-emerald-500 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-600"
          >
            สมัครตอนนี้
          </button>
        )}
        </div>
      </div>

      {error && (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-500">
          <span>{error}</span>
          <button onClick={() => loadSummary()} className="font-semibold underline">
            ลองใหม่
          </button>
        </div>
      )}

      {/* Chart */}
      <section className="mt-5 rounded-xl border bg-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setRange(r.key)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                  range === r.key ? "bg-emerald-500 text-white" : "text-muted-foreground hover:bg-muted"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          {rangeChange && (
            <span className={`text-sm font-semibold tabular-nums ${changeColor(rangeChange.abs)}`}>
              {signed(rangeChange.abs)} ({signed(rangeChange.pct)}%) ช่วงนี้
            </span>
          )}
        </div>
        <PriceChart
          bars={bars}
          baseline={baseline}
          showBaseline={range === "1d"}
          range={range}
          loading={loadingChart}
        />
      </section>

      {/* Key statistics */}
      <section className="mt-5 grid gap-x-8 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <Stat label="ราคาปิดก่อนหน้า" value={fmt(quote?.previousClose)} />
          <Stat label="ราคาเปิด" value={fmt(quote?.open)} />
          <Stat label="Bid" value={quote?.bid ? `${fmt(quote.bid)} x ${fmtInt(quote.bidSize)}` : "--"} />
          <Stat label="Ask" value={quote?.ask ? `${fmt(quote.ask)} x ${fmtInt(quote.askSize)}` : "--"} />
        </div>
        <div>
          <Stat label="ช่วงราคาวันนี้" value={quote ? `${fmt(quote.dayLow)} - ${fmt(quote.dayHigh)}` : "--"} />
          <Stat
            label="ช่วง 52 สัปดาห์"
            value={quote ? `${fmt(quote.fiftyTwoWeekLow)} - ${fmt(quote.fiftyTwoWeekHigh)}` : "--"}
          />
          <Stat label="ปริมาณซื้อขาย" value={fmtInt(quote?.volume)} />
          <Stat label="ปริมาณเฉลี่ย" value={fmtInt(quote?.avgVolume)} />
        </div>
        <div>
          <Stat label="มูลค่าตลาด" value={fmtCompact(quote?.marketCap)} />
          <Stat label="Beta (5Y รายเดือน)" value={fmt(quote?.beta)} />
          <Stat label="P/E (TTM)" value={fmt(quote?.peRatio)} />
          <Stat label="EPS (TTM)" value={fmt(quote?.eps)} />
        </div>
        <div>
          <Stat label="วันประกาศงบ (คาดการณ์)" value={fmtDate(quote?.earningsDate)} />
          <Stat
            label="เงินปันผลและอัตราผลตอบแทน"
            value={quote?.dividendRate ? `${fmt(quote.dividendRate)} (${fmt(quote.dividendYield)}%)` : "--"}
          />
          <Stat label="ราคาเป้าหมาย 1 ปี" value={fmt(quote?.targetPrice)} />
        </div>
      </section>

      {/* Company overview */}
      <section className="mt-5 rounded-xl border bg-card">
        <button
          onClick={() => setShowOverview((v) => !v)}
          className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-semibold"
        >
          <ChevronDown className={`h-4 w-4 transition ${showOverview ? "rotate-180" : ""}`} />
          ภาพรวม {quote?.name ?? sym}
          {(quote?.sector || quote?.industry) && (
            <span className="font-normal text-muted-foreground">
              · {[quote?.sector, quote?.industry].filter(Boolean).join(" / ")}
            </span>
          )}
        </button>
        {showOverview && (
          <div className="space-y-3 border-t px-4 py-4 text-sm">
            <p className="leading-relaxed text-muted-foreground">{quote?.description || "ไม่มีข้อมูลบริษัท"}</p>
            <div className="flex flex-wrap gap-6">
              {quote?.employees != null && (
                <span>
                  พนักงาน: <b>{fmtInt(quote.employees)}</b>
                </span>
              )}
              {quote?.website && (
                <a
                  href={quote.website}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-emerald-500 hover:underline"
                >
                  เว็บไซต์ <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
          </div>
        )}
      </section>

      {/* News */}
      {news.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-4 text-lg font-bold">ข่าวที่เกี่ยวข้อง</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {news.map((n) => (
              <a
                key={n.link}
                href={n.link}
                target="_blank"
                rel="noreferrer"
                className="flex gap-3 rounded-xl border bg-card p-3 transition hover:border-emerald-500/50"
              >
                {n.thumbnail && (
                  <img
                    src={n.thumbnail}
                    alt=""
                    loading="lazy"
                    className="h-20 w-28 flex-shrink-0 rounded-md object-cover"
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                )}
                <div className="min-w-0">
                  <p className="line-clamp-2 text-sm font-semibold">{n.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {n.publisher} · {timeAgo(n.publishedAt)}
                  </p>
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

      <p className="mt-8 text-xs text-muted-foreground">
        ข้อมูลจาก Finnhub และ Yahoo Finance อาจล่าช้าได้ ใช้เพื่อประกอบการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน
      </p>
    </div>
  )
}
