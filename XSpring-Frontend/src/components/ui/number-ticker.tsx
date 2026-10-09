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
  return (
    <NumberFlow
      value={value}
      locales="th-TH"
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
