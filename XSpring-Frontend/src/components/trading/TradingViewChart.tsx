import { useEffect, useRef } from "react"

interface TradingViewChartProps {
  symbol: string
  interval?: string
  height?: number
}

export default function TradingViewChart({
  symbol,
  interval = "60",
  height = 480,
}: TradingViewChartProps) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return

    container.current.innerHTML = ""

    const wrapper = document.createElement("div")
    wrapper.className = "tradingview-widget-container"
    wrapper.style.width = "100%"
    wrapper.style.height = "100%"

    const widget = document.createElement("div")
    widget.className = "tradingview-widget-container__widget"
    widget.style.width = "100%"
    widget.style.height = "100%"

    const script = document.createElement("script")

    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"

    script.type = "text/javascript"
    script.async = true

    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: "Asia/Bangkok",
      theme: "light",
      backgroundColor: "#ffffff",
      toolbar_bg: "#ffffff",
      style: "1",
      locale: "en",
      allow_symbol_change: false,
      calendar: false,
      hide_side_toolbar: false,
      hide_top_toolbar: false,
      hide_legend: false,
      hide_volume: false,
      support_host: "https://www.tradingview.com",
    })

    wrapper.appendChild(widget)
    wrapper.appendChild(script)

    container.current.appendChild(wrapper)

    return () => {
      if (container.current) {
        container.current.innerHTML = ""
      }
    }
  }, [symbol, interval])

  return (
    <div
      ref={container}
      className="w-full overflow-hidden rounded-lg"
      style={{ height }}
    />
  )
}