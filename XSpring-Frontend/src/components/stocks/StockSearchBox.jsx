import { useEffect, useId, useRef, useState } from "react";

/**
 * กล่องค้นหาหุ้น (ใช้แทนช่องค้นหา + รายการผลลัพธ์เดิมในหน้า Stocks)
 *
 * แก้จากของเดิม:
 *  - ผลของคำค้นเก่าที่ตอบช้า ไม่ทับผลของคำค้นใหม่ (นับลำดับคำขอ)
 *  - เลือกด้วยลูกศรขึ้น/ลง + Enter ได้ Escape ปิด คลิกข้างนอกปิด
 *  - Enter ตอนไม่มีผล แต่พิมพ์เป็น ticker (เช่น BRK.B) เปิดตัวนั้นตรง ๆ
 *  - มีสถานะกำลังค้นหา / ไม่พบ / ค้นหาไม่ได้ และไฮไลต์ตัวที่พิมพ์
 *  - จำผลของคำค้นที่เคยค้นแล้วในหน้านี้ ไม่ยิงซ้ำ
 *
 * props
 *   api      ฟังก์ชันเดิมของหน้า (api("/search?q=...") คืน array)
 *   onPick   (symbol) => void  เรียกเมื่อเลือกหุ้น
 *   placeholder, className   (className ใช้กับช่อง input)
 */

const DEBOUNCE_MS = 250;
const TICKER_RE = /^[A-Za-z][A-Za-z.\-]{0,9}$/;

const typeBadge = (t) => {
  const s = String(t || "").toLowerCase();
  if (s.includes("etp") || s.includes("etf")) return "ETF";
  if (s.includes("adr")) return "ADR";
  if (s.includes("reit")) return "REIT";
  return "";
};

function Highlight({ text, q }) {
  const s = String(text || "");
  const needle = String(q || "").trim();
  if (!needle) return s;
  const i = s.toLowerCase().indexOf(needle.toLowerCase());
  if (i < 0) return s;
  return (
    <>
      {s.slice(0, i)}
      <mark className="rounded-sm bg-emerald-500/25 text-inherit">{s.slice(i, i + needle.length)}</mark>
      {s.slice(i + needle.length)}
    </>
  );
}

export default function StockSearchBox({
  api,
  onPick,
  placeholder = "ค้นหาหุ้น เช่น Apple, TSLA, แอปเปิล",
  className = "w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-emerald-500",
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [forKey, setForKey] = useState(""); // คำค้นที่ผล results เป็นของ (กันเลือกผลค้างของคำค้นเก่า)
  const pendingEnter = useRef(false); // กด Enter ตอนผลยังโหลดไม่เสร็จ ให้รอแล้วเลือกให้
  const reqId = useRef(0);
  const cache = useRef(new Map());
  const root = useRef(null);
  const uid = useId();

  // ค้นหาแบบหน่วงเวลา และทิ้งผลที่ไม่ใช่คำขอล่าสุด
  useEffect(() => {
    const term = q.trim();
    const id = ++reqId.current;
    if (!term) {
      setResults([]);
      setForKey("");
      setStatus("idle");
      return;
    }
    const key = term.toLowerCase();
    if (cache.current.has(key)) {
      setResults(cache.current.get(key));
      setForKey(key);
      setStatus("done");
      setActive(0);
      return;
    }
    setStatus("loading");
    const timer = setTimeout(() => {
      Promise.resolve()
        .then(() => api(`/search?q=${encodeURIComponent(term)}`))
        .then((d) => {
          if (id !== reqId.current) return; // มีคำค้นใหม่กว่าแล้ว
          const list = Array.isArray(d) ? d : [];
          cache.current.set(key, list);
          setResults(list);
          setForKey(key);
          setStatus("done");
          setActive(0);
          if (pendingEnter.current) {
            pendingEnter.current = false;
            if (list[0]) pick(list[0].symbol);
            else if (TICKER_RE.test(term)) pick(term.toUpperCase());
          }
        })
        .catch(() => {
          if (id !== reqId.current) return;
          setResults([]);
          setStatus("error");
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [q, api]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (root.current && !root.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const pick = (symbol) => {
    pendingEnter.current = false;
    setOpen(false);
    setQ("");
    setResults([]);
    setStatus("idle");
    reqId.current++; // ทิ้งคำขอที่ยังค้างอยู่
    onPick(symbol);
  };

  const onKeyDown = (e) => {
    if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      const term = q.trim();
      if (!term) return;
      e.preventDefault();
      if (forKey !== term.toLowerCase()) {
        pendingEnter.current = true; // ผลยังเป็นของคำค้นเก่า รอผลใหม่แล้วเลือกตัวแรกให้
      } else if (results[active]) {
        pick(results[active].symbol);
      } else if (TICKER_RE.test(term)) {
        pick(term.toUpperCase());
      }
    }
  };

  const term = q.trim();
  const showPanel = open && term !== "";
  const listId = `${uid}-list`;

  return (
    <div ref={root} className="relative w-full">
      <input
        role="combobox"
        aria-expanded={showPanel}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showPanel && results[active] ? `${uid}-opt-${active}` : undefined}
        aria-label="ค้นหาหุ้น"
        autoComplete="off"
        spellCheck={false}
        className={className}
        placeholder={placeholder}
        value={q}
        onChange={(e) => {
          pendingEnter.current = false;
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />

      {showPanel && (
        <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-border bg-card shadow-xl">
          {results.length > 0 ? (
            <ul id={listId} role="listbox" aria-label="ผลการค้นหาหุ้น" className="max-h-80 overflow-auto py-1">
              {results.map((x, i) => {
                const badge = typeBadge(x.type);
                return (
                  <li
                    key={x.symbol}
                    id={`${uid}-opt-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseMove={() => i !== active && setActive(i)}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => pick(x.symbol)}
                    className={`flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm ${i === active ? "bg-accent" : ""}`}
                  >
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="font-semibold text-foreground">
                        <Highlight text={x.symbol} q={x.match === "symbol" ? term : ""} />
                      </span>
                      {badge && <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{badge}</span>}
                    </span>
                    <span className="truncate text-muted-foreground">
                      <Highlight text={x.name} q={x.match === "name" ? term : ""} />
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p id={listId} role="status" className="px-3 py-3 text-sm text-muted-foreground">
              {status === "loading" && "กำลังค้นหา…"}
              {status === "error" && "ค้นหาไม่ได้ในตอนนี้ ลองใหม่อีกครั้ง"}
              {status === "done" && (
                <>
                  ไม่พบหุ้นที่ตรงกับ “{term}”
                  {TICKER_RE.test(term) && <> · กด Enter เพื่อเปิด {term.toUpperCase()} ตรง ๆ</>}
                </>
              )}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
