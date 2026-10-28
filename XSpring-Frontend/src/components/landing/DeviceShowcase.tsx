import { useEffect, useState } from "react"
import { MacbookPro } from "../ui/macbook-pro"
import { useLanguage } from "../../i18n/LanguageContext"
import CoinsOverlay from "./CoinsOverlay";

// ภาพหน้าจอจริงของ Nobodi: วางไฟล์ไว้ที่ XSpring-Frontend/public/mockups/
const SHOTS = {
  crypto: "/mockups/crypto.jpg",
  stocks: "/mockups/stocks.jpg",
}

// โหลดภาพล่วงหน้า: ถ้าไฟล์ยังไม่มีหรือโหลดไม่ได้ จะไม่แสดงทั้ง section (ไม่ให้เห็นเครื่องจอดำเปล่าๆ)
function useShotsReady(urls: string[]) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let alive = true
    Promise.all(
      urls.map(
        (u) =>
          new Promise<boolean>((resolve) => {
            const img = new Image()
            img.onload = () => resolve(true)
            img.onerror = () => resolve(false)
            img.src = u
          }),
      ),
    ).then((r) => alive && setReady(r.every(Boolean)))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return ready
}

export default function DeviceShowcase({ onRegister }: { onRegister: () => void }) {
  const { t } = useLanguage()
  const ready = useShotsReady([SHOTS.crypto, SHOTS.stocks])
  if (!ready) return null

  return (
    <section id="tour-devices" className="mx-auto max-w-7xl px-4 py-16">
      <h2 className="text-center text-3xl font-extrabold tracking-tight">{t("showcase.title")}</h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted-foreground">{t("showcase.subtitle")}</p>

      <div className="mt-10 grid items-center gap-10 lg:grid-cols-[0.75fr_1.25fr]">
        <div>
          <p className="text-base leading-7 text-muted-foreground">{t("showcase.text")}</p>
          <ul className="mt-5 space-y-2 text-sm">
            <li className="flex gap-2">
              <span className="text-emerald-500">●</span>
              <span>{t("showcase.p1")}</span>
            </li>
            <li className="flex gap-2">
              <span className="text-emerald-500">●</span>
              <span>{t("showcase.p2")}</span>
            </li>
          </ul>
          <button
            type="button"
            onClick={onRegister}
            className="mt-8 rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
          >
            {t("cta.register")}
          </button>
        </div>

        {/* MacBook 2 เครื่องซ้อนกัน (ไม่เอียง 3 มิติ เพราะการเอียงทำให้เบราว์เซอร์ย่อภาพจนเบลอ):
            เครื่องหลัง (หุ้นสหรัฐ) เล็กกว่าและอยู่ขวาบน เครื่องหน้า (คริปโต) ใหญ่กว่าอยู่ซ้ายล่าง
            บนจอเล็กแสดงเครื่องหน้าเครื่องเดียว เพราะซ้อนกันแล้วตัวหนังสือในจอเล็กเกินอ่าน */}
     
      <div className="hero-visual relative mx-auto w-full max-w-3xl sm:aspect-[16/11]">
        <MacbookPro
          src={SHOTS.stocks}
          alt={t("showcase.altStocks")}
          className="hidden drop-shadow-[0_20px_30px_rgba(0,0,0,0.35)] sm:absolute sm:right-0 sm:top-0 sm:block sm:w-[62%]"
        />
        <MacbookPro
          src={SHOTS.crypto}
          alt={t("showcase.altCrypto")}
          className="drop-shadow-[0_25px_35px_rgba(0,0,0,0.45)] sm:absolute sm:bottom-0 sm:left-0 sm:w-[78%]"
        />
        <CoinsOverlay />
      </div>
      </div>
    </section>
  )
}
