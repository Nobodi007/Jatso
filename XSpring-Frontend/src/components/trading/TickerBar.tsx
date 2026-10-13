import { dp, fmt, splitSymbol } from "../../lib/market"
import type { Ticker } from "../../lib/market"
import { useLanguage } from "../../i18n/LanguageContext"

export default function TickerBar({ symbol, t: ticker }: { symbol: string; t: Ticker | null }) {
  const { base, quote } = splitSymbol(symbol)
  const { t } = useLanguage()
  const d = ticker ? dp(ticker.last) : 2
  const up = (ticker?.change ?? 0) >= 0
  const Item = ({ label, value, cls = "" }: { label: string; value: string; cls?: string }) => (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className={`text-sm ${cls}`}>{value}</span>
    </div>
  )

  return (
    <div className="flex items-center gap-8 overflow-x-auto border-b border-[#1c1c1c] bg-[#0f0f0f] px-5 py-3">
      <div><div className="text-xl font-semibold text-white">{base}/{quote}</div></div>
      <div className={`text-lg font-semibold ${up ? "text-[#13c38b]" : "text-[#f6465d]"}`}>
        {ticker ? fmt(ticker.last, d) : "-"}
      </div>
      <Item label={t("tradePage.change24h")} cls={up ? "text-[#13c38b]" : "text-[#f6465d]"}
        value={ticker ? `${fmt(ticker.change, d)} | ${up ? "+" : ""}${ticker.changePct.toFixed(2)}%` : "-"} />
      <Item label={t("tradePage.high24h")} value={ticker ? fmt(ticker.high, d) : "-"} />
      <Item label={t("tradePage.low24h")} value={ticker ? fmt(ticker.low, d) : "-"} />
      <Item label={t("tradePage.volume24hBase", { asset: base })} value={ticker ? fmt(ticker.volBase, 2) : "-"} />
      <Item label={t("tradePage.volume24hQuote", { asset: quote })} value={ticker ? fmt(ticker.volQuote, 2) : "-"} />
    </div>
  )
}
