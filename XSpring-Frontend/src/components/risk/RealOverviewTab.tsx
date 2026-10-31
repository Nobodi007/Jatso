import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

/* ภาพรวมพอร์ตจริง: มูลค่าล่าสุด (ราคาปิดล่าสุด ไม่ใช่ราคาสด) เงินสด สถานะที่ถือ และกำไรขาดทุนที่ยังไม่ขาย
   อ่านจาก /api/stocks/risk/overview และ /exposure ด้วย portfolio=real (ใช้แคชรายงาน 60 วินาทีเดิม ไม่เรียกราคาสด) */

interface Pos {
  symbol: string; qty?: number; price?: number; avg_cost?: number | null;
  market_value: number; weight_nav: number; unrealized_pnl?: number | null;
}
interface Overview {
  meta: { as_of?: string; data_status?: string; warnings?: { code: string; symbol?: string | null }[] };
  cards: { market_value?: { value: number | null } };
}
interface Exposure { exposure: { nav: number; equity_value: number; cash: number; cash_weight: number; positions: Pos[] } | null }

const usd = (n: number | null | undefined, sign = false) =>
  n == null || !Number.isFinite(n)
    ? "—"
    : `${sign && n > 0 ? "+" : ""}${n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })}`;
const pct = (n: number | null | undefined, d = 1, sign = false) =>
  n == null || !Number.isFinite(n) ? "—" : `${sign && n > 0 ? "+" : ""}${(n * 100).toFixed(d)}%`;
const tone = (n: number | null | undefined) => (n == null || n === 0 ? "text-foreground" : n > 0 ? "text-emerald-500" : "text-rose-500");

const STATUS: Record<string, string> = {
  no_account: "ยังไม่มีพอร์ตจริง ไปที่แท็บ “รายการ” เพื่อกรอกเงินฝากและรายการซื้อขาย",
  no_activity: "ยังไม่มีรายการซื้อขาย (อาจมีแต่เงินฝาก) ไปที่แท็บ “รายการ” เพื่อกรอกรายการซื้อ",
  incomplete: "คำนวณมูลค่าไม่ครบ เพราะราคาของบางตัวขาดหาย ระบบไม่เดามูลค่าให้ (ดูรายละเอียดในแท็บ Risk)",
  ledger_integrity_error: "รายการซื้อขายไม่สอดคล้องกัน (เช่น ขายเกินที่ถือ) ตรวจในแท็บ “รายการ”",
  unavailable: "ดึงข้อมูลตลาดไม่สำเร็จ ลองรีเฟรชภายหลัง",
};

function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-3xl border border-border bg-card p-5">{children}</div>;
}

