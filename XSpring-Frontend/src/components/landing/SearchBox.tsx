import { useEffect, useMemo, useRef, useState } from "react"
import { Search } from "lucide-react"

const API_BASE_URL = "https://xspring-api.onrender.com"

type Row = { asset: string; name: string; price: number; change: number }

const fmtPrice = (v: number) =>
  v.toLocaleString("th-TH", { maximumFractionDigits: v < 1 ? 4 : 2 })

export default function SearchBox({ onSelect }: { onSelect: (asset: string) => void }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // โหลดรายชื่อเหรียญครั้งแรกที่เปิดช่องค้นหา
  useEffect(() => {
    if (!open || rows) return
    const ctrl = new AbortController()
    fetch(`${API_BASE_URL}/api/public/markets`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setRows(Array.isArray(d.rows) ? d.rows : []))
      .catch((e) => {
        if (e.name !== "AbortError") setError(true)
      })
    return () => ctrl.abort()
  }, [open, rows])

  // โฟกัสช่องพิมพ์ + ปิดเมื่อคลิกข้างนอกหรือกด Esc
  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  const results = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!rows) return []
    if (!s) return rows
    return rows.filter((r) => r.asset.toLowerCase().includes(s) || r.name.toLowerCase().includes(s))
  }, [rows, q])

  const pick = (asset: string) => {
    setOpen(false)
    setQ("")
    onSelect(asset)
  }

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        aria-label="ค้นหา"
        onClick={() => setOpen((v) => !v)}
        className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Search className="h-4 w-4" />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border bg-background p-2 shadow-xl">
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && results[0]) pick(results[0].asset)
            }}
            placeholder="ค้นหาเหรียญ เช่น BTC, Bitcoin"
            className="w-full rounded-md border bg-transparent px-3 py-2 text-sm outline-none focus:border-emerald-500"
          />

          <div className="mt-2 max-h-80 overflow-y-auto">
            {error && <p className="px-3 py-3 text-sm text-red-500">โหลดรายชื่อเหรียญไม่สำเร็จ</p>}
            {!error && !rows && <p className="px-3 py-3 text-sm text-muted-foreground">กำลังโหลด…</p>}
            {rows && results.length === 0 && (
              <p className="px-3 py-3 text-sm text-muted-foreground">ไม่พบเหรียญที่ค้นหา</p>
            )}
            {!q.trim() && results.length > 0 && (
              <p className="px-3 pb-1 pt-2 text-xs text-muted-foreground">เหรียญทั้งหมด</p>
            )}
            {results.map((r) => (
              <button
                key={r.asset}
                type="button"
                onClick={() => pick(r.asset)}
                className="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-accent"
              >
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{r.asset}</span>
                  <span className="block truncate text-xs text-muted-foreground">{r.name}</span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block text-sm">฿{fmtPrice(r.price)}</span>
                  <span className={`block text-xs ${r.change >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                    {r.change >= 0 ? "+" : ""}
                    {r.change.toFixed(2)}%
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
