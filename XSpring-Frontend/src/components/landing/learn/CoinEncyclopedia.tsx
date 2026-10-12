import { useMemo, useState } from "react"
import { Search, CheckCircle2, AlertTriangle, XCircle } from "lucide-react"
import { COIN_PROFILES, COIN_ACCENT, SUPPORTED_ASSETS } from "./coin-data"
import { ENGLISH_COIN_PROFILES } from "./coin-data.en"
import { useLanguage } from "../../../i18n/LanguageContext"

function hexToRgb(hex: string) {
  const h = hex.replace("#", "")
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `${r},${g},${b}`
}

function CoinLogo({ symbol, accent, size = 44 }: { symbol: string; accent: string; size?: number }) {
  const [broken, setBroken] = useState(false)
  const src = `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/svg/color/${symbol.toLowerCase()}.svg`
  if (broken) {
    return (
      <div
        className="flex shrink-0 items-center justify-center rounded-full font-bold text-white"
        style={{ width: size, height: size, backgroundColor: accent, fontSize: symbol.length > 3 ? 12 : 15 }}
      >
        {symbol}
      </div>
    )
  }
  return (
    <img
      src={src}
      alt={symbol}
      width={size}
      height={size}
      onError={() => setBroken(true)}
      className="shrink-0 rounded-full bg-muted object-cover"
      style={{ width: size, height: size }}
    />
  )
}

type CoinProfile = {
  name: string
  category: string
  tagline: string
  about: string
  launched: string
  creator: string
  consensus: string
  supply: string
  chapters: string | number
  strengths: string[]
  risks: string[]
  tech: string[]
  tokenomics: string[]
  timeline: [string, string][]
  ecosystem: string[]
  metrics: string[]
  myths: { myth: string; fact: string }[]
}

const TABS = [
  { key: "overview", label: "overview" },
  { key: "tech", label: "tech" },
  { key: "tokenomics", label: "tokenomics" },
  { key: "timeline", label: "timeline" },
  { key: "ecosystem", label: "ecosystem" },
  { key: "metrics", label: "metrics" },
  { key: "myths", label: "myths" },
] as const
type TabKey = (typeof TABS)[number]["key"]

