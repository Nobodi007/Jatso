import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldAlert } from "lucide-react";
import { LossDistributionSection, PerformanceSection, RollingSection } from "./PerformanceSections";
import type { PerfRes } from "./PerformanceSections";
import { CashDragNote, PnlSection, SectorContributionSection } from "./AttributionExtras";
import { InfoTip } from "./InfoTip";
import type { CashDrag, PnlBreakdown, SectorContribution } from "./AttributionExtras";

/* ───────── types (ตรงกับ /api/stocks/risk/*) ───────── */
interface Metric {
  value: number | null;
  status: string;
  unit?: string;
  formula?: string;
  n_obs?: number | null;
  reason?: string | null;
}
interface Warning {
  code: string;
  symbols?: string[];
  inception_session?: string;
  detail?: unknown;
}
interface Overview {
  meta: {
    as_of?: string;
    benchmark?: { symbol: string; name: string };
    warnings?: Warning[];
    period?: { label?: string; trading_days?: number };
  };
  cards: {
    market_value?: { value: number | null };
    portfolio_return?: Metric;
    benchmark_return?: Metric;
    active_return?: Metric;
    volatility?: Metric;
    max_drawdown?: Metric;
    sharpe?: Metric;
    active_alerts?: { value: number | null; status: string };
  };
}
interface Position {
  symbol: string;
  market_value: number;
  weight_nav: number;
  unrealized_pnl?: number | null;
}
interface Exposure {
  exposure: {
    nav: number;
    equity_value: number;
    cash: number;
    cash_weight: number;
    positions: Position[];
    hhi?: Metric;
    effective_n?: Metric;
    top1?: Metric;
    sectors?: { sector: string; weight_nav: number; market_value?: number }[];
  };
  meta?: { sector_classification?: string };
}
interface Limits {
  max_drawdown: number | null;
  max_single_weight: number | null;
  max_hhi: number | null;
  min_cash_weight: number | null;
  max_sector_weight: number | null;
  max_daily_loss: number | null;
  max_volatility: number | null;
  max_tracking_error: number | null;
}
type LimitSource = "default" | "custom" | "off";
interface LimitsRes {
  limits: Limits;
  source: Record<keyof Limits, LimitSource>;
  defaults: Limits;
}
interface AlertRow {
  id: number | string;
  alert_type: string;
  symbol?: string | null;
  sector?: string | null;
  severity?: "info" | "warning" | "critical" | null;
  threshold?: number | null;
  observed_value?: number | null;
  status: string;
  opened_at?: string;
  resolved_at?: string | null;
  acknowledged_at?: string | null;
  detail?: { stale?: boolean; missing?: { code: string; symbol?: string | null }[]; classification?: string } | null;
}
interface DrawdownPoint { date: string; drawdown: number }
interface Episode {
  peak_date: string; trough_date: string; recovery_date: string | null;
  duration_trading_days: number; recovery_trading_days: number | null;
}
interface Extreme { date?: string; period?: string; return: number; days?: number }
interface Tail {
  current_drawdown?: Metric; drawdown_episode?: Episode | null;
  longest_underwater_trading_days?: number;
  var_95?: Metric; es_95?: Metric; downside_deviation?: Metric;
  extremes?: { worst_day?: Extreme; best_day?: Extreme; worst_week?: Extreme; worst_month?: Extreme };
  drawdown_series?: DrawdownPoint[];
}
interface MetricsRes { risk_adjusted?: Record<string, Metric>; performance?: Record<string, Metric>; tail?: Tail }

/* Phase 2: risk decomposition + stress test (ตรงกับ /risk-decomposition และ /stress-test) */
interface Contribution {
  symbol: string; weight_nav: number; volatility: number; mcr: number; ccr: number; pct_of_risk: number;
}
interface Decomp {
  decomposition: null | {
    portfolio_volatility?: Metric;
    diversification_ratio?: Metric;
    avg_pairwise_correlation?: Metric;
    contributions: Contribution[];
    correlation: { symbols: string[]; matrix: (number | null)[][] } | null;
    top_pairs?: { a: string; b: string; correlation: number }[];
    excluded?: { symbol: string; reason: string }[];
  };
  status?: string;
  reason?: string;
}
interface StressPos { symbol: string; market_value: number; shock: number; pnl: number; basis: string; sector?: string | null }
interface StressSector { sector: string; market_value: number; pnl: number; pnl_pct_nav: number | null }
interface StressRes {
  stress: null | {
    hypothetical: boolean;
    disclaimer: string;
    nav_before: number;
    pnl: number;
    pnl_pct_nav: number | null;
    nav_after: number;
    positions: StressPos[];
    skipped: { symbol: string; reason: string }[];
    unknown_symbols?: string[];
    unknown_sectors?: string[];
    by_sector?: StressSector[];
    betas?: Record<string, Metric>;
  };
  status?: string;
  reason?: string;
}
type Caller = <T>(path: string, init?: RequestInit) => Promise<T>;

/* Phase 3: attribution แบบบางส่วน (ตรงกับ /attribution) */
interface AttrRow { symbol: string; contribution: number; avg_weight_nav: number; days_held: number; held_now: boolean }
interface AttrRes {
  attribution: null | {
    partial: boolean;
    partial_note: string;
    n_obs: number;
    portfolio_return: number;
    positions: AttrRow[];
    execution_and_fees: { value: number; note: string };
    execution?: { value: number; note: string };
    fees?: { value: number; note: string };
    cash_drag?: CashDrag;
    sum_check: { positions: number; execution_and_fees: number; portfolio_return: number; residual: number; ok: boolean };
  };
  pnl?: PnlBreakdown | null;
  by_sector?: SectorContribution[];
  sector_classification?: string;
  status?: string;
  reason?: string;
}

interface Props {
  getToken: () => string | null;
  apiBase: string;
}

/* ───────── helpers ───────── */
const MIN_VOL = 20;
const MIN_SHARPE = 60;

const usd = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

const pct = (n: number | null | undefined, d = 2, sign = false) =>
  n == null ? "—" : `${sign && n > 0 ? "+" : ""}${(n * 100).toFixed(d)}%`;

const PCT_UNIT = /^(decimal(\/yr( per β)?| \(1-day\))?|share( of equity)?)$/;
const fmtMetric = (m?: Metric, sign = false) => {
  if (!m || m.value == null) return "—";
  if (m.unit?.includes("display ×100 as pp")) return `${sign && m.value > 0 ? "+" : ""}${(m.value * 100).toFixed(2)} pp`;
  return m.unit && PCT_UNIT.test(m.unit) ? pct(m.value, 2, sign) : m.value.toFixed(2);
};

const tone = (n: number | null | undefined) =>
  n == null || n === 0 ? "text-foreground" : n > 0 ? "text-emerald-500" : "text-rose-500";

const LIMIT_META: { key: keyof Limits; label: string; hint: string }[] = [
  { key: "max_drawdown", label: "Drawdown สูงสุดที่ยอมรับได้", hint: "เตือนเมื่อ drawdown ปัจจุบันลึกกว่านี้" },
  { key: "max_single_weight", label: "น้ำหนักหุ้นตัวเดียวสูงสุด", hint: "เตือนเมื่อหุ้นตัวใดเกินสัดส่วนของ NAV" },
  { key: "max_hhi", label: "ความกระจุกตัว (HHI) สูงสุด", hint: "ยิ่งใกล้ 1 ยิ่งกระจุกตัว" },
  { key: "min_cash_weight", label: "เงินสดขั้นต่ำ", hint: "เตือนเมื่อเงินสดต่ำกว่าสัดส่วนของ NAV" },
  { key: "max_sector_weight", label: "น้ำหนัก sector สูงสุด", hint: "เตือนเมื่อ sector ใดเกินสัดส่วนของ NAV (sector จาก Finnhub ไม่ใช่ GICS)" },
  { key: "max_daily_loss", label: "ขาดทุนรายวันสูงสุด", hint: "เตือนเมื่อ NAV ของวันซื้อขายล่าสุดลดลงเกินนี้" },
  { key: "max_volatility", label: "ความผันผวนสูงสุด (ต่อปี)", hint: "เตือนเมื่อความผันผวนต่อปีของพอร์ตสูงกว่านี้ (ต้องมีข้อมูลอย่างน้อย 20 วัน)" },
  { key: "max_tracking_error", label: "Tracking error สูงสุด (ต่อปี)", hint: "เตือนเมื่อผลตอบแทนต่างจากดัชนีเกณฑ์เกินนี้ (ต้องมีข้อมูลอย่างน้อย 20 วัน)" },
];

