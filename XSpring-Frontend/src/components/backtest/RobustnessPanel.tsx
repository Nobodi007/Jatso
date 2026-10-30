import { useMemo, useState } from "react"

// Monte Carlo + ทดสอบความนิ่ง — ไฟล์ใหม่ ไม่แตะโค้ด Backtest เดิม (เรียก API ของ Backtest Lab เท่านั้น)
type Props = { runId: string; apiBase: string; getToken: () => string | null }

type Dist = { p5: number; p25: number; p50: number; p75: number; p95: number; mean: number }
type MC = {
  params: { sims: number; horizon_days: number; horizon_years: number; block_days: number; seed: number; method: string }
  final_return: Dist
  cagr: Dist
  max_drawdown: Dist
  benchmark_final_return: Dist
  prob: { loss: number; beat_benchmark: number; drawdown_worse_20: number; drawdown_worse_30: number; drawdown_worse_50: number }
  fan: { x: number[]; p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] }
  actual?: { final_return: number; percentile_rank: number }
  caveats: string[]
}
type Triple = { total_return: number | null; cagr: number | null; max_drawdown: number | null }
type Brief = { portfolio: Triple; buy_hold: Triple; benchmark: Triple; trade_count: number; time_in_market: number }
type Rob = {
  window_test: {
    windows: ({ start: string; end: string } & Brief)[]
    skipped: { start: string; end: string; reason: string }[]
    summary: { windows: number; positive: number; beat_benchmark: number; beat_buy_hold: number; worst_return: number | null; best_return: number | null }
  }
  sensitivity: {
    available: boolean
    reason?: string
    note?: string
    families?: Record<string, {
      label: string
      rows: ({ factor: number } & Brief)[]
      summary: { min?: number; max?: number; median?: number; beat_benchmark?: number; variants?: number; neighbor_drop?: number; fragile?: boolean }
    }>
  }
  caveats: string[]
}

const card = "rounded-xl border bg-card p-5"
const num = "w-20 rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-primary"
const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`)
const cls = (v: number | null | undefined) => (v == null ? "text-muted-foreground" : v >= 0 ? "text-emerald-500" : "text-red-500")

async function post<T>(apiBase: string, token: string | null, path: string, body: unknown): Promise<T> {
  if (!token) throw new Error("กรุณาเข้าสู่ระบบ")
  let res: Response
  try {
    res = await fetch(`${apiBase}/api/backtest-lab${path}`, {
      method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify(body),
    })
  } catch {
    throw new Error("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้")
  }
  let data: { message?: string } | null = null
  try { data = await res.json() } catch { data = null }
  if (!res.ok) throw new Error(data?.message ?? `ผิดพลาด (${res.status})`)
  return data as T
}

function Fan({ fan, days }: { fan: MC["fan"]; days: number }) {
  const W = 800, H = 280, P = { l: 52, r: 12, t: 10, b: 24 }
  const g = useMemo(() => {
    const all = [...fan.p5, ...fan.p95, 0]
    const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1
    const x = (i: number) => P.l + (fan.x[i] / Math.max(days - 1, 1)) * (W - P.l - P.r)
    const y = (v: number) => P.t + (1 - (v - lo) / span) * (H - P.t - P.b)
    const line = (a: number[]) => a.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")
    const band = (a: number[], b: number[]) =>
      `${a.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")} ` +
      `${b.map((_, k) => { const i = b.length - 1 - k; return `L${x(i).toFixed(1)},${y(b[i]).toFixed(1)}` }).join(" ")} Z`
    return {
      outer: band(fan.p5, fan.p95), inner: band(fan.p25, fan.p75), med: line(fan.p50), y0: y(0),
      ticks: [0, 1, 2, 3, 4].map((n) => { const v = lo + (span * n) / 4; return { v, y: y(v) } }),
    }
  }, [fan, days])
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full text-muted-foreground" role="img" aria-label="ช่วงผลตอบแทนสะสมจากการจำลอง">
      {g.ticks.map((t) => (
        <g key={t.v}>
          <line x1={P.l} x2={W - P.r} y1={t.y} y2={t.y} stroke="currentColor" strokeOpacity="0.15" />
          <text x={P.l - 6} y={t.y + 3} textAnchor="end" fontSize="10" fill="currentColor">{(t.v * 100).toFixed(0)}%</text>
        </g>
      ))}
      <line x1={P.l} x2={W - P.r} y1={g.y0} y2={g.y0} stroke="currentColor" strokeOpacity="0.5" strokeDasharray="4 3" />
      <path d={g.outer} fill="#38bdf8" fillOpacity="0.15" />
      <path d={g.inner} fill="#38bdf8" fillOpacity="0.3" />
      <path d={g.med} fill="none" stroke="#38bdf8" strokeWidth="2" />
      <text x={P.l} y={H - 6} fontSize="10" fill="currentColor">วันที่ 0</text>
      <text x={W - P.r} y={H - 6} textAnchor="end" fontSize="10" fill="currentColor">วันที่ {days}</text>
    </svg>
  )
}

