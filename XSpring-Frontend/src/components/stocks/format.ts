import type { RangeKey } from "./stockApi"

export const NY = "America/New_York"

export const fmt = (n: number | null | undefined, d = 2) =>
  n == null || !isFinite(n)
    ? "--"
    : n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })

export const fmtInt = (n: number | null | undefined) =>
  n == null || !isFinite(n) ? "--" : Math.round(n).toLocaleString("en-US")

export const fmtCompact = (n: number | null | undefined) => {
  if (n == null || !isFinite(n)) return "--"
  const abs = Math.abs(n)
  const cut = (v: number, s: string) => v.toFixed(3).replace(/\.?0+$/, "") + s
  if (abs >= 1e12) return cut(n / 1e12, "T")
  if (abs >= 1e9) return cut(n / 1e9, "B")
  if (abs >= 1e6) return cut(n / 1e6, "M")
  if (abs >= 1e3) return cut(n / 1e3, "K")
  return fmtInt(n)
}

export const signed = (n: number | null | undefined, d = 2) =>
  n == null || !isFinite(n) ? "--" : (n >= 0 ? "+" : "") + fmt(n, d)

/** รองรับ "2026-12-23" จาก Finnhub ไม่ให้วันเลื่อน */
export const fmtDate = (iso: string | null | undefined) => {
  if (!iso) return "--"
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso)
  if (isNaN(d.getTime())) return "--"
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: NY })
}

export const fmtAsOf = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
        timeZone: NY,
        timeZoneName: "short",
      })
    : ""

export const marketStateLabel = (s: string) =>
  (
    {
      REGULAR: "ตลาดเปิด",
      PRE: "ก่อนตลาดเปิด",
      PREPRE: "ก่อนตลาดเปิด",
      POST: "หลังตลาดปิด",
      POSTPOST: "หลังตลาดปิด",
      CLOSED: "ตลาดปิด",
    } as Record<string, string>
  )[s] ?? s

export const timeAgo = (iso: string | null) => {
  if (!iso) return ""
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (m < 1) return "เมื่อสักครู่"
  if (m < 60) return `${m} นาทีที่แล้ว`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} ชม.ที่แล้ว`
  return `${Math.floor(h / 24)} วันที่แล้ว`
}

export function niceTicks(min: number, max: number, count = 5) {
  const raw = (max - min) / count
  if (!isFinite(raw) || raw <= 0) return [min]
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag
  const ticks: number[] = []
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) ticks.push(+v.toFixed(6))
  return ticks
}

export function xLabel(t: number, range: RangeKey) {
  const d = new Date(t)
  if (range === "1d") return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: NY })
  if (range === "5d" || range === "1mo")
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: NY })
  if (range === "5y" || range === "max") return d.toLocaleDateString("en-US", { year: "numeric", timeZone: NY })
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: NY })
}

export function tooltipLabel(t: number, range: RangeKey) {
  const intraday = range === "1d" || range === "5d"
  return new Date(t).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: intraday ? undefined : "numeric",
    hour: intraday ? "numeric" : undefined,
    minute: intraday ? "2-digit" : undefined,
    timeZone: NY,
  })
}
