import Footer from "./Footer"
import AboutSystem from "./AboutSystem"
import UserGuide from "./UserGuide"
import PrivacyPolicy from "./PrivacyPolicy"
import Disclosure from "./Disclosure"
import { useEffect, useState } from "react"
import { BarChart3, Newspaper, Scale, ShieldCheck, TestTube2, UserPlus } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"

const API_BASE_URL = "https://xspring-api.onrender.com"

type Row = { asset: string; name: string; price: number; change: number }
type Props = {
  onLogin: () => void
  onRegister: () => void
  onOpenCoin: (asset: string) => void
  onGo: (label: string) => void
  heroTitle: string
  heroSub: string
  heroArt: React.ReactNode
}

const fmtPrice = (v: number, locale: string) =>
  v.toLocaleString(locale, { maximumFractionDigits: v < 1 ? 4 : 2 })

function Spark({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return <span className="text-xs text-muted-foreground">—</span>
  const min = Math.min(...data)
  const span = Math.max(...data) - min || 1
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * 100},${28 - ((v - min) / span) * 26}`)
    .join(" ")
  return (
    <svg viewBox="0 0 100 30" className="h-8 w-24" preserveAspectRatio="none" aria-hidden="true">
      <polyline
        points={pts}
        fill="none"
        strokeWidth={1.8}
        vectorEffect="non-scaling-stroke"
        className={up ? "stroke-emerald-500" : "stroke-red-500"}
      />
    </svg>
  )
}

const WHY: { icon: LucideIcon; title: string; text: string }[] = [
  {
    icon: ShieldCheck,
    title: "why.c1Title",
    text: "why.c1Desc",
  },
  {
    icon: BarChart3,
    title: "why.c2Title",
    text: "why.c2Desc",
  },
  {
    icon: TestTube2,
    title: "why.c3Title",
    text: "why.c3Desc",
  },
]

const STEPS: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: UserPlus, title: "steps.s1Title", text: "steps.s1Desc" },
  { icon: Scale, title: "steps.s2Title", text: "steps.s2Desc" },
  { icon: BarChart3, title: "steps.s3Title", text: "steps.s3Desc" },
]

const TOOLS: { icon: LucideIcon; title: string; text: string; go: string }[] = [
  { icon: Newspaper, title: "tools.t1Title", text: "tools.t1Desc", go: "ข่าว" },
  { icon: Scale, title: "tools.t2Title", text: "tools.t2Desc", go: "ตลาด" },
  { icon: TestTube2, title: "tools.t3Title", text: "tools.t3Desc", go: "ลองลงทุนย้อนหลัง" },
]

export default function HomeSections({ onRegister, onLogin, onOpenCoin, onGo, heroTitle, heroSub, heroArt }: Props) {
  const { t, lang } = useLanguage()
  const locale = lang === "th" ? "th-TH" : "en-US"
  const [rows, setRows] = useState<Row[] | null>(null)
  const [sparks, setSparks] = useState<Record<string, number[]>>({})
  const [page, setPage] = useState<"home" | "about" | "guide" | "privacy">("home")
  const openPage = (p: string) => {
    if (p === "about" || p === "guide" || p === "privacy") setPage(p)
  }


  useEffect(() => {
    let alive = true
    const load = () =>
      fetch(`${API_BASE_URL}/api/public/markets`, { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((d) => {
          if (!alive) return
          setRows(Array.isArray(d.rows) ? d.rows.slice(0, 5) : [])
          setSparks(d.sparks ?? {})
        })
        .catch(() => alive && setRows((p) => p ?? []))
    load()
    const id = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])
  
   if (page !== "home") {
    return (
      <>
        {page === "privacy" && <PrivacyPolicy onBack={() => setPage("home")} />}
        {page === "about" && <AboutSystem onBack={() => setPage("home")} />}
        {page === "guide" && <UserGuide onBack={() => setPage("home")} />}
        <Footer onGo={onGo} onOpenCoin={onOpenCoin} onPage={openPage} />
      </>
    )
  }

  return (
    <>
      {/* HERO */}
      <section className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-16 lg:grid-cols-2 lg:py-24">
        <div>
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{heroTitle}</h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground">{heroSub}</p>
          <button
            type="button"
            onClick={onRegister}
            className="mt-8 rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
          >
            {t("hero.cta")}
          </button>
        </div>
        <div className="flex justify-center lg:justify-end">{heroArt}</div>
      </section>

      {/* ตลาด */}
      <section className="mx-auto max-w-4xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">{t("market.title")}</h2>
        <p className="mt-2 text-center text-sm text-muted-foreground">{t("market.subtitle")}</p>

        <div className="mt-8 overflow-hidden rounded-2xl border">
          <div className="grid grid-cols-[1.4fr_1fr_0.8fr_0.8fr] gap-2 bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
            <span>{t("market.colName")}</span>
            <span className="text-right">{t("market.colPrice")}</span>
            <span className="text-right">{t("market.colChange")}</span>
            <span className="text-right">{t("market.colTrend")}</span>
          </div>
          {rows === null && <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t("market.loading")}</p>}
          {rows?.length === 0 && <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t("market.loadFailed")}</p>}
          {rows?.map((r) => {
            const up = r.change >= 0
            const sp = sparks[r.asset] ?? []
            return (
              <button
                key={r.asset}
                type="button"
                onClick={() => onOpenCoin(r.asset)}
                className="grid w-full grid-cols-[1.4fr_1fr_0.8fr_0.8fr] items-center gap-2 border-t px-4 py-3 text-left text-sm hover:bg-accent"
              >
                <span>
                  <span className="font-semibold">{r.asset}</span>{" "}
                  <span className="text-xs text-muted-foreground">{r.name}</span>
                </span>
                <span className="text-right font-semibold">฿{fmtPrice(r.price, locale)}</span>
                <span className={`text-right font-semibold ${up ? "text-emerald-500" : "text-red-500"}`}>
                  {up ? "+" : ""}
                  {r.change.toFixed(2)}%
                </span>
                <span className="flex justify-end">
                  <Spark data={sp} up={sp.length > 1 ? sp[sp.length - 1] >= sp[0] : up} />
                </span>
              </button>
            )
          })}
        </div>
        <div className="mt-4 text-center">
          <button type="button" onClick={() => onGo("ตลาด")} className="text-sm text-muted-foreground hover:text-foreground">
            {t("market.viewMore")}
          </button>
        </div>
      </section>

      {/* ทำไมต้อง Nobodi */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">{t("why.title")}</h2>
        <p className="mt-2 text-center text-sm text-muted-foreground">
          {t("why.subtitle")}
        </p>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {WHY.map((w) => {
            const Icon = w.icon
            return (
              <div key={w.title} className="rounded-2xl border p-6 text-center">
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
                  <Icon className="h-6 w-6" />
                </span>
                <h3 className="mt-4 text-lg font-bold">{t(w.title)}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{t(w.text)}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* เริ่มต้นใน 3 ขั้น */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">{t("steps.title")}</h2>
        <div className="mt-8 grid items-center gap-8 lg:grid-cols-[1fr_320px]">
          <ol className="space-y-6">
            {STEPS.map((s, i) => {
              const Icon = s.icon
              return (
                <li key={s.title} className="flex gap-4">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
                    <Icon className="h-6 w-6" />
                  </span>
                  <div>
                    <p className="text-lg font-bold">
                      {i + 1}. {t(s.title)}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">{t(s.text)}</p>
                  </div>
                </li>
              )
            })}
            <li>
              <button
                type="button"
                onClick={onRegister}
                className="rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
              >
                {t("cta.register")}
              </button>
            </li>
          </ol>

          {/* ภาพประกอบ SVG วาดเอง */}
          <svg viewBox="0 0 320 240" className="mx-auto h-auto w-full max-w-xs" aria-hidden="true">
            <rect x="10" y="10" width="300" height="220" rx="24" className="fill-muted/40 stroke-border" />
            <rect x="40" y="150" width="30" height="50" rx="5" className="fill-emerald-500/40" />
            <rect x="90" y="120" width="30" height="80" rx="5" className="fill-emerald-500/60" />
            <rect x="140" y="95" width="30" height="105" rx="5" className="fill-emerald-500/80" />
            <rect x="190" y="70" width="30" height="130" rx="5" className="fill-emerald-500" />
            <polyline
              points="55,140 105,110 155,85 205,55 265,38"
              fill="none"
              strokeWidth={3}
              strokeDasharray="6 6"
              strokeLinecap="round"
              className="stroke-foreground/50"
            />
            <circle cx="265" cy="38" r="8" className="fill-emerald-500" />
          </svg>
        </div>
      </section>

      {/* เครื่องมือ */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-center text-3xl font-extrabold tracking-tight">{t("tools.title")}</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {TOOLS.map((tool) => {
            const Icon = tool.icon
            return (
              <button
                key={tool.title}
                type="button"
                onClick={() => onGo(tool.go)}
                className="rounded-2xl border p-6 text-left transition-colors hover:bg-accent"
              >
                <Icon className="h-6 w-6 text-emerald-500" />
                <h3 className="mt-4 text-lg font-bold">{t(tool.title)}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{t(tool.text)}</p>
                <span className="mt-4 inline-block text-sm text-emerald-500">{t("tools.open")}</span>
              </button>
            )
          })}
        </div>
      </section>

            {/* ปิดท้าย */}
      <section className="mx-auto max-w-4xl px-4 py-16 text-center">
        <h2 className="text-3xl font-extrabold tracking-tight">{t("cta.title")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("cta.subtitle")}</p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={onRegister}
            className="rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
          >
            {t("cta.register")}
          </button>
          <button type="button" onClick={onLogin} className="rounded-lg border px-6 py-3 text-sm font-semibold hover:bg-accent">
            {t("cta.login")}
          </button>
        </div>
      </section>

      <Footer onGo={onGo} onOpenCoin={onOpenCoin} onPage={openPage} />
    </>
  )
}
