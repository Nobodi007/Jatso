import { useEffect, useState } from "react"
import { useLanguage } from "../../i18n/LanguageContext"

// เวลาทำการปกติของตลาดหุ้นสหรัฐ (NYSE / Nasdaq): จันทร์-ศุกร์ 09:30-16:00 เวลานิวยอร์ก
// Intl จัดการเวลาออมแสงให้เอง / คำนวณในเบราว์เซอร์ล้วน ไม่เรียก API (ไม่เสีย egress)
// หมายเหตุ: ยังไม่รวมวันหยุดตลาด จึงเป็นสถานะตามเวลาทำการปกติเท่านั้น
function usMarketOpen(now = new Date()): boolean {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(now)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ""
  const day = get("weekday")
  if (day === "Sat" || day === "Sun") return false
  const mins = (Number(get("hour")) % 24) * 60 + Number(get("minute")) // บางเบราว์เซอร์คืน "24" ตอนเที่ยงคืน
  return mins >= 9 * 60 + 30 && mins < 16 * 60
}

export default function MarketStatusBadge() {
  const { t } = useLanguage()
  const [open, setOpen] = useState(() => usMarketOpen())

  useEffect(() => {
    const id = setInterval(() => setOpen(usMarketOpen()), 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/5 px-3 py-1.5 text-xs">
      <span
        className={`h-2 w-2 rounded-full ${open ? "animate-pulse bg-emerald-500" : "bg-muted-foreground/50"}`}
        aria-hidden="true"
      />
      <span className="font-semibold">{t("hero.usMarket")}</span>
      <span className={open ? "text-emerald-500" : "text-muted-foreground"}>
        {open ? t("hero.usOpen") : t("hero.usClosed")}
      </span>
    </div>
  )
}
