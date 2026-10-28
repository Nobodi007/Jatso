import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"


type QA = { q: string; a: string }

const FAQ = {
  th: {
    title: "คำถามที่พบบ่อย",
    desc: "ข้อสงสัยที่ผู้ใช้ใหม่ถามบ่อย ถ้ายังไม่เจอคำตอบ ติดต่อเราได้จากเมนู “ติดต่อเรา”",
    items: [
      {
        q: "Nobodi คืออะไร",
        a: "Nobodi เป็นแพลตฟอร์มฝึกลงทุนคริปโตและหุ้นสหรัฐด้วยบัญชีจำลอง ดูราคาตลาดแบบสด ทดลองลงทุนย้อนหลัง และฝึกซื้อขายก่อนตัดสินใจลงทุนจริง",
      },
      {
        q: "ใครเป็นผู้สร้าง Nobodi",
        a: "Nobodi สร้างโดย ธีรภัทร นิยม อายุ 22 ปี จบการศึกษาจากมหาวิทยาลัยหอการค้าไทย สาขาการเงินการลงทุน เริ่มทำแพลตฟอร์มนี้เพื่อให้คนไทยฝึกลงทุนด้วยบัญชีจำลองก่อนใช้เงินจริง",
      },
      {
        q: "ใช้เงินจริงไหม",
        a: "ไม่ใช้ครับ บัญชีบน Nobodi เป็นบัญชีจำลอง คำสั่งซื้อขายทั้งหมดทำงานในระบบจำลอง ไม่ได้ส่งไปที่ Exchange หรือโบรกเกอร์จริง",
      },
      {
        q: "มีตลาดอะไรให้ฝึกบ้าง",
        a: "มีทั้งคริปโตและหุ้นสหรัฐ สลับดูได้จากช่องค้นหาและเมนูหลังล็อกอิน ฝั่งคริปโตดึงราคาจาก Bitkub ส่วนหุ้นสหรัฐดึงจาก Finnhub และ Yahoo Finance",
      },
      {
        q: "ต้องสมัครก่อนไหมถึงจะดูข้อมูลได้",
        a: "ไม่ต้องครับ ราคา กราฟ สถิติ และข่าวของคริปโตและหุ้นดูได้ฟรีโดยไม่ต้องล็อกอิน สมัครเมื่อต้องการฝึกซื้อขาย สร้างพอร์ต หรือใช้ฟีเจอร์ที่ผูกกับบัญชี",
      },
      {
        q: "ลองลงทุนย้อนหลังคืออะไร",
        a: "คือการจำลองว่าถ้าลงทุนด้วยกลยุทธ์หนึ่งในอดีตจะได้ผลเป็นอย่างไร เช่น ซื้อสะสมรายเดือน ใช้เพื่อเรียนรู้เท่านั้น ผลในอดีตไม่รับประกันอนาคต",
      },
      {
        q: "ข้อมูลราคาเป็นแบบเรียลไทม์ไหม",
        a: "ราคาอัปเดตต่อเนื่อง แต่บางครั้งอาจล่าช้าตามแหล่งข้อมูล โดยเฉพาะหุ้นสหรัฐ ใช้เพื่อประกอบการเรียนรู้ ไม่ควรใช้ตัดสินใจซื้อขายจริงแบบวินาทีต่อวินาที",
      },
      {
        q: "Nobodi เป็นคำแนะนำการลงทุนไหม",
        a: "ไม่ใช่ครับ เนื้อหา สัญญาณ และผลทดสอบย้อนหลังทั้งหมดมีไว้เพื่อการศึกษา การลงทุนในสินทรัพย์ดิจิทัลและหุ้นมีความเสี่ยงสูง โปรดศึกษาและตัดสินใจด้วยตัวเอง",
      },
    ] as QA[],
  },
  en: {
    title: "Frequently asked questions",
    desc: "Common questions from new users. If you can't find your answer, reach us from the \"Contact\" menu.",
    items: [
      {
        q: "What is Nobodi?",
        a: "Nobodi is a practice platform for crypto and US stocks using a simulated account. Watch live market prices, backtest strategies, and practice trading before putting real money at risk.",
      },
      {
        q: "Who created Nobodi?",
        a: "Nobodi was created by Thiraphat Niyom, 22, a graduate of the University of the Thai Chamber of Commerce with a degree in Finance and Investment. He built the platform so people can practice investing with a simulated account before using real money.",
      },
      {
        q: "Does it use real money?",
        a: "No. Accounts on Nobodi are simulated. All orders run inside the simulation and are never sent to a real exchange or broker.",
      },
      {
        q: "Which markets can I practice on?",
        a: "Both crypto and US stocks. Crypto prices come from Bitkub, and US stock data comes from Finnhub and Yahoo Finance.",
      },
      {
        q: "Do I need to sign up to view market data?",
        a: "No. Prices, charts, stats and news for crypto and stocks are free to browse without logging in. Sign up when you want to practice trading, build a portfolio, or use account features.",
      },
      {
        q: "What is the backtest feature?",
        a: "It simulates how a strategy, such as monthly dollar-cost averaging, would have performed in the past. It is for learning only, and past performance does not guarantee future results.",
      },
      {
        q: "Is the price data real-time?",
        a: "Prices update continuously, but may be delayed depending on the data source, especially for US stocks. Use it for learning, not for split-second real trading decisions.",
      },
      {
        q: "Is this investment advice?",
        a: "No. All content, signals and backtest results are for educational purposes only. Crypto and stocks are high-risk assets, so please do your own research.",
      },
    ] as QA[],
  },
}

export default function FaqSection({ onBack }: { onBack?: () => void }) {
  const { lang } = useLanguage()
  const content = lang === "th" ? FAQ.th : FAQ.en
  const [open, setOpen] = useState<number | null>(0)

  return (
    <section id="faq" className="border-t py-20">
      <div className="mx-auto max-w-3xl px-6">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" /> {lang === "th" ? "กลับ" : "Back"}
          </button>
        )}
        <h2 className="text-center text-3xl font-bold tracking-tight md:text-4xl">{content.title}</h2>
        <p className="mx-auto mt-4 max-w-xl text-center text-sm text-muted-foreground md:text-base">
          {content.desc}
        </p>

        <div className="mt-10 divide-y rounded-xl border bg-card">
          {content.items.map((item, i) => {
            const isOpen = open === i
            return (
              <div key={i}>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : i)}
                  className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-sm font-semibold hover:bg-accent/40 md:text-base"
                >
                  <span>{item.q}</span>
                  <ChevronDown
                    className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${
                      isOpen ? "rotate-180 text-emerald-500" : ""
                    }`}
                  />
                </button>
                <div
                  className={`grid transition-all duration-200 ${
                    isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                  }`}
                >
                  <div className="overflow-hidden">
                    <p className="px-5 pb-5 text-sm leading-relaxed text-muted-foreground">{item.a}</p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
