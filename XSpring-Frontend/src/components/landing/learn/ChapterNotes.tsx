import { useEffect, useMemo, useRef, useState } from "react"
import { Search, Menu, X } from "lucide-react"
import { chapters, type Block } from "./notes-data"
import { useLanguage } from "../../../i18n/LanguageContext"


const chapterTitlesEn: Record<string, string> = {
  ch1: "Digital Assets & Web3 Fundamentals", ch2: "Fintech and Digital Money", ch3: "Cryptocurrency Technical Concepts",
  ch4: "Smart Contract Platforms", ch5: "DeFi and Decentralized Infrastructure", ch6: "Tokenization and Real-World Assets",
  ch7: "Digital Asset Custody and Security", ch8: "Digital Asset Markets and Regulation", ch9: "Careers in Digital Assets",
}
const sectionTitlesEn: Record<string, string> = {
  s11: "1.1 Background: A Crisis of Trust", s12: "1.2 The Evolution of the Internet", s13: "1.3 Tokenisation & Tokenomics",
  s14: "1.4 Decentralization & DLT", s15: "1.5 Smart Contracts & Gas", s16: "1.6 DApps & Asset Custody",
  s21: "2.1 What Is Fintech?", s22: "2.2 The Evolution of Fintech", s23: "2.3 Blockchain & Bitcoin Basics", s24: "2.4 The History of Money",
  s25: "2.5 Stablecoins", s26: "2.6 CBDC", s27: "2.7 Comparing Types of Digital Money", s31: "3.0 Overview", s32: "3.1 Asymmetric Cryptography",
  s33: "3.2 Distributed Ledger & Proof-of-Work", s34: "3.3 Scaling Bitcoin", s41: "4.1 Smart Contract Platforms", s42: "4.2 Off-chain Scaling Solutions",
  s43: "4.3 Essential Platform Metrics", s44: "4.4 Investment Metrics", s45: "4.5 Blockchain Business Use Cases",
  s51: "5.1 Decentralized Finance (DeFi)", s52: "5.2 Essential DEX Metrics", s53: "5.3 DEX Investment Metrics", s54: "5.4 Infrastructure",
  s55: "5.5 Staking Solutions", s56: "5.6 DePIN and Other Applications", s57: "5.7 Challenges to Consider",
  s61: "6.1 Understanding Tokenization", s62: "6.2 Real-World Assets (RWAs)", s63: "6.3 Legal Framework and Regulation", s64: "6.4 The Seven-Step Tokenization Process",
  s65: "6.5 Impacts and Risk Management", s71: "7.1 Introduction to Digital Asset Custody", s72: "7.2 Data Encryption Basics",
  s73: "7.3 Wallet Types and Risks", s74: "7.4 Security Awareness", s75: "7.5 Institutional-Grade Custody", s76: "7.6 Enterprise Security Best Practices",
  s81: "8.1 Money, Capital, and Digital Asset Markets", s82: "8.2 Market Ecosystem and Thailand's Digital Asset Emergency Decree B.E. 2561",
  s83: "8.3 Fundraising Through Digital Tokens (ICO)", s84: "8.4 Regulation of Digital Asset Businesses", s85: "8.5 Market Abuse Prevention, Penalties, Sandbox, and Tax",
  s86: "8.6 Ethics, Advertising, and Mule Accounts", s91: "9.1 Thailand's Crypto and Web3 Job Market", s92: "9.2 Roles and Market Demand",
  s93: "9.3 Skills in Demand", s94: "9.4 Career Roadmap in Digital Assets", s95: "9.5 Career Preparation and Resume Writing",
  s96: "9.6 Eight Common Interview Questions", s97: "9.7 Job Search Red Flags",
}
function chapterTitle(id: string, title: string, lang: string) { return lang === "en" ? chapterTitlesEn[id] ?? title : title }
function sectionTitle(id: string, title: string, lang: string) { return lang === "en" ? sectionTitlesEn[id] ?? title : title }

