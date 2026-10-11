import { dp, fmt, splitSymbol } from "../../lib/market"
import type { Trade } from "../../lib/market"

export default function RecentTrades({ symbol, trades }: { symbol: string; trades: Trade[] }) {
  const { base, quote } = splitSymbol(symbol);
  const time = (ms: number) => new Date(ms).toLocaleTimeString("th-TH", { hour12: false });

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[#0f0f0f] p-4">
      <div className="mb-3 text-sm font-semibold text-[#13c38b]">รายการล่าสุด</div>
      <div className="grid grid-cols-3 pb-2 text-xs text-zinc-500">
        <span>ราคา({quote})</span><span className="text-right">จำนวน({base})</span><span className="text-right">เวลา</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {trades.map((t) => (
          <div key={t.id} className="grid grid-cols-3 py-[3px] text-xs">
            <span className={t.isBuyerMaker ? "text-[#f6465d]" : "text-[#13c38b]"}>{fmt(t.price, dp(t.price))}</span>
            <span className="text-right text-zinc-300">{fmt(t.qty, 4)}</span>
            <span className="text-right text-zinc-400">{time(t.time)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
