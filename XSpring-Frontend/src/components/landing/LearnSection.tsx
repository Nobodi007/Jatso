import { useState } from "react"
import { BookOpen, Coins } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"
import ChapterNotes from "./learn/ChapterNotes"
import CoinEncyclopedia from "./learn/CoinEncyclopedia"

type Tab = "notes" | "coins"

export default function LearnSection() {
  const [tab, setTab] = useState<Tab>("notes")
  const { t } = useLanguage()

  return (
    <main className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">{t("learnPage.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("learnPage.subtitle")}</p>
        </div>
      </div>

      <div className="mt-6 flex gap-2 border-b pb-3">
        <button
          type="button"
          onClick={() => setTab("notes")}
          className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
            tab === "notes" ? "bg-emerald-500 text-black" : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
        >
          <BookOpen className="size-4" /> {t("learnPage.notesTab")}
        </button>
        <button
          type="button"
          onClick={() => setTab("coins")}
          className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
            tab === "coins" ? "bg-emerald-500 text-black" : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
        >
          <Coins className="size-4" /> {t("learnPage.coinsTab")}
        </button>
      </div>

      <div className="mt-6">
        {tab === "notes" ? <ChapterNotes /> : <CoinEncyclopedia />}
      </div>
    </main>
  )
}
