import { dp, fmt, splitSymbol } from "../../lib/market"
import type { Trade } from "../../lib/market"
import { useLanguage } from "../../i18n/LanguageContext"

export default function RecentTrades({ symbol, trades }: { symbol: string; trades: Trade[] }) {
  const { base, quote } = splitSymbol(symbol)
  const { t, lang } = useLanguage()

  return (
    <div className="bg-[#0f0f0f] p-4">
      <h3 className="mb-2 text-sm font-semibold text-[#13c38b]">{t("tradePage.recentTrades")}</h3>
      <div className="grid grid-cols-3 pb-2 text-xs text-zinc-500">
        <span>{t("tradePage.price")} ({quote})</span><span className="text-right">{t("tradePage.amount")} ({base})</span><span className="text-right">{t("tradePage.time")}</span>
      </div>
      <div className="max-h-[360px] overflow-y-auto">
        {trades.length === 0 && <p className="py-4 text-center text-xs text-zinc-500">{t("tradePage.loading")}</p>}
        {trades.slice(0, 30).map((trade) => (
          <div key={trade.id} className="grid grid-cols-3 py-0.5 text-xs">
            <span className={trade.isBuyerMaker ? "text-[#f6465d]" : "text-[#13c38b]"}>{fmt(trade.price, dp(trade.price))}</span>
            <span className="text-right text-zinc-200">{fmt(trade.qty, 4)}</span>
            <span className="text-right text-zinc-500">{new Date(trade.time).toLocaleTimeString(lang === "th" ? "th-TH" : "en-US", { hour12: false })}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
