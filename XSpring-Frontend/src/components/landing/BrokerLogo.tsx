import { useState } from "react"

// โลโก้โบรกเกอร์: ถ้ามีไฟล์ใน public/brokers/ จะแสดงบนแผ่นสีขาว (โลโก้ตัวหนังสือสีเข้มจะยังอ่านออกในโหมดมืด)
// ถ้าไม่มีไฟล์หรือโหลดไม่ขึ้น จะกลับไปแสดงตัวย่อ (monogram) แทน ไม่ทำให้หน้าพัง
const initials = (name: string) => {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean)
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? "?").slice(0, 2)).toUpperCase()
}

export default function BrokerLogo({ name, src }: { name: string; src?: string | null }) {
  const [failed, setFailed] = useState(false)

  if (!src || failed) {
    return (
      <div
        className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-muted text-xs font-bold text-muted-foreground"
        aria-hidden="true"
      >
        {initials(name)}
      </div>
    )
  }

  return (
    <div className="inline-flex h-11 shrink-0 items-center rounded-lg bg-white px-2.5 ring-1 ring-border">
      <img
        src={src}
        alt={`${name} logo`}
        height={28}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className="h-7 w-auto max-w-[120px] object-contain"
      />
    </div>
  )
}
