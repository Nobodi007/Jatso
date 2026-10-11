import { useEffect } from "react"
import type { LucideIcon } from "lucide-react"
import {
  AlertTriangle, ArrowLeft, ArrowLeftRight, BookOpen, Bot, Briefcase, FlaskConical, Layers,
  LayoutDashboard, Lightbulb, LineChart, ListOrdered, Newspaper, RefreshCw, Settings, ShieldAlert, Wallet,
} from "lucide-react"

type Mod = { id: string; icon: LucideIcon; name: string; th: string; text: string; points?: string[]; tip?: string }
type Group = { id: string; title: string; mods: Mod[] }

const GROUPS: Group[] = [
  {
    id: "g-view", title: "ดูข้อมูลตลาด",
    mods: [
      { id: "dashboard", icon: LayoutDashboard, name: "Dashboard", th: "ภาพรวม",
        text: "หน้าแรกหลังเข้าสู่ระบบ ดูสถานะพอร์ตทั้งหมดได้ในหน้าเดียว",
        points: ["มูลค่าพอร์ต", "เงินสด", "สินทรัพย์ที่ถือ", "กำไร/ขาดทุน", "รายการซื้อขายล่าสุด"],
        tip: "ข้อมูลรีเฟรชเองทุก 10 วินาที ไม่ต้องกดรีโหลดหน้า" },
      { id: "markets", icon: LineChart, name: "Markets", th: "ตลาด",
        text: "ดูราคาล่าสุดและการเปลี่ยนแปลงของทุกเหรียญที่ระบบรองรับ ราคาทั้งหมดเป็นเงินบาท",
        points: ["ราคาล่าสุด", "% เปลี่ยนแปลง 24 ชม.", "ราคาสูงสุด/ต่ำสุด"],
        tip: "ถ้าเซิร์ฟเวอร์ของเราขัดข้อง ระบบจะดึงราคาจาก Bitkub มาแสดงแทนให้อัตโนมัติ" },
      { id: "orderbook", icon: BookOpen, name: "Order Book", th: "สมุดคำสั่งซื้อขาย",
        text: "ดูว่าตอนนี้มีคนตั้งซื้อและตั้งขายไว้ที่ราคาเท่าไหร่ จำนวนเท่าไหร่ เลือกเหรียญที่ต้องการดูได้",
        points: ["Best Bid", "Best Ask", "Mid Price", "Spread", "Spread %", "ปริมาณแต่ละระดับราคา"],
        tip: "Spread ยิ่งแคบ ราคาซื้อกับราคาขายยิ่งใกล้กัน ต้นทุนแฝงก็ยิ่งต่ำ ดูความหมายคำศัพท์ได้ท้ายหน้า" },
      { id: "news", icon: Newspaper, name: "News", th: "ข่าว",
        text: "รวมข่าวคริปโตล่าสุดจากหลายสำนักไว้ในที่เดียว",
        tip: "ข่าวใช้ประกอบการติดตามตลาดเท่านั้น ไม่ใช่สัญญาณให้ซื้อหรือขาย" },
    ],
  },
  {
    id: "g-trade", title: "ซื้อขาย",
    mods: [
      { id: "trade", icon: ArrowLeftRight, name: "Trade", th: "ซื้อขาย",
        text: "เลือกเหรียญ ใส่รายละเอียดคำสั่ง แล้วกดส่ง พอคำสั่งสำเร็จ ระบบจะอัปเดตพอร์ตให้ทันที",
        points: ["เลือกเหรียญ", "ใส่จำนวน", "กดซื้อหรือขาย"],
        tip: "เช็กเงินสดใน Wallet ก่อนส่งคำสั่งทุกครั้ง" },
      { id: "orders", icon: ListOrdered, name: "Orders", th: "ประวัติคำสั่ง",
        text: "ดูคำสั่งซื้อขายย้อนหลัง เรียงจากรายการล่าสุดลงไป",
        tip: "รายการใหม่จะขึ้นเองภายใน 10 วินาที" },
      { id: "positions", icon: Layers, name: "Positions", th: "สถานะการถือครอง",
        text: "ดูว่าตอนนี้ถือเหรียญอะไรอยู่บ้าง และแต่ละเหรียญมีสถานะอย่างไร" },
    ],
  },
  {
    id: "g-money", title: "พอร์ตและเงิน",
    mods: [
      { id: "portfolio", icon: Briefcase, name: "Portfolio", th: "พอร์ตการลงทุน",
        text: "ดูรายละเอียดสินทรัพย์ทุกตัวในพอร์ต ว่าซื้อมาเท่าไหร่ ตอนนี้มีมูลค่าเท่าไหร่ และกำไรหรือขาดทุนอยู่",
        points: ["จำนวนที่ถือ", "ต้นทุนเฉลี่ย", "มูลค่าตลาด", "กำไร/ขาดทุนที่ยังไม่ขาย", "P&L %", "สัดส่วนในพอร์ต"] },
      { id: "wallet", icon: Wallet, name: "Wallet", th: "กระเป๋าเงิน",
        text: "ดูเงินสด มูลค่าสินทรัพย์ ยอดรวมพอร์ต และค่าธรรมเนียมที่จ่ายไปแล้ว",
        tip: "ดูหน้านี้ก่อนซื้อขาย จะได้รู้ว่ามีเงินสดพอหรือไม่" },
    ],
  },
  {
    id: "g-tools", title: "เครื่องมือวิเคราะห์",
    mods: [
      { id: "risk", icon: ShieldAlert, name: "Risk Center", th: "ศูนย์ความเสี่ยง",
        text: "ดูตัวชี้วัดความเสี่ยงที่คำนวณจากพอร์ตของคุณ ช่วยให้เห็นว่าพอร์ตเสี่ยงแค่ไหน" },
      { id: "quant", icon: FlaskConical, name: "Quant Lab", th: "ห้องทดลองเชิงตัวเลข",
        text: "เครื่องมือวิเคราะห์ข้อมูลเชิงสถิติ ไว้ทดลองแนวคิดก่อนนำไปใช้จริง" },
      { id: "ai", icon: Bot, name: "AI Assistant", th: "ผู้ช่วย AI",
        text: "กดไอคอนผู้ช่วยแล้วพิมพ์คำถามได้เลย ผู้ช่วยจำบทสนทนาก่อนหน้าได้บางส่วน จึงถามต่อเนื่องได้",
        tip: "คำตอบของ AI อาจผิดพลาดได้ ควรตรวจสอบก่อนตัดสินใจ" },
    ],
  },
  {
    id: "g-settings", title: "ตั้งค่า",
    mods: [
      { id: "settings", icon: Settings, name: "Settings", th: "ตั้งค่า",
        text: "เปลี่ยนธีมมืดหรือสว่าง ระบบจำค่าที่เลือกไว้ในเบราว์เซอร์ เปิดครั้งหน้าก็ยังเป็นธีมเดิม" },
    ],
  },
]

