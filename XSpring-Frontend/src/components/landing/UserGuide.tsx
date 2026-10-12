import { useEffect } from "react"
import { useLanguage } from "../../i18n/LanguageContext"
import type { LucideIcon } from "lucide-react"
import {
  AlertTriangle, ArrowLeft, ArrowLeftRight, BookOpen, Bot, Briefcase, FlaskConical, Layers,
  LayoutDashboard, Lightbulb, LineChart, ListOrdered, Newspaper, RefreshCw, Settings, ShieldAlert, Wallet,
} from "lucide-react"

type Mod = { id: string; icon: LucideIcon; name: string; th: string; text: string; points?: string[]; tip?: string }
type Group = { id: string; title: string; mods: Mod[] }

const GROUPS: Group[] = [
  {
    id: "g-view", title: "guideText.k001",
    mods: [
      { id: "dashboard", icon: LayoutDashboard, name: "Dashboard", th: "guideText.k002",
        text: "guideText.k006",
        points: ["guideText.k007", "guideText.k008", "guideText.k009", "guideText.k010", "guideText.k011"],
        tip: "guideText.k012" },
      { id: "markets", icon: LineChart, name: "Markets", th: "guideText.k003",
        text: "guideText.k013",
        points: ["guideText.k014", "guideText.k015", "guideText.k016"],
        tip: "guideText.k017" },
      { id: "orderbook", icon: BookOpen, name: "Order Book", th: "guideText.k004",
        text: "guideText.k018",
        points: ["Best Bid", "Best Ask", "Mid Price", "Spread", "Spread %", "guideText.k019"],
        tip: "guideText.k020" },
      { id: "news", icon: Newspaper, name: "News", th: "guideText.k005",
        text: "guideText.k021",
        tip: "guideText.k022" },
    ],
  },
  {
    id: "g-trade", title: "guideText.k023",
    mods: [
      { id: "trade", icon: ArrowLeftRight, name: "Trade", th: "guideText.k023",
        text: "guideText.k024",
        points: ["guideText.k025", "guideText.k026", "guideText.k027"],
        tip: "guideText.k028" },
      { id: "orders", icon: ListOrdered, name: "Orders", th: "guideText.k029",
        text: "guideText.k030",
        tip: "guideText.k031" },
      { id: "positions", icon: Layers, name: "Positions", th: "guideText.k032",
        text: "guideText.k033" },
    ],
  },
  {
    id: "g-money", title: "guideText.k034",
    mods: [
      { id: "portfolio", icon: Briefcase, name: "Portfolio", th: "guideText.k035",
        text: "guideText.k036",
        points: ["guideText.k037", "guideText.k038", "guideText.k039", "guideText.k040", "guideText.k041", "guideText.k042"] },
      { id: "wallet", icon: Wallet, name: "Wallet", th: "guideText.k043",
        text: "guideText.k044",
        tip: "guideText.k045" },
    ],
  },
  {
    id: "g-tools", title: "guideText.k046",
    mods: [
      { id: "risk", icon: ShieldAlert, name: "Risk Center", th: "guideText.k047",
        text: "guideText.k048" },
      { id: "quant", icon: FlaskConical, name: "Quant Lab", th: "guideText.k049",
        text: "guideText.k050" },
      { id: "ai", icon: Bot, name: "AI Assistant", th: "guideText.k051",
        text: "guideText.k052",
        tip: "guideText.k053" },
    ],
  },
  {
    id: "g-settings", title: "guideText.k054",
    mods: [
      { id: "settings", icon: Settings, name: "Settings", th: "guideText.k054",
        text: "guideText.k055" },
    ],
  },
]

const QUICK = [
  { id: "dashboard", title: "guideText.k056", text: "guideText.k057" },
  { id: "markets", title: "guideText.k058", text: "guideText.k059" },
  { id: "orderbook", title: "guideText.k060", text: "guideText.k061" },
  { id: "trade", title: "guideText.k062", text: "guideText.k063" },
  { id: "portfolio", title: "guideText.k064", text: "guideText.k065" },
  { id: "orders", title: "guideText.k066", text: "guideText.k067" },
]

const GLOSSARY = [
  { term: "Best Bid", def: "guideText.k072" },
  { term: "Best Ask", def: "guideText.k073" },
  { term: "Mid Price", def: "guideText.k074" },
  { term: "Spread", def: "guideText.k075" },
  { term: "Spread %", def: "guideText.k076" },
  { term: "Average Cost", def: "guideText.k077" },
  { term: "Market Value", def: "guideText.k078" },
  { term: "Unrealized P&L", def: "guideText.k079" },
]

const REFRESH = [
  { name: "Portfolio / Dashboard", every: "guideText.k068" },
  { name: "Orders", every: "guideText.k068" },
]

const SCOPE = [
  "guideText.k082",
  "guideText.k083",
  "guideText.k084",
]

const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })

function IconBox({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
      <Icon className="h-5 w-5" />
    </span>
  )
}

