// @ts-nocheck
import { useState, useEffect, useMemo, useRef } from "react";

const MAX_CHIPS = 6; // จำนวนชื่อหุ้นสูงสุดต่อช่องวัน (เรียงตามประมาณการรายได้ ส่วนที่เหลือดูในรายละเอียดวัน)
const MAX_XD = 3;
const PAGE = 50;

const MONTHS = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];
const DAYS_SHORT = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"];
const DAYS_LONG = ["วันอาทิตย์", "วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัสบดี", "วันศุกร์", "วันเสาร์"];

const ERR = {
  rate_limited: "โควต้าข้อมูลเต็มชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่",
  provider_error: "แหล่งข้อมูลขัดข้อง ลองใหม่อีกครั้ง",
  invalid_range: "ช่วงวันที่ไม่ถูกต้อง",
};
const msg = (e) => ERR[e] || "โหลดข้อมูลไม่สำเร็จ ลองใหม่อีกครั้ง";

/* ---------- ตัวช่วย ---------- */
const pad = (n) => String(n).padStart(2, "0");
const ymd = (y, m, d) => `${y}-${pad(m + 1)}-${pad(d)}`; // ใช้วันที่ท้องถิ่น ไม่ผ่าน UTC เพื่อกันวันเลื่อน
const usd = (n, d = 2) => (n == null ? "–" : "$" + Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const big = (n) => {
  if (n == null) return "–";
  const a = Math.abs(n);
  return a >= 1e12 ? (n / 1e12).toFixed(2) + "T" : a >= 1e9 ? (n / 1e9).toFixed(2) + "B" : a >= 1e6 ? (n / 1e6).toFixed(1) + "M" : Number(n).toLocaleString("en-US");
};
const money = (n) => (n == null ? "–" : "$" + big(n));

const HOUR = { bmo: "ก่อนเปิด", amc: "หลังปิด", dmh: "ระหว่างวัน" };
const HOUR_ICON = { bmo: "☀", amc: "🌙", dmh: "◐" };

const surprise = (r) => {
  if (r.epsActual == null || r.epsEstimate == null) return null;
  if (r.epsEstimate === 0) return r.epsActual > 0 ? 100 : r.epsActual < 0 ? -100 : 0;
  return ((r.epsActual - r.epsEstimate) / Math.abs(r.epsEstimate)) * 100;
};

const chipTone = (h) =>
  h === "bmo"
    ? "bg-sky-500/15 text-sky-600 dark:text-sky-300"
    : h === "amc"
    ? "bg-violet-500/15 text-violet-600 dark:text-violet-300"
    : "bg-zinc-500/15 text-foreground/80";

/* ---------- ชิ้นส่วนย่อย ---------- */
function Chip({ r, star, onPick }) {
  const s = surprise(r);
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onPick(r.symbol); }}
      title={`${r.symbol} · ${HOUR[r.hour] || "ไม่ระบุเวลา"} · EPS คาด ${r.epsEstimate ?? "–"}${s != null ? ` · จริง ${r.epsActual}` : ""}`}
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold hover:brightness-125 ${chipTone(r.hour)}`}
    >
      {star && <span className="text-amber-400">★</span>}
      {r.symbol}
      {s != null && <span className={`h-1.5 w-1.5 rounded-full ${s >= 0 ? "bg-emerald-400" : "bg-red-400"}`} />}
    </button>
  );
}

function XdChip({ r, onPick }) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onPick(r.symbol); }}
      title={`${r.symbol} · ขึ้นเครื่องหมาย XD · ปันผล ${r.dividend ?? "–"}${r.paymentDate ? ` · จ่าย ${r.paymentDate}` : ""}`}
      className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-600 hover:brightness-125 dark:text-emerald-300"
    >
      {r.symbol}
    </button>
  );
}

const Toggle = ({ on, children, ...p }) => (
  <button
    type="button"
    {...p}
    className={`rounded-full px-3 py-1.5 text-sm transition disabled:opacity-40 ${
      on ? "bg-emerald-500 font-medium text-black" : "border border-border bg-card text-foreground/80 hover:bg-accent"
    }`}
  >
    {children}
  </button>
);

/* ---------- หน้า Earnings ---------- */
export default function EarningsPage({ api, open, authed }) {
  const now = new Date();
  const todayIso = ymd(now.getFullYear(), now.getMonth(), now.getDate());
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sel, setSel] = useState(todayIso);
  const [showEarn, setShowEarn] = useState(true);
  const [showXd, setShowXd] = useState(true);
  const [onlyEst, setOnlyEst] = useState(true);
  const [onlyWl, setOnlyWl] = useState(false);
  const [wl, setWl] = useState(null); // Set ของหุ้นใน Watchlist (โหลดเมื่อเปิดตัวกรอง)
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const cache = useRef({});

  const { y, m } = ym;
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const isCurrentMonth = y === now.getFullYear() && m === now.getMonth();

  // โหลดข้อมูลเดือนที่เลือก (ประกาศงบ + XD แยกกัน ถ้าปันผลพัง งบยังแสดงได้)
  useEffect(() => {
    const key = `${y}-${m}`;
    if (cache.current[key]) {
      setData(cache.current[key]);
      setLoading(false);
      setError("");
      return;
    }
    let off = false;
    setLoading(true);
    setError("");
    setData(null);
    const frm = ymd(y, m, 1), to = ymd(y, m, daysInMonth);
    Promise.allSettled([api(`/calendar/earnings?from=${frm}&to=${to}`), api(`/calendar/dividends?from=${frm}&to=${to}`)]).then(([e, d]) => {
      if (off) return;
      setLoading(false);
      if (e.status === "rejected") return setError(msg(e.reason?.message));
      const val = {
        earn: Array.isArray(e.value) ? e.value : [],
        div: d.status === "fulfilled" && Array.isArray(d.value) ? d.value : [],
        divFailed: d.status === "rejected",
      };
      cache.current[key] = val;
      setData(val);
    });
    return () => { off = true; };
  }, [api, y, m, daysInMonth]);

  // โหลด Watchlist ครั้งเดียวเมื่อผู้ใช้เปิดตัวกรอง
  useEffect(() => {
    if (!onlyWl || wl || !authed) return;
    let off = false;
    api("/me/watchlist")
      .then((d) => !off && setWl(new Set((Array.isArray(d) ? d : []).map((r) => r.symbol))))
      .catch(() => !off && setWl(new Set()));
    return () => { off = true; };
  }, [onlyWl, wl, authed, api]);

  const pass = (sym) => (!q || sym.includes(q)) && (!onlyWl || !!(wl && wl.has(sym)));

  // จัดกลุ่มตามวัน เรียงบริษัทใหญ่ (ประมาณการรายได้สูง) ก่อน
  const earnBy = useMemo(() => {
    const rows = data?.earn || [];
    const strict = onlyEst && rows.some((r) => r.revenueEstimate != null); // ถ้าแหล่งข้อมูลไม่มีประมาณการเลย ไม่ซ่อนอะไร
    const map = {};
    for (const r of rows) {
      if (!r.date || !r.symbol || !pass(r.symbol)) continue;
      if (strict && r.revenueEstimate == null) continue;
      (map[r.date] ||= []).push(r);
    }
    for (const k in map) map[k].sort((a, b) => (b.revenueEstimate ?? -1) - (a.revenueEstimate ?? -1));
    return map;
  }, [data, onlyEst, q, onlyWl, wl]);

  const xdBy = useMemo(() => {
    const map = {};
    for (const r of data?.div || []) {
      if (!r.date || !r.symbol || !pass(r.symbol)) continue;
      (map[r.date] ||= []).push(r);
    }
    for (const k in map) map[k].sort((a, b) => (b.yield ?? -1) - (a.yield ?? -1));
    return map;
  }, [data, q, onlyWl, wl]);

  const totalEarn = Object.values(earnBy).reduce((a, x) => a + x.length, 0);
  const totalXd = Object.values(xdBy).reduce((a, x) => a + x.length, 0);

  // เลือกวันอัตโนมัติเมื่อเปลี่ยนเดือน: วันนี้ (ถ้าอยู่ในเดือน) ไม่งั้นวันแรกที่มีรายการ
  useEffect(() => {
    if (sel.startsWith(`${y}-${pad(m + 1)}`)) return;
    if (isCurrentMonth) return setSel(todayIso);
    const first = Object.keys({ ...earnBy, ...xdBy }).sort()[0];
    setSel(first || ymd(y, m, 1));
  }, [y, m, data]); // eslint-disable-line

  useEffect(() => setLimit(PAGE), [sel, q]);

  // สร้างตารางจันทร์–ศุกร์ (ตลาดสหรัฐไม่ประกาศงบวันเสาร์อาทิตย์)
  const weeks = useMemo(() => {
    const out = [];
    let cur = Array(5).fill(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const wd = (new Date(y, m, d).getDay() + 6) % 7;
      if (wd > 4) continue;
      cur[wd] = d;
      if (wd === 4) { out.push(cur); cur = Array(5).fill(null); }
    }
    if (cur.some(Boolean)) out.push(cur);
    return out;
  }, [y, m, daysInMonth]);

  const move = (delta) => setYm(({ y: yy, m: mm }) => {
    const d = new Date(yy, mm + delta, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  });

  // ประกาศเด่น: รายใหญ่ที่กำลังจะมา (หรือเด่นสุดของเดือนที่ดูย้อนหลัง)
  const highlights = useMemo(() => {
    const all = Object.entries(earnBy).flatMap(([d, rows]) => rows.map((r) => ({ ...r, date: d })));
    const list = isCurrentMonth ? all.filter((r) => r.date >= todayIso) : all;
    return list
      .filter((r) => r.revenueEstimate != null)
      .sort((a, b) => b.revenueEstimate - a.revenueEstimate)
      .slice(0, 6)
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [earnBy, isCurrentMonth, todayIso]);

  const selDate = new Date(`${sel}T00:00:00`);
  const selEarn = earnBy[sel] || [];
  const selXd = xdBy[sel] || [];
  const starOf = (s) => !!(wl && wl.has(s));

  /* ----- ช่องวันในปฏิทิน ----- */
  const Cell = ({ d }) => {
    if (!d) return <div className="hidden rounded-xl bg-muted/20 md:block" />;
    const iso = ymd(y, m, d);
    const e = showEarn ? earnBy[iso] || [] : [];
    const x = showXd ? xdBy[iso] || [] : [];
    const shown = q ? e : e.slice(0, MAX_CHIPS);
    const hidden = e.length - shown.length;
    const groups = [["bmo", shown.filter((r) => r.hour === "bmo")], ["amc", shown.filter((r) => r.hour === "amc")], ["", shown.filter((r) => r.hour !== "bmo" && r.hour !== "amc")]];
    const isSel = iso === sel;
    const isToday = iso === todayIso;
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={() => setSel(iso)}
        onKeyDown={(ev) => ev.key === "Enter" && setSel(iso)}
        className={`min-h-[132px] cursor-pointer rounded-xl border p-2 transition ${isSel ? "border-emerald-500 bg-accent" : "border-border hover:bg-accent/50"}`}
      >
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] text-muted-foreground">{e.length + x.length > 0 ? `${e.length + x.length} รายการ` : ""}</span>
          <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${isToday ? "bg-emerald-500 text-black" : "text-foreground"}`}>{d}</span>
        </div>
        <div className="space-y-1.5">
          {groups.map(([h, rows]) =>
            rows.length ? (
              <div key={h || "x"} className="flex flex-wrap items-center gap-1">
                <span className="text-[11px]" title={HOUR[h] || ""}>{HOUR_ICON[h] || "·"}</span>
                {rows.map((r) => <Chip key={r.symbol} r={r} star={starOf(r.symbol)} onPick={open} />)}
              </div>
            ) : null
          )}
          {hidden > 0 && <div className="text-[11px] text-muted-foreground">+{hidden} บริษัท</div>}
          {x.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 border-t border-border/60 pt-1.5">
              <span className="text-[10px] font-semibold text-emerald-500">XD</span>
              {x.slice(0, MAX_XD).map((r) => <XdChip key={r.symbol} r={r} onPick={open} />)}
              {x.length > MAX_XD && <span className="text-[11px] text-muted-foreground">+{x.length - MAX_XD}</span>}
            </div>
          )}
        </div>
      </div>
    );
  };

  const agendaDays = Object.keys({ ...(showEarn ? earnBy : {}), ...(showXd ? xdBy : {}) }).sort();

  return (
    <div className="space-y-5">
      {/* แถบควบคุม */}
      <section className="rounded-2xl border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button onClick={() => move(-1)} aria-label="เดือนก่อนหน้า" className="rounded-lg border border-border px-3 py-1.5 hover:bg-accent">‹</button>
            <h3 className="min-w-[150px] text-center text-lg font-semibold text-foreground">{MONTHS[m]} {y}</h3>
            <button onClick={() => move(1)} aria-label="เดือนถัดไป" className="rounded-lg border border-border px-3 py-1.5 hover:bg-accent">›</button>
            {!isCurrentMonth && (
              <button onClick={() => { setYm({ y: now.getFullYear(), m: now.getMonth() }); setSel(todayIso); }} className="ml-1 text-sm text-emerald-500 hover:underline">
                วันนี้
              </button>
            )}
          </div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value.toUpperCase())}
            placeholder="ค้นหาหุ้นในเดือนนี้ เช่น NVDA"
            aria-label="ค้นหาหุ้นในปฏิทิน"
            className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-emerald-500 sm:w-64"
          />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Toggle on={showEarn} onClick={() => setShowEarn((v) => !v)}>ประกาศงบ{data ? ` (${totalEarn})` : ""}</Toggle>
          <Toggle on={showXd} onClick={() => setShowXd((v) => !v)}>ขึ้น XD{data ? ` (${totalXd})` : ""}</Toggle>
          <Toggle on={onlyEst} onClick={() => setOnlyEst((v) => !v)} title="ซ่อนบริษัทเล็กที่ไม่มีประมาณการรายได้">เฉพาะบริษัทที่มีประมาณการ</Toggle>
          <Toggle on={onlyWl} disabled={!authed} onClick={() => setOnlyWl((v) => !v)} title={authed ? "" : "เข้าสู่ระบบก่อน"}>
            ★ เฉพาะ Watchlist
          </Toggle>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span><span className="rounded bg-sky-500/15 px-1.5 text-sky-600 dark:text-sky-300">☀</span> ก่อนตลาดเปิด</span>
          <span><span className="rounded bg-violet-500/15 px-1.5 text-violet-600 dark:text-violet-300">🌙</span> หลังตลาดปิด</span>
          <span><span className="rounded bg-emerald-500/15 px-1.5 text-emerald-600 dark:text-emerald-300">XD</span> ขึ้นเครื่องหมายไม่ได้รับปันผล</span>
          <span><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />ประกาศแล้ว ดีกว่าคาด <span className="mx-1 inline-block h-1.5 w-1.5 rounded-full bg-red-400" />แย่กว่าคาด</span>
        </div>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</p>}
      {data?.divFailed && showXd && <p className="text-xs text-amber-400">ดึงข้อมูลปันผล (XD) ไม่ได้ในตอนนี้ แสดงเฉพาะประกาศงบ</p>}
      {onlyWl && authed && !wl && <p className="text-xs text-muted-foreground">กำลังโหลด Watchlist…</p>}

      {/* ประกาศเด่น */}
      {showEarn && highlights.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-foreground">{isCurrentMonth ? "ประกาศเด่นที่กำลังจะมา" : "ประกาศเด่นของเดือนนี้"}</h4>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {highlights.map((r) => {
              const dt = new Date(`${r.date}T00:00:00`);
              return (
                <button key={r.symbol + r.date} onClick={() => open(r.symbol)} className="rounded-2xl border bg-card p-3 text-left hover:border-emerald-500/60">
                  <div className="flex items-center justify-between">
                    <span className="text-base font-bold text-foreground">{r.symbol}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[11px] ${chipTone(r.hour)}`}>{HOUR_ICON[r.hour] || "·"} {HOUR[r.hour] || "ไม่ระบุ"}</span>
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">{dt.getDate()} {MONTHS[dt.getMonth()]}</div>
                  <div className="mt-2 text-xs text-muted-foreground">รายได้คาด <span className="text-foreground">{money(r.revenueEstimate)}</span></div>
                  <div className="text-xs text-muted-foreground">EPS คาด <span className="text-foreground">{usd(r.epsEstimate)}</span></div>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* ปฏิทิน (จอกว้าง) */}
      <section className="hidden rounded-2xl border bg-card p-4 md:block">
        <div className="mb-2 grid grid-cols-5 gap-2">
          {DAYS_SHORT.map((n) => <div key={n} className="text-center text-xs font-medium text-muted-foreground">{n}</div>)}
        </div>
        {loading ? (
          <div className="grid grid-cols-5 gap-2">
            {[...Array(20)].map((_, i) => <div key={i} className="h-[132px] animate-pulse rounded-xl bg-muted/50" />)}
          </div>
        ) : (
          <div className="space-y-2">
            {weeks.map((w, i) => (
              <div key={i} className="grid grid-cols-5 gap-2">
                {w.map((d, j) => <Cell key={j} d={d} />)}
              </div>
            ))}
          </div>
        )}
        {!loading && !error && totalEarn + totalXd === 0 && (
          <p className="mt-3 text-center text-sm text-muted-foreground">ไม่มีรายการในเดือนนี้ตามตัวกรองที่เลือก</p>
        )}
      </section>

      {/* รายการแบบเรียงวัน (จอเล็ก) */}
      <section className="space-y-2 md:hidden">
        {loading && <div className="h-40 animate-pulse rounded-2xl bg-muted/50" />}
        {!loading && agendaDays.length === 0 && !error && <p className="rounded-2xl border bg-card p-4 text-center text-sm text-muted-foreground">ไม่มีรายการในเดือนนี้ตามตัวกรองที่เลือก</p>}
        {agendaDays.map((iso) => {
          const dt = new Date(`${iso}T00:00:00`);
          const e = showEarn ? earnBy[iso] || [] : [];
          const x = showXd ? xdBy[iso] || [] : [];
          return (
            <div key={iso} onClick={() => setSel(iso)} className={`rounded-2xl border bg-card p-3 ${iso === sel ? "border-emerald-500" : ""}`}>
              <div className="mb-2 text-sm font-semibold text-foreground">{DAYS_LONG[dt.getDay()]} {dt.getDate()} {MONTHS[dt.getMonth()]}{iso === todayIso ? " · วันนี้" : ""}</div>
              <div className="flex flex-wrap gap-1">
                {(q ? e : e.slice(0, 12)).map((r) => <Chip key={r.symbol} r={r} star={starOf(r.symbol)} onPick={open} />)}
                {x.slice(0, 6).map((r) => <XdChip key={"x" + r.symbol} r={r} onPick={open} />)}
              </div>
              {(!q && e.length > 12) && <div className="mt-1 text-xs text-muted-foreground">+{e.length - 12} บริษัท แตะวันเพื่อดูทั้งหมด</div>}
            </div>
          );
        })}
      </section>

      {/* รายละเอียดวันที่เลือก */}
      <section className="rounded-2xl border bg-card p-5">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-base font-semibold text-foreground">
            {DAYS_LONG[selDate.getDay()]}ที่ {selDate.getDate()} {MONTHS[selDate.getMonth()]} {selDate.getFullYear()}
          </h3>
          <span className="text-xs text-muted-foreground">ประกาศงบ {selEarn.length} บริษัท · ขึ้น XD {selXd.length} บริษัท</span>
        </div>

        {selEarn.length === 0 && selXd.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">ไม่มีรายการในวันนี้</p>}

        {selEarn.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground">
                  {["หุ้น", "เวลา", "EPS คาด", "EPS จริง", "ผล", "รายได้คาด", "รายได้จริง"].map((t, i) => (
                    <th key={t} className={`py-2 font-normal ${i < 2 ? "text-left" : "text-right"}`}>{t}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {selEarn.slice(0, limit).map((r) => {
                  const s = surprise(r);
                  return (
                    <tr key={r.symbol} onClick={() => open(r.symbol)} className="cursor-pointer hover:bg-accent/40">
                      <td className="py-2.5 font-semibold text-foreground">{starOf(r.symbol) && <span className="mr-1 text-amber-400">★</span>}{r.symbol}</td>
                      <td className="py-2.5"><span className={`rounded px-1.5 py-0.5 text-[11px] ${chipTone(r.hour)}`}>{HOUR_ICON[r.hour] || "·"} {HOUR[r.hour] || "ไม่ระบุ"}</span></td>
                      <td className="py-2.5 text-right tabular-nums">{usd(r.epsEstimate)}</td>
                      <td className="py-2.5 text-right tabular-nums">{usd(r.epsActual)}</td>
                      <td className="py-2.5 text-right">
                        {s == null ? <span className="text-muted-foreground">–</span> : (
                          <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${s > 0.5 ? "bg-emerald-500/10 text-emerald-400" : s < -0.5 ? "bg-red-500/10 text-red-400" : "bg-muted text-muted-foreground"}`}>
                            {s > 0.5 ? "ดีกว่าคาด" : s < -0.5 ? "แย่กว่าคาด" : "ตรงคาด"} {s > 0 ? "+" : ""}{s.toFixed(1)}%
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{money(r.revenueEstimate)}</td>
                      <td className="py-2.5 text-right tabular-nums">{money(r.revenueActual)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {selEarn.length > limit && (
              <button onClick={() => setLimit((l) => l + PAGE)} className="mt-3 w-full rounded-xl border border-border py-2 text-sm text-foreground hover:bg-accent">
                แสดงเพิ่ม ({selEarn.length - limit} บริษัทที่เหลือ)
              </button>
            )}
          </div>
        )}

        {selXd.length > 0 && (
          <div className={selEarn.length ? "mt-6" : ""}>
            <h4 className="mb-2 text-sm font-semibold text-foreground">ขึ้นเครื่องหมาย XD</h4>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground">
                    {["หุ้น", "ปันผล/หุ้น", "Yield %", "วันจ่ายปันผล"].map((t, i) => <th key={t} className={`py-2 font-normal ${i ? "text-right" : "text-left"}`}>{t}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {selXd.slice(0, limit).map((r) => (
                    <tr key={r.symbol} onClick={() => open(r.symbol)} className="cursor-pointer hover:bg-accent/40">
                      <td className="py-2.5 font-semibold text-foreground">{r.symbol}</td>
                      <td className="py-2.5 text-right tabular-nums">{usd(r.dividend, 4)}</td>
                      <td className="py-2.5 text-right tabular-nums">{r.yield == null ? "–" : Number(r.yield).toFixed(2)}</td>
                      <td className="py-2.5 text-right">{r.paymentDate || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <p className="text-xs leading-5 text-muted-foreground">
        วันที่เป็นเวลาสหรัฐ (ET) · บริษัทที่ประกาศหลังตลาดปิดจะตรงกับเช้าวันถัดไปตามเวลาไทย · ประมาณการเป็นของนักวิเคราะห์และอาจเปลี่ยนได้ ·
        แสดงบริษัทใหญ่ก่อนในแต่ละวัน กดวันเพื่อดูครบทุกบริษัท · ข้อมูลประกาศงบจาก Finnhub ปันผลจาก FMP · ใช้เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน
      </p>
    </div>
  );
}
