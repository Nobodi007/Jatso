import { useEffect } from "react"
import { AlertTriangle, ArrowLeft, Bot, ChartNoAxesCombined, Database, FlaskConical, ShieldCheck } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"

type Props = { onBack: () => void }

const CONTENT = {
  th: {
    back: "กลับหน้าแรก",
    badge: "ข้อมูลสำคัญก่อนใช้งาน",
    title: "การเปิดเผยข้อมูลและคำเตือนความเสี่ยง",
    intro: "Nobodi เป็นแพลตฟอร์มสำหรับเรียนรู้และทดลองใช้งานเครื่องมือเกี่ยวกับตลาดคริปโต โปรดอ่านข้อจำกัดของข้อมูลและความเสี่ยงต่อไปนี้ก่อนนำข้อมูลไปใช้ประกอบการตัดสินใจ",
    cards: [
      { title: "บัญชีจำลอง", text: "การซื้อขายในบัญชีจำลองมีไว้เพื่อการเรียนรู้ ผลกำไร ขาดทุน และยอดสินทรัพย์จำลองไม่ได้แสดงหรือรับประกันผลลัพธ์ที่จะเกิดขึ้นเมื่อซื้อขายเงินจริง" },
      { title: "ข้อมูลตลาด", text: "ราคาและข้อมูลตลาดมาจากผู้ให้บริการภายนอก อาจล่าช้า คลาดเคลื่อน ขาดหาย หรือไม่พร้อมใช้งานชั่วคราว โปรดตรวจสอบราคากับแหล่งข้อมูลที่เกี่ยวข้องก่อนตัดสินใจ" },
      { title: "เครื่องมือวิเคราะห์และผลย้อนหลัง", text: "ผลการจำลอง ตัวชี้วัด และการทดสอบย้อนหลังขึ้นอยู่กับข้อมูล สมมติฐาน และวิธีคำนวณ ผลในอดีตไม่สามารถรับประกันผลในอนาคตได้" },
      { title: "AI Assistant", text: "คำตอบที่สร้างโดย AI อาจไม่ถูกต้อง ไม่ครบถ้วน หรือล้าสมัย ไม่ควรใช้เป็นแหล่งข้อมูลเพียงแหล่งเดียวหรือถือเป็นคำแนะนำการลงทุนเฉพาะบุคคล" },
    ],
    riskTitle: "ความเสี่ยงของสินทรัพย์ดิจิทัล",
    risks: [
      "ราคาสินทรัพย์ดิจิทัลอาจผันผวนอย่างรวดเร็วและมีโอกาสสูญเสียเงินลงทุนบางส่วนหรือทั้งหมดเมื่อทำธุรกรรมด้วยเงินจริง",
      "สภาพคล่อง ความล่าช้าของระบบ ค่าธรรมเนียม และความคลาดเคลื่อนของราคาอาจส่งผลต่อผลลัพธ์การซื้อขาย",
      "การทดลองหรือทดสอบกลยุทธ์ไม่สามารถจำลองสภาวะตลาดจริงได้ครบทุกประการ เช่น สภาพคล่องและการส่งคำสั่ง",
    ],
    scopeTitle: "ขอบเขตและการใช้งานข้อมูล",
    scope: "ข้อมูลและเครื่องมือบน Nobodi จัดทำขึ้นเพื่อให้ข้อมูลและสนับสนุนการเรียนรู้ ไม่ใช่คำแนะนำให้ซื้อ ขาย หรือถือสินทรัพย์ใดโดยเฉพาะ ไม่รับประกันความถูกต้อง ความต่อเนื่อง หรือผลตอบแทน ผู้ใช้งานควรตรวจสอบข้อมูลจากแหล่งที่เชื่อถือได้ ประเมินความเสี่ยงด้วยตนเอง และพิจารณาความเหมาะสมก่อนตัดสินใจ",
    update: "หน้านี้เป็นคำอธิบายทั่วไป ไม่ใช่คำปรึกษาทางกฎหมายหรือการเงิน ควรปรับปรุงให้ตรงกับฟังก์ชันจริงและข้อกำหนดที่ใช้บังคับก่อนเผยแพร่",
  },
  en: {
    back: "Back to home",
    badge: "Important information",
    title: "Disclosures & Risk Notice",
    intro: "Nobodi is a platform for learning about and experimenting with tools related to crypto markets. Please review the following data limitations and risks before relying on information shown on the platform.",
    cards: [
      { title: "Demo account", text: "Trading in a demo account is for learning purposes. Simulated profits, losses, and balances do not represent or guarantee outcomes from real-money trading." },
      { title: "Market data", text: "Prices and market information come from external providers and may be delayed, inaccurate, unavailable, or temporarily interrupted. Verify relevant information with appropriate sources before making decisions." },
      { title: "Analytics and backtests", text: "Simulation results, metrics, and backtests depend on the underlying data, assumptions, and calculation methods. Past results do not guarantee future performance." },
      { title: "AI Assistant", text: "AI-generated responses may be inaccurate, incomplete, or outdated. Do not rely on them as your sole information source or treat them as personalized investment advice." },
    ],
    riskTitle: "Digital asset risks",
    risks: [
      "Digital asset prices can change rapidly. Real-money transactions may result in the loss of some or all of the amount invested.",
      "Liquidity, system delays, fees, and price discrepancies may affect trading outcomes.",
      "Simulations and strategy tests cannot fully reproduce all real-market conditions, including liquidity and order execution.",
    ],
    scopeTitle: "Scope and use of information",
    scope: "Information and tools on Nobodi are provided for informational and educational purposes. They are not a recommendation to buy, sell, or hold any particular asset. Accuracy, uninterrupted availability, and returns are not guaranteed. Users should verify information with reliable sources, assess risks independently, and consider suitability before making decisions.",
    update: "This page provides general information and is not legal or financial advice. Review it against the platform's actual features and applicable requirements before publication.",
  },
} as const

