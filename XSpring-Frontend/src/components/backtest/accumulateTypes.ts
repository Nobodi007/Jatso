// ชนิดข้อมูลของโหมดทยอยสะสม (DCA / Buy-the-dip) — แยกไฟล์ ไม่แตะ types.ts ของคุณ
// ใน Spec ของคุณเพิ่ม:  accumulate?: AccumulateSpec   (และ risk_free_source?: "tbill" จากรอบก่อน)

export type AccFreq = "weekly" | "monthly" | "quarterly"

export interface AccumulateSpec {
  contribution?: { amount: number; frequency: AccFreq } | null
  schedule?: { amount: number; frequency: AccFreq } | null
  dip?: { drop_pct: number; lookback_days: number; amount: number; cooldown_days: number } | null
  when?: Record<string, unknown> | null
  max_invested_per_stock?: number | null
  initial_invest_pct?: number
}

export interface AccPerStock {
  symbol: string
  invested: number
  shares: number
  avg_cost: number | null
  market_value: number
  return_on_cost: number | null
  cash_left: number
  buys: number
}

export interface AccResultBlock {
  buy_counts: { initial: number; schedule: number; dip: number }
  blocked: { cap: number; no_cash: number }
  per_stock: AccPerStock[]
  cash_left_total: number
  contribution_events: number
}

export interface AccStats {
  final_value: number
  buy_hold_final_value: number
  initial_capital: number
  total_contributed: number
  total_invested: number
  profit: number
  profit_pct_invested: number
  buy_hold_profit: number
  benchmark_final_value: number
  benchmark_profit: number
  money_weighted_return: number | null
  buy_hold_money_weighted_return: number | null
  benchmark_money_weighted_return: number | null
  time_in_market: number
}

/** ชนิดที่ AccumulatePanel รับ — ส่ง Result ของคุณเข้ามาได้ตรง ๆ (field เสริมเป็น optional) */
export interface AccumulateResult {
  mode?: string
  series: { date: string; value?: number; invested?: number }[]
  stats: Partial<AccStats> & { final_value: number }
  accumulate_result?: AccResultBlock
}
