import { useEffect, useState } from "react"

type NewsItem = {
  title: string
  summary: string
  source: string
  url: string
  published_at: string
}

const API_BASE = import.meta.env.VITE_API_URL ?? "" // ใช้ตัวเดียวกับ MarketSection

function fmtTime(s: string) {
  const d = new Date(s)
  return isNaN(d.getTime())
    ? s
    : d.toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" })
}

export default function NewsSection() {
  const [items, setItems] = useState<NewsItem[] | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    const ctrl = new AbortController()
    fetch(`${API_BASE}/api/public/news`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setItems(d.items ?? []))
      .catch((e) => {
        if (e.name !== "AbortError") setError("โหลดข่าวไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")
      })
    return () => ctrl.abort()
  }, [])

  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl font-extrabold tracking-tight">ข่าวคริปโต</h1>

      {error && <p className="mt-6 text-sm text-red-500">{error}</p>}
      {!error && items === null && <p className="mt-6 text-sm text-muted-foreground">กำลังโหลด…</p>}
      {items?.length === 0 && <p className="mt-6 text-sm text-muted-foreground">ยังไม่มีข่าวในขณะนี้</p>}

      <ul className="mt-6 divide-y">
        {items?.map((n, i) => {
          const body = (
            <>
              <h2 className="font-semibold leading-snug">{n.title}</h2>
              {n.summary && <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{n.summary}</p>}
              <p className="mt-2 text-xs text-muted-foreground">
                {[n.source, n.published_at && fmtTime(n.published_at)].filter(Boolean).join(" · ")}
              </p>
            </>
          )
          return (
            <li key={`${n.url}-${i}`} className="py-4">
              {n.url ? (
                <a href={n.url} target="_blank" rel="noopener noreferrer" className="block hover:text-emerald-500">
                  {body}
                </a>
              ) : (
                body
              )}
            </li>
          )
        })}
      </ul>
    </main>
  )
}
