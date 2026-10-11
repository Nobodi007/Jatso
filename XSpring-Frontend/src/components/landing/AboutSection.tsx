import type { ReactNode } from "react"
import { ArrowLeft } from "lucide-react"

// ใส่ "/founder.jpg" เมื่อวางรูปไว้ที่ public/founder.jpg (ปล่อยว่าง = ใช้ตัวอักษร N แทน)
const FOUNDER_PHOTO = ""

const BODY = "mt-5 text-base leading-8 text-foreground/90"

const LOOP = ["ทำผิดก็แก้", "ไม่เข้าใจก็ลองใหม่", "ทำไม่ได้ก็หาวิธีใหม่"]

const CHAIN = [
  "เมื่อมีไอเดีย ก็อยากลองทำ",
  "เมื่อทำสำเร็จ ก็อยากลองต่อ",
  "และเมื่อเห็นว่าสิ่งหนึ่งสามารถพัฒนาได้ ก็เริ่มอยากรู้ว่ามันจะไปได้ไกลกว่านั้นอีกแค่ไหน",
]

function PullQuote({ children }: { children: ReactNode }) {
  return (
    <blockquote className="my-8 rounded-r-xl border-l-4 border-emerald-500 bg-emerald-500/5 py-4 pl-5 pr-4 text-lg font-semibold leading-8">
      {children}
    </blockquote>
  )
}

