import { dp, splitSymbol } from "../../lib/market"
import type { Ticker } from "../../lib/market"

export default function TickerBar({ symbol, t }: { symbol: string; t: Ticker | null }) {
  const { base, quote } = splitSymbol(symbol);
  const d = t ? dp(t.last) : 2;
  const up = (t?.change ?? 0) >= 0;
  const Item = ({ label, value, cls = "" }: { label: string; value: string; cls?: string }) => (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className={`text-sm ${cls}`}>{value}</span>
    </div>
  );

  return (
    <div className="flex items-center gap-8 overflow-x-auto border-b border-[#1c1c1c] bg-[#0f0f0f] px-5 py-3">
      <div>
        <div className="text-xl font-semibold text-white">{base}/{quote}</div>
      </div>
      <div className={`text-lg font-semibold ${up ? "text-[#13c38b]" : "text-[#f6465d]"}`}>
        {t ? fmt(t.last, d) : "-"}
      </div>
      <Item label="เปลี่ยน 24 ชม." cls={up ? "text-[#13c38b]" : "text-[#f6465d]"}
        value={t ? `${fmt(t.change, d)} | ${up ? "+" : ""}${t.changePct.toFixed(2)}%` : "-"} />
      <Item label="สูงสุดใน 24 ชม." value={t ? fmt(t.high, d) : "-"} />
      <Item label="ต่ำสุดใน 24 ชม." value={t ? fmt(t.low, d) : "-"} />
      <Item label={`ปริมาณ 24 ชม.(${base})`} value={t ? fmt(t.volBase, 2) : "-"} />
      <Item label={`ปริมาณ 24 ชม.(${quote})`} value={t ? fmt(t.volQuote, 2) : "-"} />
    </div>
  );
}