function Tile({ label, value, c = "" }: { label: string; value: string; c?: string }) {
  return (
    <div className="rounded-lg border bg-muted/20 px-3 py-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold tabular-nums ${c}`}>{value}</div>
    </div>
  )
}

function MonteCarlo({ runId, apiBase, getToken }: Props) {
  const [sims, setSims] = useState("2000")
  const [block, setBlock] = useState("21")
  const [years, setYears] = useState("")
  const [seed, setSeed] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [r, setR] = useState<MC | null>(null)
  const go = async () => {
    setBusy(true); setErr(null)
    try {
      const body: Record<string, number> = { sims: Number(sims), block_days: Number(block) }
      if (years.trim() !== "") body.years = Number(years)
      if (seed.trim() !== "") body.seed = Number(seed)
      setR(await post<MC>(apiBase, getToken(), `/runs/${encodeURIComponent(runId)}/montecarlo`, body))
    } catch (e) {
      setErr(e instanceof Error ? e.message : "เกิดข้อผิดพลาด")
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className={card}>
      <h3 className="text-sm font-medium">Monte Carlo — ช่วงความไม่แน่นอนของผล</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        สุ่มบล็อกผลตอบแทนรายวันที่เคยเกิดจริงมาต่อกันใหม่ เพื่อดูว่าผลที่ได้อาจกว้างแค่ไหน · <b>ไม่ใช่การพยากรณ์</b> ไม่ได้บอกว่าอนาคตจะเป็นอย่างไร
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3 text-xs text-muted-foreground">
        <label>จำนวนรอบ<input className={`${num} ml-2`} inputMode="numeric" value={sims} onChange={(e) => setSims(e.target.value)} /></label>
        <label>ความยาวบล็อก (วัน)<input className={`${num} ml-2 w-16`} inputMode="numeric" value={block} onChange={(e) => setBlock(e.target.value)} /></label>
        <label>จำลองไปข้างหน้า (ปี, ว่าง = เท่าช่วงที่ทดสอบ)<input className={`${num} ml-2 w-16`} inputMode="numeric" value={years} onChange={(e) => setYears(e.target.value)} /></label>
        <label>Seed (ว่าง = ค่าคงที่ของรันนี้)<input className={`${num} ml-2`} inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value)} /></label>
        <button type="button" disabled={busy} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50" onClick={() => void go()}>
          {busy ? "กำลังจำลอง…" : "รัน Monte Carlo"}
        </button>
      </div>
      {err && <div className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-red-500">{err}</div>}
      {r && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <Tile label="ผลตอบแทนรวม — มัธยฐาน" value={pct(r.final_return.p50)} c={cls(r.final_return.p50)} />
            <Tile label="ช่วง 5%–95%" value={`${pct(r.final_return.p5, 0)} ถึง ${pct(r.final_return.p95, 0)}`} />
            <Tile label="โอกาสขาดทุน" value={pct(r.prob.loss)} />
            <Tile label="โอกาสชนะ S&P 500" value={pct(r.prob.beat_benchmark)} />
            <Tile label="CAGR มัธยฐาน" value={pct(r.cagr.p50)} c={cls(r.cagr.p50)} />
            <Tile label="Max DD มัธยฐาน" value={pct(r.max_drawdown.p50)} c="text-red-500" />
            <Tile label="Max DD แย่ (5%)" value={pct(r.max_drawdown.p5)} c="text-red-500" />
            <Tile label="DD เกิน −30%" value={pct(r.prob.drawdown_worse_30)} />
          </div>
          <div>
            <Fan fan={r.fan} days={r.params.horizon_days} />
            <div className="mt-1 flex flex-wrap gap-4 text-xs text-muted-foreground">
              <span><i className="mr-1 inline-block h-0.5 w-4 bg-sky-400 align-middle" />มัธยฐาน</span>
              <span><i className="mr-1 inline-block h-2 w-4 bg-sky-400/30 align-middle" />25–75%</span>
              <span><i className="mr-1 inline-block h-2 w-4 bg-sky-400/15 align-middle" />5–95%</span>
            </div>
          </div>
          {r.actual && (
            <p className="text-xs text-muted-foreground">
              ผลจริงของรันนี้ {pct(r.actual.final_return)} อยู่ที่เปอร์เซ็นไทล์ {(r.actual.percentile_rank * 100).toFixed(0)} ของเส้นทางจำลอง
              (ใกล้ 50 = ผลจริงเป็นกลาง ๆ, สูงมาก = ได้ลำดับที่ดีกว่าปกติ อาจเป็นโชค)
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            S&P 500 ในการจำลองชุดเดียวกัน: มัธยฐาน {pct(r.benchmark_final_return.p50)} · {r.params.sims} รอบ · {r.params.horizon_years} ปี · บล็อก {r.params.block_days} วัน · seed {r.params.seed}
          </p>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-amber-500">{r.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

function Stability({ runId, apiBase, getToken }: Props) {
  const [k, setK] = useState("4")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [r, setR] = useState<Rob | null>(null)
  const go = async () => {
    setBusy(true); setErr(null)
    try {
      setR(await post<Rob>(apiBase, getToken(), `/runs/${encodeURIComponent(runId)}/robustness`, { windows: Number(k), sensitivity: true }))
    } catch (e) {
      setErr(e instanceof Error ? e.message : "เกิดข้อผิดพลาด")
    } finally {
      setBusy(false)
    }
  }
  const s = r?.window_test.summary
  return (
    <div className={card}>
      <h3 className="text-sm font-medium">ทดสอบความนิ่งของกฎ</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        รันกฎเดิมซ้ำ (1) แยกเป็นช่วงเวลาย่อย และ (2) ขยับพารามิเตอร์ขึ้นลง — ดูว่าผลกระจุกอยู่ช่วงเดียว หรือเกาะอยู่ที่ค่าเดียวหรือไม่ (ลักษณะของ overfit)
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3 text-xs text-muted-foreground">
        <label>จำนวนช่วง<input className={`${num} ml-2 w-14`} inputMode="numeric" value={k} onChange={(e) => setK(e.target.value)} /></label>
        <button type="button" disabled={busy} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50" onClick={() => void go()}>
          {busy ? "กำลังทดสอบ…" : "รันการทดสอบ"}
        </button>
        <span>อาจใช้เวลาครึ่งนาทีหรือมากกว่า</span>
      </div>
      {err && <div className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-red-500">{err}</div>}
      {r && s && (
        <div className="mt-4 space-y-5">
          <div>
            <div className="mb-2 text-xs text-muted-foreground">
              บวก {s.positive}/{s.windows} ช่วง · ชนะ S&P 500 {s.beat_benchmark}/{s.windows} · ชนะ Buy-and-Hold {s.beat_buy_hold}/{s.windows} · แย่สุด {pct(s.worst_return)} · ดีสุด {pct(s.best_return)}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-xs tabular-nums">
                <thead className="text-left text-muted-foreground">
                  <tr><th className="py-1 font-normal">ช่วง</th><th className="text-right font-normal">กลยุทธ์</th><th className="text-right font-normal">Buy-and-Hold</th>
                    <th className="text-right font-normal">S&P 500</th><th className="text-right font-normal">Max DD กลยุทธ์</th><th className="text-right font-normal">รอบเทรด</th></tr>
                </thead>
                <tbody>
                  {r.window_test.windows.map((w) => (
                    <tr key={w.start} className="border-t border-border">
                      <td className="py-1">{w.start} → {w.end}</td>
                      <td className={`text-right ${cls(w.portfolio.total_return)}`}>{pct(w.portfolio.total_return)}</td>
                      <td className={`text-right ${cls(w.buy_hold.total_return)}`}>{pct(w.buy_hold.total_return)}</td>
                      <td className={`text-right ${cls(w.benchmark.total_return)}`}>{pct(w.benchmark.total_return)}</td>
                      <td className="text-right text-red-500">{pct(w.portfolio.max_drawdown)}</td>
                      <td className="text-right">{w.trade_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {r.window_test.skipped.length > 0 && <p className="mt-1 text-xs text-amber-500">ข้ามบางช่วงเพราะข้อมูลไม่พอ: {r.window_test.skipped.map((x) => x.start).join(", ")}</p>}
          </div>

          {r.sensitivity.available && r.sensitivity.families ? (
            <div className="space-y-4">
              {Object.entries(r.sensitivity.families).map(([key, f]) => (
                <div key={key}>
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-medium">ขยับ{f.label}</span>
                    <span className="text-muted-foreground">ผลรวม {pct(f.summary.min)} ถึง {pct(f.summary.max)} (มัธยฐาน {pct(f.summary.median)}) · ชนะ S&P 500 {f.summary.beat_benchmark}/{f.summary.variants} แบบ</span>
                    {f.summary.fragile != null && (
                      <span className={`rounded-md border px-2 py-0.5 ${f.summary.fragile ? "border-rose-500/40 bg-rose-500/10 text-red-500" : "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"}`}>
                        {f.summary.fragile ? "ไวต่อพารามิเตอร์ (fragile)" : "ค่อนข้างนิ่ง"}
                      </span>
                    )}
                  </div>
                  <table className="w-full text-xs tabular-nums">
                    <thead className="text-left text-muted-foreground">
                      <tr><th className="py-1 font-normal">ตัวคูณ</th><th className="text-right font-normal">ผลตอบแทนรวม</th><th className="text-right font-normal">CAGR</th>
                        <th className="text-right font-normal">Max DD</th><th className="text-right font-normal">รอบเทรด</th></tr>
                    </thead>
                    <tbody>
                      {f.rows.map((x) => (
                        <tr key={x.factor} className={`border-t border-border ${x.factor === 1 ? "bg-primary/5 font-medium" : ""}`}>
                          <td className="py-1">×{x.factor}{x.factor === 1 ? " (ค่าที่ใช้)" : ""}</td>
                          <td className={`text-right ${cls(x.portfolio.total_return)}`}>{pct(x.portfolio.total_return)}</td>
                          <td className={`text-right ${cls(x.portfolio.cagr)}`}>{pct(x.portfolio.cagr)}</td>
                          <td className="text-right text-red-500">{pct(x.portfolio.max_drawdown)}</td>
                          <td className="text-right">{x.trade_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
              {r.sensitivity.note && <p className="text-xs text-muted-foreground">{r.sensitivity.note}</p>}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">ขยับพารามิเตอร์ไม่ได้: {r.sensitivity.reason}</p>
          )}
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-amber-500">{r.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

export default function RobustnessPanel(p: Props) {
  return (
    <div className="space-y-4">
      <MonteCarlo {...p} />
      <Stability {...p} />
    </div>
  )
}
