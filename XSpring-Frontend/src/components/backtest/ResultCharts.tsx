import { useMemo, useState } from "react"

// กราฟเสริมผลลัพธ์: ผลตอบแทนสะสม (สลับ linear/log + เลื่อนเมาส์ดูค่า), Drawdown, ตารางผลรายเดือน
// ใช้ข้อมูลจาก result.series เท่านั้น (ไม่ต้องเพิ่ม API) — ไฟล์ใหม่ ไม่แตะโค้ด Backtest เดิม
type Point = { date: string; portfolio: number; buy_hold: number; benchmark: number }
type Key = "portfolio" | "buy_hold" | "benchmark"

const card = "rounded-xl border bg-card p-5"
const LINES: { key: Key; name: string; color: string; dash?: string; w: number }[] = [
  { key: "portfolio", name: "พอร์ตที่ทดสอบ", color: "#38bdf8", w: 2 },
  { key: "buy_hold", name: "Buy-and-Hold", color: "#f59e0b", w: 1.5 },
  { key: "benchmark", name: "S&P 500 (Price)", color: "#a1a1aa", dash: "5 3", w: 1.5 },
]
const pct = (v: number, d = 1) => `${(v * 100).toFixed(d)}%`
const W = 800, P = { l: 52, r: 12, t: 10, b: 22 }

function useHover(n: number) {
  const [i, setI] = useState<number | null>(null)
  const onMove = (e: { clientX: number; currentTarget: { getBoundingClientRect: () => { left: number; width: number } } }) => {
    const r = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * W
    const f = (px - P.l) / (W - P.l - P.r)
    setI(Math.max(0, Math.min(n - 1, Math.round(f * (n - 1)))))
  }
  return { i, onMove, onLeave: () => setI(null) }
}

function drawdowns(series: Point[], key: Key): number[] {
  let peak = 1
  return series.map((s) => {
    const v = 1 + s[key]
    if (v > peak) peak = v
    return v / peak - 1
  })
}

function Legend() {
  return (
    <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted-foreground">
      {LINES.map((l) => <span key={l.key}><i className="mr-1 inline-block h-0.5 w-4 align-middle" style={{ backgroundColor: l.color }} />{l.name}</span>)}
    </div>
  )
}

function Readout({ series, i, values }: { series: Point[]; i: number | null; values: (k: Key) => number }) {
  if (i === null) return <div className="h-5 text-xs text-muted-foreground">เลื่อนเมาส์บนกราฟเพื่อดูค่ารายวัน</div>
  return (
    <div className="flex h-5 flex-wrap gap-x-4 text-xs tabular-nums">
      <span className="text-muted-foreground">{series[i].date}</span>
      {LINES.map((l) => <span key={l.key} style={{ color: l.color }}>{l.name} {pct(values(l.key))}</span>)}
    </div>
  )
}

