import { useEffect } from "react"
import { useLanguage } from "../../i18n/LanguageContext"
import type { LucideIcon } from "lucide-react"
import {
  AlertTriangle, ArrowLeft, ArrowLeftRight, BookOpen, Bot, Briefcase, FlaskConical, Layers,
  LayoutDashboard, Lightbulb, LineChart, ListOrdered, Newspaper, RefreshCw, Settings, ShieldAlert, Wallet,
} from "lucide-react"

type Lang = "th" | "en"
type Localized = Record<Lang, string>
type Mod = { id: string; icon: LucideIcon; name: string; th: Localized; text: Localized; points?: Localized[]; tip?: Localized }
type Group = { id: string; title: Localized; mods: Mod[] }
const L = (th: string, en: string): Localized => ({ th, en })

const GROUPS: Group[] = [
  { id: "g-view", title: L("ดูข้อมูลตลาด", "Market information"), mods: [
    { id: "dashboard", icon: LayoutDashboard, name: "Dashboard", th: L("ภาพรวม", "Overview"), text: L("หน้าแรกหลังเข้าสู่ระบบ ดูสถานะพอร์ตทั้งหมดได้ในหน้าเดียว", "The first page after signing in, where you can review your portfolio status in one place."), points: [L("มูลค่าพอร์ต", "Portfolio value"), L("เงินสด", "Cash"), L("สินทรัพย์ที่ถือ", "Held assets"), L("กำไร/ขาดทุน", "Profit / loss"), L("รายการซื้อขายล่าสุด", "Recent trades")], tip: L("ข้อมูลรีเฟรชเองทุก 10 วินาที ไม่ต้องกดรีโหลดหน้า", "Data refreshes automatically every 10 seconds; you do not need to reload the page.") },
    { id: "markets", icon: LineChart, name: "Markets", th: L("ตลาด", "Markets"), text: L("ดูราคาล่าสุดและการเปลี่ยนแปลงของทุกเหรียญที่ระบบรองรับ ราคาทั้งหมดเป็นเงินบาท", "View the latest prices and price changes for supported coins. All prices are shown in Thai baht."), points: [L("ราคาล่าสุด", "Latest price"), L("% เปลี่ยนแปลง 24 ชม.", "24-hour change %"), L("ราคาสูงสุด/ต่ำสุด", "High / low")], tip: L("หากเซิร์ฟเวอร์ขัดข้อง ระบบจะพยายามดึงราคาจาก Bitkub มาแสดงแทนโดยอัตโนมัติ", "If our server is unavailable, the app may automatically use Bitkub prices as a fallback.") },
    { id: "orderbook", icon: BookOpen, name: "Order Book", th: L("สมุดคำสั่งซื้อขาย", "Order book"), text: L("ดูราคาที่มีผู้ตั้งซื้อและตั้งขาย พร้อมจำนวนที่แต่ละราคา เลือกเหรียญที่ต้องการดูได้", "See the prices and quantities currently offered by buyers and sellers. You can select which coin to view."), points: [L("ราคาซื้อสูงสุด (Best Bid)", "Best Bid"), L("ราคาขายต่ำสุด (Best Ask)", "Best Ask"), L("ราคากึ่งกลาง (Mid Price)", "Mid Price"), L("ส่วนต่างราคา (Spread)", "Spread"), L("Spread %", "Spread %"), L("ปริมาณในแต่ละระดับราคา", "Quantity at each price level")], tip: L("Spread ยิ่งแคบ ราคาซื้อและขายยิ่งใกล้กัน ดูคำอธิบายศัพท์ได้ท้ายหน้า", "A narrower spread means the bid and ask prices are closer. See the glossary at the bottom of this page.") },
    { id: "news", icon: Newspaper, name: "News", th: L("ข่าว", "News"), text: L("รวมข่าวคริปโตล่าสุดจากหลายสำนักไว้ในที่เดียว", "Read recent crypto news from multiple sources in one place."), tip: L("ข่าวมีไว้ติดตามตลาดเท่านั้น ไม่ใช่สัญญาณให้ซื้อหรือขาย", "News is for market awareness only and is not a buy or sell signal.") },
  ]},
  { id: "g-trade", title: L("ซื้อขาย", "Trading"), mods: [
    { id: "trade", icon: ArrowLeftRight, name: "Trade", th: L("ซื้อขาย", "Trade"), text: L("เลือกเหรียญ กรอกรายละเอียดคำสั่ง แล้วกดส่ง เมื่อคำสั่งสำเร็จ ระบบจะอัปเดตพอร์ต", "Choose a coin, enter the order details, and submit. Your portfolio updates when the order succeeds."), points: [L("เลือกเหรียญ", "Choose a coin"), L("ใส่จำนวน", "Enter quantity"), L("กดซื้อหรือขาย", "Buy or sell")], tip: L("ตรวจสอบเงินสดใน Wallet ก่อนส่งคำสั่งทุกครั้ง", "Check your Wallet cash balance before submitting an order.") },
    { id: "orders", icon: ListOrdered, name: "Orders", th: L("ประวัติคำสั่ง", "Order history"), text: L("ดูคำสั่งซื้อขายย้อนหลัง โดยเรียงรายการล่าสุดไว้ด้านบน", "Review past orders, with the newest entries shown first."), tip: L("รายการใหม่จะปรากฏโดยอัตโนมัติภายในประมาณ 10 วินาที", "New entries should appear automatically within about 10 seconds.") },
    { id: "positions", icon: Layers, name: "Positions", th: L("สถานะการถือครอง", "Positions"), text: L("ตรวจสอบว่าตอนนี้ถือเหรียญอะไรอยู่บ้างและแต่ละเหรียญมีสถานะอย่างไร", "See which coins you currently hold and review each holding's status.") },
  ]},
  { id: "g-money", title: L("พอร์ตและเงิน", "Portfolio and funds"), mods: [
    { id: "portfolio", icon: Briefcase, name: "Portfolio", th: L("พอร์ตการลงทุน", "Portfolio"), text: L("ดูสินทรัพย์ทั้งหมดในพอร์ต ต้นทุน มูลค่าปัจจุบัน และกำไรหรือขาดทุน", "Review all portfolio assets, their cost basis, current market value, and profit or loss."), points: [L("จำนวนที่ถือ", "Quantity held"), L("ต้นทุนเฉลี่ย", "Average cost"), L("มูลค่าตลาด", "Market value"), L("กำไร/ขาดทุนที่ยังไม่ขาย", "Unrealized P&L"), L("P&L %", "P&L %"), L("สัดส่วนในพอร์ต", "Portfolio allocation")] },
    { id: "wallet", icon: Wallet, name: "Wallet", th: L("กระเป๋าเงิน", "Wallet"), text: L("ดูเงินสด มูลค่าสินทรัพย์ ยอดรวมพอร์ต และค่าธรรมเนียมที่จ่ายไปแล้ว", "View cash, asset value, total portfolio value, and fees already paid."), tip: L("ตรวจสอบหน้านี้ก่อนซื้อขายเพื่อดูว่ามีเงินสดเพียงพอหรือไม่", "Check this page before trading to make sure you have enough cash.") },
  ]},
  { id: "g-tools", title: L("เครื่องมือวิเคราะห์", "Analysis tools"), mods: [
    { id: "risk", icon: ShieldAlert, name: "Risk Center", th: L("ศูนย์ความเสี่ยง", "Risk center"), text: L("ดูตัวชี้วัดความเสี่ยงที่คำนวณจากพอร์ต เพื่อช่วยประเมินระดับความเสี่ยง", "Review portfolio-based risk indicators to help assess your portfolio's risk level.") },
    { id: "quant", icon: FlaskConical, name: "Quant Lab", th: L("ห้องทดลองเชิงตัวเลข", "Quant lab"), text: L("เครื่องมือวิเคราะห์ข้อมูลเชิงสถิติสำหรับทดลองแนวคิดก่อนนำไปใช้จริง", "Statistical analysis tools for testing ideas before applying them in practice.") },
    { id: "ai", icon: Bot, name: "AI Assistant", th: L("ผู้ช่วย AI", "AI assistant"), text: L("เปิดผู้ช่วยแล้วพิมพ์คำถามได้ ระบบอาจจดจำบริบทบทสนทนาก่อนหน้าได้บางส่วน", "Open the assistant and type a question. It may retain some context from earlier messages."), tip: L("คำตอบจาก AI อาจผิดพลาดได้ ควรตรวจสอบข้อมูลก่อนตัดสินใจ", "AI responses can be incorrect. Verify information before making decisions.") },
  ]},
  { id: "g-settings", title: L("ตั้งค่า", "Settings"), mods: [
    { id: "settings", icon: Settings, name: "Settings", th: L("ตั้งค่า", "Settings"), text: L("เปลี่ยนธีมมืดหรือสว่าง ระบบจะจำค่าที่เลือกไว้ในเบราว์เซอร์", "Switch between dark and light themes. Your choice is saved in the browser.") },
  ]},
]
const QUICK = [
  { id: "dashboard", title: L("ดูภาพรวม", "View overview"), text: L("เริ่มที่ Dashboard เพื่อตรวจสอบสถานะพอร์ต", "Start at Dashboard to check your portfolio status.") },
  { id: "markets", title: L("เช็กราคา", "Check prices"), text: L("เข้า Markets เพื่อดูราคาล่าสุด", "Open Markets to view the latest prices.") },
  { id: "orderbook", title: L("ดู Spread", "View spread"), text: L("เปิด Order Book เพื่อดูราคาเสนอซื้อและเสนอขาย", "Open Order Book to compare bid and ask prices.") },
  { id: "trade", title: L("ส่งคำสั่ง", "Place an order"), text: L("ซื้อหรือขายในหน้า Trade", "Buy or sell from the Trade page.") },
  { id: "portfolio", title: L("ตรวจพอร์ต", "Review portfolio"), text: L("ตรวจสอบ Portfolio และ Wallet หลังทำรายการ", "Review Portfolio and Wallet after a transaction.") },
  { id: "orders", title: L("ดูประวัติ", "View history"), text: L("ตรวจสอบรายการย้อนหลังใน Orders", "Review past entries in Orders.") },
]
const GLOSSARY = [
  { term: "Best Bid", def: L("ราคาสูงสุดที่มีผู้ตั้งรอซื้ออยู่ในขณะนั้น", "The highest price a buyer is currently willing to pay.") },
  { term: "Best Ask", def: L("ราคาต่ำสุดที่มีผู้ตั้งรอขายอยู่ในขณะนั้น", "The lowest price a seller is currently willing to accept.") },
  { term: "Mid Price", def: L("ราคากึ่งกลางระหว่าง Best Bid กับ Best Ask", "The midpoint between the Best Bid and Best Ask.") },
  { term: "Spread", def: L("ส่วนต่างระหว่าง Best Ask กับ Best Bid ยิ่งแคบยิ่งดี", "The difference between the Best Ask and Best Bid; narrower is generally better.") },
  { term: "Spread %", def: L("Spread ที่แสดงเป็นเปอร์เซ็นต์ของราคา ใช้เปรียบเทียบระหว่างเหรียญได้", "The spread expressed as a percentage of price, useful for comparing coins.") },
  { term: "Average Cost", def: L("ต้นทุนเฉลี่ยต่อเหรียญจากการซื้อทั้งหมด", "The average cost per coin across purchases.") },
  { term: "Market Value", def: L("มูลค่าของสินทรัพย์ที่ถือ โดยคำนวณจากราคาตลาดปัจจุบัน", "The value of held assets based on current market prices.") },
  { term: "Unrealized P&L", def: L("กำไรหรือขาดทุนที่ยังไม่เกิดขึ้นจริงจนกว่าจะปิดหรือขายสถานะ", "Profit or loss that has not been realized by closing or selling the position.") },
]
const REFRESH = [
  { name: "Portfolio / Dashboard", every: L("ทุก 10 วินาที", "Every 10 seconds") },
  { name: "Orders", every: L("ทุก 10 วินาที", "Every 10 seconds") },
]
const SCOPE = [
  L("ทุกการซื้อขายเกิดในบัญชีจำลองเพื่อการเรียนรู้ ไม่ได้ใช้เงินจริง", "All trades take place in a simulated account for learning and do not use real money."),
  L("ราคาตลาดอาจล่าช้ากว่าราคาจริงเล็กน้อยหรือขาดหายชั่วคราวตามข้อจำกัดของผู้ให้บริการข้อมูล", "Market prices may be slightly delayed or temporarily unavailable due to data-provider limitations."),
  L("ผลลัพธ์ในระบบไม่ใช่คำแนะนำการลงทุนและไม่รับประกันผลตอบแทนในอนาคต", "Results in this app are not investment advice and do not guarantee future returns."),
]
const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
function IconBox({ icon: Icon }: { icon: LucideIcon }) {
  return <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500"><Icon className="h-5 w-5" /></span>
}
function ModCard({ m, lang }: { m: Mod; lang: Lang }) {
  return <div id={m.id} className="scroll-mt-24 rounded-2xl border p-6"><div className="flex items-start gap-4"><IconBox icon={m.icon} /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline gap-2"><h3 className="text-lg font-bold">{m.name}</h3><span className="text-sm text-muted-foreground">{m.th[lang]}</span></div><p className="mt-2 text-sm leading-7 text-muted-foreground">{m.text[lang]}</p>{m.points && <div className="mt-4 flex flex-wrap gap-2">{m.points.map((p) => <span key={p[lang]} className="rounded-full border bg-muted/40 px-3 py-1 text-xs font-medium">{p[lang]}</span>)}</div>}{m.tip && <div className="mt-4 flex gap-2 rounded-xl bg-emerald-500/10 p-3 text-sm leading-6 text-emerald-700 dark:text-emerald-400"><Lightbulb className="mt-0.5 h-4 w-4 shrink-0" /><span>{m.tip[lang]}</span></div>}</div></div></div>
}
export default function UserGuide({ onBack }: { onBack: () => void }) {
  const { lang } = useLanguage()
  const isTh = lang === "th"
  useEffect(() => { window.scrollTo({ top: 0 }) }, [])
  const text = isTh ? {
    back: "กลับหน้าแรก", badge: "คู่มือการใช้งาน", title: "ใช้งานระบบอย่างไร", intro: "รวมวิธีใช้ทุกเมนู ตั้งแต่ดูราคา ส่งคำสั่งซื้อขายในบัญชีจำลอง ไปจนถึงตรวจพอร์ตและวิเคราะห์ความเสี่ยง", quick: "เริ่มต้นใน 6 ขั้น", glossary: "คำศัพท์ที่ควรรู้", refresh: "การอัปเดตข้อมูล", auto: "รีเฟรชอัตโนมัติ", refreshNote: "ระบบจะหยุดรีเฟรชเมื่อคุณสลับไปแท็บอื่น และกลับมารีเฟรชต่อเมื่อเปิดหน้าเว็บอีกครั้ง เพื่อไม่ให้โหลดข้อมูลโดยไม่จำเป็น", scope: "ขอบเขตการใช้งาน"
  } : {
    back: "Back to home", badge: "USER GUIDE", title: "How to use the platform", intro: "Learn how to use each section, from checking prices and placing simulated trades to reviewing your portfolio and risk.", quick: "Get started in 6 steps", glossary: "Glossary", refresh: "Data refresh", auto: "Automatic refresh", refreshNote: "Refreshing pauses when you switch to another tab and resumes when you return, avoiding unnecessary requests.", scope: "Usage scope"
  }
  return <div className="mx-auto max-w-6xl px-4"><div className="pt-10"><button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />{text.back}</button></div>
    <header className="py-12"><span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">{text.badge}</span><h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{text.title}</h1><p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">{text.intro}</p></header>
    <section className="pb-12"><h2 className="text-2xl font-extrabold tracking-tight">{text.quick}</h2><div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{QUICK.map((q, i) => <button key={q.id} type="button" onClick={() => jump(q.id)} className="flex items-center gap-4 rounded-2xl border p-4 text-left transition-colors hover:bg-accent"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-sm font-bold text-black">{i + 1}</span><span><span className="block font-bold">{q.title[lang]}</span><span className="block text-xs text-muted-foreground">{q.text[lang]}</span></span></button>)}</div></section>
    <div className="grid gap-10 pb-16 lg:grid-cols-[200px_1fr]"><aside className="hidden lg:block"><nav className="sticky top-24 space-y-5 text-sm">{GROUPS.map((g) => <div key={g.id}><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-emerald-500">{g.title[lang]}</p><ul className="space-y-1.5">{g.mods.map((m) => <li key={m.id}><button type="button" onClick={() => jump(m.id)} className="text-muted-foreground hover:text-foreground">{m.name}</button></li>)}</ul></div>)}<div className="space-y-1.5 border-t pt-4"><button type="button" onClick={() => jump("glossary")} className="block text-muted-foreground hover:text-foreground">{text.glossary}</button><button type="button" onClick={() => jump("refresh")} className="block text-muted-foreground hover:text-foreground">{text.refresh}</button><button type="button" onClick={() => jump("scope")} className="block text-muted-foreground hover:text-foreground">{text.scope}</button></div></nav></aside>
      <div className="min-w-0 space-y-12">{GROUPS.map((g) => <section key={g.id} id={g.id} className="scroll-mt-24"><h2 className="text-2xl font-extrabold tracking-tight">{g.title[lang]}</h2><div className="mt-5 space-y-4">{g.mods.map((m) => <ModCard key={m.id} m={m} lang={lang} />)}</div></section>)}
        <section id="glossary" className="scroll-mt-24"><h2 className="text-2xl font-extrabold tracking-tight">{text.glossary}</h2><div className="mt-5 overflow-hidden rounded-2xl border">{GLOSSARY.map((g, i) => <div key={g.term} className={`grid gap-1 px-5 py-4 sm:grid-cols-[160px_1fr] sm:gap-4 ${i ? "border-t" : ""}`}><span className="font-semibold">{g.term}</span><span className="text-sm leading-6 text-muted-foreground">{g.def[lang]}</span></div>)}</div></section>
        <section id="refresh" className="scroll-mt-24"><h2 className="text-2xl font-extrabold tracking-tight">{text.refresh}</h2><div className="mt-5 rounded-2xl border p-6"><div className="flex items-center gap-2 font-bold"><RefreshCw className="h-5 w-5 text-emerald-500" />{text.auto}</div><div className="mt-4 grid gap-3 sm:grid-cols-2">{REFRESH.map((r) => <div key={r.name} className="flex items-center justify-between rounded-xl bg-muted/40 px-4 py-3 text-sm"><span>{r.name}</span><span className="font-semibold text-emerald-500">{r.every[lang]}</span></div>)}</div><p className="mt-4 text-sm leading-6 text-muted-foreground">{text.refreshNote}</p></div></section>
        <section id="scope" className="scroll-mt-24"><div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6"><div className="flex items-center gap-2 text-amber-500"><AlertTriangle className="h-5 w-5" /><p className="font-bold">{text.scope}</p></div><ul className="mt-4 space-y-2">{SCOPE.map((s) => <li key={s[lang]} className="flex gap-2 text-sm leading-6 text-muted-foreground"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />{s[lang]}</li>)}</ul></div></section>
      </div></div></div>
}

