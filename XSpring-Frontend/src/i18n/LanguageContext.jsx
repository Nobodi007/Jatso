import { createContext, useContext, useEffect, useState } from "react";
import { translations } from "./translations";

const LanguageContext = createContext();

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState("th");

  // โหลดภาษาที่เคยเลือกไว้
  useEffect(() => {
    const saved = localStorage.getItem("lang");
    if (saved === "th" || saved === "en") setLang(saved);
  }, []);

  // บันทึก + ตั้งค่า <html lang>
  useEffect(() => {
    localStorage.setItem("lang", lang);
    document.documentElement.lang = lang;
  }, [lang]);

  // t("nav.market") -> คำแปลตามภาษาปัจจุบัน
  const t = (key) =>
    key.split(".").reduce((obj, k) => obj?.[k], translations[lang]) ?? key;

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export const useLanguage = () => useContext(LanguageContext);
