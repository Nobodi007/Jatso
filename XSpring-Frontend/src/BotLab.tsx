import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

/* =========================================================
   BotLab — หน้าบอทเทรดใน Quant Lab
   ใช้: <BotLab api={botApi} />
   ดีไซน์: ใช้ Tailwind token เดียวกับหน้าอื่นของเว็บ (bg-card, border, text-muted-foreground ฯลฯ)
   ตรรกะ/การเรียก API เหมือนเวอร์ชันก่อนทุกประการ
   ========================================================= */

export type BotApi = (
  path: string,
  init?: { method?: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown },
) => Promise<any>;

type Operand =
  | { ind: "price" }
  | { ind: "sma" | "ema" | "rsi" | "roc"; period: number }
  | { value: number };
type Cond = { left: Operand; op: string; right: Operand };
type Group = { op: "all" | "any"; conds: Cond[] };
type Spec = {
  asset: string;
  entry: Group;
  exit: Group & { take_profit_pct: number | null; stop_loss_pct: number | null };
  sizing: { type: "pct_of_cash" | "fixed_thb"; value: number };
};
type Template = { key: string; name: string; desc: string; spec: Spec; rule_text: string };
type Bot = {
  id: string;
  name: string;
  rule_text: string;
  enabled: boolean;
  dry_run: boolean;
  created_at?: string;
};
type Run = { bar: string | null; action: string; reason: string | null; pnl_pct: number | null; created_at: string };
type BtResult = {
  asset: string;
  rule_text: string;
  bars: number;
  from: string;
  to: string;
  capital: number;
  final: number | null;
  return_pct: number | null;
  buy_hold_return_pct: number | null;
  max_dd: number | null;
  n_trades: number;
  n_closed: number;
  win_rate: number | null;
  holding_at_end: boolean;
  equity: { date: string; value: number | null; buy_hold: number | null }[];
  trades: { date: string; side: string; price: number | null; amount_thb: number | null; reason: string; pnl_pct: number | null }[];
  warnings: string[];
};

const ASSETS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "HBAR", "LINK", "XLM"];
const OPS: [string, string][] = [
  [">", "มากกว่า"],
  ["<", "น้อยกว่า"],
  ["crosses_above", "ตัดขึ้นเหนือ"],
  ["crosses_below", "ตัดลงต่ำกว่า"],
];
const KINDS: [string, string][] = [
  ["price", "ราคา"],
  ["sma", "SMA"],
  ["ema", "EMA"],
  ["rsi", "RSI"],
  ["roc", "% เปลี่ยนแปลง (ROC)"],
  ["value", "ตัวเลข"],
];
const DEFAULT_PERIOD: Record<string, number> = { sma: 20, ema: 20, rsi: 14, roc: 7 };
const MAX_CONDS = 6;

const EMPTY_SPEC: Spec = {
  asset: "BTC",
  entry: { op: "all", conds: [{ left: { ind: "rsi", period: 14 }, op: "<", right: { value: 30 } }] },
  exit: { op: "any", conds: [], take_profit_pct: null, stop_loss_pct: 10 },
  sizing: { type: "pct_of_cash", value: 20 },
};

/* ---------- helpers ---------- */
const kindOf = (o: Operand): string => ("value" in o ? "value" : o.ind);

function makeOperand(kind: string, prev?: Operand): Operand {
  if (kind === "value") return { value: prev && "value" in prev ? prev.value : 0 };
  if (kind === "price") return { ind: "price" };
  const period = prev && "period" in prev ? prev.period : DEFAULT_PERIOD[kind];
  return { ind: kind as "sma" | "ema" | "rsi" | "roc", period };
}

const errMsg = (e: unknown): string => {
  const m = e instanceof Error ? e.message : String(e);
  return m || "เกิดข้อผิดพลาด";
};
const fmtThb = (n: number | null | undefined) =>
  n == null ? "-" : n.toLocaleString("th-TH", { maximumFractionDigits: 0 });
