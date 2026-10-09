import { useEffect, useState } from "react"
import NumberFlow from "@number-flow/react"

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
  // เริ่มที่ 0 ก่อน แล้วค่อยเปลี่ยนเป็นค่าจริง ตัวเลขจะได้เลื่อนตอนเปิดหน้า
  const [shown, setShown] = useState(0)

  useEffect(() => {
    const t = window.setTimeout(() => setShown(value), 150)
    return () => window.clearTimeout(t)
  }, [value])

  return (
    <NumberFlow
      value={shown}
      locales="th-TH"
      respectMotionPreference={false}
      format={{
        style: currency ? "currency" : "decimal",
        currency,
        minimumFractionDigits: decimalPlaces,
        maximumFractionDigits: decimalPlaces,
        signDisplay: showSign ? "exceptZero" : "auto",
      }}
      className={`tabular-nums ${className}`}
    />
  )
}
