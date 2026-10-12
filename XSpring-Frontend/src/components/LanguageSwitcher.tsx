import { useEffect, useRef, useState } from "react";
import { Globe } from "lucide-react";
import { useLanguage } from "../i18n/LanguageContext";
import type { Lang } from "../i18n/translations";

const options: { code: Lang; label: string }[] = [
  { code: "th", label: "ไทย" },
  { code: "en", label: "English" },
];

export default function LanguageSwitcher() {
  const { lang, setLang } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="ภาษา"
        className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Globe className="h-4 w-4" />
      </button>

      {open && (
        <ul className="absolute right-0 top-full z-50 mt-2 min-w-28 rounded-lg border border-border bg-popover p-1 shadow-lg">
          {options.map((o) => (
            <li key={o.code}>
              <button
                type="button"
                onClick={() => {
                  setLang(o.code);
                  setOpen(false);
                }}
                className={`w-full rounded-md px-3 py-2 text-left text-sm hover:bg-accent ${
                  lang === o.code ? "text-emerald-500" : "text-foreground"
                }`}
              >
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
