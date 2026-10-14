import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

/* =========================================================
   BotLab — หน้าบอทเทรดใน Quant Lab (ไม่พึ่งไลบรารีอื่น)
   ใช้: <BotLab api={botApi} />
   botApi ต้อง: ใส่ base URL + header (API key / token) ให้ครบ,
   แปลง body เป็น JSON, และ throw Error(ข้อความ detail) เมื่อ response ไม่ ok
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
  n == null || n === 0 ? undefined : n > 0 ? "#16a34a" : "#dc2626";

/* ---------- styles (เป็นกลาง ใช้ได้ทั้งโหมดมืด/สว่าง) ---------- */
const line = "1px solid rgba(128,128,128,.35)";
const box: CSSProperties = { border: line, borderRadius: 14, padding: 16, marginBottom: 16 };
const inp: CSSProperties = {
  background: "transparent", color: "inherit", border: line, borderRadius: 8,
  padding: "6px 8px", font: "inherit", minWidth: 0,
};
const btn: CSSProperties = {
  background: "transparent", color: "inherit", border: line, borderRadius: 999,
  padding: "7px 14px", font: "inherit", cursor: "pointer",
};
const btnPrimary: CSSProperties = { ...btn, background: "rgba(128,128,128,.22)", fontWeight: 600 };
const muted: CSSProperties = { opacity: 0.65, fontSize: 13 };

function Card({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section style={box}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 17 }}>{title}</h3>
        {right}
      </div>
      {children}
    </section>
  );
}

/* ---------- ตัวแก้ operand / กลุ่มเงื่อนไข ---------- */
function OperandEditor({ o, onChange }: { o: Operand; onChange: (o: Operand) => void }) {
  return (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
      <select value={kindOf(o)} onChange={(e) => onChange(makeOperand(e.target.value, o))} style={inp}>
        {KINDS.map(([k, label]) => (
          <option key={k} value={k}>{label}</option>
        ))}
      </select>
      {"value" in o && (
        <input type="number" value={o.value} style={{ ...inp, width: 90 }}
          onChange={(e) => onChange({ value: Number(e.target.value) })} />
      )}
      {"period" in o && (
        <input type="number" min={1} value={o.period} style={{ ...inp, width: 64 }} title="period (จำนวนแท่ง)"
          onChange={(e) => onChange({ ...o, period: Math.round(Number(e.target.value)) })} />
      )}
    </span>
  );
}

