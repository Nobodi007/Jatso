import { useEffect, useRef, useState, type RefObject } from "react"

interface TradingViewChartProps {
  symbol: string
  interval?: string
  height?: number
}

// แปลงสี CSS (rgb/oklch/hsl ฯลฯ) เป็นค่าจริง แล้วดูว่า "มืด" หรือไม่
// คืน null ถ้าสีโปร่งใสหรืออ่านไม่ได้
function colorIsDark(css: string): boolean | null {
  const canvas = document.createElement("canvas")
  canvas.width = 1
  canvas.height = 1
  const ctx = canvas.getContext("2d", { willReadFrequently: true })
  if (!ctx) return null

  const sentinel = "#123456"
  ctx.fillStyle = sentinel
  ctx.fillStyle = css
  if (ctx.fillStyle === sentinel && css.trim().toLowerCase() !== sentinel) {
    return null
  }

  ctx.clearRect(0, 0, 1, 1)
  ctx.fillRect(0, 0, 1, 1)
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
  if (a < 10) return null

  return 0.299 * r + 0.587 * g + 0.114 * b < 128
}

// ดูสีพื้นหลังจริงของหน้าเว็บ ณ ตำแหน่งกราฟ (เดินขึ้นไปหา element ที่มีสีพื้น)
function detectDark(el: HTMLElement | null): boolean {
  let node: HTMLElement | null = el
  while (node) {
    const result = colorIsDark(getComputedStyle(node).backgroundColor)
    if (result !== null) return result
    node = node.parentElement
  }

  return (
    document.documentElement.classList.contains("dark") ||
    window.matchMedia("(prefers-color-scheme: dark)").matches
  )
}

function debugInfo(el: HTMLElement | null): string {
  const parts: string[] = []
  let node: HTMLElement | null = el
  let hops = 0
  while (node && hops < 12) {
    const bg = getComputedStyle(node).backgroundColor
    parts.push(`${node.tagName.toLowerCase()}:${bg}->${String(colorIsDark(bg))}`)
    if (colorIsDark(bg) !== null) break
    node = node.parentElement
    hops++
  }
  return `htmlClass="${document.documentElement.className}" | ${parts.join(" > ")}`
}

function useIsDark(ref: RefObject<HTMLElement | null>, onDebug: (v: string) => void) {
  const [isDark, setIsDark] = useState(
    () =>
      document.documentElement.classList.contains("dark") ||
      window.matchMedia("(prefers-color-scheme: dark)").matches
  )

  useEffect(() => {
    const update = () => {
      setIsDark(detectDark(ref.current))
      onDebug(debugInfo(ref.current))
    }

    // เช็คหลังสีเปลี่ยนเสร็จ เผื่อมี transition
    const updateSoon = () => {
      update()
      window.setTimeout(update, 350)
    }

    update()

    const observer = new MutationObserver(updateSoon)
    const watch = { attributes: true, attributeFilter: ["class", "style", "data-theme"] }
    observer.observe(document.documentElement, watch)
    observer.observe(document.body, watch)

    const media = window.matchMedia("(prefers-color-scheme: dark)")
    media.addEventListener("change", updateSoon)

    return () => {
      observer.disconnect()
      media.removeEventListener("change", updateSoon)
    }
  }, [ref, onDebug])

  return isDark
}

export default function TradingViewChart({
  symbol,
  interval = "60",
  height = 480,
}: TradingViewChartProps) {
  const container = useRef<HTMLDivElement>(null)
  const [debug, setDebug] = useState("")
  const isDark = useIsDark(container, setDebug)

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
      theme: isDark ? "dark" : "light",
      backgroundColor: isDark ? "#000000" : "#ffffff",
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
  }, [symbol, interval, isDark])

  return (
    <>
      <div
        ref={container}
        className="w-full overflow-hidden rounded-lg"
        style={{ height }}
      />
      <div className="mt-1 break-all text-[10px] text-muted-foreground">
        DEBUG chartTheme={isDark ? "dark" : "light"} | {debug}
      </div>
    </>
  )
}