/** ช่วงค่าที่ API/DB ยอมรับ (หน่วยทศนิยม ไม่ใช่ %) */
const LIMIT_RANGE: Record<keyof Limits, { min: number; max: number; minInclusive?: boolean; maxInclusive?: boolean }> = {
  max_drawdown: { min: 0, max: 1, maxInclusive: true },
  max_single_weight: { min: 0, max: 1, maxInclusive: true },
  max_hhi: { min: 0, max: 1, maxInclusive: true },
  min_cash_weight: { min: 0, max: 1, minInclusive: true },
  max_sector_weight: { min: 0, max: 1, maxInclusive: true },
  max_daily_loss: { min: 0, max: 1, maxInclusive: true },
  max_volatility: { min: 0, max: 5, maxInclusive: true },
  max_tracking_error: { min: 0, max: 5, maxInclusive: true },
};
const isDecimalLimit = (key: keyof Limits) => key === "max_hhi";
const limitText = (key: keyof Limits, v: number) => (isDecimalLimit(key) ? v.toFixed(2) : pct(v, 0));
const limitDraft = (key: keyof Limits, v: number | null) =>
  v == null ? "" : String(isDecimalLimit(key) ? v : Number((v * 100).toFixed(2)));

/** แปลงข้อความที่ผู้ใช้กรอกเป็นค่าที่ API ต้องการ: null = ไม่ตั้ง, "bad" = ค่าผิด */
const parseLimit = (key: keyof Limits, s: string): number | null | "bad" => {
  const t = s.trim();
  if (t === "") return null;
  const n = Number(t);
  if (!Number.isFinite(n)) return "bad";
  const v = isDecimalLimit(key) ? n : Number((n / 100).toFixed(6));
  const r = LIMIT_RANGE[key];
  const ok = (r.minInclusive ? v >= r.min : v > r.min) && (r.maxInclusive ? v <= r.max : v < r.max);
  return ok ? v : "bad";
};

const ALERT_LABEL: Record<string, string> = {
  drawdown: "Drawdown เกินลิมิต",
  single_weight: "หุ้นตัวเดียวเกินลิมิต",
  hhi: "HHI เกินลิมิต",
  low_cash: "เงินสดต่ำกว่าลิมิต",
  sector_weight: "Sector เกินลิมิต",
  daily_loss: "ขาดทุนรายวันเกินลิมิต",
  volatility: "ความผันผวนเกินลิมิต",
  tracking_error: "Tracking error เกินลิมิต",
  stale_data: "ข้อมูลเก่าหรือไม่ครบ",
};
const SEVERITY_META: Record<string, { label: string; kind: "muted" | "warn" | "bad" }> = {
  info: { label: "แจ้งทราบ", kind: "muted" },
  warning: { label: "เฝ้าระวัง", kind: "warn" },
  critical: { label: "รุนแรง", kind: "bad" },
};
const alertVal = (type: string, v: number) =>
  type === "hhi" ? v.toFixed(2) : type === "stale_data" ? `${v.toFixed(0)} วัน` : pct(v, 2);

/** เปิดหน้า Company ด้วยกลไกเดียวกับหน้า Screener */
function openCompany(symbol: string) {
  try {
    localStorage.setItem("stocks_pending_symbol", symbol);
  } catch {
    // เก็บไม่ได้ก็ยังกดได้ แต่หน้า Company จะไม่เปิดหุ้นตัวนั้นให้
  }
  window.dispatchEvent(new CustomEvent("stocks:open-company", { detail: symbol }));
}

const WARNING_TEXT = (w: Warning): string => {
  const syms = w.symbols?.length ? ` (${w.symbols.join(", ")})` : "";
  switch (w.code) {
    case "unofficial_price_source":
      return `ราคาของบางตัวมาจากแหล่งสำรองที่ไม่เป็นทางการ${syms}`;
    case "portfolio_younger_than_period":
      return `พอร์ตเริ่มหลังช่วงเวลาที่เลือก${w.inception_session ? ` (เริ่ม ${w.inception_session})` : ""} จึงคำนวณเท่าที่มี`;
    case "trades_after_last_close":
      return "มีรายการซื้อขายหลังราคาปิดล่าสุด ยังไม่รวมใน NAV จนกว่าจะมีราคาปิดของรอบนั้น";
    default:
      return `หมายเหตุข้อมูล: ${w.code}`;
  }
};

function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-3xl border border-border bg-card p-5 ${className}`}>{children}</div>;
}

function Chip({ children, kind = "muted" }: { children: ReactNode; kind?: "muted" | "ok" | "warn" | "bad" }) {
  const c =
    kind === "ok"
      ? "bg-emerald-500/10 text-emerald-500"
      : kind === "warn"
        ? "bg-amber-500/10 text-amber-500"
        : kind === "bad"
          ? "bg-rose-500/10 text-rose-500"
          : "bg-muted text-muted-foreground";
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs ${c}`}>{children}</span>;
}

function Bar({ value, max = 1, kind = "muted" }: { value: number; max?: number; kind?: "muted" | "ok" | "warn" | "bad" }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100));
  const c = kind === "bad" ? "bg-rose-500" : kind === "warn" ? "bg-amber-500" : kind === "ok" ? "bg-emerald-500" : "bg-foreground/60";
  return (
    <div className="h-1.5 w-full rounded-full bg-muted">
      <div className={`h-1.5 rounded-full ${c}`} style={{ width: `${w}%` }} />
    </div>
  );
}

/** การ์ดที่ข้อมูลไม่พอ: ขอบประ + แถบความคืบหน้าจาก n_obs จริง */
function PendingCard({ title, m, need, help }: { title: string; m?: Metric; need: number; help?: string }) {
  const n = m?.n_obs ?? 0;
  return (
    <Card className="border-dashed">
      <p className="text-sm text-muted-foreground">
        {title}
        {help && <InfoTip k={help} />}
      </p>
      <p className="mt-3 text-lg text-muted-foreground">ยังคำนวณไม่ได้</p>
      <div className="mt-4">
        <Bar value={n} max={need} />
        <p className="mt-2 text-xs text-muted-foreground tabular-nums">
          มีข้อมูล {n} จาก {need} วัน
        </p>
      </div>
    </Card>
  );
}

function ReturnCard({ title, m, note, help }: { title: string; m?: Metric; note?: string; help?: string }) {
  const v = m?.value ?? null;
  const grad =
    v == null
      ? ""
      : v < 0
        ? "bg-gradient-to-l from-rose-500/10 to-card to-80%"
        : "bg-gradient-to-l from-emerald-500/10 to-card to-80%";
  return (
    <Card className={grad}>
      <p className="text-sm text-muted-foreground">
        {title}
        {help && <InfoTip k={help} />}
      </p>
      <p className={`mt-3 text-3xl font-medium tabular-nums ${tone(v)}`}>{fmtMetric(m, true)}</p>
      {note && <p className="mt-2 text-xs text-muted-foreground">{note}</p>}
    </Card>
  );
}

const MIN_DD_DAYS = 5;
const show = (m?: Metric) => (!m ? "—" : m.value == null ? "ข้อมูลยังไม่พอ" : fmtMetric(m));
const extremeText = (x?: Extreme) => (x ? `${pct(x.return, 2, true)} · ${x.date ?? x.period ?? ""}` : "—");

