import { useEffect, useRef, useState } from "react"
import { ChevronLeft, ChevronRight, Pause, Play, X } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"

// title / text เป็น key ใน translations.ts (ไม่ใช่ข้อความจริง)
export type TourStep = { target: string; title: string; text: string }

// target = id ของ element บนหน้าแรก (ดู id="tour-..." ใน LandingPage และ HomeSections)
export const HOME_TOUR: TourStep[] = [
  { target: "tour-nav", title: "tour.nav.title", text: "tour.nav.text" },
  { target: "tour-hero", title: "tour.hero.title", text: "tour.hero.text" },
  { target: "tour-market", title: "tour.market.title", text: "tour.market.text" },
  { target: "tour-why", title: "tour.why.title", text: "tour.why.text" },
  { target: "tour-steps", title: "tour.steps.title", text: "tour.steps.text" },
  { target: "tour-tools", title: "tour.tools.title", text: "tour.tools.text" },
  { target: "tour-cta", title: "tour.cta.title", text: "tour.cta.text" },
]

const HEADER_OFFSET = 80 // เว้นที่ให้แถบเมนูด้านบน
const PAD = 8 // ระยะขอบของกรอบไฮไลต์

type Props = {
  steps?: TourStep[]
  onClose: () => void
  onRegister: () => void
}

export default function TourGuide({ steps = HOME_TOUR, onClose, onRegister }: Props) {
  const { t, lang } = useLanguage()

  // ข้ามขั้นที่หา element ไม่เจอ (เช่น เปิดทัวร์ตอนอยู่หน้าย่อย)
  const [list] = useState(() => steps.filter((s) => document.getElementById(s.target)))
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(true)
  const hlRef = useRef<HTMLDivElement>(null)

  const step = list[idx]
  const last = idx === list.length - 1

  useEffect(() => {
    if (list.length === 0) onClose()
  }, [list, onClose])

  // เลื่อนไปหา section ของขั้นนี้
  useEffect(() => {
    if (!step) return
    const el = document.getElementById(step.target)
    if (!el) return
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const top = el.getBoundingClientRect().top + window.scrollY - HEADER_OFFSET
    window.scrollTo({ top: Math.max(0, top), behavior: reduce ? "auto" : "smooth" })
  }, [step])

  // ให้กรอบไฮไลต์ตามตำแหน่ง element ทุกเฟรม (รวมตอนกำลังเลื่อน)
  useEffect(() => {
    if (!step) return
    let raf = 0
    const tick = () => {
      const el = document.getElementById(step.target)
      const hl = hlRef.current
      if (el && hl) {
        const r = el.getBoundingClientRect()
        hl.style.top = `${r.top - PAD}px`
        hl.style.left = `${r.left - PAD}px`
        hl.style.width = `${r.width + PAD * 2}px`
        hl.style.height = `${r.height + PAD * 2}px`
      }
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [step])

  // เล่นอัตโนมัติ: เวลาอ่านขึ้นกับความยาวข้อความ
  useEffect(() => {
    if (!playing || !step) return
    const ms = Math.max(5000, t(step.text).length * (lang === "th" ? 80 : 55))
    const id = setTimeout(() => {
      if (last) setPlaying(false)
      else setIdx((i) => i + 1)
    }, ms)
    return () => clearTimeout(id)
  }, [playing, step, last, lang, t])

  const next = () => setIdx((i) => Math.min(i + 1, list.length - 1))
  const prev = () => setIdx((i) => Math.max(i - 1, 0))

  // คีย์ลัด: Esc ปิด, ลูกศรซ้าย/ขวาเปลี่ยนขั้น
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
      else if (e.key === "ArrowRight") next()
      else if (e.key === "ArrowLeft") prev()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose, list.length])

  if (!step) return null

  const btn = "rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"

  return (
    <>
      {/* ฉากมืด + กรอบไฮไลต์ (กดทะลุได้ เลื่อนหน้าเองก็ได้) */}
      <div
        ref={hlRef}
        aria-hidden="true"
        className="pointer-events-none fixed z-40 rounded-2xl border-2 border-emerald-500"
        style={{ boxShadow: "0 0 0 9999px rgba(0,0,0,0.6)" }}
      />

      {/* คำบรรยาย */}
      <div
        role="dialog"
        aria-live="polite"
        className="fixed bottom-4 left-1/2 z-50 w-[min(640px,calc(100vw-1.5rem))] -translate-x-1/2 rounded-2xl border bg-background p-4 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-emerald-500">
              {t("tour.stepOf", { n: idx + 1, total: list.length })}
            </p>
            <p className="mt-1 text-base font-bold">{t(step.title)}</p>
          </div>
          <button type="button" onClick={onClose} aria-label={t("tour.close")} className={btn}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <p className="mt-2 text-sm leading-6 text-muted-foreground">{t(step.text)}</p>

        <div className="mt-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5" aria-hidden="true">
            {list.map((s, i) => (
              <span
                key={s.target}
                className={`h-1.5 rounded-full transition-all ${
                  i === idx ? "w-5 bg-emerald-500" : i < idx ? "w-1.5 bg-emerald-500/50" : "w-1.5 bg-muted"
                }`}
              />
            ))}
          </div>

          <div className="flex items-center gap-1">
            <button type="button" onClick={prev} disabled={idx === 0} aria-label={t("tour.prev")} className={btn}>
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setPlaying((p) => !p)}
              aria-label={playing ? t("tour.pause") : t("tour.play")}
              className={btn}
            >
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            {last ? (
              <button
                type="button"
                onClick={onRegister}
                className="ml-1 rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400"
              >
                {t("tour.signup")}
              </button>
            ) : (
              <button type="button" onClick={next} aria-label={t("tour.next")} className={btn}>
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
