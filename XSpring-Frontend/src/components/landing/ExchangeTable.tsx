import { useEffect, useState } from "react"
import { useLanguage } from "../../i18n/LanguageContext"

const API_BASE_URL = "https://xspring-api.onrender.com"

type Venue = {
  exchange: string
  symbol: string
  url: string
  logo: string
  badge: string
  bg: string
  fg: string
  bid: number | null
  ask: number | null
  spread: number | null
  spread_pct: number | null
  fee_pct: number | null
  net_buy: number | null
  net_sell: number | null
  error: string
}

const baht = (v: number | null) => (v == null ? "—" : `฿${v.toLocaleString("th-TH", { maximumFractionDigits: 0 })}`)

function Logo({ v }: { v: Venue }) {
  const [broken, setBroken] = useState(false)
  if (v.logo && !broken) {
    return (
      <img
        src={v.logo}
        alt=""
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
        className="h-8 w-8 shrink-0 rounded-full object-cover"
      />
    )
  }
  return (
    <span
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold"
      style={{ background: v.bg, color: v.fg }}
    >
      {v.badge}
    </span>
  )
}

export default function ExchangeTable({ asset }: { asset: string }) {
  const { t } = useLanguage()
  const [rows, setRows] = useState<Venue[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () =>
      fetch(`${API_BASE_URL}/api/public/exchanges?asset=${encodeURIComponent(asset)}`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
                .then((d) => {
          if (!alive) return
          setRows(Array.isArray(d.rows) ? d.rows : [])
          setError(false)
        })
        .catch(() => alive && setError(true))
    setRows(null)
    setError(false)
    load()
    const id = setInterval(load, 10000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [asset])

  // กระดานที่ได้ราคาดีที่สุด: ซื้อถูกสุด / ขายได้มากสุด
  const buys = (rows ?? []).map((r) => r.net_buy).filter((x): x is number => x != null)
  const sells = (rows ?? []).map((r) => r.net_sell).filter((x): x is number => x != null)
  const bestBuy = buys.length ? Math.min(...buys) : null
  const bestSell = sells.length ? Math.max(...sells) : null

  return (
    <section className="mt-10">
      <h2 className="text-xl font-bold">{t("exch.title", { asset })}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{t("exch.subtitle")}</p>
      
      {error && <p className="mt-4 text-sm text-red-500">{t("exch.loadFailed")}</p>}
      {!error && !rows && <p className="mt-4 text-sm text-muted-foreground">{t("exch.loading")}</p>}
      {rows && (
        <div className="mt-4 overflow-x-auto rounded-xl border">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">{t("exch.colExchange")}</th>
                <th className="px-4 py-3 font-medium">{t("exch.colSymbol")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("exch.colBid")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("exch.colAsk")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("exch.colSpread")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("exch.colFee")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("exch.colNetBuy")}</th>
                <th className="px-4 py-3 text-right font-medium">{t("exch.colNetSell")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => {
                const ok = r.bid != null && r.ask != null
                return (
                  <tr key={r.exchange}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <Logo v={r} />
                        <span className="font-semibold">{r.exchange}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {r.url ? (
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-sky-500 hover:underline">
                          {r.symbol}
                        </a>
                      ) : (
                        r.symbol
                      )}
                    </td>
                    {ok ? (
                      <>
                        <td className="px-4 py-3 text-right font-semibold text-emerald-500">{baht(r.bid)}</td>
                        <td className="px-4 py-3 text-right font-semibold text-amber-500">{baht(r.ask)}</td>
                        <td className="px-4 py-3 text-right">
                          {baht(r.spread)}{" "}
                          <span className="text-xs text-muted-foreground">({(r.spread_pct ?? 0).toFixed(2)}%)</span>
                        </td>
                        <td className="px-4 py-3 text-right">{r.fee_pct == null ? "—" : `${r.fee_pct.toFixed(2)}%`}</td>
                        <td
                          className={`px-4 py-3 text-right font-semibold ${
                            r.net_buy != null && r.net_buy === bestBuy ? "text-emerald-500" : ""
                          }`}
                        >
                          {baht(r.net_buy)}
                          {r.net_buy != null && r.net_buy === bestBuy && <span className="ml-1 text-xs">★</span>}
                        </td>
                        <td
                          className={`px-4 py-3 text-right font-semibold ${
                            r.net_sell != null && r.net_sell === bestSell ? "text-emerald-500" : ""
                          }`}
                        >
                          {baht(r.net_sell)}
                          {r.net_sell != null && r.net_sell === bestSell && <span className="ml-1 text-xs">★</span>}
                        </td>
                      </>
                    ) : (
                      <td colSpan={6} className="px-4 py-3 text-center text-muted-foreground">
                        {r.error || t("exch.noData")}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-muted-foreground">{t("exch.legend")}</p>
    </section>
  )
}
