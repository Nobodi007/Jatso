import { useEffect, useRef, useState } from "react"

type TradingViewChartProps = {
  symbol: string
  interval?: string
  height?: number
}

// อ่านโหมดจาก class "dark" บน <html> (ตั้งโดยปุ่มสลับธีมใน App.tsx)
function useIsDark() {
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  )

  useEffect(() => {
    const root = document.documentElement
    const observer = new MutationObserver(() => {
      setIsDark(root.classList.contains("dark"))
    })
    observer.observe(root, { attributes: true, attributeFilter: ["class"] })
    return () => observer.disconnect()
  }, [])

  return isDark
}

export default function TradingViewChart({
  symbol,
  interval = "60",
  height = 420,
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const isDark = useIsDark()

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    container.innerHTML = ""

    const widget = document.createElement("div")
    widget.className = "tradingview-widget-container__widget"
    widget.style.height = "100%"
    widget.style.width = "100%"

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
      theme: isDark ? "dark" : "light",
      backgroundColor: isDark ? "#000000" : "#ffffff",
      style: "1",
      locale: "en",
      allow_symbol_change: false,
      hide_side_toolbar: false,
      support_host: "https://www.tradingview.com",
    })

    container.appendChild(widget)
    container.appendChild(script)

    return () => {
      container.innerHTML = ""
    }
  }, [symbol, interval, isDark])

  return (
    <div
      ref={containerRef}
      className="tradingview-widget-container"
      style={{ height, width: "100%" }}
    />
  )
}
