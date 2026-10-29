import * as React from "react"

export interface DonutChartSegment {
  value: number
  color: string
  label: string
}

type Props = {
  data: DonutChartSegment[]
  size?: number
  strokeWidth?: number
  centerContent?: React.ReactNode
  onSegmentHover?: (segment: DonutChartSegment | null) => void
  className?: string
}

export function DonutChart({ data, size = 200, strokeWidth = 20, centerContent, onSegmentHover, className }: Props) {
  const [hovered, setHovered] = React.useState<string | null>(null)
  const total = data.reduce((s, d) => s + d.value, 0)
  const r = size / 2 - strokeWidth / 2
  const c = 2 * Math.PI * r
  const hover = (seg: DonutChartSegment | null) => {
    setHovered(seg ? seg.label : null)
    onSegmentHover?.(seg)
  }
  let acc = 0

  return (
    <div
      className={`relative flex items-center justify-center text-muted-foreground ${className ?? ""}`}
      style={{ width: size, height: size }}
      onMouseLeave={() => hover(null)}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90 overflow-visible">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeOpacity={0.15} strokeWidth={strokeWidth} />
        {total > 0 &&
          data.map((seg) => {
            if (seg.value <= 0) return null
            const len = (seg.value / total) * c
            const start = (acc / total) * c
            acc += seg.value
            return (
              <circle
                key={seg.label}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={seg.color}
                strokeWidth={strokeWidth}
                strokeDasharray={`${len} ${c - len}`}
                strokeDashoffset={-start}
                className="cursor-pointer"
                style={{
                  opacity: hovered && hovered !== seg.label ? 0.4 : 1,
                  transition: "stroke-dasharray .35s ease, stroke-dashoffset .35s ease, opacity .2s ease",
                }}
                onMouseEnter={() => hover(seg)}
              />
            )
          })}
      </svg>
      {centerContent && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">{centerContent}</div>
      )}
    </div>
  )
}