function BlockView({ block }: { block: Block }) {
  switch (block.t) {
    case "p":
      return <p className="text-sm leading-7 text-foreground/90">{block.text}</p>
    case "h4":
      return <h4 className="mt-4 text-sm font-semibold text-emerald-500">{block.text}</h4>
    case "box":
      return (
        <div className="rounded-r-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-4 py-3 text-sm leading-7 text-foreground/90">
          {block.text}
        </div>
      )
    case "list":
      return block.ordered ? (
        <ol className="ml-5 list-decimal space-y-1.5 text-sm leading-7 text-foreground/90 marker:text-emerald-500 marker:font-semibold">
          {block.items.map((it, i) => <li key={i}>{it}</li>)}
        </ol>
      ) : (
        <ul className="space-y-1.5">
          {block.items.map((it, i) => (
            <li key={i} className="flex gap-2 text-sm leading-7 text-foreground/90">
              <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-emerald-500" />
              <span>{it}</span>
            </li>
          ))}
        </ul>
      )
    case "tags":
      return (
        <div className="flex flex-wrap gap-1.5">
          {block.items.map((it, i) => (
            <span key={i} className="rounded-full border bg-muted px-2.5 py-1 text-xs text-muted-foreground">{it}</span>
          ))}
        </div>
      )
    case "table":
      return (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[480px] border-collapse text-sm">
            <thead>
              <tr className="bg-muted">
                {block.head.map((h, i) => (
                  <th key={i} className="border-b px-3 py-2 text-left text-xs font-medium text-muted-foreground">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, ri) => (
                <tr key={ri} className="border-b last:border-b-0 hover:bg-accent/40">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-2 align-top leading-6 text-foreground/90">{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
  }
}

export default function ChapterNotes() {
  const { t: tr, lang } = useLanguage()
  const [query, setQuery] = useState("")
  const [activeId, setActiveId] = useState<string>(chapters[0]?.sections[0]?.id ?? "")
  const [navOpen, setNavOpen] = useState(false)
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({})

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActiveId(entry.target.id)
        })
      },
      { rootMargin: "-10% 0px -75% 0px" }
    )
    Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el))
    return () => observer.disconnect()
  }, [])

  const q = query.trim().toLowerCase()
  const filteredChapters = useMemo(() => {
    if (!q) return chapters
    return chapters
      .map((ch) => ({
        ...ch,
        sections: ch.sections.filter((s) => sectionTitle(s.id, s.title, lang).toLowerCase().includes(q) || chapterTitle(ch.id, ch.title, lang).toLowerCase().includes(q)),
      }))
      .filter((ch) => ch.sections.length > 0)
  }, [q, lang])

  const scrollToSection = (id: string) => {
    sectionRefs.current[id]?.scrollIntoView({ behavior: "smooth", block: "start" })
    setNavOpen(false)
  }

  return (
    <div className="relative grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      {/* ปุ่มเปิดสารบัญ (มือถือ) */}
      <button
        type="button"
        onClick={() => setNavOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm font-medium lg:hidden"
      >
        {navOpen ? <X className="size-4" /> : <Menu className="size-4" />}
        {tr("learnPage.toc")}
      </button>

      {/* สารบัญ */}
      <nav
        className={`${navOpen ? "block" : "hidden"} lg:block lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto rounded-xl border bg-card p-3`}
      >
        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={tr("learnPage.searchTopic")}
            className="w-full rounded-md border bg-background py-1.5 pl-8 pr-2 text-xs outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </div>
        <div className="space-y-4">
          {filteredChapters.map((ch) => (
            <div key={ch.id}>
              <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold text-foreground">
                <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: ch.color }} />
                {tr("learnPage.chapter")} {ch.num}
              </div>
              <div className="space-y-0.5">
                {ch.sections.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => scrollToSection(s.id)}
                    className={`block w-full truncate rounded-md border-l-2 px-2 py-1 text-left text-xs transition-colors ${
                      activeId === s.id
                        ? "border-emerald-500 bg-emerald-500/10 font-medium text-emerald-500"
                        : "border-transparent text-muted-foreground hover:bg-accent hover:text-foreground"
                    }`}
                  >
                    {s.title}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </nav>

      {/* เนื้อหา */}
      <div className="space-y-10">
        {chapters.map((ch) => (
          <div key={ch.id}>
            <div className="mb-4 flex items-baseline gap-3 border-l-4 pl-3" style={{ borderColor: ch.color }}>
              <span className="text-xs font-semibold tracking-wide" style={{ color: ch.color }}>{tr("learnPage.chapterFull", { num: ch.num })}</span>
              <h2 className="text-lg font-bold leading-snug">{chapterTitle(ch.id, ch.title, lang)}</h2>
            </div>
            <div className="space-y-4">
              {ch.sections.map((s) => (
                <section
                  key={s.id}
                  id={s.id}
                  ref={(el) => { sectionRefs.current[s.id] = el }}
                  className="scroll-mt-20 rounded-xl border bg-card p-4"
                >
                  <h3 className="mb-3 text-sm font-bold">{sectionTitle(s.id, s.title, lang)}</h3>
                  <div className="space-y-3">
                    {s.blocks.map((b, i) => <BlockView key={i} block={b} />)}
                  </div>
                </section>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
