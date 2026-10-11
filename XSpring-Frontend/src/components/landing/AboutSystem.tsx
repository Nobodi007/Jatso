import { Fragment, useEffect } from "react"
import type { LucideIcon } from "lucide-react"
import {
  AlertTriangle, ArrowDown, ArrowLeft, ArrowLeftRight, ArrowRight, BookOpen, Bot, Briefcase, Database,
  FlaskConical, Layers, LayoutDashboard, LineChart, ListOrdered, Lock, Monitor, Newspaper, Palette,
  RefreshCw, Server, Settings, ShieldCheck, Wallet,
} from "lucide-react"

type Item = { icon: LucideIcon; title: string; text: string }

const STATS = [
  { value: "12", label: "ระบบหลักในแอป" },
  { value: "10 วิ", label: "รีเฟรชพอร์ตอัตโนมัติ" },
  { value: "100%", label: "บัญชีจำลอง ไม่ใช้เงินจริง" },
]

const FLOW: Item[] = [
  { icon: Monitor, title: "หน้าจอ React", text: "ผู้ใช้ดูข้อมูลหรือส่งคำสั่ง" },
  { icon: Layers, title: "สถานะในหน้าเว็บ", text: "เก็บข้อมูลที่ใช้แสดงผล" },
  { icon: Server, title: "Backend API", text: "ประมวลผลและตอบกลับ" },
  { icon: Database, title: "พอร์ต / คำสั่ง / ราคา", text: "ส่งกลับมาแสดงบนหน้าจอ" },
]

const MODULES: Item[] = [
  { icon: LayoutDashboard, title: "Dashboard", text: "ภาพรวมพอร์ต มูลค่าสินทรัพย์ กำไรขาดทุน และคำสั่งล่าสุด" },
  { icon: LineChart, title: "Markets", text: "ราคาตลาดสดเป็นเงินบาท มีแหล่งข้อมูลสำรองเมื่อระบบหลักขัดข้อง" },
  { icon: ArrowLeftRight, title: "Trade", text: "ส่งคำสั่งซื้อขายในบัญชีจำลอง แล้วอัปเดตพอร์ตให้ทันที" },
  { icon: BookOpen, title: "Order Book", text: "ราคาเสนอซื้อ/ขาย, Best Bid, Best Ask, Mid Price และ Spread" },
  { icon: Briefcase, title: "Portfolio", text: "สินทรัพย์ที่ถือ ต้นทุน มูลค่าปัจจุบัน และกำไรขาดทุน" },
  { icon: Wallet, title: "Wallet", text: "เงินสด มูลค่าสินทรัพย์ ยอดรวมพอร์ต และค่าธรรมเนียม" },
  { icon: ListOrdered, title: "Orders", text: "ประวัติคำสั่งซื้อขาย เรียงตามเวลาล่าสุด" },
  { icon: Layers, title: "Positions", text: "สถานะการถือครองของแต่ละสินทรัพย์" },
  { icon: ShieldCheck, title: "Risk Center", text: "เครื่องมือวิเคราะห์ความเสี่ยงของพอร์ต" },
  { icon: FlaskConical, title: "Quant Lab", text: "เครื่องมือวิเคราะห์เชิงปริมาณและทดสอบกลยุทธ์" },
  { icon: Newspaper, title: "News", text: "ข่าวคริปโตล่าสุดจากหลายแหล่ง" },
  { icon: Settings, title: "Settings", text: "ตั้งค่าการใช้งานของระบบ" },
]

const STACK = [
  { group: "สร้างหน้าเว็บ", items: ["React 19", "TypeScript", "Vite", "Tailwind CSS 4", "Radix UI / shadcn", "Lucide React", "Lightweight Charts"] },
  { group: "เชื่อมต่อข้อมูล", items: ["XSpring Backend API", "Bitkub API", "RSS-to-JSON API", "Google OAuth"] },
]

