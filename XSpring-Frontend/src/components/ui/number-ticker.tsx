import { useEffect, useRef, useState } from "react"

type Props = {
  value: number
  currency?: string
  showSign?: boolean
  decimalPlaces?: number
  className?: string
}

export function NumberTicker({
  value,
  currency,
  showSign = false,
  decimalPlaces = 2,
  className = "",
}: Props) {
  const [display, setDisplay] = useState(0)
  const currentRef = useRef(0)

  useEffect(() => {
    const from = currentRef.current
    const start = performance.now()
    const duration = 1000
    let frame = 0

    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - t, 3)
      const current = from + (value - from) * eased
      currentRef.current = current
      setDisplay(current)
      if (t < 1) frame = requestAnimationFrame(tick)
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value])

  const rounded = Number(display.toFixed(decimalPlaces)) || 0
  const text = new Intl.NumberFormat("th-TH", {
    style: currency ? "currency" : "decimal",
    currency,
    minimumFractionDigits: decimalPlaces,
    maximumFractionDigits: decimalPlaces,
    signDisplay: showSign ? "exceptZero" : "auto",
  }).format(rounded)

  return <span className={`inline-block tabular-nums ${className}`}>{text}</span>
}