export default function AboutSection({
  onBack,
  onRegister,
}: {
  onBack: () => void
  onRegister: () => void
}) {
  return (
    <main className="mx-auto max-w-3xl px-4 py-10 sm:py-14">
      <button
        type="button"
        onClick={onBack}
        className="mb-8 flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        กลับ
      </button>

      {/* HERO */}
      <p className="text-sm font-semibold text-emerald-500">ประวัติความเป็นมา</p>
      <h1 className="mt-2 text-4xl font-extrabold tracking-tight sm:text-5xl">จุดเริ่มต้นของ Nobodi</h1>
      <p className={BODY}>
        <b>Nobodi</b> เริ่มต้นจากคนเพียงคนเดียว กับคำถามง่าย ๆ ว่า
      </p>
      <PullQuote>“ถ้าภาพในอุดมคติที่อยู่ในหัว สามารถสร้างขึ้นมาเป็นความจริงได้ มันจะไปได้ไกลแค่ไหน?”</PullQuote>

      {/* FOUNDER */}
      <div className="flex items-center gap-4 rounded-2xl border bg-muted/20 p-5">
        {FOUNDER_PHOTO ? (
          <img
            src={FOUNDER_PHOTO}
            alt="ธีรภัทร นิยม"
            className="h-20 w-20 shrink-0 rounded-2xl object-cover"
          />
        ) : (
          <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-emerald-500 text-3xl font-extrabold text-black">
            N
          </div>
        )}
        <div className="min-w-0">
          <p className="text-lg font-bold">ธีรภัทร นิยม</p>
          <p className="text-sm text-muted-foreground">ผู้ก่อตั้ง Nobodi · อายุ 22 ปี</p>
          <p className="mt-1 text-xs text-muted-foreground">
            บริหารธุรกิจ สาขาการเงินและการลงทุน มหาวิทยาลัยหอการค้าไทย
          </p>
        </div>
      </div>

      {/* STORY */}
      <p className={BODY}>
        ผมชื่อ <b>ธีรภัทร นิยม</b> อายุ 22 ปี เป็นเด็กจบใหม่จากคณะบริหารธุรกิจ สาขาการเงินและการลงทุน
        มหาวิทยาลัยหอการค้าไทย
      </p>
      <p className={BODY}>
        ช่วงเวลาที่เรียนมหาวิทยาลัย ผมใช้เวลาส่วนใหญ่ไปกับการเรียนรู้เรื่องการลงทุน
        และหลังจากเรียนเสร็จหรือในวันที่ไม่มีเรียน ผมมักจะเข้าไปนั่งอยู่ในห้องคอมพิวเตอร์
        หรือห้องที่ใช้สำหรับเทรดหุ้น
      </p>
      <p className="mt-5 text-lg font-semibold">ส่วนใหญ่ผมจะนั่งอยู่คนเดียว</p>
      <p className={BODY}>
        รวมถึงช่วงการแข่งขันเทรดหุ้น ตั้งแต่ปี 1 จนถึงปี 3 ผมก็ยังคงไปนั่งเทรดคนเดียว
        และจนถึงทุกวันนี้ ผมก็ยังใช้ชีวิตและทำหลายสิ่งหลายอย่างด้วยตัวเองเป็นส่วนใหญ่
      </p>

      <div className="my-8 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-5">
        <p className="text-xs font-semibold text-emerald-500">ที่มาของชื่อ</p>
        <p className="mt-2 text-base leading-8">
          สิ่งเหล่านี้จึงกลายเป็นส่วนหนึ่งของตัวตน และเป็นที่มาของชื่อ <b>Nobodi</b> ซึ่งมาจากคำว่า{" "}
          <b>Nobody</b> ที่แปลว่า “ไม่มีใคร”
        </p>
      </div>

      <p className={BODY}>แต่ Nobodi ไม่ได้เริ่มต้นจากการวางแผนสร้างเว็บไซต์หรือระบบขนาดใหญ่</p>
      <p className={BODY}>มันเริ่มต้นจากความสงสัยเล็ก ๆ ในวันหนึ่ง</p>
      <p className={BODY}>
        วันหนึ่งผมกำลังเลื่อน TikTok และบังเอิญไปเจอคลิปที่อธิบายเกี่ยวกับ <b>Monte Carlo Simulation</b>
      </p>
      <p className={BODY}>ด้วยความสงสัย ผมจึงลองตั้งคำถามกับตัวเองว่า</p>
      <PullQuote>“ถ้าใช้ AI เราจะสามารถสร้างมันขึ้นมาได้ไหม?”</PullQuote>

      <p className={BODY}>
        ตอนนั้นผมไม่ได้มีพื้นฐานด้านการเขียนโปรแกรม และยังไม่สามารถรันโค้ดด้วยตัวเองได้ด้วยซ้ำ
      </p>
      <p className={BODY}>
        ผมจึงเริ่มต้นจากการลองให้ AI ช่วยสร้างสิ่งที่ผมคิดออกมา และเรียนรู้จากการลองผิดลองถูกไปเรื่อย ๆ
      </p>

      <div className="my-8 grid gap-3 sm:grid-cols-3">
        {LOOP.map((t, i) => (
          <div key={t} className="rounded-xl border bg-muted/20 p-4 text-center">
            <p className="text-xs font-bold text-emerald-500">0{i + 1}</p>
            <p className="mt-1 text-sm font-semibold">{t}</p>
          </div>
        ))}
      </div>

      <p className={BODY}>จนในที่สุด ผลลัพธ์ที่ออกมาก็เริ่มกลายเป็นสิ่งที่ผมต้องการ</p>
      <p className={BODY}>และนั่นทำให้ผมเริ่มรู้สึกสนุกกับการสร้าง</p>
      <p className={BODY}>
        จากการทดลองเพียงครั้งเดียว จึงกลายเป็นการทดลองครั้งต่อไป และค่อย ๆ ต่อยอดออกไปเรื่อย ๆ
      </p>
      <p className={BODY}>
        ต่อมา ผมมีโอกาสสัมภาษณ์เกี่ยวกับบริษัทที่ทำธุรกิจเกี่ยวกับคริปโต
        จึงนำสิ่งที่กำลังทดลองสร้างอยู่มาพัฒนาเป็นเว็บไซต์เพื่อนำไปใช้ในการนำเสนอ
      </p>
      <p className={BODY}>
        เมื่อได้รับผลตอบรับที่ดี สิ่งที่เดิมทีเป็นเพียงการทดลองก็เริ่มกลายเป็นโปรเจกต์ที่ผมอยากพัฒนาต่อ
      </p>
      <p className={BODY}>ผมเริ่มอยากรู้ว่า</p>
      <PullQuote>
        “ภาพในอุดมคติที่อยู่ในหัวของเรา ถ้าเราพยายามสร้างมันขึ้นมาจริง ๆ จะสามารถไปได้ไกลแค่ไหน?”
      </PullQuote>

      <div className="my-8 flex items-center gap-4 rounded-2xl border bg-muted/20 p-5">
        <div className="shrink-0 rounded-xl bg-emerald-500 px-4 py-2 text-center text-black">
          <p className="text-2xl font-extrabold leading-none">18</p>
          <p className="mt-1 text-xs font-bold">กันยายน</p>
        </div>
        <p className="text-base font-semibold">วันที่ผมเริ่มโปรเจกต์นี้</p>
      </div>

      <p className={BODY}>จุดเริ่มต้นไม่ได้ยิ่งใหญ่หรือสวยหรูอะไร</p>
      <p className={BODY}>
        ตอนแรกผมเพียงต้องการทดลองทำสิ่งที่เกี่ยวข้องกับงานที่กำลังจะไปสัมภาษณ์
        เพื่อทำความเข้าใจก่อนว่า กระบวนการทำงานเบื้องหลังของระบบลักษณะนี้เป็นอย่างไร
      </p>
      <p className={BODY}>มันเป็นเพียงงานเตรียมตัว</p>
      <p className={BODY}>แต่เมื่อเริ่มทำ ผมก็เริ่มมีไอเดียใหม่ ๆ เพิ่มขึ้นเรื่อย ๆ</p>

      <ul className="my-6 space-y-2 border-l-2 border-emerald-500/40 pl-5 text-base leading-8">
        {CHAIN.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>

      <p className={BODY}>
        จากโปรเจกต์เล็ก ๆ ที่เริ่มต้นเพียงเพื่อเรียนรู้ จึงค่อย ๆ เติบโตขึ้นจากการลองผิดลองถูก ความอยากรู้
        และความสนุกในการสร้าง จนกลายมาเป็น <b>Nobodi ในวันนี้</b>
      </p>

      {/* VISION + MISSION */}
      <div className="mt-14 grid gap-4 sm:grid-cols-2">
        <section className="rounded-2xl border bg-muted/20 p-6">
          <p className="text-xs font-bold tracking-wide text-emerald-500">VISION</p>
          <h2 className="mt-2 text-xl font-bold leading-snug">
            ทำให้ภาพในอุดมคติ กับความเป็นจริงมาบรรจบกัน
          </h2>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">
            ทุกสิ่งที่เกิดขึ้นบน Nobodi เริ่มต้นจากภาพบางอย่างที่อยู่ในหัว
          </p>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">
            Nobodi จึงเกิดขึ้นจากความต้องการที่จะนำสิ่งเหล่านั้นออกจากความคิด
            และค่อย ๆ เปลี่ยนให้กลายเป็นสิ่งที่สามารถสร้าง ทดลอง และเกิดขึ้นจริงได้
          </p>
        </section>

        <section className="rounded-2xl border bg-muted/20 p-6">
          <p className="text-xs font-bold tracking-wide text-emerald-500">MISSION</p>
          <h2 className="mt-2 text-xl font-bold leading-snug">
            “ถ้าคนเพียงคนเดียวไม่หยุดเรียนรู้และไม่หยุดสร้าง จะสามารถพาสิ่งที่อยู่ในหัวไปได้ไกลแค่ไหน”
          </h2>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">
            นี่คือคำถามที่อยู่เบื้องหลังการพัฒนา Nobodi
          </p>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">
            Nobodi เริ่มต้นจากคนเพียงคนเดียว เรียนรู้จากข้อผิดพลาด ลงมือทำ และพัฒนาต่อไปทีละขั้น
          </p>
          <p className="mt-3 text-sm leading-7 text-muted-foreground">
            ไม่ใช่เพื่อพิสูจน์ว่าคนเพียงคนเดียวสามารถสร้างได้มากแค่ไหน แต่เพื่อค้นหาว่า{" "}
            <b className="text-foreground">
              ขีดจำกัดของสิ่งที่คนหนึ่งคนสามารถเรียนรู้และสร้างขึ้นมาได้ อยู่ไกลแค่ไหน
            </b>
          </p>
        </section>
      </div>

      {/* CTA */}
      <div className="mt-12 flex flex-wrap items-center justify-between gap-4 rounded-2xl border p-6">
        <div>
          <p className="text-lg font-bold">อยากลองใช้ Nobodi?</p>
          <p className="mt-1 text-sm text-muted-foreground">
            สมัครฟรีด้วยบัญชี Google แล้วลองในบัญชีจำลอง
          </p>
        </div>
        <button
          type="button"
          onClick={onRegister}
          className="rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
        >
          สมัครตอนนี้
        </button>
      </div>
    </main>
  )
}
