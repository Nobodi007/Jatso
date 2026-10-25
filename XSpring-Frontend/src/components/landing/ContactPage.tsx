import { useState } from "react"
import { ArrowUpRight, Check, Copy, Mail, MapPin, Navigation, Phone } from "lucide-react"
import { useLanguage } from "../../i18n/LanguageContext"

const CONTACT = {
  // ใช้ที่อยู่ภาษาไทยเป็น query ของแผนที่เสมอ เพราะ Google Maps หาเจอแม่นกว่า
  mapQuery: "205/3 ประชาสงเคราะห์ 27 ดินแดง กรุงเทพมหานคร",
  phone: "0901556855",
  email: "teerapat30204@gmail.com",
  linkedin: "https://www.linkedin.com/in/thiraphat-niyom-11044727b/",
}

function LinkedinIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.125 2.062 2.062 0 0 1 0 4.125zM7.119 20.452H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  )
}

function CopyButton({ value, label, doneLabel }: { value: string; label: string; doneLabel: string }) {
  const [done, setDone] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setDone(true)
      window.setTimeout(() => setDone(false), 1800)
    } catch {
      // คัดลอกไม่ได้ก็ไม่ต้องทำอะไร
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={done ? doneLabel : label}
      title={done ? doneLabel : label}
      className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
    >
      {done ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
    </button>
  )
}

type RowProps = {
  icon: React.ReactNode
  label: string
  value: string
  href: string
  external?: boolean
  action?: React.ReactNode
}

function ContactRow({ icon, label, value, href, external, action }: RowProps) {
  return (
    <div className="flex items-center gap-2 py-4">
      <a
        href={href}
        {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        className="group flex min-w-0 flex-1 items-center gap-4 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
      >
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          {icon}
        </span>
        <span className="min-w-0">
          <span className="block text-xs text-muted-foreground">{label}</span>
          <span className="block break-all text-base font-medium group-hover:underline group-hover:decoration-emerald-500 group-hover:underline-offset-4">
            {value}
          </span>
        </span>
      </a>
      {action}
    </div>
  )
}

export default function ContactPage() {
  const { t } = useLanguage()
  const mapQuery = encodeURIComponent(CONTACT.mapQuery)

  return (
    <main className="min-h-[calc(100vh-4rem)] bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-5 py-12 md:py-16">
        {/* หัวเรื่อง */}
        <header className="max-w-2xl">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t("contact.title")}</h1>
          <p className="mt-3 text-base leading-7 text-muted-foreground">{t("contact.subtitle")}</p>
        </header>

        <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] lg:gap-14">
          {/* ช่องทางติดต่อ */}
          <section aria-label={t("contact.channels")}>
            <div className="divide-y divide-border border-y">
              <ContactRow
                icon={<Phone className="h-5 w-5" />}
                label={t("contact.phone")}
                value={CONTACT.phone}
                href={`tel:${CONTACT.phone}`}
                action={
                  <CopyButton value={CONTACT.phone} label={t("contact.copy")} doneLabel={t("contact.copied")} />
                }
              />
              <ContactRow
                icon={<Mail className="h-5 w-5" />}
                label={t("contact.email")}
                value={CONTACT.email}
                href={`mailto:${CONTACT.email}`}
                action={
                  <CopyButton value={CONTACT.email} label={t("contact.copy")} doneLabel={t("contact.copied")} />
                }
              />
              <ContactRow
                icon={<LinkedinIcon className="h-5 w-5" />}
                label={t("contact.linkedin")}
                value={t("contact.linkedinDesc")}
                href={CONTACT.linkedin}
                external
                action={<ArrowUpRight className="mr-2 h-4 w-4 text-muted-foreground" aria-hidden="true" />}
              />
            </div>

            <div className="mt-8 flex gap-4">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <MapPin className="h-5 w-5" />
              </span>
              <div>
                <p className="text-xs text-muted-foreground">{t("contact.address")}</p>
                <p className="mt-0.5 text-base font-medium leading-7">{t("contact.addressFull")}</p>
              </div>
            </div>
          </section>

          {/* แผนที่ */}
          <section aria-label={t("contact.findUs")}>
            <div className="overflow-hidden rounded-2xl border bg-card">
              <iframe
                title={t("contact.mapTitle")}
                src={`https://www.google.com/maps?q=${mapQuery}&output=embed`}
                className="h-[320px] w-full sm:h-[420px] dark:[filter:invert(.92)_hue-rotate(180deg)_saturate(.8)]"
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <a
                href={`https://www.google.com/maps/search/?api=1&query=${mapQuery}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-black transition-colors hover:bg-emerald-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                <Navigation className="h-4 w-4" />
                {t("contact.directions")}
              </a>
              <a
                href={`https://www.google.com/maps/search/?api=1&query=${mapQuery}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              >
                {t("contact.openMaps")}
                <ArrowUpRight className="h-4 w-4" />
              </a>
            </div>
          </section>
        </div>

        <p className="mt-14 border-t pt-6 text-xs text-muted-foreground">
          © {new Date().getFullYear()} Nobodi. {t("contact.rights")}
        </p>
      </div>
    </main>
  )
}
