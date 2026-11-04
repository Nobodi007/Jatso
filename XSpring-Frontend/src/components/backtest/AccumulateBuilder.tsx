import type { ReactNode } from "react"
import type { AccFreq, AccumulateSpec } from "./accumulateTypes"

/* ฟอร์มตั้งค่า DCA / Buy-the-dip — ควบคุมจากหน้าแม่
   const [acc, setAcc] = useState<AccState>(defaultAccState)
   <AccumulateBuilder value={acc} onChange={setAcc} />
   ตอนสร้าง spec:  const a = accStateToSpec(acc); if (a.error) {แสดง a.error; return}  spec.accumulate = a.spec ?? undefined
   (accumulate ใช้ร่วมกับ strategy ไม่ได้ และ rebalance ต้องเป็น none) */

export type WhenKind = "none" | "close_lt_ema" | "close_gt_ema" | "rsi_lt" | "custom"

export interface AccState {
  enabled: boolean
  contribOn: boolean; contribAmount: string; contribFreq: AccFreq
  schedOn: boolean; schedAmount: string; schedFreq: AccFreq
  dipOn: boolean; dipDrop: string; dipLookback: string; dipAmount: string; dipCooldown: string
  maxInvested: string
  initialPct: string
  whenKind: WhenKind; whenN: string; whenJson: string
}

export const defaultAccState: AccState = {
  enabled: false,
  contribOn: false, contribAmount: "1000", contribFreq: "monthly",
  schedOn: true, schedAmount: "1000", schedFreq: "monthly",
  dipOn: false, dipDrop: "20", dipLookback: "252", dipAmount: "2000", dipCooldown: "21",
  maxInvested: "", initialPct: "0",
  whenKind: "none", whenN: "200", whenJson: "",
}

const num = (s: string): number => (s.trim() === "" ? NaN : Number(s))

function buildWhen(a: AccState): { when: Record<string, unknown> | null; error?: string } {
  const n = num(a.whenN)
  switch (a.whenKind) {
    case "none":
      return { when: null }
    case "close_lt_ema":
    case "close_gt_ema":
      if (!Number.isFinite(n) || n < 2) return { when: null, error: "ช่วงของ EMA ต้องเป็นตัวเลข ≥ 2" }
      return { when: { op: a.whenKind === "close_lt_ema" ? "<" : ">", left: { price: "close" }, right: { ind: "ema", period: n } } }
    case "rsi_lt":
      if (!Number.isFinite(n) || n <= 0 || n >= 100) return { when: null, error: "ค่า RSI ต้องอยู่ระหว่าง 0 ถึง 100" }
      return { when: { op: "<", left: { ind: "rsi", period: 14 }, right: { value: n } } }
    default:
      try {
        const j = JSON.parse(a.whenJson) as unknown
        if (typeof j !== "object" || j === null || Array.isArray(j)) return { when: null, error: "เงื่อนไข (JSON) ต้องเป็น object" }
        return { when: j as Record<string, unknown> }
      } catch {
        return { when: null, error: "เงื่อนไข (JSON) อ่านไม่ได้" }
      }
  }
}

