import { useLanguage } from "../../i18n/LanguageContext"

type FooterLink = { label: string; go?: string; asset?: string; page?: string; highlight?: boolean; href?: string }

const ABOUT: FooterLink[] = [
  { label: "footer.history", go: "ประวัติความเป็นมา" },
  { label: "footer.system", page: "about" },
  { label: "footer.guide", page: "guide" },
  { label: "footer.privacy", page: "privacy" },
  { label: "footer.disclosure", page: "disclosure" },
  { label: "footer.news", go: "ข่าว" },
  { label: "footer.contact", highlight: true, href: "https://www.linkedin.com/in/thiraphat-niyom-11044727b" },
]

const SERVICES: FooterLink[] = [
  { label: "footer.tradingCenter", go: "การซื้อขาย" },
  { label: "nav.market", go: "ตลาด" },
  { label: "nav.backtest", go: "ลองลงทุนย้อนหลัง" },
  { label: "footer.buyBtc", asset: "BTC" },
  { label: "footer.buyEth", asset: "ETH" },
  { label: "footer.buyUsdt", asset: "USDT" },
  { label: "footer.buyDoge", asset: "DOGE" },
]

type Props = {
  onGo: (label: string) => void
  onOpenCoin: (asset: string) => void
  onPage?: (page: string) => void
}

export default function Footer({ onGo, onOpenCoin, onPage }: Props) {
  const { t, lang } = useLanguage()
  const click = (l: FooterLink) => {
    if (l.page) onPage?.(l.page)
    else if (l.asset) onOpenCoin(l.asset)
    else if (l.go) onGo(l.go)
  }

  const Column = ({ title, links }: { title: string; links: FooterLink[] }) => (
    <div>
      <p className="font-semibold">{title}</p>
      <ul className="mt-3 space-y-2">
        {links.map((l) => (
              <li key={l.label}>
                {l.href ? (
                  <a
                    href={l.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`text-left ${
                      l.highlight ? "text-sky-500 hover:text-sky-400" : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {t(l.label)}
                  </a>
                ) : (
                  <button
                    type="button"
                    onClick={() => click(l)}
                    className={`text-left ${
                      l.highlight ? "text-sky-500 hover:text-sky-400" : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {t(l.label)}
                  </button>
                )}
            </li>
        ))}
      </ul>
    </div>
  )

  return (
    <footer className="border-t">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm md:grid-cols-4">
        <div>
          <p className="text-lg font-extrabold">Nobodi</p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{t("footer.tagline")}</p>
        </div>
        <Column title={t("footer.aboutTitle")} links={ABOUT} />
        <Column title={t("footer.servicesTitle")} links={SERVICES} />
        <div>
          <p className="font-semibold">{t("footer.noticeTitle")}</p>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            {t("footer.notice")}
          </p>
          <button
            type="button"
            onClick={() => onPage?.("faq")}
            className="mt-4 text-left text-muted-foreground hover:text-foreground"
          >
            {lang === "th" ? "คำถามที่พบบ่อย" : "FAQ"}
          </button>
        </div>
      </div>
      <p className="border-t py-4 text-center text-xs text-muted-foreground">© Nobodi</p>
    </footer>
  )
}
