import { useState } from "react";
import { METRIC_HELP } from "./metricHelp";

/** ปุ่ม ⓘ เล็ก ๆ กดแล้วขยายคำอธิบายใต้ป้ายชื่อ (ใช้ได้บนมือถือและคีย์บอร์ด ไม่พึ่ง hover) */
export function InfoTip({ k }: { k: string }) {
  const [open, setOpen] = useState(false);
  const h = METRIC_HELP[k];
  if (!h) return null;
  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        aria-label={`อธิบาย ${h.title}`}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e: { key: string }) => {
          if (e.key === "Escape") setOpen(false);
        }}
        className="ml-1.5 inline-flex size-4 items-center justify-center rounded-full border border-border align-middle text-[10px] leading-none text-muted-foreground hover:bg-muted"
      >
        i
      </button>
      {open && (
        <span role="note" className="mt-2 block rounded-xl bg-muted p-3 text-left text-xs font-normal leading-relaxed text-muted-foreground">
          <span className="block font-medium text-foreground">{h.title}</span>
          <span className="mt-1 block">คืออะไร: {h.what}</span>
          <span className="mt-1 block">อ่านอย่างไร: {h.read}</span>
          {h.caution && <span className="mt-1 block">ข้อจำกัด: {h.caution}</span>}
        </span>
      )}
    </>
  );
}