const fmtPct = (n: number | null | undefined) =>
  n == null ? "-" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
const colorOf = (n: number | null | undefined) =>
  n == null || n === 0 ? "" : n > 0 ? "text-emerald-500" : "text-red-500";

const ACTION_TH: Record<string, { label: string; cls: string }> = {
  buy: { label: "ซื้อ", cls: "bg-emerald-500/10 text-emerald-500" },
  sell: { label: "ขาย", cls: "bg-red-500/10 text-red-500" },
  hold: { label: "ถือ", cls: "bg-muted text-muted-foreground" },
};

/* ---------- class ที่ใช้ซ้ำ (ตรงกับดีไซน์หน้าอื่น) ---------- */
const inputBase =
  "h-10 rounded-lg border bg-background px-3 text-sm outline-none transition-colors focus:border-primary/60 disabled:opacity-50";
const btnGhost =
  "rounded-lg border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50";
const btnPrimary =
  "rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40";
const btnSmall =
  "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50";

/* ---------- ชิ้นส่วน UI ---------- */
function Card({
  step,
  title,
  subtitle,
  right,
  children,
}: {
  step?: number;
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border bg-card">
      <div className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="flex items-start gap-3">
          {step !== undefined && (
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
              {step}
            </span>
          )}
          <div>
            <h3 className="font-semibold">{title}</h3>
            {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
        </div>
        {right}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Field({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function NumInput({
  value,
  onChange,
  suffix,
  min,
  title,
  className = "",
  placeholder,
}: {
  value: number | string;
  onChange: (v: string) => void;
  suffix?: string;
  min?: number;
  title?: string;
  className?: string;
  placeholder?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <input
        type="number"
        min={min}
        value={value}
        title={title}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={`${inputBase} w-full ${suffix ? "pr-12" : ""}`}
      />
      {suffix && (
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
          {suffix}
        </span>
      )}
    </div>
  );
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onChange}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? "bg-emerald-500" : "bg-muted"}`}
    >
      <span
        className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all ${checked ? "left-[22px]" : "left-0.5"}`}
      />
    </button>
  );
}

/* ---------- ตัวแก้ operand / กลุ่มเงื่อนไข ---------- */
function OperandEditor({ o, onChange }: { o: Operand; onChange: (o: Operand) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select value={kindOf(o)} onChange={(e) => onChange(makeOperand(e.target.value, o))} className={`${inputBase} cursor-pointer`}>
        {KINDS.map(([k, label]) => (
          <option key={k} value={k}>{label}</option>
        ))}
      </select>
      {"value" in o && (
        <NumInput className="w-28" value={o.value} onChange={(v) => onChange({ value: Number(v) })} />
      )}
      {"period" in o && (
        <NumInput
          className="w-20"
          min={1}
          value={o.period}
          title="period (จำนวนแท่ง)"
          onChange={(v) => onChange({ ...o, period: Math.round(Number(v)) })}
        />
      )}
    </div>
  );
}

function GroupEditor({ g, onChange, label, hint }: { g: Group; onChange: (g: Group) => void; label: string; hint: string }) {
  const setCond = (i: number, c: Cond) => onChange({ ...g, conds: g.conds.map((x, j) => (j === i ? c : x)) });
  return (
    <div className="rounded-xl border bg-background/40 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">{label}</div>
          <div className="text-xs text-muted-foreground">{hint}</div>
        </div>
        <select
          value={g.op}
          className={`${inputBase} cursor-pointer`}
          onChange={(e) => onChange({ ...g, op: e.target.value as "all" | "any" })}
        >
          <option value="all">ทุกข้อ (และ)</option>
          <option value="any">ข้อใดข้อหนึ่ง (หรือ)</option>
        </select>
      </div>

      <div className="space-y-2">
        {g.conds.length === 0 && (
          <div className="rounded-lg border border-dashed px-3 py-3 text-center text-xs text-muted-foreground">
            ยังไม่มีเงื่อนไข
          </div>
        )}
        {g.conds.map((c, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-2.5">
            <OperandEditor o={c.left} onChange={(left) => setCond(i, { ...c, left })} />
            <select value={c.op} className={`${inputBase} cursor-pointer`} onChange={(e) => setCond(i, { ...c, op: e.target.value })}>
              {OPS.map(([k, t]) => (
                <option key={k} value={k}>{t}</option>
              ))}
            </select>
            <OperandEditor o={c.right} onChange={(right) => setCond(i, { ...c, right })} />
            <button
              type="button"
              className={`${btnSmall} ml-auto text-red-500`}
              onClick={() => onChange({ ...g, conds: g.conds.filter((_, j) => j !== i) })}
            >
              ลบ
            </button>
          </div>
        ))}
      </div>

      {g.conds.length < MAX_CONDS && (
        <button
          type="button"
          className={`${btnGhost} mt-3`}
          onClick={() =>
            onChange({ ...g, conds: [...g.conds, { left: { ind: "price" }, op: ">", right: { ind: "sma", period: 50 } }] })
          }
        >
          + เพิ่มเงื่อนไข
        </button>
      )}
    </div>
  );
}

/* ---------- กราฟ equity (SVG ล้วน) ---------- */
function EquityChart({ pts }: { pts: BtResult["equity"] }) {
  const W = 720, H = 240, PX = 8, PY = 10;
  if (pts.length < 2) return null;
  const a = pts.map((p) => Number(p.value ?? 0));
  const b = pts.map((p) => Number(p.buy_hold ?? 0));
  const all = [...a, ...b];
  const lo = Math.min(...all), hi = Math.max(...all);
  const span = hi - lo || 1;
  const x = (i: number, n: number) => PX + (i / (n - 1)) * (W - 2 * PX);
  const y = (v: number) => H - PY - ((v - lo) / span) * (H - 2 * PY);
  const path = (arr: number[]) => arr.map((v, i) => `${x(i, arr.length).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${PX},${H - PY} ${path(a)} ${(W - PX).toFixed(1)},${H - PY}`;
  const grid = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-emerald-500" /> บอท
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0 w-4 border-t-2 border-dashed border-muted-foreground" /> ถือเฉยๆ
        </span>
      </div>
      <div className="rounded-lg border bg-background/40 p-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full text-muted-foreground">
          {grid.map((g) => (
            <line
              key={g}
              x1={PX} x2={W - PX}
              y1={PY + g * (H - 2 * PY)} y2={PY + g * (H - 2 * PY)}
              stroke="currentColor" strokeOpacity={0.15} strokeWidth={1}
            />
          ))}
          <polygon points={area} fill="#10b981" fillOpacity={0.08} />
          <polyline points={path(b)} fill="none" stroke="currentColor" strokeOpacity={0.7} strokeWidth={1.5} strokeDasharray="5 4" />
          <polyline points={path(a)} fill="none" stroke="#10b981" strokeWidth={2} strokeLinejoin="round" />
          <text x={PX + 2} y={PY + 10} fontSize={11} fill="currentColor">฿{fmtThb(hi)}</text>
          <text x={PX + 2} y={H - PY - 4} fontSize={11} fill="currentColor">฿{fmtThb(lo)}</text>
        </svg>
      </div>
      <div className="mt-1.5 flex justify-between text-xs text-muted-foreground">
        <span>{pts[0].date}</span>
        <span>{pts[pts.length - 1].date}</span>
      </div>
    </div>
  );
}

/* =========================================================
   หน้าหลัก
   ========================================================= */
export default function BotLab({ api }: { api: BotApi }) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [spec, setSpec] = useState<Spec>(EMPTY_SPEC);
  const [ruleText, setRuleText] = useState("");
  const [ruleErr, setRuleErr] = useState("");

  const [capital, setCapital] = useState(100000);
  const [bt, setBt] = useState<BtResult | null>(null);
  const [btBusy, setBtBusy] = useState(false);
  const [btErr, setBtErr] = useState("");

  const [name, setName] = useState("");
  const [bots, setBots] = useState<Bot[]>([]);
  const [maxBots, setMaxBots] = useState(3);
  const [msg, setMsg] = useState("");
  const [runsFor, setRunsFor] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);

  const loadBots = useCallback(async () => {
    try {
      const r = await api("/api/bots");
      setBots(r.bots || []);
      setMaxBots(r.max_bots || 3);
    } catch (e) {
      setMsg(errMsg(e));
    }
  }, [api]);

  useEffect(() => {
    api("/api/bots/templates").then((r) => setTemplates(r.templates || [])).catch((e) => setMsg(errMsg(e)));
    loadBots();
  }, [api, loadBots]);

  // แปลงกฎเป็นประโยคไทย (หน่วงเล็กน้อยกันยิงถี่)
  useEffect(() => {
    let dead = false;
    const t = setTimeout(async () => {
      try {
        const r = await api("/api/bots/preview", { method: "POST", body: { spec } });
        if (!dead) { setRuleText(r.rule_text || ""); setRuleErr(""); }
      } catch (e) {
        if (!dead) { setRuleText(""); setRuleErr(errMsg(e)); }
      }
    }, 500);
    return () => { dead = true; clearTimeout(t); };
  }, [api, spec]);

  const runBacktest = async () => {
    setBtBusy(true); setBtErr(""); setBt(null);
    try {
      setBt(await api("/api/bots/backtest", { method: "POST", body: { spec, capital } }));
    } catch (e) {
      setBtErr(errMsg(e));
    } finally {
      setBtBusy(false);
    }
  };

  const saveBot = async () => {
    setMsg("");
    try {
      await api("/api/bots", { method: "POST", body: { name: name.trim() || `บอท ${spec.asset}`, spec } });
      setName("");
      setMsg("บันทึกบอทแล้ว (โหมดทดลอง ปิดอยู่)");
      loadBots();
    } catch (e) {
      setMsg(errMsg(e));
    }
  };

  const toggleBot = async (b: Bot) => {
    try {
      await api(`/api/bots/${b.id}`, { method: "PATCH", body: { enabled: !b.enabled } });
      loadBots();
    } catch (e) { setMsg(errMsg(e)); }
  };

  const setMode = async (b: Bot, mode: "live" | "dry") => {
  if (mode === "live" && !window.confirm(`เปลี่ยนบอท "${b.name}" เป็นโหมดจริง?\nบอทจะซื้อขายจริงในพอร์ตของคุณ (สวิตช์จะถูกปิดไว้ก่อน)`)) return;
  try {
    await api(`/api/bots/${b.id}/mode`, { method: "POST", body: { mode, confirm: true } });
    loadBots();
  } catch (e) { setMsg(errMsg(e)); }
};

  const showRuns = async (b: Bot) => {
    if (runsFor === b.id) { setRunsFor(null); return; }
    try {
      const r = await api(`/api/bots/${b.id}/runs`);
      setRuns(r.runs || []);
      setRunsFor(b.id);
    } catch (e) { setMsg(errMsg(e)); }
  };

  const numOrNull = (v: string) => (v === "" ? null : Number(v));
  const canSave = !ruleErr && bots.length < maxBots;
  const tradesShown = useMemo(() => (bt ? [...bt.trades].reverse().slice(0, 30) : []), [bt]);

  const stats: { label: string; value: string; cls?: string }[] = bt
    ? [
        { label: "เงินสุดท้าย", value: `฿${fmtThb(bt.final)}` },
        { label: "ผลตอบแทนบอท", value: fmtPct(bt.return_pct), cls: colorOf(bt.return_pct) },
        { label: "ถือเฉยๆ", value: fmtPct(bt.buy_hold_return_pct), cls: colorOf(bt.buy_hold_return_pct) },
        { label: "ขาดทุนสูงสุด", value: fmtPct(bt.max_dd), cls: colorOf(bt.max_dd) },
        { label: "รอบที่ปิดแล้ว", value: String(bt.n_closed) },
        { label: "ชนะ", value: bt.win_rate == null ? "-" : `${bt.win_rate.toFixed(0)}%` },
      ]
    : [];

  return (
    <div className="space-y-6">
      {/* หัวข้อ */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xl font-bold">บอทเทรด</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            ประกอบกฎซื้อขาย ทดสอบย้อนหลังด้วยราคาจริงของเว็บ แล้วบันทึกเป็นบอทของคุณ
          </p>
        </div>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-500">
          โหมดทดลอง · ยังไม่ส่งคำสั่งซื้อขายจริง
        </span>
      </div>

      {/* 1. เทมเพลต */}
      <Card step={1} title="เลือกเทมเพลต หรือประกอบกฎเอง" subtitle="กดเทมเพลตเพื่อโหลดกฎเริ่มต้น แล้วปรับแก้ได้ในขั้นถัดไป">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {templates.map((t) => (
            <button
              key={t.key}
              type="button"
              className="rounded-xl border bg-background/40 p-4 text-left transition-colors hover:bg-accent"
              onClick={() => { setSpec(JSON.parse(JSON.stringify(t.spec))); setBt(null); }}
            >
              <div className="text-sm font-semibold">{t.name}</div>
              <div className="mt-1 text-xs text-muted-foreground">{t.desc}</div>
            </button>
          ))}
          <button
            type="button"
            className="rounded-xl border border-dashed p-4 text-left transition-colors hover:bg-accent"
            onClick={() => { setSpec(JSON.parse(JSON.stringify(EMPTY_SPEC))); setBt(null); }}
          >
            <div className="text-sm font-semibold">เริ่มใหม่</div>
            <div className="mt-1 text-xs text-muted-foreground">ล้างกฎกลับเป็นค่าเริ่มต้น</div>
          </button>
        </div>
      </Card>

      {/* 2. กฎ */}
      <Card step={2} title="กฎของบอท" subtitle="ตัดสินใจจากข้อมูลถึงแท่งก่อนหน้า แล้วซื้อ/ขายที่ราคาแท่งปัจจุบัน (ไม่มองอนาคต)">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="เหรียญ">
            <select
              value={spec.asset}
              className={`${inputBase} w-full cursor-pointer`}
              onChange={(e) => setSpec({ ...spec, asset: e.target.value })}
            >
              {ASSETS.map((a) => <option key={a}>{a}</option>)}
            </select>
          </Field>
          <Field label="ขนาดออเดอร์">
            <select
              value={spec.sizing.type}
              className={`${inputBase} w-full cursor-pointer`}
              onChange={(e) => setSpec({ ...spec, sizing: { ...spec.sizing, type: e.target.value as Spec["sizing"]["type"] } })}
            >
              <option value="pct_of_cash">% ของเงินสด</option>
              <option value="fixed_thb">จำนวนเงิน (บาท)</option>
            </select>
          </Field>
          <Field label="ค่า">
            <NumInput
              value={spec.sizing.value}
              suffix={spec.sizing.type === "pct_of_cash" ? "%" : "THB"}
              onChange={(v) => setSpec({ ...spec, sizing: { ...spec.sizing, value: Number(v) } })}
            />
          </Field>
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          <GroupEditor
            label="เงื่อนไขซื้อ"
            hint="บอทจะซื้อเมื่อเข้าเงื่อนไข (ถือได้ทีละ 1 ตำแหน่ง)"
            g={spec.entry}
            onChange={(g) => setSpec({ ...spec, entry: g })}
          />
          <GroupEditor
            label="เงื่อนไขขาย"
            hint="หรือจะใช้ Take-profit / Stop-loss ด้านล่างอย่างเดียวก็ได้"
            g={spec.exit}
            onChange={(g) => setSpec({ ...spec, exit: { ...spec.exit, ...g } })}
          />
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Field label="Take-profit (ขายเมื่อกำไรถึง)">
            <NumInput
              suffix="%"
              value={spec.exit.take_profit_pct ?? ""}
              placeholder="ไม่ใช้"
              onChange={(v) => setSpec({ ...spec, exit: { ...spec.exit, take_profit_pct: numOrNull(v) } })}
            />
          </Field>
          <Field label="Stop-loss (ขายเมื่อขาดทุนถึง)">
            <NumInput
              suffix="%"
              value={spec.exit.stop_loss_pct ?? ""}
              placeholder="ไม่ใช้"
              onChange={(v) => setSpec({ ...spec, exit: { ...spec.exit, stop_loss_pct: numOrNull(v) } })}
            />
          </Field>
        </div>

        <div className="mt-5 rounded-xl border bg-muted/40 px-4 py-3">
          <div className="mb-1 text-xs text-muted-foreground">กฎที่ประกอบ (สรุปเป็นประโยค)</div>
          {ruleErr ? (
            <div className="text-sm text-red-500">{ruleErr}</div>
          ) : (
            <div className="text-sm font-medium">{ruleText || "กำลังตรวจกฎ…"}</div>
          )}
        </div>
      </Card>

      {/* 3. Backtest */}
      <Card step={3} title="ทดสอบย้อนหลัง" subtitle="ใช้ราคาจริง + ส่วนต่าง (spread) และค่าธรรมเนียมเดียวกับหน้าซื้อขาย ไม่แตะพอร์ตของคุณ">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="เงินลงทุน" className="w-48">
            <NumInput value={capital} suffix="THB" onChange={(v) => setCapital(Number(v))} />
          </Field>
          <button type="button" className={btnPrimary} disabled={btBusy || !!ruleErr} onClick={runBacktest}>
            {btBusy ? "กำลังทดสอบ…" : "ทดสอบย้อนหลัง"}
          </button>
        </div>

        {btErr && (
          <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-500">{btErr}</div>
        )}

        {bt && (
          <div className="mt-6 space-y-5">
            <p className="text-xs text-muted-foreground">
              {bt.asset} · {bt.from} ถึง {bt.to} ({bt.bars} วัน)
            </p>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              {stats.map((s) => (
                <div key={s.label} className="rounded-xl border bg-background/40 p-4">
                  <div className="text-xs text-muted-foreground">{s.label}</div>
                  <div className={`mt-1 text-xl font-bold ${s.cls ?? ""}`}>{s.value}</div>
                </div>
              ))}
            </div>

            <EquityChart pts={bt.equity} />

            {bt.warnings.length > 0 && (
              <div className="space-y-1.5 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-500">
                {bt.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
              </div>
            )}

            {tradesShown.length > 0 && (
              <div className="rounded-xl border">
                <div className="border-b px-5 py-3 text-sm font-semibold">รายการซื้อขายย้อนหลัง</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground">
                        <th className="px-5 py-3 text-left font-medium">วันที่</th>
                        <th className="px-5 py-3 text-left font-medium">ฝั่ง</th>
                        <th className="px-5 py-3 text-right font-medium">ราคา</th>
                        <th className="px-5 py-3 text-right font-medium">จำนวนเงิน</th>
                        <th className="px-5 py-3 text-right font-medium">กำไร/ขาดทุน</th>
                        <th className="px-5 py-3 text-left font-medium">เหตุผล</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tradesShown.map((t, i) => (
                        <tr key={i} className="border-b last:border-0">
                          <td className="whitespace-nowrap px-5 py-3">{t.date}</td>
                          <td className="px-5 py-3">
                            <span
                              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                                t.side === "buy" ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"
                              }`}
                            >
                              {t.side === "buy" ? "ซื้อ" : "ขาย"}
                            </span>
                          </td>
                          <td className="px-5 py-3 text-right">฿{fmtThb(t.price)}</td>
                          <td className="px-5 py-3 text-right">฿{fmtThb(t.amount_thb)}</td>
                          <td className={`px-5 py-3 text-right ${colorOf(t.pnl_pct)}`}>
                            {t.pnl_pct == null ? "-" : fmtPct(t.pnl_pct)}
                          </td>
                          <td className="px-5 py-3 text-muted-foreground">{t.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="border-t px-5 py-2.5 text-xs text-muted-foreground">แสดง 30 รายการล่าสุด</div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* 4. บอทของฉัน */}
      <Card
        step={4}
        title={`บอทของฉัน (${bots.length}/${maxBots})`}
        subtitle="สร้างได้สูงสุดตามจำนวนที่กำหนด บอททุกตัวเริ่มที่โหมดทดลองและปิดอยู่"
      >
        <div className="flex flex-wrap items-center gap-3">
          <input
            placeholder="ตั้งชื่อบอท"
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
            className={`${inputBase} min-w-[180px] flex-1`}
          />
          <button type="button" className={btnPrimary} disabled={!canSave} onClick={saveBot}>
            บันทึกกฎนี้เป็นบอท
          </button>
        </div>
        {msg && <p className="mt-3 text-sm text-muted-foreground">{msg}</p>}

        <div className="mt-5 space-y-3">
          {bots.length === 0 && (
            <div className="flex min-h-[120px] items-center justify-center rounded-xl border border-dashed text-sm text-muted-foreground">
              ยังไม่มีบอท
            </div>
          )}

          {bots.map((b) => (
            <div key={b.id} className="rounded-xl border bg-background/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-semibold">{b.name}</span>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                      b.dry_run ? "bg-amber-500/10 text-amber-500" : "bg-red-500/10 text-red-500"
                    }`}
                  >
                    {b.dry_run ? "โหมดทดลอง" : "โหมดจริง"}
                  </span>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                      b.enabled ? "bg-emerald-500/10 text-emerald-500" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {b.enabled ? "เปิดอยู่" : "ปิดอยู่"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                   <button type="button" className={`${btnSmall} ${b.dry_run ? "" : "text-amber-500"}`} onClick={() => setMode(b, b.dry_run ? "live" : "dry")}>
                    {b.dry_run ? "ไปโหมดจริง" : "กลับโหมดทดลอง"}
                  </button>
                  <Switch checked={b.enabled} onChange={() => toggleBot(b)} label={`เปิดใช้งาน ${b.name}`} />
                  <button type="button" className={btnSmall} onClick={() => showRuns(b)}>
                    {runsFor === b.id ? "ซ่อนประวัติ" : "ประวัติ"}
                  </button>
                  <button type="button" className={`${btnSmall} text-red-500`} onClick={() => deleteBot(b)}>
                    ลบ
                  </button>
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{b.rule_text}</p>

              {runsFor === b.id && (
                <div className="mt-3 max-h-64 overflow-y-auto rounded-lg border bg-card">
                  {runs.length === 0 ? (
                    <div className="px-4 py-6 text-center text-xs text-muted-foreground">ยังไม่มีประวัติการทำงาน</div>
                  ) : (
                    runs.map((r, i) => {
                      const a = ACTION_TH[r.action] ?? { label: r.action, cls: "bg-muted text-muted-foreground" };
                      return (
                        <div key={i} className="flex items-center justify-between gap-3 border-b px-4 py-2.5 text-sm last:border-0">
                          <div className="flex min-w-0 items-center gap-2">
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${a.cls}`}>{a.label}</span>
                            <span className="truncate text-xs text-muted-foreground">{r.reason ?? ""}</span>
                          </div>
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {r.created_at.slice(0, 16).replace("T", " ")}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs text-muted-foreground">
          การเปิดใช้งานตอนนี้แค่บันทึกสถานะ ยังไม่มีตัววนเช็กที่ส่งคำสั่ง (ขั้นสุดท้ายของแผน) ผลย้อนหลังไม่รับประกันกำไรในอนาคต
        </p>
      </Card>
    </div>
  );
}
