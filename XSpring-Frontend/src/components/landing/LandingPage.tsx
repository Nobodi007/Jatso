import { useEffect, useState } from "react"
import { Menu, Moon, Sparkles, Sun, X } from "lucide-react"
import MarketPage from "./MarketPage"
import NewsSection from "./NewsSection"
import SearchBox from "./SearchBox"
import CoinDetail from "./CoinDetail"
import BacktestSection from "./BacktestSection"
import LearnSection from "./LearnSection"
import TradePage from "../trading/TradePage"
import HomeSections from "./HomeSections"
import AboutSection from "./AboutSection"
import LanguageSwitcher from "../LanguageSwitcher";
import { useLanguage } from "../../i18n/LanguageContext";
import { PriceTicker } from "./LandingEffects"
import { GlobeHero } from "./GlobeHero"
import TourGuide from "./TourGuide";
import ContactPage from "./ContactPage";
import MarketStatusBadge from "./MarketStatusBadge"

type LandingPageProps = {
  onLogin: () => void
  onRegister: () => void
}

type View = "home" | "market" | "news" | "coin" | "backtest" | "trade" | "learn" | "about" | "contact"

const BRAND = "Nobodi"
const MENU = ["ตลาด", "การซื้อขาย", "เรียนรู้", "ข่าว", "ลองลงทุนย้อนหลัง", "ติดต่อเรา"]

// ข้อความไทยด้านบนใช้เป็นรหัสอ้างอิงภายใน (ห้ามแปล) ตัวนี้แมปไปหาคำแปลที่แสดงจริง
const MENU_KEY: Record<string, string> = {
  "ตลาด": "nav.market",
  "การซื้อขาย": "nav.trade",
  "เรียนรู้": "nav.learn",
  "ข่าว": "nav.news",
  "ลองลงทุนย้อนหลัง": "nav.backtest",
  "ติดต่อเรา": "nav.contact",
}

// เมนูไหนเปิดหน้าอะไร (เมนูที่ไม่อยู่ในนี้ = พาไปล็อกอิน)
const VIEW_OF: Record<string, View> = {
  "ตลาด": "market",
  "การซื้อขาย": "trade",
  "เรียนรู้": "learn",
  "ข่าว": "news",
  "ลองลงทุนย้อนหลัง": "backtest",
  "ประวัติความเป็นมา": "about",
  "ติดต่อเรา": "contact",
}

// หน้านี้อยู่นอก AppInner จึงตั้งธีมเองให้ตรงกับที่เคยเลือกไว้
function initialDark(): boolean {
  let dark = window.matchMedia("(prefers-color-scheme: dark)").matches
  try {
    const saved = localStorage.getItem("theme")
    if (saved === "light" || saved === "dark") dark = saved === "dark"
  } catch {
    // ใช้ค่าตามเครื่อง
  }
  return dark
}

