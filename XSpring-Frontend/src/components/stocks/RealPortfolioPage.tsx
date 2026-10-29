import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

/* พอร์ตจริง: กรอกเองจากรายการของโบรกเกอร์ (เช่น Webull) 1 อีเมล = 1 บัญชี ไม่ได้เชื่อมต่อบัญชีโบรกเกอร์
   ตรงกับ api/stocks/real_book.py · ยังไม่เชื่อมกับ Risk Center */

interface Trade {
  id: number; symbol: string; side: "buy" | "sell"; qty: number; price: number; fee: number;
  trade_date: string; after_close: boolean; note?: string | null;
}
interface Flow { id: number; flow_date: string; amount: number; note?: string | null }
interface Position { symbol: string; qty: number; avg_cost: number; realized_gross: number; fees: number }
interface Warn { code: string; date?: string; balance?: number; symbol?: string; detail?: string }
interface Summary {
  account: { broker: string } | null;
  positions: Position[];
  cash_balance: number; realized_gross: number; fees_paid: number;
  counts: { trades: number; cash_flows: number };
  warnings: Warn[];
}

class ApiError extends Error {
  code: string;
  status: number;
  extra: Record<string, unknown>;
  constructor(status: number, code: string, extra: Record<string, unknown> = {}) {
    super(code);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

const ERR_TEXT: Record<string, string> = {
  invalid_symbol: "สัญลักษณ์ไม่ถูกต้อง (ตัวอักษรภาษาอังกฤษ เช่น MU, META, BRK.B)",
  invalid_side: "ต้องเลือกซื้อหรือขาย",
  invalid_amount: "จำนวน ราคา หรือค่าธรรมเนียมไม่ถูกต้อง",
  invalid_broker: "ชื่อโบรกเกอร์ต้องยาว 1–40 ตัวอักษร",
  note_too_long: "หมายเหตุยาวเกิน 200 ตัวอักษร",
  date_too_early: "วันที่ต้องไม่ก่อนปี 2010",
  trade_in_future: "วันที่ซื้อขายอยู่ในอนาคต (วันที่ตามเวลาสหรัฐ)",
  flow_in_future: "วันที่ฝาก/ถอนอยู่ในอนาคต",
  symbol_not_found: "ไม่พบสัญลักษณ์นี้ ตรวจตัวสะกดอีกครั้ง",
  duplicate_trade: "มีรายการเหมือนกันเป๊ะอยู่แล้ว",
  ledger_inconsistent: "บันทึกไม่ได้ เพราะจะทำให้ยอดถือครองติดลบ (ขายเกินที่ถือในวันนั้น หรือยกเลิกรายการซื้อที่มีการขายตามมา)",
  trade_not_found: "ไม่พบรายการนี้ (อาจถูกยกเลิกไปแล้ว)",
  cash_flow_not_found: "ไม่พบรายการนี้ (อาจถูกยกเลิกไปแล้ว)",
  too_many_trades: "จำนวนรายการซื้อขายเต็มขีดจำกัดแล้ว",
  too_many_cash_flows: "จำนวนรายการฝาก/ถอนเต็มขีดจำกัดแล้ว",
};

const todayET = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
const usd = (n: number | null | undefined, sign = false) =>
  n == null || !Number.isFinite(n)
    ? "—"
    : `${sign && n > 0 ? "+" : ""}${n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })}`;
const tone = (n: number) => (n > 0 ? "text-emerald-500" : n < 0 ? "text-rose-500" : "text-foreground");
const SYMBOL_RE = /^[A-Z][A-Z0-9.-]{0,9}$/;
const num = (s: string) => (s.trim() === "" ? NaN : Number(s));

const warnText = (w: Warn): string => {
  switch (w.code) {
    case "negative_cash":
      return `เงินสดติดลบตั้งแต่ ${w.date} (${usd(w.balance)}) ตรวจว่าลืมกรอกเงินฝากหรือกรอกวันที่ผิดหรือไม่`;
    case "symbol_unverified":
      return `ตรวจสัญลักษณ์ ${w.symbol} ไม่ได้ในตอนนี้ (บันทึกแล้ว ตรวจตัวสะกดด้วยตัวเอง)`;
    case "splits_unavailable":
      return "ดึงข้อมูล split ไม่สำเร็จ จำนวนที่แสดงอาจยังไม่ปรับ split";
    default:
      return w.code;
  }
};

function Panel({ children }: { children: ReactNode }) {
  return <div className="rounded-3xl border border-border bg-card p-5">{children}</div>;
}
const field = "w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:border-emerald-500";
const btn = "rounded-full px-4 py-2 text-sm font-medium disabled:opacity-50";

export default function RealPortfolioPage({ getToken, apiBase = "" }: { getToken?: () => string | null; apiBase?: string }) {
  const authed = !!(typeof getToken === "function" && getToken());
  const [sum, setSum] = useState<Summary | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [flows, setFlows] = useState<Flow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [broker, setBroker] = useState("");

  const [t, setT] = useState({ symbol: "", side: "buy" as "buy" | "sell", qty: "", price: "", fee: "0", date: todayET(), after: false, note: "" });
  const [dup, setDup] = useState(false);
  const [f, setF] = useState({ kind: "deposit" as "deposit" | "withdraw", amount: "", date: todayET(), note: "" });

  const call = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const token = typeof getToken === "function" ? getToken() : null;
      const r = await fetch(`${apiBase}/api/stocks/real${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
      const j = await r.json().catch(() => null);
      if (!r.ok) {
        if (r.status === 401) throw new ApiError(401, "session_expired");
        if (r.status === 429) throw new ApiError(429, "rate_limited");
        const d = j?.detail;
        throw new ApiError(r.status, typeof d === "object" && d?.code ? d.code : "server_error", typeof d === "object" ? d : {});
      }
      return j as T;
    },
    [getToken, apiBase],
  );

  const msgOf = (e: unknown): string => {
    if (!(e instanceof ApiError)) return "เกิดข้อผิดพลาด ลองใหม่อีกครั้ง";
    if (e.code === "session_expired") return "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่";
    if (e.code === "rate_limited") return "เรียกถี่เกินไป กรุณารอสักครู่แล้วลองใหม่";
    if (e.code === "server_error") return `เซิร์ฟเวอร์ตอบ ${e.status} ลองใหม่อีกครั้ง`;
    const base = ERR_TEXT[e.code] ?? e.code;
    return e.code === "ledger_inconsistent" && typeof e.extra.message === "string" ? `${base} (${e.extra.message})` : base;
  };

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, tr, fl] = await Promise.all([
        call<Summary>("/summary"),
        call<{ trades: Trade[] }>("/trades?limit=500"),
        call<{ cash_flows: Flow[] }>("/cash-flows?limit=500"),
      ]);
      setSum(s);
      setTrades(tr.trades);
      setFlows(fl.cash_flows);
      setBroker((b) => b || s.account?.broker || "");
    } catch (e) {
      setError(msgOf(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [call]);

  useEffect(() => {
    if (authed) void load();
    else setLoading(false);
  }, [authed, load]);

  const run = async (fn: () => Promise<string[] | void>) => {
    setBusy(true);
    setError(null);
    setNotice([]);
    try {
      const w = await fn();
      if (w) setNotice(w);
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.code === "duplicate_trade") setDup(true);
      setError(msgOf(e));
    } finally {
      setBusy(false);
    }
  };

  const saveBroker = () =>
    run(async () => {
      const b = broker.trim();
      if (b.length < 1 || b.length > 40) throw new ApiError(400, "invalid_broker");
      await call("/account", { method: "PUT", body: JSON.stringify({ broker: b }) });
    });

  const submitTrade = (confirmDuplicate = false) => {
    const sym = t.symbol.trim().toUpperCase();
    const qty = num(t.qty), price = num(t.price), fee = num(t.fee);
    if (!SYMBOL_RE.test(sym)) return setError(ERR_TEXT.invalid_symbol);
    if (!(qty > 0) || !(price > 0) || !(fee >= 0) || ![qty, price, fee].every(Number.isFinite)) return setError(ERR_TEXT.invalid_amount);
    if (!t.date) return setError("เลือกวันที่ซื้อขาย");
    setDup(false);
    return run(async () => {
      const r = await call<{ warnings: Warn[] }>("/trades", {
        method: "POST",
        body: JSON.stringify({ symbol: sym, side: t.side, qty, price, fee, trade_date: t.date, after_close: t.after,
          note: t.note.trim() || null, confirm_duplicate: confirmDuplicate }),
      });
      setT((x) => ({ ...x, symbol: "", qty: "", price: "", note: "" }));
      return r.warnings.map(warnText);
    });
  };

  const submitFlow = () => {
    const amt = num(f.amount);
    if (!(amt > 0) || !Number.isFinite(amt)) return setError("ใส่จำนวนเงินเป็นตัวเลขมากกว่า 0");
    if (!f.date) return setError("เลือกวันที่");
    return run(async () => {
      const r = await call<{ warnings: Warn[] }>("/cash-flows", {
        method: "POST",
        body: JSON.stringify({ flow_date: f.date, amount: f.kind === "deposit" ? amt : -amt, note: f.note.trim() || null }),
      });
      setF((x) => ({ ...x, amount: "", note: "" }));
      return r.warnings.map(warnText);
    });
  };

  const voidTrade = (x: Trade) => {
    if (!window.confirm(`ยกเลิกรายการ ${x.side === "buy" ? "ซื้อ" : "ขาย"} ${x.symbol} ${x.qty} หุ้น วันที่ ${x.trade_date}?`)) return;
    void run(async () => {
      const r = await call<{ warnings: Warn[] }>(`/trades/${x.id}`, { method: "DELETE" });
      return r.warnings.map(warnText);
    });
  };
  const voidFlow = (x: Flow) => {
    if (!window.confirm(`ยกเลิกรายการ${x.amount > 0 ? "ฝาก" : "ถอน"} ${usd(Math.abs(x.amount))} วันที่ ${x.flow_date}?`)) return;
    void run(async () => {
      const r = await call<{ warnings: Warn[] }>(`/cash-flows/${x.id}`, { method: "DELETE" });
      return r.warnings.map(warnText);
    });
  };

  if (!authed) {
    return <Panel><p className="text-sm text-muted-foreground">เข้าสู่ระบบเพื่อบันทึกพอร์ตจริง</p></Panel>;
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">พอร์ตจริง</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          กรอกเองจากรายการของโบรกเกอร์ ไม่ได้เชื่อมต่อบัญชีโบรกเกอร์ · ยังไม่เชื่อมกับ Risk Center (ตัวเลขความเสี่ยงยังมาจากพอร์ตจำลอง)
        </p>
      </div>

      {error && <p role="alert" className="rounded-xl bg-rose-500/10 px-3 py-2 text-sm text-rose-400">{error}</p>}
      {notice.length > 0 && (
        <div className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-500">
          {notice.map((n) => <p key={n}>{n}</p>)}
        </div>
      )}
      {dup && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border px-3 py-2 text-sm">
          <span>ถ้าเป็นคนละรายการที่ซื้อขายพร้อมกัน (เช่น แบ่งจับคู่หลายครั้ง) ยืนยันเพื่อบันทึกซ้ำ</span>
          <button onClick={() => void submitTrade(true)} disabled={busy} className={`${btn} bg-emerald-500 text-black`}>บันทึกซ้ำ</button>
          <button onClick={() => setDup(false)} className={`${btn} border border-border`}>ยกเลิก</button>
        </div>
      )}

      <Panel>
        <div className="flex flex-wrap items-end gap-3">
          <label className="block text-sm">
            <span className="text-xs text-muted-foreground">โบรกเกอร์</span>
            <input className={`${field} mt-1 w-56`} value={broker} maxLength={40} placeholder="เช่น Webull"
              onChange={(e: { target: { value: string } }) => setBroker(e.target.value)} />
          </label>
          <button onClick={() => void saveBroker()} disabled={busy} className={`${btn} border border-border hover:bg-muted`}>บันทึกชื่อ</button>
        </div>
      </Panel>

      <Panel>
        <h2 className="text-base font-medium">สถานะที่ถืออยู่ (เทียบกับหน้าถือครองใน Webull)</h2>
        {loading ? (
          <p className="mt-3 text-sm text-muted-foreground">กำลังโหลด…</p>
        ) : !sum || sum.counts.trades + sum.counts.cash_flows === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">ยังไม่มีรายการ เริ่มจากกรอกเงินฝากและรายการซื้อด้านล่าง</p>
        ) : (
          <>
            <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
              <div><p className="text-xs text-muted-foreground">เงินสดคงเหลือ</p><p className={`mt-1 text-lg font-medium tabular-nums ${tone(sum.cash_balance)}`}>{usd(sum.cash_balance)}</p></div>
              <div><p className="text-xs text-muted-foreground">Realized (ก่อนค่าธรรมเนียม)</p><p className={`mt-1 text-lg font-medium tabular-nums ${tone(sum.realized_gross)}`}>{usd(sum.realized_gross, true)}</p></div>
              <div><p className="text-xs text-muted-foreground">ค่าธรรมเนียมที่จ่าย</p><p className="mt-1 text-lg font-medium tabular-nums">{usd(sum.fees_paid)}</p></div>
              <div><p className="text-xs text-muted-foreground">จำนวนรายการ</p><p className="mt-1 text-lg font-medium tabular-nums">{sum.counts.trades} ซื้อขาย · {sum.counts.cash_flows} ฝาก/ถอน</p></div>
            </div>
            {sum.positions.length > 0 && (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-sm tabular-nums">
                  <thead><tr className="text-left text-xs text-muted-foreground">
                    <th className="py-1 pr-3 font-normal">หุ้น</th><th className="py-1 pr-3 text-right font-normal">จำนวน</th>
                    <th className="py-1 pr-3 text-right font-normal">ต้นทุนเฉลี่ย</th><th className="py-1 text-right font-normal">Realized</th>
                  </tr></thead>
                  <tbody>
                    {sum.positions.map((p) => (
                      <tr key={p.symbol} className="border-t border-border">
                        <td className="py-1.5 pr-3 font-medium">{p.symbol}</td>
                        <td className="py-1.5 pr-3 text-right">{p.qty}</td>
                        <td className="py-1.5 pr-3 text-right">{usd(p.avg_cost)}</td>
                        <td className={`py-1.5 text-right ${tone(p.realized_gross)}`}>{usd(p.realized_gross, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {sum.warnings.length > 0 && (
              <div className="mt-3 space-y-1 text-xs text-amber-500">{sum.warnings.map((w, i) => <p key={i}>{warnText(w)}</p>)}</div>
            )}
            <p className="mt-3 text-xs text-muted-foreground">จำนวนและต้นทุนเฉลี่ยปรับ split แล้ว · ต้นทุนเฉลี่ยไม่รวมค่าธรรมเนียม · ยังไม่รวมปันผล</p>
          </>
        )}
      </Panel>

      <Panel>
        <h2 className="text-base font-medium">เพิ่มรายการซื้อขาย</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <label className="block text-sm"><span className="text-xs text-muted-foreground">สัญลักษณ์</span>
            <input className={`${field} mt-1 uppercase`} value={t.symbol} maxLength={10} placeholder="MU"
              onChange={(e: { target: { value: string } }) => setT({ ...t, symbol: e.target.value.toUpperCase() })} /></label>
          <div className="text-sm"><span className="text-xs text-muted-foreground">ประเภท</span>
            <div className="mt-1 flex gap-2">
              {(["buy", "sell"] as const).map((s) => (
                <button key={s} type="button" onClick={() => setT({ ...t, side: s })}
                  className={`${btn} flex-1 ${t.side === s ? (s === "buy" ? "bg-emerald-500 text-black" : "bg-rose-500 text-white") : "border border-border"}`}>
                  {s === "buy" ? "ซื้อ" : "ขาย"}
                </button>
              ))}
            </div></div>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">จำนวนหุ้น (ตามที่เกิดขึ้นจริงวันนั้น)</span>
            <input className={`${field} mt-1`} inputMode="decimal" value={t.qty} placeholder="10"
              onChange={(e: { target: { value: string } }) => setT({ ...t, qty: e.target.value })} /></label>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">ราคาต่อหุ้น (USD)</span>
            <input className={`${field} mt-1`} inputMode="decimal" value={t.price} placeholder="95.50"
              onChange={(e: { target: { value: string } }) => setT({ ...t, price: e.target.value })} /></label>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">ค่าธรรมเนียม (USD)</span>
            <input className={`${field} mt-1`} inputMode="decimal" value={t.fee}
              onChange={(e: { target: { value: string } }) => setT({ ...t, fee: e.target.value })} /></label>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">วันที่ (เวลาสหรัฐ ET)</span>
            <input type="date" className={`${field} mt-1`} value={t.date} min="2010-01-01" max={todayET()}
              onChange={(e: { target: { value: string } }) => setT({ ...t, date: e.target.value })} /></label>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input type="checkbox" checked={t.after} onChange={(e: { target: { checked: boolean } }) => setT({ ...t, after: e.target.checked })} />
            <span>ซื้อขายหลังตลาดปิด (หลัง 16:00 ET)</span></label>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">หมายเหตุ (ไม่บังคับ)</span>
            <input className={`${field} mt-1`} value={t.note} maxLength={200}
              onChange={(e: { target: { value: string } }) => setT({ ...t, note: e.target.value })} /></label>
        </div>
        <button onClick={() => void submitTrade(false)} disabled={busy} className={`${btn} mt-4 bg-emerald-500 text-black`}>
          {busy ? "กำลังบันทึก…" : "บันทึกรายการ"}
        </button>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          <li>กรอกจำนวนและราคาตามที่เกิดขึ้นจริงในวันนั้น ไม่ต้องปรับ split ระบบปรับให้เอง</li>
          <li>วันที่เป็นวันตามเวลาสหรัฐ (ET) ถ้า Webull แสดงเวลาไทย รายการที่ซื้อช่วงบ่าย-เย็นตามเวลาสหรัฐจะเป็นวันถัดไปในเวลาไทย ให้แปลงก่อนกรอก</li>
          <li>กรอกเงินฝากด้านล่างด้วย ไม่งั้นเงินสดจะติดลบ (ระบบเตือนแต่ไม่บล็อก)</li>
        </ul>
      </Panel>

      <Panel>
        <h2 className="text-base font-medium">เพิ่มเงินฝาก / ถอน</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="text-sm"><span className="text-xs text-muted-foreground">ประเภท</span>
            <div className="mt-1 flex gap-2">
              {(["deposit", "withdraw"] as const).map((k) => (
                <button key={k} type="button" onClick={() => setF({ ...f, kind: k })}
                  className={`${btn} flex-1 ${f.kind === k ? "bg-emerald-500 text-black" : "border border-border"}`}>
                  {k === "deposit" ? "ฝาก" : "ถอน"}
                </button>
              ))}
            </div></div>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">จำนวนเงิน (USD)</span>
            <input className={`${field} mt-1`} inputMode="decimal" value={f.amount} placeholder="5000"
              onChange={(e: { target: { value: string } }) => setF({ ...f, amount: e.target.value })} /></label>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">วันที่ (ET)</span>
            <input type="date" className={`${field} mt-1`} value={f.date} min="2010-01-01" max={todayET()}
              onChange={(e: { target: { value: string } }) => setF({ ...f, date: e.target.value })} /></label>
          <label className="block text-sm"><span className="text-xs text-muted-foreground">หมายเหตุ (ไม่บังคับ)</span>
            <input className={`${field} mt-1`} value={f.note} maxLength={200}
              onChange={(e: { target: { value: string } }) => setF({ ...f, note: e.target.value })} /></label>
        </div>
        <button onClick={() => void submitFlow()} disabled={busy} className={`${btn} mt-4 bg-emerald-500 text-black`}>บันทึก</button>
      </Panel>

      <Panel>
        <h2 className="text-base font-medium">รายการซื้อขาย</h2>
        {trades.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">ยังไม่มีรายการ</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm tabular-nums">
              <thead><tr className="text-left text-xs text-muted-foreground">
                <th className="py-1 pr-3 font-normal">วันที่ (ET)</th><th className="py-1 pr-3 font-normal">หุ้น</th>
                <th className="py-1 pr-3 font-normal">ประเภท</th><th className="py-1 pr-3 text-right font-normal">จำนวน</th>
                <th className="py-1 pr-3 text-right font-normal">ราคา</th><th className="py-1 pr-3 text-right font-normal">ค่าธรรมเนียม</th>
                <th className="py-1 text-right font-normal" />
              </tr></thead>
              <tbody>
                {trades.map((x) => (
                  <tr key={x.id} className="border-t border-border">
                    <td className="py-1.5 pr-3">{x.trade_date}{x.after_close ? " 🌙" : ""}</td>
                    <td className="py-1.5 pr-3 font-medium" title={x.note ?? ""}>{x.symbol}</td>
                    <td className={`py-1.5 pr-3 ${x.side === "buy" ? "text-emerald-500" : "text-rose-500"}`}>{x.side === "buy" ? "ซื้อ" : "ขาย"}</td>
                    <td className="py-1.5 pr-3 text-right">{x.qty}</td>
                    <td className="py-1.5 pr-3 text-right">{usd(x.price)}</td>
                    <td className="py-1.5 pr-3 text-right text-muted-foreground">{usd(x.fee)}</td>
                    <td className="py-1.5 text-right">
                      <button onClick={() => voidTrade(x)} disabled={busy} className="text-xs text-muted-foreground underline hover:text-foreground">ยกเลิก</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-xs text-muted-foreground">🌙 = หลังตลาดปิด · การยกเลิกไม่ลบรายการจริง แต่เก็บประวัติไว้และไม่นับในยอด</p>
      </Panel>

      <Panel>
        <h2 className="text-base font-medium">เงินฝาก / ถอน</h2>
        {flows.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">ยังไม่มีรายการ</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <tbody>
                {flows.map((x) => (
                  <tr key={x.id} className="border-t border-border first:border-0">
                    <td className="py-1.5 pr-3">{x.flow_date}</td>
                    <td className="py-1.5 pr-3">{x.amount > 0 ? "ฝาก" : "ถอน"}</td>
                    <td className={`py-1.5 pr-3 text-right ${tone(x.amount)}`}>{usd(x.amount, true)}</td>
                    <td className="py-1.5 pr-3 text-muted-foreground">{x.note ?? ""}</td>
                    <td className="py-1.5 text-right">
                      <button onClick={() => voidFlow(x)} disabled={busy} className="text-xs text-muted-foreground underline hover:text-foreground">ยกเลิก</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
