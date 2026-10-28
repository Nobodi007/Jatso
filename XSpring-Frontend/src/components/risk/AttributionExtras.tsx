import type { ReactNode } from "react";

/* ───────── types (ตรงกับ /api/stocks/risk/attribution) ───────── */
export interface CashDrag { value: number; avg_cash_weight: number; memo: boolean; note: string }
export interface SectorContribution { sector: string; contribution: number; avg_weight_nav: number; symbols: string[] }
export interface PnlRow {
  symbol: string; open_qty: number; avg_cost: number | null; price: number | null;
  realized_gross: number; fees: number; unrealized: number | null; total_net: number | null;
}
export interface PnlBreakdown {
  basis: string; symbols: PnlRow[]; realized_gross: number; unrealized: number; fees_paid: number; total_net: number;
  incomplete_symbols: string[];
  check?: { nav_change: number; total_net: number; difference: number; ok: boolean };
}

/* ───────── helpers ───────── */
const usd = (n: number | null | undefined, sign = false) =>
  n == null || !Number.isFinite(n)
    ? "—"
    : `${sign && n > 0 ? "+" : ""}${n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })}`;
const pp = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)} pp`;
const pct1 = (v: number) => `${(v * 100).toFixed(1)}%`;
const tone = (n: number | null | undefined) =>
  n == null || n === 0 ? "text-foreground" : n > 0 ? "text-emerald-500" : "text-rose-500";

function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-3xl border border-border bg-card p-5">{children}</div>;
}
function Tag({ children, kind = "muted" }: { children: ReactNode; kind?: "muted" | "ok" | "bad" | "warn" }) {
  const cls = { muted: "bg-muted text-muted-foreground", ok: "bg-emerald-500/10 text-emerald-500",
    bad: "bg-rose-500/10 text-rose-500", warn: "bg-amber-500/10 text-amber-500" }[kind];
  return <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs ${cls}`}>{children}</span>;
}
function Bar({ value, max, good }: { value: number; max: number; good: boolean }) {
  const w = max > 0 ? Math.min(Math.abs(value) / max, 1) * 100 : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${good ? "bg-emerald-500" : "bg-rose-500"}`} style={{ width: `${w}%` }} />
    </div>
  );
}

/* ───────── cash drag (memo) ───────── */
export function CashDragNote({ c }: { c?: CashDrag | null }) {
  if (!c) return null;
  const helped = c.value > 0;
  return (
    <div className="mt-4 rounded-2xl border border-border p-3 text-sm" title={c.note}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          Cash drag <Tag>ข้อมูลประกอบ ไม่รวมในผลรวม</Tag>
        </span>
        <span className={`tabular-nums ${tone(c.value)}`}>{pp(c.value)}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        เงินสดเฉลี่ย {pct1(c.avg_cash_weight)} ของ NAV · {helped ? "เงินสดช่วยลดการขาดทุนจากหุ้นในช่วงนี้" : "การถือเงินสดทำให้ผลตอบแทนต่ำกว่าถ้าลงทุนเต็มจำนวน"}{" "}
        (เงินสดในระบบไม่มีดอกเบี้ย)
      </p>
    </div>
  );
}

/* ───────── ส่วนร่วมราย sector ───────── */
export function SectorContributionSection({ rows, note }: { rows?: SectorContribution[] | null; note?: string }) {
  if (!rows || rows.length === 0) return null;
  const max = Math.max(...rows.map((r) => Math.abs(r.contribution)), 1e-9);
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">ส่วนร่วมต่อผลตอบแทนแยกตามอุตสาหกรรม</h2>
        <Tag kind="warn">ประมาณ ไม่ใช่ GICS</Tag>
      </div>
      <ul className="mt-4 space-y-3">
        {rows.map((r) => (
          <li key={r.sector}>
            <div className="mb-1 flex items-center justify-between gap-2 text-sm">
              <span>{r.sector === "Unknown" ? "ไม่ทราบอุตสาหกรรม" : r.sector}</span>
              <span className={`tabular-nums ${tone(r.contribution)}`}>{pp(r.contribution)}</span>
            </div>
            <Bar value={r.contribution} max={max} good={r.contribution >= 0} />
            <p className="mt-1 text-xs text-muted-foreground">{r.symbols.join(", ")}</p>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">
        รวมตัวที่ขายไปแล้วในช่วงเดียวกับตาราง “ที่มาของผลตอบแทน” · ผลรวมทุกอุตสาหกรรมเท่ากับผลรวมส่วนร่วมรายตัว (ไม่รวมส่วนซื้อขาย/ค่าธรรมเนียม)
        {note ? ` · ${note}` : ""}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        ไม่ใช่ Brinson: ไม่มีน้ำหนักอุตสาหกรรมของ S&amp;P 500 จึงแยก allocation/selection เทียบดัชนีไม่ได้
      </p>
    </Panel>
  );
}

/* ───────── Realized / Unrealized P&L ───────── */
export function PnlSection({ p }: { p?: PnlBreakdown | null }) {
  const title = <h2 className="text-base font-medium">กำไรขาดทุน Realized / Unrealized</h2>;
  if (!p) {
    return (
      <Panel>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">ยังคำนวณไม่ได้</p>
      </Panel>
    );
  }
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {title}
        <Tag>ตั้งแต่ซื้อครั้งแรก · ต้นทุนเฉลี่ย</Tag>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          ["Realized (ก่อนค่าธรรมเนียม)", p.realized_gross],
          ["Unrealized", p.unrealized],
          ["ค่าธรรมเนียมที่จ่าย", -p.fees_paid],
          ["รวมสุทธิ", p.total_net],
        ].map(([label, v]) => (
          <div key={label as string}>
            <p className="text-xs text-muted-foreground">{label as string}</p>
            <p className={`mt-1 text-lg font-medium tabular-nums ${tone(v as number)}`}>{usd(v as number, true)}</p>
          </div>
        ))}
      </div>

      {p.symbols.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="py-1 pr-3 font-normal">หุ้น</th>
                <th className="py-1 pr-3 text-right font-normal">ถืออยู่</th>
                <th className="py-1 pr-3 text-right font-normal">ต้นทุนเฉลี่ย</th>
                <th className="py-1 pr-3 text-right font-normal">Realized</th>
                <th className="py-1 pr-3 text-right font-normal">Unrealized</th>
                <th className="py-1 text-right font-normal">ค่าธรรมเนียม</th>
              </tr>
            </thead>
            <tbody>
              {p.symbols.map((r) => (
                <tr key={r.symbol} className="border-t border-border">
                  <td className="py-1.5 pr-3">{r.symbol}</td>
                  <td className="py-1.5 pr-3 text-right text-muted-foreground">{r.open_qty > 1e-9 ? r.open_qty : "ขายหมด"}</td>
                  <td className="py-1.5 pr-3 text-right text-muted-foreground">{usd(r.avg_cost)}</td>
                  <td className={`py-1.5 pr-3 text-right ${tone(r.realized_gross)}`}>{usd(r.realized_gross, true)}</td>
                  <td className={`py-1.5 pr-3 text-right ${tone(r.unrealized)}`}>{usd(r.unrealized, true)}</td>
                  <td className="py-1.5 text-right text-muted-foreground">{usd(r.fees)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-muted-foreground">
        {p.check && (
          <Tag kind={p.check.ok ? "ok" : "bad"}>{p.check.ok ? "ตรงกับการเปลี่ยนแปลงของ NAV" : "ไม่ตรงกับ NAV"}</Tag>
        )}
        <span className="tabular-nums">
          {p.check
            ? `NAV เปลี่ยน ${usd(p.check.nav_change, true)} · realized + unrealized − ค่าธรรมเนียม = ${usd(p.check.total_net, true)}`
            : "ยังตรวจกับ NAV ไม่ได้"}
        </span>
      </div>
      {p.incomplete_symbols.length > 0 && (
        <p className="mt-2 text-xs text-amber-500">
          ไม่มีราคาล่าสุดของ {p.incomplete_symbols.join(", ")} จึงไม่นับ Unrealized ของตัวนี้ในยอดรวม
        </p>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        เป็นยอดเงินดอลลาร์สะสมตั้งแต่ซื้อครั้งแรก ไม่ใช่ผลตอบแทนแบบ time-weighted ในช่วง 1 ปีด้านบน จึงเทียบตัวเลขตรง ๆ กันไม่ได้ · ไม่รวมปันผล
      </p>
    </Panel>
  );
}