const QUICK = [
  { id: "dashboard", title: "ดูภาพรวม", text: "เริ่มที่ Dashboard ดูสถานะพอร์ต" },
  { id: "markets", title: "เช็กราคา", text: "เข้า Markets ดูราคาล่าสุด" },
  { id: "orderbook", title: "ดู Spread", text: "เปิด Order Book ดูราคาเสนอซื้อ/ขาย" },
  { id: "trade", title: "ส่งคำสั่ง", text: "ซื้อหรือขายในหน้า Trade" },
  { id: "portfolio", title: "ตรวจพอร์ต", text: "ดู Portfolio และ Wallet หลังทำรายการ" },
  { id: "orders", title: "ดูประวัติ", text: "ย้อนดูรายการใน Orders" },
]

const GLOSSARY = [
  { term: "Best Bid", def: "ราคาสูงสุดที่มีคนตั้งรอซื้ออยู่ตอนนี้" },
  { term: "Best Ask", def: "ราคาต่ำสุดที่มีคนตั้งรอขายอยู่ตอนนี้" },
  { term: "Mid Price", def: "ราคากึ่งกลางระหว่าง Best Bid กับ Best Ask" },
  { term: "Spread", def: "ส่วนต่างระหว่าง Best Ask กับ Best Bid ยิ่งแคบยิ่งดี" },
  { term: "Spread %", def: "Spread คิดเป็นเปอร์เซ็นต์ของราคา ใช้เทียบข้ามเหรียญได้" },
  { term: "Average Cost", def: "ต้นทุนเฉลี่ยต่อเหรียญ จากการซื้อทุกครั้งรวมกัน" },
  { term: "Market Value", def: "มูลค่าของเหรียญที่ถือ คิดจากราคาตลาดตอนนี้" },
  { term: "Unrealized P&L", def: "กำไรหรือขาดทุนบนกระดาษ ยังไม่เกิดจริงจนกว่าจะขาย" },
]

const REFRESH = [
  { name: "Portfolio / Dashboard", every: "ทุก 10 วินาที" },
  { name: "Orders", every: "ทุก 10 วินาที" },
]

const SCOPE = [
  "ทุกการซื้อขายเกิดในบัญชีจำลองเพื่อการเรียนรู้ ไม่ได้ใช้เงินจริง",
  "ราคาตลาดอาจช้ากว่าราคาจริงเล็กน้อย หรือขาดหายชั่วคราวตามข้อจำกัดของผู้ให้บริการข้อมูล",
  "ผลลัพธ์ในระบบไม่ใช่คำแนะนำการลงทุน และไม่รับประกันผลตอบแทนในอนาคต",
]

const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })

function IconBox({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
      <Icon className="h-5 w-5" />
    </span>
  )
}

