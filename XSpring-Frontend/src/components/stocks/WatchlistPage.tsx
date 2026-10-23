// @ts-nocheck
import { useState, useEffect, useMemo, useCallback, memo } from "react";

const MAX = 20;
const SEL_KEY = "jatso_watchlist_selected";

const ERR = {
  rate_limited: "โควต้าข้อมูลเต็มชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่",
  provider_error: "แหล่งข้อมูลขัดข้อง ลองใหม่อีกครั้ง",
  symbol_not_found: "ไม่พบหุ้นตัวนี้",
  invalid_symbol: "สัญลักษณ์หุ้นไม่ถูกต้อง",
  watchlist_full: `Watchlist เต็มแล้ว (สูงสุด ${MAX} ตัว)`,
  already_exists: "มีหุ้นตัวนี้ใน Watchlist แล้ว",
  login_required: "กรุณาเข้าสู่ระบบ",
  session_expired: "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่",
};
const msg = (e) => ERR[e] || "เกิดข้อผิดพลาด ลองใหม่อีกครั้ง";

const usd = (n, d = 2) => (n == null ? "–" : "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (n) => (n == null ? "–" : `${n > 0 ? "+" : ""}${Number(n).toFixed(2)}%`);
const big = (n) => {
  if (n == null) return "–";
  const a = Math.abs(n);
  return a >= 1e12 ? (n / 1e12).toFixed(2) + "T" : a >= 1e9 ? (n / 1e9).toFixed(2) + "B" : a >= 1e6 ? (n / 1e6).toFixed(1) + "M" : Number(n).toLocaleString("en-US");
};
const tone = (n) => (n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-muted-foreground");
const chip = (n) =>
  n == null ? "bg-muted text-muted-foreground" : n > 0 ? "bg-emerald-500/10 text-emerald-400" : n < 0 ? "bg-red-500/10 text-red-400" : "bg-muted text-muted-foreground";

/* ---------- ชิ้นส่วน UI ---------- */
const Btn = ({ kind, className = "", ...p }) => (
  <button
    {...p}
    className={`rounded-xl px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${
      kind === "ghost" ? "border border-border text-foreground hover:bg-accent" : "bg-emerald-500 text-black hover:bg-emerald-400"
    } ${className}`}
  />
);

/* ---------- กราฟ TradingView (ใช้ widget ฟรี ไม่กินโควต้า API) ---------- */
function useIsDark() {
  const read = () => {
    if (typeof document === "undefined") return false;
    const html = document.documentElement, body = document.body;
    if (html.classList.contains("dark") || body?.classList.contains("dark")) return true;
    const t = html.dataset.theme || body?.dataset.theme;
    return t ? t === "dark" : false;
  };
  const [dark, setDark] = useState(read);
  useEffect(() => {
    const update = () => setDark(read());
    const mo = new MutationObserver(update);
    const opts = { attributes: true, attributeFilter: ["class", "data-theme"] };
    mo.observe(document.documentElement, opts);
    if (document.body) mo.observe(document.body, opts);
    update();
    return () => mo.disconnect();
  }, []);
  return dark;
}

const ETF_EX = { SPY: "AMEX:SPY", QQQ: "NASDAQ:QQQ", DIA: "AMEX:DIA" };
const tvSymbol = (symbol, exchange = "") => {
  if (ETF_EX[symbol]) return ETF_EX[symbol];
  const e = (exchange || "").toUpperCase();
  if (e.includes("NASDAQ")) return `NASDAQ:${symbol}`;
  if (e.includes("NEW YORK") || e.includes("NYSE")) return `NYSE:${symbol}`;
  if (e.includes("AMEX") || e.includes("ARCA")) return `AMEX:${symbol}`;
  return symbol;
};

const TVChart = memo(function TVChart({ symbol, height }) {
  const dark = useIsDark();
  const ref = useCallback(
    (el) => {
      if (!el) return;
      el.innerHTML = "";
      const w = document.createElement("div");
      w.className = "tradingview-widget-container__widget";
      w.style.height = `${height}px`;
      w.style.width = "100%";
      el.appendChild(w);
      const s = document.createElement("script");
      s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
      s.async = true;
      s.innerHTML = JSON.stringify({
        autosize: false, width: "100%", height,
        symbol, interval: "D", timezone: "Asia/Bangkok",
        theme: dark ? "dark" : "light", style: "1", locale: "th_TH",
        backgroundColor: dark ? "rgba(10,10,10,1)" : "rgba(255,255,255,1)",
        allow_symbol_change: false, hide_side_toolbar: true,
        support_host: "https://www.tradingview.com",
      });
      el.appendChild(s);
    },
    [symbol, dark, height]
  );
  return <div ref={ref} className="tradingview-widget-container" style={{ height, width: "100%" }} />;
});

/* ---------- หน้า Watchlist ---------- */
export default function WatchlistPage({ api, authed, open, goTrade }) {
  const [items, setItems] = useState(null); // null = ยังไม่โหลด
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [sel, setSel] = useState(() => {
    try { return localStorage.getItem(SEL_KEY) || null; } catch { return null; }
  });
  const [sort, setSort] = useState("added");
  const [refreshing, setRefreshing] = useState(false);
  const [updated, setUpdated] = useState(null);
  const [pr, setPr] = useState(null);
  const [q, setQ] = useState("");
  const [sr, setSr] = useState([]);

  const load = useCallback(async () => {
    if (!authed) return;
    setRefreshing(true);
    try {
      const d = await api("/me/watchlist");
      setItems(Array.isArray(d) ? d : []);
      setError("");
      setUpdated(new Date());
    } catch (e) {
      setError(msg(e.message));
      setItems((x) => x ?? []);
    } finally {
      setRefreshing(false);
    }
  }, [api, authed]);

  // โหลดครั้งแรก + รีเฟรชราคาทุก 2 นาที (เฉพาะตอนเปิดแท็บอยู่ เพื่อไม่เปลือง quota)
  useEffect(() => {
    load();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 120000);
    return () => clearInterval(id);
  }, [load]);

  // ถ้าตัวที่เลือกไว้ไม่อยู่ในรายการ ให้เลือกตัวแรก
  useEffect(() => {
    if (!items) return;
    if (!items.length) return setSel(null);
    if (!sel || !items.some((r) => r.symbol === sel)) setSel(items[0].symbol);
  }, [items, sel]);

  useEffect(() => {
    try { if (sel) localStorage.setItem(SEL_KEY, sel); } catch {}
  }, [sel]);

  // ข้อมูลบริษัทของตัวที่เลือก (ชื่อ โลโก้ ตลาด)
  useEffect(() => {
    setPr(null);
    if (!sel) return;
    let off = false;
    api(`/${sel}/profile`).then((d) => !off && setPr(d)).catch(() => {});
    return () => { off = true; };
  }, [api, sel]);

  // ค้นหาหุ้นเพื่อเพิ่ม
  useEffect(() => {
    if (!q.trim()) return setSr([]);
    const id = setTimeout(
      () => api(`/search?q=${encodeURIComponent(q.trim())}`).then((d) => setSr(Array.isArray(d) ? d.slice(0, 6) : [])).catch(() => setSr([])),
      300
    );
    return () => clearTimeout(id);
  }, [q, api]);

  const count = items?.length ?? 0;
  const full = count >= MAX;

  const add = async (symbol) => {
    const s = (symbol || "").trim().toUpperCase();
    if (!s) return;
    setSr([]);
    setQ("");
    if (items?.some((r) => r.symbol === s)) { setSel(s); setNote("มีหุ้นตัวนี้ใน Watchlist แล้ว"); return; }
    if (full) { setNote(ERR.watchlist_full); return; }
    try {
      await api("/me/watchlist", { method: "POST", body: { symbol: s } });
      setNote("");
      setSel(s);
      await load();
    } catch (e) {
      setNote(msg(e.message));
    }
  };

  const remove = async (symbol) => {
    setItems((x) => x.filter((r) => r.symbol !== symbol));
    try {
      await api(`/me/watchlist/${symbol}`, { method: "DELETE" });
    } catch (e) {
      setNote(msg(e.message));
      load();
    }
  };

  const list = useMemo(() => {
    const a = [...(items || [])];
    if (sort === "chg") a.sort((x, y) => (y.changePercent ?? -1e9) - (x.changePercent ?? -1e9));
    if (sort === "az") a.sort((x, y) => x.symbol.localeCompare(y.symbol));
    return a;
  }, [items, sort]);

  const cur = items?.find((r) => r.symbol === sel);

  if (!authed)
    return (
      <section className="rounded-2xl border bg-card p-5">
        <p className="text-sm text-muted-foreground">เข้าสู่ระบบเพื่อใช้ Watchlist</p>
      </section>
    );

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      {/* ซ้าย: ข้อมูลหุ้นที่เลือก + กราฟ */}
      <div className="space-y-4">
        {sel && (
          <section className="rounded-2xl border bg-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                {pr?.logo ? (
                  <img src={pr.logo} alt="" className="h-12 w-12 rounded-xl bg-white p-1" />
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted text-sm font-semibold text-emerald-400">{sel.slice(0, 2)}</div>
                )}
                <div>
                  <div className="text-sm text-muted-foreground">
                    {sel}
                    {pr?.name ? ` · ${pr.name}` : ""}
                  </div>
                  <div className="flex items-end gap-3">
                    <span className="text-3xl font-bold text-foreground">{usd(cur?.price)}</span>
                    <span className={`mb-1 rounded px-1.5 py-0.5 text-xs font-medium ${chip(cur?.changePercent)}`}>{pct(cur?.changePercent)}</span>
                  </div>
                  {pr?.marketCap ? <div className="mt-0.5 text-xs text-muted-foreground">มูลค่าตลาด ${big(pr.marketCap * 1e6)}</div> : null}
                </div>
              </div>
              <div className="flex gap-2">
                <Btn kind="ghost" onClick={() => open(sel)}>ข้อมูลบริษัท</Btn>
                <Btn onClick={() => goTrade(sel)}>เทรด {sel}</Btn>
              </div>
            </div>
          </section>
        )}

        <section className="rounded-2xl border bg-card p-3">
          {sel ? (
            <TVChart symbol={tvSymbol(sel, pr?.exchange)} height={540} />
          ) : (
            <div className="flex h-[540px] items-center justify-center rounded-xl text-sm text-muted-foreground">
              {items === null ? "กำลังโหลด…" : "เพิ่มหุ้นใน Watchlist เพื่อดูกราฟ"}
            </div>
          )}
        </section>
      </div>

      {/* ขวา: รายการหุ้น */}
      <aside className="self-start rounded-2xl border bg-card p-4 lg:sticky lg:top-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">Watchlist</h3>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${full ? "bg-amber-500/10 text-amber-400" : "bg-muted text-muted-foreground"}`}>
            {count}/{MAX}
          </span>
        </div>
        <div className="mb-4 h-1 overflow-hidden rounded-full bg-muted">
          <div className={`h-full rounded-full ${full ? "bg-amber-400" : "bg-emerald-500"}`} style={{ width: `${(count / MAX) * 100}%` }} />
        </div>

        {/* เพิ่มหุ้น */}
        <div className="relative mb-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") add(sr[0]?.symbol || q);
            }}
            disabled={full}
            placeholder={full ? "Watchlist เต็มแล้ว ลบตัวเก่าก่อนเพิ่ม" : "ค้นหาแล้วเพิ่มหุ้น เช่น NVDA"}
            aria-label="เพิ่มหุ้นใน Watchlist"
            className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-emerald-500 disabled:opacity-60"
          />
          {sr.length > 0 && (
            <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-xl border bg-card shadow-xl">
              {sr.map((x) => (
                <li key={x.symbol}>
                  <button onClick={() => add(x.symbol)} className="flex w-full justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-accent">
                    <span className="font-semibold text-foreground">{x.symbol}</span>
                    <span className="truncate text-muted-foreground">{x.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {(note || error) && <p className="mb-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{note || error}</p>}

        {/* เรียงลำดับ + รีเฟรช */}
        <div className="mb-2 flex items-center justify-between text-xs">
          <div className="flex gap-1">
            {[["added", "ที่เพิ่ม"], ["chg", "% วันนี้"], ["az", "A–Z"]].map(([id, t]) => (
              <button
                key={id}
                onClick={() => setSort(id)}
                className={`rounded-full px-2.5 py-1 ${sort === id ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60"}`}
              >
                {t}
              </button>
            ))}
          </div>
          <button onClick={load} disabled={refreshing} className="text-muted-foreground hover:text-foreground disabled:opacity-50" title="รีเฟรชราคา">
            {refreshing ? "กำลังโหลด…" : updated ? `อัปเดต ${updated.toLocaleTimeString("th-TH")} ↻` : "รีเฟรช ↻"}
          </button>
        </div>

        {/* รายการ */}
        {items === null ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => <div key={i} className="h-12 animate-pulse rounded-xl bg-muted" />)}
          </div>
        ) : list.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            ยังไม่มีหุ้น ค้นหาด้านบนเพื่อเพิ่ม<br />หรือกด “+ Watchlist” ในหน้า Company
          </p>
        ) : (
          <ul className="max-h-[560px] space-y-1 overflow-y-auto pr-1">
            {list.map((r) => {
              const on = r.symbol === sel;
              return (
                <li key={r.symbol} className={`group flex items-center rounded-xl border-l-2 ${on ? "border-emerald-500 bg-accent" : "border-transparent hover:bg-accent/60"}`}>
                  <button onClick={() => setSel(r.symbol)} className="flex min-w-0 flex-1 items-center justify-between gap-3 px-3 py-2.5 text-left">
                    <div className="min-w-0">
                      <div className="font-semibold text-foreground">{r.symbol}</div>
                      {r.error && <div className="text-[11px] text-muted-foreground">ดึงราคาไม่ได้</div>}
                    </div>
                    <div className="text-right">
                      <div className="text-sm text-foreground">{r.error ? "–" : usd(r.price)}</div>
                      <div className={`text-xs ${tone(r.changePercent)}`}>{pct(r.changePercent)}</div>
                    </div>
                  </button>
                  <button
                    aria-label={`ลบ ${r.symbol}`}
                    title="ลบออกจาก Watchlist"
                    onClick={() => remove(r.symbol)}
                    className="px-3 py-2 text-muted-foreground opacity-60 hover:text-red-400 group-hover:opacity-100"
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </aside>
    </div>
  );
}
