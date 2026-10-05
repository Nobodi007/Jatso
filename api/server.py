import TradingViewChart from "@/components/trading/TradingViewChart"
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
  | "orders"
  | "positions"
  | "risk"
  | "quant"
  | "news"
  | "settings"

type Asset = "BTC" | "ETH" | "SOL" | "XRP"
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


const navigation = [
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
] as const

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

  const loadPortfolio = async () => {
    setPortfolioLoading(true)
    setPortfolioError("")

    try {
      const response = await fetch(`${API_BASE_URL}/api/portfolio`, {
        method: "GET",
        headers: { Accept: "application/json" },
      })

      const body = await response.json()

      if (!response.ok || body?.status !== "ok" || !body?.portfolio) {
        throw new Error(
          body?.detail?.message ||
            body?.detail ||
            "ไม่สามารถโหลด Portfolio จาก Backend ได้"
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

        <aside
          className={`border-r bg-card transition-all duration-200 ${
            sidebarOpen ? "w-64" : "w-16"
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
                  onClick={() => setPage(item.id)}
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

                      {item.count && (
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

        <div className="flex min-w-0 flex-1 flex-col">

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

          <main className="flex-1 overflow-auto p-6">

            {page === "dashboard" && (
              <Dashboard
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
              />
            )}

            {page === "trade" && (
              <TradePage />
            )}

            {page === "portfolio" && (
              <PortfolioPage
                portfolio={portfolio}
                loading={portfolioLoading}
                error={portfolioError}
                onRefresh={loadPortfolio}
              />
            )}

            {page !== "dashboard" &&
              page !== "trade" &&
              page !== "portfolio" && (
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
   DASHBOARD
========================================================= */

function Dashboard({
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
  const openPositions =
    portfolio?.holdings.filter((holding) => Number(holding.qty || 0) > 0).length ?? 0

  const pnlPositive = Number(portfolio?.total_pnl_thb || 0) >= 0

  return (
    <div className="space-y-6">

      {/* HEADER */}

      <div>

        <h2 className="text-2xl font-bold">
          Dashboard
        </h2>

        <p className="mt-1 text-sm text-muted-foreground">
          XSpring Dealer Suite
        </p>

      </div>


      {/* STAT CARDS */}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">

        <StatCard
          title="Portfolio Value"
          value={
            loading
              ? "Loading..."
              : formatTHB(portfolio?.total_value_thb ?? 0)
          }
          change={
            error
              ? "โหลดข้อมูลไม่สำเร็จ"
              : "มูลค่าพอร์ตจาก Backend"
          }
        />

        <StatCard
          title="Available Balance"
          value={
            loading
              ? "Loading..."
              : formatTHB(portfolio?.cash_thb ?? 0)
          }
          change="Cash / THB"
        />

        <StatCard
          title="Total P&L"
          value={
            loading
              ? "Loading..."
              : formatTHB(portfolio?.total_pnl_thb ?? 0)
          }
          change={
            loading
              ? "—"
              : `${pnlPositive ? "+" : ""}${Number(
                  portfolio?.pnl_pct ?? 0
                ).toFixed(2)}%`
          }
        />

        <StatCard
          title="Open Positions"
          value={loading ? "—" : String(openPositions)}
          change={
            loading
              ? "—"
              : `${portfolio?.holdings.length ?? 0} assets in portfolio`
          }
        />

      </div>


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

      {/* DASHBOARD GRID */}

      <div className="grid gap-4 xl:grid-cols-3">

        {/* MARKET OVERVIEW */}

        <div className="min-h-[400px] rounded-xl border bg-card p-5 xl:col-span-2">

          <div className="mb-4">

            <h3 className="font-semibold">
              Market Overview
            </h3>

            <p className="text-xs text-muted-foreground">
              Real-time market data
            </p>

          </div>


          <div className="flex h-[320px] items-center justify-center rounded-lg bg-muted/30">

            <div className="text-center">

              <CandlestickChart className="mx-auto mb-3 size-10 text-muted-foreground" />

              <p className="text-sm font-medium">
                Trading Chart
              </p>

              <p className="mt-1 text-xs text-muted-foreground">
                TradingView จะถูกเชื่อมในขั้นต่อไป
              </p>

            </div>

          </div>

        </div>


        {/* WATCHLIST */}

        <div className="min-h-[400px] rounded-xl border bg-card p-5">

          <h3 className="font-semibold">
            Watchlist
          </h3>

          <div className="mt-4 space-y-2">

            {loading ? (
              <div className="py-10 text-center text-sm text-muted-foreground">
                Loading market prices...
              </div>
            ) : (
              ["BTC", "ETH", "SOL", "XRP"].map((symbol) => {
                const holding = portfolio?.holdings.find(
                  (item) => item.asset.toUpperCase() === symbol
                )

                if (!holding) return null

                const positionPnl = Number(holding.pnl_pct || 0)
                const positive = positionPnl >= 0

                return (
                  <div
                    key={symbol}
                    className="flex items-center justify-between rounded-lg px-3 py-3 hover:bg-accent"
                  >
                    <div>
                      <div className="font-medium">
                        {symbol}/THB
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Current Price
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-sm">
                        {formatTHB(holding.price)}
                      </div>
                      <div
                        className={`text-xs ${
                          positive
                            ? "text-emerald-500"
                            : "text-red-500"
                        }`}
                      >
                        Position P&L {positive ? "+" : ""}
                        {positionPnl.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                )
              })
            )}

          </div>

        </div>

      </div>

    </div>
  )
}


/* =========================================================
   TRADE PAGE
========================================================= */

function TradePage() {

  const [asset, setAsset] =
    useState<Asset>("BTC")

  const [side, setSide] =
    useState<OrderSide>("BUY")

  const [amount, setAmount] =
    useState("")

  const market = marketData[asset]

  return (
    <div className="space-y-5">

      {/* =================================================
          MARKET SELECTOR
      ================================================= */}

      <div className="flex flex-wrap items-center justify-between gap-4">

        <div className="flex items-center gap-3">

          {/* ASSET ICON */}

          <div className="flex size-11 items-center justify-center rounded-full bg-muted text-lg font-bold">
            {asset[0]}
          </div>


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
            className="appearance-none rounded-lg border bg-card px-4 py-2 pr-9 text-sm font-medium outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="BTC">
              BTC/THB
            </option>

            <option value="ETH">
              ETH/THB
            </option>

            <option value="SOL">
              SOL/THB
            </option>

            <option value="XRP">
              XRP/THB
            </option>

          </select>

          <ChevronDown className="pointer-events-none absolute right-2 top-2.5 size-4 text-muted-foreground" />

        </div>

      </div>


      {/* =================================================
          MARKET DATA
      ================================================= */}

      <div className="grid gap-3 md:grid-cols-4">

        <MarketStat
          label="ราคา"
          value={`฿${market.price.toLocaleString()}`}
          positive={market.change >= 0}
          sub={`${
            market.change >= 0
              ? "+"
              : ""
          }${market.change.toFixed(2)}% 24H`}
        />

        <MarketStat
          label="Bid"
          value={`฿${market.bid.toLocaleString()}`}
        />

        <MarketStat
          label="Ask"
          value={`฿${market.ask.toLocaleString()}`}
        />

        <MarketStat
          label="Volume 24H"
          value={market.volume.toLocaleString()}
          sub={asset}
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
              ฿0.00
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
                value={market.price}
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
              จำนวน {asset}
            </label>

            <div className="flex items-center rounded-lg border bg-background">

              <input
                value={amount}
                onChange={(e) =>
                  setAmount(
                    e.target.value
                  )
                }
                placeholder="0.00000000"
                className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm outline-none"
              />

              <span className="px-3 text-xs text-muted-foreground">
                {asset}
              </span>

            </div>

          </div>


          {/* =================================================
              QUICK AMOUNT
          ================================================= */}

          <div className="mt-3 grid grid-cols-4 gap-2">

            {[
              "25%",
              "50%",
              "75%",
              "100%",
            ].map((percent) => (

              <button
                key={percent}
                className="rounded-md border py-1.5 text-[11px] text-muted-foreground hover:bg-accent"
              >
                {percent}
              </button>

            ))}

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
                ฿0.00
              </span>

            </div>


            <div className="flex justify-between text-xs">

              <span className="text-muted-foreground">
                Fee
              </span>

              <span>
                ฿0.00
              </span>

            </div>

          </div>


          {/* =================================================
              SUBMIT
          ================================================= */}

          <button
            disabled
            className={`mt-5 w-full rounded-lg py-3 text-sm font-semibold text-white ${
              side === "BUY"
                ? "bg-emerald-500"
                : "bg-red-500"
            } opacity-60`}
          >
            {side === "BUY"
              ? `ซื้อ ${asset}`
              : `ขาย ${asset}`}
          </button>


          <p className="mt-3 text-center text-[10px] text-muted-foreground">
            Trading engine ยังไม่ได้เชื่อมกับ Backend
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
              {asset}/THB
            </p>

          </div>

          <span className="rounded-full bg-muted px-2 py-1 text-[10px]">
            Live
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


            {[
              [market.ask + 1000, 0.42],
              [market.ask + 500, 0.31],
              [market.ask, 0.18],
            ].map(
              ([price, amount], index) => (

                <div
                  key={index}
                  className="grid grid-cols-3 py-1.5 text-xs"
                >

                  <span className="text-red-500">
                    ฿
                    {Number(
                      price
                    ).toLocaleString()}
                  </span>

                  <span className="text-right">
                    {amount}
                  </span>

                  <span className="text-right text-muted-foreground">
                    {(
                      Number(price) *
                      Number(amount)
                    ).toLocaleString()}
                  </span>

                </div>

              )
            )}

          </div>


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


            {[
              [market.bid, 0.22],
              [market.bid - 500, 0.37],
              [market.bid - 1000, 0.54],
            ].map(
              ([price, amount], index) => (

                <div
                  key={index}
                  className="grid grid-cols-3 py-1.5 text-xs"
                >

                  <span className="text-emerald-500">
                    ฿
                    {Number(
                      price
                    ).toLocaleString()}
                  </span>

                  <span className="text-right">
                    {amount}
                  </span>

                  <span className="text-right text-muted-foreground">
                    {(
                      Number(price) *
                      Number(amount)
                    ).toLocaleString()}
                  </span>

                </div>

              )
            )}

          </div>

        </div>

      </div>

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
          change={portfolio ? "มูลค่าพอร์ตทั้งหมด" : "กำลังโหลด"}
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
                        <span className="font-semibold">
                          {holding.asset}
                        </span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          /THB
                        </span>
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
