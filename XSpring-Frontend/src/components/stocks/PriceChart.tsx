import { useEffect, useId, useMemo, useRef, useState } from "react"
import type { Bar, RangeKey } from "./stockApi"
import { fmt, fmtCompact, niceTicks, tooltipLabel, xLabel } from "./format"

const UP = "#10b981"
const DOWN = "#ef4444"

type Props = {
  bars: Bar[]
  baseline: number
  showBaseline: boolean
  range: RangeKey
  loading: boolean
}

export default function PriceChart({ bars, baseline, showBaseline, range, loading }: Props) {
  const gid = useId().replace(/:/g, "")
  const wrapRef = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(800)
  const [hover, setHover] = useState<number | null>(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => setHover(null), [bars])

  const H = 300
  const VOL_H = 48
  const PAD_T = 12
  const PAD_B = 8
  const AXIS_W = 68
  const plotW = Math.max(w - AXIS_W, 10)
  const total = H + VOL_H + 22

  const calc = useMemo(() => {
    if (!bars.length) return null
    const closes = bars.map((b) => b.c)
    let min = Math.min(...closes)
    let max = Math.max(...closes)
    if (showBaseline && baseline) {
      min = Math.min(min, baseline)
      max = Math.max(max, baseline)
    }
    const pad = (max - min) * 0.08 || max * 0.01 || 1
    min -= pad
    max += pad
    const n = bars.length
    const x = (i: number) => (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW)
    const y = (v: number) => PAD_T + (1 - (v - min) / (max - min)) * (H - PAD_T - PAD_B)
    const line = bars.map((b, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(b.c).toFixed(1)}`).join("")
    const area = `${line}L${x(n - 1).toFixed(1)},${H}L${x(0).toFixed(1)},${H}Z`
    const maxV = Math.max(...bars.map((b) => b.v), 1)
    const xTickIdx = [...new Set(Array.from({ length: 6 }, (_, k) => Math.round((k / 5) * (n - 1))))]
    return { x, y, line, area, maxV, yTicks: niceTicks(min, max, 5), xTickIdx }
  }, [bars, baseline, showBaseline, plotW])

  if (!calc) {
    return (
      <div ref={wrapRef} className="flex h-[370px] items-center justify-center text-sm text-muted-foreground">
        {loading ? (
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-emerald-500" />
        ) : (
          "ไม่มีข้อมูลกราฟ"
        )}
      </div>
    )
  }

  const last = bars[bars.length - 1]
  const color = last.c >= baseline ? UP : DOWN
  const hb = hover != null ? bars[hover] : null

  const pick = (clientX: number, rect: DOMRect) => {
    const mx = clientX - rect.left
    if (mx < 0 || mx > plotW) return setHover(null)
    setHover(Math.max(0, Math.min(bars.length - 1, Math.round((mx / plotW) * (bars.length - 1)))))
  }

  const tagY = (v: number) => Math.min(Math.max(calc.y(v), 9), H - 9)

  return (
    <div ref={wrapRef} className={`relative w-full select-none ${loading ? "opacity-60" : ""}`}>
      {hb && (
        <div className="pointer-events-none absolute left-2 top-1 z-10 rounded-md border bg-card/95 px-3 py-1.5 text-xs shadow">
          <div className="text-muted-foreground">{tooltipLabel(hb.t, range)}</div>
          <div className="font-semibold tabular-nums">{fmt(hb.c)}</div>
          <div className="text-muted-foreground">Vol {fmtCompact(hb.v)}</div>
        </div>
      )}

      <svg
        width={w}
        height={total}
        className="block touch-pan-y"
        onMouseMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
        onMouseLeave={() => setHover(null)}
        onTouchMove={(e) => pick(e.touches[0].clientX, e.currentTarget.getBoundingClientRect())}
        onTouchEnd={() => setHover(null)}
      >
        <defs>
          <linearGradient id={`g${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.45} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* Grid + Y labels */}
        {calc.yTicks.map((t) => (
          <g key={t}>
            <line x1={0} x2={plotW} y1={calc.y(t)} y2={calc.y(t)} stroke="currentColor" className="text-border" />
            <text x={plotW + 8} y={calc.y(t) + 4} fontSize={11} className="fill-muted-foreground">
              {fmt(t)}
            </text>
          </g>
        ))}

        {/* Area + line */}
        <path d={calc.area} fill={`url(#g${gid})`} />
        <path d={calc.line} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" />

        {/* Previous close */}
        {showBaseline && baseline > 0 && (
          <g>
            <line
              x1={0}
              x2={plotW}
              y1={calc.y(baseline)}
              y2={calc.y(baseline)}
              stroke="currentColor"
              className="text-muted-foreground"
              strokeDasharray="4 4"
            />
            <rect x={plotW + 2} y={tagY(baseline) - 9} width={AXIS_W - 4} height={18} rx={3} className="fill-muted" />
            <text x={plotW + 8} y={tagY(baseline) + 4} fontSize={11} className="fill-foreground">
              {fmt(baseline)}
            </text>
          </g>
        )}

        {/* Last price tag */}
        <rect x={plotW + 2} y={tagY(last.c) - 9} width={AXIS_W - 4} height={18} rx={3} fill={color} />
        <text x={plotW + 8} y={tagY(last.c) + 4} fontSize={11} fontWeight={600} fill="#fff">
          {fmt(last.c)}
        </text>

        {/* Volume */}
        {bars.map((b, i) => {
          const bw = Math.max((plotW / bars.length) * 0.7, 1)
          const h = (b.v / calc.maxV) * VOL_H
          return (
            <rect
              key={b.t}
              x={calc.x(i) - bw / 2}
              y={H + VOL_H - h}
              width={bw}
              height={h}
              className="fill-muted-foreground"
              opacity={hover === i ? 0.9 : 0.35}
            />
          )
        })}

        {/* X labels */}
        {calc.xTickIdx.map((i) => (
          <text
            key={i}
            x={Math.min(Math.max(calc.x(i), 24), plotW - 24)}
            y={H + VOL_H + 16}
            fontSize={11}
            textAnchor="middle"
            className="fill-muted-foreground"
          >
            {xLabel(bars[i].t, range)}
          </text>
        ))}

        {/* Crosshair */}
        {hb && hover != null && (
          <g>
            <line
              x1={calc.x(hover)}
              x2={calc.x(hover)}
              y1={0}
              y2={H + VOL_H}
              stroke="currentColor"
              className="text-muted-foreground"
              strokeDasharray="3 3"
            />
            <circle cx={calc.x(hover)} cy={calc.y(hb.c)} r={4} fill={color} stroke="#fff" strokeWidth={1.5} />
          </g>
        )}
      </svg>
    </div>
  )
}
