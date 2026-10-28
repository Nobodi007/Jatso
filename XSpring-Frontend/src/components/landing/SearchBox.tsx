import { useEffect, useMemo, useRef, useState } from "react"
import { Search } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"

const API_BASE_URL = "https://xspring-api.onrender.com"
const TAB_KEY = "nobodi:searchTab"

type Tab = "crypto" | "stocks"
type CoinRow = { asset: string; name: string; price: number; change: number }
type StockRow = { symbol: string; name: string; price: number | null; changePercent: number | null }
type RemoteStock = { symbol: string; name: string; type: string }
type RemoteResult = { term: string; status: "ok" | "busy" | "error"; items: RemoteStock[] }

const fmtCoin = (v: number, locale: string) =>
  v.toLocaleString(locale, { maximumFractionDigits: v < 1 ? 4 : 2 })

const fmtUsd = (v: number, locale: string) =>
  v.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// จำแท็บล่าสุดที่ผู้ใช้เลือก (ครั้งแรกเป็นคริปโต)
const readTab = (): Tab => {
  try {
    return localStorage.getItem(TAB_KEY) === "stocks" ? "stocks" : "crypto"
  } catch {
    return "crypto"
  }
}

export default function SearchBox({
  onSelect,
  onSelectStock,
}: {
  onSelect: (asset: string) => void
  onSelectStock: (symbol: string) => void
}) {
  const { t, lang } = useLanguage()
  const locale = lang === "th" ? "th-TH" : "en-US"
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<Tab>(readTab)
  const [q, setQ] = useState("")
  const [coins, setCoins] = useState<CoinRow[] | null>(null)
  const [coinError, setCoinError] = useState(false)
  const [stocks, setStocks] = useState<StockRow[] | null>(null)
  const [stockError, setStockError] = useState(false)
  const [remote, setRemote] = useState<RemoteResult | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const term = q.trim()

  // โหลดรายชื่อเหรียญครั้งแรกที่เปิดแท็บคริปโต
  useEffect(() => {
    if (!open || tab !== "crypto" || coins) return
    const ctrl = new AbortController()
    setCoinError(false)
    fetch(`${API_BASE_URL}/api/public/markets`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setCoins(Array.isArray(d.rows) ? d.rows : []))
      .catch((e) => {
        if (e.name !== "AbortError") setCoinError(true)
      })
    return () => ctrl.abort()
  }, [open, tab, coins])

  // โหลดรายการหุ้นยอดนิยมครั้งแรกที่เปิดแท็บหุ้น (เซิร์ฟเวอร์ cache ก้อนเดียวให้ทุกคน)
  useEffect(() => {
    if (!open || tab !== "stocks" || stocks) return
    const ctrl = new AbortController()
    setStockError(false)
    fetch(`${API_BASE_URL}/api/stocks/public/market`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setStocks(Array.isArray(d.rows) ? d.rows : []))
      .catch((e) => {
        if (e.name !== "AbortError") setStockError(true)
      })
    return () => ctrl.abort()
  }, [open, tab, stocks])

  // โฟกัสช่องพิมพ์เมื่อเปิดหรือสลับแท็บ
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open, tab])

  // ปิดเมื่อคลิกข้างนอกหรือกด Esc
  useEffect(() => {
    if (!open) return
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

  const coinResults = useMemo(() => {
    const s = term.toLowerCase()
    if (!coins) return []
    if (!s) return coins
    return coins.filter((r) => r.asset.toLowerCase().includes(s) || r.name.toLowerCase().includes(s))
  }, [coins, term])

  const stockResults = useMemo(() => {
    const s = term.toLowerCase()
    if (!stocks) return []
    if (!s) return stocks
    return stocks.filter((r) => r.symbol.toLowerCase().includes(s) || r.name.toLowerCase().includes(s))
  }, [stocks, term])

  // ถ้าไม่เจอในรายการยอดนิยม และพิมพ์ตั้งแต่ 2 ตัวอักษร ค่อยถามเซิร์ฟเวอร์ (หน่วง 400 ms)
  const needsRemote = open && tab === "stocks" && !!stocks && term.length >= 2 && stockResults.length === 0
  useEffect(() => {
    if (!needsRemote) return
    const ctrl = new AbortController()
    const id = setTimeout(() => {
      fetch(`${API_BASE_URL}/api/stocks/public/market/search?q=${encodeURIComponent(term)}`, { signal: ctrl.signal })
        .then(async (r) => {
          if (r.status === 503) return setRemote({ term, status: "busy", items: [] })
          if (!r.ok) throw new Error(String(r.status))
          const d = await r.json()
          setRemote({ term, status: "ok", items: Array.isArray(d) ? d : [] })
        })
        .catch((e) => {
          if (e.name !== "AbortError") setRemote({ term, status: "error", items: [] })
        })
    }, 400)
    return () => {
      clearTimeout(id)
      ctrl.abort()
    }
  }, [needsRemote, term])
  const remoteReady = remote && remote.term === term ? remote : null

  const switchTab = (next: Tab) => {
    setTab(next)
    setQ("")
    try {
      localStorage.setItem(TAB_KEY, next)
    } catch {
      /* localStorage ใช้ไม่ได้ก็ข้ามไป */
    }
  }

  const pickCoin = (asset: string) => {
    setOpen(false)
    setQ("")
    onSelect(asset)
  }
  const pickStock = (symbol: string) => {
  try {
    sessionStorage.setItem("pendingStock", symbol)
  } catch {
    /* sessionStorage ใช้ไม่ได้ก็ข้ามไป */
  }
  setOpen(false)
  setQ("")
  onSelectStock(symbol)
}

  const onEnter = () => {
    if (tab === "crypto") {
      if (coinResults[0]) pickCoin(coinResults[0].asset)
    } else {
      const first = stockResults[0]?.symbol ?? remoteReady?.items[0]?.symbol
      if (first) pickStock(first)
    }
  }

  const msg = "px-3 py-3 text-sm text-muted-foreground"

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        aria-label={t("search.aria")}
        onClick={() => setOpen((v) => !v)}
        className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Search className="h-4 w-4" />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border bg-background p-2 shadow-xl">
          <div role="tablist" className="mb-2 grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
            {(["crypto", "stocks"] as Tab[]).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={tab === k}
                onClick={() => switchTab(k)}
                className={`rounded-md px-2 py-1.5 text-xs font-medium ${
                  tab === k ? "bg-emerald-500 text-black" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t(k === "crypto" ? "search.tabCrypto" : "search.tabStocks")}
              </button>
            ))}
          </div>

          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onEnter()
            }}
            placeholder={t(tab === "crypto" ? "search.placeholder" : "search.placeholderStock")}
            className="w-full rounded-md border bg-transparent px-3 py-2 text-sm outline-none focus:border-emerald-500"
          />

          <div className="mt-2 max-h-80 overflow-y-auto">
            {tab === "crypto" && (
              <>
                {coinError && <p className="px-3 py-3 text-sm text-red-500">{t("search.loadFailed")}</p>}
                {!coinError && !coins && <p className={msg}>{t("search.loading")}</p>}
                {coins && coinResults.length === 0 && <p className={msg}>{t("search.notFound")}</p>}
                {!term && coinResults.length > 0 && (
                  <p className="px-3 pb-1 pt-2 text-xs text-muted-foreground">{t("search.all")}</p>
                )}
                {coinResults.map((r) => (
                  <button
                    key={r.asset}
                    type="button"
                    onClick={() => pickCoin(r.asset)}
                    className="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-accent"
                  >
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold">{r.asset}</span>
                      <span className="block truncate text-xs text-muted-foreground">{r.name}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-sm">฿{fmtCoin(r.price, locale)}</span>
                      <span className={`block text-xs ${r.change >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                        {r.change >= 0 ? "+" : ""}
                        {r.change.toFixed(2)}%
                      </span>
                    </span>
                  </button>
                ))}
              </>
            )}

            {tab === "stocks" && (
              <>
                {stockError && <p className="px-3 py-3 text-sm text-red-500">{t("search.loadFailedStock")}</p>}
                {!stockError && !stocks && <p className={msg}>{t("search.loading")}</p>}
                {!term && stockResults.length > 0 && (
                  <p className="px-3 pb-1 pt-2 text-xs text-muted-foreground">{t("search.popularStocks")}</p>
                )}
                {stockResults.map((r) => (
                  <button
                    key={r.symbol}
                    type="button"
                    onClick={() => pickStock(r.symbol)}
                    className="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-accent"
                  >
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold">{r.symbol}</span>
                      <span className="block truncate text-xs text-muted-foreground">{r.name}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-sm">{r.price == null ? "—" : `$${fmtUsd(r.price, locale)}`}</span>
                      <span
                        className={`block text-xs ${
                          r.changePercent == null
                            ? "text-muted-foreground"
                            : r.changePercent >= 0
                              ? "text-emerald-500"
                              : "text-red-500"
                        }`}
                      >
                        {r.changePercent == null
                          ? "—"
                          : `${r.changePercent >= 0 ? "+" : ""}${r.changePercent.toFixed(2)}%`}
                      </span>
                    </span>
                  </button>
                ))}

                {stocks && stockResults.length === 0 && !needsRemote && <p className={msg}>{t("search.notFoundStock")}</p>}
                {needsRemote && !remoteReady && <p className={msg}>{t("search.searching")}</p>}
                {remoteReady?.status === "busy" && <p className={msg}>{t("search.busy")}</p>}
                {remoteReady?.status === "error" && (
                  <p className="px-3 py-3 text-sm text-red-500">{t("search.loadFailedStock")}</p>
                )}
                {remoteReady?.status === "ok" && remoteReady.items.length === 0 && (
                  <p className={msg}>{t("search.notFoundStock")}</p>
                )}
                {remoteReady?.items.map((r) => (
                  <button
                    key={r.symbol}
                    type="button"
                    onClick={() => pickStock(r.symbol)}
                    className="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left hover:bg-accent"
                  >
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold">{r.symbol}</span>
                      <span className="block truncate text-xs text-muted-foreground">{r.name}</span>
                    </span>
                    {r.type && <span className="shrink-0 text-xs text-muted-foreground">{r.type}</span>}
                  </button>
                ))}

                <p className="px-3 pb-1 pt-2 text-xs text-muted-foreground">{t("search.stockCta")}</p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
