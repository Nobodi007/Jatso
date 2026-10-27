import { useMemo, useState } from "react"
import type { ReactNode } from "react"
import { ExternalLink, Info, Search } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"
import brokerData from "../../data/brokers-us.json"
import BrokerLogo from "./BrokerLogo"

type Bi = { th: string; en: string }

type Broker = {
  id: string
  name: string
  entity: string | null
  url: string
  sourceUrl: string
  dataAsOf?: string
  needsConfirm?: string[]
  minInvest: Bi
  commission: Bi
  otherFees: Bi
  extras: Bi
  logo?: string | null
  logoBg?: "light" | "dark"
  // internalNote ในไฟล์ JSON เป็นโน้ตของทีม ไม่แสดงให้ผู้ใช้เห็น
}

type BrokerFile = { checkedAt: string; note: string; brokers: Broker[] }

const data = brokerData as unknown as BrokerFile

type Lang = "th" | "en"

const STR = {
  th: {
    title: "โบรกเกอร์ไทยที่เทรดหุ้นสหรัฐได้",
    sub: "เทียบขั้นต่ำการลงทุนและค่าธรรมเนียมของแต่ละเจ้า ข้อมูลมาจากเอกสารและหน้าเว็บทางการของโบรกเกอร์",
    checked: "ตรวจล่าสุด",
    note:
      "แสดงเฉพาะโบรกเกอร์ที่ยืนยันจากเอกสารหรือหน้าทางการแล้วว่ามีบริการหุ้นสหรัฐ ค่าธรรมเนียมส่วนใหญ่ยังไม่รวม VAT 7% (บางเจ้าไม่ได้ระบุ) ตัวเลขเปลี่ยนได้ โปรดเช็กที่ลิงก์ต้นทางก่อนตัดสินใจ ข้อมูลนี้ไม่ใช่คำแนะนำการลงทุน",
    search: "ค้นหาโบรกเกอร์",
    count: (n: number) => `${n} โบรกเกอร์`,
    empty: "ไม่พบโบรกเกอร์ที่ค้นหา",
    colBroker: "โบรกเกอร์",
    colMin: "ขั้นต่ำการลงทุน",
    colComm: "ค่าคอมมิชชัน",
    colOther: "ค่าธรรมเนียมอื่น",
    site: "เว็บโบรกเกอร์",
    feeSource: "ที่มาของค่าธรรมเนียม",
    asOf: "ข้อมูล ณ",
    logoNote: "โลโก้และชื่อเป็นเครื่องหมายการค้าของเจ้าของ แสดงเพื่อระบุตัวโบรกเกอร์เท่านั้น ไม่ได้เป็นการรับรองหรือความร่วมมือ",
    orderNote:
      "เรียงตามตัวอักษร A–Z ของชื่อโบรกเกอร์เท่านั้น ไม่ใช่การจัดอันดับ ไม่ได้เรียงตามคะแนน ความนิยม หรือค่าตอบแทน และไม่มีโบรกเกอร์รายใดจ่ายเงินให้ Nobodi เพื่อเปลี่ยนตำแหน่งหรือเนื้อหาในหน้านี้",
    flags: {
      commission: "ยังไม่ยืนยันอัตรานี้",
      fractionalUnit: "หน่วยของเศษหุ้นไม่ระบุในตาราง",
      otherFees: "ค่าธรรมเนียมบางรายการยังไม่ครบ",
      taxServiceFees: "ยังไม่ยืนยันค่าบริการภาษีสหรัฐ",
      vat: "ไม่ระบุเรื่อง VAT",
      sourceUrl: "ลิงก์ต้นทางเป็นหน้าแรก ควรเช็กตารางค่าธรรมเนียมในเว็บ",
      dataAsOf: "วันที่ของข้อมูลควรยืนยัน",
    } as Record<string, string>,
  },
  en: {
    title: "Thai brokers for US stocks",
    sub: "Minimum investment and fees side by side, taken from each broker's own documents and pages.",
    checked: "Last checked",
    note:
      "Only brokers confirmed from official documents or pages to offer US stocks. Fees mostly exclude 7% VAT (some brokers don't state it). Rates change, so check the source link before deciding. This is not investment advice.",
    search: "Search brokers",
    count: (n: number) => `${n} ${n === 1 ? "broker" : "brokers"}`,
    empty: "No brokers match your search",
    colBroker: "Broker",
    colMin: "Minimum investment",
    colComm: "Commission",
    colOther: "Other fees",
    site: "Broker site",
    feeSource: "Fee source",
    asOf: "Data as of",
    logoNote: "Logos and names are trademarks of their owners, shown only to identify each broker, not as an endorsement or partnership.",
    orderNote:
      "Brokers are listed alphabetically (A–Z) by name. The order is not a ranking and reflects no score, popularity or payment. No broker has paid Nobodi to change its position or content on this page.",
    flags: {
      commission: "This rate is not confirmed",
      fractionalUnit: "Fractional-share unit not shown in the table",
      otherFees: "Some fees are missing",
      taxServiceFees: "US tax service fees not confirmed",
      vat: "VAT not stated",
      sourceUrl: "Source link is the home page; check the fee table on the site",
      dataAsOf: "Data date needs confirming",
    } as Record<string, string>,
  },
} satisfies Record<Lang, unknown>

