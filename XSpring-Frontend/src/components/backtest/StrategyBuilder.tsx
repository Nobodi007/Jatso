import type { CondSpec, IndicatorDef, OperandSpec, StrategySpec } from "./types"

// ตัวสร้างกฎกลยุทธ์ (ฟอร์ม -> JSON ตามภาษากฎของ Backtest Lab) — ไฟล์ใหม่ ไม่แตะโค้ดเดิม
export type OperandForm = {
  kind: "price" | "ind" | "value"
  price: string
  ind: string
  output: string
  params: Record<string, string>
  source: string
  value: string
  bench: boolean
  shift: string
  mult: string
}
export type CondRow = { left: OperandForm; op: string; right: OperandForm }
export type Group = { mode: "all" | "any"; rows: CondRow[] }
export type StrategyForm = {
  enabled: boolean
  entry: Group
  exit: Group
  stopLoss: string
  takeProfit: string
  trailing: string
  maxHold: string
}

const OP_LABEL: Record<string, string> = {
  ">": "มากกว่า", ">=": "มากกว่าหรือเท่ากับ", "<": "น้อยกว่า", "<=": "น้อยกว่าหรือเท่ากับ",
  cross_above: "ตัดขึ้นเหนือ", cross_below: "ตัดลงใต้",
}

export function emptyOperand(kind: OperandForm["kind"] = "price"): OperandForm {
  return { kind, price: "close", ind: "ema", output: "", params: {}, source: "close", value: "", bench: false, shift: "0", mult: "1" }
}

export function defaultStrategyForm(): StrategyForm {
  const ema = { ...emptyOperand("ind"), ind: "ema", params: { period: "200" } }
  return {
    enabled: false,
    entry: { mode: "all", rows: [{ left: emptyOperand(), op: ">", right: ema }] },
    exit: { mode: "all", rows: [] },
    stopLoss: "", takeProfit: "", trailing: "", maxHold: "",
  }
}

function num(s: string, name: string): number | string {
  const v = Number(s)
  return s.trim() === "" || !Number.isFinite(v) ? `${name} ต้องเป็นตัวเลข` : v
}

function buildOperand(o: OperandForm, cat: IndicatorDef[], where: string): OperandSpec | string {
  if (o.kind === "value") {
    const v = num(o.value, `${where}: ค่าคงที่`)
    return typeof v === "string" ? v : { value: v }
  }
  const out: OperandSpec = {}
  if (o.kind === "price") {
    out.price = o.price
  } else {
    const def = cat.find((d) => d.key === o.ind)
    if (!def) return `${where}: เลือกตัวชี้วัด`
    out.ind = def.key
    if (o.output && o.output !== def.outputs[0]) out.output = o.output
    for (const p of def.params) {
      const raw = o.params[p.name]
      const v = raw === undefined || raw.trim() === "" ? p.default : Number(raw)
      if (!Number.isFinite(v)) return `${where}: ${def.key}.${p.name} ต้องเป็นตัวเลข`
      out[p.name] = v
    }
    if (def.uses_source && o.source !== "close") out.source = o.source
  }
  const shift = Number(o.shift || "0")
  if (!Number.isInteger(shift) || shift < 0) return `${where}: shift ต้องเป็นจำนวนเต็ม ≥ 0`
  if (shift > 0) out.shift = shift
  const mult = Number(o.mult || "1")
  if (!Number.isFinite(mult)) return `${where}: mult ต้องเป็นตัวเลข`
  if (mult !== 1) out.mult = mult
  if (o.bench) out.of = "benchmark"
  return out
}

function buildGroup(g: Group, cat: IndicatorDef[], name: string): CondSpec | string | null {
  if (g.rows.length === 0) return null
  const conds: CondSpec[] = []
  for (let i = 0; i < g.rows.length; i++) {
    const r = g.rows[i]
    const l = buildOperand(r.left, cat, `${name} ข้อ ${i + 1} ซ้าย`)
    if (typeof l === "string") return l
    const rr = buildOperand(r.right, cat, `${name} ข้อ ${i + 1} ขวา`)
    if (typeof rr === "string") return rr
    conds.push({ op: r.op, left: l, right: rr })
  }
  if (conds.length === 1) return conds[0]
  return g.mode === "all" ? { all: conds } : { any: conds }
}

