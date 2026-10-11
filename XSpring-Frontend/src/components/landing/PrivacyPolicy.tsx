import { useEffect } from "react"
import type { LucideIcon } from "lucide-react"
import {
  AlertTriangle, ArrowLeft, Ban, Bot, Check, Cloud, Database, Globe, Monitor, ShieldCheck, Trash2, User,
} from "lucide-react"

type Item = { icon: LucideIcon; title: string; text: string }

const SUMMARY = [
  { icon: ShieldCheck, title: "บัญชีจำลอง", text: "ระบบไม่ได้ใช้เงินจริง ข้อมูลพอร์ตทั้งหมดเป็นการจำลองเพื่อการเรียนรู้" },
  { icon: User, title: "ใช้ข้อมูลเท่าที่จำเป็น", text: "ใช้ข้อมูลบัญชี Google พื้นฐานเพื่อยืนยันตัวตนและแสดงชื่อ" },
  { icon: Ban, title: "ไม่ขอข้อมูลลับ", text: "ระบบไม่เคยขอรหัสผ่าน หรือกุญแจกระเป๋าเงินของคุณ" },
]

const DATA: Item[] = [
  { icon: User, title: "ข้อมูลบัญชี",
    text: "อีเมล ชื่อ รูปโปรไฟล์ และสิทธิ์การใช้งานของบัญชี ได้จากการเข้าสู่ระบบด้วย Google ใช้เพื่อยืนยันตัวตนและแสดงในเมนูผู้ใช้" },
  { icon: Database, title: "พอร์ตและคำสั่งซื้อขายจำลอง",
    text: "เงินสดจำลอง เหรียญที่ถือ ต้นทุน กำไรขาดทุน ค่าธรรมเนียม ประวัติคำสั่ง และแผน Auto DCA ที่คุณตั้งไว้ เก็บบนเซิร์ฟเวอร์ของระบบเพื่อให้เปิดดูได้ทุกครั้งที่เข้าสู่ระบบ" },
  { icon: Bot, title: "ข้อความที่คุยกับผู้ช่วย AI",
    text: "ข้อความที่คุณพิมพ์และบทสนทนาก่อนหน้าบางส่วนจะถูกส่งไปประมวลผลเพื่อให้ผู้ช่วยตอบได้ต่อเนื่อง" },
  { icon: Monitor, title: "การตั้งค่าในเบราว์เซอร์",
    text: "ธีมมืด/สว่าง และรายการเหรียญโปรด เก็บไว้ในเบราว์เซอร์ของคุณเอง เพื่อให้เปิดครั้งหน้าเป็นแบบเดิม" },
]

const WHERE = [
  { place: "เบราว์เซอร์ของคุณ", what: "ธีม รายการโปรด และข้อมูลที่แสดงบนหน้าจอระหว่างใช้งาน", persist: "ค้างอยู่จนกว่าคุณจะล้างข้อมูลเว็บไซต์" },
  { place: "เซิร์ฟเวอร์ของระบบ", what: "พอร์ตจำลอง ประวัติคำสั่ง แผน Auto DCA และข้อมูลบัญชีที่จำเป็น", persist: "เก็บเพื่อให้ใช้งานต่อเนื่องข้ามอุปกรณ์" },
]

const THIRD: Item[] = [
  { icon: Globe, title: "ผู้ให้บริการข้อมูลราคา", text: "ราคาและข้อมูลตลาดมาจากแหล่งข้อมูลตลาดภายนอก (เช่น Bitkub) ซึ่งอาจบันทึกข้อมูลการเชื่อมต่อทั่วไปตามนโยบายของเขา" },
  { icon: Globe, title: "แหล่งข่าว", text: "ข่าวถูกดึงจากสำนักข่าวคริปโตภายนอกผ่านบริการแปลงข้อมูลข่าว" },
  { icon: User, title: "Google", text: "ใช้สำหรับเข้าสู่ระบบ ระบบได้รับเฉพาะข้อมูลโปรไฟล์พื้นฐานที่ Google ส่งให้ ไม่ได้รับรหัสผ่านของคุณ" },
  { icon: Bot, title: "ผู้ให้บริการ AI", text: "ข้อความที่ส่งให้ผู้ช่วย AI ถูกประมวลผลโดยผู้ให้บริการด้านโมเดลภาษาที่ระบบใช้" },
]

const DONT = ["รหัสผ่าน", "Private Key หรือ Seed Phrase", "API Secret / Token", "ข้อมูลส่วนตัวที่อ่อนไหว เช่น เลขบัตรประชาชน"]

const NAV = [
  { id: "p-data", label: "ข้อมูลที่ใช้" },
  { id: "p-where", label: "เก็บที่ไหน" },
  { id: "p-third", label: "บริการภายนอก" },
  { id: "p-dont", label: "ข้อมูลที่ไม่ควรส่ง" },
  { id: "p-control", label: "ควบคุมและลบข้อมูล" },
]

const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })

function IconBox({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
      <Icon className="h-5 w-5" />
    </span>
  )
}

