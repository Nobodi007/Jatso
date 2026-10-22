import { useEffect, useMemo, useState } from "react"
import { authFetch } from "../../auth"

type Sent = "bullish" | "bearish" | "neutral"

type Item = {
  id: number | string
  headline: string
  summary?: string
  source?: string
  url: string
  datetime: number
}

type Hit = { symbol: string; name: string }

const SENT: Record<Sent, { label: string; icon: string; cls: string }> = {
  bullish: { label: "บวก", icon: "▲", cls: "bg-emerald-500/10 text-emerald-500" },
  neutral: { label: "กลาง", icon: "●", cls: "bg-muted text-muted-foreground" },
  bearish: { label: "ลบ", icon: "▼", cls: "bg-red-500/10 text-red-500" },
}

const TABS: { key: "all" | Sent; label: string }[] = [
  { key: "all", label: "ทั้งหมด" },
  { key: "bullish", label: "บวก" },
  { key: "neutral", label: "กลาง" },
  { key: "bearish", label: "ลบ" },
]

function AiButton({ apiBase, item }: { apiBase: string; item: Item }) {
  const [data, setData] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")

  const run = async () => {
    setBusy(true)
    setErr("")
    try {
      const res = await authFetch(`${apiBase}/api/news/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: item.url,
          title: item.headline,
          snippet: item.summary || "",
          kind: "stock",
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
    } catch (e) {
      setErr(e instanceof Error ? e.message : "สรุปไม่สำเร็จ")
    } finally {
      setBusy(false)
    }
  }

  const s = data?.sentiment as Sent | undefined
  const color = s === "bullish" ? "text-emerald-500" : s === "bearish" ? "text-red-500" : "text-muted-foreground"

  return (
    <div className="mt-3">
      {!data && (
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="rounded-md border px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
        >
          {busy ? "กำลังแปล..." : "✨ แปล/สรุปไทย"}
        </button>
      )}
      {err && <p className="mt-2 text-xs text-red-500">{err}</p>}
      {data && (
        <div className="space-y-1.5 rounded-lg bg-muted/50 p-3 text-xs">
          <p className="font-semibold">{data.title_th}</p>
          <p>{data.summary_th}</p>
          <p className={color}>
            {s === "bullish" ? "▲ บวก" : s === "bearish" ? "▼ ลบ" : "● กลาง"}
            {data.note ? ` · ${data.note}` : ""}
          </p>
        </div>
      )}
    </div>
  )
}

export default function StockNewsPage({ apiBase }: { apiBase: string }) {
  const [symbol, setSymbol] = useState("")
  const [q, setQ] = useState("")
  const [hits, setHits] = useState<Hit[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [sent, setSent] = useState<Record<string, Sent>>({})
  const [tab, setTab] = useState<"all" | Sent>("all")
  const [loading, setLoading] = useState(true)
  const [classifying, setClassifying] = useState(false)
  const [error, setError] = useState("")
  const [tick, setTick] = useState(0)

  // ค้นหาหุ้น (หน่วงเวลาให้พิมพ์จบก่อน)
  useEffect(() => {
    const text = q.trim()
    if (!text) {
      setHits([])
      return
    }
    const id = window.setTimeout(async () => {
      try {
        const r = await fetch(`${apiBase}/api/stocks/search?q=${encodeURIComponent(text)}`)
        const j = await r.json()
        setHits(Array.isArray(j) ? j : [])
      } catch {
        setHits([])
      }
    }, 350)
    return () => window.clearTimeout(id)
  }, [q, apiBase])

  // โหลดข่าว (ว่าง = ข่าวรวม) แล้วให้ AI จัดหมวด
  useEffect(() => {
    let off = false
    const run = async () => {
      setLoading(true)
      setError("")
      try {
        const r = await fetch(`${apiBase}/api/stocks/newsfeed?symbol=${encodeURIComponent(symbol)}`)
        if (!r.ok) throw new Error(r.status === 503 ? "โควต้าข้อมูลเต็มชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่" : `HTTP ${r.status}`)
        const rows = (await r.json()) as Item[]
        if (off) return
        setItems(Array.isArray(rows) ? rows : [])
        setLoading(false)

        const todo = rows.filter((x) => !(String(x.id) in sent))
        if (todo.length === 0) return
        setClassifying(true)
        try {
          const c = await authFetch(`${apiBase}/api/stocks/newsfeed/classify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              items: todo.map((x) => ({
                id: String(x.id),
                headline: x.headline.slice(0, 300),
                summary: (x.summary || "").slice(0, 400),
              })),
            }),
          })
          if (c.ok) {
            const j = await c.json()
            if (!off) {
              const next: Record<string, Sent> = {}
              for (const x of todo) next[String(x.id)] = (j?.sentiments?.[String(x.id)] as Sent) || "neutral"
              setSent((prev) => ({ ...prev, ...next }))
            }
          }
        } catch {
          // จัดหมวดไม่ได้ก็ยังอ่านข่าวได้ตามปกติ
        } finally {
          if (!off) setClassifying(false)
        }
      } catch (e) {
        if (!off) {
          setError(e instanceof Error ? e.message : "โหลดข่าวไม่สำเร็จ")
          setItems([])
          setLoading(false)
        }
      }
    }
    run()
    return () => {
      off = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, symbol, tick])

  const counts = useMemo(() => {
    const c = { all: items.length, bullish: 0, neutral: 0, bearish: 0 }
    for (const x of items) {
      const s = sent[String(x.id)]
      if (s) c[s] += 1
    }
    return c
  }, [items, sent])

  const visible = tab === "all" ? items : items.filter((x) => sent[String(x.id)] === tab)

  const pick = (s: string) => {
    setSymbol(s.toUpperCase())
    setQ("")
    setHits([])
    setTab("all")
  }

  const submitTyped = () => {
    const t = q.trim().toUpperCase()
    if (/^[A-Z][A-Z.\-]{0,9}$/.test(t)) pick(t)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">News</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {symbol ? `ข่าวของ ${symbol} ย้อนหลัง 7 วัน` : "ข่าวรวมตลาดหุ้นล่าสุด ค้นหาหุ้นเพื่อดูข่าวเฉพาะตัว"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setTick((t) => t + 1)}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full md:w-96">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitTyped()}
            placeholder="ค้นหาหุ้นเพื่อดูข่าว เช่น Apple, TSLA"
            aria-label="ค้นหาหุ้น"
            className="w-full rounded-xl border bg-card px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary"
          />
          {hits.length > 0 && (
            <ul className="absolute z-10 mt-2 max-h-72 w-full overflow-auto rounded-xl border bg-card shadow-xl">
              {hits.map((h) => (
                <li key={h.symbol}>
                  <button
                    type="button"
                    onClick={() => pick(h.symbol)}
                    className="flex w-full justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-accent"
                  >
                    <span className="font-semibold">{h.symbol}</span>
                    <span className="truncate text-muted-foreground">{h.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {symbol && (
          <button
            type="button"
            onClick={() => setSymbol("")}
            className="flex items-center gap-2 rounded-full border bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
          >
            {symbol} <span aria-hidden>✕</span>
            <span className="sr-only">ล้างการค้นหา</span>
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-full border px-4 py-2 text-sm transition-colors ${
              tab === t.key ? "bg-primary text-primary-foreground" : "hover:bg-accent"
            }`}
          >
            {t.label} <span className="ml-1 text-xs opacity-70">{counts[t.key]}</span>
          </button>
        ))}
        {classifying && <span className="text-xs text-muted-foreground">AI กำลังจัดหมวดข่าว...</span>}
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">{error}</div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {visible.map((x) => {
          const s = sent[String(x.id)]
          return (
            <article key={x.id} className="rounded-xl border bg-card p-5 transition-colors hover:bg-accent/30">
              <div className="mb-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-muted px-2.5 py-1 font-medium">{x.source || "—"}</span>
                  {s && (
                    <span className={`rounded-full px-2.5 py-1 font-semibold ${SENT[s].cls}`}>
                      {SENT[s].icon} {SENT[s].label}
                    </span>
                  )}
                </div>
                <span>{new Date(x.datetime * 1000).toLocaleString("th-TH")}</span>
              </div>
              <h3 className="text-base font-semibold leading-6">
                <a href={x.url} target="_blank" rel="noreferrer" className="hover:underline">
                  {x.headline}
                </a>
              </h3>
              {x.summary && <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">{x.summary}</p>}
              <a
                href={x.url}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-flex text-sm font-medium text-primary hover:underline"
              >
                อ่านข่าวเต็ม →
              </a>
              <AiButton apiBase={apiBase} item={x} />
            </article>
          )
        })}
      </div>

      {!loading && visible.length === 0 && !error && (
        <div className="flex min-h-[200px] items-center justify-center rounded-xl border bg-card text-sm text-muted-foreground">
          {tab === "all" ? "ไม่มีข่าวในช่วงนี้" : "ยังไม่มีข่าวในหมวดนี้"}
        </div>
      )}

      <div className="rounded-xl border bg-card px-5 py-4 text-xs leading-5 text-muted-foreground">
        ข่าวจาก Finnhub การจัดหมวดบวก/กลาง/ลบเป็นการประเมินของ AI จากหัวข้อและสรุปข่าวเท่านั้น อาจคลาดเคลื่อน
        ใช้เพื่อการติดตามข่าว ไม่ใช่คำแนะนำการลงทุน
      </div>
    </div>
  )
}
