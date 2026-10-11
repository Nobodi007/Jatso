type FooterLink = { label: string; go?: string; asset?: string; page?: string; highlight?: boolean }

const ABOUT: FooterLink[] = [
  { label: "ประวัติความเป็นมา" },
  { label: "เกี่ยวกับระบบ", page: "about" },
  { label: "คู่มือการใช้งาน", page: "guide" },
  { label: "ความเป็นส่วนตัว" },
  { label: "เปิดเผยข้อมูล/แจ้งความเสี่ยง" },
  { label: "ข่าวสาร", go: "ข่าว" },
  { label: "ติดต่อ คุณNobodi สุดเท่", highlight: true },
]

const SERVICES: FooterLink[] = [
  { label: "ศูนย์ซื้อขาย", go: "การซื้อขาย" },
  { label: "ตลาด", go: "ตลาด" },
  { label: "ลองลงทุนย้อนหลัง", go: "ลองลงทุนย้อนหลัง" },
  { label: "ซื้อ Bitcoin", asset: "BTC" },
  { label: "ซื้อ ETH", asset: "ETH" },
  { label: "ซื้อ USDT", asset: "USDT" },
  { label: "ซื้อ DOGE", asset: "DOGE" },
]

type Props = {
  onGo: (label: string) => void
  onOpenCoin: (asset: string) => void
  onPage?: (page: string) => void
}

export default function Footer({ onGo, onOpenCoin, onPage }: Props) {
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
            <button
              type="button"
              onClick={() => click(l)}
              className={`text-left ${
                l.highlight ? "text-sky-500 hover:text-sky-400" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {l.label}
            </button>
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
          <p className="mt-2 text-xs leading-5 text-muted-foreground">แพลตฟอร์มฝึกลงทุนคริปโตด้วยบัญชีจำลอง</p>
        </div>
        <Column title="About Us" links={ABOUT} />
        <Column title="บริการ" links={SERVICES} />
        <div>
          <p className="font-semibold">ข้อควรรู้</p>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            การลงทุนในสินทรัพย์ดิจิทัลมีความเสี่ยงสูง ผลย้อนหลังไม่ได้รับประกันผลตอบแทนในอนาคต
            และบัญชีของเราเป็นบัญชีจำลองเพื่อการเรียนรู้เท่านั้น
          </p>
        </div>
      </div>
      <p className="border-t py-4 text-center text-xs text-muted-foreground">© Nobodi</p>
    </footer>
  )
}
