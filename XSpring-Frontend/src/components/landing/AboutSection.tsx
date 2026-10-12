import type { ReactNode } from "react"
import { ArrowLeft } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext" 

// ใส่ "/founder.jpg" เมื่อวางรูปไว้ที่ public/founder.jpg (ปล่อยว่าง = ใช้ตัวอักษร N แทน)
const FOUNDER_PHOTO = "/founder.jpg"

const rich = (s: string) => s.split("**").map((p, i) => (i % 2 ? <b key={i}>{p}</b> : p))

const BODY = "mt-5 text-base leading-8 text-foreground/90"

const LOOP = ["ทำผิดก็แก้", "ไม่เข้าใจก็ลองใหม่", "ทำไม่ได้ก็หาวิธีใหม่"]

const CHAIN = [
  "เมื่อมีไอเดีย ก็อยากลองทำ",
  "เมื่อทำสำเร็จ ก็อยากลองต่อ",
  "และเมื่อเห็นว่าสิ่งหนึ่งสามารถพัฒนาได้ ก็เริ่มอยากรู้ว่ามันจะไปได้ไกลกว่านั้นอีกแค่ไหน",
]

function PullQuote({ children }: { children: ReactNode }) {
  return (
    <blockquote className="my-8 rounded-r-xl border-l-4 border-emerald-500 bg-emerald-500/5 py-4 pl-5 pr-4 text-lg font-semibold leading-8">
      {children}
    </blockquote>
  )
}

export default function AboutSection({ onBack, onRegister }: { onBack: () => void; onRegister: () => void }) {
  const { t } = useLanguage()
  const P = ({ k }: { k: string }) => <p className={BODY}>{rich(t(`about.${k}`))}</p>

  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:py-14">
      <button
        type="button"
        onClick={onBack}
        className="mb-8 flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("about.back")}
      </button>

      <p className="text-sm font-semibold text-emerald-500">{t("about.eyebrow")}</p>
      <h1 className="mt-2 text-4xl font-extrabold tracking-tight sm:text-5xl">{t("about.heroTitle")}</h1>
      <P k="heroIntro" />
      <PullQuote>{t("about.q1")}</PullQuote>

      <div className="flex items-center gap-4 rounded-2xl border bg-muted/20 p-5">
        {FOUNDER_PHOTO ? (
          <img
            src={FOUNDER_PHOTO}
            alt={t("about.founderAlt")}
            width={112}
            height={112}
            className="h-24 w-24 shrink-0 rounded-2xl object-cover sm:h-28 sm:w-28"
          />
        ) : (
          <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-emerald-500 text-3xl font-extrabold text-black">
            N
          </div>
        )}
        <div className="min-w-0">
          <p className="text-lg font-bold">{t("about.founderName")}</p>
          <p className="text-sm text-muted-foreground">{t("about.founderRole")}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t("about.founderEdu")}</p>
        </div>
      </div>

      <P k="p1" />
      <P k="p2" />
      <p className="mt-5 text-lg font-semibold">{t("about.p3")}</p>
      <P k="p4" />

      <div className="my-8 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5">
        <p className="text-xs font-semibold text-emerald-500">{t("about.nameLabel")}</p>
        <p className="mt-2 text-base leading-8">{rich(t("about.nameText"))}</p>
      </div>

      <P k="p5" />
      <P k="p6" />
      <P k="p7" />
      <P k="p8" />
      <PullQuote>{t("about.q2")}</PullQuote>

      <P k="p9" />
      <P k="p10" />

      <div className="my-8 grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-xl border bg-muted/20 p-4 text-center">
            <p className="text-xs font-bold text-emerald-500">0{i + 1}</p>
            <p className="mt-1 text-sm font-semibold">{t(`about.loop.${i}`)}</p>
          </div>
        ))}
      </div>

      <P k="p11" />
      <P k="p12" />
      <P k="p13" />
      <P k="p14" />
      <P k="p15" />
      <P k="p16" />
      <PullQuote>{t("about.q3")}</PullQuote>

      <div className="my-8 flex items-center gap-4 rounded-2xl border bg-muted/20 p-5">
        <div className="shrink-0 rounded-xl bg-emerald-500 px-4 py-2 text-center text-black">
          <p className="text-2xl font-extrabold leading-none">{t("about.dateDay")}</p>
          <p className="mt-1 text-xs font-bold">{t("about.dateMonth")}</p>
        </div>
        <p className="text-base font-semibold">{t("about.dateLabel")}</p>
      </div>

      <P k="p17" />
      <P k="p18" />
      <P k="p19" />
      <P k="p20" />

      <ul className="my-6 space-y-2 border-l-2 border-emerald-500/40 pl-5 text-base leading-8">
        {[0, 1, 2].map((i) => (
          <li key={i}>{t(`about.chain.${i}`)}</li>
        ))}
      </ul>

      <P k="p21" />

      <div className="mt-14 grid gap-4 sm:grid-cols-2">
        <section className="rounded-2xl border bg-muted/20 p-6">
          <p className="text-xs font-bold tracking-wide text-emerald-500">{t("about.visionLabel")}</p>
          <h2 className="mt-2 text-xl font-bold leading-snug">{t("about.visionTitle")}</h2>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">{t("about.visionP1")}</p>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">{t("about.visionP2")}</p>
        </section>

        <section className="rounded-2xl border bg-muted/20 p-6">
          <p className="text-xs font-bold tracking-wide text-emerald-500">{t("about.missionLabel")}</p>
          <h2 className="mt-2 text-xl font-bold leading-snug">{t("about.missionTitle")}</h2>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">{t("about.missionP1")}</p>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">{t("about.missionP2")}</p>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">
            {t("about.missionP3a")} <b className="text-foreground">{t("about.missionP3b")}</b>
          </p>
        </section>
      </div>

      <div className="mt-12 flex flex-wrap items-center justify-between gap-4 rounded-2xl border p-6">
        <div>
          <p className="text-lg font-bold">{t("about.ctaTitle")}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t("about.ctaSub")}</p>
        </div>
        <button
          type="button"
          onClick={onRegister}
          className="rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
        >
          {t("about.ctaBtn")}
        </button>
      </div>
    </main>
  )
}
