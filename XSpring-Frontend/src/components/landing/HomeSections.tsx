import { useEffect, useState } from "react"
import { BarChart3, Newspaper, Scale, ShieldCheck, TestTube2, UserPlus } from "lucide-react"
import type { LucideIcon } from "lucide-react"

const API_BASE_URL = "https://xspring-api.onrender.com"

type Row = { asset: string; name: string; price: number; change: number }
type Props = {
  onLogin: () => void
  onRegister: () => void
  onOpenCoin: (asset: string) => void
  onGo: (label: string) => void
  heroTitle: string
  heroSub: string
  heroArt: React.ReactNode
}

const fmtPrice = (v: number) => v.toLocaleString("th-TH", { maximumFractionDigits: v < 1 ? 4 : 2 })

function Spark({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return <span className="text-xs text-muted-foreground">—</span>
  const min = Math.min(...data)
  const span = Math.max(...data) - min || 1
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * 100},${28 - ((v - min) / span) * 26}`)
    .join(" ")
  return (
    <svg viewBox="0 0 100 30" className="h-8 w-24" preserveAspectRatio="none" aria-hidden="true">
      <polyline
        points={pts}
        fill="none"
        strokeWidth={1.8}
        vectorEffect="non-scaling-stroke"
        className={up ? "stroke-emerald-500" : "stroke-red-500"}
      />
    </svg>
  )
}

const WHY: { icon: LucideIcon; title: string; text: string }[] = [
  {
    icon: ShieldCheck,
    title: "ฝึกโดยไม่เสี่ยงเงินจริง",
    text: "ทุกการซื้อขายเกิดในบัญชีจำลอง คุณลองผิดลองถูกได้เต็มที่ โดยที่เงินในกระเป๋ายังอยู่ครบ",
  },
  {
    icon: BarChart3,
    title: "ข้อมูลราคาเป็นบาท",
    text: "ดูราคาสดจากกระดานไทย พร้อมเทียบต้นทุนซื้อและรายรับขายหลังหักค่าธรรมเนียม ไม่ต้องคำนวณเอง",
  },
  {
    icon: TestTube2,
    title: "ทดสอบก่อนตัดสินใจ",
    text: "ลองจำลองการลงทุนย้อนหลังหลายรูปแบบ แล้วดูว่าผลต่างจากการฝากออมทรัพย์แค่ไหน",
  },
]

const STEPS: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: UserPlus, title: "สมัครด้วยบัญชี Google", text: "ใช้เวลาไม่กี่วินาที ไม่ต้องตั้งรหัสผ่านใหม่" },
  { icon: Scale, title: "ฝึกซื้อขายในบัญชีจำลอง", text: "เริ่มจากเงินจำลอง เรียนรู้จังหวะและต้นทุนจริงของตลาด" },
  { icon: BarChart3, title: "ทดสอบกลยุทธ์ย้อนหลัง", text: "เทียบผลลัพธ์ก่อนนำไปใช้กับการตัดสินใจของคุณเอง" },
]

const TOOLS: { icon: LucideIcon; title: string; text: string; go: string }[] = [
  { icon: Newspaper, title: "ข่าวคริปโต", text: "ข่าวล่าสุดที่เกี่ยวกับเหรียญในระบบ", go: "ข่าว" },
  { icon: Scale, title: "เทียบราคากระดานไทย", text: "ดูว่ากระดานไหนซื้อถูกและขายได้มากกว่า", go: "ตลาด" },
  { icon: TestTube2, title: "ลองลงทุนย้อนหลัง", text: "ซื้อทีเดียว ทยอยซื้อ หรือตามเทรนด์", go: "ลองลงทุนย้อนหลัง" },
]

export default function HomeSections({ onRegister, onLogin, onOpenCoin, onGo, heroTitle, heroSub, heroArt }: Props) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [sparks, setSparks] = useState<Record<string, number[]>>({})

  useEffect(() => {
    let alive = true
    const load = () =>
      fetch(`${API_BASE_URL}/api/public/markets`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((d) => {
          if (!alive) return
          setRows(Array.isArray(d.rows) ? d.rows.slice(0, 5) : [])
          setSparks(d.sparks ?? {})
        })
        .catch(() => alive && setRows((p) => p ?? []))
    load()
    const id = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  return (
    <>
      {/* HERO */}
      <section className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-16 lg:grid-cols-2 lg:py-24">
        <div>
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{heroTitle}</h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground">{heroSub}</p>
          <button
            type="button"
            onClick={onRegister}
            className="mt-8 rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
          >
            สมัครตอนนี้
          </button>
        </div>
        <div className="flex justify-center lg:justify-end">{heroArt}</div>
      </section>

      {/* ตลาด */}
      <section className="mx-auto max-w-4xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">ตลาด</h2>
        <p className="mt-2 text-center text-sm text-muted-foreground">ราคาสดเป็นสกุลเงินบาท อัปเดตอัตโนมัติ</p>

        <div className="mt-8 overflow-hidden rounded-2xl border">
          <div className="grid grid-cols-[1.4fr_1fr_0.8fr_0.8fr] gap-2 bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
            <span>ชื่อ</span>
            <span className="text-right">ราคาล่าสุด</span>
            <span className="text-right">เปลี่ยนแปลง 24 ชม.</span>
            <span className="text-right">แนวโน้ม 7 วัน</span>
          </div>
          {rows === null && <p className="px-4 py-8 text-center text-sm text-muted-foreground">กำลังโหลด…</p>}
          {rows?.length === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">โหลดราคาไม่สำเร็จ</p>}
          {rows?.map((r) => {
            const up = r.change >= 0
            const sp = sparks[r.asset] ?? []
            return (
              <button
                key={r.asset}
                type="button"
                onClick={() => onOpenCoin(r.asset)}
                className="grid w-full grid-cols-[1.4fr_1fr_0.8fr_0.8fr] items-center gap-2 border-t px-4 py-3 text-left text-sm hover:bg-accent"
              >
                <span>
                  <span className="font-semibold">{r.asset}</span>{" "}
                  <span className="text-xs text-muted-foreground">{r.name}</span>
                </span>
                <span className="text-right font-semibold">฿{fmtPrice(r.price)}</span>
                <span className={`text-right font-semibold ${up ? "text-emerald-500" : "text-red-500"}`}>
                  {up ? "+" : ""}
                  {r.change.toFixed(2)}%
                </span>
                <span className="flex justify-end">
                  <Spark data={sp} up={sp.length > 1 ? sp[sp.length - 1] >= sp[0] : up} />
                </span>
              </button>
            )
          })}
        </div>
        <div className="mt-4 text-center">
          <button type="button" onClick={() => onGo("ตลาด")} className="text-sm text-muted-foreground hover:text-foreground">
            ดูเพิ่มเติม ›
          </button>
        </div>
      </section>

      {/* ทำไมต้อง Nobodi */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">ทำไมต้อง Nobodi?</h2>
        <p className="mt-2 text-center text-sm text-muted-foreground">
          เริ่มต้นเรียนรู้ตลาดคริปโตได้อย่างเป็นขั้นเป็นตอน โดยไม่ต้องใช้เงินจริง
        </p>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {WHY.map((w) => {
            const Icon = w.icon
            return (
              <div key={w.title} className="rounded-2xl border p-6 text-center">
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
                  <Icon className="h-6 w-6" />
                </span>
                <h3 className="mt-4 text-lg font-bold">{w.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{w.text}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* เริ่มต้นใน 3 ขั้น */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">เริ่มต้นง่าย ๆ ใน 3 ขั้นตอน</h2>
        <div className="mt-8 grid items-center gap-8 lg:grid-cols-[1fr_320px]">
          <ol className="space-y-6">
            {STEPS.map((s, i) => {
              const Icon = s.icon
              return (
                <li key={s.title} className="flex gap-4">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
                    <Icon className="h-6 w-6" />
                  </span>
                  <div>
                    <p className="text-lg font-bold">
                      {i + 1}. {s.title}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
                  </div>
                </li>
              )
            })}
            <li>
              <button
                type="button"
                onClick={onRegister}
                className="rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
              >
                สมัครตอนนี้
              </button>
            </li>
          </ol>

          {/* ภาพประกอบ SVG วาดเอง */}
          <svg viewBox="0 0 320 240" className="mx-auto h-auto w-full max-w-xs" aria-hidden="true">
            <rect x="10" y="10" width="300" height="220" rx="24" className="fill-muted/40 stroke-border" />
            <rect x="40" y="150" width="30" height="50" rx="5" className="fill-emerald-500/40" />
            <rect x="90" y="120" width="30" height="80" rx="5" className="fill-emerald-500/60" />
            <rect x="140" y="95" width="30" height="105" rx="5" className="fill-emerald-500/80" />
            <rect x="190" y="70" width="30" height="130" rx="5" className="fill-emerald-500" />
            <polyline
              points="55,140 105,110 155,85 205,55 265,38"
              fill="none"
              strokeWidth={3}
              strokeDasharray="6 6"
              strokeLinecap="round"
              className="stroke-foreground/50"
            />
            <circle cx="265" cy="38" r="8" className="fill-emerald-500" />
          </svg>
        </div>
      </section>

      {/* เครื่องมือ */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">เครื่องมือที่ช่วยให้ตัดสินใจได้ดีขึ้น</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {TOOLS.map((t) => {
            const Icon = t.icon
            return (
              <button
                key={t.title}
                type="button"
                onClick={() => onGo(t.go)}
                className="rounded-2xl border p-6 text-left transition-colors hover:bg-accent"
              >
                <Icon className="h-6 w-6 text-emerald-500" />
                <h3 className="mt-4 text-lg font-bold">{t.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{t.text}</p>
                <span className="mt-4 inline-block text-sm text-emerald-500">เปิดดู ›</span>
              </button>
            )
          })}
        </div>
      </section>

      {/* ปิดท้าย + footer */}
      <section className="mx-auto max-w-4xl px-4 py-16 text-center">
        <h2 className="text-3xl font-extrabold tracking-tight">พร้อมลองแล้วหรือยัง?</h2>
        <p className="mt-2 text-sm text-muted-foreground">สมัครฟรี ใช้บัญชี Google ของคุณได้เลย</p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={onRegister}
            className="rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
          >
            สมัครตอนนี้
          </button>
          <button type="button" onClick={onLogin} className="rounded-lg border px-6 py-3 text-sm font-semibold hover:bg-accent">
            เข้าสู่ระบบ
          </button>
        </div>
      </section>

      <footer className="border-t">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm md:grid-cols-4">
          <div>
            <p className="text-lg font-extrabold">Nobodi</p>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">แพลตฟอร์มฝึกลงทุนคริปโตด้วยบัญชีจำลอง</p>
          </div>
          <div>
            <p className="font-semibold">สินค้า</p>
            <ul className="mt-3 space-y-2 text-muted-foreground">
              {["ตลาด", "ข่าว", "ลองลงทุนย้อนหลัง"].map((l) => (
                <li key={l}>
                  <button type="button" onClick={() => onGo(l)} className="hover:text-foreground">
                    {l}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="font-semibold">เริ่มใช้งาน</p>
            <ul className="mt-3 space-y-2 text-muted-foreground">
              <li>
                <button type="button" onClick={onRegister} className="hover:text-foreground">
                  สมัครสมาชิก
                </button>
              </li>
              <li>
                <button type="button" onClick={onLogin} className="hover:text-foreground">
                  เข้าสู่ระบบ
                </button>
              </li>
            </ul>
          </div>
          <div>
            <p className="font-semibold">ข้อควรรู้</p>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              การลงทุนในสินทรัพย์ดิจิทัลมีความเสี่ยงสูง ผลย้อนหลังไม่ได้รับประกันผลตอบแทนในอนาคต
              และบัญชีของเราเป็นบัญชีจำลองเพื่อการเรียนรู้เท่านั้น
            </p>
          </div>
        </div>
        <p className="border-t py-4 text-center text-xs text-muted-foreground">© Nobodi</p>
      </footer>
    </>
  )
}
