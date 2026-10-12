import { Fragment, useEffect } from "react"
import type { LucideIcon } from "lucide-react"
import {
  AlertTriangle, ArrowDown, ArrowLeft, ArrowLeftRight, ArrowRight, BookOpen, Bot, Briefcase, Database,
  FlaskConical, Layers, LayoutDashboard, LineChart, ListOrdered, Lock, Monitor, Newspaper, Palette,
  RefreshCw, Server, Settings, ShieldCheck, Wallet,
} from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"

const FLOW_ICONS = [Monitor, Layers, Server, Database]
const MODULE_ICONS = [LayoutDashboard, LineChart, ArrowLeftRight, BookOpen, Briefcase, Wallet, ListOrdered, Layers, ShieldCheck, FlaskConical, Newspaper, Settings]
const MODULE_TITLES = ["Dashboard", "Markets", "Trade", "Order Book", "Portfolio", "Wallet", "Orders", "Positions", "Risk Center", "Quant Lab", "News", "Settings"]
const STACK_ITEMS = [
  ["React 19", "TypeScript", "Vite", "Tailwind CSS 4", "Radix UI / shadcn", "Lucide React", "Lightweight Charts"],
  ["XSpring Backend API", "Bitkub API", "RSS-to-JSON API", "Google OAuth"],
]
const REFRESH = [true, false, false, true, false]
const SECURITY_ICONS = [Lock, ShieldCheck, RefreshCw, Palette, Server, Bot]
const range = (n: number) => Array.from({ length: n }, (_, i) => i)

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
  const { t } = useLanguage()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4">
      <div className="pt-10">
        <button type="button" onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> {t("sys.back")}
        </button>
      </div>

      <header className="py-12">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">
          {t("sys.badge")}
        </span>
        <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
          XSpring Dealer Suite
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">{t("sys.intro")}</p>
        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          {range(3).map((i) => (
            <div key={i} className="rounded-2xl border p-5">
              <p className="text-3xl font-extrabold text-emerald-500">{t(`sys.stats.${i}.value`)}</p>
              <p className="mt-1 text-sm text-muted-foreground">{t(`sys.stats.${i}.label`)}</p>
            </div>
          ))}
        </div>
      </header>

      <Section eyebrow={t("sys.overviewEyebrow")} title={t("sys.overviewTitle")} desc={t("sys.overviewDesc")}>
        <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
          {FLOW_ICONS.map((icon, i) => (
            <Fragment key={i}>
              <div className="flex flex-1 items-center gap-3 rounded-2xl border p-4">
                <IconBox icon={icon} />
                <div>
                  <p className="text-sm font-bold">{t(`sys.flow.${i}.title`)}</p>
                  <p className="text-xs text-muted-foreground">{t(`sys.flow.${i}.text`)}</p>
                </div>
              </div>
              {i < FLOW_ICONS.length - 1 && (
                <div className="flex justify-center text-muted-foreground">
                  <ArrowDown className="h-5 w-5 md:hidden" />
                  <ArrowRight className="hidden h-5 w-5 md:block" />
                </div>
              )}
            </Fragment>
          ))}
        </div>
      </Section>

      <Section eyebrow={t("sys.modulesEyebrow")} title={t("sys.modulesTitle")}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {MODULE_ICONS.map((icon, i) => (
            <div key={i} className="flex gap-4 rounded-2xl border p-5 transition-colors hover:bg-accent">
              <IconBox icon={icon} />
              <div>
                <p className="font-bold">{MODULE_TITLES[i]}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{t(`sys.modules.${i}`)}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section eyebrow={t("sys.techEyebrow")} title={t("sys.techTitle")}>
        <div className="grid gap-4 md:grid-cols-2">
          {STACK_ITEMS.map((items, gi) => (
            <div key={gi} className="rounded-2xl border p-6">
              <p className="text-sm font-bold">{t(`sys.stackGroups.${gi}`)}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {items.map((name) => (
                  <span key={name} className="rounded-full border bg-muted/40 px-3 py-1 text-xs font-medium">{name}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section eyebrow={t("sys.dataEyebrow")} title={t("sys.dataTitle")}>
        <ol className="relative space-y-6 border-l pl-8">
          {REFRESH.map((hasRefresh, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[45px] flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-xs font-bold text-black">
                {i + 1}
              </span>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-bold">{t(`sys.dataFlow.${i}.title`)}</p>
                <code className="rounded-md bg-muted px-2 py-0.5 text-xs">{t(`sys.dataFlow.${i}.tag`)}</code>
                {hasRefresh && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-500">
                    <RefreshCw className="h-3 w-3" /> {t("sys.refresh")}
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{t(`sys.dataFlow.${i}.text`)}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section eyebrow={t("sys.secEyebrow")} title={t("sys.secTitle")}>
        <div className="grid gap-4 md:grid-cols-2">
          {SECURITY_ICONS.map((icon, i) => (
            <div key={i} className="flex gap-4 rounded-2xl border p-5">
              <IconBox icon={icon} />
              <div>
                <p className="font-bold">{t(`sys.security.${i}.title`)}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{t(`sys.security.${i}.text`)}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <section className="pb-16 pt-4">
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6">
          <div className="flex items-center gap-2 text-amber-500">
            <AlertTriangle className="h-5 w-5" />
            <p className="font-bold">{t("sys.scopeTitle")}</p>
          </div>
          <ul className="mt-4 space-y-2">
            {range(4).map((i) => (
              <li key={i} className="flex gap-2 text-sm leading-6 text-muted-foreground">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                {t(`sys.scope.${i}`)}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  )
}
        </div>
      </section>
    </div>
  )
}
