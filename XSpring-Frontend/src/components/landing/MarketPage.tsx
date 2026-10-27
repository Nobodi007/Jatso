import AssetToggle from "./AssetToggle"
import MarketSection from "./MarketSection"
import StockMarketSection from "./StockMarketSection"
import { useAssetTab } from "../../hooks/useAssetTab"

type Props = {
  onLogin: () => void
  onRegister: () => void
  onSelectStock: (symbol: string) => void
}

// หน้า Market บน landing: สลับระหว่างตลาดคริปโต (เดิม) กับตลาดหุ้นสหรัฐ (ใหม่)
export default function MarketPage({ onLogin, onRegister, onSelectStock }: Props) {
  const [tab] = useAssetTab()
  return (
    <>
      <div className="mx-auto max-w-7xl px-4 pt-8">
        <AssetToggle />
      </div>
      {tab === "crypto" ? (
        <MarketSection onLogin={onLogin} onRegister={onRegister} />
      ) : (
        <StockMarketSection onRegister={onRegister} onSelectStock={onSelectStock} />
      )}
    </>
  )
}
