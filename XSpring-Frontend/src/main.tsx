import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { LanguageProvider } from "./i18n/LanguageContext";   // ← เพิ่ม

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LanguageProvider>      {/* ← เพิ่ม */}
      <App />
    </LanguageProvider>     {/* ← เพิ่ม */}
  </StrictMode>,
);
