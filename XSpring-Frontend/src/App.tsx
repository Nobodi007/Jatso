import TradingViewChart from "./components/trading/TradingViewChart"
import { useEffect, useState } from "react"
import {
  LayoutDashboard,
  CandlestickChart,
  ArrowLeftRight,
  BookOpen,
  Wallet,
  ClipboardList,
  BarChart3,
  ShieldAlert,
  FlaskConical,
  Newspaper,
  Settings,
  Menu,
  Search,
  Bell,
  ChevronDown,
  TrendingUp,
  TrendingDown,
} from "lucide-react"

type Page =
  | "dashboard"
  | "markets"
  | "trade"
  | "orderbook"
  | "portfolio"
  | "wallet"
  | "orders"
  | "positions"
  | "risk"
  | "quant"
  | "news"
  | "settings"

type Asset = string
type OrderSide = "BUY" | "SELL"

type PortfolioHolding = {
  asset: string
  qty: number
  avg_cost: number
  price: number
  market_value: number
  cost_basis: number
  unrealized_pnl: number
  allocation_pct: number
  pnl_pct: number
}

type PortfolioData = {
  cash_thb: number
  market_value_thb: number
  total_value_thb: number
  realized_pnl_thb: number
  unrealized_pnl_thb: number
  total_pnl_thb: number
  pnl_pct: number
  fees_thb: number
  holdings: PortfolioHolding[]
}

const API_BASE_URL = "https://xspring-api.onrender.com"
const DEALER_API_KEY = String(import.meta.env.VITE_DEALER_API_KEY || "").trim()

function formatTHB(value: number) {
  return `฿${Number(value || 0).toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function formatQty(value: number) {
  return Number(value || 0).toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 8,
  })
}


type NavigationItem = {
  id: Page
  label: string
  icon: typeof LayoutDashboard
  count?: number
}

const navigation: NavigationItem[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
  },
  {
    id: "markets",
    label: "Markets",
    icon: CandlestickChart,
  },
  {
    id: "trade",
    label: "Trade",
    icon: ArrowLeftRight,
  },
  {
    id: "orderbook",
    label: "Order Book",
    icon: BookOpen,
  },
  {
    id: "portfolio",
    label: "Portfolio",
    icon: Wallet,
  },
  {
    id: "wallet",
    label: "Wallet",
    icon: Wallet,
  },
  {
    id: "orders",
    label: "Orders",
    icon: ClipboardList,
    count: 3,
  },
  {
    id: "positions",
    label: "Positions",
    icon: BarChart3,
  },
  {
    id: "risk",
    label: "Risk Center",
    icon: ShieldAlert,
  },
  {
    id: "quant",
    label: "Quant Lab",
    icon: FlaskConical,
  },
  {
    id: "news",
    label: "News",
    icon: Newspaper,
  },
  {
    id: "settings",
    label: "Settings",
    icon: Settings,
  },
]

const marketData: Record<
  Asset,
  {
    name: string
    price: number
    change: number
    bid: number
    ask: number
    high: number
    low: number
    volume: number
  }
> = {
  BTC: {
    name: "Bitcoin",
    price: 3684250,
    change: 2.34,
    bid: 3684000,
    ask: 3684500,
    high: 3721000,
    low: 3598000,
    volume: 124.52,
  },

  ETH: {
    name: "Ethereum",
    price: 128450,
    change: 1.82,
    bid: 128400,
    ask: 128500,
    high: 130200,
    low: 125800,
    volume: 2840.31,
  },

  SOL: {
    name: "Solana",
    price: 6240,
    change: -0.74,
    bid: 6238,
    ask: 6242,
    high: 6380,
    low: 6120,
    volume: 18420.5,
  },

  XRP: {
    name: "XRP",
    price: 82.45,
    change: 3.12,
    bid: 82.42,
    ask: 82.48,
    high: 84.2,
    low: 79.8,
    volume: 4820000,
  },
}

/* =========================================================
   APP
========================================================= */

function App() {
  const [page, setPage] = useState<Page>("dashboard")
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null)
  const [portfolioLoading, setPortfolioLoading] = useState(false)
  const [portfolioError, setPortfolioError] = useState("")
  const [orderRefreshKey, setOrderRefreshKey] = useState(0)

  const notifyOrderCreated = () => {
    setOrderRefreshKey((value) => value + 1)
  }

  const loadPortfolio = async () => {
    setPortfolioLoading(true)
    setPortfolioError("")

    try {
      const response = await fetch(`${API_BASE_URL}/api/portfolio`, {
        method: "GET",
        headers: {
          Accept: "application/json",
          "X-API-Key": DEALER_API_KEY,
        },
      })

      const body = await response.json()

      if (!response.ok || body?.status !== "ok" || !body?.portfolio) {
        const detail = body?.detail

        // Backend diagnostic: keep the original safety message, but expose
        // the real load failure so we can fix the Supabase/gu.py path.
        if (detail && typeof detail === "object") {
          const diagnostic = detail.diagnostic
          const diagnosticText = diagnostic
            ? `\n\nDiagnostic:\n${JSON.stringify(diagnostic, null, 2)}`
            : ""

          throw new Error(
            `${detail.message || "ไม่สามารถโหลด Portfolio จาก Backend ได้"}${diagnosticText}`
          )
        }

        throw new Error(
          typeof detail === "string"
            ? detail
            : "ไม่สามารถโหลด Portfolio จาก Backend ได้"
        )
      }

      setPortfolio(body.portfolio as PortfolioData)
    } catch (error) {
      setPortfolioError(
        error instanceof Error
          ? error.message
          : "ไม่สามารถโหลด Portfolio จาก Backend ได้"
      )
    } finally {
      setPortfolioLoading(false)
    }
  }

  useEffect(() => {
    loadPortfolio()
  }, [])

  const currentPage = navigation.find(
    (item) => item.id === page
  )

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="flex min-h-screen">

        {/* =================================================
            SIDEBAR
        ================================================= */}

        {sidebarOpen && (
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
            className="mobile-sidebar-backdrop"
          />
        )}

        <aside
          className={`mobile-sidebar border-r bg-card transition-all duration-200 ${
            sidebarOpen ? "mobile-sidebar-open w-64" : "mobile-sidebar-closed w-16"
          }`}
        >
          {/* LOGO */}

          <div className="flex h-16 items-center border-b px-4">

            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary font-bold text-primary-foreground">
              X
            </div>

            {sidebarOpen && (
              <div className="ml-3 min-w-0">

                <div className="truncate text-sm font-semibold">
                  XSpring
                </div>

                <div className="truncate text-xs text-muted-foreground">
                  Dealer Suite
                </div>

              </div>
            )}

          </div>


          {/* NAVIGATION */}

          <nav className="space-y-1 p-2">

            {navigation.map((item) => {

              const Icon = item.icon
              const active = page === item.id

              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setPage(item.id)
                    if (window.innerWidth < 768) {
                      setSidebarOpen(false)
                    }
                  }}
                  className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground"
                  }`}
                >

                  <Icon className="size-4 shrink-0" />

                  {sidebarOpen && (
                    <>
                      <span className="flex-1 truncate">
                        {item.label}
                      </span>

                      {item.count !== undefined && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            active
                              ? "bg-primary-foreground/20"
                              : "bg-muted"
                          }`}
                        >
                          {item.count}
                        </span>
                      )}
                    </>
                  )}

                </button>
              )
            })}

          </nav>
        </aside>


        {/* =================================================
            MAIN
        ================================================= */}

        <div className="mobile-main flex min-w-0 flex-1 flex-col">

          {/* =================================================
              TOPBAR
          ================================================= */}

          <header className="flex h-16 items-center gap-3 border-b bg-background px-4">

            {/* SIDEBAR TOGGLE */}

            <button
              onClick={() =>
                setSidebarOpen(!sidebarOpen)
              }
              className="rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Menu className="size-5" />
            </button>


            {/* PAGE TITLE */}

            <div className="flex-1">

              <h1 className="text-sm font-semibold">
                {currentPage?.label}
              </h1>

            </div>


            {/* SEARCH */}

            <button
              className="rounded-lg p-2 text-muted-foreground hover:bg-accent"
              aria-label="Search"
            >
              <Search className="size-5" />
            </button>


            {/* NOTIFICATION */}

            <button
              className="rounded-lg p-2 text-muted-foreground hover:bg-accent"
              aria-label="Notifications"
            >
              <Bell className="size-5" />
            </button>


            {/* USER */}

            <div className="ml-2 flex size-8 items-center justify-center rounded-full bg-muted text-xs font-semibold">
              N
            </div>

          </header>


          {/* =================================================
              CONTENT
          ================================================= */}

          <main className="min-w-0 flex-1 overflow-auto p-4 sm:p-6">

            {page === "dashboard" && (
              <Dashboard
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
                onTrade={() => setPage("trade")}
              />
            )}

            {page === "trade" && (
              <TradePage
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
                onOrderCreated={notifyOrderCreated}
              />
            )}

            {page === "orderbook" && <OrderBookPage />}

            {page === "wallet" && (
              <WalletPage
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
              />
            )}

            {page === "portfolio" && (
              <PortfolioPage
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
              />
            )}

            {page === "orders" && (
              <OrdersPage refreshKey={orderRefreshKey} />
            )}

            {page === "positions" && (
              <PositionsPage
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
              />
            )}

            {page === "risk" && (
              <RiskCenterPage
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
              />
            )}

            {page === "quant" && (
              <QuantLabPage
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
              />
            )}

            {page === "news" && <NewsPage />}

            {page !== "dashboard" &&
              page !== "trade" &&
              page !== "orderbook" &&
              page !== "portfolio" &&
              page !== "wallet" &&
              page !== "orders" &&
              page !== "positions" &&
              page !== "risk" &&
              page !== "quant" &&
              page !== "news" && (
                <PlaceholderPage
                  title={currentPage?.label ?? ""}
                />
              )}

          </main>

        </div>

      </div>
    </div>
  )
}


/* =========================================================
   WALLET
========================================================= */

function WalletPage({
  portfolio,
  loading,
  error,
  onRefresh,
}: {
  portfolio: PortfolioData | null
  loading: boolean
  error: string
  onRefresh: () => void
}) {
  const holdings = (portfolio?.holdings || [])
    .filter((item) => Number(item.qty || 0) > 0)
    .sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0))

  const cash = Number(portfolio?.cash_thb || 0)
  const marketValue = Number(portfolio?.market_value_thb || 0)
  const totalValue = Number(portfolio?.total_value_thb || 0)
  const totalPnl = Number(portfolio?.total_pnl_thb || 0)
  const fees = Number(portfolio?.fees_thb || 0)
  const cashRatio = totalValue > 0 ? (cash / totalValue) * 100 : 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Wallet</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            ยอดเงินและสินทรัพย์จาก Portfolio Backend จริง
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard title="Total Equity" value={loading ? "Loading..." : formatTHB(totalValue)} change="Cash + Market Value" />
        <StatCard title="Available Cash" value={loading ? "Loading..." : formatTHB(cash)} change={`${cashRatio.toFixed(2)}% ของพอร์ต`} />
        <StatCard title="Crypto Value" value={loading ? "Loading..." : formatTHB(marketValue)} change={`${holdings.length} assets`} />
        <StatCard title="Total P&L" value={loading ? "Loading..." : formatTHB(totalPnl)} change={loading ? "—" : `${Number(portfolio?.pnl_pct || 0) >= 0 ? "+" : ""}${Number(portfolio?.pnl_pct || 0).toFixed(2)}%`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="rounded-xl border bg-card p-5 xl:col-span-2">
          <div className="flex items-center justify-between border-b pb-4">
            <div>
              <h3 className="font-semibold">Asset Balances</h3>
              <p className="mt-1 text-xs text-muted-foreground">สินทรัพย์ที่ถืออยู่จริง</p>
            </div>
            <span className="text-xs text-muted-foreground">{holdings.length} assets</span>
          </div>

          {loading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">กำลังโหลด Wallet...</div>
          ) : holdings.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground">ยังไม่มีสินทรัพย์ที่ถืออยู่</div>
          ) : (
            <div className="divide-y">
              {holdings.map((item) => {
                const pnl = Number(item.unrealized_pnl || 0)
                const positive = pnl >= 0
                return (
                  <div key={item.asset} className="flex flex-wrap items-center justify-between gap-4 py-4">
                    <div className="flex min-w-[150px] items-center gap-3">
                      <CoinLogo asset={item.asset} size={36} />
                      <div>
                        <div className="font-semibold">{item.asset}/THB</div>
                        <div className="mt-1 text-xs text-muted-foreground">{formatQty(Number(item.qty || 0))} units</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-medium">{formatTHB(Number(item.market_value || 0))}</div>
                      <div className="mt-1 text-xs text-muted-foreground">Avg {formatTHB(Number(item.avg_cost || 0))}</div>
                    </div>
                    <div className={`text-right text-sm ${positive ? "text-emerald-500" : "text-red-500"}`}>
                      {positive ? "+" : ""}{formatTHB(pnl)}
                      <div className="text-xs">{positive ? "+" : ""}{Number(item.pnl_pct || 0).toFixed(2)}%</div>
                    </div>
                    <div className="text-right text-xs text-muted-foreground">
                      {Number(item.allocation_pct || 0).toFixed(2)}%
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="rounded-xl border bg-card p-5">
          <h3 className="font-semibold">Wallet Summary</h3>
          <div className="mt-5 space-y-4">
            <MiniStat label="Cash / THB" value={formatTHB(cash)} />
            <MiniStat label="Crypto Market Value" value={formatTHB(marketValue)} />
            <MiniStat label="Total Equity" value={formatTHB(totalValue)} />
            <MiniStat label="Fees Paid" value={formatTHB(fees)} />
            <MiniStat label="Cash Ratio" value={`${cashRatio.toFixed(2)}%`} />
          </div>
        </div>
      </div>
    </div>
  )
}


/* =========================================================
   ORDER BOOK — BITKUB PUBLIC DEPTH
========================================================= */

type OrderBookLevel = {
  price_thb: number
  quantity: number
  total_thb: number
}

type OrderBookResponse = {
  status?: string
  asset?: string
  symbol?: string
  quote?: string
  source?: string
  timestamp?: string
  best_bid_thb?: number
  best_ask_thb?: number
  mid_price_thb?: number
  spread_thb?: number
  spread_pct?: number
  bids?: OrderBookLevel[]
  asks?: OrderBookLevel[]
}

const ORDERBOOK_ASSETS = ["BTC", "ETH", "SOL", "DOGE", "ADA", "HBAR", "LINK", "XLM", "XRP"]

const COIN_LOGOS: Record<string, { slug: string; color: string }> = {
  BTC: { slug: "bitcoin", color: "F7931A" },
  ETH: { slug: "ethereum", color: "627EEA" },
  SOL: { slug: "solana", color: "9945FF" },
  DOGE: { slug: "dogecoin", color: "C2A633" },
  ADA: { slug: "cardano", color: "0033AD" },
  HBAR: { slug: "hedera", color: "000000" },
  LINK: { slug: "chainlink", color: "2A5ADA" },
  XLM: { slug: "stellar", color: "7D00FF" },
  XRP: { slug: "ripple", color: "23292F" },
}

function CoinLogo({
  asset,
  size = 24,
  className = "",
}: {
  asset: string
  size?: number
  className?: string
}) {
  const symbol = String(asset || "").toUpperCase()
  const logo = COIN_LOGOS[symbol]
  const [failed, setFailed] = useState(false)

  if (!logo || failed) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-foreground ${className}`}
        style={{ width: size, height: size }}
        aria-hidden="true"
      >
        {symbol.slice(0, 3)}
      </span>
    )
  }

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-white ${className}`}
      style={{ width: size, height: size }}
    >
      <img
        src={`https://cdn.simpleicons.org/${logo.slug}/${logo.color}`}
        alt=""
        width={size - 4}
        height={size - 4}
        className="block"
        onError={() => setFailed(true)}
        aria-hidden="true"
      />
    </span>
  )
}