function Card({ item }: { item: Item }) {
  return (
    <div className="flex gap-4 rounded-2xl border p-5">
      <IconBox icon={item.icon} />
      <div>
        <h3 className="font-bold">{item.title}</h3>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.text}</p>
      </div>
    </div>
  )
}

export default function PrivacyPolicy({ onBack }: { onBack: () => void }) {
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  return (
    <div className="mx-auto max-w-5xl px-4">
      <div className="pt-10">
        <button type="button" onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> กลับหน้าแรก
        </button>
      </div>

      <header className="py-12">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">
          ความเป็นส่วนตัว
        </span>
        <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">ความเป็นส่วนตัวและข้อมูล</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
          อธิบายว่าเราใช้ข้อมูลอะไร เก็บไว้ที่ไหน ส่งต่อให้ใครบ้าง และคุณควบคุมข้อมูลของตัวเองได้อย่างไร
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {SUMMARY.map((s) => (
            <div key={s.title} className="rounded-2xl border bg-muted/30 p-5">
              <s.icon className="h-5 w-5 text-emerald-500" />
              <p className="mt-3 font-bold">{s.title}</p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{s.text}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {NAV.map((n) => (
            <button key={n.id} type="button" onClick={() => jump(n.id)}
              className="rounded-full bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground">
              {n.label}
            </button>
          ))}
        </div>
      </header>

      <div className="space-y-12 pb-16">
        <section id="p-data" className="scroll-mt-24">
          <h2 className="text-2xl font-extrabold tracking-tight">เราใช้ข้อมูลอะไร</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {DATA.map((d) => <Card key={d.title} item={d} />)}
          </div>
        </section>

        <section id="p-where" className="scroll-mt-24">
          <h2 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
            <Cloud className="h-6 w-6 text-emerald-500" /> ข้อมูลถูกเก็บไว้ที่ไหน
          </h2>
          <div className="mt-5 overflow-hidden rounded-2xl border">
            {WHERE.map((w, i) => (
              <div key={w.place} className={`grid gap-2 px-5 py-4 md:grid-cols-[180px_1fr_1fr] md:gap-4 ${i ? "border-t" : ""}`}>
                <span className="font-semibold">{w.place}</span>
                <span className="text-sm leading-6 text-muted-foreground">{w.what}</span>
                <span className="text-sm leading-6 text-emerald-500">{w.persist}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            ข้อมูลที่แสดงอยู่บนหน้าจอชั่วคราว ไม่ได้หมายความว่าถูกบันทึกถาวร
          </p>
        </section>

        <section id="p-third" className="scroll-mt-24">
          <h2 className="text-2xl font-extrabold tracking-tight">บริการภายนอกที่เกี่ยวข้อง</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {THIRD.map((t) => <Card key={t.title} item={t} />)}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            บริการแต่ละรายมีนโยบายความเป็นส่วนตัวและระยะเวลาเก็บข้อมูลของตัวเอง
          </p>
        </section>

        <section id="p-dont" className="scroll-mt-24">
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6">
            <div className="flex items-center gap-2 text-amber-500">
              <AlertTriangle className="h-5 w-5" />
              <p className="font-bold">ข้อมูลที่ไม่ควรใส่ในระบบ</p>
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              โดยเฉพาะในข้อความที่พิมพ์คุยกับผู้ช่วย AI ข้อความเหล่านี้ถูกส่งไปประมวลผล
            </p>
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {DONT.map((d) => (
                <li key={d} className="flex items-center gap-2 text-sm">
                  <Ban className="h-4 w-4 shrink-0 text-amber-500" /> {d}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="p-control" className="scroll-mt-24">
          <h2 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
            <Trash2 className="h-6 w-6 text-emerald-500" /> การควบคุมและลบข้อมูล
          </h2>
          <div className="mt-5 space-y-3">
            {[
              "ล้างธีมและรายการโปรดได้เองโดยล้างข้อมูลเว็บไซต์ในเบราว์เซอร์ การล้างนี้ไม่ได้ลบข้อมูลที่เก็บบนเซิร์ฟเวอร์",
              "การออกจากระบบเป็นการปิด session บนอุปกรณ์นี้ ไม่ได้ลบพอร์ตหรือประวัติคำสั่งของคุณ",
              "หากต้องการให้ลบพอร์ต ประวัติคำสั่ง หรือข้อมูลบัญชีบนเซิร์ฟเวอร์ ให้ติดต่อผู้ดูแลระบบ [ใส่ช่องทางติดต่อ]",
              "ยกเลิกแผน Auto DCA ได้เองทุกเมื่อในหน้า Trade",
            ].map((t) => (
              <div key={t} className="flex gap-3 rounded-xl border p-4 text-sm leading-6">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                <span className="text-muted-foreground">{t}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border bg-muted/30 p-6 text-sm leading-7 text-muted-foreground">
          หน้านี้อธิบายการทำงานของระบบเพื่อให้เข้าใจง่าย ไม่ใช่เอกสารทางกฎหมาย
          ระบบเป็นบัญชีจำลองเพื่อการเรียนรู้ และไม่ใช่คำแนะนำการลงทุน
        </section>
      </div>
    </div>
  )
}
