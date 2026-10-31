// ชนิดข้อมูลของ Backtest Lab — แยกไฟล์ใหม่ ไม่ import จากโค้ดเดิมของโปรเจกต์

export type Metric = {
  value: number | null
  status: string // ok | limited_sample | insufficient_data | undefined | unavailable
  unit: string
  formula: string
  n_obs: number
  reason: string | null
}

export type RebalanceMode = "none" | "calendar" | "threshold" | "hybrid"
export type RebalanceFreq = "monthly" | "quarterly" | "annual"

export type Spec = {
  version: 1
  start: string
  end: string
  initial_capital: number
  positions: { symbol: string; weight: number }[]
  rebalance: { mode: RebalanceMode; frequency?: RebalanceFreq; threshold_pct?: number }
  costs: { commission_bps: number; slippage_bps: number }
  risk_free_annual: number | null
  return_mode?: "price" | "total"
  strategy?: StrategySpec
}

export type OperandSpec = Record<string, string | number>
export type CondSpec = { all: CondSpec[] } | { any: CondSpec[] } | { not: CondSpec } | { op: string; left: OperandSpec; right: OperandSpec }
export type StrategySpec = {
  entry: CondSpec
  exit?: CondSpec | null
  stops?: { stop_loss_pct?: number; take_profit_pct?: number; trailing_stop_pct?: number; max_hold_days?: number }
}

export type Trip = {
  symbol: string
  entry_date: string
  exit_date: string | null
  entry_price: number | null
  exit_price: number | null
  return: number
  pnl: number
  holding_days: number
  exit_reason: string
  open: boolean
}

export type TripStats = {
  closed_trades: number
  open_at_end: number
  win_rate?: number
  avg_win?: number | null
  avg_loss?: number | null
  profit_factor?: number | null
  expectancy?: number
  avg_holding_days?: number
  best_trade?: number
  worst_trade?: number
  max_consecutive_losses?: number
}

export type StrategyResult = {
  trips: Trip[]
  trip_stats: TripStats
  first_entry_signal: Record<string, string | null>
  exit_reasons: Record<string, number>
}

export type Brief = {
  total_return: Metric
  cagr: Metric
  volatility: Metric
  max_drawdown: Metric
  sharpe: Metric
  sortino: Metric
  calmar: Metric
}

export type DayRow = { date: string; portfolio: number; benchmark: number; active: number }
export type PeriodRow = { period: string; portfolio: number; benchmark: number; active: number; days: number }

export type Trade = {
  date: string
  symbol: string
  side: "buy" | "sell"
  shares: number
  price: number
  notional: number
  commission: number
  slippage_cost: number
  reason: string
}

export type Warning = { code: string; severity: "info" | "low" | "medium" | "high"; message: string; symbol?: string }

export type Result = {
  mode?: "strategy"
  return_mode?: "total"
  strategy_result?: StrategyResult
  period: { base_date: string; first_trade_date: string; last_date: string; trading_days: number }
  comparison: { portfolio: Brief; buy_hold: Brief; benchmark: Brief }
  series: { date: string; portfolio: number; buy_hold: number; benchmark: number }[]
  extremes: {
    days: { worst: DayRow[]; best: DayRow[]; n: number }
    weeks: { worst: PeriodRow; best: PeriodRow }
    months: { worst: PeriodRow; best: PeriodRow }
  }
  calendar_years: { year: number; days: number; portfolio?: number; buy_hold?: number; benchmark?: number }[]
  trades: Trade[]
  trades_truncated: boolean
  rebalances: { date: string; trigger: string }[]
  stats: {
    final_value: number
    buy_hold_final_value: number
    initial_capital: number
    trade_count: number
    rebalance_count: number
    commission_paid: number
    slippage_cost: number
    total_cost: number
    total_cost_pct_of_initial: number
    turnover_annual_one_way: number
    time_in_market: number
    final_weights: Record<string, number>
  }
  warnings: Warning[]
  labels: string[]
  data_snapshot: { symbol: string; source: string; first_date: string; last_date: string; fetched_at: string; stale: boolean; bars_used: number }[]
  engine_version: string
}

export type RunStatus = "queued" | "running" | "done" | "failed"
export type Run = {
  id: string
  status: RunStatus
  spec: Spec
  created_at: string
  finished_at: string | null
  error: { code: string; message: string } | null
  result?: Result | null
}

export type Meta = {
  engine_version: string
  benchmark: string
  limits: { max_symbols: number; max_years: number; min_capital: number; max_capital: number; max_commission_bps: number; max_slippage_bps: number }
  defaults: { commission_bps: number; slippage_bps: number }
  indicators: IndicatorDef[]
  rule_language: { operators: string[]; price_fields: string[]; max_nodes: number; stops: string[] }
  notice: string
}

export type IndicatorDef = {
  key: string
  label: string
  outputs: string[]
  uses_source: boolean
  params: { name: string; default: number; min: number; max: number; integer: boolean }[]
}
