import { useState } from "react"
import type { StrategyResult } from "./types"

const card = "rounded-xl border bg-card p-5"
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`)
const signCls = (v: number | null | undefined) => (v == null ? "text-muted-foreground" : v >= 0 ? "text-emerald-500" : "text-red-500")

export const REASON_LABEL: Record<string, string> = {
  initial: "ซื้อเริ่มต้น", entry: "เข้าตามสัญญาณ", signal_exit: "ขายตามสัญญาณ", stop_loss: "Stop-loss",
  trailing_stop: "Trailing stop", take_profit: "Take-profit", max_hold: "ถือครบกำหนด", rebalance: "ปรับสัดส่วน",
  open_at_end: "ยังถืออยู่ ณ วันสุดท้าย",
}

export default function StrategyResults({ sr }: { sr: StrategyResult }) {
  const [show, setShow] = useState(false)
  const t = sr.trip_stats
  return (
    <div className={card}>
      <h3 className="mb-2 text-sm font-medium text-foreground">สถิติต่อรอบการเทรด (กลยุทธ์)</h3>
      {t.closed_trades === 0 ? (
        <p className="text-xs text-muted-foreground">ไม่มีรอบที่ปิดสถานะแล้ว (ยังถืออยู่ {t.open_at_end} ตำแหน่ง)</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div><div className="text-xs text-muted-foreground">รอบที่ปิดแล้ว</div><div>{t.closed_trades}</div></div>
          <div><div className="text-xs text-muted-foreground">Win rate</div><div className="tabular-nums">{pct(t.win_rate, 1)}</div></div>
          <div><div className="text-xs text-muted-foreground">เฉลี่ยรอบชนะ</div><div className={`tabular-nums ${signCls(t.avg_win)}`}>{pct(t.avg_win)}</div></div>
          <div><div className="text-xs text-muted-foreground">เฉลี่ยรอบแพ้</div><div className={`tabular-nums ${signCls(t.avg_loss)}`}>{pct(t.avg_loss)}</div></div>
          <div><div className="text-xs text-muted-foreground">Profit factor</div><div className="tabular-nums">{t.profit_factor == null ? "ไม่มีรอบขาดทุน" : t.profit_factor.toFixed(2)}</div></div>
          <div><div className="text-xs text-muted-foreground">Expectancy ต่อรอบ</div><div className={`tabular-nums ${signCls(t.expectancy)}`}>{pct(t.expectancy)}</div></div>
          <div><div className="text-xs text-muted-foreground">ถือเฉลี่ย (วันทำการ)</div><div className="tabular-nums">{t.avg_holding_days?.toFixed(1)}</div></div>
          <div><div className="text-xs text-muted-foreground">แพ้ติดกันสูงสุด</div><div>{t.max_consecutive_losses}</div></div>
          <div><div className="text-xs text-muted-foreground">รอบดีสุด</div><div className={`tabular-nums ${signCls(t.best_trade)}`}>{pct(t.best_trade)}</div></div>
          <div><div className="text-xs text-muted-foreground">รอบแย่สุด</div><div className={`tabular-nums ${signCls(t.worst_trade)}`}>{pct(t.worst_trade)}</div></div>
          <div><div className="text-xs text-muted-foreground">ยังถืออยู่ปลายช่วง</div><div>{t.open_at_end}</div></div>
        </div>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        เหตุผลที่ออก: {Object.entries(sr.exit_reasons).map(([k, v]) => `${REASON_LABEL[k] ?? k} ${v}`).join(" · ") || "—"}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        สัญญาณเข้าครั้งแรก: {Object.entries(sr.first_entry_signal).map(([k, v]) => `${k} ${v ?? "ไม่เคยมี"}`).join(" · ")}
      </p>
      <button type="button" className="mt-2 text-xs text-primary hover:underline" onClick={() => setShow((v) => !v)}>
        {show ? "ซ่อนรายการรอบ" : `แสดงรายการรอบ (${sr.trips.length})`}
      </button>
      {show && (
        <div className="mt-2 max-h-80 overflow-auto">
          <table className="w-full min-w-[560px] text-xs tabular-nums">
            <thead className="sticky top-0 bg-zinc-900 text-left text-muted-foreground">
              <tr><th className="py-1 font-normal">หุ้น</th><th className="font-normal">เข้า</th><th className="font-normal">ออก</th>
                <th className="text-right font-normal">ผลตอบแทน</th><th className="text-right font-normal">วัน</th><th className="pl-3 font-normal">เหตุผล</th></tr>
            </thead>
            <tbody>
              {sr.trips.map((x, i) => (
                <tr key={`${x.symbol}-${x.entry_date}-${i}`} className="border-t border-border">
                  <td className="py-1">{x.symbol}</td><td>{x.entry_date}</td><td>{x.exit_date ?? "—"}</td>
                  <td className={`text-right ${signCls(x.return)}`}>{pct(x.return)}</td><td className="text-right">{x.holding_days}</td>
                  <td className="pl-3 text-muted-foreground">{REASON_LABEL[x.exit_reason] ?? x.exit_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