export function buildStrategy(f: StrategyForm, cat: IndicatorDef[]): StrategySpec | string {
  const entry = buildGroup(f.entry, cat, "เงื่อนไขเข้าซื้อ")
  if (entry === null) return "ใส่เงื่อนไขเข้าซื้ออย่างน้อย 1 ข้อ"
  if (typeof entry === "string") return entry
  const exit = buildGroup(f.exit, cat, "เงื่อนไขขาย")
  if (typeof exit === "string") return exit
  const stops: NonNullable<StrategySpec["stops"]> = {}
  const opt = (s: string, name: string, key: "stop_loss_pct" | "take_profit_pct" | "trailing_stop_pct" | "max_hold_days"): string | null => {
    if (s.trim() === "") return null
    const v = num(s, name)
    if (typeof v === "string") return v
    stops[key] = v
    return null
  }
  const errs = [opt(f.stopLoss, "Stop-loss %", "stop_loss_pct"), opt(f.takeProfit, "Take-profit %", "take_profit_pct"),
    opt(f.trailing, "Trailing stop %", "trailing_stop_pct"), opt(f.maxHold, "ถือสูงสุด (วัน)", "max_hold_days")].filter((e) => e)
  if (errs.length) return errs[0] as string
  return { entry, exit, stops }
}

const sel = "rounded-lg border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-primary"
const inp = "w-16 rounded-lg border bg-background px-2 py-1.5 text-xs outline-none focus:ring-2 focus:ring-primary"
const chip = "rounded-md border px-2.5 py-1 text-xs hover:bg-accent disabled:opacity-40"

