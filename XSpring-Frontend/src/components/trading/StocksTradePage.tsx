import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import TradingViewChart from "./TradingViewChart"; // ปรับ path ให้ตรงกับโปรเจกต์

/* ---------- types ---------- */
type Side = "buy" | "sell";
type OType = "market" | "limit";
type Quote = {
  symbol: string; price: number; change: number; changePercent: number;
  open: number; high: number; low: number; prevClose: number; timestamp: number;
};
type Profile = { name?: string; logo?: string; exchange?: string; industry?: string; marketCap?: number };
type Account = { cash: number; marketValue: number; equity: number };
type Position = { symbol: string; qty: number; avgCost: number; price: number };
type Order = {
  id: number; symbol: string; side: Side; type: OType; qty: number;
  limitPrice: number | null; status: "open" | "filled" | "cancelled" | "rejected";
  fillPrice: number | null; createdAt: string; filledAt: string | null; reason?: string | null;
};

/* ---------- config ---------- */
const BOOK_BASE = "https://xspring-api.onrender.com"; // ใช้เมื่อไม่ได้ส่ง apiBase มา

/* ---------- helpers ---------- */
const ERR: Record<string, string> = {
  rate_limited: "ผู้ให้บริการราคาจำกัดการเรียกชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่",
  provider_error: "ดึงราคาไม่สำเร็จ ลองใหม่อีกครั้ง",
  symbol_not_found: "ไม่พบหุ้นตัวนี้",
  invalid_symbol: "สัญลักษณ์หุ้นไม่ถูกต้อง",
  unauthorized: "กรุณาเข้าสู่ระบบก่อนซื้อขาย",
};
const QUICK = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "META", "GOOGL", "SPY"];

const num = (n: number | null | undefined, d = 2) =>
  n == null || !isFinite(n) ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const usd = (n: number | null | undefined) =>
  n == null || !isFinite(n) ? "—" : `${n < 0 ? "-" : ""}$${num(Math.abs(n))}`;
const tone = (n: number) => (n > 0 ? "text-emerald-500" : n < 0 ? "text-rose-500" : "text-muted-foreground");
const sign = (n: number) => (n > 0 ? "+" : "");

function tvSymbol(sym: string, exchange?: string) {
  const e = (exchange || "").toUpperCase();
  if (e.includes("NASDAQ")) return `NASDAQ:${sym}`;
  if (e.includes("ARCA") || e.includes("AMERICAN")) return `AMEX:${sym}`;
  if (e.includes("NEW YORK") || e.includes("NYSE")) return `NYSE:${sym}`;
  return sym; // ETF/ไม่รู้ตลาด ให้ TradingView resolve เอง
}

const STATUS: Record<Order["status"], [string, string]> = {
  open: ["รอจับคู่", "bg-amber-500/15 text-amber-500"],
  filled: ["จับคู่แล้ว", "bg-emerald-500/15 text-emerald-500"],
  cancelled: ["ยกเลิก", "bg-muted text-muted-foreground"],
  rejected: ["ถูกปฏิเสธ", "bg-rose-500/15 text-rose-500"],
};

