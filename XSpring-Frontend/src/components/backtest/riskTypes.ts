// ชนิดข้อมูลส่วนเสริมของผลลัพธ์ (attribution / exposure / analysis / risk_free) — แยกไฟล์ ไม่แตะ types.ts ของคุณ

export interface RM {
  value: number | null
  status: string
  unit?: string
  n_obs?: number | null
  reason?: string | null
}

export interface RiskFree {
  source: string | null // tbill_3m | user_constant | null
  status: string // ok | unavailable | no_data | not_set
  avg_annual: number | null
  first_annual?: number
  last_annual?: number
}

export interface AttrRow {
  symbol: string
  net_pnl: number
  contribution: number
  gross_pnl: number
  commission: number
  slippage_cost: number
  final_value: number
  final_weight: number
  avg_weight: number
  trade_count: number
  pct_of_risk: number | null
  risk_volatility_contribution: number | null
}

export interface Attribution {
  method: string
  positions: AttrRow[]
  totals: {
    net_pnl: number
    portfolio_pnl: number
    reconciliation_error: number
    total_return: number
    sum_contribution: number
    commission: number
    slippage_cost: number
    pct_risk_sum: number | null
  }
  risk_status: string // ok | insufficient_data
  n_obs: number
}

export interface DecompRow { symbol: string; weight_nav: number; volatility: number; mcr: number; ccr: number; pct_of_risk: number }
export interface Concentration { hhi: RM; effective_n: RM; top1: RM; top3: RM; top5: RM }
export interface Exposure {
  note: string
  target: Concentration
  average_held: Concentration
  final: Concentration
  static_decomposition: {
    portfolio_volatility: RM
    diversification_ratio?: RM
    avg_pairwise_correlation?: RM
    contributions: DecompRow[]
    top_pairs?: { a: string; b: string; correlation: number }[]
    excluded: { symbol: string; reason: string }[]
  }
}

export interface Analysis {
  performance?: Record<string, RM>
  risk_adjusted?: Record<string, RM>
  tail?: {
    max_drawdown?: RM
    current_drawdown?: RM
    drawdown_episode?: { peak_date: string; trough_date: string; recovery_date: string | null; duration_trading_days: number; recovery_trading_days: number | null } | null
    longest_underwater_trading_days?: number
    var_95?: RM
    es_95?: RM
    downside_deviation?: RM
    drawdown_series?: { date: string; drawdown: number }[]
  }
  monthly?: { period: string; portfolio: number; benchmark: number | null; active: number | null; days: number }[]
  rolling?: { window_trading_days: number; points: { date: string; volatility: number; beta?: number | null; sharpe?: number | null }[] }
}

/** ชนิดที่ RiskPanel รับ — ส่ง Result ของคุณเข้ามาได้ตรง ๆ (field เสริมเป็น optional) */
export interface RiskResult {
  period: { first_trade_date: string; last_date: string; trading_days: number }
  series: { date: string; portfolio: number; benchmark: number }[]
  return_mode?: string
  analysis?: Analysis
  attribution?: Attribution
  exposure?: Exposure
  risk_free?: RiskFree
}
