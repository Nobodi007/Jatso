import { useEffect, useRef } from "react"

const HEIGHT = 520

export default function TvChart({ symbol }: { symbol: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    el.innerHTML = ""
    const inner = document.createElement("div")
    inner.className = "tradingview-widget-container__widget"
    inner.style.height = `${HEIGHT}px`
    inner.style.width = "100%"
    el.appendChild(inner)

    const script = document.createElement("script")
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: false,
      width: "100%",
      height: HEIGHT,
      symbol: `BINANCE:${symbol}`,
      interval: "240",
      timezone: "Asia/Bangkok",
      theme: "dark",
      style: "1",
      locale: "th_TH",
      allow_symbol_change: false,
      hide_side_toolbar: false,
      calendar: false,
      support_host: "https://www.tradingview.com",
    })
    el.appendChild(script)

    return () => {
      el.innerHTML = ""
    }
  }, [symbol])

  return (
    <div
      ref={ref}
      className="tradingview-widget-container w-full overflow-hidden"
      style={{ height: HEIGHT }}
    />
  )
}
