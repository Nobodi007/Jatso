import { useEffect } from "react"
import type { LucideIcon } from "lucide-react"
import {
  AlertTriangle, ArrowLeft, Ban, Bot, Check, Cloud, Database, Globe, Monitor, ShieldCheck, Trash2, User,
} from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"

type Item = { icon: LucideIcon; title: string; text: string }

const SUMMARY_ICONS = [ShieldCheck, User, Ban]
const DATA_ICONS = [User, Database, Bot, Monitor]
const THIRD_ICONS = [Globe, Globe, User, Bot]
const NAV_IDS = ["p-data", "p-where", "p-third", "p-dont", "p-control"]
const COUNT = { data: 4, where: 2, third: 4, dont: 4, control: 4 }
const range = (n: number) => Array.from({ length: n }, (_, i) => i)

const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })

function IconBox({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
      <Icon className="h-5 w-5" />
    </span>
  )
}

function Card({ icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return (
    <div className="flex gap-4 rounded-2xl border p-5">
      <IconBox icon={icon} />
      <div>
        <h3 className="font-bold">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{text}</p>
      </div>
    </div>
  )
}

export default function PrivacyPolicy({ onBack }: { onBack: () => void }) {
  const { t } = useLanguage()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  return (
    <div className="mx-auto max-w-5xl px-4">
      <div className="pt-10">
        <button type="button" onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> {t("privacy.back")}
        </button>
      </div>

      <header className="py-12">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">
          {t("privacy.badge")}
        </span>
        <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{t("privacy.title")}</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">{t("privacy.intro")}</p>

        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {SUMMARY_ICONS.map((Icon, i) => (
            <div key={i} className="rounded-2xl border bg-muted/30 p-5">
              <Icon className="h-5 w-5 text-emerald-500" />
              <p className="mt-3 font-bold">{t(`privacy.summary.${i}.title`)}</p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{t(`privacy.summary.${i}.text`)}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {NAV_IDS.map((id, i) => (
            <button key={id} type="button" onClick={() => jump(id)}
              className="rounded-full bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground">
              {t(`privacy.nav.${i}`)}
            </button>
          ))}
        </div>
      </header>

      <div className="space-y-12 pb-16">
        <section id="p-data" className="scroll-mt-24">
          <h2 className="text-2xl font-extrabold tracking-tight">{t("privacy.dataTitle")}</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {range(COUNT.data).map((i) => (
              <Card key={i} icon={DATA_ICONS[i]} title={t(`privacy.data.${i}.title`)} text={t(`privacy.data.${i}.text`)} />
            ))}
          </div>
        </section>

        <section id="p-where" className="scroll-mt-24">
          <h2 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
            <Cloud className="h-6 w-6 text-emerald-500" /> {t("privacy.whereTitle")}
          </h2>
          <div className="mt-5 overflow-hidden rounded-2xl border">
            {range(COUNT.where).map((i) => (
              <div key={i} className={`grid gap-2 px-5 py-4 md:grid-cols-[180px_1fr_1fr] md:gap-4 ${i ? "border-t" : ""}`}>
                <span className="font-semibold">{t(`privacy.where.${i}.place`)}</span>
                <span className="text-sm leading-6 text-muted-foreground">{t(`privacy.where.${i}.what`)}</span>
                <span className="text-sm leading-6 text-emerald-500">{t(`privacy.where.${i}.persist`)}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">{t("privacy.whereNote")}</p>
        </section>

        <section id="p-third" className="scroll-mt-24">
          <h2 className="text-2xl font-extrabold tracking-tight">{t("privacy.thirdTitle")}</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            {range(COUNT.third).map((i) => (
              <Card key={i} icon={THIRD_ICONS[i]} title={t(`privacy.third.${i}.title`)} text={t(`privacy.third.${i}.text`)} />
            ))}
          </div>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">{t("privacy.thirdNote")}</p>
        </section>

        <section id="p-dont" className="scroll-mt-24">
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6">
            <div className="flex items-center gap-2 text-amber-500">
              <AlertTriangle className="h-5 w-5" />
              <p className="font-bold">{t("privacy.dontTitle")}</p>
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("privacy.dontIntro")}</p>
            <ul className="mt-4 grid gap-2 sm:grid-cols-2">
              {range(COUNT.dont).map((i) => (
                <li key={i} className="flex items-center gap-2 text-sm">
                  <Ban className="h-4 w-4 shrink-0 text-amber-500" /> {t(`privacy.dont.${i}`)}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="p-control" className="scroll-mt-24">
          <h2 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
            <Trash2 className="h-6 w-6 text-emerald-500" /> {t("privacy.controlTitle")}
          </h2>
          <div className="mt-5 space-y-3">
            {range(COUNT.control).map((i) => (
              <div key={i} className="flex gap-3 rounded-xl border p-4 text-sm leading-6">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                <span className="text-muted-foreground">{t(`privacy.control.${i}`)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border bg-muted/30 p-6 text-sm leading-7 text-muted-foreground">
          {t("privacy.disclaimer")}
        </section>
      </div>
    </div>
  )
}