export default function Disclosure({ onBack }: Props) {
  const { lang } = useLanguage()
  const c = CONTENT[lang]

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  const icons = [ShieldCheck, Database, FlaskConical, Bot]

  return (
    <div className="mx-auto max-w-5xl px-4">
      <div className="pt-10">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> {c.back}
        </button>
      </div>

      <header className="py-12">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">{c.badge}</span>
        <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{c.title}</h1>
        <p className="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">{c.intro}</p>
      </header>

      <div className="grid gap-4 pb-12 sm:grid-cols-2">
        {c.cards.map((item, i) => {
          const Icon = icons[i]
          return (
            <section key={item.title} className="flex gap-4 rounded-2xl border p-5">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500"><Icon className="h-5 w-5" /></span>
              <div><h2 className="font-bold">{item.title}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{item.text}</p></div>
            </section>
          )
        })}
      </div>

      <section className="mb-10 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-6">
        <div className="flex items-center gap-2 text-amber-500"><AlertTriangle className="h-5 w-5" /><h2 className="text-xl font-extrabold">{c.riskTitle}</h2></div>
        <ul className="mt-4 space-y-3">{c.risks.map((risk) => <li key={risk} className="flex gap-3 text-sm leading-6 text-muted-foreground"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />{risk}</li>)}</ul>
      </section>

      <section className="mb-8 rounded-2xl border p-6">
        <div className="flex items-center gap-2"><ChartNoAxesCombined className="h-5 w-5 text-emerald-500" /><h2 className="text-xl font-extrabold">{c.scopeTitle}</h2></div>
        <p className="mt-3 text-sm leading-7 text-muted-foreground">{c.scope}</p>
      </section>
      <p className="pb-16 text-xs leading-6 text-muted-foreground">{c.update}</p>
    </div>
  )
}