const DATA_FLOW = [
  { title: "พอร์ตการลงทุน", tag: "GET /api/portfolio", refresh: "ทุก 10 วินาที",
    text: "ดึงเงินสด มูลค่าสินทรัพย์ ต้นทุน กำไรขาดทุน และค่าธรรมเนียม แล้วส่งต่อให้ Dashboard, Wallet และ Portfolio ใช้ร่วมกัน จะโหลดใหม่เฉพาะตอนที่เปิดหน้าเว็บอยู่" },
  { title: "ราคาตลาด", tag: "Backend → สำรอง Bitkub", refresh: "",
    text: "ดึงราคาจากเซิร์ฟเวอร์ของเราก่อน ถ้าไม่สำเร็จจะดึงจาก Bitkub โดยตรงแทน ราคาจึงยังแสดงได้" },
  { title: "Order Book", tag: "GET /api/orderbook", refresh: "",
    text: "ระบุเหรียญและจำนวนระดับราคาที่ต้องการ แล้วแสดงผลเป็นฝั่งเสนอซื้อและเสนอขาย" },
  { title: "ประวัติคำสั่ง", tag: "GET /api/orders", refresh: "ทุก 10 วินาที",
    text: "ดึงคำสั่งซื้อขายล่าสุด 100 รายการ และรีเฟรชอัตโนมัติขณะที่เปิดหน้าเว็บอยู่" },
  { title: "ผู้ช่วย AI", tag: "POST /api/chat", refresh: "",
    text: "ส่งคำถามพร้อมประวัติการสนทนาไปที่เซิร์ฟเวอร์ แล้วแสดงคำตอบในหน้าต่างผู้ช่วย" },
]

const SECURITY: Item[] = [
  { icon: Lock, title: "เข้าสู่ระบบด้วย Google", text: "ยืนยันตัวตนผ่านบัญชี Google และแนบสิทธิ์การใช้งานไปกับทุกคำขอ" },
  { icon: ShieldCheck, title: "จัดการข้อผิดพลาด", text: "ตรวจผลตอบกลับทุกครั้ง และแจ้งผู้ใช้เมื่อโหลดข้อมูลไม่สำเร็จ" },
  { icon: RefreshCw, title: "ไม่มีข้อมูลค้าง", text: "ยกเลิกการอัปเดตเมื่อออกจากหน้า กันไม่ให้ข้อมูลเก่ามาทับข้อมูลใหม่" },
  { icon: Palette, title: "จำธีมที่เลือก", text: "บันทึกโหมดมืดหรือสว่างไว้ในเครื่อง เปิดครั้งหน้าก็ยังเป็นธีมเดิม" },
  { icon: Server, title: "แยกหน้าเว็บกับเซิร์ฟเวอร์", text: "การคำนวณพอร์ตและคำสั่งซื้อขายทำที่เซิร์ฟเวอร์ ไม่ได้คำนวณในเบราว์เซอร์" },
  { icon: Bot, title: "ผู้ช่วย AI ผ่านเซิร์ฟเวอร์", text: "คำถามถูกส่งผ่านเซิร์ฟเวอร์ของเรา ไม่ได้ต่อกับผู้ให้บริการ AI จากเบราว์เซอร์โดยตรง" },
]

const SCOPE = [
  "เป็นบัญชีจำลองเพื่อการเรียนรู้ ไม่มีการซื้อขายด้วยเงินจริง",
  "ข้อมูลบางส่วนบนหน้าเว็บเป็นข้อมูลตัวอย่าง ไม่ใช่ราคาสด",
  "บางเมนู เช่น Risk Center, Quant Lab และ Settings ยังอยู่ระหว่างพัฒนา ฟังก์ชันอาจยังไม่ครบ",
  "ข้อมูลและผลลัพธ์ในระบบไม่ใช่คำแนะนำการลงทุน",
]