export default function CoinEncyclopedia() {
  const { t: tr, lang } = useLanguage()
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState(SUPPORTED_ASSETS[0])
  const [tab, setTab] = useState<TabKey>("overview")

  const coins = useMemo(() => {
    const q = search.trim().toLowerCase()
    return SUPPORTED_ASSETS.filter((s) => {
      const p = COIN_PROFILES[s]
      if (!p) return false
      if (!q) return true
      return s.toLowerCase().includes(q) || p.name.toLowerCase().includes(q)
    })
  }, [search])

  const baseProfile = COIN_PROFILES[selected] as unknown as CoinProfile | undefined
  const profile: CoinProfile | undefined =
  baseProfile && lang === "en"
    ? ({ ...baseProfile, ...(ENGLISH_COIN_PROFILES[selected] ?? {}) } as CoinProfile)
    : baseProfile
  const accent = COIN_ACCENT[selected] ?? "#10b981"
  const rgb = hexToRgb(accent)

  if (!profile) return null

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
      {/* รายชื่อเหรียญ */}
      <div className="rounded-xl border bg-card p-3 lg:sticky lg:top-4 lg:self-start">
        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={tr("learnPage.searchCoin")}
            className="w-full rounded-md border bg-background py-1.5 pl-8 pr-2 text-xs outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
          {coins.map((s) => {
            const p = COIN_PROFILES[s]
            const isActive = s === selected
            const a = COIN_ACCENT[s] ?? "#10b981"
            return (
              <button
                key={s}
                type="button"
                onClick={() => { setSelected(s); setTab("overview") }}
                className={`flex shrink-0 items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-xs transition-colors lg:w-full ${
                  isActive ? "border-emerald-500 bg-emerald-500/10" : "hover:bg-accent"
                }`}
              >
                <CoinLogo symbol={s} accent={a} size={24} />
                <div className="min-w-0">
                  <div className="font-semibold leading-tight">{s}</div>
                  <div className="hidden truncate text-[10px] text-muted-foreground lg:block">{p.name}</div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* รายละเอียดเหรียญ */}
      <div className="min-w-0">
        <div
          className="mb-4 flex items-center gap-4 rounded-2xl border p-5"
          style={{
            background: `linear-gradient(135deg, rgba(${rgb},0.30) 0%, rgba(24,26,32,0.6) 65%)`,
            borderColor: `rgba(${rgb},0.4)`,
          }}
        >
          <CoinLogo symbol={selected} accent={accent} size={56} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-bold leading-tight">{profile.name}</h2>
              <span
                className="rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
                style={{ color: accent, borderColor: `rgba(${rgb},0.45)`, backgroundColor: `rgba(${rgb},0.14)` }}
              >
                {profile.category}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{profile.tagline}</p>
          </div>
        </div>

        {/* แท็บ */}
        <div className="mb-4 flex flex-wrap gap-2 border-b pb-3">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.key ? "bg-emerald-500 text-black" : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {tr(`learnPage.tabs.${t.key}`)}
            </button>
          ))}
        </div>

        {tab === "overview" && (
          <div className="space-y-4">
            <div className="rounded-r-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-4 py-3 text-sm leading-7 text-foreground/90">
              {profile.about}
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                [tr("learnPage.launched"), profile.launched],
                [tr("learnPage.creator"), profile.creator],
                [tr("learnPage.consensus"), profile.consensus],
                [tr("learnPage.supply"), profile.supply],
              ].map(([k, v]) => (
                <div key={k} className="rounded-lg border bg-card p-3">
                  <div className="text-[11px] text-muted-foreground">{k}</div>
                  <div className="mt-1 text-sm font-semibold leading-snug">{v}</div>
                </div>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-t-2 border-t-emerald-500 bg-card p-3">
                <h5 className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><CheckCircle2 className="size-4 text-emerald-500" /> {tr("learnPage.strengths")}</h5>
                <ul className="space-y-1.5">
                  {profile.strengths.map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm leading-6 text-foreground/90">
                      <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-500" /><span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-lg border border-t-2 border-t-red-500 bg-card p-3">
                <h5 className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><AlertTriangle className="size-4 text-red-500" /> {tr("learnPage.risks")}</h5>
                <ul className="space-y-1.5">
                  {profile.risks.map((s, i) => (
                    <li key={i} className="flex gap-2 text-sm leading-6 text-foreground/90">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-red-500" /><span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="inline-block rounded-full border border-dashed px-3 py-1.5 text-xs text-muted-foreground">
              📖 {tr("learnPage.readMore", { chapters: profile.chapters })}
            </div>
          </div>
        )}

        {tab === "tech" && (
          <div className="space-y-2">
            {profile.tech.map((t, i) => (
              <div key={i} className="flex items-start gap-3 rounded-lg border bg-card p-3">
                <div
                  className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-bold"
                  style={{ color: accent, borderColor: accent, backgroundColor: `rgba(${rgb},0.15)` }}
                >
                  {i + 1}
                </div>
                <p className="text-sm leading-6 text-foreground/90">{t}</p>
              </div>
            ))}
          </div>
        )}

        {tab === "tokenomics" && (
          <div className="space-y-3">
            <div className="rounded-xl border p-4" style={{ backgroundColor: `rgba(${rgb},0.1)`, borderColor: `rgba(${rgb},0.3)` }}>
              <div className="text-xs text-muted-foreground">📦 {tr("learnPage.supply")}</div>
              <div className="mt-1 text-base font-bold">{profile.supply}</div>
            </div>
            <ul className="space-y-1.5">
              {profile.tokenomics.map((t, i) => (
                <li key={i} className="flex gap-2 rounded-lg bg-muted px-3 py-2 text-sm leading-6 text-foreground/90">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full" style={{ backgroundColor: accent }} />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {tab === "timeline" && (
          <div className="relative ml-2 space-y-4 border-l-2 pl-5" style={{ borderColor: `rgba(${rgb},0.4)` }}>
            {profile.timeline.map(([year, text], i) => (
              <div key={i} className="relative">
                <span
                  className="absolute -left-[26px] top-1.5 size-3 rounded-full"
                  style={{ backgroundColor: accent, boxShadow: `0 0 0 4px rgba(${rgb},0.22)` }}
                />
                <span
                  className="mb-1 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-bold text-black"
                  style={{ backgroundColor: accent }}
                >
                  {year}
                </span>
                <div className="rounded-lg border bg-card px-3 py-2 text-sm leading-6 text-foreground/90">{text}</div>
              </div>
            ))}
          </div>
        )}

        {tab === "ecosystem" && (
          <div className="grid gap-2 sm:grid-cols-2">
            {profile.ecosystem.map((e, i) => (
              <div key={i} className="rounded-lg border bg-card px-3 py-2 text-sm leading-6 text-foreground/90">🔹 {e}</div>
            ))}
          </div>
        )}

        {tab === "metrics" && (
          <div className="space-y-2">
            <div className="grid gap-2 sm:grid-cols-2">
              {profile.metrics.map((m, i) => {
                const [k, v] = m.includes(" — ") ? m.split(" — ") : [m, null]
                return (
                  <div key={i} className="rounded-lg border bg-card px-3 py-2 text-sm leading-6 text-foreground/90">
                    📊 {v ? <><span className="font-semibold">{k}</span> — {v}</> : k}
                  </div>
                )
              })}
            </div>
            <p className="text-xs text-muted-foreground">{tr("learnPage.metricsNote")}</p>
          </div>
        )}

        {tab === "myths" && (
          <div className="space-y-3">
            {profile.myths.map((m, i) => (
              <div key={i} className="overflow-hidden rounded-xl border">
                <div className="flex items-start gap-2 bg-red-500/10 px-4 py-2.5 text-sm font-medium leading-6 text-red-400">
                  <XCircle className="mt-0.5 size-4 shrink-0" /> {m.myth}
                </div>
                <div className="flex items-start gap-2 bg-emerald-500/10 px-4 py-2.5 text-sm leading-6 text-emerald-300">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> {m.fact}
                </div>
              </div>
            ))}
            <p className="text-xs text-muted-foreground">{tr("learnPage.mythsNote")}</p>
          </div>
        )}
      </div>
    </div>
  )
}
