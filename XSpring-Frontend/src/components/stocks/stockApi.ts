export type RangeKey = "1d" | "5d" | "1mo" | "6mo" | "ytd" | "1y" | "5y" | "max"
export type Bar = { t: number; c: number; v: number }

export type StockSummary = {
  symbol: string
  name: string
  logo?: string | null
  exchange: string
  currency: string
  marketState: string
  time: string | null
  price: number
  change: number | null
  changePercent: number | null
  preMarketPrice?: number | null
  preMarketChange?: number | null
  preMarketChangePercent?: number | null
  postMarketPrice?: number | null
  postMarketChange?: number | null
  postMarketChangePercent?: number | null
  previousClose: number | null
  open: number | null
  dayLow: number | null
  dayHigh: number | null
  bid: number | null
  bidSize: number | null
  ask: number | null
  askSize: number | null
  fiftyTwoWeekLow: number | null
  fiftyTwoWeekHigh: number | null
  volume: number | null
  avgVolume: number | null
  marketCap: number | null
  beta: number | null
  peRatio: number | null
  eps: number | null
  earningsDate: string | null
  dividendRate: number | null
  dividendYield: number | null // หน่วย % แล้ว
  targetPrice: number | null
  sector?: string | null
  industry?: string | null
  description?: string | null
  website?: string | null
  employees?: number | null
}

export type NewsItem = {
  title: string
  publisher: string
  link: string
  publishedAt: string | null
  thumbnail?: string | null
}

export const RANGES: { key: RangeKey; label: string }[] = [
  { key: "1d", label: "1D" },
  { key: "5d", label: "5D" },
  { key: "1mo", label: "1M" },
  { key: "6mo", label: "6M" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1Y" },
  { key: "5y", label: "5Y" },
  { key: "max", label: "All" },
]

export const API_BASE_URL = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || "https://xspring-api.onrender.com"
).replace(/\/$/, "")

export class ApiError extends Error {
  status: number
  constructor(status: number, message?: string) {
    super(message ?? `HTTP ${status}`)
    this.status = status
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API_BASE_URL}${path}`, { signal })
  if (!r.ok) throw new ApiError(r.status)
  return r.json() as Promise<T>
}

const enc = (s: string) => encodeURIComponent(s.toUpperCase())

export function fetchSummary(symbol: string, signal?: AbortSignal) {
  return getJson<StockSummary>(`/api/stocks/${enc(symbol)}/summary`, signal)
}

export async function fetchChart(symbol: string, range: RangeKey, signal?: AbortSignal) {
  const d = await getJson<{ bars?: Bar[] }>(`/api/stocks/${enc(symbol)}/chart?range=${range}`, signal)
  return d.bars ?? []
}

/** endpoint /news เดิมคืนรูปแบบ Finnhub -> แปลงเป็น NewsItem */
export async function fetchNews(symbol: string, signal?: AbortSignal): Promise<NewsItem[]> {
  const d = await getJson<any>(`/api/stocks/${enc(symbol)}/news`, signal)
  const items: any[] = Array.isArray(d) ? d : d?.news ?? d?.items ?? []
  const seen = new Set<string>()
  return items
    .map((n) => ({
      title: n.headline ?? n.title ?? "",
      publisher: n.source ?? n.publisher ?? "",
      link: n.url ?? n.link ?? "",
      publishedAt:
        typeof n.datetime === "number"
          ? new Date(n.datetime * 1000).toISOString()
          : n.publishedAt ?? null,
      thumbnail: n.image || n.thumbnail || null,
    }))
    .filter((n) => n.title && n.link && !seen.has(n.link) && seen.add(n.link))
    .slice(0, 8)
}
