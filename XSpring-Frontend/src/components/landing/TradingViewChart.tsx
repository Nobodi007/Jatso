import { useEffect, useRef, useState } from "react"

// สัญลักษณ์บน TradingView ถ้าเหรียญไหนขึ้น "Invalid symbol" ให้แก้ตรงนี้
const TV_SYMBOL: Record<string, string> = {
  BTC: "BITKUB:BTCTHB",
  ETH: "BITKUB:ETHTHB",
  SOL: "BITKUB:SOLTHB",
  XRP: "BITKUB:XRPTHB",
  ADA: "BITKUB:ADATHB",
  DOGE: "BITKUB:DOGETHB",
  HBAR: "BITKUB:HBARTHB",
  LINK: "BITKUB:LINKTHB",
  XLM: "BITKUB:XLMTHB",
}

const CHART_HEIGHT = 560

const isDark = () => document.documentElement.classList.contains("dark")

export default function TradingViewChart({ asset }: { asset: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [dark, setDark] = useState(isDark)

  // ตามการสลับธีมของเว็บ
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(isDark()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    const el = ref.current
    if (!el) return

    el.innerHTML = ""
    const inner = document.createElement("div")
    inner.className = "tradingview-widget-container__widget"
    inner.style.height = `${CHART_HEIGHT}px`
    inner.style.width = "100%"
    el.appendChild(inner)

    const script = document.createElement("script")
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
    script.async = true
    script.innerHTML = JSON.stringify({
      autosize: false,
      width: "100%",
      height: CHART_HEIGHT,
      symbol: TV_SYMBOL[asset] ?? `BITKUB:${asset}THB`,
      interval: "60",
      timezone: "Asia/Bangkok",
      theme: dark ? "dark" : "light",
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
  }, [asset, dark])

  return (
    <div
      ref={ref}
      className="tradingview-widget-container w-full overflow-hidden rounded-2xl border"
      style={{ height: CHART_HEIGHT, minHeight: CHART_HEIGHT }}
    />
  )
}
