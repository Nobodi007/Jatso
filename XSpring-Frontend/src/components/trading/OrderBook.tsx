import { Book, splitSymbol, dp, fmt } from "../../lib/market"
import type { Level } from "../../lib/market"

export default function OrderBook({ symbol, book, last, rows = 14 }:
  { symbol: string; book: Book; last?: number; rows?: number }) {
  const { base, quote } = splitSymbol(symbol);
  const asks = book.asks.slice(0, rows).reverse();
  const bids = book.bids.slice(0, rows);
  const max = Math.max(...[...asks, ...bids].map((l) => l[1]), 1);
  const d = last ? dp(last) : 2;
  const prevLast = book.asks[0] && book.bids[0] ? (book.asks[0][0] + book.bids[0][0]) / 2 : last;
  const up = last && prevLast ? last >= prevLast : true;

  const Row = ({ l, side }: { l: Level; side: "ask" | "bid" }) => (
    <div className="relative grid grid-cols-3 px-4 py-[3px] text-xs hover:bg-white/5">
      <div className={`absolute inset-y-0 right-0 ${side === "ask" ? "bg-[#f6465d]/15" : "bg-[#13c38b]/15"}`}
        style={{ width: `${(l[1] / max) * 100}%` }} />
      <span className={`relative ${side === "ask" ? "text-[#f6465d]" : "text-[#13c38b]"}`}>{fmt(l[0], d)}</span>
      <span className="relative text-right text-zinc-300">{fmt(l[1], 4)}</span>
      <span className="relative text-right text-zinc-400">{fmt(l[0] * l[1], 2)}</span>
    </div>
  );

  return (
    <div className="flex h-full flex-col bg-[#0f0f0f]">
      <div className="grid grid-cols-3 px-4 py-2 text-xs text-zinc-500">
        <span>ราคา({quote})</span><span className="text-right">จำนวน({base})</span><span className="text-right">ทั้งหมด</span>
      </div>
      <div>{asks.map((l) => <Row key={"a" + l[0]} l={l} side="ask" />)}</div>
      <div className={`px-4 py-3 text-xl font-semibold ${up ? "text-[#13c38b]" : "text-[#f6465d]"}`}>
        {last ? fmt(last, d) : "-"} {up ? "↑" : "↓"}
      </div>
      <div>{bids.map((l) => <Row key={"b" + l[0]} l={l} side="bid" />)}</div>
    </div>
  );
}