function GroupEditor({ g, onChange, label }: { g: Group; onChange: (g: Group) => void; label: string }) {
  const setCond = (i: number, c: Cond) => onChange({ ...g, conds: g.conds.map((x, j) => (j === i ? c : x)) });
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
        <strong>{label}</strong>
        <span style={muted}>เมื่อเข้าเงื่อนไข</span>
        <select value={g.op} style={inp} onChange={(e) => onChange({ ...g, op: e.target.value as "all" | "any" })}>
          <option value="all">ทุกข้อ (และ)</option>
          <option value="any">ข้อใดข้อหนึ่ง (หรือ)</option>
        </select>
      </div>
      {g.conds.map((c, i) => (
        <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
          <OperandEditor o={c.left} onChange={(left) => setCond(i, { ...c, left })} />
          <select value={c.op} style={inp} onChange={(e) => setCond(i, { ...c, op: e.target.value })}>
            {OPS.map(([k, t]) => (
              <option key={k} value={k}>{t}</option>
            ))}
          </select>
          <OperandEditor o={c.right} onChange={(right) => setCond(i, { ...c, right })} />
          <button style={btn} onClick={() => onChange({ ...g, conds: g.conds.filter((_, j) => j !== i) })}>ลบ</button>
        </div>
      ))}
      {g.conds.length < MAX_CONDS && (
        <button
          style={btn}
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
  const W = 640, H = 220, P = 6;
  if (pts.length < 2) return null;
  const a = pts.map((p) => Number(p.value ?? 0));
  const b = pts.map((p) => Number(p.buy_hold ?? 0));
  const all = [...a, ...b];
  const lo = Math.min(...all), hi = Math.max(...all);
  const span = hi - lo || 1;
  const path = (arr: number[]) =>
    arr.map((v, i) => `${(P + (i / (arr.length - 1)) * (W - 2 * P)).toFixed(1)},${(H - P - ((v - lo) / span) * (H - 2 * P)).toFixed(1)}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", border: line, borderRadius: 10 }}>
        <polyline points={path(b)} fill="none" stroke="#9ca3af" strokeWidth={1.5} strokeDasharray="4 3" />
        <polyline points={path(a)} fill="none" stroke="#3b82f6" strokeWidth={2} />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", ...muted }}>
        <span>{pts[0].date}</span>
        <span>
          <span style={{ color: "#3b82f6" }}>━ บอท</span>{"  "}
          <span style={{ color: "#9ca3af" }}>┅ ถือเฉยๆ</span>
        </span>
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

  const deleteBot = async (b: Bot) => {
    if (!window.confirm(`ลบบอท "${b.name}" ?`)) return;
    try {
      await api(`/api/bots/${b.id}`, { method: "DELETE" });
      if (runsFor === b.id) setRunsFor(null);
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

  return (
    <div style={{ marginTop: 24 }}>
      <h2 style={{ marginBottom: 4 }}>บอทเทรด</h2>
      <p style={{ ...muted, marginTop: 0 }}>
        บอททุกตัวเป็น <strong>โหมดทดลอง</strong> ยังไม่ส่งคำสั่งซื้อขายจริง ผลย้อนหลังไม่รับประกันกำไรในอนาคต
      </p>

      <Card title="1. เลือกเทมเพลต หรือประกอบกฎเอง">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {templates.map((t) => (
            <button key={t.key} style={btn} title={t.desc} onClick={() => { setSpec(JSON.parse(JSON.stringify(t.spec))); setBt(null); }}>
              {t.name}
            </button>
          ))}
          <button style={btn} onClick={() => { setSpec(JSON.parse(JSON.stringify(EMPTY_SPEC))); setBt(null); }}>เริ่มใหม่</button>
        </div>
      </Card>

      <Card title="2. กฎของบอท">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
          <label>เหรียญ</label>
          <select value={spec.asset} style={inp} onChange={(e) => setSpec({ ...spec, asset: e.target.value })}>
            {ASSETS.map((a) => <option key={a}>{a}</option>)}
          </select>
          <label style={{ marginLeft: 12 }}>ขนาดออเดอร์</label>
          <select value={spec.sizing.type} style={inp}
            onChange={(e) => setSpec({ ...spec, sizing: { ...spec.sizing, type: e.target.value as Spec["sizing"]["type"] } })}>
            <option value="pct_of_cash">% ของเงินสด</option>
            <option value="fixed_thb">จำนวนเงิน (บาท)</option>
          </select>
          <input type="number" value={spec.sizing.value} style={{ ...inp, width: 100 }}
            onChange={(e) => setSpec({ ...spec, sizing: { ...spec.sizing, value: Number(e.target.value) } })} />
        </div>

        <GroupEditor label="เงื่อนไขซื้อ" g={spec.entry} onChange={(g) => setSpec({ ...spec, entry: g })} />
        <GroupEditor label="เงื่อนไขขาย" g={spec.exit}
          onChange={(g) => setSpec({ ...spec, exit: { ...spec.exit, ...g } })} />

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 12 }}>
          <label>Take-profit (%){" "}
            <input type="number" style={{ ...inp, width: 80 }} value={spec.exit.take_profit_pct ?? ""}
              onChange={(e) => setSpec({ ...spec, exit: { ...spec.exit, take_profit_pct: numOrNull(e.target.value) } })} />
          </label>
          <label>Stop-loss (%){" "}
            <input type="number" style={{ ...inp, width: 80 }} value={spec.exit.stop_loss_pct ?? ""}
              onChange={(e) => setSpec({ ...spec, exit: { ...spec.exit, stop_loss_pct: numOrNull(e.target.value) } })} />
          </label>
        </div>

        <div style={{ border: line, borderRadius: 10, padding: 12 }}>
          {ruleErr
            ? <span style={{ color: "#dc2626" }}>{ruleErr}</span>
            : <span>{ruleText || "กำลังตรวจกฎ…"}</span>}
        </div>
      </Card>

      <Card title="3. ทดสอบย้อนหลัง">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <label>เงินลงทุน (บาท)</label>
          <input type="number" value={capital} style={{ ...inp, width: 120 }} onChange={(e) => setCapital(Number(e.target.value))} />
          <button style={btnPrimary} disabled={btBusy || !!ruleErr} onClick={runBacktest}>
            {btBusy ? "กำลังทดสอบ…" : "ทดสอบย้อนหลัง"}
          </button>
        </div>
        {btErr && <p style={{ color: "#dc2626" }}>{btErr}</p>}

        {bt && (
          <div style={{ marginTop: 16 }}>
            <p style={muted}>{bt.asset} · {bt.from} ถึง {bt.to} ({bt.bars} วัน)</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: 10, marginBottom: 14 }}>
              {[
                ["เงินสุดท้าย", `${fmtThb(bt.final)} ฿`, undefined],
                ["ผลตอบแทนบอท", fmtPct(bt.return_pct), colorOf(bt.return_pct)],
                ["ถือเฉยๆ", fmtPct(bt.buy_hold_return_pct), colorOf(bt.buy_hold_return_pct)],
                ["ขาดทุนสูงสุด", fmtPct(bt.max_dd), colorOf(bt.max_dd)],
                ["รอบที่ปิดแล้ว", String(bt.n_closed), undefined],
                ["ชนะ", bt.win_rate == null ? "-" : `${bt.win_rate.toFixed(0)}%`, undefined],
              ].map(([k, v, c]) => (
                <div key={k as string} style={{ border: line, borderRadius: 10, padding: 10 }}>
                  <div style={muted}>{k}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: c as string | undefined }}>{v}</div>
                </div>
              ))}
            </div>

            <EquityChart pts={bt.equity} />

            {bt.warnings.map((w, i) => <p key={i} style={{ ...muted, margin: "8px 0 0" }}>⚠ {w}</p>)}

            {tradesShown.length > 0 && (
              <div style={{ overflowX: "auto", marginTop: 14 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ textAlign: "left", opacity: 0.7 }}>
                      <th>วันที่</th><th>ฝั่ง</th><th>ราคา</th><th>จำนวนเงิน</th><th>กำไร/ขาดทุน</th><th>เหตุผล</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tradesShown.map((t, i) => (
                      <tr key={i} style={{ borderTop: line }}>
                        <td>{t.date}</td>
                        <td>{t.side === "buy" ? "ซื้อ" : "ขาย"}</td>
                        <td>{fmtThb(t.price)}</td>
                        <td>{fmtThb(t.amount_thb)}</td>
                        <td style={{ color: colorOf(t.pnl_pct) }}>{t.pnl_pct == null ? "-" : fmtPct(t.pnl_pct)}</td>
                        <td>{t.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p style={muted}>แสดง 30 รายการล่าสุด</p>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title={`4. บอทของฉัน (${bots.length}/${maxBots})`}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <input placeholder="ตั้งชื่อบอท" value={name} maxLength={60} style={{ ...inp, flex: 1, minWidth: 160 }}
            onChange={(e) => setName(e.target.value)} />
          <button style={btnPrimary} disabled={!canSave} onClick={saveBot}>บันทึกกฎนี้เป็นบอท</button>
        </div>
        {msg && <p style={muted}>{msg}</p>}
        {bots.length === 0 && <p style={muted}>ยังไม่มีบอท</p>}

        {bots.map((b) => (
          <div key={b.id} style={{ border: line, borderRadius: 10, padding: 12, marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <div>
                <strong>{b.name}</strong>{" "}
                <span style={{ ...muted, border: line, borderRadius: 999, padding: "1px 8px" }}>
                  {b.dry_run ? "โหมดทดลอง" : "โหมดจริง"}
                </span>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <label style={{ cursor: "pointer" }}>
                  <input type="checkbox" checked={b.enabled} onChange={() => toggleBot(b)} /> เปิดใช้งาน
                </label>
                <button style={btn} onClick={() => showRuns(b)}>ประวัติ</button>
                <button style={btn} onClick={() => deleteBot(b)}>ลบ</button>
              </div>
            </div>
            <div style={{ ...muted, marginTop: 6 }}>{b.rule_text}</div>

            {runsFor === b.id && (
              <div style={{ marginTop: 10 }}>
                {runs.length === 0
                  ? <span style={muted}>ยังไม่มีประวัติการทำงาน</span>
                  : runs.map((r, i) => (
                    <div key={i} style={{ fontSize: 13, borderTop: line, padding: "4px 0" }}>
                      {r.created_at.slice(0, 16).replace("T", " ")} · {r.action} {r.reason ? `· ${r.reason}` : ""}
                    </div>
                  ))}
              </div>
            )}
          </div>
        ))}
        <p style={muted}>การเปิดใช้งานตอนนี้แค่บันทึกสถานะ ยังไม่มีตัววนเช็กที่ส่งคำสั่ง (ขั้นสุดท้ายของแผน)</p>
      </Card>
    </div>
  );
}
