import { useEffect, useState } from "react"
import { authFetch } from "../../auth"

const API_BASE_URL = "https://xspring-api.onrender.com"
const f = (v: unknown, d = 1) => {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(d) : "—"
}

type Status = "ok" | "watch" | "high" | "na"
type Metric = { key: string; value_pct: number | null; watch: number; high: number; below: boolean; status: Status }
type Alloc = { asset: string; name?: string; value_thb: number; pct: number }
type RiskData = { metrics: Metric[]; active: number; high_count: number; watch_count: number; allocation: Alloc[] }

const LABELS: Record<string, string> = {
  volatility: "Volatility",
  max_drawdown: "Max Drawdown",
  concentration: "Concentration",
  btc_exposure: "BTC Exposure",
  cash: "Cash",
}

const STYLE: Record<Status, { text: string; bar: string; badge: string }> = {
  ok: { text: "OK", bar: "bg-emerald-500", badge: "border-emerald-500/50 text-emerald-400" },
  watch: { text: "WATCH", bar: "bg-yellow-500", badge: "border-yellow-500/50 text-yellow-400" },
  high: { text: "HIGH", bar: "bg-red-500", badge: "border-red-500/50 text-red-400" },
  na: { text: "N/A", bar: "bg-muted", badge: "border-muted text-muted-foreground" },
}

const thb = (v: number) =>
  `฿${Number(v || 0).toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function RiskPage() {
  const [data, setData] = useState<RiskData | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    setError("")
    try {
      const res = await authFetch(`${API_BASE_URL}/api/risk`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      })
      const body = await res.json().catch(() => null)
      if (!res.ok || body?.status !== "ok") {
        throw new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`)
      }
      setData(body)
    } catch (e) {
      setError(e instanceof Error ? e.message : "โหลดไม่สำเร็จ")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="p-6">
      <div className="flex items-start justify-between rounded-xl border p-5">
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Portfolio Monitoring</div>
          <h1 className="mt-1 text-2xl font-bold">Risk Alert Engine</h1>
          <p className="mt-1 text-sm text-muted-foreground">ตรวจจับความเสี่ยงของพอร์ตเทียบกับ threshold</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-3xl font-bold">{data?.active ?? 0}</div>
            <div className="text-xs uppercase text-muted-foreground">Active alerts</div>
          </div>
          <button onClick={load} className="rounded-lg border px-3 py-1.5 text-sm hover:bg-accent">
            {loading ? "..." : "Refresh"}
          </button>
        </div>
      </div>

      {error && <div className="mt-4 rounded-xl border border-red-500/50 p-4 text-red-400">{error}</div>}

      {data && (
        <>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            {[
              ["Active", data.active],
              ["High", data.high_count],
              ["Watch", data.watch_count],
            ].map(([l, v]) => (
              <div key={String(l)} className="rounded-xl border p-4">
                <div className="text-xs uppercase text-muted-foreground">{l}</div>
                <div className="mt-1 text-2xl font-semibold">{v}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.metrics.map((m) => {
              const s = STYLE[m.status]
              const width = m.value_pct == null ? 0 : Math.min(Math.max(m.value_pct, 0), 100)
              return (
                <div key={m.key} className="rounded-xl border p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold">{LABELS[m.key] ?? m.key}</span>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${s.badge}`}>{s.text}</span>
                  </div>
                  <div className="mt-2 text-2xl font-semibold">
                    {m.value_pct == null ? "—" : `${m.value_pct.toFixed(1)}%`}
                  </div>
                  <div className="mt-2 h-1.5 rounded-full bg-muted">
                    <div className={`h-1.5 rounded-full ${s.bar}`} style={{ width: `${width}%` }} />
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {m.below ? `<${m.watch}% watch · <${m.high}% high` : `${m.watch}% watch · ${m.high}% high`}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="mt-6 rounded-xl border p-5">
            <h2 className="text-lg font-semibold">Allocation &amp; Exposure</h2>
            <p className="text-sm text-muted-foreground">สัดส่วนของแต่ละสินทรัพย์ในพอร์ต</p>
            <div className="mt-4 space-y-3">
              {data.allocation.map((a) => (
                <div key={a.asset} className="flex items-center gap-3">
                  <div className="w-24 shrink-0 text-sm font-semibold">
                    {a.asset}
                    {a.name && <span className="ml-1 text-xs font-normal text-muted-foreground">{a.name}</span>}
                  </div>
                  <div className="h-2 flex-1 rounded-full bg-muted">
                    <div className="h-2 rounded-full bg-zinc-400" style={{ width: `${Math.min(a.pct, 100)}%` }} />
                  </div>
                  <div className="w-36 shrink-0 text-right text-sm">{thb(a.value_thb)}</div>
                  <div className="w-14 shrink-0 text-right text-sm text-muted-foreground">{a.pct.toFixed(2)}%</div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
