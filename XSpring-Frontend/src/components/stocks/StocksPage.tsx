// @ts-nocheck
import { useState, useEffect, useMemo, useCallback, useRef, memo } from "react";

const ERR = {
  rate_limited: "โควต้าข้อมูลเต็มชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่",
  provider_error: "แหล่งข้อมูลขัดข้อง ลองใหม่อีกครั้ง",
  symbol_not_found: "ไม่พบหุ้นตัวนี้",
  invalid_symbol: "สัญลักษณ์หุ้นไม่ถูกต้อง",
  not_in_sec: "ไม่มีงบการเงินของหุ้นตัวนี้ใน SEC (อาจเป็นหุ้นต่างชาติ)",
  login_required: "กรุณาเข้าสู่ระบบ",
  session_expired: "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่",
  watchlist_full: "Watchlist เต็มแล้ว (สูงสุด 30 ตัว)",
  alerts_full: "แจ้งเตือนเต็มแล้ว (สูงสุด 20 รายการ)",
  sell_exceeds_holdings: "จำนวนที่ขายมากกว่าที่ถืออยู่",
  already_exists: "มีรายการนี้อยู่แล้ว",
  compare_2_to_4: "เลือกหุ้น 2–4 ตัว คั่นด้วยเครื่องหมายจุลภาค",
  invalid_range: "ช่วงวันที่ไม่ถูกต้อง (ไม่เกิน 31 วัน)",
  telegram_failed: "ส่งข้อความ Telegram ไม่สำเร็จ กด /start กับบอทก่อน",
  no_backend: "เชื่อมต่อ API หุ้นไม่ได้ ตรวจ apiBase และการ deploy backend",
};
const msg = (e) => ERR[e] || "เกิดข้อผิดพลาด ลองใหม่อีกครั้ง";

