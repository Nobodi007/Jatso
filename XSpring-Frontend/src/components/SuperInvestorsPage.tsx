import { useEffect, useMemo, useState } from "react"

// หน้าพอร์ตนักลงทุนชื่อดัง (ข้อมูลจาก SEC 13F-HR) อ่านจาก /data/superinvestors.json
type Holding = {
  cusip: string; ticker: string; name: string; value: number; shares: number
  weight: number; change: "" | "new" | "added" | "reduced" | "same"; change_pct: number | null
}
type Sold = { cusip: string; ticker: string; name: string; value: number }
type Investor = {
  id: string; person: string; fund: string; period: string; filed: string
  total_value: number; holdings_count: number; holdings: Holding[]; sold: Sold[]
}
type Data = { generated_at: string; investors: Investor[] }

const card = "rounded-xl border bg-card p-5"
const usd = (v: number) =>
  v >= 1e9 ? `$${(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v).toLocaleString("en-US")}`
const badge: Record<string, { text: string; cls: string }> = {
  new: { text: "ซื้อใหม่", cls: "bg-emerald-500/15 text-emerald-500" },
  added: { text: "เพิ่ม", cls: "bg-sky-500/15 text-sky-400" },
  reduced: { text: "ลด", cls: "bg-amber-500/15 text-amber-500" },
}

export default function SuperInvestorsPage() {
  const [data, setData] = useState<Data | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sel, setSel] = useState<string>("")

  useEffect(() => {
    fetch("/data/superinvestors.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("ยังไม่มีไฟล์ข้อมูล"))))
      .then((d: Data) => { setData(d); setSel(d.investors[0]?.id ?? "") })
      .catch((e) => setErr(e instanceof Error ? e.message : "โหลดข้อมูลไม่ได้"))
  }, [])

  const inv = useMemo(() => data?.investors.find((i) => i.id === sel), [data, sel])

  if (err) return <div className={`${card} text-sm text-red-500`}>{err}</div>
  if (!data) return <div className="text-sm text-muted-foreground">กำลังโหลด…</div>

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold">พอร์ตนักลงทุนชื่อดัง</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          ข้อมูลจากฟอร์ม 13F ที่ยื่นต่อ SEC ทุกไตรมาส · แสดงเฉพาะหุ้นสหรัฐฝั่งซื้อ (ไม่รวม short เงินสด และหุ้นต่างประเทศ) ·
          ล่าช้าได้ถึง 45 วันหลังสิ้นไตรมาส · ไม่ใช่คำแนะนำลงทุน
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {data.investors.map((i) => (
          <button key={i.id} type="button" onClick={() => setSel(i.id)}
            className={`rounded-full border px-3 py-1.5 text-xs hover:bg-accent ${i.id === sel ? "border-primary bg-accent font-semibold" : ""}`}>
            {i.person}
          </button>
        ))}
      </div>

      {inv && (
        <div className={card}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-lg font-semibold">{inv.person} <span className="text-sm font-normal text-muted-foreground">· {inv.fund}</span></h3>
            <span className="text-xs text-muted-foreground">งวด {inv.period} · ยื่นเมื่อ {inv.filed} · มูลค่ารวม {usd(inv.total_value)} · {inv.holdings_count} ตัว</span>
          </div>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm tabular-nums">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1 font-normal">หุ้น</th>
                  <th className="font-normal">สัดส่วน</th>
                  <th className="text-right font-normal">มูลค่า</th>
                  <th className="text-right font-normal">เทียบไตรมาสก่อน</th>
                </tr>
              </thead>
              <tbody>
                {inv.holdings.slice(0, 25).map((h) => (
                  <tr key={h.cusip} className="border-t border-border">
                    <td className="py-1.5 pr-2">
                      <span className="font-semibold">{h.ticker || "—"}</span>
                      <span className="ml-2 text-xs text-muted-foreground">{h.name}</span>
                    </td>
                    <td className="pr-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-24 overflow-hidden rounded bg-muted"><div className="h-full bg-primary" style={{ width: `${Math.min(100, h.weight * 100 * 2)}%` }} /></div>
                        <span className="text-xs">{(h.weight * 100).toFixed(1)}%</span>
                      </div>
                    </td>
                    <td className="text-right">{usd(h.value)}</td>
                    <td className="text-right text-xs">
                      {badge[h.change] && <span className={`rounded px-1.5 py-0.5 ${badge[h.change].cls}`}>{badge[h.change].text}{h.change_pct != null ? ` ${(h.change_pct * 100).toFixed(0)}%` : ""}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {inv.sold.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              ขายออกหมดในไตรมาสนี้: {inv.sold.map((s) => s.ticker || s.name).join(", ")}
            </p>
          )}
        </div>
      )}
      <p className="text-xs text-muted-foreground">อัปเดตข้อมูลล่าสุด {data.generated_at.slice(0, 10)} · ที่มา SEC EDGAR</p>
    </div>
  )
}
