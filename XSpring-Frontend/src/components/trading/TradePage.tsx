import { useState } from "react"
import { useMarket } from "../../hooks/useMarket"
import TickerBar from "./TickerBar"
import OrderBook from "./OrderBook"
import TvChart from "./TvChart"
import OrderForm from "./OrderForm"
import PairList from "./PairList"
import RecentTrades from "./RecentTrades"

export default function TradePage({ symbol: initial = "BTCUSDT" }: { symbol?: string }) {
  const [symbol, setSymbol] = useState(initial)
  const { ticker, book, trades } = useMarket(symbol, "1h")

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-200">
      <TickerBar symbol={symbol} t={ticker} />
      <div className="grid items-start gap-px bg-[#0a0a0a] lg:grid-cols-[300px_1fr_320px]">
        <OrderBook symbol={symbol} book={book} last={ticker?.last} />
        <div className="flex min-w-0 flex-col gap-px">
          <TvChart symbol={symbol} />
          <OrderForm symbol={symbol} last={ticker?.last} />
        </div>
        <div className="flex flex-col gap-px">
          <PairList active={symbol} onSelect={setSymbol} />
          <RecentTrades symbol={symbol} trades={trades} />
        </div>
      </div>
    </div>
  )
}