export default function RealOverviewTab({ getToken, apiBase = "" }: { getToken?: () => string | null; apiBase?: string }) {
  const [ov, setOv] = useState<Overview | null>(null);
  const [ex, setEx] = useState<Exposure | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const get = useCallback(
    async <T,>(path: string): Promise<T> => {
      const token = typeof getToken === "function" ? getToken() : null;
      const r = await fetch(`${apiBase}/api/stocks/risk${path}?portfolio=real`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) throw new Error(r.status === 401 ? "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่" : r.status === 429 ? "เรียกถี่เกินไป รอสักครู่แล้วลองใหม่" : `เซิร์ฟเวอร์ตอบ ${r.status}`);
      return (await r.json()) as T;
    },
    [getToken, apiBase],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [o, e] = await Promise.all([get<Overview>("/overview"), get<Exposure>("/exposure")]);
      // exposure เป็น null ได้ (พอร์ตว่าง/ยังไม่มีราคา) ถือว่าถูกต้อง แต่ถ้าไม่ใช่ object หรือ positions ไม่ใช่ list = เวอร์ชันหลังบ้านไม่ตรง
      if (!o?.meta || !o?.cards || !e || typeof e !== "object" || (e.exposure != null && !Array.isArray(e.exposure.positions))) {
        throw new Error("เซิร์ฟเวอร์ตอบข้อมูลไม่ตรงรูปแบบที่คาด (หลังบ้านอาจยังเป็นเวอร์ชันเก่า)");
      }
      setOv(o);
      setEx(e);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, [get]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !ov) return <Panel><p className="text-sm text-muted-foreground">กำลังโหลด…</p></Panel>;
  if (error && !ov) {
    return (
      <Panel>
        <p role="alert" className="text-sm text-rose-400">{error}</p>
        <button onClick={() => void load()} className="mt-3 rounded-full border border-border px-4 py-2 text-sm">ลองใหม่</button>
      </Panel>
    );
  }
  if (!ov || !ex) return null;

  const e = ex.exposure;                       // null = ยังไม่มีหุ้นที่มีราคา
  const status = STATUS[ov.meta.data_status ?? ""];
  const pos = [...(e?.positions ?? [])].sort((a, b) => b.market_value - a.market_value);
  const unr = pos.reduce((sum, p) => sum + (p.unrealized_pnl ?? 0), 0);
  const cost = pos.reduce((sum, p) => sum + (p.avg_cost != null && p.qty != null ? p.avg_cost * p.qty : 0), 0);
  const priced = pos.every((p) => p.unrealized_pnl != null);

  return (
    <div className="space-y-5">
      {status && <div role="status" className="rounded-3xl border border-border bg-card p-4 text-sm">{status}</div>}
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-medium">มูลค่าพอร์ตจริง</h2>
          <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">
            ราคาปิด ณ {ov.meta.as_of ? ov.meta.as_of.slice(0, 10) : "—"} (ไม่ใช่ราคาสด)
          </span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
          <div><p className="text-xs text-muted-foreground">มูลค่ารวม (NAV)</p><p className="mt-1 text-2xl font-medium tabular-nums">{usd(ov.cards.market_value?.value)}</p></div>
          <div><p className="text-xs text-muted-foreground">หุ้น</p><p className="mt-1 text-lg font-medium tabular-nums">{usd(e?.equity_value)}</p></div>
          <div><p className="text-xs text-muted-foreground">เงินสด</p><p className="mt-1 text-lg font-medium tabular-nums">{usd(e?.cash)} <span className="text-xs text-muted-foreground">({pct(e?.cash_weight)})</span></p></div>
          <div>
            <p className="text-xs text-muted-foreground">กำไรขาดทุนที่ยังไม่ขาย</p>
            <p className={`mt-1 text-lg font-medium tabular-nums ${tone(unr)}`}>{usd(unr, true)}</p>
            <p className="text-[11px] text-muted-foreground">{cost > 0 ? `${pct(unr / cost, 2, true)} ของต้นทุน` : ""}{priced ? "" : " · บางตัวไม่มีต้นทุน"}</p>
          </div>
        </div>
      </Panel>

      <Panel>
        <h2 className="text-base font-medium">สถานะที่ถืออยู่</h2>
        {pos.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">ยังไม่มีหุ้นที่ถืออยู่</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[620px] text-sm tabular-nums">
              <thead><tr className="text-left text-xs text-muted-foreground">
                <th className="py-1 pr-3 font-normal">หุ้น</th><th className="py-1 pr-3 text-right font-normal">จำนวน</th>
                <th className="py-1 pr-3 text-right font-normal">ต้นทุนเฉลี่ย</th><th className="py-1 pr-3 text-right font-normal">ราคาปิด</th>
                <th className="py-1 pr-3 text-right font-normal">มูลค่า</th><th className="py-1 pr-3 text-right font-normal">น้ำหนัก</th>
                <th className="py-1 text-right font-normal">กำไรขาดทุนที่ยังไม่ขาย</th>
              </tr></thead>
              <tbody>
                {pos.map((p) => (
                  <tr key={p.symbol} className="border-t border-border">
                    <td className="py-1.5 pr-3 font-medium">{p.symbol}</td>
                    <td className="py-1.5 pr-3 text-right">{p.qty ?? "—"}</td>
                    <td className="py-1.5 pr-3 text-right text-muted-foreground">{usd(p.avg_cost)}</td>
                    <td className="py-1.5 pr-3 text-right">{usd(p.price)}</td>
                    <td className="py-1.5 pr-3 text-right">{usd(p.market_value)}</td>
                    <td className="py-1.5 pr-3 text-right">{pct(p.weight_nav)}</td>
                    <td className={`py-1.5 text-right ${tone(p.unrealized_pnl)}`}>
                      {usd(p.unrealized_pnl, true)}
                      {p.unrealized_pnl != null && p.avg_cost && p.qty ? ` (${pct(p.unrealized_pnl / (p.avg_cost * p.qty), 1, true)})` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          ต้นทุนเฉลี่ยไม่รวมค่าธรรมเนียม · ราคาปิดรายวัน อาจต่างจากราคาใน Webull ที่เป็นราคาสด · ผลตอบแทนและตัวชี้วัดความเสี่ยงดูในแท็บ Risk
        </p>
      </Panel>
    </div>
  );
}