const usd = (n, d = 2) => (n == null ? "–" : "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const num = (n, d = 2) => (n == null ? "–" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d }));
const pct = (n) => (n == null ? "–" : `${n > 0 ? "+" : ""}${Number(n).toFixed(2)}%`);
const big = (n) => {
  if (n == null) return "–";
  const a = Math.abs(n);
  return a >= 1e12 ? (n / 1e12).toFixed(2) + "T" : a >= 1e9 ? (n / 1e9).toFixed(2) + "B" : a >= 1e6 ? (n / 1e6).toFixed(1) + "M" : num(n, 0);
};
const tone = (n) => (n > 0 ? "text-emerald-400" : n < 0 ? "text-red-400" : "text-zinc-400");
const iso = (d) => d.toISOString().slice(0, 10);

function useGet(api, path) {
  const [s, setS] = useState({ data: null, error: null, loading: !!path });
  useEffect(() => {
    if (!path) return setS({ data: null, error: null, loading: false });
    let off = false;
    setS((x) => ({ ...x, loading: true, error: null }));
    api(path)
      .then((d) => !off && setS({ data: d, error: null, loading: false }))
      .catch((e) => !off && setS({ data: null, error: e.message, loading: false }));
    return () => { off = true; };
  }, [api, path]);
  return s;
}

const Card = ({ title, right, children, className = "" }) => (
  <section className={`rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 ${className}`}>
    {(title || right) && (
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-white">{title}</h3>
        {right}
      </div>
    )}
    {children}
  </section>
);
const Status = ({ s, empty }) =>
  s.loading ? <p className="py-6 text-sm text-zinc-500">กำลังโหลด…</p>
  : s.error ? <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{msg(s.error)}</p>
  : empty ? <p className="py-6 text-sm text-zinc-500">{empty}</p> : null;
const Pill = ({ on, children, ...p }) => (
  <button {...p} className={`rounded-full px-4 py-1.5 text-sm transition ${on ? "bg-emerald-500 font-medium text-black" : "border border-zinc-800 bg-zinc-900 text-zinc-300 hover:bg-zinc-800"}`}>{children}</button>
);
const Btn = ({ kind, ...p }) => (
  <button {...p} className={`rounded-xl px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${kind === "ghost" ? "border border-zinc-700 text-zinc-200 hover:bg-zinc-800" : "bg-emerald-500 text-black hover:bg-emerald-400"}`} />
);
const Input = (p) => <input {...p} className={`w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-emerald-500 ${p.className || ""}`} />;
const Stat = ({ label, value }) => (
  <div className="rounded-xl bg-zinc-950/60 p-3">
    <div className="text-xs text-zinc-500">{label}</div>
    <div className="mt-1 text-sm font-semibold text-white">{value}</div>
  </div>
);


const PAL = ["#10b981", "#34d399", "#059669", "#6ee7b7", "#047857", "#a7f3d0"];

/* การ์ดตัวเลขแบบ Tailgrids: ไอคอน ป้ายชื่อ ค่า และป้ายเปลี่ยนแปลง */
function StatCard({ icon, label, value, change, sub, onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 text-left hover:border-zinc-700">
      <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-800 text-sm font-semibold text-emerald-400">{icon}</div>
      <div className="text-sm text-zinc-400">{label}</div>
      <div className="mt-1 flex items-end justify-between gap-2">
        <div className="text-2xl font-bold text-white">{value}</div>
        {change != null && (
          <div className="text-right">
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${change >= 0 ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>{change >= 0 ? "↑" : "↓"} {pct(change)}</span>
            {sub && <div className="mt-1 text-[11px] text-zinc-500">{sub}</div>}
          </div>
        )}
      </div>
    </Tag>
  );
}

function Donut({ items, center }) {
  const total = items.reduce((a, x) => a + x.value, 0) || 1, r = 52, C = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="flex flex-wrap items-center justify-center gap-6">
      <svg viewBox="0 0 140 140" className="h-40 w-40" role="img" aria-label="สัดส่วนพอร์ต">
        <g transform="rotate(-90 70 70)">
          {items.map((x, i) => {
            const len = (x.value / total) * C, el = <circle key={x.label} cx="70" cy="70" r={r} fill="none" stroke={PAL[i % PAL.length]} strokeWidth="18" strokeDasharray={`${Math.max(len - 2, 0)} ${C}`} strokeDashoffset={-acc} />;
            acc += len; return el;
          })}
        </g>
        <text x="70" y="66" textAnchor="middle" fontSize="9" fill="#a1a1aa">มูลค่ารวม</text>
        <text x="70" y="82" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">{center}</text>
      </svg>
      <ul className="space-y-1.5 text-sm">
        {items.map((x, i) => <li key={x.label} className="flex items-center gap-2 text-zinc-300"><span className="h-2.5 w-2.5 rounded-full" style={{ background: PAL[i % PAL.length] }} />{x.label}<span className="text-zinc-500">{((x.value / total) * 100).toFixed(1)}%</span></li>)}
      </ul>
    </div>
  );
}

function Bars({ rows, series }) {
  const [hi, setHi] = useState(null);
  const [on, setOn] = useState(false);
  useEffect(() => { const t = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(t); }, []);
  const W = 600, H = 200, max = Math.max(...rows.flatMap((r) => series.map((s) => r[s.k] || 0)), 1);
  const gw = W / rows.length, bw = Math.min(28, (gw - 16) / series.length);
  const sel = rows[hi ?? rows.length - 1];
  const margin = sel.revenue && sel.netIncome != null ? ((sel.netIncome / sel.revenue) * 100).toFixed(1) + "%" : "–";
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H + 22}`} className="w-full" role="img" aria-label="กราฟแท่งรายปี">
        {[0.25, 0.5, 0.75, 1].map((t) => <line key={t} x1="0" x2={W} y1={H - H * t} y2={H - H * t} stroke="#27272a" />)}
        {rows.map((r, i) => (
          <g key={r.year} opacity={hi == null || hi === i ? 1 : 0.35} style={{ transition: "opacity .2s" }}>
            {hi === i && <rect x={i * gw} y="0" width={gw} height={H + 22} fill="#fff" opacity="0.04" rx="6" />}
            {series.map((s, j) => {
              const h = (Math.max(r[s.k] || 0, 0) / max) * H;
              return <rect key={s.k} x={i * gw + gw / 2 - (bw * series.length) / 2 + j * bw} y={H - h} width={bw - 3} height={h} rx="3" fill={s.color}
                style={{ transformBox: "fill-box", transformOrigin: "bottom", transform: on ? "scaleY(1)" : "scaleY(0)", transition: `transform .6s ease ${i * 70}ms` }} />;
            })}
            <text x={i * gw + gw / 2} y={H + 16} textAnchor="middle" fontSize="11" fill={hi === i ? "#fff" : "#71717a"}>{r.year}</text>
            <rect x={i * gw} y="0" width={gw} height={H + 22} fill="transparent" style={{ cursor: "pointer" }}
              onMouseEnter={() => setHi(i)} onMouseLeave={() => setHi(null)} onClick={() => setHi(hi === i ? null : i)} />
          </g>
        ))}
      </svg>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl bg-zinc-950/60 px-3 py-2 text-sm">
        <span className="font-semibold text-white">ปี {sel.year}</span>
        {series.map((s) => <span key={s.k} className="flex items-center gap-1.5 text-zinc-300"><span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />{s.label} {big(sel[s.k])}</span>)}
        <span className="text-zinc-500">อัตรากำไรสุทธิ {margin}</span>
      </div>
    </div>
  );
}

function Sankey({ a }) {
  const [h, setH] = useState(null);
  const { revenue: rev, grossProfit: gp, operatingIncome: oi, netIncome: ni } = a;
  if ([rev, gp, oi, ni].some((v) => v == null) || rev <= 0 || gp > rev || oi > gp || ni > oi || ni < 0)
    return <p className="py-4 text-sm text-zinc-500">ข้อมูลปีนี้ไม่พอวาด Sankey (ต้องมีรายได้ กำไรขั้นต้น กำไรดำเนินงาน และกำไรสุทธิที่เป็นบวก)</p>;
  const N = [["รายได้", rev, 0], ["ต้นทุนขาย", rev - gp, 1, 1], ["กำไรขั้นต้น", gp, 1], ["ค่าใช้จ่ายดำเนินงาน", gp - oi, 2, 1], ["กำไรดำเนินงาน", oi, 2], ["ภาษี ดอกเบี้ย อื่นๆ", oi - ni, 3, 1], ["กำไรสุทธิ", ni, 3]];
  const L = [[0, 1], [0, 2], [2, 3], [2, 4], [4, 5], [4, 6]];
  const W = 720, H = 250, NW = 12, TOP = 20, GAP = 14, k = (H - TOP - GAP) / rev;
  const col = [0, 0, 0, 0], nodes = N.map(([n, v, c, bad]) => { const hh = Math.max(v * k, 2), y = TOP + col[c]; col[c] += hh + GAP; return { n, v, bad, h: hh, y, x: (c * (W - NW)) / 3, c, o: 0, i: 0 }; });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="แผนภาพ Sankey งบกำไรขาดทุน">
      {L.map(([s, t]) => {
        const a1 = nodes[s], b = nodes[t], th = Math.max(b.v * k, 1);
        if (b.v <= 0) return null;
        const y0 = a1.y + a1.o + th / 2, y1 = b.y + b.i + th / 2, x0 = a1.x + NW, x1 = b.x, xm = (x0 + x1) / 2;
        a1.o += th; b.i += th;
        const hot = h != null && (h === s || h === t);
        return <path key={`${s}-${t}`} d={`M${x0},${y0} C${xm},${y0} ${xm},${y1} ${x1},${y1}`} fill="none" stroke={b.bad ? "#f87171" : "#10b981"}
          strokeOpacity={h == null ? 0.28 : hot ? 0.6 : 0.07} strokeWidth={th} style={{ transition: "stroke-opacity .2s" }} />;
      })}
      {nodes.map((n, i) => (
        <g key={n.n} style={{ cursor: "pointer" }} onMouseEnter={() => setH(i)} onMouseLeave={() => setH(null)} onClick={() => setH(h === i ? null : i)}>
          <rect x={n.x - 6} y={n.y - 4} width={NW + 12} height={n.h + 8} fill="transparent" />
          <rect x={n.x} y={n.y} width={NW} height={n.h} rx="3" fill={n.bad ? "#f87171" : "#10b981"} opacity={h == null || h === i ? 1 : 0.4} />
          <text x={n.c === 3 ? n.x + NW : n.x} y={n.y - 6} textAnchor={n.c === 3 ? "end" : "start"} fontSize={h === i ? 12 : 11} fontWeight={h === i ? 700 : 400} fill={h === i ? "#fff" : "#d4d4d8"}>
            {n.n} {big(n.v)}{h === i ? ` (${((n.v / rev) * 100).toFixed(1)}% ของรายได้)` : ""}
          </text>
        </g>
      ))}
    </svg>
  );
}

/* ---------- กราฟเส้นแบบ SVG ไม่ใช้ไลบรารี ---------- */
function Line({ rows }) {
  if (!rows?.length) return null;
  const pts = rows.slice(-100);
  const c = pts.map((r) => r.close);
  const lo = Math.min(...c), hi = Math.max(...c), W = 600, H = 200;
  const x = (i) => (i / Math.max(pts.length - 1, 1)) * W;
  const y = (v) => H - 8 - ((v - lo) / (hi - lo || 1)) * (H - 16);
  const d = c.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const up = c[c.length - 1] >= c[0];
  const col = up ? "#34d399" : "#f87171";
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-52 w-full" preserveAspectRatio="none" role="img" aria-label="กราฟราคาปิดรายวัน">
        <path d={`${d} L${W},${H} L0,${H} Z`} fill={col} opacity="0.1" />
        <path d={d} fill="none" stroke={col} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-2 flex justify-between text-xs text-zinc-500">
        <span>{pts[0].time}</span><span>ต่ำสุด {usd(lo)} · สูงสุด {usd(hi)}</span><span>{pts[pts.length - 1].time}</span>
      </div>
    </div>
  );
}

/* ---------- กราฟ TradingView (widget ฟรี ไม่กินโควต้า API) ---------- */
const ETF_EX = { SPY: "AMEX:SPY", QQQ: "NASDAQ:QQQ", DIA: "AMEX:DIA" };
const tvSymbol = (symbol, exchange = "") => {
  if (ETF_EX[symbol]) return ETF_EX[symbol];
  const e = (exchange || "").toUpperCase();
  if (e.includes("NASDAQ")) return `NASDAQ:${symbol}`;
  if (e.includes("NEW YORK") || e.includes("NYSE")) return `NYSE:${symbol}`;
  if (e.includes("AMEX") || e.includes("ARCA")) return `AMEX:${symbol}`;
  return symbol;
};

const TVChart = memo(function TVChart({ symbol, height = 420 }) {
  const ref = useCallback((el) => {
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
      autosize: false, width: "100%", height,   // ← แก้บรรทัดนี้ (ส่ง height เข้าไป)
      symbol, interval: "D", timezone: "Asia/Bangkok",
      theme: "dark", style: "1", locale: "th_TH",
      backgroundColor: "rgba(10,10,10,1)", allow_symbol_change: false,
      hide_side_toolbar: true, support_host: "https://www.tradingview.com",
    });
    el.appendChild(s);
  }, [symbol]);
  return <div ref={ref} className="tradingview-widget-container" style={{ height, width: "100%" }} />;
});

/* ---------- 1) ภาพรวมตลาด ---------- */
function Market({ api, open }) {
  const ov = useGet(api, "/market/overview");
  const mv = useGet(api, "/market/movers");
  const [k, setK] = useState("gainers");
  const KEYS = { gainers: "ขึ้นแรง", losers: "ลงแรง", mostActive: "วอลุ่มสูง" };
  return (
    <div className="space-y-5">
      <Status s={ov} />
      <div className="grid gap-4 md:grid-cols-3">
        {ov.data?.map((q, n) => (
          <StatCard key={q.symbol} onClick={() => open(q.symbol)} icon={["500", "100", "30"][n]} label={`${q.name} · ${q.symbol}`} value={usd(q.price)} change={q.changePercent} sub="เทียบวานนี้" />
        ))}
      </div>
      <Card title="หุ้นเคลื่อนไหวเด่น" right={<div className="flex gap-2">{Object.entries(KEYS).map(([id, t]) => <Pill key={id} on={k === id} onClick={() => setK(id)}>{t}</Pill>)}</div>}>
        <Status s={mv} empty={!mv.loading && !mv.error && !mv.data?.[k]?.length && "ไม่มีข้อมูล"} />
        <div className="divide-y divide-zinc-800">
          {mv.data?.[k]?.map((r) => (
            <button key={r.symbol} onClick={() => open(r.symbol)} className="grid w-full grid-cols-4 items-center py-2.5 text-sm hover:bg-zinc-800/40">
              <span className="text-left font-semibold text-white">{r.symbol}</span>
              <span className="text-right text-zinc-300">{usd(r.price)}</span>
              <span className={`text-right ${tone(r.changePercent)}`}>{pct(r.changePercent)}</span>
              <span className="text-right text-zinc-500">{r.volume ? big(r.volume) : "–"}</span>
            </button>
          ))}
        </div>
        {mv.data?.updatedAt && <p className="mt-3 text-xs text-zinc-600">อัปเดตล่าสุด {mv.data.updatedAt}</p>}
      </Card>
    </div>
  );
}

/* ---------- ตารางงบการเงิน 3 งบ ---------- */
const FIN_LABELS = {
  revenue: "รายได้", costOfRevenue: "ต้นทุนขาย", grossProfit: "กำไรขั้นต้น",
  researchAndDevelopment: "R&D", sga: "SG&A", operatingExpenses: "ค่าใช้จ่ายดำเนินงานรวม",
  operatingIncome: "กำไรจากการดำเนินงาน", interestExpense: "ดอกเบี้ยจ่าย",
  incomeBeforeTax: "กำไรก่อนภาษี", incomeTax: "ภาษี", netIncome: "กำไรสุทธิ",
  eps: "EPS (diluted)", dilutedShares: "จำนวนหุ้น (diluted)",
  cash: "เงินสด", shortTermInvestments: "เงินลงทุนระยะสั้น", receivables: "ลูกหนี้",
  inventory: "สินค้าคงคลัง", currentAssets: "สินทรัพย์หมุนเวียน", ppe: "ที่ดิน อาคาร อุปกรณ์",
  goodwill: "Goodwill", totalAssets: "สินทรัพย์รวม", currentLiabilities: "หนี้สินหมุนเวียน",
  shortTermDebt: "หนี้ระยะสั้น", longTermDebt: "หนี้ระยะยาว", totalDebt: "หนี้รวม",
  totalLiabilities: "หนี้สินรวม", equity: "ส่วนของผู้ถือหุ้น", netDebt: "หนี้สุทธิ",
  depreciation: "ค่าเสื่อมราคา", sbc: "ค่าตอบแทนเป็นหุ้น (SBC)",
  operatingCashFlow: "กระแสเงินสดดำเนินงาน", capex: "CapEx", freeCashFlow: "กระแสเงินสดอิสระ",
  investingCashFlow: "กระแสเงินสดลงทุน", financingCashFlow: "กระแสเงินสดจัดหาเงิน",
  buybacks: "ซื้อหุ้นคืน", dividendsPaid: "จ่ายปันผล",
  grossMargin: "Gross margin", operatingMargin: "Operating margin", netMargin: "Net margin", fcfMargin: "FCF margin",
};
const FIN_TABS = { income: "งบกำไรขาดทุน", balance: "งบดุล", cashflow: "งบกระแสเงินสด" };
const FIN_MARGINS = { income: ["grossMargin", "operatingMargin", "netMargin"], balance: [], cashflow: ["fcfMargin"] };
const MARGIN_KEYS = new Set(["grossMargin", "operatingMargin", "netMargin", "fcfMargin"]);

function Statements({ s }) {
  const [tab, setTab] = useState("income");
  const rows = s.data?.annual;
  if (!rows?.length) return null;
  const keys = [...(s.data.statements?.[tab] || []), ...FIN_MARGINS[tab]];
  const cell = (k, v) => (v == null ? "–" : MARGIN_KEYS.has(k) ? v.toFixed(1) + "%" : k === "eps" ? num(v) : big(v));
  return (
    <Card title="งบการเงินรายปี (USD)" right={<div className="flex gap-2">{Object.entries(FIN_TABS).map(([id, t]) => <Pill key={id} on={tab === id} onClick={() => setTab(id)}>{t}</Pill>)}</div>}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-zinc-500">
              <th className="sticky left-0 bg-zinc-900 py-2 pr-4 text-left font-normal">รายการ</th>
              {[...rows].reverse().map((r) => <th key={r.fiscalYearEnd} className="px-3 py-2 text-right font-normal">{r.year}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {keys.map((k) => (
              <tr key={k} className="text-zinc-200">
                <td className="sticky left-0 whitespace-nowrap bg-zinc-900 py-2 pr-4 text-zinc-400">{FIN_LABELS[k] || k}</td>
                {[...rows].reverse().map((r) => {
                  const v = r[k], g = r.yoy?.[k];
                  return (
                    <td key={r.fiscalYearEnd} className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                      <div className={v < 0 ? "text-red-400" : ""}>{cell(k, v)}</div>
                      {g != null && !MARGIN_KEYS.has(k) && <div className={`text-[11px] ${tone(g)}`}>{pct(g)}</div>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-zinc-600">ที่มา SEC EDGAR · ตัวเลข "–" คือบริษัทนี้ไม่ได้รายงานรายการนั้นด้วย tag มาตรฐาน · % ใต้ตัวเลขคือเปลี่ยนจากปีก่อน</p>
    </Card>
  );
}

/* ---------- 2) หุ้นรายตัว ---------- */
const MET = [["P/E", "pe"], ["P/B", "pb"], ["P/S", "ps"], ["ROE %", "roe"], ["ROA %", "roa"], ["Gross margin %", "grossMargin"],
  ["Net margin %", "netMargin"], ["D/E", "debtToEquity"], ["Current ratio", "currentRatio"], ["ปันผล %", "dividendYield"],
  ["EPS", "eps"], ["รายได้โต %", "revenueGrowth"], ["Beta", "beta"], ["สูงสุด 52 สัปดาห์", "high52w"], ["ต่ำสุด 52 สัปดาห์", "low52w"]];

function Detail({ api, symbol, authed, onWatch }) {
  const q = useGet(api, `/${symbol}/quote`);
  const pr = useGet(api, `/${symbol}/profile`);
  const m = useGet(api, `/${symbol}/metrics`);
  const f = useGet(api, `/${symbol}/financials?years=15`);
  const n = useGet(api, `/${symbol}/news`);
  const [note, setNote] = useState("");
  const add = async () => {
    try { await api("/me/watchlist", { method: "POST", body: { symbol } }); setNote("เพิ่มใน Watchlist แล้ว"); onWatch?.(); }
    catch (e) { setNote(msg(e.message)); }
  };
  const d = q.data;
  return (
    <div className="space-y-5">
      <Card className="min-h-[210px]">
  {q.error && <Status s={q} />}

  {q.loading && !d && (
    <div className="animate-pulse space-y-4">
      <div className="flex items-center gap-4">
        <div className="h-12 w-12 rounded-xl bg-zinc-800" />
        <div className="space-y-2">
          <div className="h-4 w-48 rounded bg-zinc-800" />
          <div className="h-8 w-32 rounded bg-zinc-800" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-[58px] rounded-xl bg-zinc-800/60" />
        ))}
      </div>
    </div>
  )}

  {d && (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {pr.data?.logo && (
            <img
              src={pr.data.logo}
              alt=""
              className="h-12 w-12 rounded-xl bg-white p-1"
            />
          )}
          <div>
            <div className="text-sm text-zinc-400">
              {pr.data?.name || symbol} · {pr.data?.exchange}
            </div>
            <div className="text-3xl font-bold text-white">
              {usd(d.price)}
            </div>
            <div className={`text-sm ${tone(d.change)}`}>
              {usd(d.change)} ({pct(d.changePercent)})
            </div>
          </div>
        </div>
        <div className="text-right">
          <Btn kind="ghost" onClick={add} disabled={!authed}>
            + Watchlist
          </Btn>
          {note && (
            <p className="mt-2 text-xs text-zinc-400">{note}</p>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="เปิด" value={usd(d.open)} />
        <Stat label="สูงสุดวันนี้" value={usd(d.high)} />
        <Stat label="ต่ำสุดวันนี้" value={usd(d.low)} />
        <Stat label="ปิดก่อนหน้า" value={usd(d.prevClose)} />
        <Stat
          label="มูลค่าตลาด"
          value={
            pr.data?.marketCap
              ? "$" + big(pr.data.marketCap * 1e6)
              : "–"
          }
        />
      </div>
    </>
  )}
  </Card>

<Card title="กราฟราคา">
  {pr.loading && !pr.data ? (
    <div className="h-[420px] animate-pulse rounded-xl bg-zinc-800/40" />
  ) : (
    <TVChart
      symbol={tvSymbol(symbol, pr.data?.exchange)}
      height={420}
    />
  )}
</Card>
      {f.data?.annual?.length > 0 && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title="รายได้และกำไรสุทธิรายปี"><Bars rows={f.data.annual.slice(-8)} series={[{ k: "revenue", label: "รายได้", color: "#10b981" }, { k: "netIncome", label: "กำไรสุทธิ", color: "#a7f3d0" }]} /></Card>
          <Card title={`รายได้ไหลไปไหน ปี ${f.data.annual[f.data.annual.length - 1].year}`}><Sankey a={f.data.annual[f.data.annual.length - 1]} /></Card>
        </div>
      )}
      <Card title="อัตราส่วนการเงิน">
        <Status s={m} />
        {m.data && <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{MET.map(([l, k]) => <Stat key={k} label={l} value={num(m.data[k])} />)}</div>}
      </Card>
      <Status s={f} empty={!f.loading && !f.error && !f.data?.annual?.length && (f.data?.taxonomy === "non-us-gaap" ? "หุ้นตัวนี้ใช้มาตรฐานบัญชี IFRS ยังไม่รองรับ" : "ไม่มีข้อมูล")} />
      <Statements s={f} />
      <Card title="ข่าวล่าสุด (7 วัน)">
        <Status s={n} empty={!n.loading && !n.error && !n.data?.length && "ไม่มีข่าวในช่วงนี้"} />
        <div className="divide-y divide-zinc-800">
          {n.data?.slice(0, 8).map((x) => (
            <a key={x.id} href={x.url} target="_blank" rel="noreferrer" className="block py-3 hover:bg-zinc-800/40">
              <div className="text-sm font-medium text-white">{x.headline}</div>
              <div className="mt-1 text-xs text-zinc-500">{x.source} · {new Date(x.datetime * 1000).toLocaleString("th-TH")}</div>
            </a>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ---------- 3) พอร์ตของฉัน: Watchlist / Portfolio / แจ้งเตือน ---------- */
function Mine({ api, open, authed }) {
  const [t, setT] = useState(0);
  const re = () => setT((x) => x + 1);
  const wl = useGet(api, authed ? `/me/watchlist?_=${t}` : null);
  const pf = useGet(api, authed ? `/me/portfolio?_=${t}` : null);
  const al = useGet(api, authed ? `/me/alerts?_=${t}` : null);
  const [err, setErr] = useState("");
  const run = async (fn) => { setErr(""); try { await fn(); re(); } catch (e) { setErr(msg(e.message)); } };
  const [w, setW] = useState("");
  const [tx, setTx] = useState({ symbol: "", side: "BUY", quantity: "", price: "", fee: "0" });
  const [a, setA] = useState({ symbol: "", condition: "above", target: "" });
  if (!authed) return <Card><p className="text-sm text-zinc-400">เข้าสู่ระบบเพื่อใช้ Watchlist พอร์ต และแจ้งเตือนราคา</p></Card>;
  const S = pf.data?.summary;
  return (
    <div className="space-y-5">
      {err && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{err}</p>}
      <Status s={pf} />
      {S && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[["$", "มูลค่าพอร์ต", usd(S.marketValue), null], ["฿", "ต้นทุนรวม", usd(S.costBasis), null], ["P", "กำไร/ขาดทุนที่ยังไม่รับรู้", usd(S.unrealizedPL), S.unrealizedPLPercent], ["D", "กำไร/ขาดทุนวันนี้", usd(S.dayPL), S.marketValue ? (S.dayPL / S.marketValue) * 100 : null]].map(([ic, l, v, c]) => (
            <StatCard key={l} icon={ic === "฿" ? "∑" : ic} label={l} value={v} change={c} sub={c == null ? null : "เทียบต้นทุน/วันก่อน"} />
          ))}
        </div>
      )}
      {pf.data?.partial && <p className="text-xs text-amber-400">บางตัวดึงราคาไม่ได้ ตัวเลขรวมจึงยังไม่ครบ</p>}
      {pf.data?.holdings?.some((h) => h.marketValue) && (
        <Card title="สัดส่วนพอร์ต"><Donut center={usd(S.marketValue, 0)} items={pf.data.holdings.filter((h) => h.marketValue).map((h) => ({ label: h.symbol, value: h.marketValue }))} /></Card>
      )}
      <Card title="สถานะที่ถืออยู่">
        {pf.data?.holdings?.length ? (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="text-zinc-500">{["หุ้น", "จำนวน", "ต้นทุนเฉลี่ย", "ราคา", "มูลค่า", "กำไร/ขาดทุน", "สัดส่วน"].map((t, i) => <th key={t} className={`py-2 font-normal ${i ? "text-right" : "text-left"}`}>{t}</th>)}</tr></thead>
            <tbody className="divide-y divide-zinc-800 text-zinc-200">
              {pf.data.holdings.map((r) => (
                <tr key={r.symbol}>
                  <td className="py-2"><button onClick={() => open(r.symbol)} className="font-semibold text-white hover:underline">{r.symbol}</button></td>
                  <td className="text-right">{num(r.quantity, 4)}</td><td className="text-right">{usd(r.avgCost)}</td>
                  <td className="text-right">{r.error ? "–" : usd(r.price)}</td><td className="text-right">{usd(r.marketValue)}</td>
                  <td className={`text-right ${tone(r.unrealizedPL)}`}>{r.unrealizedPL == null ? "–" : `${usd(r.unrealizedPL)} (${pct(r.unrealizedPLPercent)})`}</td>
                  <td className="text-right">{r.weightPercent == null ? "–" : r.weightPercent + "%"}</td>
                </tr>
              ))}
            </tbody></table></div>
        ) : !pf.loading && <p className="py-4 text-sm text-zinc-500">ยังไม่มีสถานะ บันทึกรายการซื้อด้านล่างเพื่อเริ่มต้น</p>}
      </Card>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="บันทึกรายการซื้อขาย">
          <div className="grid grid-cols-2 gap-3">
            <Input placeholder="สัญลักษณ์ เช่น AAPL" value={tx.symbol} onChange={(e) => setTx({ ...tx, symbol: e.target.value.toUpperCase() })} />
            <div className="flex gap-2">{["BUY", "SELL"].map((s) => <Pill key={s} on={tx.side === s} onClick={() => setTx({ ...tx, side: s })}>{s === "BUY" ? "ซื้อ" : "ขาย"}</Pill>)}</div>
            <Input type="number" placeholder="จำนวนหุ้น" value={tx.quantity} onChange={(e) => setTx({ ...tx, quantity: e.target.value })} />
            <Input type="number" placeholder="ราคาต่อหุ้น (USD)" value={tx.price} onChange={(e) => setTx({ ...tx, price: e.target.value })} />
            <Input type="number" placeholder="ค่าธรรมเนียม" value={tx.fee} onChange={(e) => setTx({ ...tx, fee: e.target.value })} />
            <Btn onClick={() => run(async () => { await api("/me/transactions", { method: "POST", body: { ...tx, traded_at: new Date().toISOString() } }); setTx({ ...tx, quantity: "", price: "" }); })}>บันทึกรายการ</Btn>
          </div>
        </Card>
        <Card title="Watchlist">
          <div className="mb-3 flex gap-2"><Input placeholder="เพิ่มสัญลักษณ์" value={w} onChange={(e) => setW(e.target.value.toUpperCase())} /><Btn onClick={() => run(async () => { await api("/me/watchlist", { method: "POST", body: { symbol: w } }); setW(""); })}>เพิ่ม</Btn></div>
          <Status s={wl} empty={!wl.loading && !wl.error && !wl.data?.length && "ยังไม่มีหุ้นใน Watchlist"} />
          <div className="divide-y divide-zinc-800">
            {wl.data?.map((r) => (
              <div key={r.symbol} className="flex items-center justify-between py-2 text-sm">
                <button onClick={() => open(r.symbol)} className="font-semibold text-white hover:underline">{r.symbol}</button>
                <span className="text-zinc-300">{r.error ? "ดึงราคาไม่ได้" : usd(r.price)}</span>
                <span className={tone(r.changePercent)}>{pct(r.changePercent)}</span>
                <button aria-label={`ลบ ${r.symbol}`} onClick={() => run(() => api(`/me/watchlist/${r.symbol}`, { method: "DELETE" }))} className="text-zinc-500 hover:text-red-400">ลบ</button>
              </div>
            ))}
          </div>
        </Card>
      </div>
      <Card title="แจ้งเตือนราคา" right={<span className="text-xs text-zinc-500">ส่งผ่าน Telegram ตรวจทุก 5 นาที</span>}>
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Input placeholder="สัญลักษณ์" value={a.symbol} onChange={(e) => setA({ ...a, symbol: e.target.value.toUpperCase() })} />
          <div className="flex gap-2">{[["above", "ขึ้นถึง"], ["below", "ลงถึง"]].map(([v, t]) => <Pill key={v} on={a.condition === v} onClick={() => setA({ ...a, condition: v })}>{t}</Pill>)}</div>
          <Input type="number" placeholder="ราคาเป้าหมาย (USD)" value={a.target} onChange={(e) => setA({ ...a, target: e.target.value })} />
          <Btn onClick={() => run(async () => { await api("/me/alerts", { method: "POST", body: a }); setA({ ...a, target: "" }); })}>ตั้งแจ้งเตือน</Btn>
        </div>
        <Status s={al} empty={!al.loading && !al.error && !al.data?.length && "ยังไม่มีแจ้งเตือน"} />
        <div className="divide-y divide-zinc-800">
          {al.data?.map((r) => (
            <div key={r.id} className="flex items-center justify-between py-2 text-sm">
              <span className="font-semibold text-white">{r.symbol}</span>
              <span className="text-zinc-300">{r.condition === "above" ? "ขึ้นถึง" : "ลงถึง"} {usd(r.target)}</span>
              <span className={r.is_active ? "text-emerald-400" : "text-zinc-500"}>{r.is_active ? "กำลังเฝ้า" : `เตือนแล้วที่ ${usd(r.triggered_price)}`}</span>
              <button aria-label="ลบแจ้งเตือน" onClick={() => run(() => api(`/me/alerts/${r.id}`, { method: "DELETE" }))} className="text-zinc-500 hover:text-red-400">ลบ</button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

/* ---------- 4) เปรียบเทียบ + ปฏิทิน ---------- */
const CMP = [["ราคา", "price", usd], ["% วันนี้", "changePercent", pct], ["P/E", "pe"], ["P/B", "pb"], ["ROE %", "roe"], ["Net margin %", "netMargin"], ["ปันผล %", "dividendYield"], ["EPS", "eps"], ["รายได้โต %", "revenueGrowth"], ["Beta", "beta"]];

function Compare({ api, open }) {
  const [inp, setInp] = useState("AAPL,MSFT,NVDA");
  const [path, setPath] = useState("/compare?symbols=AAPL,MSFT,NVDA");
  const c = useGet(api, path);
  const [kind, setKind] = useState("earnings");
  const today = new Date(), end = new Date(Date.now() + 7 * 864e5);
  const cal = useGet(api, `/calendar/${kind}?from=${iso(today)}&to=${iso(end)}`);
  const rows = cal.data?.slice(0, 40);
  return (
    <div className="space-y-5">
      <Card title="เปรียบเทียบหุ้น" right={<div className="flex gap-2"><Input className="w-56" value={inp} onChange={(e) => setInp(e.target.value.toUpperCase())} /><Btn onClick={() => setPath(`/compare?symbols=${encodeURIComponent(inp)}`)}>เปรียบเทียบ</Btn></div>}>
        <Status s={c} />
        {c.data && (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr><th />{c.data.map((r) => <th key={r.symbol} className="py-2 text-right"><button onClick={() => open(r.symbol)} className="font-semibold text-white hover:underline">{r.symbol}</button><div className="text-xs font-normal text-zinc-500">{r.name}</div></th>)}</tr></thead>
            <tbody className="divide-y divide-zinc-800 text-zinc-200">
              {CMP.map(([l, k, f]) => <tr key={k}><td className="py-2 text-zinc-500">{l}</td>{c.data.map((r) => <td key={r.symbol} className={`text-right ${k === "changePercent" ? tone(r[k]) : ""}`}>{(f || num)(r[k])}</td>)}</tr>)}
            </tbody></table></div>
        )}
      </Card>
      <Card title="ปฏิทิน 7 วันข้างหน้า" right={<div className="flex gap-2"><Pill on={kind === "earnings"} onClick={() => setKind("earnings")}>ประกาศงบ</Pill><Pill on={kind === "dividends"} onClick={() => setKind("dividends")}>ปันผล</Pill></div>}>
        <Status s={cal} empty={!cal.loading && !cal.error && !rows?.length && "ไม่มีรายการในช่วงนี้"} />
        {rows?.length > 0 && (
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="text-zinc-500">{(kind === "earnings" ? ["วันที่", "หุ้น", "เวลา", "EPS คาด", "EPS จริง"] : ["วันที่ XD", "หุ้น", "ปันผล", "Yield %", "วันจ่าย"]).map((t, i) => <th key={t} className={`py-2 font-normal ${i < 2 ? "text-left" : "text-right"}`}>{t}</th>)}</tr></thead>
            <tbody className="divide-y divide-zinc-800 text-zinc-200">
              {rows.map((r, i) => kind === "earnings" ? (
                <tr key={i}><td className="py-2">{r.date}</td><td><button onClick={() => open(r.symbol)} className="font-semibold text-white hover:underline">{r.symbol}</button></td><td className="text-right">{r.hour === "bmo" ? "ก่อนตลาดเปิด" : r.hour === "amc" ? "หลังตลาดปิด" : "–"}</td><td className="text-right">{num(r.epsEstimate)}</td><td className="text-right">{num(r.epsActual)}</td></tr>
              ) : (
                <tr key={i}><td className="py-2">{r.date}</td><td><button onClick={() => open(r.symbol)} className="font-semibold text-white hover:underline">{r.symbol}</button></td><td className="text-right">{usd(r.dividend, 4)}</td><td className="text-right">{num(r.yield)}</td><td className="text-right">{r.paymentDate || "–"}</td></tr>
              ))}
            </tbody></table></div>
        )}
      </Card>
    </div>
  );
}

/* ---------- หน้าหลัก ---------- */
export default function StocksPage({ getToken, apiBase = "", view = "market" }) {
  const authed = !!(typeof getToken === "function" && getToken());
  const tokenRef = useRef(getToken);
  tokenRef.current = getToken;

  const api = useCallback(async (path, opts = {}) => {
    const t = typeof tokenRef.current === "function" ? tokenRef.current() : null;

    const r = await fetch(`${apiBase}/api/stocks${path}`, {
      method: opts.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });

    if (r.status === 204) return null;

    const j = await r.json().catch(() => null);

    if (!r.ok) {
      throw new Error(typeof j?.detail === "string" ? j.detail : "error");
    }

    if (j === null) throw new Error("no_backend");

    return j;
  }, [apiBase]);

  const [sym, setSym] = useState(null);
  const [q, setQ] = useState("");
  const [sr, setSr] = useState([]);

  // ค้นหา/กดหุ้นจากหน้าไหนก็ตาม เก็บตัวที่เลือกไว้ แล้วขอให้ App สลับไปหน้า Company
  const open = (s) => {
    setSym(s);
    setSr([]);
    setQ("");
    if (view !== "detail") {
      try { localStorage.setItem("stocks_pending_symbol", s); } catch {}
      window.dispatchEvent(new CustomEvent("stocks:open-company", { detail: s }));
    }
  };

  // ถ้ามาถึงหน้า Company พร้อมหุ้นที่ค้างไว้ ให้เปิดตัวนั้น
  useEffect(() => {
    if (view !== "detail") return;
    try {
      const p = localStorage.getItem("stocks_pending_symbol");
      if (p) {
        setSym(p);
        localStorage.removeItem("stocks_pending_symbol");
      }
    } catch {}
  }, [view]);

  useEffect(() => {
    if (!q.trim()) return setSr([]);
    const id = setTimeout(
      () =>
        api(`/search?q=${encodeURIComponent(q.trim())}`)
          .then((d) => setSr(Array.isArray(d) ? d : []))
          .catch(() => setSr([])),
      350
    );
    return () => clearTimeout(id);
  }, [q, api]);

  const TITLES = {
    market: ["หุ้นสหรัฐ", "ราคา งบการเงิน และพอร์ตหุ้น NYSE / Nasdaq หน่วย USD"],
    detail: ["ข้อมูลบริษัท", "ราคา กราฟ งบการเงิน และข่าวของหุ้นรายตัว"],
    mine: ["พอร์ตหุ้นของฉัน", "สถานะที่ถือ Watchlist และแจ้งเตือนราคา"],
  };
  const [title, subtitle] = TITLES[view] || TITLES.market;

  return (
    <div className="min-h-screen bg-[#0a0a0a] p-6 text-zinc-100">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white">{title}</h1>
            <p className="mt-1 text-sm text-zinc-400">{subtitle}</p>
          </div>
          <div className="relative w-full md:w-80">
            <Input
              placeholder="ค้นหาหุ้น เช่น Apple, TSLA"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="ค้นหาหุ้น"
            />
            {sr.length > 0 && (
              <ul className="absolute z-10 mt-2 max-h-72 w-full overflow-auto rounded-xl border border-zinc-800 bg-zinc-900 shadow-xl">
                {sr.map((x) => (
                  <li key={x.symbol}>
                    <button
                      onClick={() => open(x.symbol)}
                      className="flex w-full justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-zinc-800"
                    >
                      <span className="font-semibold text-white">{x.symbol}</span>
                      <span className="truncate text-zinc-400">{x.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </header>

        {view === "market" && <Market api={api} open={open} />}
        {view === "detail" &&
          (sym ? (
            <Detail key={sym} api={api} symbol={sym} authed={authed} />
          ) : (
            <Card>
              <p className="text-sm text-zinc-500">ค้นหาหุ้นด้านบน หรือเลือกจากหน้า Market Overview</p>
            </Card>
          ))}
        {view === "mine" && <Mine api={api} open={open} authed={authed} />}
      </div>
    </div>
  );
}
