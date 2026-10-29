import { useEffect, useMemo, useState } from "react"
import { Label, Pie, PieChart } from "recharts"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"

// ---------- types ----------
type Holding = {
  cusip: string; ticker: string; name: string; value: number; shares: number
  weight: number; change: "" | "new" | "added" | "reduced" | "same"; change_pct: number | null
}
type Sold = { cusip: string; ticker: string; name: string; value: number }
type Investor = {
  id: string; person: string; fund: string; period: string; filed: string
  total_value: number; holdings_count: number; holdings: Holding[]; sold: Sold[]
}
type Data = { generated_at: string; investors: Investor[] }
type Filter = "all" | "new" | "added" | "reduced"

// ---------- helpers ----------
const TOP_N = 7
const PALETTE = [
  "var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)",
  "var(--chart-5)", "#8b5cf6", "#06b6d4",
]
const OTHER_COLOR = "#3f3f46"

const usd = (v: number) =>
  v >= 1e9 ? `${(v / 1e9).toFixed(2)}B`
  : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M`
  : `${Math.round(v).toLocaleString("en-US")}`
const pct = (w: number, d = 1) => `${(w * 100).toFixed(d)}%`
const initials = (n: string) =>
  n.replace(/\(.*?\)/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase()

const card = "rounded-2xl border bg-card"

// ---------- small components ----------
function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border bg-background/40 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  )
}

function ChangeBadge({ h }: { h: Holding }) {
  const p = h.change_pct != null ? ` ${Math.abs(h.change_pct * 100).toFixed(0)}%` : ""
  const base = "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium"
  if (h.change === "new") return <span className={`${base} bg-emerald-500/15 text-emerald-400`}>● ซื้อใหม่</span>
  if (h.change === "added") return <span className={`${base} bg-sky-500/15 text-sky-400`}>▲ เพิ่ม{p}</span>
  if (h.change === "reduced") return <span className={`${base} bg-amber-500/15 text-amber-400`}>▼ ลด{p}</span>
  return <span className="text-xs text-muted-foreground/40">—</span>
}

function ActivityBox({ title, tone, items }: {
  title: string; tone: string; items: { key: string; label: string }[]
}) {
  return (
    <div className="rounded-xl border bg-background/40 p-4">
      <div className="flex items-center justify-between">
        <p className={`text-sm font-semibold ${tone}`}>{title}</p>
        <span className="text-xs text-muted-foreground">{items.length} ตัว</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {items.length === 0 && <span className="text-xs text-muted-foreground/60">ไม่มี</span>}
        {items.slice(0, 12).map((i) => (
          <span key={i.key} className="rounded-md border bg-card px-2 py-0.5 text-[11px] font-medium">{i.label}</span>
        ))}
        {items.length > 12 && (
          <span className="px-1 text-[11px] text-muted-foreground">+{items.length - 12}</span>
        )}
      </div>
    </div>
  )
}

// ---------- page ----------
export default function SuperInvestorsPage() {
  const [data, setData] = useState<Data | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sel, setSel] = useState("")
  const [filter, setFilter] = useState<Filter>("all")
  const [q, setQ] = useState("")
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    fetch("/data/superinvestors.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("ยังไม่มีไฟล์ข้อมูล"))))
      .then((d: Data) => { setData(d); setSel(d.investors[0]?.id ?? "") })
      .catch((e) => setErr(e instanceof Error ? e.message : "โหลดข้อมูลไม่ได้"))
  }, [])

  useEffect(() => { setFilter("all"); setQ(""); setShowAll(false) }, [sel])

  const inv = useMemo(() => data?.investors.find((i) => i.id === sel), [data, sel])

  const view = useMemo(() => {
    if (!inv) return null
    const hs = [...inv.holdings].sort((a, b) => b.value - a.value)
    const top = hs.slice(0, TOP_N)

    const slices = top.map((h, i) => ({
      key: `s${i}`, label: h.ticker || h.name, value: h.value, weight: h.weight, fill: PALETTE[i],
    }))
    const rest = inv.total_value - top.reduce((s, h) => s + h.value, 0)
    if (rest > 0) {
      slices.push({
        key: "other", label: "อื่นๆ", value: rest,
        weight: Math.max(0, 1 - top.reduce((s, h) => s + h.weight, 0)), fill: OTHER_COLOR,
      })
    }

    const config = Object.fromEntries(
      slices.map((s) => [s.key, { label: s.label, color: s.fill }]),
    ) as ChartConfig

    const toChip = (h: { cusip: string; ticker: string; name: string }) => ({ key: h.cusip, label: h.ticker || h.name })

    return {
      hs,
      slices,
      config,
      colorOf: new Map(top.map((h, i) => [h.cusip, PALETTE[i]])),
      maxW: hs[0]?.weight || 1,
      top10: hs.slice(0, 10).reduce((s, h) => s + h.weight, 0),
      groups: {
        new: hs.filter((h) => h.change === "new").map(toChip),
        added: hs.filter((h) => h.change === "added").map(toChip),
        reduced: hs.filter((h) => h.change === "reduced").map(toChip),
        sold: inv.sold.map(toChip),
      },
    }
  }, [inv])

  const rows = useMemo(() => {
    if (!view) return []
    const s = q.trim().toLowerCase()
    return view.hs.filter(
      (h) =>
        (filter === "all" || h.change === filter) &&
        (!s || h.ticker.toLowerCase().includes(s) || h.name.toLowerCase().includes(s)),
    )
  }, [view, filter, q])

  if (err) return <div className={`${card} p-5 text-sm text-red-500`}>{err}</div>
  if (!data) return <div className="animate-pulse text-sm text-muted-foreground">กำลังโหลด…</div>

  const shown = showAll ? rows : rows.slice(0, 25)
  const filters: { id: Filter; label: string; count?: number }[] = [
    { id: "all", label: "ทั้งหมด", count: view?.hs.length },
    { id: "new", label: "ซื้อใหม่", count: view?.groups.new.length },
    { id: "added", label: "เพิ่ม", count: view?.groups.added.length },
    { id: "reduced", label: "ลด", count: view?.groups.reduced.length },
  ]

  return (
    <div className="space-y-6 pb-24">
      {/* ---------- header ---------- */}
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-3xl font-bold tracking-tight">พอร์ตนักลงทุนชื่อดัง</h2>
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-[11px] text-amber-400">
            ไม่ใช่คำแนะนำลงทุน
          </span>
        </div>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          ข้อมูลจากฟอร์ม 13F ที่ยื่นต่อ SEC ทุกไตรมาส · แสดงเฉพาะหุ้นสหรัฐฝั่งซื้อ
          (ไม่รวม short เงินสด และหุ้นต่างประเทศ) · ล่าช้าได้ถึง 45 วันหลังสิ้นไตรมาส
        </p>
      </div>

      {/* ---------- investor picker ---------- */}
      <div className="flex flex-wrap gap-2">
        {data.investors.map((i) => {
          const active = i.id === sel
          return (
            <button
              key={i.id}
              type="button"
              onClick={() => setSel(i.id)}
              className={`group flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-xs transition-all ${
                active
                  ? "border-foreground bg-foreground font-semibold text-background shadow-lg shadow-black/30"
                  : "hover:border-foreground/40 hover:bg-accent"
              }`}
            >
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${
                  active ? "bg-background text-foreground" : "bg-muted text-muted-foreground group-hover:text-foreground"
                }`}
              >
                {initials(i.person)}
              </span>
              {i.person}
            </button>
          )
        })}
      </div>

      {inv && view && (
        <>
          {/* ---------- hero ---------- */}
          <div className={`${card} overflow-hidden`}>
            <div className="grid gap-6 p-6 lg:grid-cols-5">
              {/* left: info + stats */}
              <div className="flex flex-col gap-5 lg:col-span-3">
                <div className="flex items-center gap-4">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--chart-1)] to-[var(--chart-3)] text-lg font-bold text-white">
                    {initials(inv.person)}
                  </div>
                  <div>
                    <h3 className="text-2xl font-bold">{inv.person}</h3>
                    <p className="text-sm text-muted-foreground">{inv.fund}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 text-[11px]">
                  <span className="rounded-md border px-2 py-1 text-muted-foreground">งวด <b className="text-foreground">{inv.period}</b></span>
                  <span className="rounded-md border px-2 py-1 text-muted-foreground">ยื่นเมื่อ <b className="text-foreground">{inv.filed}</b></span>
                </div>

                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  <Stat label="มูลค่าพอร์ต" value={usd(inv.total_value)} />
                  <Stat label="จำนวนหุ้น" value={`${inv.holdings_count} ตัว`} />
                  <Stat label="Top 10 กระจุกตัว" value={pct(view.top10)} sub="ของพอร์ตทั้งหมด" />
                  <Stat
                    label="ซื้อใหม่ / ขายหมด"
                    value={`${view.groups.new.length} / ${view.groups.sold.length}`}
                    sub="เทียบไตรมาสก่อน"
                  />
                </div>
              </div>

              {/* right: donut */}
              <div className="flex flex-col items-center gap-4 lg:col-span-2">
                <ChartContainer config={view.config} className="mx-auto aspect-square w-full max-w-[260px]">
                  <PieChart>
                    <ChartTooltip
                      cursor={false}
                      content={
                        <ChartTooltipContent
                          hideLabel
                          nameKey="key"
                          formatter={(value, _name, item) => (
                            <div className="flex w-full min-w-[10rem] items-center gap-2">
                              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: item.payload.fill }} />
                              <span className="font-medium">{item.payload.label}</span>
                              <span className="ml-auto tabular-nums text-muted-foreground">
                                {usd(Number(value))} · {pct(item.payload.weight)}
                              </span>
                            </div>
                          )}
                        />
                      }
                    />
                    <Pie
                      data={view.slices}
                      dataKey="value"
                      nameKey="key"
                      innerRadius={72}
                      outerRadius={112}
                      paddingAngle={1.5}
                      cornerRadius={4}
                      stroke="var(--card)"
                      strokeWidth={2}
                    >
                      <Label
                        content={({ viewBox }) => {
                          if (!viewBox || !("cx" in viewBox) || !("cy" in viewBox)) return null
                          const cx = viewBox.cx ?? 0
                          const cy = viewBox.cy ?? 0
                          return (
                            <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle">
                              <tspan x={cx} y={cy - 6} className="fill-foreground text-2xl font-bold tabular-nums">
                                {usd(inv.total_value)}
                              </tspan>
                              <tspan x={cx} y={cy + 18} className="fill-muted-foreground text-xs">
                                มูลค่าพอร์ต
                              </tspan>
                            </text>
                          )
                        }}
                      />
                    </Pie>
                  </PieChart>
                </ChartContainer>

                <div className="grid w-full max-w-sm grid-cols-2 gap-x-4 gap-y-1.5">
                  {view.slices.map((s) => (
                    <div key={s.key} className="flex items-center gap-2 text-xs">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: s.fill }} />
                      <span className="truncate font-medium">{s.label}</span>
                      <span className="ml-auto tabular-nums text-muted-foreground">{pct(s.weight)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* ---------- quarter activity ---------- */}
          <div className={`${card} p-6`}>
            <h4 className="font-semibold">ความเคลื่อนไหวไตรมาสนี้</h4>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <ActivityBox title="ซื้อใหม่" tone="text-emerald-400" items={view.groups.new} />
              <ActivityBox title="เพิ่มสัดส่วน" tone="text-sky-400" items={view.groups.added} />
              <ActivityBox title="ลดสัดส่วน" tone="text-amber-400" items={view.groups.reduced} />
              <ActivityBox title="ขายออกหมด" tone="text-red-400" items={view.groups.sold} />
            </div>
          </div>

          {/* ---------- holdings table ---------- */}
          <div className={`${card} p-6`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-1 rounded-lg bg-muted/50 p-1">
                {filters.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => { setFilter(f.id); setShowAll(false) }}
                    className={`rounded-md px-3 py-1 text-xs transition-colors ${
                      filter === f.id ? "bg-card font-semibold shadow" : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {f.label}
                    <span className="ml-1.5 text-[10px] text-muted-foreground">{f.count ?? 0}</span>
                  </button>
                ))}
              </div>
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="ค้นหา ticker หรือชื่อบริษัท…"
                className="h-9 w-full rounded-lg border bg-background/40 px-3 text-sm outline-none focus:border-foreground/40 sm:w-64"
              />
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm tabular-nums">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="w-10 pb-2 font-normal">#</th>
                    <th className="pb-2 font-normal">หุ้น</th>
                    <th className="pb-2 font-normal">สัดส่วน</th>
                    <th className="pb-2 text-right font-normal">มูลค่า</th>
                    <th className="pb-2 text-right font-normal">เทียบไตรมาสก่อน</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((h) => {
                    const rank = view.hs.indexOf(h) + 1
                    const color = view.colorOf.get(h.cusip) ?? "var(--muted-foreground)"
                    return (
                      <tr key={h.cusip} className="border-t border-border/60 transition-colors hover:bg-accent/40">
                        <td className="py-3 text-xs text-muted-foreground">{rank}</td>
                        <td className="py-3 pr-3">
                          <div className="flex items-center gap-3">
                            <span className="h-8 w-1 rounded-full" style={{ background: color }} />
                            <div className="min-w-0">
                              <p className="font-semibold">{h.ticker || "—"}</p>
                              <p className="truncate text-[11px] text-muted-foreground">{h.name}</p>
                            </div>
                          </div>
                        </td>
                        <td className="pr-4">
                          <div className="flex items-center gap-3">
                            <div className="h-2 w-32 overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full"
                                style={{ width: `${(h.weight / view.maxW) * 100}%`, background: color }}
                              />
                            </div>
                            <span className="w-12 text-xs">{pct(h.weight)}</span>
                          </div>
                        </td>
                        <td className="text-right font-medium">{usd(h.value)}</td>
                        <td className="text-right"><ChangeBadge h={h} /></td>
                      </tr>
                    )
                  })}
                  {shown.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-10 text-center text-sm text-muted-foreground">ไม่พบหุ้นที่ตรงเงื่อนไข</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {rows.length > 25 && (
              <button
                type="button"
                onClick={() => setShowAll((v) => !v)}
                className="mt-4 w-full rounded-lg border py-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                {showAll ? "ย่อลง" : `ดูทั้งหมด ${rows.length} ตัว`}
              </button>
            )}
          </div>
        </>
      )}

      <p className="text-xs text-muted-foreground">
        อัปเดตข้อมูลล่าสุด {data.generated_at.slice(0, 10)} · ที่มา SEC EDGAR
      </p>
    </div>
  )
}