export default function LandingPage({ onLogin, onRegister }: LandingPageProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [view, setView] = useState<View>("home")
  const [coin, setCoin] = useState("BTC")
  const [dark, setDark] = useState(initialDark)
  const { t } = useLanguage()
  const [tour, setTour] = useState(false)

// ออกจากหน้าแรก = ปิดทัวร์
useEffect(() => {
  if (view !== "home") setTour(false)
}, [view])

const startTour = () => {
  setMenuOpen(false)
  setView("home")
  window.scrollTo({ top: 0 })
  setTour(true)
}

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
  }, [dark])

  const toggleTheme = () => {
    const next = !dark
    setDark(next)
    try {
      localStorage.setItem("theme", next ? "dark" : "light")
    } catch {
      // บันทึกไม่ได้ก็ใช้ชั่วคราว
    }
  }

  const go = (label: string) => {
    setMenuOpen(false)
    const target = VIEW_OF[label]
    if (target) {
      setView(target)
      window.scrollTo({ top: 0 })
    } else {
      onLogin()
    }
  }

  const openCoin = (asset: string) => {
    setCoin(asset)
    setView("coin")
    window.scrollTo({ top: 0 })
  }
  
  const openStock = (symbol: string) => {
    // จำหุ้นที่เลือกไว้ แล้วพาไปสมัคร หลังล็อกอินแอปจะเปิดหน้าหุ้นตัวนั้นให้ (ดู App.tsx)
    try {
      localStorage.setItem("landing_pending_stock", JSON.stringify({ symbol, ts: Date.now() }))
    } catch {
      /* ข้ามถ้า localStorage ใช้ไม่ได้ */
    }
    onRegister()
  }

    return (
    <div className="min-h-screen bg-background text-foreground">
      <header id="tour-nav" className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4">
          <button type="button" onClick={() => setView("home")} className="text-xl font-extrabold tracking-tight">
            {BRAND}
          </button>

          <nav className="hidden items-center gap-5 text-sm md:flex">
            {MENU.map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => go(label)}
                className={`transition-colors hover:text-foreground ${
                  VIEW_OF[label] === view
                    ? "border-b-2 border-emerald-500 pb-0.5 font-semibold text-foreground"
                    : "text-muted-foreground"
                }`}
              >
                {t(MENU_KEY[label])}
              </button>
            ))}
          </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={startTour}
            aria-label={t("tour.start")}
            className="flex items-center gap-1.5 rounded-md border border-emerald-500/40 px-2.5 py-1.5 text-sm font-medium text-emerald-500 hover:bg-emerald-500/10"
          >
            <Sparkles className="h-4 w-4" />
            <span className="hidden sm:inline">{t("tour.start")}</span>
          </button>
          <SearchBox onSelect={openCoin} onSelectStock={openStock} />
          <button
            type="button"
            onClick={onLogin}
            className="hidden rounded-md px-3 py-1.5 text-sm font-medium hover:bg-accent sm:block"
          >
            {t("nav.login")}
          </button>
            <button
              type="button"
              onClick={onRegister}
              className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400"
            >
              {t("nav.register")}
            </button>
            <button
              type="button"
              aria-label={dark ? t("nav.themeLight") : t("nav.themeDark")}
              onClick={toggleTheme}
              className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>

            <LanguageSwitcher />

            <button
              type="button"
              aria-label={t("nav.menu")}
              onClick={() => setMenuOpen((v) => !v)}
              className="rounded-md p-2 hover:bg-accent md:hidden"
            >
              {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <div className="border-t px-4 py-2 md:hidden">
            {MENU.map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => go(label)}
                className="block w-full py-2 text-left text-sm"
              >
                {t(MENU_KEY[label])}
              </button>
            ))}
            <button
              type="button"
              onClick={onLogin}
              className="block w-full py-2 text-left text-sm"
            >
              {t("nav.login")}
            </button>
          </div>
        )}
      </header>

      {view === "contact" ? (
        <ContactPage />
      ) : view === "market" ? (
        <MarketPage onLogin={onLogin} onRegister={onRegister} onSelectStock={openStock} />
      ) : view === "news" ? (
        <NewsSection />
      ) : view === "backtest" ? (
        <BacktestSection onLogin={onLogin} onRegister={onRegister} />
      ) : view === "trade" ? (
        <TradePage symbol="BTCUSDT" onLogin={onLogin} onRegister={onRegister} />
      ) : view === "about" ? (
        <AboutSection onBack={() => setView("home")} onRegister={onRegister} />
      ) : view === "coin" ? (
        <CoinDetail asset={coin} onBack={() => setView("market")} onLogin={onLogin} onRegister={onRegister} />
      ) : view === "learn" ? (
        <LearnSection />
              ) : (
          <>
            <HomeSections
              onLogin={onLogin}
              onRegister={onRegister}
              onOpenCoin={openCoin}
              onGo={go}
              onSelectStock={openStock}
              heroTitle={t("hero.title")}
              heroSub={t("hero.desc")}
              heroArt={
                <div className="flex w-full flex-col items-center gap-4">
                  <GlobeHero />
                  <MarketStatusBadge />
                </div>
              }
            />
            <PriceTicker />
          </>
        )}
    {tour && view === "home" && (
        <TourGuide
          onClose={() => setTour(false)}
          onRegister={() => {
            setTour(false)
            onRegister()
          }}
        />
      )}
    </div>
  )
}
