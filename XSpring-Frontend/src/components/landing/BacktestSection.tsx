import { useMemo, useRef, useState } from "react"
import { useLanguage } from "../../i18n/LanguageContext"
import type { PointerEvent } from "react"
import { CalendarClock, Check, Loader2, TrendingDown, TrendingUp, Wallet } from "lucide-react"
import type { LucideIcon } from "lucide-react"

const API_BASE_URL = "https://xspring-api.onrender.com"

type Summary = {
  final: number
  profit: number
  pct: number
  hold_final: number
  hold_pct: number
  sav_final: number
  sav_pct: number
  max_dd: number
  hold_max_dd: number
  trades: number
  cash_left: number
}

type Result = {
  asset: string
  kind: string
  freq: string
  amount: number
  start: string
  end: string
  fee_pct: number
  spread_pct: number
  dates: string[]
  strategy: number[]
  hold: number[]
  savings: number[]
  summary: Summary
}

type Kind = "lump" | "dca" | "dip" | "trend"

const ASSETS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "HBAR", "LINK", "XLM"]

const PERIODS = [
  { key: "1m", days: 30 },
  { key: "3m", days: 90 },
  { key: "6m", days: 180 },
  { key: "1y", days: 365 },
  { key: "3y", days: 365 * 3 },
  { key: "5y", days: 365 * 5 },
  { key: "custom", days: 0 },
]

const STRATEGIES: { kind: Kind; icon: LucideIcon }[] = [
  { kind: "lump", icon: Wallet },
  { kind: "dca", icon: CalendarClock },
  { kind: "dip", icon: TrendingDown },
  { kind: "trend", icon: TrendingUp },
]

// value = ค่าที่ backend รู้จัก (ห้ามแปล), key = ใช้หา label ใน translations
const FREQS = [
  { value: "รายสัปดาห์", key: "weekly" },
  { value: "รายเดือน", key: "monthly" },
]

const QUICK_AMOUNTS = [10000, 50000, 100000, 500000]

const pad2 = (n: number) => String(n).padStart(2, "0")
const iso = (d: Date) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
const daysAgo = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d
}

const signedPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`
const tone = (v: number) => (v >= 0 ? "text-emerald-500" : "text-red-500")

function useFmt() {
  const { lang } = useLanguage()
  const locale = lang === "th" ? "th-TH" : "en-US"
  return {
    locale,
    baht: (v: number) => `฿${Math.round(v).toLocaleString(locale)}`,
    signedBaht: (v: number) => `${v >= 0 ? "+" : "−"}฿${Math.abs(Math.round(v)).toLocaleString(locale)}`,
    date: (s: string) => new Date(s).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" }),
  }
}

const compact = (v: number) => {
  const a = Math.abs(v)
  if (a >= 1e6) return `฿${(v / 1e6).toFixed(2)}M`
  if (a >= 1e3) return `฿${(v / 1e3).toFixed(0)}K`
  return `฿${v.toFixed(0)}`
}

type Line = { name: string; color: string; values: number[]; dashed?: boolean }

function EquityChart({ dates, lines, baseline }: { dates: string[]; lines: Line[]; baseline: number }) {
  const { baht, date } = useFmt()
  const [hover, setHover] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const n = dates.length
  const W = 800
  const H = 300

  const { lo, hi, min, max } = useMemo(() => {
    const all = lines.flatMap((l) => l.values).concat(baseline)
    const mn = Math.min(...all)
    const mx = Math.max(...all)
    const pad = (mx - mn) * 0.08 || 1
    return { lo: mn - pad, hi: mx + pad, min: mn, max: mx }
  }, [lines, baseline])

  const x = (i: number) => (n > 1 ? (i / (n - 1)) * W : 0)
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
  const xPct = (i: number) => (n > 1 ? (i / (n - 1)) * 100 : 0)
  const yPct = (v: number) => 100 - ((v - lo) / (hi - lo)) * 100

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const r = ref.current?.getBoundingClientRect()
    if (!r || n < 2) return
    const ratio = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
    setHover(Math.round(ratio * (n - 1)))
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        {lines.map((l) => (
          <span key={l.name} className="flex items-center gap-2">
            <span
              className="inline-block w-5 border-t-2"
              style={{ borderColor: l.color, borderStyle: l.dashed ? "dashed" : "solid" }}
            />
            {l.name}
          </span>
        ))}
      </div>

      <div
        ref={ref}
        className="relative h-72 w-full touch-pan-y select-none"
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden="true">
          <line
            x1={0}
            x2={W}
            y1={y(baseline)}
            y2={y(baseline)}
            strokeWidth={1}
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
            className="stroke-muted-foreground/40"
          />
          {lines.map((l) => (
            <polyline
              key={l.name}
              points={l.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
              fill="none"
              stroke={l.color}
              strokeWidth={l.dashed ? 1.6 : 2.4}
              strokeDasharray={l.dashed ? "5 4" : undefined}
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>

        <span className="pointer-events-none absolute left-1 top-1 rounded bg-background/70 px-1 text-[10px] text-muted-foreground">
          {compact(max)}
        </span>
        <span className="pointer-events-none absolute bottom-1 left-1 rounded bg-background/70 px-1 text-[10px] text-muted-foreground">
          {compact(min)}
        </span>

        {hover !== null && (
          <>
            <div
              className="pointer-events-none absolute top-0 h-full w-px bg-foreground/30"
              style={{ left: `${xPct(hover)}%` }}
            />
            {lines.map((l) => (
              <div
                key={l.name}
                className="pointer-events-none absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background"
                style={{ left: `${xPct(hover)}%`, top: `${yPct(l.values[hover])}%`, background: l.color }}
              />
            ))}
            <div
              className="pointer-events-none absolute top-2 z-10 w-48 rounded-lg border bg-background/95 p-3 text-xs shadow-lg"
              style={xPct(hover) > 55 ? { right: `${100 - xPct(hover) + 2}%` } : { left: `${xPct(hover) + 2}%` }}
            >
              <p className="mb-2 font-semibold">{date(dates[hover])}</p>
              {lines.map((l) => (
                <p key={l.name} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <span className="h-2 w-2 rounded-full" style={{ background: l.color }} />
                    {l.name}
                  </span>
                  <span className="font-semibold">{baht(l.values[hover])}</span>
                </p>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="mt-2 flex justify-between text-xs text-muted-foreground">
        <span>{date(dates[0])}</span>
        <span>{date(dates[n - 1])}</span>
      </div>
    </div>
  )
}

function Stat({ label, value, sub, valueClass = "" }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="rounded-xl border bg-muted/20 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 text-lg font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

export default function BacktestSection({ onRegister }: { onLogin: () => void; onRegister: () => void }) {
  const { t } = useLanguage()
  const { locale, baht, signedBaht, date } = useFmt()
  const [asset, setAsset] = useState("BTC")
  const [period, setPeriod] = useState("1y")
  const [customStart, setCustomStart] = useState(iso(daysAgo(365)))
  const [customEnd, setCustomEnd] = useState(iso(new Date()))
  const [kind, setKind] = useState<Kind>("lump")
  const [freq, setFreq] = useState(FREQS[1].value)
  const [amountText, setAmountText] = useState("100000")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<Result | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const run = async () => {
    const amount = Number(amountText.replace(/,/g, ""))
    if (!Number.isFinite(amount) || amount < 100) {
      setError(t("bt.errMin"))
      return
    }
    let start: string
    let end: string
    if (period === "custom") {
      start = customStart
      end = customEnd
    } else {
      start = iso(daysAgo(PERIODS.find((p) => p.key === period)?.days ?? 365))
      end = iso(new Date())
    }
    if (!start || !end || start >= end) {
      setError(t("bt.errDate"))
      return
    }

    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const timer = setTimeout(() => ctrl.abort(), 90000)

    setLoading(true)
    setError("")
    try {
      const res = await fetch(`${API_BASE_URL}/api/public/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset, kind, amount, start, end, freq }),
        signal: ctrl.signal,
      })
      if (!res.ok) {
        let msg = t("bt.errHttp", { status: res.status })
        try {
          const j = await res.json()
          if (typeof j.detail === "string") msg = j.detail
        } catch {
          // ใช้ข้อความเริ่มต้น
        }
        throw new Error(msg)
      }
      setResult((await res.json()) as Result)
    } catch (e) {
      if ((e as Error).name === "AbortError") {
        if (abortRef.current === ctrl) setError(t("bt.errTimeout"))
      } else {
        setError((e as Error).message || t("bt.errGeneric"))
      }
    } finally {
      clearTimeout(timer)
      if (abortRef.current === ctrl) setLoading(false)
    }
  }

  const s = result?.summary
  const isLump = result?.kind === "lump"
  const vsHold = s ? s.final - s.hold_final : 0
  const vsSav = s ? s.final - s.sav_final : 0

  let verdict = ""
  if (s) {
    if (vsSav < 0) verdict = t("bt.verdictLoseSav")
    else if (!isLump && vsHold < 0) verdict = t("bt.verdictLoseHold")
    else verdict = isLump ? t("bt.verdictWinLump") : t("bt.verdictWinAll")
  }

  const bars = s
    ? [
        { name: t("bt.lineStrategy"), value: s.final, pct: s.pct, color: "#10b981" },
        ...(isLump ? [] : [{ name: t("bt.barHold"), value: s.hold_final, pct: s.hold_pct, color: "#94a3b8" }]),
        { name: t("bt.barSavings"), value: s.sav_final, pct: s.sav_pct, color: "#f59e0b" },
      ]
    : []
  const barMax = Math.max(...bars.map((b) => b.value), 1)

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-3xl font-extrabold tracking-tight">{t("bt.title")}</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{t("bt.subtitle")}</p>

      <div className="mt-8 grid gap-6 lg:grid-cols-[400px_1fr]">
        {/* ---------- แผงตั้งค่า ---------- */}
        <section className="h-fit space-y-6 rounded-2xl border bg-muted/20 p-5 lg:sticky lg:top-24">
          <div>
            <label htmlFor="bt-asset" className="mb-2 block text-sm font-semibold">
              {t("bt.asset")}
            </label>
            <select
              id="bt-asset"
              value={asset}
              onChange={(e) => setAsset(e.target.value)}
              className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm outline-none focus:border-emerald-500"
            >
              {ASSETS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>

          <div>
            <p className="mb-2 text-sm font-semibold">{t("bt.period")}</p>
            <div className="grid grid-cols-4 gap-1 rounded-lg border bg-background p-1">
              {PERIODS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => setPeriod(p.key)}
                  className={`rounded-md px-1 py-2 text-xs font-medium transition-colors ${
                    period === p.key ? "bg-emerald-500 text-black" : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  }`}
                >
                  {t(`bt.periods.${p.key}`)}
                </button>
              ))}
            </div>
            {period === "custom" && (
              <div className="mt-3 grid grid-cols-2 gap-2">
                <label className="text-xs text-muted-foreground">
                  {t("bt.start")}
                  <input
                    type="date"
                    value={customStart}
                    min="2015-01-01"
                    max={iso(new Date())}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="mt-1 w-full rounded-lg border bg-background px-2 py-2 text-sm text-foreground outline-none focus:border-emerald-500"
                  />
                </label>
                <label className="text-xs text-muted-foreground">
                  {t("bt.end")}
                  <input
                    type="date"
                    value={customEnd}
                    min="2015-01-01"
                    max={iso(new Date())}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="mt-1 w-full rounded-lg border bg-background px-2 py-2 text-sm text-foreground outline-none focus:border-emerald-500"
                  />
                </label>
              </div>
            )}
          </div>

          <div>
            <p className="mb-2 text-sm font-semibold">{t("bt.strategy")}</p>
            <div className="space-y-2">
              {STRATEGIES.map((st) => {
                const Icon = st.icon
                const active = kind === st.kind
                return (
                  <button
                    key={st.kind}
                    type="button"
                    onClick={() => setKind(st.kind)}
                    className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors ${
                      active ? "border-emerald-500 bg-emerald-500/10" : "bg-background hover:bg-accent"
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                        active ? "bg-emerald-500 text-black" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold">{t(`bt.strategies.${st.kind}.title`)}</span>
                      <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{t(`bt.strategies.${st.kind}.desc`)}</span>
                    </span>
                    {active && <Check className="mt-1 h-4 w-4 shrink-0 text-emerald-500" />}
                  </button>
                )
              })}
            </div>
          </div>

          {kind === "dca" && (
            <div>
              <p className="mb-2 text-sm font-semibold">{t("bt.freqLabel")}</p>
              <div className="grid grid-cols-2 gap-1 rounded-lg border bg-background p-1">
                {FREQS.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    onClick={() => setFreq(f.value)}
                    className={`rounded-md py-2 text-sm font-medium transition-colors ${
                      freq === f.value ? "bg-emerald-500 text-black" : "text-muted-foreground hover:bg-accent hover:text-foreground"
                    }`}
                  >
                    {t(`bt.freqs.${f.key}`)}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label htmlFor="bt-amount" className="mb-2 block text-sm font-semibold">
              {t("bt.amount")}
            </label>
            <input
              id="bt-amount"
              inputMode="numeric"
              value={amountText}
              onChange={(e) => setAmountText(e.target.value.replace(/[^\d]/g, ""))}
              className="w-full rounded-lg border bg-background px-3 py-2.5 text-base font-semibold outline-none focus:border-emerald-500"
            />
            <div className="mt-2 flex flex-wrap gap-2">
              {QUICK_AMOUNTS.map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => setAmountText(String(a))}
                  className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  {a.toLocaleString(locale)}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 py-3 text-sm font-bold text-black hover:bg-emerald-400 disabled:opacity-60"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" />}
            {loading ? t("bt.running") : t("bt.run")}
          </button>
          {error && <p className="text-sm text-red-500">{error}</p>}
        </section>

        {/* ---------- ผลลัพธ์ ---------- */}
        <section className="min-w-0">
          {!result && !loading && (
            <div className="flex h-full min-h-[420px] flex-col items-center justify-center rounded-2xl border border-dashed p-8 text-center">
              <TrendingUp className="h-10 w-10 text-muted-foreground" />
              <p className="mt-4 text-lg font-semibold">{t("bt.emptyTitle")}</p>
              <p className="mt-1 max-w-sm text-sm text-muted-foreground">{t("bt.emptyDesc")}</p>
            </div>
          )}

          {loading && !result && (
            <div className="flex min-h-[420px] flex-col items-center justify-center rounded-2xl border p-8 text-center">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
              <p className="mt-4 text-sm text-muted-foreground">{t("bt.loadingDesc")}</p>
            </div>
          )}

          {result && s && (
            <div className={`space-y-4 transition-opacity ${loading ? "opacity-50" : ""}`}>
              <div className="rounded-2xl border bg-muted/20 p-6">
                <p className="text-xs text-muted-foreground">
                  {result.asset} · {t(`bt.strategies.${result.kind}.title`)}
                  {result.kind === "dca"
                    ? ` (${(() => { const f = FREQS.find((x) => x.value === result.freq); return f ? t(`bt.freqs.${f.key}`) : result.freq })()})`
                    : ""}{" "}
                  · {date(result.start)} – {date(result.end)}
                </p>
                <p className="mt-3 text-xs text-muted-foreground">{t("bt.finalValue")}</p>
                <p className={`text-4xl font-extrabold tracking-tight sm:text-5xl ${tone(s.profit)}`}>{baht(s.final)}</p>
                <p className="mt-2 text-sm">
                  <span className={`font-semibold ${tone(s.profit)}`}>
                    {signedBaht(s.profit)} ({signedPct(s.pct)})
                  </span>{" "}
                  <span className="text-muted-foreground">{t("bt.fromAmount", { amount: baht(result.amount) })}</span>
                </p>
              </div>

              <div className="rounded-2xl border p-5">
                <p className="mb-4 text-sm font-semibold">{t("bt.compare")}</p>
                <div className="space-y-4">
                  {bars.map((b) => (
                    <div key={b.name}>
                      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                        <span className="text-muted-foreground">{b.name}</span>
                        <span className="font-semibold">
                          {baht(b.value)} <span className={`text-xs ${tone(b.pct)}`}>{signedPct(b.pct)}</span>
                        </span>
                      </div>
                      <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${Math.max(2, (b.value / barMax) * 100)}%`, background: b.color }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat label={t("bt.maxDd")} value={`${s.max_dd.toFixed(2)}%`} valueClass="text-red-500" />
                <Stat label={t("bt.trades")} value={t("bt.tradesCount", { n: s.trades })} />
                {!isLump && (
                  <Stat label={t("bt.vsHold")} value={signedBaht(vsHold)} valueClass={tone(vsHold)} sub={signedPct(s.hold_pct)} />
                )}
                <Stat label={t("bt.vsSav")} value={signedBaht(vsSav)} valueClass={tone(vsSav)} sub={signedPct(s.sav_pct)} />
              </div>

              {s.cash_left > 1 && (
                <p className="text-xs text-muted-foreground">
                  {t("bt.cashLeft", { amount: baht(s.cash_left) })}
                </p>
              )}

              <div className="rounded-2xl border p-5">
                <p className="mb-4 text-sm font-semibold">{t("bt.equityTitle")}</p>
                <EquityChart
                  dates={result.dates}
                  baseline={result.amount}
                  lines={[
                    { name: t("bt.lineStrategy"), color: "#10b981", values: result.strategy },
                    ...(isLump ? [] : [{ name: t("bt.lineHold"), color: "#94a3b8", values: result.hold }]),
                    { name: t("bt.lineSavings"), color: "#f59e0b", values: result.savings, dashed: true },
                  ]}
                />
              </div>

              <div className="rounded-xl border-l-4 border-emerald-500 bg-emerald-500/10 p-4 text-sm leading-6">
                <p>{verdict}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("bt.disclaimer", { spread: result.spread_pct.toFixed(2), fee: result.fee_pct.toFixed(2) })}
                </p>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-5">
                <p className="text-sm text-muted-foreground">{t("bt.ctaText")}</p>
                <button
                  type="button"
                  onClick={onRegister}
                  className="rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-bold text-black hover:bg-emerald-400"
                >
                  {t("bt.ctaBtn")}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
