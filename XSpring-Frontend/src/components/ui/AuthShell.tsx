import type { ReactNode } from "react"
import { ArrowLeft, Check } from "lucide-react"

const AUTH_POINTS = [
  "ดูราคาตลาดแบบสด",
  "ฝึกซื้อขายในบัญชีจำลอง ไม่ใช้เงินจริง",
  "ทดสอบกลยุทธ์ย้อนหลังก่อนตัดสินใจ",
]

function AuthShell({
  title = "XSpring Dealer Suite",
  subtitle = "เข้าสู่ระบบด้วยบัญชี Google",
  onBack,
  children,
}: {
  title?: string
  subtitle?: string
  onBack?: () => void
  children: ReactNode
}) {
  return (
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-background px-4 py-10 text-foreground">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-1/3 h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-500/15 blur-3xl"
      />

      <div className="relative w-full max-w-sm rounded-3xl border bg-card/80 p-8 shadow-2xl backdrop-blur">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="absolute left-4 top-4 flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            กลับหน้าแรก
          </button>
        )}

        <div className="flex flex-col items-center pt-6 text-center">
          <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500 text-2xl font-extrabold text-black shadow-lg shadow-emerald-500/30">
            X
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
        </div>

        {/* ปุ่ม Google เดิมวางตรงนี้ (children) */}
        <div className="mt-8 flex min-h-[44px] w-full items-center justify-center">{children}</div>

        <div className="my-6 flex items-center gap-3">
          <div className="h-px flex-1 border-t border-dashed" />
          <span className="text-xs text-muted-foreground">สิ่งที่คุณจะได้</span>
          <div className="h-px flex-1 border-t border-dashed" />
        </div>

        <ul className="space-y-2.5">
          {AUTH_POINTS.map((p) => (
            <li key={p} className="flex items-start gap-2.5 text-sm text-muted-foreground">
              <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500">
                <Check className="h-3 w-3" />
              </span>
              {p}
            </li>
          ))}
        </ul>

        <p className="mt-6 text-center text-[11px] leading-5 text-muted-foreground">
          เข้าสู่ระบบผ่าน Google เท่านั้น ระบบไม่เก็บรหัสผ่านของคุณ
        </p>
      </div>
    </div>
  )
}

export default AuthShell
