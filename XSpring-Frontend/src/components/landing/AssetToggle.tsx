import { useLanguage } from "../../i18n/LanguageContext"
import { useAssetTab } from "../../hooks/useAssetTab"
import type { AssetTab } from "../../hooks/useAssetTab"

export default function AssetToggle() {
  const { t } = useLanguage()
  const [tab, setTab] = useAssetTab()
  return (
    <div role="tablist" className="inline-flex gap-1 rounded-full bg-muted p-1">
      {(["crypto", "stocks"] as AssetTab[]).map((k) => (
        <button
          key={k}
          type="button"
          role="tab"
          aria-selected={tab === k}
          onClick={() => setTab(k)}
          className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
            tab === k ? "bg-emerald-500 text-black" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {t(k === "crypto" ? "search.tabCrypto" : "search.tabStocks")}
        </button>
      ))}
    </div>
  )
}
