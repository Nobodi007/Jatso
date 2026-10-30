import { useEffect, useMemo, useState } from "react"

export interface DonutPosition {
  symbol: string
  qty: number
  avg_cost: number
  last: number
  market_value: number
  unrealized_pnl: number
  unrealized_pct: number
}

interface PositionsDonutProps {
  positions: DonutPosition[]
  usd: (n: number) => string
  sUsd: (n: number) => string
  nf: (n: number, digits: number) => string
  size?: number
  strokeWidth?: number
}

const PALETTE = [
  "#10b981",
  "#3b82f6",
  "#f59e0b",
  "#a855f7",
  "#ec4899",
  "#06b6d4",
  "#84cc16",
  "#f97316",
]

const GAP = 3 // ช่องว่างระหว่างชิ้น (px)

export default function PositionsDonut({
  positions,
  usd,
  sUsd,
  nf,
  size = 240,
  strokeWidth = 28,
}: PositionsDonutProps) {
  const [hovered, setHovered] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  // เริ่ม animation หลัง mount
  useEffect(() => {
    const id = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(id)
  }, [])

  const total = useMemo(
    () => positions.reduce((s, p) => s + Math.max(p.market_value, 0), 0),
    [positions],
  )

  const radius = size / 2 - strokeWidth / 2 - 4
  const circumference = 2 * Math.PI * radius
  const center = size / 2

  const segments = useMemo(() => {
    const sorted = [...positions]
      .filter((p) => p.market_value > 0)
      .sort((a, b) => b.market_value - a.market_value)
    let acc = 0
    return sorted.map((p, i) => {
      const share = total > 0 ? p.market_value / total : 0
      const len = share * circumference
      const seg = {
        p,
        share,
        color: PALETTE[i % PALETTE.length],
        len,
        offset: acc,
      }
      acc += len
      return seg
    })
  }, [positions, total, circumference])

  if (segments.length === 0) {
    return (
      <p className="py-6 text-sm text-muted-foreground">ยังไม่มีหุ้นที่ถืออยู่</p>
    )
  }

  const active = segments.find((s) => s.p.symbol === hovered) ?? null
  const pnlClass = (n: number) =>
    n >= 0 ? "text-emerald-400" : "text-rose-400"

  return (
    <div className="flex flex-col items-center gap-6 md:flex-row md:items-center md:gap-10">
      {/* ===== Donut ===== */}
      <div
        className="relative shrink-0 text-foreground"
        style={{ width: size, height: size }}
        onMouseLeave={() => setHovered(null)}
      >
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <g transform={`rotate(-90 ${center} ${center})`}>
            <circle
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke="currentColor"
              strokeOpacity={0.08}
              strokeWidth={strokeWidth}
            />
            {segments.map((s, i) => {
              const gap = segments.length > 1 ? GAP : 0
              const dash = Math.max(s.len - gap, 0.5)
              const isActive = active?.p.symbol === s.p.symbol
              return (
                <circle
                  key={s.p.symbol}
                  cx={center}
                  cy={center}
                  r={radius}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={isActive ? strokeWidth + 6 : strokeWidth}
                  strokeDasharray={
                    ready ? `${dash} ${circumference - dash}` : `0 ${circumference}`
                  }
                  strokeDashoffset={-s.offset}
                  opacity={active && !isActive ? 0.45 : 1}
                  style={{
                    transition: `stroke-dasharray 0.8s ease-out ${i * 0.06}s, stroke-width 0.2s, opacity 0.2s`,
                    cursor: "pointer",
                  }}
                  onMouseEnter={() => setHovered(s.p.symbol)}
                />
              )
            })}
          </g>
        </svg>

        {/* ข้อความกลางวง */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          {active ? (
            <>
              <p className="text-sm font-medium text-muted-foreground">
                {active.p.symbol}
              </p>
              <p className="text-2xl font-bold">{usd(active.p.market_value)}</p>
              <p className="text-sm text-muted-foreground">
                {nf(active.share * 100, 1)}% ของหุ้นที่ถือ
              </p>
              <p className={`text-sm font-medium ${pnlClass(active.p.unrealized_pnl)}`}>
                {sUsd(active.p.unrealized_pnl)} ({nf(active.p.unrealized_pct, 2)}%)
              </p>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-muted-foreground">
                มูลค่าหุ้นที่ถือ
              </p>
              <p className="text-2xl font-bold">{usd(total)}</p>
              <p className="text-sm text-muted-foreground">
                {segments.length} ตัว
              </p>
            </>
          )}
        </div>
      </div>

      {/* ===== Legend ===== */}
      <ul className="w-full flex-1 divide-y divide-border/50">
        {segments.map((s) => {
          const isActive = active?.p.symbol === s.p.symbol
          return (
            <li
              key={s.p.symbol}
              onMouseEnter={() => setHovered(s.p.symbol)}
              onMouseLeave={() => setHovered(null)}
              className={`flex cursor-pointer items-center justify-between gap-3 rounded-md px-2 py-3 transition-colors ${
                isActive ? "bg-muted/60" : ""
              }`}
            >
              <div className="flex items-center gap-3">
                <span
                  className="h-3 w-3 shrink-0 rounded-full"
                  style={{ backgroundColor: s.color }}
                />
                <div>
                  <p className="text-sm font-semibold">{s.p.symbol}</p>
                  <p className="text-xs text-muted-foreground">
                    {nf(s.p.qty, 0)} หุ้น · ทุน {usd(s.p.avg_cost)} · ล่าสุด {usd(s.p.last)}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold">
                  {nf(s.share * 100, 1)}%
                  <span className="ml-2 font-normal text-muted-foreground">
                    {usd(s.p.market_value)}
                  </span>
                </p>
                <p className={`text-xs ${pnlClass(s.p.unrealized_pnl)}`}>
                  {sUsd(s.p.unrealized_pnl)} · {nf(s.p.unrealized_pct, 2)}%
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