function ModCard({ m }: { m: Mod }) {
  return (
    <div id={m.id} className="scroll-mt-24 rounded-2xl border p-6">
      <div className="flex items-start gap-4">
        <IconBox icon={m.icon} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <h3 className="text-lg font-bold">{m.name}</h3>
            <span className="text-sm text-muted-foreground">{t(m.th)}</span>
          </div>
          <p className="mt-2 text-sm leading-7 text-muted-foreground">{t(m.text)}</p>
          {m.points && (
            <div className="mt-4 flex flex-wrap gap-2">
              {m.points.map((p) => (
                <span key={p} className="rounded-full border bg-muted/40 px-3 py-1 text-xs font-medium">{t(p)}</span>
              ))}
            </div>
          )}
          {m.tip && (
            <div className="mt-4 flex gap-2 rounded-xl bg-emerald-500/10 p-3 text-sm leading-6 text-emerald-700 dark:text-emerald-400">
              <Lightbulb className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{t(m.tip)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function UserGuide({ onBack }: { onBack: () => void }) {
  const { t } = useLanguage()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4">
      <div className="pt-10">
        <button type="button" onClick={onBack}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> {t("guideText.k085")}
        </button>
      </div>

      {/* หัวหน้า */}
      <header className="py-12">
        <span className="inline-block rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-500">
          {t("guideText.k086")}
        </span>
        <h1 className="mt-4 text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{t("guideText.k087")}</h1>
        <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
          {t("guideText.k088")}
        </p>
      </header>

      {/* เริ่มต้น 6 ขั้น */}
      <section className="pb-12">
        <h2 className="text-2xl font-extrabold tracking-tight">{t("guideText.k089")}</h2>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {QUICK.map((q, i) => (
            <button key={q.id} type="button" onClick={() => jump(q.id)}
              className="flex items-center gap-4 rounded-2xl border p-4 text-left transition-colors hover:bg-accent">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-sm font-bold text-black">
                {i + 1}
              </span>
              <span>
                <span className="block font-bold">{t(q.title)}</span>
                <span className="block text-xs text-muted-foreground">{t(q.text)}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-10 pb-16 lg:grid-cols-[200px_1fr]">
        {/* สารบัญ */}
        <aside className="hidden lg:block">
          <nav className="sticky top-24 space-y-5 text-sm">
            {GROUPS.map((g) => (
              <div key={g.id}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-emerald-500">{t(g.title)}</p>
                <ul className="space-y-1.5">
                  {g.mods.map((m) => (
                    <li key={m.id}>
                      <button type="button" onClick={() => jump(m.id)} className="text-muted-foreground hover:text-foreground">
                        {m.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <div className="space-y-1.5 border-t pt-4">
              <button type="button" onClick={() => jump("glossary")} className="block text-muted-foreground hover:text-foreground">{t("guideText.k069")}</button>
              <button type="button" onClick={() => jump("refresh")} className="block text-muted-foreground hover:text-foreground">{t("guideText.k070")}</button>
              <button type="button" onClick={() => jump("scope")} className="block text-muted-foreground hover:text-foreground">{t("guideText.k071")}</button>
            </div>
          </nav>
        </aside>

        <div className="min-w-0 space-y-12">
          {/* แต่ละหมวด */}
          {GROUPS.map((g) => (
            <section key={g.id} id={g.id} className="scroll-mt-24">
              <h2 className="text-2xl font-extrabold tracking-tight">{t(g.title)}</h2>
              <div className="mt-5 space-y-4">
                {g.mods.map((m) => <ModCard key={m.id} m={m} />)}
              </div>
            </section>
          ))}

          {/* คำศัพท์ */}
          <section id="glossary" className="scroll-mt-24">
            <h2 className="text-2xl font-extrabold tracking-tight">{t("guideText.k069")}</h2>
            <div className="mt-5 overflow-hidden rounded-2xl border">
              {GLOSSARY.map((g, i) => (
                <div key={g.term} className={`grid gap-1 px-5 py-4 sm:grid-cols-[160px_1fr] sm:gap-4 ${i ? "border-t" : ""}`}>
                  <span className="font-semibold">{g.term}</span>
                  <span className="text-sm leading-6 text-muted-foreground">{t(g.def)}</span>
                </div>
              ))}
            </div>
          </section>

          {/* การอัปเดตข้อมูล */}
          <section id="refresh" className="scroll-mt-24">
            <h2 className="text-2xl font-extrabold tracking-tight">{t("guideText.k070")}</h2>
            <div className="mt-5 rounded-2xl border p-6">
              <div className="flex items-center gap-2 font-bold">
                <RefreshCw className="h-5 w-5 text-emerald-500" /> {t("guideText.k080")}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {REFRESH.map((r) => (
                  <div key={r.name} className="flex items-center justify-between rounded-xl bg-muted/40 px-4 py-3 text-sm">
                    <span>{r.name}</span>
                    <span className="font-semibold text-emerald-500">{t(r.every)}</span>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-sm leading-6 text-muted-foreground">
                {t("guideText.k081")}
              </p>
            </div>
          </section>

          {/* ขอบเขต */}
          <section id="scope" className="scroll-mt-24">
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6">
              <div className="flex items-center gap-2 text-amber-500">
                <AlertTriangle className="h-5 w-5" />
                <p className="font-bold">{t("guideText.k071")}</p>
              </div>
              <ul className="mt-4 space-y-2">
                {SCOPE.map((s) => (
                  <li key={t(s)} className="flex gap-2 text-sm leading-6 text-muted-foreground">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                    {t(s)}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