function EquityScaled({ series }: { series: Point[] }) {
  const [log, setLog] = useState(true)
  const h = useHover(series.length)
  const g = useMemo(() => {
    const H = 280
    const tf = (c: number) => (log ? Math.log(Math.max(1 + c, 1e-6)) : c)
    let lo = Infinity, hi = -Infinity
    for (const s of series) for (const l of LINES) { const v = tf(s[l.key]); lo = Math.min(lo, v); hi = Math.max(hi, v) }
    lo = Math.min(lo, tf(0)); hi = Math.max(hi, tf(0))
    const span = hi - lo || 1
    const x = (i: number) => P.l + (i / Math.max(series.length - 1, 1)) * (W - P.l - P.r)
    const y = (v: number) => P.t + (1 - (v - lo) / span) * (H - P.t - P.b)
    const path = (k: Key) => series.map((s, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(tf(s[k])).toFixed(1)}`).join(" ")
    // แกน: linear = 5 ขีดเท่ากัน ; log = ขีดที่ผลตอบแทน 0%, +100%, +300% ... (เท่าตัว)
    const ticks: { label: string; y: number }[] = []
    if (log) {
      const mults = [0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 50, 100, 200]
      for (const m of mults) { const v = Math.log(m); if (v >= lo - 1e-9 && v <= hi + 1e-9) ticks.push({ label: `×${m}`, y: y(v) }) }
    } else {
      for (let n = 0; n <= 4; n++) { const v = lo + (span * n) / 4; ticks.push({ label: `${(v * 100).toFixed(0)}%`, y: y(v) }) }
    }
    return { H, x, y, path: { portfolio: path("portfolio"), buy_hold: path("buy_hold"), benchmark: path("benchmark") }, ticks, y0: y(tf(0)) }
  }, [series, log])
  return (
    <div className={card}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">ผลตอบแทนสะสม {log ? "(แกน log — เทียบอัตราการเติบโตได้ตรง)" : "(แกนเส้นตรง)"}</h3>
        <div className="inline-flex overflow-hidden rounded-md border text-xs">
          {([true, false] as const).map((m) => (
            <button key={String(m)} type="button" onClick={() => setLog(m)} className={`px-2.5 py-1 ${log === m ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{m ? "log" : "linear"}</button>
          ))}
        </div>
      </div>
      <Readout series={series} i={h.i} values={(k) => series[h.i ?? 0][k]} />
      <svg viewBox={`0 0 ${W} ${g.H}`} className="w-full text-muted-foreground" role="img" aria-label="ผลตอบแทนสะสม" onMouseMove={h.onMove} onMouseLeave={h.onLeave}>
        {g.ticks.map((t) => (
          <g key={t.label + t.y}>
            <line x1={P.l} x2={W - P.r} y1={t.y} y2={t.y} stroke="currentColor" strokeOpacity="0.15" />
            <text x={P.l - 6} y={t.y + 3} textAnchor="end" fontSize="10" fill="currentColor">{t.label}</text>
          </g>
        ))}
        <line x1={P.l} x2={W - P.r} y1={g.y0} y2={g.y0} stroke="currentColor" strokeOpacity="0.5" strokeDasharray="4 3" />
        {LINES.map((l) => <path key={l.key} d={g.path[l.key]} fill="none" stroke={l.color} strokeWidth={l.w} strokeDasharray={l.dash} />)}
        {h.i !== null && <line x1={g.x(h.i)} x2={g.x(h.i)} y1={P.t} y2={g.H - P.b} stroke="currentColor" strokeOpacity="0.5" />}
        <text x={P.l} y={g.H - 6} fontSize="10" fill="currentColor">{series[0]?.date}</text>
        <text x={W - P.r} y={g.H - 6} textAnchor="end" fontSize="10" fill="currentColor">{series[series.length - 1]?.date}</text>
      </svg>
      <Legend />
      {log && <p className="mt-1 text-[11px] text-muted-foreground">แกน log: ×2 = เงินโตเป็น 2 เท่าของเงินต้น (+100%) ระยะห่างเท่ากัน = อัตราการเติบโตเท่ากัน ทำให้เห็น S&amp;P 500 ไม่ถูกหุ้นที่โตแรงกลบ</p>}
    </div>
  )
}

function Drawdown({ series }: { series: Point[] }) {
  const h = useHover(series.length)
  const g = useMemo(() => {
    const H = 220
    const dd = { portfolio: drawdowns(series, "portfolio"), buy_hold: drawdowns(series, "buy_hold"), benchmark: drawdowns(series, "benchmark") }
    const lo = Math.min(-0.05, ...dd.portfolio, ...dd.buy_hold, ...dd.benchmark)
    const x = (i: number) => P.l + (i / Math.max(series.length - 1, 1)) * (W - P.l - P.r)
    const y = (v: number) => P.t + (v / lo) * (H - P.t - P.b)           // 0 อยู่บนสุด
    const path = (a: number[]) => a.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")
    const area = `${path(dd.portfolio)} L${x(series.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`
    const ticks = [0, 1, 2, 3, 4].map((n) => { const v = (lo * n) / 4; return { v, y: y(v) } })
    return { H, dd, x, area, ticks, p: { portfolio: path(dd.portfolio), buy_hold: path(dd.buy_hold), benchmark: path(dd.benchmark) } }
  }, [series])
  return (
    <div className={card}>
      <h3 className="mb-2 text-sm font-medium">Drawdown (ลึกจากจุดสูงสุดเดิมแค่ไหน)</h3>
      <Readout series={series} i={h.i} values={(k) => g.dd[k][h.i ?? 0]} />
      <svg viewBox={`0 0 ${W} ${g.H}`} className="w-full text-muted-foreground" role="img" aria-label="Drawdown" onMouseMove={h.onMove} onMouseLeave={h.onLeave}>
        {g.ticks.map((t) => (
          <g key={t.v}>
            <line x1={P.l} x2={W - P.r} y1={t.y} y2={t.y} stroke="currentColor" strokeOpacity="0.15" />
            <text x={P.l - 6} y={t.y + 3} textAnchor="end" fontSize="10" fill="currentColor">{(t.v * 100).toFixed(0)}%</text>
          </g>
        ))}
        <path d={g.area} fill="#38bdf8" fillOpacity="0.18" />
        <path d={g.p.benchmark} fill="none" stroke="#a1a1aa" strokeWidth="1.2" strokeDasharray="5 3" />
        <path d={g.p.buy_hold} fill="none" stroke="#f59e0b" strokeWidth="1.2" />
        <path d={g.p.portfolio} fill="none" stroke="#38bdf8" strokeWidth="1.8" />
        {h.i !== null && <line x1={g.x(h.i)} x2={g.x(h.i)} y1={P.t} y2={g.H - P.b} stroke="currentColor" strokeOpacity="0.5" />}
      </svg>
      <Legend />
    </div>
  )
}

const MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

function Monthly({ series }: { series: Point[] }) {
  const [key, setKey] = useState<Key>("portfolio")
  const rows = useMemo(() => {
    // ผลรายเดือน = มูลค่าปลายเดือน / มูลค่าปลายเดือนก่อนหน้า − 1 (เดือนแรกเทียบเงินต้น) ; เดือนแรก/ท้ายอาจไม่เต็มเดือน
    const last = new Map<string, number>()
    for (const s of series) last.set(s.date.slice(0, 7), 1 + s[key])
    const keys = [...last.keys()].sort()
    const byYear = new Map<number, (number | null)[]>()
    let prev = 1
    for (const k of keys) {
      const v = last.get(k) as number
      const y = Number(k.slice(0, 4)), m = Number(k.slice(5, 7)) - 1
      if (!byYear.has(y)) byYear.set(y, Array(12).fill(null))
      ;(byYear.get(y) as (number | null)[])[m] = v / prev - 1
      prev = v
    }
    return [...byYear.entries()].map(([y, ms]) => {
      const tot = ms.reduce<number>((a, x) => (x === null ? a : a * (1 + x)), 1) - 1
      return { y, ms, tot }
    })
  }, [series, key])
  const cell = (v: number | null) => {
    if (v === null) return {}
    const a = Math.min(Math.abs(v) / 0.12, 1) * 0.55 + 0.08
    return { backgroundColor: v >= 0 ? `rgba(16,185,129,${a})` : `rgba(239,68,68,${a})` }
  }
  return (
    <div className={card}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">ผลรายเดือน</h3>
        <div className="inline-flex overflow-hidden rounded-md border text-xs">
          {LINES.map((l) => (
            <button key={l.key} type="button" onClick={() => setKey(l.key)} className={`px-2.5 py-1 ${key === l.key ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{l.name}</button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-separate border-spacing-0.5 text-[11px] tabular-nums">
          <thead className="text-muted-foreground">
            <tr><th className="text-left font-normal">ปี</th>{MONTHS.map((m) => <th key={m} className="font-normal">{m}</th>)}<th className="font-normal">รวมปี</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.y}>
                <td className="pr-2 text-muted-foreground">{r.y}</td>
                {r.ms.map((v, i) => <td key={i} className="rounded-sm px-1 py-1 text-center" style={cell(v)}>{v === null ? "" : (v * 100).toFixed(1)}</td>)}
                <td className="rounded-sm px-1 py-1 text-center font-medium" style={cell(r.tot)}>{(r.tot * 100).toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">หน่วย % · เดือนแรกและเดือนสุดท้ายอาจไม่เต็มเดือน</p>
    </div>
  )
}

export default function ResultCharts({ series }: { series: Point[] }) {
  if (series.length < 2) return null
  return (
    <div className="space-y-4">
      <EquityScaled series={series} />
      <Drawdown series={series} />
      <Monthly series={series} />
    </div>
  )
}
