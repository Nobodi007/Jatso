import { useState } from "react"
import type { PointerEvent as RPointerEvent, ReactNode } from "react"
import { InfoTip } from "./InfoTip"
import { dailyFromCumulative, histogram, labelIndexes, linePath, nearestIndex, niceTicks } from "./chartMath"
import type { Concentration, RM, RiskFree, RiskResult } from "./riskTypes"

/* แผงความเสี่ยงของ Backtest Lab — หน้าตา/สูตรอ่านเหมือน Risk Center แต่เป็นไฟล์ของ Lab เอง (ไม่ import จากโค้ดเดิม)
   ใช้: <RiskPanel result={run.result} />  (ส่ง Result ของคุณได้ตรง ๆ) */

/* ───────── helpers ───────── */
const MIN_HIST = 20
const pctS = (v: number | null | undefined, d = 2, sign = false) =>
  v == null || !Number.isFinite(v) ? "—" : `${sign && v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`
const ppS = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)} pp`)
const num2 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(2))
const usd = (v: number | null | undefined, sign = false) =>
  v == null || !Number.isFinite(v)
    ? "—"
    : `${sign && v > 0 ? "+" : ""}${v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })}`
const toneCls = (v: number | null | undefined) => (v == null || v === 0 ? "text-foreground" : v > 0 ? "text-emerald-500" : "text-rose-500")
const why = (m?: RM) =>
  m && m.value == null ? (m.status === "unavailable" ? "ไม่มีค่า (ต้องมี risk-free/benchmark)" : `ข้อมูลยังไม่พอ${m.n_obs != null ? ` (มี ${m.n_obs} วัน)` : ""}`) : m?.status === "limited_sample" ? "ตัวอย่างน้อย (<250 วัน)" : undefined

export function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-3xl border border-border bg-card p-5">{children}</div>
}
export function Tag({ children, warn = false }: { children: ReactNode; warn?: boolean }) {
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs ${warn ? "bg-amber-500/10 text-amber-500" : "bg-muted text-muted-foreground"}`}>{children}</span>
}
function Progress({ have, need, unit = "วัน" }: { have: number; need: number; unit?: string }) {
  const w = Math.max(0, Math.min(1, need > 0 ? have / need : 0)) * 100
  return (
    <div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-muted-foreground/60" style={{ width: `${w}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground tabular-nums">มีข้อมูล {have} จาก {need} {unit}</p>
    </div>
  )
}
export function Stat({ label, value, cls = "", note, help }: { label: string; value: string; cls?: string; note?: string; help?: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">
        {label}
        {help && <InfoTip k={help} />}
      </p>
      <p className={`mt-1 text-xl font-medium tabular-nums ${cls}`}>{value}</p>
      {note && <p className="mt-0.5 text-[11px] text-muted-foreground">{note}</p>}
    </div>
  )
}
function Bar({ value, max, good }: { value: number; max: number; good: boolean }) {
  const w = max > 0 ? Math.min(Math.abs(value) / max, 1) * 100 : 0
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${good ? "bg-emerald-500" : "bg-rose-500"}`} style={{ width: `${w}%` }} />
    </div>
  )
}

/* ───────── line chart (SVG ล้วน เหมือนของ Risk Center) ───────── */
interface Line { name: string; values: (number | null)[]; stroke: string; swatch: string; fill: string }

export function LineChart({ dates, lines, fmt, zero = false, label }: { dates: string[]; lines: Line[]; fmt: (v: number | null) => string; zero?: boolean; label: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const n = dates.length
  const all = lines.flatMap((l) => l.values).filter((v): v is number => v != null && Number.isFinite(v))
  if (n < 2 || all.length === 0) return null
  const W = 600, H = 190, PL = 46, PR = 8, PT = 8, PB = 20
  let lo = Math.min(...all), hi = Math.max(...all)
  if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0) }
  if (hi - lo < 1e-9) { lo -= 0.005; hi += 0.005 }
  const pad = (hi - lo) * 0.08
  lo -= pad; hi += pad
  const ticks = niceTicks(lo, hi, 4)
  const sx = (i: number) => PL + (i / (n - 1)) * (W - PL - PR)
  const sy = (v: number) => PT + (1 - (v - lo) / (hi - lo)) * (H - PT - PB)
  const xl = labelIndexes(n, 4)
  const onMove = (e: RPointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    if (r.width <= 0) return
    setHover(nearestIndex((((e.clientX - r.left) / r.width) * W - PL) / (W - PL - PR), n))
  }
  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {lines.map((l) => (
          <span key={l.name} className="inline-flex items-center gap-1.5">
            <span className={`inline-block size-2 rounded-full ${l.swatch}`} />
            {l.name}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-48 w-full touch-pan-y" role="img" aria-label={label} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PL} x2={W - PR} y1={sy(t)} y2={sy(t)} className="stroke-border" strokeWidth={0.5} />
            <text x={PL - 6} y={sy(t) + 3} textAnchor="end" fontSize={10} className="fill-muted-foreground">{fmt(t)}</text>
          </g>
        ))}
        {lo < 0 && hi > 0 && <line x1={PL} x2={W - PR} y1={sy(0)} y2={sy(0)} className="stroke-muted-foreground" strokeWidth={0.8} strokeDasharray="3 3" />}
        {xl.map((i) => (
          <text key={i} x={sx(i)} y={H - 5} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} fontSize={10} className="fill-muted-foreground">{dates[i]}</text>
        ))}
        {lines.map((l) => (
          <path key={l.name} d={linePath(l.values.map((y, i) => ({ x: i, y })), sx, sy)} fill="none" className={l.stroke} strokeWidth={1.6} strokeLinejoin="round" />
        ))}
        {hover != null && (
          <g>
            <line x1={sx(hover)} x2={sx(hover)} y1={PT} y2={H - PB} className="stroke-muted-foreground" strokeWidth={0.8} />
            {lines.map((l) => {
              const v = l.values[hover]
              return v == null ? null : <circle key={l.name} cx={sx(hover)} cy={sy(v)} r={3} className={l.fill} />
            })}
          </g>
        )}
      </svg>
      <p className="mt-1 min-h-4 text-xs text-muted-foreground tabular-nums">
        {hover != null ? `${dates[hover]} · ${lines.map((l) => `${l.name} ${fmt(l.values[hover])}`).join(" · ")}` : `${dates[0]} → ${dates[n - 1]} · เลื่อนเมาส์/นิ้วบนกราฟเพื่อดูค่ารายวัน`}
      </p>
    </div>
  )
}

/* ───────── 1) ผลตอบแทนปรับตามความเสี่ยง ───────── */
function rfTag(rf?: RiskFree) {
  if (!rf) return null
  if (rf.status === "ok")
    return <Tag>{rf.source === "tbill_3m" ? `Risk-free: T-bill 3 เดือน เฉลี่ย ${pctS(rf.avg_annual, 2)}/ปี` : `Risk-free: ค่าคงที่ ${pctS(rf.avg_annual, 2)}/ปี`}</Tag>
  if (rf.status === "not_set") return <Tag warn>ไม่ได้ระบุ risk-free · Sharpe/Alpha ไม่มีค่า</Tag>
  return <Tag warn>ดึง risk-free (T-bill) ไม่ได้ · Sharpe/Alpha ไม่มีค่า</Tag>
}

function RiskAdjustedSection({ r }: { r: RiskResult }) {
  const ra = r.analysis?.risk_adjusted ?? {}
  const pf = r.analysis?.performance ?? {}
  const items: { label: string; m?: RM; f: (v: number | null | undefined) => string; help: string; note?: string }[] = [
    { label: "Sharpe", m: ra.sharpe, f: num2, help: "sharpe" },
    { label: "Sortino", m: ra.sortino, f: num2, help: "sortino" },
    { label: "Calmar", m: ra.calmar, f: num2, help: "calmar" },
    { label: "Information ratio", m: ra.information_ratio, f: num2, help: "information_ratio" },
    { label: "Jensen's alpha (ต่อปี)", m: ra.jensens_alpha, f: (v) => pctS(v, 2, true), help: "jensens_alpha", note: ra.alpha_t_stat?.value != null ? `t = ${num2(ra.alpha_t_stat.value)}` : undefined },
    { label: "Beta", m: pf.beta, f: num2, help: "beta" },
    { label: "Treynor", m: ra.treynor, f: (v) => pctS(v, 2, true), help: "treynor" },
    { label: "Tracking error", m: ra.tracking_error, f: (v) => pctS(v, 2), help: "tracking_error" },
    { label: "Downside beta", m: ra.downside_beta, f: num2, help: "downside_beta" },
    { label: "Hit rate", m: pf.hit_rate, f: (v) => pctS(v, 1), help: "hit_rate" },
    { label: "Up capture", m: pf.up_capture, f: (v) => pctS(v, 0), help: "up_capture" },
    { label: "Down capture", m: pf.down_capture, f: (v) => pctS(v, 0), help: "down_capture" },
  ]
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">ผลตอบแทนปรับตามความเสี่ยง</h2>
        {rfTag(r.risk_free)}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        {items.map((it) => (
          <Stat key={it.label} label={it.label} value={it.f(it.m?.value)} note={why(it.m) ?? it.note} help={it.help} />
        ))}
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        สูตรเดียวกับ Risk Center (ตัวอย่างรายวัน, ×√252) · ตัวที่ต้องการ risk-free จะไม่มีค่าถ้าไม่ได้ระบุหรือดึงอัตราไม่ได้ ระบบไม่เดาค่าให้
      </p>
    </Panel>
  )
}

/* ───────── 2) Drawdown + VaR/ES + การกระจาย ───────── */
function DrawdownSection({ r }: { r: RiskResult }) {
  const t = r.analysis?.tail
  const dd = t?.drawdown_series ?? []
  const ep = t?.drawdown_episode
  const rets = dailyFromCumulative(r.series.map((s) => s.portfolio))
  const n = rets.length
  const bins = n >= MIN_HIST ? histogram(rets) : []
  const varV = t?.var_95?.value != null ? -t.var_95.value : null
  const esV = t?.es_95?.value != null ? -t.es_95.value : null
  const W = 600, H = 170, PL = 8, PR = 8, PT = 14, PB = 22
  const lo = bins.length ? Math.min(bins[0].lo, varV ?? Infinity, esV ?? Infinity) : 0
  const hi = bins.length ? Math.max(bins[bins.length - 1].hi, 1e-9) : 1
  const span = Math.max(hi - lo, 1e-9)
  const sx = (v: number) => PL + ((v - lo) / span) * (W - PL - PR)
  const maxC = Math.max(...bins.map((b) => b.count), 1)
  const sy = (c: number) => H - PB - (c / maxC) * (H - PB - PT)
  return (
    <Panel>
      <h2 className="text-base font-medium">Drawdown และความเสี่ยงขาลง</h2>
      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Max drawdown" value={pctS(t?.max_drawdown?.value, 2)} cls={toneCls(t?.max_drawdown?.value)} help="max_drawdown" note={why(t?.max_drawdown)} />
        <Stat label="Drawdown ปัจจุบัน" value={pctS(t?.current_drawdown?.value, 2)} cls={toneCls(t?.current_drawdown?.value)} help="current_drawdown" />
        <Stat label="จมน้ำนานสุด" value={t?.longest_underwater_trading_days != null ? `${t.longest_underwater_trading_days} วัน` : "—"} help="longest_underwater" />
        <Stat label="Downside deviation" value={pctS(t?.downside_deviation?.value, 2)} help="downside_deviation" note={why(t?.downside_deviation)} />
        <Stat label="VaR 95% (1 วัน)" value={pctS(t?.var_95?.value, 2)} help="var_95" note={why(t?.var_95)} />
        <Stat label="ES 95% (1 วัน)" value={pctS(t?.es_95?.value, 2)} help="es_95" note={why(t?.es_95)} />
      </div>
      {ep && (
        <p className="mt-3 text-xs text-muted-foreground tabular-nums">
          ช่วงตกลึกสุด: ยอดสูง {ep.peak_date} → ต่ำสุด {ep.trough_date} → {ep.recovery_date ? `ฟื้นกลับ ${ep.recovery_date} (ใช้ ${ep.recovery_trading_days} วันทำการจากจุดต่ำสุด)` : "ยังไม่ฟื้นกลับถึงยอดเดิมจนสิ้นสุดช่วงทดสอบ"}
        </p>
      )}
      {dd.length >= 2 && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-muted-foreground">Drawdown ของพอร์ต</p>
          <LineChart dates={dd.map((d) => d.date)} label="กราฟ drawdown" fmt={(v) => pctS(v, 1)} zero
            lines={[{ name: "Drawdown", values: dd.map((d) => d.drawdown), stroke: "stroke-rose-500", swatch: "bg-rose-500", fill: "fill-rose-500" }]} />
        </div>
      )}
      <div className="mt-5">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">การกระจายผลตอบแทนรายวัน</p>
          <Tag warn={n < 60}>{n} วัน{n < 60 ? " · ตัวอย่างน้อย" : ""}</Tag>
        </div>
        {n < MIN_HIST ? (
          <div className="rounded-2xl border border-dashed border-border p-4">
            <p className="mb-3 text-sm text-muted-foreground">ต้องมีผลตอบแทนรายวันอย่างน้อย {MIN_HIST} วัน กราฟจึงจะน่าเชื่อถือ</p>
            <Progress have={n} need={MIN_HIST} />
          </div>
        ) : (
          <>
            <svg viewBox={`0 0 ${W} ${H}`} className="h-44 w-full" role="img" aria-label="ฮิสโตแกรมผลตอบแทนรายวันของพอร์ต">
              {bins.map((b, i) => (
                <rect key={i} x={sx(b.lo) + 0.5} y={sy(b.count)} width={Math.max(sx(b.hi) - sx(b.lo) - 1, 1)} height={H - PB - sy(b.count)} className={(b.lo + b.hi) / 2 < 0 ? "fill-rose-500/60" : "fill-emerald-500/60"}>
                  <title>{`${pctS(b.lo, 2, true)} ถึง ${pctS(b.hi, 2, true)}: ${b.count} วัน`}</title>
                </rect>
              ))}
              {lo < 0 && hi > 0 && <line x1={sx(0)} x2={sx(0)} y1={PT} y2={H - PB} className="stroke-muted-foreground" strokeWidth={0.8} strokeDasharray="3 3" />}
              {varV != null && (
                <g>
                  <line x1={sx(varV)} x2={sx(varV)} y1={PT - 4} y2={H - PB} className="stroke-rose-500" strokeWidth={1.2} />
                  <text x={sx(varV)} y={PT - 5} textAnchor="middle" fontSize={10} className="fill-rose-500">VaR 95%</text>
                </g>
              )}
              {esV != null && (
                <g>
                  <line x1={sx(esV)} x2={sx(esV)} y1={PT - 4} y2={H - PB} className="stroke-amber-500" strokeWidth={1.2} strokeDasharray="4 2" />
                  <text x={sx(esV)} y={PT - 5} textAnchor="middle" fontSize={10} className="fill-amber-500">ES</text>
                </g>
              )}
              <text x={PL} y={H - 6} fontSize={10} className="fill-muted-foreground">{pctS(lo, 2, true)}</text>
              <text x={W - PR} y={H - 6} textAnchor="end" fontSize={10} className="fill-muted-foreground">{pctS(hi, 2, true)}</text>
            </svg>
            <p className="mt-2 text-xs text-muted-foreground">
              แกนนอน = ผลตอบแทนรายวัน · แกนตั้ง = จำนวนวัน · VaR/ES 95% เป็นค่าประวัติศาสตร์ 1 วัน (ไม่ใช่การพยากรณ์) · วันแรกของช่วงไม่นับในกราฟนี้
            </p>
          </>
        )}
      </div>
    </Panel>
  )
}

/* ───────── 3) Rolling ───────── */
function RollingSection({ r }: { r: RiskResult }) {
  const w = r.analysis?.rolling?.window_trading_days ?? 63
  const pts = r.analysis?.rolling?.points ?? []
  const days = r.period.trading_days
  if (pts.length < 2)
    return (
      <Panel>
        <h2 className="text-base font-medium">Rolling ความผันผวน / Beta / Sharpe</h2>
        <p className="mt-3 text-sm text-muted-foreground">กราฟ rolling ใช้หน้าต่าง {w} วันซื้อขาย ต้องมีข้อมูลอย่างน้อย {w + 1} วัน</p>
        <div className="mt-3"><Progress have={days} need={w + 1} /></div>
      </Panel>
    )
  const dates = pts.map((x) => x.date)
  const has = (k: "beta" | "sharpe") => pts.some((x) => x[k] != null)
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">Rolling ความผันผวน / Beta / Sharpe</h2>
        <Tag>หน้าต่าง {w} วันซื้อขาย</Tag>
      </div>
      <div className="mt-4">
        <p className="mb-2 text-sm text-muted-foreground">ความผันผวนต่อปี</p>
        <LineChart dates={dates} label="Rolling volatility" fmt={(v) => pctS(v, 1)} lines={[{ name: "ความผันผวน", values: pts.map((x) => x.volatility), stroke: "stroke-amber-500", swatch: "bg-amber-500", fill: "fill-amber-500" }]} />
      </div>
      {has("beta") && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-muted-foreground">Beta เทียบดัชนี</p>
          <LineChart dates={dates} label="Rolling beta" fmt={num2} lines={[{ name: "Beta", values: pts.map((x) => x.beta ?? null), stroke: "stroke-violet-500", swatch: "bg-violet-500", fill: "fill-violet-500" }]} />
        </div>
      )}
      {has("sharpe") && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-muted-foreground">Sharpe ratio (ต่อปี)</p>
          <LineChart dates={dates} label="Rolling Sharpe" fmt={num2} zero lines={[{ name: "Sharpe", values: pts.map((x) => x.sharpe ?? null), stroke: "stroke-sky-500", swatch: "bg-sky-500", fill: "fill-sky-500" }]} />
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">หน้าต่างสั้นแกว่งตามข้อมูลช่วงนั้นมาก ไม่ควรตีความเป็นแนวโน้มระยะยาว</p>
    </Panel>
  )
}

/* ───────── 4) ความกระจุกตัวและความเสี่ยงรายหุ้น ───────── */
function ConcRow({ label, c }: { label: string; c: Concentration }) {
  return (
    <tr className="border-t border-border">
      <td className="py-1.5 pr-3">{label}</td>
      <td className="py-1.5 pr-3 text-right">{num2(c.hhi.value)}</td>
      <td className="py-1.5 pr-3 text-right">{c.effective_n.value == null ? "—" : c.effective_n.value.toFixed(1)}</td>
      <td className="py-1.5 pr-3 text-right">{pctS(c.top1.value, 1)}</td>
      <td className="py-1.5 text-right">{pctS(c.top3.value, 1)}</td>
    </tr>
  )
}

function ConcentrationSection({ r }: { r: RiskResult }) {
  const ex = r.exposure
  const at = r.attribution
  if (!ex || !at) return null
  const sd = ex.static_decomposition
  const real = [...at.positions].sort((a, b) => (b.pct_of_risk ?? -1) - (a.pct_of_risk ?? -1))
  const maxR = Math.max(...real.map((p) => Math.max(p.pct_of_risk ?? 0, p.avg_weight)), 1e-9)
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">ความกระจุกตัวและความเสี่ยงรายหุ้น</h2>
        <Tag>น้ำหนักเทียบเฉพาะส่วนหุ้น ไม่รวมเงินสด</Tag>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1 pr-3 font-normal">มุมมอง<InfoTip k="hhi" /></th>
              <th className="py-1 pr-3 text-right font-normal">HHI</th>
              <th className="py-1 pr-3 text-right font-normal">หุ้นเทียบเท่า</th>
              <th className="py-1 pr-3 text-right font-normal">ตัวใหญ่สุด</th>
              <th className="py-1 text-right font-normal">Top 3</th>
            </tr>
          </thead>
          <tbody>
            <ConcRow label="น้ำหนักเป้าหมาย" c={ex.target} />
            <ConcRow label="ถือจริงเฉลี่ย" c={ex.average_held} />
            <ConcRow label="ปลายช่วง" c={ex.final} />
          </tbody>
        </table>
      </div>

      <div className="mt-5">
        <p className="mb-1 text-sm text-muted-foreground">
          สัดส่วนความเสี่ยงที่เกิดจริง เทียบน้ำหนักที่ถือเฉลี่ย<InfoTip k="pct_of_risk_realized" />
        </p>
        {at.risk_status !== "ok" ? (
          <div className="mt-2 rounded-2xl border border-dashed border-border p-4">
            <p className="mb-3 text-sm text-muted-foreground">ต้องมีอย่างน้อย 60 วันซื้อขายจึงแยกความเสี่ยงได้</p>
            <Progress have={at.n_obs} need={60} />
          </div>
        ) : (
          <ul className="mt-3 space-y-3">
            {real.map((p) => (
              <li key={p.symbol}>
                <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                  <span className="font-medium">{p.symbol}</span>
                  <span className="tabular-nums text-muted-foreground">
                    น้ำหนักเฉลี่ย {pctS(p.avg_weight, 1)} → ความเสี่ยง <span className="text-foreground">{pctS(p.pct_of_risk, 1)}</span>
                  </span>
                </div>
                <Bar value={p.avg_weight} max={maxR} good />
                <div className="mt-1"><Bar value={p.pct_of_risk ?? 0} max={maxR} good={false} /></div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted-foreground">แถบบน = น้ำหนักเฉลี่ย (เขียว) · แถบล่าง = สัดส่วนความเสี่ยง (แดง) · รวมทุกตัว = 100%</p>
      </div>

      <div className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">การแยกความเสี่ยงตามน้ำหนักเป้าหมาย (ถือคงที่)<InfoTip k="static_risk" /></p>
          {sd.portfolio_volatility.value != null && <Tag>ผันผวนพอร์ต {pctS(sd.portfolio_volatility.value, 1)}/ปี</Tag>}
        </div>
        {sd.contributions.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">{why(sd.portfolio_volatility) ?? "ข้อมูลยังไม่พอ"}</p>
        ) : (
          <>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-sm tabular-nums">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="py-1 pr-3 font-normal">หุ้น</th>
                    <th className="py-1 pr-3 text-right font-normal">น้ำหนัก</th>
                    <th className="py-1 pr-3 text-right font-normal">ผันผวน</th>
                    <th className="py-1 pr-3 text-right font-normal">MCR<InfoTip k="mcr" /></th>
                    <th className="py-1 text-right font-normal">% ความเสี่ยง</th>
                  </tr>
                </thead>
                <tbody>
                  {sd.contributions.map((c) => (
                    <tr key={c.symbol} className="border-t border-border">
                      <td className="py-1.5 pr-3 font-medium">{c.symbol}</td>
                      <td className="py-1.5 pr-3 text-right">{pctS(c.weight_nav, 1)}</td>
                      <td className="py-1.5 pr-3 text-right">{pctS(c.volatility, 1)}</td>
                      <td className="py-1.5 pr-3 text-right">{num2(c.mcr)}</td>
                      <td className="py-1.5 text-right">{pctS(c.pct_of_risk, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-4 md:grid-cols-3">
              <Stat label="Diversification ratio" value={num2(sd.diversification_ratio?.value)} note="Σ wᵢσᵢ / σₚ (มากกว่า = กระจายความเสี่ยงได้ดีกว่า)" />
              <Stat label="Correlation เฉลี่ยคู่หุ้น" value={num2(sd.avg_pairwise_correlation?.value)} />
              {sd.top_pairs && sd.top_pairs[0] && (
                <Stat label="คู่ที่ขยับไปทางเดียวกันสุด" value={`${sd.top_pairs[0].a}/${sd.top_pairs[0].b}`} note={`correlation ${num2(sd.top_pairs[0].correlation)}`} />
              )}
            </div>
          </>
        )}
        {sd.excluded.length > 0 && <p className="mt-2 text-xs text-amber-500">ไม่รวมในการคำนวณ: {sd.excluded.map((e) => `${e.symbol} (${e.reason})`).join(", ")}</p>}
        <p className="mt-2 text-xs text-muted-foreground">{ex.note}</p>
      </div>
    </Panel>
  )
}

/* ───────── 5) ส่วนร่วมต่อผลตอบแทนรายหุ้น ───────── */
function AttributionSection({ r }: { r: RiskResult }) {
  const at = r.attribution
  if (!at) return null
  const rows = at.positions
  const max = Math.max(...rows.map((p) => Math.abs(p.contribution)), 1e-9)
  const ok = Math.abs(at.totals.reconciliation_error) < 0.01
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">กำไร/ขาดทุนแยกรายหุ้น<InfoTip k="pnl_attribution" /></h2>
        <Tag warn={!ok}>{ok ? "รวมกลับเท่ากำไรพอร์ตพอดี" : `ผลรวมคลาดเคลื่อน ${usd(at.totals.reconciliation_error)}`}</Tag>
      </div>
      <ul className="mt-4 space-y-3">
        {rows.map((p) => (
          <li key={p.symbol}>
            <div className="mb-1 flex items-center justify-between gap-2 text-sm">
              <span><span className="font-medium">{p.symbol}</span> <span className="text-xs text-muted-foreground">ซื้อขาย {p.trade_count} ครั้ง · ปลายช่วง {pctS(p.final_weight, 1)}</span></span>
              <span className={`tabular-nums ${toneCls(p.net_pnl)}`}>{usd(p.net_pnl, true)} <span className="text-xs">({ppS(p.contribution)})</span></span>
            </div>
            <Bar value={p.contribution} max={max} good={p.contribution >= 0} />
          </li>
        ))}
      </ul>
      <div className="mt-4 grid grid-cols-2 gap-4 border-t border-border pt-4 md:grid-cols-4">
        <Stat label="รวมทุกหุ้น" value={usd(at.totals.net_pnl, true)} cls={toneCls(at.totals.net_pnl)} note={`ผลตอบแทนรวม ${pctS(at.totals.total_return, 2, true)}`} />
        <Stat label="ค่าคอมมิชชัน" value={usd(at.totals.commission)} />
        <Stat label="Slippage" value={usd(at.totals.slippage_cost)} />
        <Stat label="ต้นทุนรวม" value={usd(at.totals.commission + at.totals.slippage_cost)} note="หักอยู่ในกำไรแต่ละตัวแล้ว" />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        ส่วนร่วม (pp) = กำไรของหุ้นตัวนั้น ÷ เงินต้น บวกกันได้เท่าผลตอบแทนรวม (เงินต้นคงที่ ไม่ใช่ผลตอบแทนถ่วงเวลา) · เงินสดส่วนที่ไม่ได้ลงทุนไม่มีดอกเบี้ยจึงไม่มีส่วนร่วม
      </p>
    </Panel>
  )
}

export default function RiskPanel({ result }: { result: RiskResult }) {
  return (
    <div className="space-y-4">
      <RiskAdjustedSection r={result} />
      <DrawdownSection r={result} />
      <RollingSection r={result} />
      <ConcentrationSection r={result} />
      <AttributionSection r={result} />
    </div>
  )
}
