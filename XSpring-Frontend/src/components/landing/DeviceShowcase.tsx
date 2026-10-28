import { useEffect, useRef, useState } from "react"
import type { CSSProperties } from "react"
import { MacbookPro } from "../ui/macbook-pro"
import { useLanguage } from "../../i18n/LanguageContext"
import CoinsOverlay from "./CoinsOverlay"

// ภาพหน้าจอจริงของ Nobodi (มีทั้งโหมดมืดและสว่าง): วางไว้ที่ XSpring-Frontend/public/mockups/
const SHOTS = {
  cryptoDark: "/mockups/crypto-dark.jpg",
  cryptoLight: "/mockups/crypto-light.jpg",
  stocksDark: "/mockups/stocks-dark.jpg",
  stocksLight: "/mockups/stocks-light.jpg",
}

// โหลดภาพล่วงหน้า: ถ้าไฟล์ยังไม่มีหรือโหลดไม่ได้ จะไม่แสดงทั้ง section (ไม่ให้เห็นเครื่องจอดำเปล่าๆ)
function useShotsReady(urls: string[]) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let alive = true
    Promise.all(
      urls.map(
        (u) =>
          new Promise<boolean>((resolve) => {
            const img = new Image()
            img.onload = () => resolve(true)
            img.onerror = () => resolve(false)
            img.src = u
          }),
      ),
    ).then((r) => alive && setReady(r.every(Boolean)))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return ready
}

// เลื่อนแบบ parallax ตามเมาส์ (ใช้ translate อย่างเดียว ไม่เอียง/หมุนภาพ ตัวหนังสือในจอเลยคมเหมือนเดิม)
// ชั้นที่ "อยู่ใกล้" เลื่อนเยอะ ชั้นที่ "อยู่ไกล" เลื่อนน้อย จึงดูมีมิติ
const layer = (dx: number, dy: number): CSSProperties => ({
  transform: `translate3d(calc(var(--mx, 0) * ${dx}px), calc(var(--my, 0) * ${dy}px), 0)`,
})

// MacBook ที่เปลี่ยนภาพตามธีม: โหมดสว่างใช้ภาพ light / โหมดมืดใช้ภาพ dark (ตาม class "dark" ของ Tailwind)
function ThemedMac({
  light,
  dark,
  alt,
  className,
  style,
}: {
  light: string
  dark: string
  alt: string
  className?: string
  style?: CSSProperties
}) {
  return (
    <div className={className} style={style}>
      <MacbookPro src={light} alt={alt} className="block w-full dark:hidden" />
      <MacbookPro src={dark} alt={alt} className="hidden w-full dark:block" />
    </div>
  )
}

export default function DeviceShowcase({ onRegister }: { onRegister: () => void }) {
  const { t } = useLanguage()
  const ready = useShotsReady(Object.values(SHOTS))
  const stageRef = useRef<HTMLDivElement>(null)
  if (!ready) return null

  const setPointer = (x: number, y: number) => {
    const el = stageRef.current
    if (!el) return
    el.style.setProperty("--mx", x.toFixed(3))
    el.style.setProperty("--my", y.toFixed(3))
  }
  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    const r = e.currentTarget.getBoundingClientRect()
    setPointer(((e.clientX - r.left) / r.width - 0.5) * 2, ((e.clientY - r.top) / r.height - 0.5) * 2)
  }

  return (
    <section id="tour-devices" className="mx-auto max-w-7xl overflow-x-clip px-4 py-16">
      <h2 className="text-center text-3xl font-extrabold tracking-tight">{t("showcase.title")}</h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted-foreground">{t("showcase.subtitle")}</p>

      <div className="mt-10 grid items-center gap-10 lg:grid-cols-[0.75fr_1.25fr]">
        <div>
          <p className="text-base leading-7 text-muted-foreground">{t("showcase.text")}</p>
          <ul className="mt-5 space-y-2 text-sm">
            <li className="flex gap-2">
              <span className="text-emerald-500">●</span>
              <span>{t("showcase.p1")}</span>
            </li>
            <li className="flex gap-2">
              <span className="text-emerald-500">●</span>
              <span>{t("showcase.p2")}</span>
            </li>
          </ul>
          <button
            type="button"
            onClick={onRegister}
            className="mt-8 rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
          >
            {t("cta.register")}
          </button>
        </div>

        {/* MacBook 2 เครื่องซ้อนกัน เครื่องหลัง (หุ้นสหรัฐ) เล็กกว่าและอยู่ขวาบน เครื่องหน้า (คริปโต) ใหญ่กว่าอยู่ซ้ายล่าง
            บนจอเล็กแสดงเครื่องหน้าเครื่องเดียว เพราะซ้อนกันแล้วตัวหนังสือในจอเล็กเกินอ่าน */}
        <div
          ref={stageRef}
          onMouseMove={onMove}
          onMouseLeave={() => setPointer(0, 0)}
          className="hero-visual relative isolate mx-auto w-full max-w-3xl sm:aspect-[16/11]"
        >
          {/* แสงเรืองด้านหลัง + เงาตกพื้น ช่วยให้ดูลอยและมีระยะ */}
          <div className="pointer-events-none absolute -inset-10 -z-10 rounded-full bg-emerald-500/15 blur-3xl" />
          <div className="pointer-events-none absolute inset-x-[6%] -bottom-5 -z-10 hidden h-12 rounded-[100%] bg-black/40 blur-2xl sm:block dark:bg-black/70" />

          {/* ชั้นไกลสุด: เครื่องหลัง หรี่ลงเล็กน้อยให้ดูอยู่ไกล เลื่อนน้อย */}
          <ThemedMac
            light={SHOTS.stocksLight}
            dark={SHOTS.stocksDark}
            alt={t("showcase.altStocks")}
            className="hidden transition-transform duration-200 ease-out drop-shadow-[0_20px_30px_rgba(0,0,0,0.3)] sm:absolute sm:right-0 sm:top-0 sm:block sm:w-[62%] dark:brightness-[.8]"
            style={layer(-8, -5)}
          />

          {/* ชั้นกลาง: เครื่องหน้า ใหญ่และสว่างกว่า เงาหนักกว่า */}
          <ThemedMac
            light={SHOTS.cryptoLight}
            dark={SHOTS.cryptoDark}
            alt={t("showcase.altCrypto")}
            className="transition-transform duration-200 ease-out drop-shadow-[0_30px_40px_rgba(0,0,0,0.5)] sm:absolute sm:bottom-0 sm:left-0 sm:w-[78%]"
            style={layer(10, 6)}
          />

          {/* ชั้นใกล้สุด: เหรียญ เลื่อนเยอะสุด */}
          <div
            className="pointer-events-none absolute inset-0 transition-transform duration-200 ease-out"
            style={layer(22, 14)}
          >
            <CoinsOverlay />
          </div>
        </div>
      </div>
    </section>
  )
}
