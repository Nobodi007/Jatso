import { dp, fmt, splitSymbol } from "../../lib/market"
import type { Trade } from "../../lib/market"

export default function RecentTrades({ symbol, trades }: { symbol: string; trades: Trade[] }) {
  const { base, quote } = splitSymbol(symbol)

  return (
    <div className="bg-[#0f0f0f] p-4">
      <h3 className="mb-2 text-sm font-semibold text-[#13c38b]">รายการล่าสุด</h3>
      <div className="grid grid-cols-3 pb-2 text-xs text-zinc-500">
        <span>ราคา({quote})</span>
        <span className="text-right">จำนวน({base})</span>
        <span className="text-right">เวลา</span>
      </div>
      <div className="max-h-[360px] overflow-y-auto">
        {trades.length === 0 && <p className="py-4 text-center text-xs text-zinc-500">กำลังโหลด…</p>}
        {trades.slice(0, 30).map((t) => (
          <div key={t.id} className="grid grid-cols-3 py-0.5 text-xs">
            <span className={t.isBuyerMaker ? "text-[#f6465d]" : "text-[#13c38b]"}>
              {fmt(t.price, dp(t.price))}
            </span>
            <span className="text-right text-zinc-200">{fmt(t.qty, 4)}</span>
            <span className="text-right text-zinc-500">
              {new Date(t.time).toLocaleTimeString("th-TH", { hour12: false })}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
