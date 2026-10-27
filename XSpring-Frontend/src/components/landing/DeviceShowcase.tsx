import { useEffect, useState } from "react"
import { MacbookPro } from "../ui/macbook-pro"
import { useLanguage } from "../../i18n/LanguageContext"

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
    <section id="tour-devices" className="mx-auto max-w-6xl px-4 py-16">
      <h2 className="text-center text-3xl font-extrabold tracking-tight">{t("showcase.title")}</h2>
      <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted-foreground">{t("showcase.subtitle")}</p>

      <div className="mt-10 grid items-center gap-10 lg:grid-cols-[0.8fr_1.2fr]">
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

        {/* MacBook 2 เครื่อง คนละมุม: เครื่องหลัง (หุ้นสหรัฐ) เอียงไปทางขวา เครื่องหน้า (คริปโต) เอียงไปทางซ้าย
            บนจอเล็กแสดงเครื่องหน้าเครื่องเดียว เพราะซ้อนกันแล้วตัวหนังสือในจอเล็กเกินอ่าน */}
        <div className="relative mx-auto w-full max-w-2xl sm:aspect-[16/11]" style={{ perspective: "1400px" }}>
          <div
            className="absolute right-0 top-0 hidden w-[66%] sm:block"
            style={{ transform: "rotateY(-22deg) rotateX(4deg) rotateZ(2deg)", transformOrigin: "right center" }}
          >
            <MacbookPro
              src={SHOTS.stocks}
              role="img"
              aria-label={t("showcase.altStocks")}
              className="h-auto w-full drop-shadow-[0_25px_35px_rgba(0,0,0,0.45)]"
            />
          </div>
          <div
            className="relative w-full sm:absolute sm:bottom-0 sm:left-0 sm:w-[76%]"
            style={{ transform: "rotateY(14deg) rotateX(3deg)", transformOrigin: "left center" }}
          >
            <MacbookPro
              src={SHOTS.crypto}
              role="img"
              aria-label={t("showcase.altCrypto")}
              className="h-auto w-full drop-shadow-[0_30px_40px_rgba(0,0,0,0.5)]"
            />
          </div>
        </div>
      </div>
    </section>
  )
}