function formatOrderBookPrice(value: number) {
  const n = Number(value || 0)
  if (!Number.isFinite(n) || n <= 0) return "—"
  return `฿${n.toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function formatOrderBookQty(value: number) {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return "—"
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 8,
  })
}

function formatOrderBookTotal(value: number) {
  const n = Number(value || 0)
  if (!Number.isFinite(n) || n < 0) return "—"
  return `฿${n.toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function OrderBookPage() {
  const [asset, setAsset] = useState("BTC")
  const [book, setBook] = useState<OrderBookResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [lastUpdated, setLastUpdated] = useState("")

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError("")

      try {
        if (!DEALER_API_KEY) {
          throw new Error("ยังไม่ได้ตั้ง VITE_DEALER_API_KEY ใน Frontend (.env)")
        }

        const response = await fetch(
          `${API_BASE_URL}/api/orderbook?asset=${encodeURIComponent(asset)}&limit=20`,
          {
            method: "GET",
            headers: {
              Accept: "application/json",
              "X-API-Key": DEALER_API_KEY,
            },
            cache: "no-store",
          }
        )

        const body = await response.json().catch(() => ({}))

        if (!response.ok || body?.status !== "ok") {
          const detail = body?.detail
          throw new Error(
            typeof detail === "string"
              ? detail
              : detail?.message || `โหลด Order Book ไม่สำเร็จ (${response.status})`
          )
        }

        if (!cancelled) {
          setBook(body as OrderBookResponse)
          setLastUpdated(new Date().toLocaleTimeString("th-TH"))
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "โหลด Order Book ไม่สำเร็จ")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const timer = window.setInterval(load, 3000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [asset])

  const bids = Array.isArray(book?.bids) ? book!.bids! : []
  const asks = Array.isArray(book?.asks) ? book!.asks! : []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Order Book</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Live market depth จาก Bitkub Public API
          </p>
        </div>

        <div className="flex max-w-full gap-2 overflow-x-auto pb-1">
          {ORDERBOOK_ASSETS.map((item) => {
            const active = asset === item
            return (
              <button
                key={item}
                type="button"
                onClick={() => setAsset(item)}
                aria-label={`${item}/THB`}
                className={`flex shrink-0 items-center gap-2 rounded-xl border px-3.5 py-2 text-sm font-medium transition-all ${
                  active
                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                    : "bg-card hover:bg-accent"
                }`}
              >
                <CoinLogo asset={item} size={22} />
                <span>{item}/THB</span>
              </button>
            )
          })}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
        <div className="rounded-xl border bg-card p-5">
          <div className="text-sm text-muted-foreground">Best Bid</div>
          <div className="mt-2 text-xl font-semibold">
            {formatOrderBookPrice(book?.best_bid_thb || 0)}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">{asset}/THB</div>
        </div>

        <div className="rounded-xl border bg-card p-5">
          <div className="text-sm text-muted-foreground">Best Ask</div>
          <div className="mt-2 text-xl font-semibold">
            {formatOrderBookPrice(book?.best_ask_thb || 0)}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">{asset}/THB</div>
        </div>

        <div className="rounded-xl border bg-card p-5">
          <div className="text-sm text-muted-foreground">Mid Price</div>
          <div className="mt-2 text-xl font-semibold">
            {formatOrderBookPrice(book?.mid_price_thb || 0)}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">THB</div>
        </div>

        <div className="rounded-xl border bg-card p-5">
          <div className="text-sm text-muted-foreground">Spread</div>
          <div className="mt-2 text-xl font-semibold">
            {formatOrderBookPrice(book?.spread_thb || 0)}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {Number(book?.spread_pct || 0).toFixed(4)}%
          </div>
        </div>
      </div>

      <div className="rounded-xl border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="font-semibold">{asset}/THB Market Depth</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Real-time bids / asks · Auto refresh 3s
            </p>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            <div>{loading ? "Connecting..." : error ? "Disconnected" : "Connected"}</div>
            {lastUpdated && <div>Updated · {lastUpdated}</div>}
          </div>
        </div>

        <div className="mt-5 grid gap-6 lg:grid-cols-2">
          <div>
            <div className="mb-2 text-sm font-semibold">Asks</div>
            <div className="overflow-hidden rounded-lg border">
              <div className="grid grid-cols-3 border-b px-3 py-2 text-xs font-medium text-muted-foreground">
                <div>Price</div><div className="text-right">Amount</div><div className="text-right">Total</div>
              </div>
              {asks.length === 0 ? (
                <div className="px-3 py-8 text-center text-sm text-muted-foreground">No asks</div>
              ) : asks.map((item, index) => (
                <div key={`ask-${index}`} className="grid grid-cols-3 border-b px-3 py-2 text-sm last:border-b-0">
                  <div className="font-medium">{formatOrderBookPrice(item.price_thb)}</div>
                  <div className="text-right">{formatOrderBookQty(item.quantity)}</div>
                  <div className="text-right">{formatOrderBookPrice(item.total_thb)}</div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 text-sm font-semibold">Bids</div>
            <div className="overflow-hidden rounded-lg border">
              <div className="grid grid-cols-3 border-b px-3 py-2 text-xs font-medium text-muted-foreground">
                <div>Price</div><div className="text-right">Amount</div><div className="text-right">Total</div>
              </div>
              {bids.length === 0 ? (
                <div className="px-3 py-8 text-center text-sm text-muted-foreground">No bids</div>
              ) : bids.map((item, index) => (
                <div key={`bid-${index}`} className="grid grid-cols-3 border-b px-3 py-2 text-sm last:border-b-0">
                  <div className="font-medium">{formatOrderBookPrice(item.price_thb)}</div>
                  <div className="text-right">{formatOrderBookQty(item.quantity)}</div>
                  <div className="text-right">{formatOrderBookPrice(item.total_thb)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 text-sm md:grid-cols-2">
          <div className="rounded-lg border p-3">
            <div className="text-xs text-muted-foreground">Source</div>
            <div className="mt-1 font-medium">{book?.source || "Bitkub Public Order Book"}</div>
          </div>
          <div className="rounded-lg border p-3">
            <div className="text-xs text-muted-foreground">Symbol / Quote</div>
            <div className="mt-1 font-medium">{book?.symbol || `${asset}_THB`} · {book?.quote || "THB"}</div>
          </div>
        </div>
      </div>
    </div>
  )
}


/* =========================================================
   DASHBOARD
========================================================= */

function Dashboard({
  portfolio,
  loading,
  error,
  onRefresh,
  onTrade,
}: {
  portfolio: PortfolioData | null
  loading: boolean
  error: string
  onRefresh: () => void
  onTrade: () => void
}) {
  const [selectedAsset, setSelectedAsset] = useState<Asset>("BTC")
  const [recentOrders, setRecentOrders] = useState<OrderHistoryRow[]>([])
  const [ordersLoading, setOrdersLoading] = useState(true)

  const holdings = [...(portfolio?.holdings || [])]
    .filter((item) => Number(item.qty || 0) > 0)
    .sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0))

  const openPositions = holdings.length
  const totalValue = Number(portfolio?.total_value_thb || 0)
  const cash = Number(portfolio?.cash_thb || 0)
  const marketValue = Number(portfolio?.market_value_thb || 0)
  const totalPnl = Number(portfolio?.total_pnl_thb || 0)
  const pnlPct = Number(portfolio?.pnl_pct || 0)
  const pnlPositive = totalPnl >= 0

  const selectedHolding = holdings.find(
    (item) => item.asset.toUpperCase() === selectedAsset
  )

  useEffect(() => {
    let cancelled = false

    const loadRecentOrders = async () => {
      setOrdersLoading(true)

      try {
        if (!DEALER_API_KEY) {
          setRecentOrders([])
          return
        }

        const response = await fetch(
          `${API_BASE_URL}/api/orders?limit=5`,
          {
            headers: {
              Accept: "application/json",
              "X-API-Key": DEALER_API_KEY,
            },
            cache: "no-store",
          }
        )

        const body = await response.json()

        if (!response.ok || body?.status !== "ok") {
          throw new Error("Unable to load orders")
        }

        const rows = Array.isArray(body?.orders)
          ? (body.orders as OrderHistoryRow[])
          : []

        rows.sort((a, b) => {
          const dateA = parseOrderDate(a.timestamp || a.date)?.getTime() ?? NaN
          const dateB = parseOrderDate(b.timestamp || b.date)?.getTime() ?? NaN
          if (Number.isFinite(dateA) && Number.isFinite(dateB)) {
            return dateB - dateA
          }
          return 0
        })

        if (!cancelled) {
          setRecentOrders(rows.slice(0, 5))
        }
      } catch {
        if (!cancelled) {
          setRecentOrders([])
        }
      } finally {
        if (!cancelled) {
          setOrdersLoading(false)
        }
      }
    }

    loadRecentOrders()

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="space-y-6">

      {/* HEADER */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Dashboard</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            ภาพรวมพอร์ต การซื้อขาย และตลาดของ XSpring Dealer Suite
          </p>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      {/* ERROR */}
      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm">
          <span className="break-words text-red-500">{error}</span>
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-accent"
          >
            Retry
          </button>
        </div>
      )}

      {/* KPI */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Total Equity"
          value={loading ? "Loading..." : formatTHB(totalValue)}
          change="Cash + Crypto"
        />

        <StatCard
          title="Available Cash"
          value={loading ? "Loading..." : formatTHB(cash)}
          change={
            totalValue > 0
              ? `${((cash / totalValue) * 100).toFixed(1)}% of equity`
              : "THB"
          }
        />

        <StatCard
          title="Crypto Value"
          value={loading ? "Loading..." : formatTHB(marketValue)}
          change={`${openPositions} open positions`}
        />

        <StatCard
          title="Total P&L"
          value={loading ? "Loading..." : formatTHB(totalPnl)}
          change={
            loading
              ? "—"
              : `${pnlPositive ? "+" : ""}${pnlPct.toFixed(2)}%`
          }
        />
      </div>

      {/* MARKET + QUICK TRADE */}
      <div className="grid gap-4 xl:grid-cols-3">

        <div className="rounded-xl border bg-card p-5 xl:col-span-2">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold">Market Overview</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                TradingView market view
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              {(["BTC", "ETH", "SOL", "XRP"] as Asset[]).map((symbol) => (
                <button
                  key={symbol}
                  type="button"
                  onClick={() => setSelectedAsset(symbol)}
                  className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    selectedAsset === symbol
                      ? "bg-primary text-primary-foreground"
                      : "border hover:bg-accent"
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <CoinLogo asset={symbol} size={18} />
                    {symbol}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-hidden rounded-lg bg-muted/20">
            <TradingViewChart
              symbol={`BITKUB:${selectedAsset}THB`}
              interval="60"
              height={330}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{selectedAsset}/THB · 1H</span>
            <span>
              {selectedHolding
                ? `Current ${formatTHB(selectedHolding.price)}`
                : "No position"}
            </span>
          </div>
        </div>

        <div className="rounded-xl border bg-card p-5">
          <div className="mb-4">
            <h3 className="font-semibold">Quick Trade</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              เข้าหน้า Trade พร้อมเลือกสินทรัพย์
            </p>
          </div>

          <div className="space-y-2">
            {(["BTC", "ETH", "SOL", "XRP"] as Asset[]).map((symbol) => {
              const holding = holdings.find(
                (item) => item.asset.toUpperCase() === symbol
              )

              return (
                <button
                  key={symbol}
                  type="button"
                  onClick={() => setSelectedAsset(symbol)}
                  className="flex w-full items-center justify-between rounded-lg border px-3 py-3 text-left hover:bg-accent"
                >
                  <div className="flex items-center gap-2">
                    <CoinLogo asset={symbol} size={24} />
                    <div className="font-medium">{symbol}/THB</div>
                    <div className="text-xs text-muted-foreground">
                      {holding
                        ? `${formatQty(holding.qty)} ${symbol}`
                        : "No position"}
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-sm">
                      {holding ? formatTHB(holding.price) : "—"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {holding
                        ? `${Number(holding.allocation_pct || 0).toFixed(1)}% allocation`
                        : "Available"}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={onTrade}
              className="rounded-lg bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90"
            >
              Trade
            </button>

            <button
              type="button"
              onClick={onRefresh}
              className="rounded-lg border px-3 py-2.5 text-sm font-medium hover:bg-accent"
            >
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* HOLDINGS + RECENT ORDERS */}
      <div className="grid gap-4 xl:grid-cols-2">

        <div className="rounded-xl border bg-card p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold">Top Holdings</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                สินทรัพย์ตามมูลค่าในพอร์ต
              </p>
            </div>

            <span className="rounded-full bg-muted px-2.5 py-1 text-[10px]">
              {holdings.length} Assets
            </span>
          </div>

          {loading ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              กำลังโหลดพอร์ต...
            </div>
          ) : holdings.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              ยังไม่มีสินทรัพย์ในพอร์ต
            </div>
          ) : (
            <div className="space-y-2">
              {holdings.slice(0, 5).map((holding) => {
                const positive = Number(holding.unrealized_pnl || 0) >= 0

                return (
                  <button
                    key={holding.asset}
                    type="button"
                    onClick={() =>
                      setSelectedAsset(holding.asset.toUpperCase() as Asset)
                    }
                    className="flex w-full items-center justify-between rounded-lg px-3 py-3 text-left hover:bg-accent"
                  >
                    <div className="flex items-center gap-3">
                      <CoinLogo asset={holding.asset} size={36} />

                      <div>
                        <div className="font-medium">{holding.asset}/THB</div>
                        <div className="text-xs text-muted-foreground">
                          {formatQty(holding.qty)} units
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-sm font-medium">
                        {formatTHB(holding.market_value)}
                      </div>
                      <div
                        className={`flex items-center justify-end gap-1 text-xs ${
                          positive ? "text-emerald-500" : "text-red-500"
                        }`}
                      >
                        {positive ? (
                          <TrendingUp className="size-3" />
                        ) : (
                          <TrendingDown className="size-3" />
                        )}
                        {positive ? "+" : ""}
                        {Number(holding.pnl_pct || 0).toFixed(2)}%
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        <div className="rounded-xl border bg-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="font-semibold">Recent Orders</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                รายการซื้อขายล่าสุดจาก Backend
              </p>
            </div>

            <span className="rounded-full bg-muted px-2.5 py-1 text-[10px]">
              Last 5
            </span>
          </div>

          {ordersLoading ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              กำลังโหลด Orders...
            </div>
          ) : recentOrders.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              ยังไม่มีรายการซื้อขาย
            </div>
          ) : (
            <div className="space-y-2">
              {recentOrders.map((order, index) => {
                const side = String(order.side || "").toUpperCase()
                const isBuy = side === "BUY"

                return (
                  <div
                    key={order.order_id || `${order.timestamp}-${index}`}
                    className="flex items-center justify-between rounded-lg px-3 py-3 hover:bg-accent"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex size-8 items-center justify-center rounded-full ${
                          isBuy
                            ? "bg-emerald-500/10 text-emerald-500"
                            : "bg-red-500/10 text-red-500"
                        }`}
                      >
                        {isBuy ? (
                          <TrendingUp className="size-4" />
                        ) : (
                          <TrendingDown className="size-4" />
                        )}
                      </div>

                      <div>
                        <div className="text-sm font-medium">
                          {side || "ORDER"} {order.asset || "—"}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {formatOrderDate(order.timestamp || order.date)}
                        </div>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-sm font-medium">
                        {formatTHB(Number(order.amount_thb || order.quote_thb || 0))}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {order.status || "filled"}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* FOOTER SUMMARY */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs text-muted-foreground">Realized P&L</div>
          <div className="mt-1 text-lg font-semibold">
            {formatTHB(Number(portfolio?.realized_pnl_thb || 0))}
          </div>
        </div>

        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs text-muted-foreground">Unrealized P&L</div>
          <div className="mt-1 text-lg font-semibold">
            {formatTHB(Number(portfolio?.unrealized_pnl_thb || 0))}
          </div>
        </div>

        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs text-muted-foreground">Trading Fees</div>
          <div className="mt-1 text-lg font-semibold">
            {formatTHB(Number(portfolio?.fees_thb || 0))}
          </div>
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   TRADE PAGE
========================================================= */

function TradePage({
  portfolio,
  loading,
  error,
  onRefresh,
  onOrderCreated,
}: {
  portfolio: PortfolioData | null
  loading: boolean
  error: string
  onRefresh: () => void
  onOrderCreated: () => void
}) {

  const [asset, setAsset] =
    useState<Asset>("BTC")

  const [side, setSide] =
    useState<OrderSide>("BUY")

  const [amount, setAmount] =
    useState("")

  const [submitting, setSubmitting] =
    useState(false)

  const [orderMessage, setOrderMessage] =
    useState("")

  const [tradeOrderBook, setTradeOrderBook] =
    useState<OrderBookResponse | null>(null)

  const [tradeOrderBookError, setTradeOrderBookError] =
    useState("")

  const [tradeOrderBookLoading, setTradeOrderBookLoading] =
    useState(false)

  const loadTradeOrderBook = async () => {
    setTradeOrderBookLoading(true)
    setTradeOrderBookError("")

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/orderbook?asset=${encodeURIComponent(asset)}&limit=5`,
        {
          headers: {
            Accept: "application/json",
            "X-API-Key": DEALER_API_KEY,
          },
          cache: "no-store",
        }
      )

      const body = await response.json()

      if (!response.ok || body?.status !== "ok") {
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : body?.detail?.message ||
              `โหลด Order Book ไม่สำเร็จ (HTTP ${response.status})`
        )
      }

      setTradeOrderBook(body as OrderBookResponse)
    } catch (err) {
      setTradeOrderBook(null)
      setTradeOrderBookError(
        err instanceof Error ? err.message : "โหลด Order Book ไม่สำเร็จ"
      )
    } finally {
      setTradeOrderBookLoading(false)
    }
  }

  useEffect(() => {
    loadTradeOrderBook()
    const timer = window.setInterval(loadTradeOrderBook, 3000)
    return () => window.clearInterval(timer)
  }, [asset])

  const holding = portfolio?.holdings.find(
    (item) => item.asset.toUpperCase() === asset
  )

  const currentPrice = Number(holding?.price || 0)
  const availableThb =
    side === "BUY"
      ? Number(portfolio?.cash_thb || 0)
      : Number(holding?.market_value || 0)

  const amountThb = Number(amount || 0)
  const estimatedQty =
    currentPrice > 0 && amountThb > 0
      ? amountThb / currentPrice
      : 0

  const tradeReady =
    !loading &&
    !error &&
    !!portfolio &&
    currentPrice > 0 &&
    Number.isFinite(amountThb) &&
    amountThb >= 50 &&
    amountThb <= availableThb &&
    !submitting

  const submitOrder = async () => {
    setOrderMessage("")

    if (submitting) return

    if (!portfolio || loading || error) {
      setOrderMessage(
        "ยังส่งคำสั่งไม่ได้: Portfolio ต้องโหลดสำเร็จก่อน"
      )
      return
    }

    const cleanAmount = Number(amount)

    if (!Number.isFinite(cleanAmount) || cleanAmount <= 0) {
      setOrderMessage("กรุณาระบุมูลค่าคำสั่งให้ถูกต้อง")
      return
    }

    if (cleanAmount < 50) {
      setOrderMessage("ยอดขั้นต่ำคือ ฿50.00")
      return
    }

    if (currentPrice <= 0) {
      setOrderMessage("ไม่พบราคาปัจจุบันของเหรียญนี้")
      return
    }

    if (cleanAmount > availableThb + 1e-9) {
      setOrderMessage(
        `${side === "BUY" ? "ยอดซื้อ" : "ยอดขาย"}เกินยอดที่ทำรายการได้`
      )
      return
    }

    if (side === "SELL" && (!holding || Number(holding.qty || 0) <= 0)) {
      setOrderMessage(`ไม่มี ${asset} ให้ขาย`)
      return
    }

    if (!DEALER_API_KEY) {
      setOrderMessage(
        "ยังไม่ได้ตั้ง VITE_DEALER_API_KEY ใน Frontend (.env)"
      )
      return
    }

    const confirmed = window.confirm(
      `${side === "BUY" ? "ซื้อ" : "ขาย"} ${asset} มูลค่า ${formatTHB(cleanAmount)}?\n\nราคาจะถูกตรวจและกำหนดโดย Backend / Engine`
    )

    if (!confirmed) return

    setSubmitting(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/order`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-API-Key": DEALER_API_KEY,
        },
        body: JSON.stringify({
          asset: asset.toUpperCase(),
          side: side.toLowerCase(),
          amount_thb: cleanAmount,
        }),
      })

      const rawText = await response.text()

      let body: any = null
      try {
        body = rawText ? JSON.parse(rawText) : null
      } catch {
        body = null
      }

      if (!response.ok) {
        const detail =
          typeof body?.detail === "string"
            ? body.detail
            : body?.detail?.message ||
              rawText ||
              `Backend ตอบ HTTP ${response.status}`

        throw new Error(
          `ส่งคำสั่งไม่สำเร็จ (HTTP ${response.status}): ${detail}`
        )
      }

      if (body?.status === "rejected") {
        const reason =
          body?.order?.["ผลด่าน"] ||
          body?.detail?.message ||
          "Engine ปฏิเสธคำสั่ง"

        setOrderMessage(`Engine ปฏิเสธคำสั่ง: ${reason}`)
        return
      }

      if (body?.status !== "filled") {
        throw new Error(
          body?.detail?.message ||
            "Backend ไม่ได้ยืนยันคำสั่งเป็น filled"
        )
      }

      const executedQty = Number(body?.quantity || 0)
      const executedQuote = Number(body?.quote_thb || cleanAmount)

      setOrderMessage(
        `สำเร็จ: ${side === "BUY" ? "ซื้อ" : "ขาย"} ${asset} ${formatTHB(executedQuote)}${executedQty > 0 ? ` · ${formatQty(executedQty)} ${asset}` : ""}`
      )

      setAmount("")

      // Refresh Portfolio first, then tell Order History to fetch the
      // latest backend orders. Both happen only after status=filled.
      await onRefresh()
      onOrderCreated()
    } catch (err) {
      setOrderMessage(
        err instanceof Error
          ? err.message
          : "ส่งคำสั่งไม่สำเร็จ"
      )
    } finally {
      setSubmitting(false)
    }
  }


  const market = marketData[asset] || {
    name: asset,
    price: currentPrice,
    change: 0,
    bid: currentPrice,
    ask: currentPrice,
    high: currentPrice,
    low: currentPrice,
    volume: 0,
  }

  const tradeAssets = Array.from(
    new Set(
      (portfolio?.holdings || [])
        .map((item) => item.asset.toUpperCase())
        .concat(["BTC", "ETH", "SOL", "XRP"])
    )
  )

  return (
    <div className="space-y-5">

      {/* =================================================
          MARKET SELECTOR
      ================================================= */}

      <div className="flex flex-wrap items-center justify-between gap-4">

        <div className="flex items-center gap-3">

          {/* ASSET ICON */}

          <CoinLogo asset={asset} size={44} />


          {/* ASSET NAME */}

          <div>

            <div className="flex items-center gap-2">

              <h2 className="text-xl font-bold">
                {asset}/THB
              </h2>

              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">
                Bitkub
              </span>

            </div>

            <p className="text-xs text-muted-foreground">
              {market.name}
            </p>

          </div>

        </div>


        {/* ASSET SELECT */}

        <div className="relative">

          <select
            value={asset}
            onChange={(e) =>
              setAsset(
                e.target.value as Asset
              )
            }
            className="w-full appearance-none rounded-lg border bg-card px-4 py-2 pr-9 text-sm font-medium outline-none focus:ring-2 focus:ring-primary sm:w-auto"
          >
            {tradeAssets.map((symbol) => (
              <option key={symbol} value={symbol}>
                {symbol}/THB
              </option>
            ))}

          </select>

          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 size-4 text-muted-foreground" />

        </div>

      </div>


      {/* =================================================
          MARKET DATA
      ================================================= */}

      <div className="grid gap-3 md:grid-cols-4">

        <MarketStat
          label="ราคาปัจจุบัน"
          value={
            currentPrice > 0
              ? formatTHB(currentPrice)
              : "—"
          }
          sub="Portfolio Backend"
        />

        <MarketStat
          label="ถืออยู่"
          value={
            holding
              ? formatQty(holding.qty)
              : "0"
          }
          sub={asset}
        />

        <MarketStat
          label="มูลค่าที่ถือ"
          value={
            holding
              ? formatTHB(holding.market_value)
              : "฿0.00"
          }
        />

        <MarketStat
          label="ต้นทุนเฉลี่ย"
          value={
            holding
              ? formatTHB(holding.avg_cost)
              : "—"
          }
        />

      </div>


      {/* =================================================
          MAIN TRADE GRID
      ================================================= */}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">

        {/* =================================================
            CHART
        ================================================= */}

        <div className="rounded-xl border bg-card p-5">

          {/* CHART HEADER */}

          <div className="mb-4 flex items-center justify-between">

            <div>

              <h3 className="font-semibold">
                กราฟตลาด · Bitkub
              </h3>

              <p className="text-xs text-muted-foreground">
                {asset}/THB · 1H
              </p>

            </div>


            {/* TIMEFRAME */}

            <div className="flex gap-1">

              {[
                "1m",
                "5m",
                "1H",
                "4H",
                "1D",
              ].map((timeframe) => (

                <button
                  key={timeframe}
                  className={`rounded-md px-2 py-1 text-[11px] ${
                    timeframe === "1H"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {timeframe}
                </button>

              ))}

            </div>

          </div>


          {/* =================================================
              TRADINGVIEW
          ================================================= */}

          <div className="relative overflow-hidden rounded-lg">

            <TradingViewChart
              symbol={`BITKUB:${asset}THB`}
              interval="60"
              height={480}
            />

          </div>


          {/* =================================================
              MARKET RANGE
          ================================================= */}

          <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">

            <MiniStat
              label="สูงสุด 24H"
              value={`฿${market.high.toLocaleString()}`}
            />

            <MiniStat
              label="ต่ำสุด 24H"
              value={`฿${market.low.toLocaleString()}`}
            />

            <MiniStat
              label={`Volume (${asset})`}
              value={market.volume.toLocaleString()}
            />

            <MiniStat
              label="Spread"
              value={`฿${(
                market.ask -
                market.bid
              ).toLocaleString()}`}
            />

          </div>

        </div>


        {/* =================================================
            ORDER TICKET
        ================================================= */}

        <div className="rounded-xl border bg-card p-5">

          <div className="mb-5">

            <h3 className="font-semibold">
              Order
            </h3>

            <p className="text-xs text-muted-foreground">
              Spot Trading · {asset}/THB
            </p>

          </div>


          {/* =================================================
              BUY / SELL
          ================================================= */}

          <div className="grid grid-cols-2 rounded-lg bg-muted p-1">

            <button
              type="button"
              disabled={submitting}
              onClick={() =>
                setSide("BUY")
              }
              className={`rounded-md py-2 text-sm font-semibold transition ${
                side === "BUY"
                  ? "bg-emerald-500 text-white shadow"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              ซื้อ
            </button>


            <button
              type="button"
              disabled={submitting}
              onClick={() =>
                setSide("SELL")
              }
              className={`rounded-md py-2 text-sm font-semibold transition ${
                side === "SELL"
                  ? "bg-red-500 text-white shadow"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              ขาย
            </button>

          </div>


          {/* =================================================
              BALANCE
          ================================================= */}

          <div className="mt-5 flex items-center justify-between text-xs">

            <span className="text-muted-foreground">
              Available
            </span>

            <span className="font-medium">
              {formatTHB(availableThb)}
            </span>

          </div>


          {/* =================================================
              PRICE
          ================================================= */}

          <div className="mt-4">

            <label className="mb-2 block text-xs text-muted-foreground">
              ราคา
            </label>

            <div className="flex items-center rounded-lg border bg-background">

              <input
                value={currentPrice > 0 ? currentPrice : ""}
                readOnly
                className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm outline-none"
              />

              <span className="px-3 text-xs text-muted-foreground">
                THB
              </span>

            </div>

          </div>


          {/* =================================================
              AMOUNT
          ================================================= */}

          <div className="mt-4">

            <label className="mb-2 block text-xs text-muted-foreground">
              มูลค่าคำสั่ง (THB)
            </label>

            <div className="flex items-center rounded-lg border bg-background">

              <input
                value={amount}
                onChange={(e) =>
                  setAmount(
                    e.target.value
                  )
                }
                placeholder="0.00"
                className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm outline-none"
              />

              <span className="px-3 text-xs text-muted-foreground">
                THB
              </span>

            </div>

          </div>


          {/* =================================================
              QUICK AMOUNT
          ================================================= */}

          <div className="mt-3 grid grid-cols-4 gap-2">

            {[0.25, 0.5, 0.75, 1].map((ratio) => {
              const percent = `${ratio * 100}%`
              return (
                <button
                  key={percent}
                  type="button"
                  onClick={() =>
                    setAmount(
                      (availableThb * ratio).toFixed(2)
                    )
                  }
                  disabled={availableThb <= 0 || submitting}
                  className="rounded-md border py-1.5 text-[11px] text-muted-foreground hover:bg-accent disabled:opacity-50"
                >
                  {percent}
                </button>
              )
            })}

          </div>


          {/* =================================================
              TOTAL
          ================================================= */}

          <div className="mt-5 space-y-2 rounded-lg bg-muted/50 p-3">

            <div className="flex justify-between text-xs">

              <span className="text-muted-foreground">
                Estimated Total
              </span>

              <span>
                {amountThb > 0
                  ? formatTHB(amountThb)
                  : "฿0.00"}
              </span>

            </div>


            <div className="flex justify-between text-xs">

              <span className="text-muted-foreground">
                Estimated Quantity
              </span>

              <span>
                {estimatedQty > 0
                  ? `${formatQty(estimatedQty)} ${asset}`
                  : "—"}
              </span>

            </div>


            <div className="flex justify-between text-xs">

              <span className="text-muted-foreground">
                Fee
              </span>

              <span>
                คำนวณโดย Engine
              </span>

            </div>

          </div>


          {/* =================================================
              SUBMIT
          ================================================= */}

          <button
            type="button"
            onClick={submitOrder}
            disabled={!tradeReady}
            className={`mt-5 w-full rounded-lg py-3 text-sm font-semibold text-white ${
              side === "BUY"
                ? "bg-emerald-500"
                : "bg-red-500"
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            {submitting
              ? "กำลังส่งคำสั่ง..."
              : side === "BUY"
                ? `ซื้อ ${asset}`
                : `ขาย ${asset}`}
          </button>

          {orderMessage && (
            <p className="mt-3 rounded-lg border px-3 py-2 text-center text-xs">
              {orderMessage}
            </p>
          )}

          <p className="mt-3 text-center text-[10px] text-muted-foreground">
            Safety Check: Portfolio + ราคา + Balance + Engine
          </p>

        </div>

      </div>


      {/* =================================================
          ORDER BOOK
      ================================================= */}

      <div className="rounded-xl border bg-card p-5">

        {/* ORDER BOOK HEADER */}

        <div className="mb-4 flex items-center justify-between">

          <div>

            <h3 className="font-semibold">
              Order Book
            </h3>

            <p className="text-xs text-muted-foreground">
              {asset}/THB · Bitkub Public Order Book
            </p>

          </div>

          <span className="rounded-full bg-muted px-2 py-1 text-[10px]">
            {tradeOrderBookLoading ? "Loading..." : tradeOrderBookError ? "Error" : "Live"}
          </span>

        </div>


        {/* ORDER BOOK COLUMNS */}

        <div className="grid grid-cols-2 gap-6">

          {/* =================================================
              ASK
          ================================================= */}

          <div>

            <div className="mb-2 grid grid-cols-3 text-[10px] text-muted-foreground">

              <span>
                Price
              </span>

              <span className="text-right">
                Amount
              </span>

              <span className="text-right">
                Total
              </span>

            </div>


            {(tradeOrderBook?.asks || []).map((level, index) => (
              <div
                key={`ask-${index}-${level.price_thb}`}
                className="grid grid-cols-3 py-1.5 text-xs"
              >
                <span className="text-red-500">
                  {formatOrderBookPrice(level.price_thb)}
                </span>
                <span className="text-right">
                  {formatQty(level.quantity)}
                </span>
                <span className="text-right text-muted-foreground">
                  {formatOrderBookTotal(level.total_thb)}
                </span>
              </div>
            ))}          </div>


          {/* =================================================
              BID
          ================================================= */}

          <div>

            <div className="mb-2 grid grid-cols-3 text-[10px] text-muted-foreground">

              <span>
                Price
              </span>

              <span className="text-right">
                Amount
              </span>

              <span className="text-right">
                Total
              </span>

            </div>


            {(tradeOrderBook?.bids || []).map((level, index) => (
              <div
                key={`bid-${index}-${level.price_thb}`}
                className="grid grid-cols-3 py-1.5 text-xs"
              >
                <span className="text-emerald-500">
                  {formatOrderBookPrice(level.price_thb)}
                </span>
                <span className="text-right">
                  {formatQty(level.quantity)}
                </span>
                <span className="text-right text-muted-foreground">
                  {formatOrderBookTotal(level.total_thb)}
                </span>
              </div>
            ))}          </div>

        </div>

      </div>

      {tradeOrderBookError && (
        <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-500">
          {tradeOrderBookError}
        </div>
      )}

    </div>
  )
}



/* =========================================================
   PORTFOLIO PAGE
========================================================= */

function PortfolioPage({
  portfolio,
  loading,
  error,
  onRefresh,
}: {
  portfolio: PortfolioData | null
  loading: boolean
  error: string
  onRefresh: () => void
}) {
  const pnlPositive = (portfolio?.total_pnl_thb ?? 0) >= 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Portfolio</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            ข้อมูลพอร์ตจริงจาก Backend
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
          <p className="text-sm font-medium text-red-500">
            โหลด Portfolio ไม่สำเร็จ
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{error}</p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Total Portfolio"
          value={portfolio ? formatTHB(portfolio.total_value_thb) : "—"}
          change={portfolio ? "มูลค่าพอร์ตรวม" : "กำลังโหลด"}
        />

        <StatCard
          title="Cash Balance"
          value={portfolio ? formatTHB(portfolio.cash_thb) : "—"}
          change="THB Available"
        />

        <StatCard
          title="Market Value"
          value={portfolio ? formatTHB(portfolio.market_value_thb) : "—"}
          change="มูลค่าสินทรัพย์"
        />

        <StatCard
          title="Total P&L"
          value={portfolio ? formatTHB(portfolio.total_pnl_thb) : "—"}
          change={
            portfolio
              ? `${pnlPositive ? "+" : ""}${portfolio.pnl_pct.toFixed(2)}%`
              : "—"
          }
        />
      </div>

      <div className="rounded-xl border bg-card p-5">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold">Holdings</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              สินทรัพย์ทั้งหมดใน Portfolio
            </p>
          </div>

          {portfolio && (
            <span className="rounded-full bg-muted px-2.5 py-1 text-[10px]">
              {portfolio.holdings.length} Assets
            </span>
          )}
        </div>

        {loading && !portfolio ? (
          <div className="flex min-h-[220px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              กำลังโหลด Portfolio จาก Backend...
            </p>
          </div>
        ) : portfolio?.holdings?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="px-3 py-3 font-medium">Asset</th>
                  <th className="px-3 py-3 text-right font-medium">Quantity</th>
                  <th className="px-3 py-3 text-right font-medium">Avg Cost</th>
                  <th className="px-3 py-3 text-right font-medium">Price</th>
                  <th className="px-3 py-3 text-right font-medium">Market Value</th>
                  <th className="px-3 py-3 text-right font-medium">P&L</th>
                  <th className="px-3 py-3 text-right font-medium">P&L %</th>
                  <th className="px-3 py-3 text-right font-medium">Allocation</th>
                </tr>
              </thead>

              <tbody>
                {portfolio.holdings.map((holding) => {
                  const positive = holding.unrealized_pnl >= 0

                  return (
                    <tr
                      key={holding.asset}
                      className="border-b last:border-0 hover:bg-accent/40"
                    >
                      <td className="px-3 py-4">
                        <div className="flex items-center gap-3">
                          <CoinLogo asset={holding.asset} size={34} />
                          <div>
                            <div className="font-semibold">
                              {holding.asset}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              /THB
                            </div>
                          </div>
                        </div>
                      </td>

                      <td className="px-3 py-4 text-right">
                        {formatQty(holding.qty)}
                      </td>

                      <td className="px-3 py-4 text-right">
                        {formatTHB(holding.avg_cost)}
                      </td>

                      <td className="px-3 py-4 text-right font-medium">
                        {formatTHB(holding.price)}
                      </td>

                      <td className="px-3 py-4 text-right font-medium">
                        {formatTHB(holding.market_value)}
                      </td>

                      <td
                        className={`px-3 py-4 text-right font-medium ${
                          positive ? "text-emerald-500" : "text-red-500"
                        }`}
                      >
                        {positive ? "+" : ""}
                        {formatTHB(holding.unrealized_pnl)}
                      </td>

                      <td
                        className={`px-3 py-4 text-right ${
                          positive ? "text-emerald-500" : "text-red-500"
                        }`}
                      >
                        {positive ? "+" : ""}
                        {holding.pnl_pct.toFixed(2)}%
                      </td>

                      <td className="px-3 py-4 text-right">
                        {holding.allocation_pct.toFixed(2)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex min-h-[220px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              ยังไม่มีข้อมูล Holdings
            </p>
          </div>
        )}
      </div>

      {portfolio && (
        <div className="grid gap-4 md:grid-cols-3">
          <MiniStat
            label="Realized P&L"
            value={formatTHB(portfolio.realized_pnl_thb)}
          />
          <MiniStat
            label="Unrealized P&L"
            value={formatTHB(portfolio.unrealized_pnl_thb)}
          />
          <MiniStat
            label="Fees"
            value={formatTHB(portfolio.fees_thb)}
          />
        </div>
      )}
    </div>
  )
}

/* =========================================================
   POSITIONS
========================================================= */

function PositionsPage({
  portfolio,
  loading,
  error,
  onRefresh,
}: {
  portfolio: PortfolioData | null
  loading: boolean
  error: string
  onRefresh: () => void
}) {
  const positions = (portfolio?.holdings || []).filter(
    (holding) => Number(holding.qty || 0) > 0
  )

  const totalMarketValue = positions.reduce(
    (sum, holding) => sum + Number(holding.market_value || 0),
    0
  )

  const totalUnrealizedPnl = positions.reduce(
    (sum, holding) => sum + Number(holding.unrealized_pnl || 0),
    0
  )

  const pnlPositive = totalUnrealizedPnl >= 0

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Positions</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            สถานะการถือครองจาก Portfolio จริง
          </p>
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      {/* ERROR */}
      {error && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm">
          <span className="text-red-500">{error}</span>
          <button
            onClick={onRefresh}
            className="rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-accent"
          >
            Retry
          </button>
        </div>
      )}

      {/* SUMMARY */}
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Open Positions"
          value={loading ? "Loading..." : String(positions.length)}
          change={`${positions.length} assets`}
        />

        <StatCard
          title="Market Value"
          value={loading ? "Loading..." : formatTHB(totalMarketValue)}
          change="มูลค่าตลาดของสินทรัพย์ที่ถือ"
        />

        <StatCard
          title="Unrealized P&L"
          value={
            loading
              ? "Loading..."
              : `${pnlPositive ? "+" : ""}${formatTHB(totalUnrealizedPnl)}`
          }
          change={
            loading
              ? "—"
              : pnlPositive
                ? "กำไรจาก Position"
                : "ขาดทุนจาก Position"
          }
        />
      </div>

      {/* POSITIONS TABLE */}
      <div className="rounded-xl border bg-card">
        <div className="flex items-center justify-between border-b px-5 py-4">
          <div>
            <h3 className="font-semibold">Open Positions</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              คำนวณจาก holdings ที่ Backend ส่งมาจาก Portfolio
            </p>
          </div>

          {portfolio && (
            <div className="text-right">
              <p className="text-[10px] text-muted-foreground">
                Portfolio Value
              </p>
              <p className="text-sm font-semibold">
                {formatTHB(portfolio.total_value_thb)}
              </p>
            </div>
          )}
        </div>

        {loading ? (
          <div className="flex min-h-[220px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              กำลังโหลด Positions...
            </p>
          </div>
        ) : positions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="px-4 py-3 text-left font-medium">Asset</th>
                  <th className="px-4 py-3 text-right font-medium">Quantity</th>
                  <th className="px-4 py-3 text-right font-medium">Avg Cost</th>
                  <th className="px-4 py-3 text-right font-medium">Current Price</th>
                  <th className="px-4 py-3 text-right font-medium">Market Value</th>
                  <th className="px-4 py-3 text-right font-medium">P&L</th>
                  <th className="px-4 py-3 text-right font-medium">P&L %</th>
                  <th className="px-4 py-3 text-right font-medium">Allocation</th>
                </tr>
              </thead>

              <tbody>
                {positions.map((holding) => {
                  const pnl = Number(holding.unrealized_pnl || 0)
                  const positive = pnl >= 0

                  return (
                    <tr
                      key={holding.asset}
                      className="border-b last:border-0 hover:bg-accent/40"
                    >
                      <td className="px-4 py-4">
                        <div className="font-semibold">
                          {holding.asset}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {holding.asset}/THB
                        </div>
                      </td>

                      <td className="px-4 py-4 text-right font-medium">
                        {formatQty(holding.qty)}
                      </td>

                      <td className="px-4 py-4 text-right">
                        {formatTHB(holding.avg_cost)}
                      </td>

                      <td className="px-4 py-4 text-right font-medium">
                        {formatTHB(holding.price)}
                      </td>

                      <td className="px-4 py-4 text-right font-medium">
                        {formatTHB(holding.market_value)}
                      </td>

                      <td
                        className={`px-4 py-4 text-right font-medium ${
                          positive ? "text-emerald-500" : "text-red-500"
                        }`}
                      >
                        {positive ? "+" : ""}
                        {formatTHB(pnl)}
                      </td>

                      <td
                        className={`px-4 py-4 text-right ${
                          positive ? "text-emerald-500" : "text-red-500"
                        }`}
                      >
                        {positive ? "+" : ""}
                        {Number(holding.pnl_pct || 0).toFixed(2)}%
                      </td>

                      <td className="px-4 py-4 text-right">
                        {Number(holding.allocation_pct || 0).toFixed(2)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex min-h-[260px] items-center justify-center px-6">
            <div className="text-center">
              <p className="font-medium">ยังไม่มี Open Positions</p>
              <p className="mt-1 text-sm text-muted-foreground">
                เมื่อ Portfolio มีสินทรัพย์ที่ถืออยู่ จะแสดงในหน้านี้อัตโนมัติ
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* =========================================================
   ORDER HISTORY
========================================================= */

type OrderHistoryRow = {
  order_id?: string
  timestamp?: string
  date?: string
  asset?: string
  side?: string
  status?: string
  type?: string
  amount_thb?: number
  quote_thb?: number
  quantity?: number
  fee_thb?: number
  exchange?: string
  source?: string
}

function parseOrderDate(value?: string) {
  if (!value) return null

  const raw = String(value).trim()
  if (!raw) return null

  // Date-only values are handled separately so they do not shift across
  // midnight when converted through the JavaScript Date constructor.
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const [year, month, day] = raw.split("-").map(Number)
    return new Date(Date.UTC(year, month - 1, day))
  }

  // Timestamps without an explicit timezone are legacy Bangkok clock values.
  // Treat them as Asia/Bangkok instead of UTC to avoid the old +7h shift.
  let normalized = raw.replace(" ", "T")
  const hasTimezone = /Z$/i.test(normalized) || /[+-]\d{2}:\d{2}$/.test(normalized)

  if (!hasTimezone) {
    normalized += "+07:00"
  }

  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatOrderDate(value?: string) {
  if (!value) return "—"

  const raw = String(value).trim()

  // Legacy orders may contain only YYYY-MM-DD. Keep the stored calendar date.
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const [year, month, day] = raw.split("-")
    return `${day}/${month}/${Number(year) + 543}`
  }

  const d = parseOrderDate(raw)
  if (!d) return raw

  return d.toLocaleString("th-TH", {
    timeZone: "Asia/Bangkok",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

function formatNumber(value?: number, digits = 8) {
  const n = Number(value ?? 0)
  if (!Number.isFinite(n)) return "—"
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  })
}

function OrdersPage({ refreshKey }: { refreshKey: number }) {
  const [orders, setOrders] = useState<OrderHistoryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [lastLoaded, setLastLoaded] = useState("")
  const [selectedOrder, setSelectedOrder] = useState<OrderHistoryRow | null>(null)

  const loadOrders = async () => {
    setLoading(true)
    setError("")

    try {
      if (!DEALER_API_KEY) {
        throw new Error(
          "ยังไม่ได้ตั้ง VITE_DEALER_API_KEY ใน Frontend (.env)"
        )
      }

      const response = await fetch(
        `${API_BASE_URL}/api/orders?limit=100`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
            "X-API-Key": DEALER_API_KEY,
          },
          cache: "no-store",
        }
      )

      const rawText = await response.text()
      let body: any = null

      try {
        body = rawText ? JSON.parse(rawText) : null
      } catch {
        body = null
      }

      if (!response.ok) {
        const detail =
          typeof body?.detail === "string"
            ? body.detail
            : body?.detail?.message ||
              rawText ||
              `Backend ตอบ HTTP ${response.status}`

        throw new Error(
          `โหลด Order History ไม่สำเร็จ (HTTP ${response.status}): ${detail}`
        )
      }

      if (body?.status !== "ok") {
        throw new Error(
          body?.detail || "Backend ไม่ได้ตอบ status=ok"
        )
      }

      const rows = Array.isArray(body?.orders)
        ? (body.orders as OrderHistoryRow[])
        : []

      const sortedOrders = [...rows].sort((a, b) => {
        const dateA = parseOrderDate(a.timestamp || a.date)?.getTime() ?? NaN
        const dateB = parseOrderDate(b.timestamp || b.date)?.getTime() ?? NaN

        // ล่าสุด → เก่าสุด
        if (Number.isFinite(dateA) && Number.isFinite(dateB)) {
          return dateB - dateA
        }

        // ถ้ารายการหนึ่งมีวันที่อ่านได้ ให้อยู่ก่อน
        if (Number.isFinite(dateB)) return 1
        if (Number.isFinite(dateA)) return -1

        return 0
      })

      setOrders(sortedOrders)
      setLastLoaded(new Date().toLocaleTimeString("th-TH", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }))
    } catch (err) {
      setOrders([])
      setError(
        err instanceof Error
          ? err.message
          : "ไม่สามารถโหลด Order History ได้"
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [refreshKey])

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Order History</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            ประวัติคำสั่งซื้อขายจาก Backend / Portfolio จริง
          </p>
        </div>

        <button
          type="button"
          onClick={loadOrders}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
          <p className="text-sm font-semibold text-red-500">
            ไม่สามารถโหลด Order History ได้
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-xs text-muted-foreground">
            {error}
          </p>
          <button
            type="button"
            onClick={loadOrders}
            className="mt-3 rounded-lg border px-3 py-1.5 text-xs font-medium hover:bg-accent"
          >
            ลองใหม่
          </button>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          title="Orders"
          value={loading ? "—" : String(orders.length)}
          change="รายการที่โหลดจาก Backend"
        />
        <StatCard
          title="Latest Side"
          value={orders[0]?.side?.toUpperCase() || "—"}
          change={orders[0]?.asset ? `${orders[0].asset}/THB` : "ยังไม่มีรายการ"}
        />
        <StatCard
          title="Last Updated"
          value={lastLoaded || "—"}
          change="เวลาที่โหลดข้อมูลล่าสุด"
        />
      </div>

      <div className="rounded-xl border bg-card p-5">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold">Transactions</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              เรียงจากคำสั่งล่าสุดไปเก่าสุด
            </p>
          </div>

          <span className="rounded-full bg-muted px-2.5 py-1 text-[10px]">
            {orders.length} Orders
          </span>
        </div>

        {loading ? (
          <div className="flex min-h-[260px] items-center justify-center">
            <p className="text-sm text-muted-foreground">
              กำลังโหลด Order History จาก Backend...
            </p>
          </div>
        ) : orders.length === 0 ? (
          <div className="flex min-h-[260px] items-center justify-center rounded-lg border border-dashed">
            <div className="text-center">
              <ClipboardList className="mx-auto size-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium">ยังไม่มี Order History</p>
              <p className="mt-1 text-xs text-muted-foreground">
                เมื่อส่ง BUY/SELL สำเร็จ รายการจะปรากฏที่นี่
              </p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="px-3 py-3 font-medium">Date / Time</th>
                  <th className="px-3 py-3 font-medium">Side</th>
                  <th className="px-3 py-3 font-medium">Asset</th>
                  <th className="px-3 py-3 text-right font-medium">Amount</th>
                  <th className="px-3 py-3 text-right font-medium">Price</th>
                  <th className="px-3 py-3 text-right font-medium">Quantity</th>
                  <th className="px-3 py-3 text-right font-medium">Fee</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">Exchange</th>
                  <th className="px-3 py-3 font-medium">Order ID</th>
                  <th className="px-3 py-3 text-right font-medium">Detail</th>
                </tr>
              </thead>

              <tbody>
                {orders.map((order, index) => {
                  const row: any = order as any
                  const side = String(
                    row.side || row.Side || row["ฝั่ง"] || ""
                  ).toUpperCase()
                  const status = String(
                    row.status || row.Status || row["สถานะ"] || ""
                  ).toLowerCase()
                  const timestamp =
                    row.timestamp || row.time || row.execution_time || row.date
                  const orderId =
                    row.order_id || row.orderId || row["Order ID"] || row.id || ""
                  const exchange =
                    row.exchange || row.Exchange || row.exchange_name || "Bitkub"
                  const key = orderId || `${timestamp || "order"}-${index}`

                  return (
                    <tr
                      key={key}
                      className="border-b last:border-0 hover:bg-accent/40"
                    >
                      <td className="whitespace-nowrap px-3 py-4 text-xs">
                        {formatOrderDate(timestamp)}
                      </td>

                      <td className="px-3 py-4">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-semibold ${
                            side === "BUY"
                              ? "bg-emerald-500/10 text-emerald-500"
                              : side === "SELL"
                                ? "bg-red-500/10 text-red-500"
                                : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {side || "—"}
                        </span>
                      </td>

                      <td className="px-3 py-4 font-semibold">
                        {order.asset || "—"}
                      </td>

                      <td className="px-3 py-4 text-right font-medium">
                        {formatTHB(Number(order.amount_thb || 0))}
                      </td>

                      <td className="px-3 py-4 text-right">
                        {order.quote_thb != null
                          ? formatTHB(Number(order.quote_thb))
                          : "—"}
                      </td>

                      <td className="px-3 py-4 text-right">
                        {order.quantity != null
                          ? formatNumber(Number(order.quantity), 8)
                          : "—"}
                      </td>

                      <td className="px-3 py-4 text-right">
                        {order.fee_thb != null
                          ? formatTHB(Number(order.fee_thb))
                          : "—"}
                      </td>

                      <td className="px-3 py-4">
                        <span className={`text-xs font-medium ${
                          status === "filled" || status === "success"
                            ? "text-emerald-500"
                            : status === "rejected" || status === "failed"
                              ? "text-red-500"
                              : "text-muted-foreground"
                        }`}>
                          {order.status || "—"}
                        </span>
                      </td>

                      <td className="px-3 py-4 text-xs">
                        {exchange || row.source || "—"}
                      </td>

                      <td className="max-w-[180px] truncate px-3 py-4 font-mono text-[10px] text-muted-foreground">
                        {orderId || "—"}
                      </td>

                      <td className="px-3 py-4 text-right">
                        <button
                          type="button"
                          onClick={() => setSelectedOrder(order)}
                          className="rounded-md border px-2.5 py-1.5 text-[10px] font-medium hover:bg-accent"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {selectedOrder && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setSelectedOrder(null)}
        >
          <div
            className="w-full max-w-2xl rounded-2xl border bg-card p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b pb-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Order Detail
                </p>
                <h3 className="mt-1 text-xl font-bold">
                  {String(selectedOrder.side || "ORDER").toUpperCase()}{" "}
                  {selectedOrder.asset || "—"}
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  {formatOrderDate(selectedOrder.timestamp || selectedOrder.date)}
                </p>
              </div>

              <button
                type="button"
                onClick={() => setSelectedOrder(null)}
                className="rounded-lg border px-3 py-1.5 text-sm hover:bg-accent"
              >
                Close
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border bg-muted/20 p-4">
                <p className="text-xs text-muted-foreground">Status</p>
                <p className={`mt-1 text-lg font-semibold ${
                  ["filled", "success"].includes(
                    String(selectedOrder.status || "").toLowerCase()
                  )
                    ? "text-emerald-500"
                    : ["rejected", "failed"].includes(
                        String(selectedOrder.status || "").toLowerCase()
                      )
                      ? "text-red-500"
                      : ""
                }`}>
                  {selectedOrder.status || "—"}
                </p>
              </div>

              <div className="rounded-xl border bg-muted/20 p-4">
                <p className="text-xs text-muted-foreground">Order ID</p>
                <p className="mt-1 break-all font-mono text-sm">
                  {selectedOrder.order_id || "—"}
                </p>
              </div>

              <div className="rounded-xl border p-4">
                <p className="text-xs text-muted-foreground">Amount</p>
                <p className="mt-1 text-lg font-semibold">
                  {formatTHB(Number(selectedOrder.amount_thb || 0))}
                </p>
              </div>

              <div className="rounded-xl border p-4">
                <p className="text-xs text-muted-foreground">Executed Price</p>
                <p className="mt-1 text-lg font-semibold">
                  {selectedOrder.quote_thb != null
                    ? formatTHB(Number(selectedOrder.quote_thb))
                    : "—"}
                </p>
              </div>

              <div className="rounded-xl border p-4">
                <p className="text-xs text-muted-foreground">Quantity</p>
                <p className="mt-1 text-lg font-semibold">
                  {selectedOrder.quantity != null
                    ? formatNumber(Number(selectedOrder.quantity), 8)
                    : "—"}
                </p>
              </div>

              <div className="rounded-xl border p-4">
                <p className="text-xs text-muted-foreground">Trading Fee</p>
                <p className="mt-1 text-lg font-semibold">
                  {selectedOrder.fee_thb != null
                    ? formatTHB(Number(selectedOrder.fee_thb))
                    : "—"}
                </p>
              </div>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border px-4 py-3">
                <p className="text-xs text-muted-foreground">Order Type</p>
                <p className="mt-1 text-sm font-medium">
                  {selectedOrder.type || "—"}
                </p>
              </div>

              <div className="rounded-xl border px-4 py-3">
                <p className="text-xs text-muted-foreground">Exchange / Source</p>
                <p className="mt-1 text-sm font-medium">
                  {selectedOrder.exchange || selectedOrder.source || "—"}
                </p>
              </div>
            </div>

            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedOrder(null)}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* =========================================================
   MARKET STAT
========================================================= */

function MarketStat({
  label,
  value,
  sub,
  positive,
}: {
  label: string
  value: string
  sub?: string
  positive?: boolean
}) {
  return (
    <div className="rounded-xl border bg-card p-4">

      <p className="text-xs text-muted-foreground">
        {label}
      </p>


      <div className="mt-2 text-lg font-bold">
        {value}
      </div>


      {sub && (
        <div
          className={`mt-1 flex items-center gap-1 text-xs ${
            positive === undefined
              ? "text-muted-foreground"
              : positive
                ? "text-emerald-500"
                : "text-red-500"
          }`}
        >

          {positive !== undefined &&
            (positive ? (
              <TrendingUp className="size-3" />
            ) : (
              <TrendingDown className="size-3" />
            ))}

          {sub}

        </div>
      )}

    </div>
  )
}


/* =========================================================
   MINI STAT
========================================================= */

function MiniStat({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div>

      <p className="text-[10px] text-muted-foreground">
        {label}
      </p>

      <p className="mt-1 text-xs font-medium">
        {value}
      </p>

    </div>
  )
}


/* =========================================================
   STAT CARD
========================================================= */

function StatCard({
  title,
  value,
  change,
}: {
  title: string
  value: string
  change: string
}) {
  return (
    <div className="rounded-xl border bg-card p-5">

      <p className="text-sm text-muted-foreground">
        {title}
      </p>

      <div className="mt-3 text-2xl font-bold">
        {value}
      </div>

      <p className="mt-1 text-xs text-muted-foreground">
        {change}
      </p>

    </div>
  )
}


/* =========================================================
   PLACEHOLDER PAGE
========================================================= */

function RiskCenterPage({
  portfolio,
  loading,
  error,
  onRefresh,
}: {
  portfolio: PortfolioData | null
  loading: boolean
  error: string
  onRefresh: () => void
}) {
  const holdings = (portfolio?.holdings || []).filter(
    (holding) => Number(holding.qty || 0) > 0
  )

  const largest = holdings.reduce<PortfolioHolding | null>(
    (best, holding) =>
      !best || Number(holding.allocation_pct || 0) > Number(best.allocation_pct || 0)
        ? holding
        : best,
    null
  )

  const concentration = Number(largest?.allocation_pct || 0)
  const cashRatio = portfolio?.total_value_thb
    ? (Number(portfolio.cash_thb || 0) / Number(portfolio.total_value_thb)) * 100
    : 0
  const pnlPct = Number(portfolio?.pnl_pct || 0)

  const findings = [
    concentration >= 70
      ? { level: "High", title: "Concentration Risk", detail: `${largest?.asset || "สินทรัพย์"} มีสัดส่วน ${concentration.toFixed(2)}% ของพอร์ต` }
      : concentration >= 50
        ? { level: "Medium", title: "Concentration Risk", detail: `${largest?.asset || "สินทรัพย์"} มีสัดส่วน ${concentration.toFixed(2)}% ของพอร์ต` }
        : { level: "Low", title: "Concentration Risk", detail: "ยังไม่พบการกระจุกตัวสูงจากสัดส่วนปัจจุบัน" },
    cashRatio < 5
      ? { level: "Medium", title: "Liquidity", detail: `เงินสดคิดเป็น ${cashRatio.toFixed(2)}% ของมูลค่าพอร์ต` }
      : { level: "Low", title: "Liquidity", detail: `เงินสดคิดเป็น ${cashRatio.toFixed(2)}% ของมูลค่าพอร์ต` },
    pnlPct <= -10
      ? { level: "High", title: "Portfolio Drawdown", detail: `P/L รวมอยู่ที่ ${pnlPct.toFixed(2)}%` }
      : { level: "Low", title: "Portfolio Drawdown", detail: `P/L รวมอยู่ที่ ${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%` },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Risk Center</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            ตรวจความเสี่ยงจาก Portfolio จริง — ไม่ใช้ตัวเลขจำลอง
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard title="Largest Allocation" value={loading ? "Loading..." : `${largest?.asset || "—"} ${concentration.toFixed(2)}%`} change="สัดส่วนสูงสุดในพอร์ต" />
        <StatCard title="Cash Ratio" value={loading ? "Loading..." : `${cashRatio.toFixed(2)}%`} change="เงินสดเทียบมูลค่าพอร์ต" />
        <StatCard title="Portfolio P/L" value={loading ? "Loading..." : `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`} change="P/L รวมจาก Backend" />
      </div>

      <div className="rounded-xl border bg-card">
        <div className="border-b px-5 py-4">
          <h3 className="font-semibold">Risk Findings</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            สรุปอัตโนมัติจากข้อมูล Portfolio ล่าสุด
          </p>
        </div>
        <div className="divide-y">
          {findings.map((item) => (
            <div key={item.title} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
              <div>
                <div className="font-medium">{item.title}</div>
                <div className="mt-1 text-sm text-muted-foreground">{item.detail}</div>
              </div>
              <span className="rounded-full border px-3 py-1 text-xs font-medium">{item.level}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   NEWS
========================================================= */

type NewsItem = {
  title: string
  link: string
  pubDate: string
  description?: string
  source: string
}

const NEWS_FEEDS = [
  {
    name: "CoinDesk",
    url: "https://www.coindesk.com/arc/outboundfeeds/rss/",
  },
  {
    name: "Cointelegraph",
    url: "https://cointelegraph.com/rss",
  },
]

function NewsPage() {
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [activeSource, setActiveSource] = useState("All")

  const loadNews = async () => {
    setLoading(true)
    setError("")

    try {
      const responses = await Promise.all(
        NEWS_FEEDS.map(async (feed) => {
          const endpoint = `https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(feed.url)}`
          const response = await fetch(endpoint, { cache: "no-store" })
          if (!response.ok) throw new Error(`${feed.name}: HTTP ${response.status}`)

          const body = await response.json()
          const feedItems = Array.isArray(body?.items) ? body.items : []

          return feedItems.slice(0, 12).map((item: any) => ({
            title: String(item?.title || "Untitled"),
            link: String(item?.link || ""),
            pubDate: String(item?.pubDate || ""),
            description: String(item?.description || "")
              .replace(/<[^>]*>/g, " ")
              .replace(/\s+/g, " ")
              .trim(),
            source: feed.name,
          })) as NewsItem[]
        })
      )

      const merged = responses
        .flat()
        .filter((item) => item.title && item.link)
        .sort((a, b) => {
          const aTime = new Date(a.pubDate).getTime()
          const bTime = new Date(b.pubDate).getTime()
          if (Number.isFinite(aTime) && Number.isFinite(bTime)) return bTime - aTime
          return 0
        })

      setItems(merged)
      if (merged.length === 0) setError("ยังไม่มีข่าวที่โหลดได้จากแหล่งข่าว")
    } catch (err) {
      setError(err instanceof Error ? err.message : "ไม่สามารถโหลดข่าวได้")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadNews()
  }, [])

  const visibleItems = activeSource === "All"
    ? items
    : items.filter((item) => item.source === activeSource)

  const formatNewsDate = (value: string) => {
    if (!value) return ""
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return date.toLocaleString("th-TH", {
      timeZone: "Asia/Bangkok",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">News</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            ข่าวคริปโตล่าสุดจากแหล่งข่าวภายนอก สำหรับใช้ประกอบการติดตามตลาด
          </p>
        </div>
        <button
          onClick={loadNews}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard
          title="News"
          value={loading ? "Loading..." : String(items.length)}
          change="ข่าวที่โหลดได้"
        />
        <StatCard
          title="Sources"
          value={String(NEWS_FEEDS.length)}
          change="แหล่งข่าว"
        />
        <StatCard
          title="BTC"
          value={`${marketData.BTC.change >= 0 ? "+" : ""}${marketData.BTC.change.toFixed(2)}%`}
          change="Market snapshot"
        />
        <StatCard
          title="ETH"
          value={`${marketData.ETH.change >= 0 ? "+" : ""}${marketData.ETH.change.toFixed(2)}%`}
          change="Market snapshot"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {["All", ...NEWS_FEEDS.map((feed) => feed.name)].map((source) => (
          <button
            key={source}
            onClick={() => setActiveSource(source)}
            className={`rounded-full border px-4 py-2 text-sm transition-colors ${
              activeSource === source
                ? "bg-primary text-primary-foreground"
                : "hover:bg-accent"
            }`}
          >
            {source}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {visibleItems.map((item, index) => (
          <article
            key={`${item.source}-${item.link}-${index}`}
            className="rounded-xl border bg-card p-5 transition-colors hover:bg-accent/30"
          >
            <div className="mb-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span className="rounded-full bg-muted px-2.5 py-1 font-medium">
                {item.source}
              </span>
              <span>{formatNewsDate(item.pubDate)}</span>
            </div>
            <h3 className="text-base font-semibold leading-6">
              <a
                href={item.link}
                target="_blank"
                rel="noreferrer"
                className="hover:underline"
              >
                {item.title}
              </a>
            </h3>
            {item.description && (
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">
                {item.description}
              </p>
            )}
            <a
              href={item.link}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex text-sm font-medium text-primary hover:underline"
            >
              อ่านข่าวเต็ม →
            </a>
          </article>
        ))}
      </div>

      {!loading && visibleItems.length === 0 && !error && (
        <div className="flex min-h-[260px] items-center justify-center rounded-xl border bg-card text-sm text-muted-foreground">
          ยังไม่มีข่าวในหมวดนี้
        </div>
      )}

      <div className="rounded-xl border bg-card px-5 py-4 text-xs leading-5 text-muted-foreground">
        News เป็นข้อมูลจากแหล่งข่าวภายนอกและใช้เพื่อการติดตามตลาดเท่านั้น ยังไม่ถูกนำไปใช้สั่งซื้อขายอัตโนมัติ
      </div>
    </div>
  )
}

/* =========================================================
   QUANT LAB
========================================================= */

function QuantLabPage({
  portfolio,
  loading,
  error,
  onRefresh,
}: {
  portfolio: PortfolioData | null
  loading: boolean
  error: string
  onRefresh: () => void
}) {
  const holdings = (portfolio?.holdings || [])
    .filter((holding) => Number(holding.qty || 0) > 0)
    .sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0))

  const totalValue = Number(portfolio?.total_value_thb || 0)
  const investedValue = holdings.reduce(
    (sum, holding) => sum + Number(holding.cost_basis || 0),
    0
  )
  const marketValue = holdings.reduce(
    (sum, holding) => sum + Number(holding.market_value || 0),
    0
  )
  const unrealized = holdings.reduce(
    (sum, holding) => sum + Number(holding.unrealized_pnl || 0),
    0
  )
  const largestAllocation = Number(holdings[0]?.allocation_pct || 0)
  const diversificationScore = holdings.length === 0
    ? 0
    : Math.max(0, Math.min(100, 100 - largestAllocation * 0.7))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Quant Lab</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            วิเคราะห์โครงสร้างพอร์ตจากข้อมูล Portfolio จริง
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "กำลังโหลด..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">
          {error}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Assets"
          value={loading ? "Loading..." : String(holdings.length)}
          change="สินทรัพย์ที่มี Quantity > 0"
        />
        <StatCard
          title="Market Value"
          value={loading ? "Loading..." : formatTHB(marketValue)}
          change="มูลค่าตลาดจาก Holdings"
        />
        <StatCard
          title="Unrealized P/L"
          value={loading ? "Loading..." : formatTHB(unrealized)}
          change="คำนวณจาก Portfolio"
        />
        <StatCard
          title="Diversification"
          value={loading ? "Loading..." : `${diversificationScore.toFixed(0)}/100`}
          change="คะแนนเชิงโครงสร้าง ไม่ใช่คำแนะนำลงทุน"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-xl border bg-card">
          <div className="border-b px-5 py-4">
            <h3 className="font-semibold">Portfolio Metrics</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              ตัวเลขทั้งหมดอ่านจาก Backend ล่าสุด
            </p>
          </div>
          <div className="divide-y">
            <div className="flex justify-between px-5 py-4 text-sm">
              <span className="text-muted-foreground">Total Value</span>
              <span className="font-medium">{formatTHB(totalValue)}</span>
            </div>
            <div className="flex justify-between px-5 py-4 text-sm">
              <span className="text-muted-foreground">Cost Basis</span>
              <span className="font-medium">{formatTHB(investedValue)}</span>
            </div>
            <div className="flex justify-between px-5 py-4 text-sm">
              <span className="text-muted-foreground">Largest Allocation</span>
              <span className="font-medium">
                {holdings[0]?.asset || "—"} {largestAllocation.toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between px-5 py-4 text-sm">
              <span className="text-muted-foreground">Cash</span>
              <span className="font-medium">{formatTHB(portfolio?.cash_thb || 0)}</span>
            </div>
          </div>
        </div>

        <div className="rounded-xl border bg-card">
          <div className="border-b px-5 py-4">
            <h3 className="font-semibold">Holdings Analysis</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              เรียงตาม Market Value สูงสุด
            </p>
          </div>
          {holdings.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="px-5 py-3 text-left font-medium">Asset</th>
                    <th className="px-5 py-3 text-right font-medium">Weight</th>
                    <th className="px-5 py-3 text-right font-medium">P/L</th>
                    <th className="px-5 py-3 text-right font-medium">P/L %</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((holding) => {
                    const pnl = Number(holding.unrealized_pnl || 0)
                    const positive = pnl >= 0
                    return (
                      <tr key={holding.asset} className="border-b last:border-0">
                        <td className="px-5 py-3 font-medium">{holding.asset}</td>
                        <td className="px-5 py-3 text-right">
                          {Number(holding.allocation_pct || 0).toFixed(2)}%
                        </td>
                        <td className={`px-5 py-3 text-right ${positive ? "text-emerald-500" : "text-red-500"}`}>
                          {positive ? "+" : ""}{formatTHB(pnl)}
                        </td>
                        <td className={`px-5 py-3 text-right ${positive ? "text-emerald-500" : "text-red-500"}`}>
                          {positive ? "+" : ""}{Number(holding.pnl_pct || 0).toFixed(2)}%
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex min-h-[220px] items-center justify-center text-sm text-muted-foreground">
              ยังไม่มีข้อมูล Holdings
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* =========================================================
   PLACEHOLDER
========================================================= */

function PlaceholderPage({
  title,
}: {
  title: string
}) {
  return (
    <div>

      <h2 className="text-2xl font-bold">
        {title}
      </h2>


      <div className="mt-6 flex min-h-[400px] items-center justify-center rounded-xl border bg-card">

        <div className="text-center">

          <p className="font-medium">
            {title}
          </p>

          <p className="mt-1 text-sm text-muted-foreground">
            กำลังเชื่อมระบบจาก gu.py
          </p>

        </div>

      </div>

    </div>
  )
}


/* =========================================================
   EXPORT
========================================================= */

export default App
