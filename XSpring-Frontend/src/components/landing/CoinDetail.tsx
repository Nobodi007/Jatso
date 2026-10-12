import { useEffect, useState } from "react"
import { useLanguage } from "../../i18n/LanguageContext"
import TradingViewChart from "./TradingViewChart"
import ExchangeTable from "./ExchangeTable"

const API_BASE_URL = "https://xspring-api.onrender.com"

type Row = { asset: string; name: string; price: number; change: number; volume: number }
type NewsItem = { title: string; url: string; source: string; published_ts: number; tags: string[] }

type Props = {
  asset: string
  onBack: () => void
  onLogin: () => void
  onRegister: () => void
}

const fmtPrice = (v: number, locale: string) =>
  v.toLocaleString(locale, { maximumFractionDigits: v < 1 ? 4 : 2 })

const compact = (v: number) => {
  if (v >= 1e9) return `฿${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `฿${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `฿${(v / 1e3).toFixed(1)}K`
  return `฿${v.toFixed(0)}`
}

function timeAgo(ts: number, t: (key: string, vars?: Record<string, string | number>) => string) {
  if (!ts) return ""
  const secs = Math.max(0, Date.now() / 1000 - ts)
  if (secs < 3600) return t("coinDetail.minutesAgo", { count: Math.floor(secs / 60) })
  if (secs < 86400) return t("coinDetail.hoursAgo", { count: Math.floor(secs / 3600) })
  return t("coinDetail.daysAgo", { count: Math.floor(secs / 86400) })
}

export default function CoinDetail({ asset, onBack, onLogin, onRegister }: Props) {
  const { t: tr, lang } = useLanguage()
  const locale = lang === "en" ? "en-US" : "th-TH"
  const [row, setRow] = useState<Row | null>(null)
  const [news, setNews] = useState<NewsItem[]>([])
  const [error, setError] = useState("")

  // ราคา รีเฟรชทุก 15 วินาที
  useEffect(() => {
    let alive = true
    const load = () =>
      fetch(`${API_BASE_URL}/api/public/markets`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((d) => {
          if (!alive) return
          const found = ((d.rows ?? []) as Row[]).find((r) => r.asset === asset) ?? null
          setRow(found)
          setError(found ? "" : tr("coinDetail.notFound"))
        })
        .catch(() => alive && setError(tr("coinDetail.loadError")))
    setRow(null)
    setError("")
    load()
    const id = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [asset])

  // ข่าวของเหรียญนี้
  useEffect(() => {
    const ctrl = new AbortController()
    setNews([])
    fetch(`${API_BASE_URL}/api/public/news`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) =>
        setNews(((d.items ?? []) as NewsItem[]).filter((n) => n.tags?.includes(asset)).slice(0, 6)),
      )
      .catch(() => {})
    return () => ctrl.abort()
  }, [asset])

  const up = (row?.change ?? 0) >= 0

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <button type="button" onClick={onBack} className="text-sm text-muted-foreground hover:text-foreground">
        ← {tr("coinDetail.back")}
      </button>

      {error && <p className="mt-6 text-sm text-red-500">{error}</p>}
      {!error && !row && <p className="mt-6 text-sm text-muted-foreground">{tr("coinDetail.loading")}…</p>}

      {row && (
        <>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight">
                {row.name} <span className="text-base font-medium text-muted-foreground">{row.asset}</span>
              </h1>
              <p className="mt-2 text-4xl font-extrabold">฿{fmtPrice(row.price, locale)}</p>
              <p className={`mt-1 text-sm font-semibold ${up ? "text-emerald-500" : "text-red-500"}`}>
                {up ? "▲ +" : "▼ "}
                {row.change.toFixed(2)}% ({tr("coinDetail.hours24")})
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onLogin}
                className="rounded-lg border px-5 py-2.5 text-sm font-semibold hover:bg-accent"
              >
                {tr("coinDetail.trade")} {row.asset}
              </button>
              <button
                type="button"
                onClick={onRegister}
                className="rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-bold text-black hover:bg-emerald-400"
              >
                {tr("coinDetail.signUpNow")}
              </button>
            </div>
          </div>

          <div className="mt-6">
            <TradingViewChart asset={asset} />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-xl border p-4">
              <p className="text-xs text-muted-foreground">{tr("coinDetail.volume24h")}</p>
              <p className="mt-1 text-lg font-bold">{compact(row.volume)}</p>
            </div>
            <div className="rounded-xl border p-4">
              <p className="text-xs text-muted-foreground">{tr("coinDetail.change24h")}</p>
              <p className={`mt-1 text-lg font-bold ${up ? "text-emerald-500" : "text-red-500"}`}>
                {up ? "+" : ""}
                {row.change.toFixed(2)}%
              </p>
            </div>
            <div className="rounded-xl border p-4">
              <p className="text-xs text-muted-foreground">{tr("coinDetail.priceSource")}</p>
              <p className="mt-1 text-lg font-bold">Bitkub</p>
            </div>
          </div>

          <ExchangeTable asset={asset} />

          <h2 className="mt-10 text-xl font-bold">{tr("coinDetail.newsTitle", { asset: row.asset })}</h2>
          {news.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">{tr("coinDetail.noNews")}</p>
          ) : (
            <ul className="mt-3 divide-y">
              {news.map((n, i) => (
                <li key={`${n.url}-${i}`} className="py-3">
                  <a
                    href={n.url || undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block hover:text-emerald-500"
                  >
                    <p className="font-semibold leading-snug">{n.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {[n.source, timeAgo(n.published_ts, tr)].filter(Boolean).join(" • ")}
                    </p>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  )
}