/* ---------- page ---------- */
export default function StocksTradePage({
  getToken, apiBase = "",
}: { getToken?: () => Promise<string | null | undefined> | string | null | undefined; apiBase?: string }) {
  const authed = !!getToken;
  const tokenRef = useRef(getToken);
  tokenRef.current = getToken;

  /* API ราคา/ค้นหา/โปรไฟล์ (/api/stocks) */
  const api = useCallback(
    async <T,>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T | null> => {
      const t = await tokenRef.current?.();
      const r = await fetch(`${apiBase}/api/stocks${path}`, {
        method: opts.method || "GET",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
      if (r.status === 204) return null;
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new Error(r.status === 401 ? "unauthorized" : typeof j?.detail === "string" ? j.detail : "error");
      return j as T;
    },
    [apiBase],
  );

  /* API พอร์ต/ซื้อขาย (/api/stock-book) */
  const book = useCallback(
    async <T,>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> => {
      const t = await tokenRef.current?.();
      const r = await fetch(`${apiBase || BOOK_BASE}/api/stock-book${path}`, {
        method: opts.method || "GET",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${t ?? ""}` },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
      const j = await r.json().catch(() => null);
      if (!r.ok) throw new Error(typeof j?.detail === "string" ? j.detail : `HTTP ${r.status}`);
      return j as T;
    },
    [apiBase],
  );

  /* symbol + search */
  const [symbol, setSymbol] = useState(() => {
  try {
    const p = localStorage.getItem("trade_pending_symbol");
    if (p) {
      localStorage.removeItem("trade_pending_symbol");
      return p;
    }
  } catch {}
  return "AAPL";
});
  const [q, setQ] = useState("");
  const [results, setResults] = useState<{ symbol: string; name: string }[]>([]);
  useEffect(() => {
    if (!q.trim()) return setResults([]);
    const id = setTimeout(
      () => api<typeof results>(`/search?q=${encodeURIComponent(q.trim())}`)
        .then((d) => setResults(Array.isArray(d) ? d : [])).catch(() => setResults([])),
      350,
    );
    return () => clearTimeout(id);
  }, [q, api]);
  const pick = (s: string) => { setSymbol(s.toUpperCase()); setQ(""); setResults([]); };

  /* quote + profile */
  const [quote, setQuote] = useState<Quote | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [quoteErr, setQuoteErr] = useState("");
  useEffect(() => {
    let alive = true;
    setQuote(null); setProfile(null); setQuoteErr("");
    const loadQ = () =>
      api<Quote>(`/${symbol}/quote`)
        .then((x) => { if (alive && x) { setQuote(x); setQuoteErr(""); } })
        .catch((e) => alive && setQuoteErr(ERR[e.message] ?? "โหลดราคาไม่สำเร็จ"));
    loadQ();
    const id = setInterval(loadQ, 10000);
    api<Profile>(`/${symbol}/profile`).then((p) => alive && setProfile(p)).catch(() => {});
    return () => { alive = false; clearInterval(id); };
  }, [symbol, api]);

  const prev = useRef<number | null>(null);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    if (!quote) { prev.current = null; return; }
    const p = prev.current;
    prev.current = quote.price;
    if (p != null && p !== quote.price) {
      setFlash(quote.price > p ? "up" : "down");
      const t = setTimeout(() => setFlash(null), 700);
      return () => clearTimeout(t);
    }
  }, [quote?.price]); // eslint-disable-line react-hooks/exhaustive-deps

  /* account / positions / orders (จากระบบพอร์ต stock-book) */
  const [account, setAccount] = useState<Account | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [bookErr, setBookErr] = useState("");
  const refresh = useCallback(async () => {
    if (!authed) return;
    try {
      const [b, t] = await Promise.all([book<any>("/portfolio"), book<any[]>("/trades")]);
      setAccount({ cash: b.cash, marketValue: b.market_value, equity: b.equity });
      setPositions(
        (b.positions ?? []).map((p: any): Position => ({
          symbol: p.symbol, qty: p.qty, avgCost: p.avg_cost, price: p.last,
        })),
      );
      setOrders(
        (Array.isArray(t) ? t : []).map((x: any): Order => ({
          id: x.id, symbol: x.symbol, side: x.side, type: "market", qty: x.qty,
          limitPrice: null, status: "filled", fillPrice: x.price,
          createdAt: x.ts, filledAt: x.ts, reason: x.note,
        })),
      );
      setBookErr("");
    } catch (e: any) {
      setBookErr(e?.message ?? "โหลดพอร์ตไม่สำเร็จ");
    }
  }, [book, authed]);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 10000);
    return () => clearInterval(id);
  }, [refresh]);

  /* order ticket */
  const [side, setSide] = useState<Side>("buy");
  const [type, setType] = useState<OType>("market");
  const [qty, setQty] = useState("");
  const [limit, setLimit] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { setConfirming(false); }, [side, type, qty, limit, symbol]);
  useEffect(() => { setLimit(""); setQty(""); setNotice(null); }, [symbol]);

  const held = positions.find((p) => p.symbol === symbol);
  const cash = account?.cash ?? 0;
  const qtyN = Math.floor(Number(qty)) || 0;
  const limitN = Number(limit) || 0;
  const refPrice = type === "limit" ? limitN : quote?.price ?? 0;
  const est = qtyN * refPrice;
  const maxBuy = refPrice > 0 ? Math.floor(cash / refPrice) : 0;
  const maxSell = held?.qty ?? 0;
  const heldPnl = held && quote ? (quote.price - held.avgCost) * held.qty : 0;

  const problem = useMemo(() => {
    if (!authed) return "เข้าสู่ระบบเพื่อส่งคำสั่งซื้อขาย";
    if (!quote) return "รอราคาล่าสุด";
    if (qtyN <= 0) return "ใส่จำนวนหุ้นที่ต้องการ";
    if (type === "limit" && limitN <= 0) return "ใส่ราคา Limit";
    if (side === "buy" && est > cash) return "เงินสดไม่พอ";
    if (side === "sell" && qtyN > maxSell) return "จำนวนหุ้นที่ถือไม่พอขาย";
    return "";
  }, [authed, quote, qtyN, type, limitN, side, est, cash, maxSell]);

  const submit = async () => {
    if (problem) return;
    if (!confirming) { setConfirming(true); return; }
    setBusy(true); setNotice(null);
    try {
      const r = await book<{ price: number }>("/trade", {
        method: "POST",
        body: { symbol, side, qty: qtyN, price: type === "limit" ? limitN : null },
      });
      setNotice({
        ok: true,
        text: `${side === "buy" ? "ซื้อ" : "ขาย"} ${qtyN} ${symbol} @ ${usd(r.price)} สำเร็จ`,
      });
      setQty(""); setConfirming(false);
      await refresh();
    } catch (e: any) {
      setNotice({ ok: false, text: ERR[e.message] ?? e.message ?? "ส่งคำสั่งไม่สำเร็จ" });
      setConfirming(false);
    } finally { setBusy(false); }
  };

  /* bottom tabs */
  const [tab, setTab] = useState<"positions" | "history">("positions");

  const rangePct = quote && quote.high > quote.low
    ? Math.min(100, Math.max(0, ((quote.price - quote.low) / (quote.high - quote.low)) * 100)) : 50;
  const isBuy = side === "buy";

  return (
    <div className="mx-auto max-w-[1400px] space-y-4 text-foreground">
      {/* ===== Top bar: search + quick picks ===== */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full md:w-80">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="ค้นหาหุ้น เช่น AAPL, NVDA, Tesla"
            aria-label="ค้นหาหุ้น"
            className="h-10 w-full rounded-xl border border-border bg-card px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
          />
          {results.length > 0 && (
            <ul className="absolute z-20 mt-2 max-h-72 w-full overflow-auto rounded-xl border border-border bg-card shadow-xl">
              {results.map((x) => (
                <li key={x.symbol}>
                  <button onClick={() => pick(x.symbol)} className="flex w-full justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-accent">
                    <span className="font-semibold">{x.symbol}</span>
                    <span className="truncate text-muted-foreground">{x.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {QUICK.map((s) => (
            <button
              key={s}
              onClick={() => pick(s)}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                s === symbol ? "border-foreground bg-foreground text-background" : "border-border bg-card text-muted-foreground hover:text-foreground"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {bookErr && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-400">
          โหลดพอร์ตไม่ได้: {bookErr}
        </div>
      )}

      {/* ===== Symbol header ===== */}
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            {profile?.logo ? (
              <img src={profile.logo} alt="" className="h-12 w-12 rounded-full bg-white object-contain p-1" />
            ) : (
              <div className="grid h-12 w-12 place-items-center rounded-full bg-muted text-sm font-bold">{symbol.slice(0, 2)}</div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight">{symbol}</h1>
                {profile?.exchange && (
                  <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {profile.exchange.split(" ")[0]}
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground">{profile?.name ?? "กำลังโหลด…"}{profile?.industry ? ` • ${profile.industry}` : ""}</p>
            </div>
          </div>

          <div className="text-right">
            <div
              className={`text-4xl font-bold tabular-nums transition-colors duration-500 ${
                flash === "up" ? "text-emerald-400" : flash === "down" ? "text-rose-400" : ""
              }`}
            >
              {quote ? usd(quote.price) : "—"}
            </div>
            <div className={`text-sm font-medium tabular-nums ${tone(quote?.change ?? 0)}`}>
              {quote ? `${sign(quote.change)}${num(quote.change)} (${sign(quote.changePercent)}${num(quote.changePercent)}%)` : quoteErr || "กำลังโหลดราคา…"}
              <span className="ml-2 text-xs font-normal text-muted-foreground">USD</span>
            </div>
          </div>

          {/* day range */}
          <div className="w-full min-w-[260px] max-w-sm flex-1">
            <div className="mb-1 flex justify-between text-xs text-muted-foreground tabular-nums">
              <span>ต่ำสุดวันนี้ {usd(quote?.low)}</span>
              <span>สูงสุด {usd(quote?.high)}</span>
            </div>
            <div className="relative h-1.5 rounded-full bg-muted">
              <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-rose-500/70 to-emerald-500/70" style={{ width: `${rangePct}%` }} />
              <div className="absolute top-1/2 h-3.5 w-1 -translate-y-1/2 rounded bg-foreground" style={{ left: `calc(${rangePct}% - 2px)` }} />
            </div>
            <div className="mt-2 flex justify-between text-xs text-muted-foreground tabular-nums">
              <span>เปิด {usd(quote?.open)}</span>
              <span>ปิดก่อนหน้า {usd(quote?.prevClose)}</span>
            </div>
          </div>
        </div>
      </section>

      {/* ===== Chart + Order ticket ===== */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section className="h-[560px] overflow-hidden rounded-2xl border border-border bg-card">
          <TradingViewChart key={symbol + (profile?.exchange ?? "")} symbol={tvSymbol(symbol, profile?.exchange)} />
        </section>

        <aside className="rounded-2xl border border-border bg-card p-5">
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold">ส่งคำสั่ง</h2>
            <span className="text-xs text-muted-foreground">{symbol} • USD</span>
          </div>

          <div className="grid grid-cols-2 gap-1 rounded-xl bg-muted p-1">
            {(["buy", "sell"] as Side[]).map((s) => (
              <button
                key={s}
                onClick={() => setSide(s)}
                className={`rounded-lg py-2.5 text-sm font-semibold transition-colors ${
                  side === s ? (s === "buy" ? "bg-emerald-500 text-white" : "bg-rose-500 text-white") : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {s === "buy" ? "ซื้อ" : "ขาย"}
              </button>
            ))}
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            {(["market", "limit"] as OType[]).map((t) => (
              <button
                key={t}
                onClick={() => setType(t)}
                className={`rounded-lg border py-2 text-sm transition-colors ${
                  type === t ? "border-foreground font-semibold" : "border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                {t === "market" ? "Market" : "Limit"}
              </button>
            ))}
          </div>
          {type === "limit" && (
            <p className="mt-2 text-xs text-muted-foreground">ระบบจะซื้อขายที่ราคา Limit ที่ระบุทันที ไม่รอให้ราคาตลาดมาถึง</p>
          )}

          <dl className="mt-4 space-y-1.5 text-sm">
            <Row k="เงินสดคงเหลือ" v={usd(cash)} />
            <Row k={`${symbol} ที่ถืออยู่`} v={held ? `${num(held.qty, 0)} หุ้น` : "0 หุ้น"} />
            {held && (
              <>
                <Row k="ต้นทุนเฉลี่ย" v={usd(held.avgCost)} />
                <Row k="กำไร/ขาดทุนที่ยังไม่รับรู้" v={`${sign(heldPnl)}${usd(heldPnl)}`} cls={tone(heldPnl)} />
              </>
            )}
          </dl>

          {type === "limit" && (
            <Field label="ราคา Limit (USD)">
              <input
                inputMode="decimal" value={limit} placeholder={quote ? num(quote.price) : "0.00"}
                onChange={(e) => setLimit(e.target.value.replace(/[^0-9.]/g, ""))}
                className="h-11 w-full rounded-xl border border-border bg-background px-3 text-right text-base tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </Field>
          )}

          <Field label="จำนวนหุ้น">
            <input
              inputMode="numeric" value={qty} placeholder="0"
              onChange={(e) => setQty(e.target.value.replace(/[^0-9]/g, ""))}
              className="h-11 w-full rounded-xl border border-border bg-background px-3 text-right text-base tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <div className="mt-2 grid grid-cols-4 gap-1.5">
              {[0.25, 0.5, 0.75, 1].map((p) => (
                <button
                  key={p}
                  onClick={() => setQty(String(Math.floor((isBuy ? maxBuy : maxSell) * p)))}
                  className="rounded-md border border-border py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  {p * 100}%
                </button>
              ))}
            </div>
          </Field>

          <div className="mt-4 flex items-center justify-between rounded-xl bg-muted px-3 py-3 text-sm">
            <span className="text-muted-foreground">มูลค่าคำสั่งโดยประมาณ</span>
            <span className="text-lg font-semibold tabular-nums">{usd(est)}</span>
          </div>

          <button
            onClick={submit}
            disabled={!!problem || busy}
            className={`mt-4 h-12 w-full rounded-xl text-sm font-bold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40 ${
              isBuy ? "bg-emerald-500 hover:bg-emerald-600" : "bg-rose-500 hover:bg-rose-600"
            } ${confirming ? "ring-2 ring-offset-2 ring-offset-card " + (isBuy ? "ring-emerald-400" : "ring-rose-400") : ""}`}
          >
            {busy ? "กำลังส่งคำสั่ง…" : confirming
              ? `ยืนยัน${isBuy ? "ซื้อ" : "ขาย"} ${num(qtyN, 0)} ${symbol} • ${type === "limit" ? `Limit ${usd(limitN)}` : "Market"}`
              : `ตรวจสอบคำสั่ง${isBuy ? "ซื้อ" : "ขาย"} ${symbol}`}
          </button>
          {problem && <p className="mt-2 text-center text-xs text-muted-foreground">{problem}</p>}
          {notice && (
            <p role="status" className={`mt-3 rounded-lg px-3 py-2 text-sm ${notice.ok ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"}`}>
              {notice.text}
            </p>
          )}
        </aside>
      </div>

      {/* ===== Account strip ===== */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="มูลค่าพอร์ตรวม" value={usd(account?.equity)} />
        <Stat label="เงินสด" value={usd(account?.cash)} />
        <Stat label="มูลค่าหุ้นที่ถือ" value={usd(account?.marketValue)} />
        <Stat label="จำนวนรายการซื้อขาย" value={String(orders.length)} />
      </section>

      {/* ===== Positions / History ===== */}
      <section className="rounded-2xl border border-border bg-card">
        <div className="flex gap-1 border-b border-border px-3 pt-3">
          {([
            ["positions", `หุ้นที่ถือ (${positions.length})`],
            ["history", "ประวัติการซื้อขาย"],
          ] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
                tab === k ? "border-foreground font-semibold" : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="overflow-x-auto">
          {!authed ? (
            <Empty text="เข้าสู่ระบบเพื่อดูพอร์ตและคำสั่งของคุณ" />
          ) : tab === "positions" ? (
            positions.length === 0 ? <Empty text="ยังไม่มีหุ้นในพอร์ต เลือกหุ้นด้านบนแล้วส่งคำสั่งซื้อแรกได้เลย" /> : (
              <Table head={["หุ้น", "จำนวน", "ต้นทุนเฉลี่ย", "ราคาล่าสุด", "มูลค่า", "กำไร/ขาดทุน", ""]}>
                {positions.map((p) => {
                  const pnl = (p.price - p.avgCost) * p.qty;
                  const pct = p.avgCost > 0 ? ((p.price - p.avgCost) / p.avgCost) * 100 : 0;
                  return (
                    <tr key={p.symbol} className="border-t border-border">
                      <td className="px-4 py-3 font-semibold">{p.symbol}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{num(p.qty, 0)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{usd(p.avgCost)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{usd(p.price)}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{usd(p.price * p.qty)}</td>
                      <td className={`px-4 py-3 text-right tabular-nums ${tone(pnl)}`}>{sign(pnl)}{usd(pnl)} ({sign(pct)}{num(pct)}%)</td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => { pick(p.symbol); setSide("sell"); }} className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-accent">ขาย</button>
                      </td>
                    </tr>
                  );
                })}
              </Table>
            )
          ) : orders.length === 0 ? <Empty text="ยังไม่มีประวัติการซื้อขาย" /> : (
            <Table head={["เวลา", "หุ้น", "ฝั่ง", "ประเภท", "จำนวน", "ราคาจับคู่", "สถานะ"]}>
              {orders.map((o) => <OrderRow key={o.id} o={o} />)}
            </Table>
          )}
        </div>
      </section>
    </div>
  );
}

/* ---------- small pieces ---------- */
function Row({ k, v, cls = "" }: { k: string; v: string; cls?: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={`font-medium tabular-nums ${cls}`}>{v}</dd>
    </div>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="mt-4 block">
      <span className="mb-1.5 block text-sm text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}
function Empty({ text }: { text: string }) {
  return <p className="px-4 py-10 text-center text-sm text-muted-foreground">{text}</p>;
}
function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <table className="w-full min-w-[720px] text-sm">
      <thead>
        <tr className="text-xs text-muted-foreground">
          {head.map((h, i) => <th key={i} className={`px-4 py-2.5 font-medium ${i < 2 ? "text-left" : "text-right"}`}>{h}</th>)}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}
function OrderRow({ o }: { o: Order }) {
  const [label, cls] = STATUS[o.status];
  return (
    <tr className="border-t border-border">
      <td className="px-4 py-3 text-xs text-muted-foreground tabular-nums">
        {new Date(o.createdAt).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" })}
      </td>
      <td className="px-4 py-3 font-semibold">{o.symbol}</td>
      <td className={`px-4 py-3 text-right font-medium ${o.side === "buy" ? "text-emerald-500" : "text-rose-500"}`}>{o.side === "buy" ? "ซื้อ" : "ขาย"}</td>
      <td className="px-4 py-3 text-right">{o.type === "market" ? "Market" : "Limit"}</td>
      <td className="px-4 py-3 text-right tabular-nums">{num(o.qty, 0)}</td>
      <td className="px-4 py-3 text-right tabular-nums">{usd(o.fillPrice ?? o.limitPrice)}</td>
      <td className="px-4 py-3 text-right">
        <span title={o.reason ?? ""} className={`rounded-md px-2 py-0.5 text-xs ${cls}`}>{label}</span>
      </td>
    </tr>
  );
}