function ModCard({ m }: { m: Mod }) {
  return (
    <div id={m.id} className="scroll-mt-24 rounded-2xl border p-6">
      <div className="flex items-start gap-4">
        <IconBox icon={m.icon} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <h3 className="text-lg font-bold">{m.name}</h3>
            <span className="text-sm text-muted-foreground">{m.th}</span>
          </div>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">{m.text}</p>
          {m.points && (
            <div className="mt-4 flex flex-wrap gap-2">
              {m.points.map((p) => (
                <span key={p} className="rounded-full border bg-muted/40 px-3 py-1 text-xs font-medium">{p}</span>
              ))}
            </div>
          )}
          {m.tip && (
            <div className="mt-4 flex gap-2 rounded-xl bg-emerald-500/10 p-3 text-sm leading-6 text-emerald-700 dark:text-emerald-400">
              <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{m.tip}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function UserGuide({ onBack }: { onBack: () => void }) {
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4">
      <div className="pt-10">
        <button type="button" onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> กลับหน้าแรก
        </button>
      </div>

      {/* หัวหน้า */}
      <header className="py-12">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">
          คู่มือการใช้งาน
        </span>
        <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">ใช้งานระบบอย่างไร</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
          รวมวิธีใช้ทุกเมนู ตั้งแต่ดูราคา ส่งคำสั่งซื้อขายในบัญชีจำลอง ไปจนถึงตรวจพอร์ตและวิเคราะห์ความเสี่ยง
        </p>
      </header>

      {/* เริ่มต้น 6 ขั้น */}
      <section className="pb-12">
        <h2 className="text-2xl font-extrabold tracking-tight">เริ่มต้นใน 6 ขั้น</h2>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {QUICK.map((q, i) => (
            <button key={q.id} type="button" onClick={() => jump(q.id)}
              className="flex items-center gap-4 rounded-2xl border p-4 text-left transition-colors hover:bg-accent">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-sm font-bold text-black">
                {i + 1}
              </span>
              <span>
                <span className="block font-bold">{q.title}</span>
                <span className="block text-xs text-muted-foreground">{q.text}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-10 pb-16 lg:grid-cols-[200px_1fr]">
        {/* สารบัญ */}
        <aside className="hidden lg:block">
          <nav className="sticky top-24 space-y-5 text-sm">
            {GROUPS.map((g) => (
              <div key={g.id}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-emerald-500">{g.title}</p>
                <ul className="space-y-1.5">
                  {g.mods.map((m) => (
                    <li key={m.id}>
                      <button type="button" onClick={() => jump(m.id)} className="text-muted-foreground hover:text-foreground">
                        {m.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <div className="space-y-1.5 border-t pt-4">
              <button type="button" onClick={() => jump("glossary")} className="block text-muted-foreground hover:text-foreground">คำศัพท์ที่ควรรู้</button>
              <button type="button" onClick={() => jump("refresh")} className="block text-muted-foreground hover:text-foreground">การอัปเดตข้อมูล</button>
              <button type="button" onClick={() => jump("scope")} className="block text-muted-foreground hover:text-foreground">ขอบเขตการใช้งาน</button>
            </div>
          </nav>
        </aside>

        <div className="min-w-0 space-y-12">
          {/* แต่ละหมวด */}
          {GROUPS.map((g) => (
            <section key={g.id} id={g.id} className="scroll-mt-24">
              <h2 className="text-2xl font-extrabold tracking-tight">{g.title}</h2>
              <div className="mt-5 space-y-4">
                {g.mods.map((m) => <ModCard key={m.id} m={m} />)}
              </div>
            </section>
          ))}

          {/* คำศัพท์ */}
          <section id="glossary" className="scroll-mt-24">
            <h2 className="text-2xl font-extrabold tracking-tight">คำศัพท์ที่ควรรู้</h2>
            <div className="mt-5 overflow-hidden rounded-2xl border">
              {GLOSSARY.map((g, i) => (
                <div key={g.term} className={`grid gap-1 px-5 py-4 sm:grid-cols-[160px_1fr] sm:gap-4 ${i ? "border-t" : ""}`}>
                  <span className="font-semibold">{g.term}</span>
                  <span className="text-sm leading-6 text-muted-foreground">{g.def}</span>
                </div>
              ))}
            </div>
          </section>

          {/* การอัปเดตข้อมูล */}
          <section id="refresh" className="scroll-mt-24">
            <h2 className="text-2xl font-extrabold tracking-tight">การอัปเดตข้อมูล</h2>
            <div className="mt-5 rounded-2xl border p-6">
              <div className="flex items-center gap-2 font-bold">
                <RefreshCw className="h-5 w-5 text-emerald-500" /> รีเฟรชอัตโนมัติ
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {REFRESH.map((r) => (
                  <div key={r.name} className="flex items-center justify-between rounded-xl bg-muted/40 px-4 py-3 text-sm">
                    <span>{r.name}</span>
                    <span className="font-semibold text-emerald-500">{r.every}</span>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-sm leading-6 text-muted-foreground">
                ระบบจะหยุดรีเฟรชเมื่อคุณสลับไปแท็บอื่น และกลับมารีเฟรชต่อเมื่อเปิดหน้าเว็บอีกครั้ง เพื่อไม่ให้โหลดข้อมูลโดยไม่จำเป็น
              </p>
            </div>
          </section>

          {/* ขอบเขต */}
          <section id="scope" className="scroll-mt-24">
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
      </div>
    </div>
  )
}
