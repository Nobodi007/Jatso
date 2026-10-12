import { useEffect, useState } from "react"
import { useLanguage } from "../i18n/LanguageContext"

type NewsItem = {
  title: string
  summary: string
  source: string
  url: string
  published_at: string
}

const API_BASE_URL = "https://xspring-api.onrender.com"

function fmtTime(s: string, locale: string) {
  const d = new Date(s)
  return isNaN(d.getTime())
    ? s
    : d.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" })
}

export default function NewsSection() {
  const { t, lang } = useLanguage()
  const locale = lang === "th" ? "th-TH" : "en-US"
  const [items, setItems] = useState<NewsItem[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const ctrl = new AbortController()
    fetch(`${API_BASE_URL}/api/public/news`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setItems(d.items ?? []))
      .catch((e) => {
        if (e.name !== "AbortError") setFailed(true)
      })
    return () => ctrl.abort()
  }, [])

  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl font-extrabold tracking-tight">{t("news.title")}</h1>

    {failed && <p className="mt-6 text-sm text-red-500">{t("news.loadFailed")}</p>}
    {!failed && items === null && <p className="mt-6 text-sm text-muted-foreground">{t("news.loading")}</p>}
    {items?.length === 0 && <p className="mt-6 text-sm text-muted-foreground">{t("news.empty")}</p>}

      <ul className="mt-6 divide-y">
        {items?.map((n, i) => {
          const body = (
            <>
              <h2 className="font-semibold leading-snug">{n.title}</h2>
              {n.summary && <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{n.summary}</p>}
              <p className="mt-2 text-xs text-muted-foreground">
                {[n.source, n.published_at && fmtTime(n.published_at, locale)].filter(Boolean).join(" · ")}
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
