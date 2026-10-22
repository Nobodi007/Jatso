import { useCallback, useEffect, useState } from "react";

const API = "https://xspring-api.onrender.com/api/stock-book";

type Pos = {
  symbol: string; qty: number; avg_cost: number; last: number;
  market_value: number; unrealized_pnl: number; unrealized_pct: number;
};
type Book = {
  initial_cash: number; cash: number; market_value: number;
  equity: number; pnl: number; pnl_pct: number; positions: Pos[];
};
type Trade = {
  id: number; symbol: string; side: "buy" | "sell"; qty: number; price: number;
  fee: number; realized_pnl: number | null; note: string | null; ts: string;
};

const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const tone = (n: number) => (n >= 0 ? "text-emerald-400" : "text-red-400");

export default function StockBook({
  getToken,
  view,
}: {
  getToken: () => Promise<string | null> | string | null;
  view: "portfolio" | "orders" | "positions";
}) {
  const [book, setBook] = useState<Book | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ symbol: "", side: "buy", qty: "", price: "", fee: "", note: "" });

  const call = useCallback(
    async (path: string, init?: RequestInit) => {
      const token = await getToken();
      const r = await fetch(`${API}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "error");
      return j;
    },
    [getToken],
  );

  const load = useCallback(async () => {
    try {
      setErr("");
      const [b, t] = await Promise.all([call("/portfolio"), call("/trades")]);
      setBook(b);
      setTrades(t);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "โหลดไม่สำเร็จ");
    }
  }, [call]);

  useEffect(() => { void load(); }, [load]);

  const submit = async () => {
    setBusy(true);
    try {
      setErr("");
      await call("/trade", {
        method: "POST",
        body: JSON.stringify({
          symbol: f.symbol,
          side: f.side,
          qty: Number(f.qty),
          price: f.price ? Number(f.price) : null,
          fee: f.fee ? Number(f.fee) : 0,
          note: f.note || null,
        }),
      });
      setF({ ...f, qty: "", price: "", fee: "", note: "" });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "ส่งคำสั่งไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  };

  const inp = "rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-sm outline-none";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold">
          {view === "portfolio" ? "พอร์ตหุ้นของฉัน" : view === "orders" ? "ประวัติการซื้อขาย" : "Positions หุ้น"}
        </h1>
        <p className="text-sm opacity-60">พอร์ตหุ้นสหรัฐ แยกจากคริปโตทั้งหมด</p>
      </div>

      {err && <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm">{err}</div>}

      {book && view === "portfolio" && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            ["Equity", money(book.equity), ""],
            ["เงินสด", money(book.cash), ""],
            ["มูลค่าหุ้น", money(book.market_value), ""],
            ["กำไร/ขาดทุนรวม", `${money(book.pnl)} (${book.pnl_pct.toFixed(2)}%)`, tone(book.pnl)],
          ].map(([k, v, c]) => (
            <div key={k} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="text-xs opacity-60">{k}</div>
              <div className={`mt-1 text-lg font-semibold ${c}`}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {view === "portfolio" && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-7">
            <input className={inp} placeholder="Symbol เช่น AAPL" value={f.symbol}
              onChange={(e) => setF({ ...f, symbol: e.target.value })} />
            <select className={inp} value={f.side} onChange={(e) => setF({ ...f, side: e.target.value })}>
              <option value="buy">ซื้อ</option>
              <option value="sell">ขาย</option>
            </select>
            <input className={inp} placeholder="จำนวน" value={f.qty}
              onChange={(e) => setF({ ...f, qty: e.target.value })} />
            <input className={inp} placeholder="ราคา (ว่าง = ราคาตลาด)" value={f.price}
              onChange={(e) => setF({ ...f, price: e.target.value })} />
            <input className={inp} placeholder="ค่าธรรมเนียม" value={f.fee}
              onChange={(e) => setF({ ...f, fee: e.target.value })} />
            <input className={inp} placeholder="โน้ต" value={f.note}
              onChange={(e) => setF({ ...f, note: e.target.value })} />
            <button disabled={busy || !f.symbol || !f.qty} onClick={() => void submit()}
              className="rounded-xl bg-white px-3 py-2 text-sm font-semibold text-black disabled:opacity-40">
              บันทึก
            </button>
          </div>
        </div>
      )}

      {book && (view === "portfolio" || view === "positions") && (
        <div className="overflow-x-auto rounded-2xl border border-white/10 bg-white/5">
          <table className="w-full text-sm">
            <thead className="text-left text-xs opacity-60">
              <tr>
                {["Symbol", "จำนวน", "ต้นทุนเฉลี่ย", "ราคาล่าสุด", "มูลค่า", "P/L", "%"].map((h) => (
                  <th key={h} className="p-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {book.positions.length === 0 && (
                <tr><td colSpan={7} className="p-4 opacity-60">ยังไม่มีหุ้นในพอร์ต</td></tr>
              )}
              {book.positions.map((p) => (
                <tr key={p.symbol} className="border-t border-white/5">
                  <td className="p-3 font-semibold">{p.symbol}</td>
                  <td className="p-3">{p.qty}</td>
                  <td className="p-3">{money(p.avg_cost)}</td>
                  <td className="p-3">{money(p.last)}</td>
                  <td className="p-3">{money(p.market_value)}</td>
                  <td className={`p-3 ${tone(p.unrealized_pnl)}`}>{money(p.unrealized_pnl)}</td>
                  <td className={`p-3 ${tone(p.unrealized_pct)}`}>{p.unrealized_pct.toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {view === "orders" && (
        <div className="overflow-x-auto rounded-2xl border border-white/10 bg-white/5">
          <table className="w-full text-sm">
            <thead className="text-left text-xs opacity-60">
              <tr>
                {["เวลา", "Symbol", "ฝั่ง", "จำนวน", "ราคา", "ค่าธรรมเนียม", "กำไรที่รับรู้", "โน้ต"].map((h) => (
                  <th key={h} className="p-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 && (
                <tr><td colSpan={8} className="p-4 opacity-60">ยังไม่มีรายการ</td></tr>
              )}
              {trades.map((t) => (
                <tr key={t.id} className="border-t border-white/5">
                  <td className="p-3">{new Date(t.ts).toLocaleString()}</td>
                  <td className="p-3 font-semibold">{t.symbol}</td>
                  <td className={`p-3 ${t.side === "buy" ? "text-emerald-400" : "text-red-400"}`}>
                    {t.side === "buy" ? "ซื้อ" : "ขาย"}
                  </td>
                  <td className="p-3">{t.qty}</td>
                  <td className="p-3">{money(t.price)}</td>
                  <td className="p-3">{money(t.fee)}</td>
                  <td className={`p-3 ${t.realized_pnl == null ? "" : tone(t.realized_pnl)}`}>
                    {t.realized_pnl == null ? "-" : money(t.realized_pnl)}
                  </td>
                  <td className="p-3 opacity-70">{t.note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
