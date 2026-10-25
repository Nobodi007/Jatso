import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldAlert } from "lucide-react";

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
    sectors?: { sector: string; weight_nav: number }[];
  };
  meta?: { sector_classification?: string };
}
interface Limits {
  max_drawdown: number | null;
  max_single_weight: number | null;
  max_hhi: number | null;
  min_cash_weight: number | null;
}
interface AlertRow {
  id: number | string;
  alert_type: string;
  symbol?: string | null;
  threshold?: number | null;
  observed_value?: number | null;
  status: string;
  opened_at?: string;
  resolved_at?: string | null;
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
];

/** แปลงข้อความที่ผู้ใช้กรอกเป็นค่าที่ API ต้องการ: null = ไม่ตั้ง, "bad" = ค่าผิด */
const parseLimit = (key: keyof Limits, s: string): number | null | "bad" => {
  const t = s.trim();
  if (t === "") return null;
  const n = Number(t);
  if (!Number.isFinite(n)) return "bad";
  const v = key === "max_hhi" ? n : Number((n / 100).toFixed(6));
  const ok = key === "min_cash_weight" ? v >= 0 && v < 1 : v > 0 && v <= 1;
  return ok ? v : "bad";
};
const ALERT_LABEL: Record<string, string> = {
  drawdown: "Drawdown เกินลิมิต",
  single_weight: "หุ้นตัวเดียวเกินลิมิต",
  hhi: "HHI เกินลิมิต",
  low_cash: "เงินสดต่ำกว่าลิมิต",
};
const alertVal = (type: string, v: number) => (type === "hhi" ? v.toFixed(2) : pct(v, 2));

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
function PendingCard({ title, m, need }: { title: string; m?: Metric; need: number }) {
  const n = m?.n_obs ?? 0;
  return (
    <Card className="border-dashed">
      <p className="text-sm text-muted-foreground">{title}</p>
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

function ReturnCard({ title, m, note }: { title: string; m?: Metric; note?: string }) {
  const v = m?.value ?? null;
  const grad =
    v == null
      ? ""
      : v < 0
        ? "bg-gradient-to-l from-rose-500/10 to-card to-80%"
        : "bg-gradient-to-l from-emerald-500/10 to-card to-80%";
  return (
    <Card className={grad}>
      <p className="text-sm text-muted-foreground">{title}</p>
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
  const rows: [string, string][] = [
    ["Drawdown ปัจจุบัน", show(t.current_drawdown)],
    ["VaR 95% (1 วัน)", show(t.var_95)],
    ["ES 95% (1 วัน)", show(t.es_95)],
    ["Downside deviation (รายปี)", show(t.downside_deviation)],
    ["Downside beta", show(m.risk_adjusted?.downside_beta)],
  ];
  if (enough) {
    rows.push(
      ["ช่วงจมน้ำนานสุด", t.longest_underwater_trading_days != null ? `${t.longest_underwater_trading_days} วันทำการ` : "—"],
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
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="text-muted-foreground">{k}</dt>
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

function RaItem({ label, m }: { label: string; m: Metric }) {
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
      <dt className="text-muted-foreground">{label}</dt>
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
          <RaItem key={i.key} label={i.label} m={i.metric} />
        ))}
      </dl>
      <p className="mt-4 text-xs text-muted-foreground">วางเมาส์บนชื่อตัวชี้วัดเพื่อดูสูตร · ตัวที่ข้อมูลไม่พอจะไม่แสดงตัวเลข</p>
    </Card>
  );
}
/* ───────── page ───────── */
export default function StockRiskPage({ getToken, apiBase }: Props) {
  const [ov, setOv] = useState<Overview | null>(null);
  const [ex, setEx] = useState<Exposure | null>(null);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [mx, setMx] = useState<MetricsRes | null>(null);
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
      const [o, e, l, a, m] = await Promise.all([
        call<Overview>("/overview"),
        call<Exposure>("/exposure"),
        call<{ limits: Limits }>("/limits"),
        call<{ alerts: AlertRow[] }>("/alerts?limit=20"),
        call<MetricsRes>("/metrics").catch(() => null),
      ]);
      setOv(o);
      setEx(e);
      setLimits(l.limits);
      setAlerts(a.alerts);
      setMx(m);
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
      const v = limits?.[l.key] ?? null;
      d[l.key] = v == null ? "" : String(l.key === "max_hhi" ? v : Number((v * 100).toFixed(2)));
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
  const activeN = alerts.filter((a) => a.status === "active").length;
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
        <ReturnCard title="ผลตอบแทนพอร์ต" m={c.portfolio_return} note={ov.meta.period?.label} />
        <ReturnCard title={ov.meta.benchmark?.name ?? "S&P 500"} m={c.benchmark_return} note="ดัชนีราคา (^GSPC)" />

        <ReturnCard title="ผลตอบแทนส่วนเกิน" m={c.active_return} note="พอร์ต − ดัชนี" />
        {c.volatility?.value == null ? (
          <PendingCard title="ความผันผวน (รายปี)" m={c.volatility} need={MIN_VOL} />
        ) : (
          <Card>
            <p className="text-sm text-muted-foreground">ความผันผวน (รายปี)</p>
            <p className="mt-3 text-3xl font-medium tabular-nums">{fmtMetric(c.volatility)}</p>
          </Card>
        )}
        {c.sharpe?.value == null ? (
          <PendingCard title="Sharpe ratio" m={c.sharpe} need={MIN_SHARPE} />
        ) : (
          <Card>
            <p className="text-sm text-muted-foreground">Sharpe ratio</p>
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
      <RiskAdjustedSection m={mx} />
      <TailSection m={mx} />
      
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[7fr_5fr]">
        {/* concentration */}
        <Card>
          <h2 className="text-base font-medium">ความกระจุกตัว</h2>
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
            <p className="mt-3 text-xs text-muted-foreground">
              อุตสาหกรรม (สัดส่วนของ NAV): {e.sectors.map((s) => `${s.sector} ${pct(s.weight_nav, 1)}`).join(" · ")}
              {" "}(ค่าประมาณจาก Finnhub ไม่ใช่มาตรฐาน GICS)
            </p>
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
                    <span className="w-8 text-xs text-muted-foreground">{l.key === "max_hhi" ? "0–1" : "%"}</span>
                  </span>
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                เว้นว่าง = ไม่ตั้งลิมิตข้อนั้น · HHI ใส่เป็นทศนิยม 0–1 (เช่น 0.5) · ข้ออื่นใส่เป็นเปอร์เซ็นต์ (เช่น 20)
              </p>
              {saveMsg && <p className="text-xs text-rose-500">{saveMsg}</p>}
              <div className="flex gap-2">
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
                  {v == null ? <Chip>ยังไม่ตั้ง</Chip> : <Chip kind="ok">{l.key === "max_hhi" ? v.toFixed(2) : pct(v, 0)}</Chip>}
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
                {alerts.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 text-sm">
                    <span>
                      {ALERT_LABEL[a.alert_type] ?? a.alert_type}
                      {a.symbol ? ` · ${a.symbol}` : ""}
                      <span className="block text-xs text-muted-foreground tabular-nums">
                        {a.observed_value != null && a.threshold != null
                          ? `${alertVal(a.alert_type, a.observed_value)} / ลิมิต ${alertVal(a.alert_type, a.threshold)} · `
                          : ""}
                        {a.opened_at ? a.opened_at.slice(0, 10) : ""}
                      </span>
                    </span>
                    <Chip kind={a.status === "active" ? "bad" : "ok"}>{a.status === "active" ? "เปิดอยู่" : "ปิดแล้ว"}</Chip>
                  </li>
                ))}
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