/** แปลงสถานะฟอร์มเป็น spec.accumulate (spec = null เมื่อปิดโหมด) — ตรวจเบื้องต้น ส่วนที่เหลือ backend ตรวจซ้ำ */
export function accStateToSpec(a: AccState): { spec: AccumulateSpec | null; error: string | null } {
  if (!a.enabled) return { spec: null, error: null }
  const out: AccumulateSpec = {}
  const pos = (v: string, name: string): string | null => (Number.isFinite(num(v)) && num(v) > 0 ? null : `${name} ต้องเป็นตัวเลขมากกว่า 0`)
  if (a.contribOn) {
    const e = pos(a.contribAmount, "เงินเติมต่อรอบ")
    if (e) return { spec: null, error: e }
    out.contribution = { amount: num(a.contribAmount), frequency: a.contribFreq }
  }
  if (a.schedOn) {
    const e = pos(a.schedAmount, "ยอด DCA ต่อรอบ")
    if (e) return { spec: null, error: e }
    out.schedule = { amount: num(a.schedAmount), frequency: a.schedFreq }
  }
  if (a.dipOn) {
    const e = pos(a.dipAmount, "เงินซื้อต่อครั้ง (ตอนย่อ)") ?? pos(a.dipDrop, "% ที่ลง") ?? pos(a.dipLookback, "จำนวนวันย้อนหลัง") ?? pos(a.dipCooldown, "ระยะห่างระหว่างการซื้อ")
    if (e) return { spec: null, error: e }
    out.dip = { drop_pct: num(a.dipDrop), lookback_days: num(a.dipLookback), amount: num(a.dipAmount), cooldown_days: num(a.dipCooldown) }
  }
  if (a.maxInvested.trim() !== "") {
    const e = pos(a.maxInvested, "เพดานเงินซื้อสะสมต่อหุ้น")
    if (e) return { spec: null, error: e }
    out.max_invested_per_stock = num(a.maxInvested)
  }
  const ip = num(a.initialPct)
  if (!Number.isFinite(ip) || ip < 0 || ip > 100) return { spec: null, error: "% ลงทุนก้อนแรกต้องอยู่ระหว่าง 0 ถึง 100" }
  out.initial_invest_pct = ip
  if (!out.schedule && !out.dip && ip <= 0) return { spec: null, error: "ต้องเปิดอย่างน้อยหนึ่งอย่าง: DCA, ซื้อตอนย่อ หรือลงก้อนแรก" }
  const w = buildWhen(a)
  if (w.error) return { spec: null, error: w.error }
  out.when = w.when
  return { spec: out, error: null }
}

/* ───────── UI ───────── */
const inputCls = "w-full rounded-lg border border-border bg-background px-2 py-1 text-sm tabular-nums"
const selCls = "rounded-lg border border-border bg-background px-2 py-1 text-sm"

function Row({ on, onToggle, title, hint, children }: { on: boolean; onToggle: (v: boolean) => void; title: string; hint: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-border p-3">
      <label className="flex items-center gap-2 text-sm font-medium">
        <input type="checkbox" checked={on} onChange={(e: { target: { checked: boolean } }) => onToggle(e.target.checked)} />
        {title}
      </label>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      {on && <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">{children}</div>}
    </div>
  )
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-muted-foreground">{label}</label>
      {children}
    </div>
  )
}
function FreqSel({ v, onChange }: { v: AccFreq; onChange: (v: AccFreq) => void }) {
  return (
    <select className={selCls} value={v} onChange={(e: { target: { value: string } }) => onChange(e.target.value as AccFreq)}>
      <option value="weekly">ทุกสัปดาห์</option>
      <option value="monthly">ทุกเดือน</option>
      <option value="quarterly">ทุกไตรมาส</option>
    </select>
  )
}