function Section({ eyebrow, title, desc, children }: { eyebrow: string; title: string; desc?: string; children: React.ReactNode }) {
  return (
    <section className="py-12">
      <p className="text-xs font-semibold uppercase tracking-widest text-emerald-500">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h2>
      {desc && <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">{desc}</p>}
      <div className="mt-8">{children}</div>
    </section>
  )
}

function IconBox({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
      <Icon className="h-5 w-5" />
    </span>
  )
}

export default function AboutSystem({ onBack }: { onBack: () => void }) {
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4">
      {/* หัวหน้า */}
      <div className="pt-10">
        <button type="button" onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> กลับหน้าแรก
        </button>
      </div>

      <header className="py-12">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">
          เกี่ยวกับระบบ
        </span>
        <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
          XSpring Dealer Suite
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
          ระบบหน้าเว็บสำหรับดูตลาด ฝึกซื้อขายในบัญชีจำลอง จัดการพอร์ต วิเคราะห์ความเสี่ยง
          และใช้เครื่องมือวิจัย ทั้งหมดในที่เดียว
        </p>
        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {STATS.map((s) => (
            <div key={s.label} className="rounded-2xl border p-5">
              <p className="text-3xl font-extrabold text-emerald-500">{s.value}</p>
              <p className="mt-1 text-sm text-muted-foreground">{s.label}</p>
            </div>
          ))}
        </div>
      </header>

      {/* ระบบนี้คืออะไร */}
      <Section eyebrow="ภาพรวม" title="ระบบนี้ทำงานอย่างไร"
        desc="หน้าเว็บมีหน้าที่แสดงผลและรับคำสั่งจากผู้ใช้ ส่วนการคำนวณพอร์ตและการบันทึกคำสั่งซื้อขายทำที่เซิร์ฟเวอร์ แล้วส่งผลกลับมาแสดงบนหน้าจอ">
        <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
          {FLOW.map((f, i) => (
            <Fragment key={f.title}>
              <div className="flex flex-1 items-center gap-3 rounded-2xl border p-4">
                <IconBox icon={f.icon} />
                <div>
                  <p className="text-sm font-bold">{f.title}</p>
                  <p className="text-xs text-muted-foreground">{f.text}</p>
                </div>
              </div>
              {i < FLOW.length - 1 && (
                <div className="flex justify-center text-muted-foreground">
                  <ArrowDown className="h-5 w-5 md:hidden" />
                  <ArrowRight className="hidden h-5 w-5 md:block" />
                </div>
              )}
            </Fragment>
          ))}
        </div>
      </Section>

      {/* ระบบหลัก */}
      <Section eyebrow="ฟีเจอร์" title="ระบบหลักในแอป">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((m) => (
            <div key={m.title} className="flex gap-4 rounded-2xl border p-5 transition-colors hover:bg-accent">
              <IconBox icon={m.icon} />
              <div>
                <p className="font-bold">{m.title}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{m.text}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* เทคโนโลยี */}
      <Section eyebrow="เทคโนโลยี" title="สร้างด้วยอะไร">
        <div className="grid gap-4 md:grid-cols-2">
          {STACK.map((g) => (
            <div key={g.group} className="rounded-2xl border p-6">
              <p className="text-sm font-bold">{g.group}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {g.items.map((t) => (
                  <span key={t} className="rounded-full border bg-muted/40 px-3 py-1 text-xs font-medium">{t}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* ข้อมูลไหลอย่างไร */}
      <Section eyebrow="การไหลของข้อมูล" title="ข้อมูลเดินทางอย่างไร">
        <ol className="relative space-y-6 border-l pl-8">
          {DATA_FLOW.map((d, i) => (
            <li key={d.title} className="relative">
              <span className="absolute -left-[45px] flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-xs font-bold text-black">
                {i + 1}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-bold">{d.title}</p>
                <code className="rounded-md bg-muted px-2 py-0.5 text-xs">{d.tag}</code>
                {d.refresh && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-500">
                    <RefreshCw className="h-3 w-3" /> {d.refresh}
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{d.text}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* ความปลอดภัย */}
      <Section eyebrow="ความปลอดภัย" title="การดูแลความปลอดภัยและข้อผิดพลาด">
        <div className="grid gap-4 md:grid-cols-2">
          {SECURITY.map((s) => (
            <div key={s.title} className="flex gap-4 rounded-2xl border p-5">
              <IconBox icon={s.icon} />
              <div>
                <p className="font-bold">{s.title}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{s.text}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* ขอบเขต */}
      <section className="pb-16 pt-4">
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6">
          <div className="flex items-center gap-2 text-amber-500">
            <AlertTriangle className="h-5 w-5" />
            <p className="font-bold">ขอบเขตการใช้งาน</p>
          </div>
          <ul className="mt-4 space-y-2">
            {SCOPE.map((s) => (
              <li key={s} className="flex gap-2 text-sm leading-6 text-muted-foreground">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                {s}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  )
}