function UnderwaterChart({ series }: { series: DrawdownPoint[] }) {
  const W = 600, H = 140, P = 8;
  const min = Math.min(...series.map((p) => p.drawdown), -0.0001);
  const x = (i: number) => P + (i / Math.max(series.length - 1, 1)) * (W - 2 * P);
  const y = (d: number) => P + (d / min) * (H - 2 * P);
  const pts = series.map((p, i) => `${x(i)},${y(p.drawdown)}`).join(" ");
  const area = `${x(0)},${P} ${pts} ${x(series.length - 1)},${P}`;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-36 w-full" role="img" aria-label="กราฟ drawdown">
        <line x1={P} x2={W - P} y1={P} y2={P} className="stroke-border" />
        <polygon points={area} className="fill-rose-500/15" />
        <polyline points={pts} fill="none" className="stroke-rose-500" strokeWidth={1.5} />
      </svg>
      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
        {series[0]?.date} → {series[series.length - 1]?.date} · ลึกสุด {pct(min, 2)}
      </p>
    </div>
  );
}

function TailSection({ m }: { m: MetricsRes | null }) {
  if (!m) {
    return (
      <Card>
        <h2 className="text-base font-medium">Drawdown และความเสี่ยงขาลง</h2>
        <p className="mt-3 text-sm text-muted-foreground">โหลดข้อมูลส่วนนี้ไม่สำเร็จ</p>
      </Card>
    );
  }
  const t = m.tail ?? {};
  const series = t.drawdown_series ?? [];
  const nDays = Math.max(series.length - 1, 0);
  const enough = nDays >= MIN_DD_DAYS;
  const ep = t.drawdown_episode ?? null;
  const ex = t.extremes;
  const rows: [string, string, string?][] = [
    ["Drawdown ปัจจุบัน", show(t.current_drawdown), "current_drawdown"],
    ["VaR 95% (1 วัน)", show(t.var_95), "var_95"],
    ["ES 95% (1 วัน)", show(t.es_95), "es_95"],
    ["Downside deviation (รายปี)", show(t.downside_deviation), "downside_deviation"],
    ["Downside beta", show(m.risk_adjusted?.downside_beta), "downside_beta"],
  ];
  if (enough) {
    rows.push(
      ["ช่วงจมน้ำนานสุด", t.longest_underwater_trading_days != null ? `${t.longest_underwater_trading_days} วันทำการ` : "—", "longest_underwater"],
      ["วันที่แย่สุด", extremeText(ex?.worst_day)],
      ["สัปดาห์ที่แย่สุด", extremeText(ex?.worst_week)],
      ["เดือนที่แย่สุด", extremeText(ex?.worst_month)],
    );
  }
  return (
    <Card>
      <h2 className="text-base font-medium">Drawdown และความเสี่ยงขาลง</h2>
      <div className="mt-4">
        {enough ? (
          <UnderwaterChart series={series} />
        ) : (
          <p className="rounded-2xl border border-dashed border-border p-4 text-sm text-muted-foreground">
            ข้อมูลยังไม่พอสำหรับกราฟ (มี {series.length} จาก {MIN_DD_DAYS} วัน)
          </p>
        )}
      </div>
      {enough && ep && (
        <p className="mt-3 text-sm text-muted-foreground">
          ช่วงลึกสุด: ยอดเดิม {ep.peak_date} → จุดต่ำสุด {ep.trough_date} →{" "}
          {ep.recovery_date ? `ฟื้นตัว ${ep.recovery_date}` : "ยังไม่ฟื้นตัว"} ({ep.duration_trading_days} วันทำการ)
        </p>
      )}
      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 text-sm md:grid-cols-3">
        {rows.map(([k, v, help]) => (
          <div key={k}>
            <dt className="text-muted-foreground">
              {k}
              {help && <InfoTip k={help} />}
            </dt>
            <dd className="mt-0.5 tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

const RA_META: { key: string; label: string }[] = [
  { key: "sharpe", label: "Sharpe ratio" },
  { key: "sortino", label: "Sortino ratio" },
  { key: "information_ratio", label: "Information ratio" },
  { key: "tracking_error", label: "Tracking error" },
  { key: "beta_capm", label: "Beta (CAPM)" },
  { key: "jensens_alpha", label: "Alpha ของ Jensen (รายปี)" },
  { key: "alpha_t_stat", label: "t-stat ของ Alpha" },
  { key: "treynor", label: "Treynor ratio" },
  { key: "appraisal_ratio", label: "Appraisal ratio" },
  { key: "calmar", label: "Calmar ratio" },
  { key: "downside_beta", label: "Downside beta" },
  { key: "beta", label: "Beta เทียบดัชนี" },
  { key: "r_squared", label: "R²" },
  { key: "up_capture", label: "Up capture" },
  { key: "down_capture", label: "Down capture" },
  { key: "hit_rate", label: "สัดส่วนวันที่ชนะดัชนี" },
];

const needFrom = (m: Metric) => Number(/≥(\d+)/.exec(m.reason ?? "")?.[1]) || null;

function RaItem({ k, label, m }: { k: string; label: string; m: Metric }) {
  const need = needFrom(m);
  const n = m.n_obs ?? 0;
  const why =
    m.status === "unavailable"
      ? "ไม่มีข้อมูลต้นทาง"
      : m.reason?.includes("period < 1 year")
        ? "ต้องมีข้อมูลครบ 1 ปี"
        : "คำนวณไม่ได้";
  return (
    <div title={m.formula}>
      <dt className="text-muted-foreground">
        {label}
        <InfoTip k={k} />
      </dt>
      {m.value != null ? (
        <dd className="mt-0.5 flex items-center gap-2 tabular-nums">
          {fmtMetric(m)}
          {m.status === "limited_sample" && <Chip kind="warn">ตัวอย่างน้อย</Chip>}
        </dd>
      ) : m.status === "insufficient_data" && need ? (
        <dd className="mt-1.5">
          <Bar value={n} max={need} />
          <p className="mt-1 text-xs text-muted-foreground tabular-nums">
            มีข้อมูล {n} จาก {need} วัน
          </p>
        </dd>
      ) : (
        <dd className="mt-0.5 text-muted-foreground" title={m.reason ?? undefined}>
          {why}
        </dd>
      )}
    </div>
  );
}

function RiskAdjustedSection({ m }: { m: MetricsRes | null }) {
  if (!m) return null;
  const items = RA_META.flatMap(({ key, label }) => {
    const metric = m.risk_adjusted?.[key] ?? m.performance?.[key];
    return metric ? [{ key, label, metric }] : [];
  });
  if (items.length === 0) return null;
  return (
    <Card>
      <h2 className="text-base font-medium">ตัวชี้วัดปรับตามความเสี่ยง</h2>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-5 text-sm md:grid-cols-4">
        {items.map((i) => (
          <RaItem key={i.key} k={i.key} label={i.label} m={i.metric} />
        ))}
      </dl>
      <p className="mt-4 text-xs text-muted-foreground">กดปุ่ม i ข้างชื่อเพื่อดูความหมายและวิธีอ่าน (วางเมาส์บนชื่อเพื่อดูสูตร) · ตัวที่ข้อมูลไม่พอจะไม่แสดงตัวเลข</p>
    </Card>
  );
}
/* ───────── Phase 2 UI: ความเสี่ยงรายตัวและความสัมพันธ์ / Stress test ───────── */
const MIN_DECOMP = 60;
const EXCLUDE_TEXT: Record<string, string> = {
  "incomplete price history in window": "ประวัติราคาในช่วงไม่ครบ",
  "no return history": "ไม่มีประวัติผลตอบแทน",
};

const corrBg = (v: number | null): string | undefined =>
  v == null
    ? undefined
    : v >= 0
      ? `rgba(244,63,94,${(Math.abs(v) * 0.45).toFixed(2)})`
      : `rgba(16,185,129,${(Math.abs(v) * 0.45).toFixed(2)})`;

function DecompositionSection({ d }: { d: Decomp | null }) {
  const title = <h2 className="text-base font-medium">ความเสี่ยงรายตัวและความสัมพันธ์</h2>;
  if (!d) {
    return (
      <Card>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">โหลดข้อมูลส่วนนี้ไม่สำเร็จ</p>
      </Card>
    );
  }
  const x = d.decomposition;
  if (!x) {
    return (
      <Card>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">
          ยังไม่มีข้อมูล ({d.reason ?? d.status ?? "unavailable"})
        </p>
      </Card>
    );
  }
  const pv = x.portfolio_volatility;
  const excluded = x.excluded ?? [];
  if (!pv || pv.value == null) {
    const n = pv?.n_obs ?? 0;
    return (
      <Card className="border-dashed">
        {title}
        <p className="mt-3 text-lg text-muted-foreground">ยังคำนวณไม่ได้</p>
        <div className="mt-4">
          <Bar value={n} max={MIN_DECOMP} />
          <p className="mt-2 text-xs text-muted-foreground tabular-nums">
            มีข้อมูล {n} จาก {MIN_DECOMP} วัน (ต้องมีราคาย้อนหลังของทุกตัวที่ถืออยู่)
          </p>
        </div>
        {excluded.length > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            ตัดออก: {excluded.map((e) => `${e.symbol} (${EXCLUDE_TEXT[e.reason] ?? e.reason})`).join(", ")}
          </p>
        )}
      </Card>
    );
  }
  const dr = x.diversification_ratio?.value ?? null;
  const ac = x.avg_pairwise_correlation?.value ?? null;
  const syms = x.correlation?.symbols ?? [];
  const mat = x.correlation?.matrix ?? [];
  return (
    <Card>
      {title}
      <div className="mt-3 flex flex-wrap gap-2">
        <Chip>ความผันผวนพอร์ต {pct(pv.value, 2)}</Chip>
        {pv.status === "limited_sample" && <Chip kind="warn">ตัวอย่างน้อย (มี {pv.n_obs ?? 0} วัน)</Chip>}
        {dr != null && <Chip>Diversification ratio {dr.toFixed(2)}</Chip>}
        {ac != null && <Chip>correlation เฉลี่ย {ac.toFixed(2)}</Chip>}
      </div>

      <div className="mt-4 space-y-3">
        {x.contributions.map((c) => (
          <div key={c.symbol}>
            <div className="mb-1 flex justify-between text-sm">
              <span>{c.symbol}</span>
              <span className="tabular-nums text-muted-foreground">
                น้ำหนัก {pct(c.weight_nav, 1)} · สัดส่วนความเสี่ยง {pct(c.pct_of_risk, 1)} ·{" "}
                <span title="MCR: ความผันผวนพอร์ตเปลี่ยนเท่าไรเมื่อเพิ่มน้ำหนักตัวนี้ (ลดเงินสดลง)">MCR {c.mcr.toFixed(2)}</span>
              </span>
            </div>
            <Bar value={Math.max(c.pct_of_risk, 0)} />
          </div>
        ))}
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        MCR (marginal contribution to risk) = ความผันผวนพอร์ตเปลี่ยนเท่าไรต่อน้ำหนักที่เพิ่มของตัวนั้น เช่น 0.35 แปลว่าเพิ่มน้ำหนัก 1 จุดเปอร์เซ็นต์ (ลดเงินสดลง)
        ความผันผวนพอร์ตเพิ่มประมาณ 0.35 จุด · คำนวณจากความแปรปรวนร่วมในอดีตและน้ำหนักปัจจุบัน
        <InfoTip k="mcr" />
      </p>

      {syms.length >= 2 && syms.length <= 12 && (
        <div className="mt-5 overflow-x-auto">
          <table className="text-xs tabular-nums">
            <thead>
              <tr>
                <th className="p-1" />
                {syms.map((s) => (
                  <th key={s} className="p-1 font-normal text-muted-foreground">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {syms.map((a, i) => (
                <tr key={a}>
                  <th className="p-1 pr-2 text-left font-normal text-muted-foreground">{a}</th>
                  {syms.map((b, j) => {
                    const v = mat[i]?.[j] ?? null;
                    return (
                      <td key={b} className="p-1 text-center" style={{ background: i === j ? undefined : corrBg(v) }}>
                        {v == null ? "—" : v.toFixed(2)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(x.top_pairs ?? []).length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          คู่ที่สัมพันธ์กันสูงสุด: {(x.top_pairs ?? []).map((p) => `${p.a}/${p.b} ${p.correlation.toFixed(2)}`).join(" · ")}
        </p>
      )}
      {excluded.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          ตัดออกจากการคำนวณ: {excluded.map((e) => `${e.symbol} (${EXCLUDE_TEXT[e.reason] ?? e.reason})`).join(", ")}
        </p>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        คำนวณจากน้ำหนักปัจจุบันกับประวัติราคาย้อนหลัง ไม่ใช่ความผันผวนที่เกิดขึ้นจริงของพอร์ต · สูตร: σ = √(wᵀΣw)
      </p>
    </Card>
  );
}

const PRESETS = [-5, -10, -20];

function StressSection({ call, symbols, sectorNames }: { call: Caller; symbols: string[]; sectorNames: string[] }) {
  const [mkt, setMkt] = useState("");
  const [per, setPer] = useState<Record<string, string>>({});
  const [perSec, setPerSec] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(false);
  const [openSec, setOpenSec] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [res, setRes] = useState<StressRes | null>(null);

  const toShock = (s: string): number | null | "bad" => {
    const t = s.trim();
    if (t === "") return null;
    const n = Number(t);
    if (!Number.isFinite(n) || n < -100 || n > 100) return "bad";
    return Number((n / 100).toFixed(6));
  };

  const run = async () => {
    const body: { market_shock?: number; shocks?: Record<string, number>; sector_shocks?: Record<string, number> } = {};
    const m = toShock(mkt);
    if (m === "bad") {
      setMsg("ค่าของตลาดต้องอยู่ระหว่าง -100 ถึง 100");
      return;
    }
    if (m !== null) body.market_shock = m;
    const shocks: Record<string, number> = {};
    for (const s of symbols) {
      const v = toShock(per[s] ?? "");
      if (v === "bad") {
        setMsg(`ค่าของ ${s} ต้องอยู่ระหว่าง -100 ถึง 100`);
        return;
      }
      if (v !== null) shocks[s] = v;
    }
    if (Object.keys(shocks).length > 0) body.shocks = shocks;
    const secShocks: Record<string, number> = {};
    for (const n of sectorNames) {
      const v = toShock(perSec[n] ?? "");
      if (v === "bad") {
        setMsg(`ค่าของ ${n} ต้องอยู่ระหว่าง -100 ถึง 100`);
        return;
      }
      if (v !== null) secShocks[n] = v;
    }
    if (Object.keys(secShocks).length > 0) body.sector_shocks = secShocks;
    if (body.market_shock === undefined && !body.shocks && !body.sector_shocks) {
      setMsg("ใส่ค่าอย่างน้อยหนึ่งช่อง");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      setRes(
        await call<StressRes>("/stress-test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
      );
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "คำนวณไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  };

  const s = res?.stress ?? null;
  const skipText = (r: string) =>
    r.includes("beta unavailable") ? "ไม่มี beta (ข้อมูลไม่พอ) และไม่ได้กำหนดค่ารายตัว" : r;

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">จำลองสถานการณ์ (Stress test)</h2>
        <Chip kind="warn">สถานการณ์สมมติ ไม่ใช่การพยากรณ์</Chip>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        สมมติว่าราคาเปลี่ยนทันที ผลกระทบ = มูลค่าตำแหน่ง × การเปลี่ยนแปลง · ตลาดที่ลดจะส่งผลกับแต่ละตัวผ่านค่า beta · ไม่ได้จำลอง correlation หรือ volatility ที่เปลี่ยนไป
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="stress-mkt">ตลาด (S&amp;P 500) เปลี่ยน</label>
        <input
          id="stress-mkt"
          inputMode="decimal"
          value={mkt}
          onChange={(ev) => setMkt(ev.target.value)}
          placeholder="เช่น -10"
          className="w-24 rounded-lg border border-border bg-background px-2 py-1 text-right tabular-nums"
        />
        <span className="text-xs text-muted-foreground">%</span>
        {PRESETS.map((p) => (
          <button
            key={p}
            onClick={() => setMkt(String(p))}
            className="rounded-full border border-border px-2.5 py-0.5 text-xs hover:bg-muted"
          >
            {p}%
          </button>
        ))}
      </div>

      {symbols.length > 0 && (
        <div className="mt-3">
          <button onClick={() => setOpen(!open)} className="text-xs text-muted-foreground underline">
            {open ? "ซ่อนการกำหนดรายตัว" : "กำหนดรายตัว (ไม่บังคับ ใช้แทนค่าจากตลาด)"}
          </button>
          {open && (
            <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
              {symbols.map((s2) => (
                <label key={s2} className="flex items-center justify-between gap-2 text-sm">
                  <span>{s2}</span>
                  <span className="flex items-center gap-1">
                    <input
                      inputMode="decimal"
                      value={per[s2] ?? ""}
                      onChange={(ev) => setPer({ ...per, [s2]: ev.target.value })}
                      placeholder="—"
                      className="w-16 rounded-lg border border-border bg-background px-2 py-1 text-right tabular-nums"
                    />
                    <span className="text-xs text-muted-foreground">%</span>
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>
      )}

      {sectorNames.length > 0 && (
        <div className="mt-3">
          <button onClick={() => setOpenSec(!openSec)} className="text-xs text-muted-foreground underline">
            {openSec ? "ซ่อนการกำหนดรายอุตสาหกรรม" : "กำหนดรายอุตสาหกรรม (ไม่บังคับ ใช้แทนค่าจากตลาด แต่รายตัวยังมาก่อน)"}
          </button>
          {openSec && (
            <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3">
              {sectorNames.map((n) => (
                <label key={n} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate" title={n}>{n}</span>
                  <span className="flex shrink-0 items-center gap-1">
                    <input
                      inputMode="decimal"
                      value={perSec[n] ?? ""}
                      onChange={(ev) => setPerSec({ ...perSec, [n]: ev.target.value })}
                      placeholder="—"
                      className="w-16 rounded-lg border border-border bg-background px-2 py-1 text-right tabular-nums"
                    />
                    <span className="text-xs text-muted-foreground">%</span>
                  </span>
                </label>
              ))}
            </div>
          )}
          {openSec && (
            <p className="mt-1 text-xs text-muted-foreground">อุตสาหกรรมจาก Finnhub (ประมาณ ไม่ใช่ GICS)</p>
          )}
        </div>
      )}

      {msg && <p className="mt-3 text-xs text-rose-500">{msg}</p>}
      <button
        onClick={() => void run()}
        disabled={busy}
        className="mt-4 rounded-full bg-foreground px-4 py-1.5 text-xs font-medium text-background disabled:opacity-50"
      >
        {busy ? "กำลังคำนวณ…" : "คำนวณ"}
      </button>

      {res && !s && (
        <p className="mt-4 text-sm text-muted-foreground">
          ยังคำนวณไม่ได้ ({res.reason ?? res.status ?? "unavailable"})
        </p>
      )}
      {s && (
        <div className="mt-5 border-t border-border pt-4">
          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-muted-foreground">NAV ก่อน</dt>
              <dd className="mt-0.5 tabular-nums">{usd(s.nav_before)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">NAV ประมาณหลัง</dt>
              <dd className="mt-0.5 tabular-nums">{usd(s.nav_after)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">กำไร/ขาดทุนโดยประมาณ</dt>
              <dd className={`mt-0.5 tabular-nums ${tone(s.pnl)}`}>
                {usd(s.pnl)} ({pct(s.pnl_pct_nav, 2, true)})
              </dd>
            </div>
          </dl>
          <ul className="mt-4 space-y-2">
            {s.positions.map((p) => (
              <li key={p.symbol} className="flex items-center justify-between gap-2 text-sm">
                <span>
                  {p.symbol}
                  <span className="block text-xs text-muted-foreground">
                    {p.sector && p.sector !== "Unknown" ? `${p.sector} · ` : ""}
                    {p.basis.startsWith("explicit") ? "กำหนดเอง" : p.basis.startsWith("sector") ? "กำหนดตามอุตสาหกรรม" : "ผ่านค่า beta"}
                    {p.basis.includes("limited_sample") ? " · beta จากข้อมูลน้อย" : ""} · {pct(p.shock, 1, true)}
                  </span>
                </span>
                <span className={`tabular-nums ${tone(p.pnl)}`}>{usd(p.pnl)}</span>
              </li>
            ))}
          </ul>
          {(s.by_sector ?? []).length > 0 && (
            <div className="mt-4 border-t border-border pt-3">
              <p className="mb-2 text-sm text-muted-foreground">ผลขาดทุนแยกตามอุตสาหกรรม</p>
              <ul className="space-y-1.5">
                {(s.by_sector ?? []).map((b) => (
                  <li key={b.sector} className="flex items-center justify-between gap-2 text-sm">
                    <span>{b.sector === "Unknown" ? "ไม่ทราบอุตสาหกรรม" : b.sector}</span>
                    <span className={`tabular-nums ${tone(b.pnl)}`}>
                      {usd(b.pnl)} ({pct(b.pnl_pct_nav, 2, true)} ของ NAV)
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-muted-foreground">รวมเฉพาะตำแหน่งที่คำนวณได้ · อุตสาหกรรมจาก Finnhub (ประมาณ ไม่ใช่ GICS)</p>
            </div>
          )}
          {(s.unknown_sectors ?? []).length > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              ไม่มีอุตสาหกรรมนี้ในพอร์ต จึงไม่นับ: {(s.unknown_sectors ?? []).join(", ")}
            </p>
          )}
          {s.skipped.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              ข้าม: {s.skipped.map((k) => `${k.symbol} (${skipText(k.reason)})`).join(", ")}
            </p>
          )}
          {(s.unknown_symbols ?? []).length > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              ไม่ได้ถืออยู่ จึงไม่นับ: {(s.unknown_symbols ?? []).join(", ")}
            </p>
          )}
          {s.betas && Object.keys(s.betas).length > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              beta เทียบ S&amp;P 500:{" "}
              {Object.entries(s.betas)
                .map(([k, m]) => `${k} ${m.value == null ? "—" : m.value.toFixed(2)}`)
                .join(" · ")}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

/* ───────── Phase 3 UI: ที่มาของผลตอบแทน (บางส่วน) ───────── */
const ppFmt = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(2)} pp`;

function AttributionSection({ a }: { a: AttrRes | null }) {
  const title = <h2 className="text-base font-medium">ที่มาของผลตอบแทน</h2>;
  if (!a) {
    return (
      <Card>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">โหลดข้อมูลส่วนนี้ไม่สำเร็จ</p>
      </Card>
    );
  }
  const x = a.attribution;
  if (!x) {
    return (
      <Card>
        {title}
        <p className="mt-3 text-sm text-muted-foreground">ยังคำนวณไม่ได้ ({a.reason ?? a.status ?? "unavailable"})</p>
      </Card>
    );
  }
  const maxAbs = Math.max(...x.positions.map((p) => Math.abs(p.contribution)), Math.abs(x.execution_and_fees.value), 1e-9);
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {title}
        <Chip kind="warn">แบบบางส่วน: ส่วนร่วมรายตัวเท่านั้น</Chip>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        ไม่มีน้ำหนักรายอุตสาหกรรมของ S&amp;P 500 จึงไม่คำนวณ allocation/selection effect (Brinson) · หน่วยเป็น pp ของมูลค่าพอร์ตตอนเริ่มช่วง
      </p>
      <p className={`mt-3 text-2xl font-medium tabular-nums ${tone(x.portfolio_return)}`}>
        {pct(x.portfolio_return, 2, true)}
        <span className="ml-2 text-sm font-normal text-muted-foreground">ผลตอบแทนพอร์ต · {x.n_obs} วันทำการ</span>
      </p>

      <ul className="mt-4 space-y-3">
        {x.positions.map((p) => (
          <li key={p.symbol}>
            <div className="mb-1 flex items-center justify-between gap-2 text-sm">
              <span className="flex items-center gap-2">
                {p.symbol}
                {!p.held_now && <Chip>ขายแล้ว</Chip>}
              </span>
              <span className={`tabular-nums ${tone(p.contribution)}`}>{ppFmt(p.contribution)}</span>
            </div>
            <Bar value={Math.abs(p.contribution)} max={maxAbs} kind={p.contribution >= 0 ? "ok" : "bad"} />
            <p className="mt-1 text-xs text-muted-foreground tabular-nums">
              น้ำหนักเฉลี่ย {pct(p.avg_weight_nav, 1)} · ถือ {p.days_held} วัน
            </p>
          </li>
        ))}
        {x.execution && x.fees ? (
          <>
            <li>
              <div className="mb-1 flex items-center justify-between gap-2 text-sm" title={x.execution.note}>
                <span>ราคาที่ซื้อขายจริงเทียบราคาปิด</span>
                <span className={`tabular-nums ${tone(x.execution.value)}`}>{ppFmt(x.execution.value)}</span>
              </div>
              <Bar value={Math.abs(x.execution.value)} max={maxAbs} kind={x.execution.value >= 0 ? "ok" : "bad"} />
            </li>
            <li>
              <div className="mb-1 flex items-center justify-between gap-2 text-sm" title={x.fees.note}>
                <span>ค่าธรรมเนียม</span>
                <span className={`tabular-nums ${tone(x.fees.value)}`}>{ppFmt(x.fees.value)}</span>
              </div>
              <Bar value={Math.abs(x.fees.value)} max={maxAbs} kind={x.fees.value >= 0 ? "ok" : "bad"} />
            </li>
          </>
        ) : (
          <li>
            <div className="mb-1 flex items-center justify-between gap-2 text-sm" title={x.execution_and_fees.note}>
              <span>ราคาที่ซื้อขายจริงเทียบราคาปิด และค่าธรรมเนียม</span>
              <span className={`tabular-nums ${tone(x.execution_and_fees.value)}`}>{ppFmt(x.execution_and_fees.value)}</span>
            </div>
            <Bar value={Math.abs(x.execution_and_fees.value)} max={maxAbs} kind={x.execution_and_fees.value >= 0 ? "ok" : "bad"} />
          </li>
        )}
      </ul>

      <CashDragNote c={x.cash_drag} />

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-muted-foreground">
        <Chip kind={x.sum_check.ok ? "ok" : "bad"}>{x.sum_check.ok ? "ผลรวมตรงกับผลตอบแทนพอร์ต" : "ผลรวมไม่ตรง"}</Chip>
        <span className="tabular-nums">
          ส่วนร่วมรายตัว {ppFmt(x.sum_check.positions)} + ซื้อขาย/ค่าธรรมเนียม {ppFmt(x.sum_check.execution_and_fees)} ={" "}
          {ppFmt(x.sum_check.portfolio_return)}
        </span>
      </div>
    </Card>
  );
}

/* ───────── page ───────── */
export default function StockRiskPage({ getToken, apiBase }: Props) {
  const [ov, setOv] = useState<Overview | null>(null);
  const [ex, setEx] = useState<Exposure | null>(null);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [limitSrc, setLimitSrc] = useState<LimitsRes["source"] | null>(null);
  const [limitDefaults, setLimitDefaults] = useState<Limits | null>(null);
  const [ackBusy, setAckBusy] = useState<number | string | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [mx, setMx] = useState<MetricsRes | null>(null);
  const [perf, setPerf] = useState<PerfRes | null>(null);
  const [dc, setDc] = useState<Decomp | null>(null);
  const [attr, setAttr] = useState<AttrRes | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalMsg, setEvalMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const call = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const token = getToken();
      const r = await fetch(`${apiBase}/api/stocks/risk${path}`, {
        ...init,
        headers: {
          ...(init?.headers ?? {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!r.ok) throw new Error(r.status === 401 ? "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่" : r.status === 429 ? "เรียกถี่เกินไป กรุณารอสักครู่แล้วลองใหม่" : `เซิร์ฟเวอร์ตอบ ${r.status}`);
      return (await r.json()) as T;
    },
    [getToken, apiBase],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [o, e, l, a, m, pf, dcr, atr] = await Promise.all([
        call<Overview>("/overview"),
        call<Exposure>("/exposure"),
        call<LimitsRes>("/limits"),
        call<{ alerts: AlertRow[] }>("/alerts?limit=50"),
        call<MetricsRes>("/metrics").catch(() => null),
        call<PerfRes>("/performance").catch(() => null),
        call<Decomp>("/risk-decomposition").catch(() => null),
        call<AttrRes>("/attribution").catch(() => null),
      ]);
      setOv(o);
      setEx(e);
      setLimits(l.limits);
      setLimitSrc(l.source ?? null);
      setLimitDefaults(l.defaults ?? null);
      setAlerts(a.alerts);
      setMx(m);
      setPerf(pf);
      setDc(dcr);
      setAttr(atr);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, [call]);

  useEffect(() => {
    void load();
  }, [load]);

  const evaluate = async () => {
    setEvaluating(true);
    setEvalMsg(null);
    try {
      const r = await call<{ evaluated?: boolean; opened?: unknown[]; resolved?: unknown[]; skipped?: { reason: string }[] }>("/alerts/evaluate", { method: "POST" });
      if (r.evaluated === false) {
        setEvalMsg("ข้อมูลยังไม่พร้อมสำหรับการประเมิน จึงยังไม่เปิดหรือปิดการเตือนใด");
        return;
      }
      const sk = r.skipped ?? [];
      setEvalMsg(`เปิดใหม่ ${r.opened?.length ?? 0} · ปิดแล้ว ${r.resolved?.length ?? 0}${sk.length ? ` · ข้าม ${sk.length} รายการ (${sk.map((s) => s.reason).join("; ")})` : ""}`);
      await load();
    } catch (err) {
      setEvalMsg(err instanceof Error ? err.message : "ประเมินไม่สำเร็จ");
    } finally {
      setEvaluating(false);
    }
  };
  
  const startEdit = () => {
    const d: Record<string, string> = {};
    for (const l of LIMIT_META) {
      d[l.key] = limitDraft(l.key, limits?.[l.key] ?? null);
    }
    setDraft(d);
    setSaveMsg(null);
    setEditing(true);
  };

  const saveLimits = async () => {
    if (!limits) return;
    const body: Record<string, number | null> = {};
    for (const l of LIMIT_META) {
      const p = parseLimit(l.key, draft[l.key] ?? "");
      if (p === "bad") {
        setSaveMsg(`ค่าของ "${l.label}" ไม่ถูกต้อง`);
        return;
      }
      const cur = limits[l.key] ?? null;
      const same = p === cur || (p !== null && cur !== null && Math.abs(p - cur) < 1e-9);
      if (!same) body[l.key] = p;
    }
    if (Object.keys(body).length === 0) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setSaveMsg(null);
    try {
      await call("/limits", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setEditing(false);
      await load();
      await evaluate();
    } catch (err) {
      setSaveMsg(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ");
    } finally {
      setSaving(false);
    }
  };
  const fillDefaults = () => {
    if (!limitDefaults) return;
    const d: Record<string, string> = {};
    for (const l of LIMIT_META) d[l.key] = limitDraft(l.key, limitDefaults[l.key] ?? null);
    setDraft(d);
  };

  const acknowledge = async (id: number | string) => {
    setAckBusy(id);
    try {
      await call(`/alerts/${id}/acknowledge`, { method: "POST" });
      const now = new Date().toISOString();
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, acknowledged_at: now } : a)));
    } catch (err) {
      setEvalMsg(err instanceof Error ? err.message : "รับทราบไม่สำเร็จ");
    } finally {
      setAckBusy(null);
    }
  };

  if (loading && !ov) {
    return <div className="p-8 text-sm text-muted-foreground">กำลังโหลด Risk Center…</div>;
  }
  if (error && !ov) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <Card>
          <p className="flex items-center gap-2 text-rose-500">
            <AlertTriangle className="size-4" /> {error}
          </p>
          <button
            onClick={() => void load()}
            className="mt-4 rounded-full border border-border px-4 py-1.5 text-sm hover:bg-muted"
          >
            ลองใหม่
          </button>
        </Card>
      </div>
    );
  }
  if (!ov || !ex) return null;

  const c = ov.cards;
  const e = ex.exposure;
  const warnings = ov.meta.warnings ?? [];
  const activeList = alerts.filter((a) => a.status === "active");
  const activeN = activeList.length;
  const unackN = activeList.filter((a) => !a.acknowledged_at).length;
  const criticalN = activeList.filter((a) => a.severity === "critical").length;
  const top = [...e.positions].sort((a, b) => b.weight_nav - a.weight_nav);
  const maxW = limits?.max_single_weight ?? null;
  const mdd = c.max_drawdown;

  return (
    <div className="mx-auto max-w-[1160px] space-y-4 p-4 md:p-6">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-medium">
            <ShieldAlert className="size-6" /> Risk Center
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">หุ้นสหรัฐ · พอร์ตจำลอง · สกุลเงิน USD</p>
        </div>
        <div className="flex items-center gap-2">
          {ov.meta.as_of && <Chip>ข้อมูล ณ {ov.meta.as_of.slice(0, 10)}</Chip>}
          {activeN != null && (
            <Chip kind={activeN > 0 ? "bad" : "ok"}>
              {activeN > 0 ? <AlertTriangle className="size-3" /> : <CheckCircle2 className="size-3" />}
              การเตือนที่เปิดอยู่ {activeN}
              {activeN > 0 && ` (ยังไม่รับทราบ ${unackN}${criticalN ? ` · รุนแรง ${criticalN}` : ""})`}
            </Chip>
          )}
          <button
            onClick={() => void load()}
            disabled={loading}
            aria-label="รีเฟรช"
            className="rounded-full border border-border p-2 hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {/* data notes */}
      {warnings.length > 0 && (
        <div className="rounded-3xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-500">
            <AlertTriangle className="size-4" /> หมายเหตุเรื่องข้อมูล
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {warnings.map((w, i) => (
              <li key={`${w.code}-${i}`}>{WARNING_TEXT(w)}</li>
            ))}
          </ul>
        </div>
      )}

      {/* metric grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Card className="md:col-span-2">
          <p className="text-sm text-muted-foreground">มูลค่าพอร์ต (NAV)</p>
          <p className="mt-3 text-4xl font-medium tabular-nums">{usd(e.nav)}</p>
          <div className="mt-5 flex justify-between border-t border-border pt-3 text-sm">
            <span className="text-muted-foreground">
              เงินสด <span className="text-foreground tabular-nums">{usd(e.cash)}</span> ({pct(e.cash_weight, 1)})
            </span>
            <span className="text-muted-foreground">
              หุ้น <span className="text-foreground tabular-nums">{usd(e.equity_value)}</span>
            </span>
          </div>
        </Card>
        <ReturnCard title="ผลตอบแทนพอร์ต" m={c.portfolio_return} note={ov.meta.period?.label} help="portfolio_return" />
        <ReturnCard title={ov.meta.benchmark?.name ?? "S&P 500"} m={c.benchmark_return} note="ดัชนีราคา (^GSPC)" help="benchmark_return" />

        <ReturnCard title="ผลตอบแทนส่วนเกิน" m={c.active_return} note="พอร์ต − ดัชนี" help="active_return" />
        {c.volatility?.value == null ? (
          <PendingCard title="ความผันผวน (รายปี)" m={c.volatility} need={MIN_VOL} help="volatility" />
        ) : (
          <Card>
            <p className="text-sm text-muted-foreground">
              ความผันผวน (รายปี)
              <InfoTip k="volatility" />
            </p>
            <p className="mt-3 text-3xl font-medium tabular-nums">{fmtMetric(c.volatility)}</p>
          </Card>
        )}
        {c.sharpe?.value == null ? (
          <PendingCard title="Sharpe ratio" m={c.sharpe} need={MIN_SHARPE} help="sharpe" />
        ) : (
          <Card>
            <p className="text-sm text-muted-foreground">
              Sharpe ratio
              <InfoTip k="sharpe" />
            </p>
            <p className="mt-3 text-3xl font-medium tabular-nums">{fmtMetric(c.sharpe)}</p>
          </Card>
        )}
        <Card>
          <p className="text-sm text-muted-foreground">Drawdown สูงสุด</p>
          <p className={`mt-3 text-3xl font-medium tabular-nums ${tone(mdd?.value)}`}>{fmtMetric(mdd)}</p>
          {mdd?.status === "limited_sample" && (
            <div className="mt-3">
              <Chip kind="warn">ตัวอย่างน้อย (มี {mdd.n_obs ?? 0} วัน)</Chip>
            </div>
          )}
        </Card>
      </div>
      <PerformanceSection p={perf} />
      <RiskAdjustedSection m={mx} />
      <RollingSection p={perf} />
      <TailSection m={mx} />
      <LossDistributionSection p={perf} tail={mx?.tail} />
      <DecompositionSection d={dc} />
      <AttributionSection a={attr} />
      <SectorContributionSection rows={attr?.by_sector} note={attr?.sector_classification} />
      {attr?.attribution && <PnlSection p={attr.pnl} />}
      <StressSection
        call={call}
        symbols={top.map((p) => p.symbol)}
        sectorNames={(e.sectors ?? []).map((x) => x.sector).filter((n) => n !== "Unknown" && n !== "n/a")}
      />
      
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[7fr_5fr]">
        {/* concentration */}
        <Card>
          <h2 className="text-base font-medium">
            ความกระจุกตัว
            <InfoTip k="hhi" />
          </h2>
          <div className="mt-4 space-y-3">
            {top.map((p) => (
              <div key={p.symbol}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{p.symbol}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {usd(p.market_value)} · {pct(p.weight_nav, 1)}
                  </span>
                </div>
                <Bar value={p.weight_nav} kind={maxW != null && p.weight_nav > maxW ? "bad" : "muted"} />
              </div>
            ))}
            <div>
              <div className="mb-1 flex justify-between text-sm">
                <span>เงินสด</span>
                <span className="tabular-nums text-muted-foreground">
                  {usd(e.cash)} · {pct(e.cash_weight, 1)}
                </span>
              </div>
              <Bar value={e.cash_weight} kind="ok" />
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2 border-t border-border pt-3">
            <Chip>HHI {fmtMetric(e.hhi)}</Chip>
            <Chip>จำนวนหุ้นที่เทียบเท่า {fmtMetric(e.effective_n)}</Chip>
            <Chip>ตัวใหญ่สุด {fmtMetric(e.top1)}</Chip>
          </div>
          {e.sectors && e.sectors.length > 0 && (
            <div className="mt-4 border-t border-border pt-3">
              <p className="mb-2 text-sm text-muted-foreground">อุตสาหกรรม (สัดส่วนของ NAV)</p>
              <div className="space-y-2">
                {e.sectors.map((sc) => {
                  const unk = sc.sector === "Unknown" || sc.sector === "n/a";
                  return (
                    <div key={sc.sector}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span className={unk ? "text-muted-foreground" : ""}>{unk ? "ไม่ทราบอุตสาหกรรม" : sc.sector}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {pct(sc.weight_nav, 1)}{sc.market_value != null ? ` · ${usd(sc.market_value)}` : ""}
                        </span>
                      </div>
                      <Bar value={sc.weight_nav} kind={unk ? "muted" : "ok"} />
                    </div>
                  );
                })}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                ค่าประมาณจาก Finnhub ไม่ใช่มาตรฐาน GICS · ตัวที่ไม่ทราบอุตสาหกรรมไม่ถูกนับรวมในกฎ sector
              </p>
            </div>
          )}
        </Card>

        {/* limits & alerts */}
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="text-base font-medium">ลิมิตและการเตือน</h2>
            <button
              onClick={() => void evaluate()}
              disabled={evaluating}
              className="rounded-full border border-border px-3 py-1 text-xs hover:bg-muted disabled:opacity-50"
            >
              {evaluating ? "กำลังประเมิน…" : "ประเมินตอนนี้"}
            </button>
          </div>
          {evalMsg && <p className="mt-2 text-xs text-muted-foreground">{evalMsg}</p>}
                    {editing ? (
            <div className="mt-4 space-y-3 rounded-2xl border border-border p-4">
              {LIMIT_META.map((l) => (
                <div key={l.key} className="flex items-center justify-between gap-3 text-sm">
                  <label htmlFor={`lim-${l.key}`} title={l.hint}>
                    {l.label}
                  </label>
                  <span className="flex items-center gap-1.5">
                    <input
                      id={`lim-${l.key}`}
                      inputMode="decimal"
                      value={draft[l.key] ?? ""}
                      onChange={(ev) => setDraft({ ...draft, [l.key]: ev.target.value })}
                      placeholder="ไม่ตั้ง"
                      className="w-24 rounded-lg border border-border bg-background px-2 py-1 text-right tabular-nums"
                    />
                    <span className="w-8 text-xs text-muted-foreground">{isDecimalLimit(l.key) ? "0–1" : "%"}</span>
                  </span>
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                เว้นว่าง = ไม่ตั้งลิมิตข้อนั้น · HHI ใส่เป็นทศนิยม 0–1 (เช่น 0.5) · ข้ออื่นใส่เป็นเปอร์เซ็นต์ (เช่น 20)
              </p>
              {saveMsg && <p className="text-xs text-rose-500">{saveMsg}</p>}
              <div className="flex gap-2">
                {limitDefaults && (
                  <button
                    onClick={fillDefaults}
                    disabled={saving}
                    title="เติมค่าเริ่มต้นของระบบ (ตัวอย่างทั่วไป ไม่ใช่คำแนะนำการลงทุน) ยังไม่บันทึกจนกว่าจะกดบันทึก"
                    className="rounded-full border border-border px-4 py-1.5 text-xs hover:bg-muted"
                  >
                    เติมค่าเริ่มต้น
                  </button>
                )}
                <button
                  onClick={() => void saveLimits()}
                  disabled={saving}
                  className="rounded-full bg-foreground px-4 py-1.5 text-xs font-medium text-background disabled:opacity-50"
                >
                  {saving ? "กำลังบันทึก…" : "บันทึกและประเมิน"}
                </button>
                <button
                  onClick={() => {
                    setEditing(false);
                    setSaveMsg(null);
                  }}
                  disabled={saving}
                  className="rounded-full border border-border px-4 py-1.5 text-xs hover:bg-muted"
                >
                  ยกเลิก
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={startEdit}
              className="mt-3 rounded-full border border-border px-3 py-1 text-xs hover:bg-muted"
            >
              ตั้งค่าลิมิต
            </button>
          )}

          <div className="mt-4 space-y-3">
            {LIMIT_META.map((l) => {
              const v = limits?.[l.key] ?? null;
              return (
                <div key={l.key} className="flex items-center justify-between gap-3 text-sm" title={l.hint}>
                  <span>{l.label}</span>
                  <span className="flex items-center gap-1.5">
                    {limitSrc?.[l.key] === "default" && <Chip>ค่าเริ่มต้น</Chip>}
                    {v == null ? <Chip>ยังไม่ตั้ง</Chip> : <Chip kind="ok">{limitText(l.key, v)}</Chip>}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="mt-5 border-t border-border pt-3">
            <p className="mb-2 text-sm text-muted-foreground">ประวัติการเตือน</p>
            {alerts.length === 0 ? (
              <p className="text-sm text-muted-foreground">ยังไม่มีการเตือน</p>
            ) : (
              <ul className="space-y-2">
                {alerts.map((a) => {
                  const active = a.status === "active";
                  const sev = SEVERITY_META[a.severity ?? "warning"] ?? SEVERITY_META.warning;
                  const missing = a.detail?.missing ?? [];
                  return (
                    <li key={a.id} className="flex items-start justify-between gap-2 text-sm">
                      <span>
                        {ALERT_LABEL[a.alert_type] ?? a.alert_type}
                        {a.sector ? ` · ${a.sector}` : ""}
                        {a.symbol && (
                          <>
                            {" · "}
                            <button
                              type="button"
                              onClick={() => openCompany(a.symbol as string)}
                              className="underline underline-offset-2 hover:text-foreground"
                              title={`เปิดหน้า ${a.symbol}`}
                            >
                              {a.symbol}
                            </button>
                          </>
                        )}
                        <span className="block text-xs text-muted-foreground tabular-nums">
                          {a.observed_value != null && a.threshold != null
                            ? a.alert_type === "stale_data"
                              ? `เก่า ${alertVal(a.alert_type, a.observed_value)} (เกณฑ์ ${alertVal(a.alert_type, a.threshold)}) · `
                              : `${alertVal(a.alert_type, a.observed_value)} / ลิมิต ${alertVal(a.alert_type, a.threshold)} · `
                            : ""}
                          {a.opened_at ? a.opened_at.slice(0, 10) : ""}
                        </span>
                        {a.alert_type === "stale_data" && missing.length > 0 && (
                          <span className="block text-xs text-muted-foreground">
                            ข้อมูลไม่ครบ: {missing.map((m) => m.symbol ?? m.code).join(", ")}
                          </span>
                        )}
                        {a.alert_type === "sector_weight" && (
                          <span className="block text-xs text-muted-foreground">sector จาก Finnhub (ประมาณ ไม่ใช่ GICS)</span>
                        )}
                      </span>
                      <span className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
                        {active && <Chip kind={sev.kind}>{sev.label}</Chip>}
                        {active && a.acknowledged_at ? (
                          <Chip>รับทราบแล้ว</Chip>
                        ) : active ? (
                          <button
                            onClick={() => void acknowledge(a.id)}
                            disabled={ackBusy === a.id}
                            className="rounded-full border border-border px-2.5 py-0.5 text-xs hover:bg-muted disabled:opacity-50"
                          >
                            {ackBusy === a.id ? "กำลังบันทึก…" : "รับทราบ"}
                          </button>
                        ) : null}
                        <Chip kind={active ? "bad" : "ok"}>{active ? "เปิดอยู่" : "ปิดแล้ว"}</Chip>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Card>
      </div>

      <p className="px-1 text-xs text-muted-foreground">
        คำนวณจากบัญชีจำลองแบบอ่านอย่างเดียว · ผลตอบแทนเทียบดัชนีราคา S&amp;P 500 (ไม่รวมเงินปันผล) · ตัวชี้วัดที่ข้อมูลไม่พอจะไม่แสดงตัวเลข
      </p>
    </div>
  );
}