export default function AccumulateBuilder({ value, onChange }: { value: AccState; onChange: (v: AccState) => void }) {
  const set = (p: Partial<AccState>) => onChange({ ...value, ...p })
  const txt = (k: keyof AccState) => ({
    className: inputCls, inputMode: "decimal" as const, value: value[k] as string,
    onChange: (e: { target: { value: string } }) => set({ [k]: e.target.value } as Partial<AccState>),
  })
  return (
    <div className="rounded-3xl border border-border bg-card p-5">
      <label className="flex items-center gap-2 text-base font-medium">
        <input type="checkbox" checked={value.enabled} onChange={(e: { target: { checked: boolean } }) => set({ enabled: e.target.checked })} />
        ทยอยสะสม (DCA / ซื้อตอนย่อ)
      </label>
      <p className="mt-1 text-xs text-muted-foreground">
        ซื้อเป็นก้อนย่อยตามรอบเวลาหรือเมื่อราคาลงจากสูงสุด ไม่มีการขาย · ใช้ร่วมกับกฎกลยุทธ์เข้า/ออกไม่ได้ และ rebalance ต้องปิด · ราคาต่อรอบอ้างอิงจากปิดวันก่อนหน้า ซื้อที่เปิดวันนี้
      </p>
      {value.enabled && (
        <div className="mt-4 space-y-3">
          <Row on={value.contribOn} onToggle={(v) => set({ contribOn: v })} title="เติมเงินใหม่เข้าพอร์ตตามรอบ"
            hint="เงินใหม่เข้าวันทำการแรกของงวด (ไม่รวมวันแรก) แบ่งเข้าช่องของแต่ละหุ้นตามน้ำหนักเป้าหมาย">
            <Field label="จำนวนต่อรอบ (USD)"><input {...txt("contribAmount")} /></Field>
            <Field label="ความถี่"><FreqSel v={value.contribFreq} onChange={(v) => set({ contribFreq: v })} /></Field>
          </Row>
          <Row on={value.schedOn} onToggle={(v) => set({ schedOn: v })} title="DCA: ซื้อตามรอบ"
            hint="ยอดรวมต่อรอบแบ่งตามน้ำหนักเป้าหมาย ซื้อจากเงินสดในช่องของหุ้นนั้น (ซื้อรอบแรกวันเริ่มทดสอบ)">
            <Field label="ยอดซื้อรวมต่อรอบ (USD)"><input {...txt("schedAmount")} /></Field>
            <Field label="ความถี่"><FreqSel v={value.schedFreq} onChange={(v) => set({ schedFreq: v })} /></Field>
          </Row>
          <Row on={value.dipOn} onToggle={(v) => set({ dipOn: v })} title="ซื้อตอนย่อ (Buy the dip)"
            hint="ซื้อเมื่อราคาปิดต่ำกว่าสูงสุดย้อนหลังตามเกณฑ์ ต่อหุ้นแต่ละตัว ห่างกันอย่างน้อยตามระยะที่ตั้ง (กันซื้อรัวทุกวันตอนตลาดลงยาว)">
            <Field label="ลงจากสูงสุดอย่างน้อย (%)"><input {...txt("dipDrop")} /></Field>
            <Field label="สูงสุดย้อนหลัง (วันทำการ, 252 ≈ 52 สัปดาห์)"><input {...txt("dipLookback")} /></Field>
            <Field label="ซื้อต่อครั้งต่อหุ้น (USD)"><input {...txt("dipAmount")} /></Field>
            <Field label="ห่างกันอย่างน้อย (วันทำการ)"><input {...txt("dipCooldown")} /></Field>
          </Row>

          <div className="rounded-2xl border border-border p-3">
            <p className="text-sm font-medium">เงื่อนไขเพิ่มเติม (ต้องจริงด้วยจึงซื้อ)</p>
            <p className="mt-1 text-xs text-muted-foreground">ใช้กับทั้ง DCA และซื้อตอนย่อ เช่น ร่วง 20% และราคาต่ำกว่า EMA200 · ใช้ราคาปิดวันก่อนหน้า</p>
            <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Field label="เงื่อนไข">
                <select className={selCls} value={value.whenKind} onChange={(e: { target: { value: string } }) => set({ whenKind: e.target.value as WhenKind })}>
                  <option value="none">ไม่ใช้</option>
                  <option value="close_lt_ema">ราคาปิด ต่ำกว่า EMA</option>
                  <option value="close_gt_ema">ราคาปิด สูงกว่า EMA</option>
                  <option value="rsi_lt">RSI(14) ต่ำกว่า</option>
                  <option value="custom">กำหนดเอง (JSON)</option>
                </select>
              </Field>
              {value.whenKind !== "none" && value.whenKind !== "custom" && (
                <Field label={value.whenKind === "rsi_lt" ? "ค่า RSI" : "ช่วง EMA (วัน)"}><input {...txt("whenN")} /></Field>
              )}
            </div>
            {value.whenKind === "custom" && (
              <textarea className={`${inputCls} mt-3 h-24 font-mono text-xs`} placeholder='{"op":"<","left":{"price":"close"},"right":{"ind":"sma","period":50}}'
                value={value.whenJson} onChange={(e: { target: { value: string } }) => set({ whenJson: e.target.value })} />
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Field label="เพดานเงินซื้อสะสมต่อหุ้น (USD, เว้นว่าง = ไม่จำกัด)"><input {...txt("maxInvested")} /></Field>
            <Field label="ลงก้อนแรกทันที (% ของเงินช่อง)"><input {...txt("initialPct")} /></Field>
          </div>
        </div>
      )}
    </div>
  )
}