const COMM_FLAGS = ["commission", "fractionalUnit"]
const OTHER_FLAGS = ["otherFees", "taxServiceFees", "vat"]
const NAME_FLAGS = ["sourceUrl", "dataAsOf"]

function fmtDate(iso: string, lang: Lang): string {
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(lang === "th" ? "th-TH" : "en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

// ในข้อมูล ตัวเลือกหลายแบบของโบรกเกอร์เดียวกันคั่นด้วย " | " แยกเป็นบรรทัดให้อ่านง่าย
function Lines({ text, className }: { text: string; className: string }) {
  return (
    <div className="space-y-1.5">
      {text.split(" | ").map((line, i) => (
        <p key={i} className={className}>
          {line}
        </p>
      ))}
    </div>
  )
}

function Flags({ keys, labels }: { keys: string[]; labels: string[] }) {
  if (keys.length === 0) return null
  return (
    <ul className="mt-2 space-y-1">
      {keys.map((k, i) => (
        <li key={k} className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400">
          <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          <span>{labels[i]}</span>
        </li>
      ))}
    </ul>
  )
}

function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium text-muted-foreground md:hidden">{label}</div>
      {children}
    </div>
  )
}

const COLS = "md:grid-cols-[12rem_minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1.3fr)]"

export default function BrokerComparePage() {
  const { lang } = useLanguage()
  const l: Lang = lang === "en" ? "en" : "th"
  const s = STR[l]
  const [q, setQ] = useState("")

  const rows = useMemo(() => {
    const sorted = [...data.brokers].sort((a, b) => a.name.localeCompare(b.name, "en"))
    const needle = q.trim().toLowerCase()
    if (!needle) return sorted
    return sorted.filter((b) => `${b.name} ${b.entity ?? ""}`.toLowerCase().includes(needle))
  }, [q])

  const flagsOf = (b: Broker, group: string[]) => {
    const keys = (b.needsConfirm ?? []).filter((k) => group.includes(k) && s.flags[k])
    return { keys, labels: keys.map((k) => s.flags[k]) }
  }

  return (
    <section className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight">{s.title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{s.sub}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {s.checked} {fmtDate(data.checkedAt, l)}
          </p>
        </div>

        <label className="relative block w-full sm:w-64">
          <span className="sr-only">{s.search}</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={s.search}
            className="h-10 w-full rounded-lg border bg-card pl-9 pr-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-emerald-500"
          />
        </label>
      </div>

      <p className="mt-6 rounded-lg border bg-muted/40 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
        {s.note}
      </p>

      <div className="mt-6 flex items-center justify-between text-xs text-muted-foreground">
        <span aria-live="polite">{s.count(rows.length)}</span>
      </div>

      <div className="mt-2 rounded-xl border bg-card">
        <div
          className={`hidden gap-x-6 border-b px-5 py-3 text-xs font-medium text-muted-foreground md:grid ${COLS}`}
        >
          <div>{s.colBroker}</div>
          <div>{s.colMin}</div>
          <div>{s.colComm}</div>
          <div>{s.colOther}</div>
        </div>

        {rows.length === 0 && <p className="px-5 py-10 text-center text-sm text-muted-foreground">{s.empty}</p>}

        {rows.map((b) => {
          const nameFlags = flagsOf(b, NAME_FLAGS)
          const commFlags = flagsOf(b, COMM_FLAGS)
          const otherFlags = flagsOf(b, OTHER_FLAGS)
          return (
            <article
              key={b.id}
              className={`grid gap-x-6 gap-y-4 border-b px-5 py-5 last:border-b-0 ${COLS}`}
            >
              <div>
                <div className="mb-3">
                  <BrokerLogo name={b.name} src={b.logo} bg={b.logoBg} />
                </div>
                <h2 className="text-base font-semibold">{b.name}</h2>
                {b.entity && <p className="mt-0.5 text-xs text-muted-foreground">{b.entity}</p>}
                {b.dataAsOf && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {s.asOf} {fmtDate(b.dataAsOf, l)}
                  </p>
                )}
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
                  <a
                    href={b.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-emerald-600 hover:underline dark:text-emerald-400"
                  >
                    {s.site}
                    <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </a>
                  {b.sourceUrl !== b.url && (
                    <a
                      href={b.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground hover:underline"
                    >
                      {s.feeSource}
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </a>
                  )}
                </div>
                <Flags {...nameFlags} />
              </div>

              <Cell label={s.colMin}>
                <Lines text={b.minInvest[l]} className="text-sm leading-relaxed" />
              </Cell>

              <Cell label={s.colComm}>
                <Lines text={b.commission[l]} className="text-sm font-medium leading-relaxed" />
                <Flags {...commFlags} />
              </Cell>

              <Cell label={s.colOther}>
                <Lines text={b.otherFees[l]} className="text-sm leading-relaxed text-muted-foreground" />
                {b.extras[l] && (
                  <p className="mt-3 border-t pt-3 text-xs leading-relaxed text-muted-foreground">{b.extras[l]}</p>
                )}
                <Flags {...otherFlags} />
              </Cell>
            </article>
          )
        })}
      </div>
    <p className="mt-3 text-xs text-muted-foreground">{s.logoNote}</p>
    </section>
  )
}