function OperandEditor({ o, cat, fields, onChange }: { o: OperandForm; cat: IndicatorDef[]; fields: string[]; onChange: (o: OperandForm) => void }) {
  const def = cat.find((d) => d.key === o.ind)
  const set = (p: Partial<OperandForm>) => onChange({ ...o, ...p })
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg border bg-muted/50 p-1.5">
      <select className={sel} value={o.kind} onChange={(e) => set({ kind: e.target.value as OperandForm["kind"] })}>
        <option value="price">ราคา</option><option value="ind">ตัวชี้วัด</option><option value="value">ค่าคงที่</option>
      </select>
      {o.kind === "price" && (
        <select className={sel} value={o.price} onChange={(e) => set({ price: e.target.value })}>
          {fields.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      )}
      {o.kind === "value" && <input className={inp} inputMode="decimal" value={o.value} onChange={(e) => set({ value: e.target.value })} aria-label="ค่า" />}
      {o.kind === "ind" && (
        <>
          <select className={sel} value={o.ind} onChange={(e) => set({ ind: e.target.value, output: "", params: {} })}>
            {cat.map((d) => <option key={d.key} value={d.key}>{d.key.toUpperCase()}</option>)}
          </select>
          {def && def.outputs.length > 1 && (
            <select className={sel} value={o.output || def.outputs[0]} onChange={(e) => set({ output: e.target.value })}>
              {def.outputs.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          )}
          {def?.params.map((p) => (
            <label key={p.name} className="flex items-center gap-1 text-[10px] text-muted-foreground">
              {p.name}
              <input className={inp} inputMode="decimal" value={o.params[p.name] ?? String(p.default)}
                onChange={(e) => set({ params: { ...o.params, [p.name]: e.target.value } })} />
            </label>
          ))}
          {def?.uses_source && (
            <select className={sel} value={o.source} onChange={(e) => set({ source: e.target.value })} aria-label="source">
              {fields.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          )}
        </>
      )}
      {o.kind !== "value" && (
        <>
          <label className="flex items-center gap-1 text-[10px] text-muted-foreground">ย้อน
            <input className={`${inp} w-12`} inputMode="numeric" value={o.shift} onChange={(e) => set({ shift: e.target.value })} />แท่ง
          </label>
          <label className="flex items-center gap-1 text-[10px] text-muted-foreground">×
            <input className={`${inp} w-14`} inputMode="decimal" value={o.mult} onChange={(e) => set({ mult: e.target.value })} />
          </label>
          <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <input type="checkbox" className="accent-primary" checked={o.bench} onChange={(e) => set({ bench: e.target.checked })} />ของ S&amp;P 500
          </label>
        </>
      )}
    </div>
  )
}

function GroupEditor({ title, hint, g, cat, ops, fields, onChange }: {
  title: string; hint: string; g: Group; cat: IndicatorDef[]; ops: string[]; fields: string[]; onChange: (g: Group) => void
}) {
  const setRow = (i: number, r: CondRow) => onChange({ ...g, rows: g.rows.map((x, j) => (j === i ? r : x)) })
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div><div className="text-sm font-medium text-foreground">{title}</div><div className="text-xs text-muted-foreground">{hint}</div></div>
        {g.rows.length > 1 && (
          <select className={sel} value={g.mode} onChange={(e) => onChange({ ...g, mode: e.target.value as Group["mode"] })}>
            <option value="all">ต้องเป็นจริงทุกข้อ (และ)</option><option value="any">ข้อใดข้อหนึ่ง (หรือ)</option>
          </select>
        )}
      </div>
      {g.rows.map((r, i) => (
        <div key={i} className="space-y-2 rounded-lg border p-2.5">
          <OperandEditor o={r.left} cat={cat} fields={fields} onChange={(left) => setRow(i, { ...r, left })} />
          <div className="flex items-center gap-2">
            <select className={sel} value={r.op} onChange={(e) => setRow(i, { ...r, op: e.target.value })}>
              {ops.map((o) => <option key={o} value={o}>{OP_LABEL[o] ?? o}</option>)}
            </select>
            <button type="button" className="ml-auto text-[10px] text-muted-foreground hover:text-red-500" onClick={() => onChange({ ...g, rows: g.rows.filter((_, j) => j !== i) })}>ลบข้อนี้</button>
          </div>
          <OperandEditor o={r.right} cat={cat} fields={fields} onChange={(right) => setRow(i, { ...r, right })} />
        </div>
      ))}
      <button type="button" className={chip} disabled={g.rows.length >= 8}
        onClick={() => onChange({ ...g, rows: [...g.rows, { left: emptyOperand(), op: ">", right: emptyOperand("value") }] })}>+ เพิ่มเงื่อนไข</button>
    </div>
  )
}

export default function StrategyBuilder({ form, onChange, cat, ops, fields }: {
  form: StrategyForm; onChange: (f: StrategyForm) => void; cat: IndicatorDef[]; ops: string[]; fields: string[]
}) {
  const field = "w-full rounded-lg border bg-background px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary"
  return (
    <div className="mt-4 rounded-xl border p-4">
      <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
        <input type="checkbox" className="accent-primary" checked={form.enabled} onChange={(e) => onChange({ ...form, enabled: e.target.checked })} />
        ใช้กลยุทธ์เทคนิค (ไม่ติ๊ก = ถือตามสัดส่วนล้วน ๆ)
      </label>
      {form.enabled && (
        <div className="mt-3 space-y-4">
          <p className="text-xs text-muted-foreground">
            แต่ละหุ้นมีเงินของตัวเอง (น้ำหนัก × เงินทุน) ถือเต็มช่องเมื่อเข้าเงื่อนไข ไม่เช่นนั้นถือเงินสด · สัญญาณคิดจากราคาปิด ส่งคำสั่งที่เปิดวันถัดไป ·
            ถ้าไม่ใส่เงื่อนไขขาย ระบบขายเมื่อเงื่อนไขซื้อ "เป็นเท็จ"
          </p>
          <GroupEditor title="เงื่อนไขเข้าซื้อ" hint="เช่น ราคาปิด มากกว่า EMA 200" g={form.entry} cat={cat} ops={ops} fields={fields} onChange={(entry) => onChange({ ...form, entry })} />
          <GroupEditor title="เงื่อนไขขาย (ไม่บังคับ)" hint="เช่น RSI 14 มากกว่า 80" g={form.exit} cat={cat} ops={ops} fields={fields} onChange={(exit) => onChange({ ...form, exit })} />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div><label className="mb-2 block text-xs text-muted-foreground">Stop-loss %</label><input className={field} inputMode="decimal" value={form.stopLoss} onChange={(e) => onChange({ ...form, stopLoss: e.target.value })} /></div>
            <div><label className="mb-2 block text-xs text-muted-foreground">Take-profit %</label><input className={field} inputMode="decimal" value={form.takeProfit} onChange={(e) => onChange({ ...form, takeProfit: e.target.value })} /></div>
            <div><label className="mb-2 block text-xs text-muted-foreground">Trailing stop %</label><input className={field} inputMode="decimal" value={form.trailing} onChange={(e) => onChange({ ...form, trailing: e.target.value })} /></div>
            <div><label className="mb-2 block text-xs text-muted-foreground">ถือสูงสุด (วันทำการ)</label><input className={field} inputMode="numeric" value={form.maxHold} onChange={(e) => onChange({ ...form, maxHold: e.target.value })} /></div>
          </div>
        </div>
      )}
    </div>
  )
}
