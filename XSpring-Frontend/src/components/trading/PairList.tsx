import { useEffect, useState } from "react"
import { dp, fetchTickers, fmt, splitSymbol } from "../../lib/market"
import type { Ticker } from "../../lib/market"
import { useLanguage } from "../../i18n/LanguageContext"

const PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT", "HBARUSDT", "XLMUSDT", "USDCUSDT"]

export default function PairList({ active, onSelect }: { active: string; onSelect: (symbol: string) => void }) {
  const [list, setList] = useState<Ticker[]>([])
  const [q, setQ] = useState("")
  const { t } = useLanguage()

  useEffect(() => {
    const load = () => fetchTickers(PAIRS).then(setList).catch(console.error)
    load()
    const id = setInterval(load, 10_000)
    return () => clearInterval(id)
  }, [])

  const shown = list.filter((ticker) => ticker.symbol.includes(q.toUpperCase()))

  return (
    <div className="bg-[#0f0f0f] p-4">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("tradePage.search")}
        className="mb-3 w-full rounded-md bg-[#1a1a1a] px-3 py-2 text-sm outline-none placeholder:text-zinc-500" />
      <div className="grid grid-cols-3 pb-2 text-xs text-zinc-500">
        <span>{t("tradePage.pair")}</span><span className="text-right">{t("tradePage.price")}</span><span className="text-right">{t("tradePage.change")}</span>
      </div>
      {shown.map((ticker) => {
        const { base, quote } = splitSymbol(ticker.symbol)
        return (
          <button type="button" key={ticker.symbol} onClick={() => onSelect(ticker.symbol)}
            className={`grid w-full grid-cols-3 px-1 py-1.5 text-left text-xs hover:bg-white/5 ${ticker.symbol === active ? "bg-white/10" : ""}`}>
            <span className="text-white">{base}<span className="text-zinc-500">/{quote}</span></span>
            <span className="text-right text-zinc-200">{fmt(ticker.last, dp(ticker.last))}</span>
            <span className={`text-right ${ticker.changePct >= 0 ? "text-[#13c38b]" : "text-[#f6465d]"}`}>
              {ticker.changePct >= 0 ? "+" : ""}{ticker.changePct.toFixed(2)}%
            </span>
          </button>
        )
      })}
    </div>
  )
}
