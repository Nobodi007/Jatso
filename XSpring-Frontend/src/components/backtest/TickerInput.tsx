import { useEffect, useRef, useState } from "react"

export type TickerHit = { symbol: string; name: string }

type Props = {
  value: string
  onChange: (v: string) => void
  search: (q: string) => Promise<TickerHit[]>
  className?: string
  placeholder?: string
}

export default function TickerInput({ value, onChange, search, className, placeholder }: Props) {
  const [hits, setHits] = useState<TickerHit[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const searchRef = useRef(search)
  searchRef.current = search
  const seq = useRef(0)

  useEffect(() => {
    const q = value.trim()
    if (!open || q === "") {
      setHits([])
      return
    }
    const id = ++seq.current
    const t = setTimeout(async () => {
      try {
        const r = await searchRef.current(q)
        if (id === seq.current) {
          setHits(r.slice(0, 8))
          setActive(-1)
        }
      } catch {
        if (id === seq.current) setHits([])
      }
    }, 250)
    return () => clearTimeout(t)
  }, [value, open])

  const pick = (h: TickerHit) => {
    onChange(h.symbol)
    setOpen(false)
    setHits([])
  }

  return (
    <div className="relative min-w-0 flex-1">
      <input
        className={className}
        placeholder={placeholder}
        value={value}
        autoComplete="off"
        onChange={(e) => {
          onChange(e.target.value.toUpperCase())
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, hits.length - 1))
          } else if (e.key === "ArrowUp") {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === "Enter" && open && active >= 0 && hits[active]) {
            e.preventDefault()
            pick(hits[active])
          } else if (e.key === "Escape") {
            setOpen(false)
          }
        }}
      />
      {open && hits.length > 0 && (
        <ul className="absolute left-0 right-0 z-30 mt-1 max-h-64 overflow-y-auto rounded-lg border bg-card py-1 text-sm shadow-lg">
          {hits.map((h, i) => (
            <li key={h.symbol}>
              <button
                type="button"
                className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-accent ${i === active ? "bg-accent" : ""}`}
                onMouseDown={(e) => {
                  e.preventDefault()
                  pick(h)
                }}
              >
                <span className="font-semibold">{h.symbol}</span>
                <span className="truncate text-xs text-muted-foreground">{h.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
