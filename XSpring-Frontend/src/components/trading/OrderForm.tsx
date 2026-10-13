import { useEffect, useState } from "react"
import { dp, splitSymbol } from "../../lib/market"
import { useLanguage } from "../../i18n/LanguageContext"

type Props = { symbol: string; last?: number; onLogin: () => void; onRegister: () => void }

function Side({
  last, base, quote, asset, accent, cta, ctaClass, onCta, market, t,
}: {
  last?: number; base: string; quote: string; asset: string; accent: string
  cta: string; ctaClass: string; onCta: () => void; market: boolean
  t: (key: string) => string
}) {
  const [price, setPrice] = useState("")
  const [qty, setQty] = useState("")
  const [pct, setPct] = useState(0)

  useEffect(() => {
    if (last) setPrice(last.toFixed(dp(last)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset])

  return (
    <div>
      <div className="mb-2 flex justify-between text-xs text-zinc-500">
        <span>{t("tradePage.balance")}</span><span>- {asset}</span>
      </div>
      <label className="mb-3 flex items-center justify-between rounded-lg bg-[#1a1a1a] px-4 py-3 text-sm">
        <span className="text-zinc-500">{t("tradePage.price")}</span>
        <span className="flex items-center gap-2">
          <input value={market ? t("tradePage.marketPrice") : price} disabled={market}
            onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal"
            className="w-32 bg-transparent text-right outline-none disabled:text-zinc-400" />
          <span>{quote}</span>
        </span>
      </label>
      <label className="mb-3 flex items-center justify-between rounded-lg bg-[#1a1a1a] px-4 py-3 text-sm">
        <span className="text-zinc-500">{t("tradePage.amount")}</span>
        <span className="flex items-center gap-2">
          <input value={qty} onChange={(e) => setQty(e.target.value.replace(/[^\d.]/g, ""))}
            inputMode="decimal" placeholder="0.00"
            className="w-32 bg-transparent text-right outline-none placeholder:text-zinc-600" />
          <span>{base}</span>
        </span>
      </label>
      <input type="range" min={0} max={100} step={25} value={pct}
        onChange={(e) => setPct(Number(e.target.value))} style={{ accentColor: accent }}
        className="mb-4 w-full" aria-label={t("tradePage.percent")} />
      <button type="button" onClick={onCta} className={`w-full rounded-lg py-3 text-sm font-bold ${ctaClass}`}>{cta}</button>
    </div>
  )
}

export default function OrderForm({ symbol, last, onLogin, onRegister }: Props) {
  const { base, quote } = splitSymbol(symbol)
  const { t } = useLanguage()
  const [type, setType] = useState<"LIMIT" | "MARKET">("LIMIT")
  const market = type === "MARKET"

  return (
    <div className="bg-[#0f0f0f] p-6">
      <div className="mb-4 border-b border-white/10">
        <span className="inline-block border-b-2 border-emerald-500 pb-2 text-sm font-semibold">{t("tradePage.spot")}</span>
      </div>
      <div className="mb-5 flex flex-wrap gap-5 text-sm">
        <button type="button" onClick={() => setType("LIMIT")}
          className={type === "LIMIT" ? "font-semibold text-emerald-500" : "text-zinc-400 hover:text-zinc-200"}>
          {t("tradePage.limitOrder")}
        </button>
        <button type="button" onClick={() => setType("MARKET")}
          className={type === "MARKET" ? "font-semibold text-emerald-500" : "text-zinc-400 hover:text-zinc-200"}>
          {t("tradePage.marketOrder")}
        </button>
      </div>
      <div className="grid gap-8 md:grid-cols-2">
        <Side base={base} quote={quote} asset={quote} accent="#10b981" cta={t("tradePage.signUp")}
          ctaClass="bg-emerald-500 text-black hover:bg-emerald-400" onCta={onRegister} market={market} last={last} t={t} />
        <Side base={base} quote={quote} asset={base} accent="#f6465d" cta={t("tradePage.logIn")}
          ctaClass="border border-white/20 text-white hover:bg-white/10" onCta={onLogin} market={market} last={last} t={t} />
      </div>
      <p className="mt-4 text-center text-xs text-zinc-500">{t("tradePage.signInToTrade")}</p>
    </div>
  )
}
