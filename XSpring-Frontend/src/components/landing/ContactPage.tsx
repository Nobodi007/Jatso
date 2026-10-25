import { ArrowUpRight, Mail, MapPin, Phone, Linkedin } from "lucide-react"
import heroImage from "../../assets/hero.png"

const CONTACT = {
  address: "205/3 ประชาสงเคราะห์ 27 ดินแดง กรุงเทพมหานคร",
  phone: "0901556855",
  email: "teerapat30204@gmail.com",
  linkedin: "https://www.linkedin.com/in/thiraphat-niyom-11044727b/",
}

export default function ContactPage() {
  const mapQuery = encodeURIComponent(CONTACT.address)
  return (
    <main className="min-h-[calc(100vh-4rem)] bg-background text-foreground">
      <section className="relative isolate overflow-hidden bg-[#171936]">
        <div
          className="absolute inset-0 -z-10 bg-cover bg-center opacity-55"
          style={{ backgroundImage: `url(${heroImage})` }}
        />
        <div className="absolute inset-0 -z-10 bg-gradient-to-r from-[#171936] via-[#22244c]/90 to-[#171936]/35" />
        <div className="mx-auto flex min-h-48 max-w-6xl items-center px-5 py-12 sm:min-h-56">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.28em] text-emerald-300">NOBODI · CONTACT</p>
            <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">ติดต่อเรา <span className="font-medium text-white/75">/ Contact Us</span></h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-white/75 sm:text-base">
              มีคำถามหรือข้อเสนอแนะเกี่ยวกับ Nobodi? ติดต่อเราได้ผ่านช่องทางด้านล่าง
              <span className="mt-1 block">Questions or feedback? We’d be happy to hear from you.</span>
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-8 px-5 py-10 md:grid-cols-[1.15fr_.85fr] md:py-14">
        <div>
          <div className="mb-4 flex items-center gap-2">
            <MapPin className="h-5 w-5 text-emerald-500" />
            <h2 className="text-xl font-semibold">ค้นหาเรา <span className="text-base font-normal text-muted-foreground">/ Find us</span></h2>
          </div>
          <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
            <iframe
              title="แผนที่สำนักงาน Nobodi"
              src={`https://www.google.com/maps?q=${mapQuery}&output=embed`}
              className="h-[300px] w-full sm:h-[380px]"
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
            />
          </div>
          <a
            href={`https://www.google.com/maps/search/?api=1&query=${mapQuery}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-emerald-600 hover:text-emerald-500"
          >
            เปิดใน Google Maps <ArrowUpRight className="h-4 w-4" />
          </a>
        </div>

        <aside className="self-start overflow-hidden rounded-3xl bg-gradient-to-br from-[#202136] to-[#30304f] p-6 text-white shadow-xl sm:p-8">
          <div className="mb-7 text-center">
            <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-2xl border border-emerald-300/30 bg-emerald-400/10 text-lg font-black text-emerald-300">N</div>
            <p className="text-lg font-bold tracking-wide">NOBODI</p>
            <p className="mt-1 text-xs text-white/60">Trading · Research · Analytics</p>
          </div>

          <p className="text-sm font-semibold text-emerald-300">ที่อยู่ / Address</p>
          <p className="mt-2 flex gap-2 text-sm leading-6 text-white/90">
            <MapPin className="mt-1 h-4 w-4 shrink-0 text-emerald-300" />
            {CONTACT.address}
          </p>
          <p className="mt-1 pl-6 text-xs leading-5 text-white/60">Din Daeng, Bangkok, Thailand</p>

          <div className="my-6 h-px bg-white/10" />
          <div className="grid gap-5 sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2">
            <a href={`tel:${CONTACT.phone}`} className="group flex gap-3 rounded-xl p-2 transition hover:bg-white/5">
              <Phone className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" />
              <span className="min-w-0">
                <span className="block text-xs text-white/60">โทรศัพท์ / Phone</span>
                <span className="mt-1 block break-words text-sm font-semibold">{CONTACT.phone}</span>
              </span>
            </a>
            <a href={`mailto:${CONTACT.email}`} className="group flex gap-3 rounded-xl p-2 transition hover:bg-white/5">
              <Mail className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300" />
              <span className="min-w-0">
                <span className="block text-xs text-white/60">อีเมล / Email</span>
                <span className="mt-1 block break-all text-sm font-semibold">{CONTACT.email}</span>
              </span>
            </a>
          </div>

          <a
            href={CONTACT.linkedin}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.04] p-4 transition hover:border-emerald-300/40 hover:bg-white/[0.08]"
          >
            <span className="flex items-center gap-3">
              <Linkedin className="h-5 w-5 text-emerald-300" />
              <span>
                <span className="block text-sm font-semibold">LinkedIn</span>
                <span className="mt-1 block text-xs text-white/60">ติดตามและเชื่อมต่อกับเรา</span>
              </span>
            </span>
            <ArrowUpRight className="h-4 w-4 text-white/60" />
          </a>
          <p className="mt-6 text-center text-xs leading-5 text-white/45">
            © {new Date().getFullYear()} Nobodi. All rights reserved.
          </p>
        </aside>
      </section>
    </main>
  )
}
