import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { translations } from "./translations";
import type { Lang } from "./translations";

type Vars = Record<string, string | number>;

type LanguageContextValue = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string, vars?: Vars) => string;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

function getInitialLang(): Lang {
  const saved = localStorage.getItem("lang");
  return saved === "en" || saved === "th" ? saved : "th";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(getInitialLang);

  useEffect(() => {
    localStorage.setItem("lang", lang);
    document.documentElement.lang = lang;
  }, [lang]);

  const t = (key: string, vars: Vars = {}): string => {
    const value = key
      .split(".")
      .reduce<unknown>(
        (obj, k) => (obj as Record<string, unknown> | undefined)?.[k],
        translations[lang],
      );
    const str = typeof value === "string" ? value : key;
    return str.replace(/\{(\w+)\}/g, (_, v: string) => String(vars[v] ?? `{${v}}`));
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used inside <LanguageProvider>");
  return ctx;
}
