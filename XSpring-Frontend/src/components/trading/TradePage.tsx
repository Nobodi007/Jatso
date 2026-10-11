import { useState } from "react"
import { useMarket } from "../../hooks/useMarket"
import TickerBar from "./TickerBar"
import OrderBook from "./OrderBook"
import PriceChart from "./PriceChart"
import OrderForm from "./OrderForm"
import PairList from "./PairList"
import RecentTrades from "./RecentTrades"

export default function TradePage({ symbol = "BTCUSDT" }: { symbol?: string }) {
}
  const [interval, setInterval] = useState("4h")
  const { ticker, candles, live, book, trades } = useMarket(symbol, interval)

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-zinc-200">
      {/* ใส่ <Navbar /> ของเว็บไว้ตรงนี้ */}
      <TickerBar symbol={symbol} t={ticker} />
      <div className="grid gap-px bg-[#1c1c1c] lg:grid-cols-[300px_1fr_320px]">
        <OrderBook symbol={symbol} book={book} last={ticker?.last} />
        <div className="flex flex-col gap-px">
          <div className="h-[480px]">
            <PriceChart candles={candles} live={live} interval={interval} onInterval={setInterval} />
          </div>
          <OrderForm symbol={symbol} last={ticker?.last} />
        </div>
        <div className="flex flex-col gap-px lg:h-[calc(100vh-64px)]">
          <PairList active={symbol} />
          <RecentTrades symbol={symbol} trades={trades} />
        </div>
      </div>
    </div>
  )
}
