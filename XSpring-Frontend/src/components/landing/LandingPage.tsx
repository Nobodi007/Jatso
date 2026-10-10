import { useEffect, useState } from "react"
import { Globe, Menu, Search, X } from "lucide-react"
import MarketSection from "./MarketSection"
import NewsSection from "./NewsSection"

type LandingPageProps = {
  onLogin: () => void
  onRegister: () => void
}

// แก้ข้อความตรงนี้ได้เลย
const BRAND = "Nobodi"
const HERO_TITLE = "เริ่มต้นลงทุนคริปโตอย่างมีระบบ ไปกับ Nobodi"
const HERO_SUB =
  "ดูราคาตลาดแบบสด ทดลองลงทุนย้อนหลัง และฝึกซื้อขายในบัญชีจำลองก่อนตัดสินใจจริง ทุกอย่างอยู่ในที่เดียว"
const MENU = ["ตลาด", "การซื้อขาย", "เรียนรู้", "ข่าว", "ลองลงทุนย้อนหลัง"]

const CANDLES = [
  { x: 60, w1: 150, w2: 240, b: 170, h: 45, up: false },
  { x: 110, w1: 140, w2: 225, b: 160, h: 45, up: true },
  { x: 160, w1: 120, w2: 210, b: 135, h: 55, up: true },
  { x: 210, w1: 130, w2: 215, b: 150, h: 45, up: false },
  { x: 260, w1: 85, w2: 185, b: 100, h: 65, up: true },
  { x: 310, w1: 60, w2: 150, b: 75, h: 55, up: true },
  { x: 360, w1: 40, w2: 120, b: 55, h: 45, up: true },
]

function HeroArt() {
  return (
    <svg viewBox="0 0 420 300" className="h-auto w-full max-w-md" aria-hidden="true">
      <rect x="10" y="10" width="400" height="280" rx="24" className="fill-muted/40 stroke-border" />
      {CANDLES.map((c) => (
        <g key={c.x}>
          <line x1={c.x} x2={c.x} y1={c.w1} y2={c.w2} strokeWidth={2} className={c.up ? "stroke-emerald-500" : "stroke-red-500"} />
          <rect x={c.x - 12} y={c.b} width={24} height={c.h} rx={4} className={c.up ? "fill-emerald-500" : "fill-red-500"} />
        </g>
      ))}
      <polyline
        points="60,200 110,182 160,162 210,172 260,132 310,102 360,78"
        fill="none"
        strokeWidth={3}
        strokeDasharray="6 6"
        strokeLinecap="round"
        className="stroke-foreground/50"
      />
    </svg>
  )
}

export default function LandingPage({ onLogin, onRegister }: LandingPageProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const go = (label: string) => {
    setMenuOpen(false)
    if (label === "ตลาด") {
      setView("market")
      window.scrollTo({ top: 0 })
    } else if (label === "ข่าว") {
      setView("news")
      window.scrollTo({ top: 0 })
    } else {
      onLogin()
    }
  }

  const go = (label: string) => {
    setMenuOpen(false)
    if (label === "ตลาด") {
      setView("market")
      window.scrollTo({ top: 0 })
    } else {
      onLogin()
    }
  }
  
  // หน้านี้อยู่นอก AppInner จึงตั้งธีมเองให้ตรงกับที่เคยเลือกไว้
  useEffect(() => {
    let dark = window.matchMedia("(prefers-color-scheme: dark)").matches
    try {
      const saved = localStorage.getItem("theme")
      if (saved === "light" || saved === "dark") dark = saved === "dark"
    } catch {
      // ใช้ค่าตามเครื่อง
    }
    document.documentElement.classList.toggle("dark", dark)
  }, [])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
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
                  (label === "ตลาด" && view === "market") || (label === "ข่าว" && view === "news")
                    ? "border-b-2 border-emerald-500 pb-0.5 font-semibold text-foreground"
                    : "text-muted-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              aria-label="ค้นหา"
              onClick={onLogin}
              className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Search className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onLogin}
              className="hidden rounded-md px-3 py-1.5 text-sm font-medium hover:bg-accent sm:block"
            >
              เข้าสู่ระบบ
            </button>
            <button
              type="button"
              onClick={onRegister}
              className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400"
            >
              ลงทะเบียน
            </button>
            <button
              type="button"
              aria-label="ภาษา"
              className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Globe className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="เมนู"
              onClick={() => setMenuOpen((v) => !v)}
              className="rounded-md p-2 hover:bg-accent md:hidden"
            >
              {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {menuOpen && (
          <div className="border-t px-4 py-2 md:hidden">
            {[...MENU, "เข้าสู่ระบบ"].map((label) => (
              <button
                key={label}
                type="button"
                onClick={() => (label === "เข้าสู่ระบบ" ? onLogin() : go(label))}
                className="block w-full py-2 text-left text-sm"
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </header>

      {view === "market" ? (
        <MarketSection onLogin={onLogin} onRegister={onRegister} />
      ) : view === "news" ? (
        <NewsSection />
      ) : (
      <main className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-16 lg:grid-cols-2 lg:py-24">
        <div>
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">{HERO_TITLE}</h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground">{HERO_SUB}</p>
          <button
            type="button"
            onClick={onRegister}
            className="mt-8 rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
          >
            สมัครตอนนี้
          </button>
        </div>
        <div className="flex justify-center lg:justify-end">
          <HeroArt />
        </div>
      </main>
      )}
    </div>
  )
}
