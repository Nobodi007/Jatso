import { LineChart, Panel, Stat, Tag } from "./RiskPanel"
import type { AccumulateResult } from "./accumulateTypes"

/* แผงผลของโหมดทยอยสะสม (DCA / Buy-the-dip) — ใช้: {r.mode === "accumulate" && <AccumulatePanel result={r} />} */

const usd = (v: number | null | undefined, sign = false) =>
  v == null || !Number.isFinite(v) ? "—" : `${sign && v > 0 ? "+" : ""}${v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })}`
const pctS = (v: number | null | undefined, d = 1, sign = false) =>
  v == null || !Number.isFinite(v) ? "—" : `${sign && v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "text-foreground" : v > 0 ? "text-emerald-500" : "text-rose-500")

export default function AccumulatePanel({ result }: { result: AccumulateResult }) {
  const st = result.stats
  const ar = result.accumulate_result
  if (!ar || st.total_invested == null) return null
  const pts = result.series.filter((x) => x.value != null && x.invested != null)
  const cols: { name: string; final: number | undefined; profit: number | undefined; mwr: number | null | undefined }[] = [
    { name: "DCA / ซื้อตอนย่อ (พอร์ตนี้)", final: st.final_value, profit: st.profit, mwr: st.money_weighted_return },
    { name: "ลงทันที (หุ้นชุดเดียวกัน)", final: st.buy_hold_final_value, profit: st.buy_hold_profit, mwr: st.buy_hold_money_weighted_return },
    { name: "S&P 500 (กระแสเงินเดียวกัน)", final: st.benchmark_final_value, profit: st.benchmark_profit, mwr: st.benchmark_money_weighted_return },
  ]
  const bc = ar.buy_counts
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">ผลการทยอยสะสม (DCA / Buy-the-dip)</h2>
        <Tag>เงินที่ใส่รวม {usd(st.total_invested)}</Tag>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="เงินต้น" value={usd(st.initial_capital)} />
        <Stat label="เงินเติมระหว่างทาง" value={usd(st.total_contributed)} note={`${ar.contribution_events} ครั้ง`} />
        <Stat label="กำไร/ขาดทุน (เงิน)" value={usd(st.profit, true)} cls={tone(st.profit)} note={`${pctS(st.profit_pct_invested, 1, true)} ของเงินที่ใส่`} />
        <Stat label="ลงทุนอยู่เฉลี่ย" value={pctS(st.time_in_market, 0)} note="ส่วนที่เหลือเป็นเงินสดไม่มีดอกเบี้ย" />
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1 pr-3 font-normal">เทียบด้วยกระแสเงินชุดเดียวกัน</th>
              <th className="py-1 pr-3 text-right font-normal">มูลค่าสิ้นสุด</th>
              <th className="py-1 pr-3 text-right font-normal">กำไร</th>
              <th className="py-1 text-right font-normal">IRR ต่อปี</th>
            </tr>
          </thead>
          <tbody>
            {cols.map((c) => (
              <tr key={c.name} className="border-t border-border">
                <td className="py-1.5 pr-3">{c.name}</td>
                <td className="py-1.5 pr-3 text-right">{usd(c.final)}</td>
                <td className={`py-1.5 pr-3 text-right ${tone(c.profit)}`}>{usd(c.profit, true)}</td>
                <td className={`py-1.5 text-right ${tone(c.mwr)}`}>{c.mwr == null ? "—" : pctS(c.mwr, 2, true)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-muted-foreground">
          IRR = ผลตอบแทนถ่วงเงินตามวันที่เงินเข้าจริง (แสดงเมื่อช่วงทดสอบ ≥ 1 ปี) · ตัวชี้วัดความเสี่ยงอื่นในหน้านี้ใช้ผลตอบแทนถ่วงเวลา ห้ามเทียบกับกำไรเป็นเงินตรง ๆ
        </p>
      </div>

      {pts.length >= 2 && (
        <div className="mt-5">
          <p className="mb-2 text-sm text-muted-foreground">มูลค่าพอร์ตเทียบเงินที่ใส่สะสม</p>
          <LineChart
            dates={pts.map((x) => x.date)}
            label="มูลค่าพอร์ตเทียบเงินที่ใส่สะสม"
            fmt={(v) => (v == null ? "—" : usd(v))}
            lines={[
              { name: "มูลค่าพอร์ต", values: pts.map((x) => x.value ?? null), stroke: "stroke-sky-500", swatch: "bg-sky-500", fill: "fill-sky-500" },
              { name: "เงินที่ใส่สะสม", values: pts.map((x) => x.invested ?? null), stroke: "stroke-muted-foreground", swatch: "bg-muted-foreground", fill: "fill-muted-foreground" },
            ]}
          />
        </div>
      )}

      <div className="mt-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <p className="text-sm text-muted-foreground">การซื้อที่เกิดขึ้น</p>
          <Tag>ซื้อแรก {bc.initial}</Tag>
          <Tag>DCA {bc.schedule}</Tag>
          <Tag>ซื้อตอนย่อ {bc.dip}</Tag>
          {(ar.blocked.no_cash > 0 || ar.blocked.cap > 0) && <Tag warn>ซื้อไม่ได้: เงินหมด {ar.blocked.no_cash} · ชนเพดาน {ar.blocked.cap}</Tag>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1 pr-3 font-normal">หุ้น</th>
                <th className="py-1 pr-3 text-right font-normal">เงินซื้อสะสม</th>
                <th className="py-1 pr-3 text-right font-normal">ต้นทุนเฉลี่ย</th>
                <th className="py-1 pr-3 text-right font-normal">มูลค่าปัจจุบัน</th>
                <th className="py-1 pr-3 text-right font-normal">กำไรจากต้นทุน</th>
                <th className="py-1 pr-3 text-right font-normal">เงินสดเหลือ</th>
                <th className="py-1 text-right font-normal">ครั้ง</th>
              </tr>
            </thead>
            <tbody>
              {ar.per_stock.map((p) => (
                <tr key={p.symbol} className="border-t border-border">
                  <td className="py-1.5 pr-3 font-medium">{p.symbol}</td>
                  <td className="py-1.5 pr-3 text-right">{usd(p.invested)}</td>
                  <td className="py-1.5 pr-3 text-right">{p.avg_cost == null ? "—" : p.avg_cost.toFixed(2)}</td>
                  <td className="py-1.5 pr-3 text-right">{usd(p.market_value)}</td>
                  <td className={`py-1.5 pr-3 text-right ${tone(p.return_on_cost)}`}>{pctS(p.return_on_cost, 1, true)}</td>
                  <td className="py-1.5 pr-3 text-right">{usd(p.cash_left)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{p.buys}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Panel>
  )
}
