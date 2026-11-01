import { useEffect, useId, useMemo, useRef, useState } from "react";
import { BROKERS, findBroker, type Broker } from "./brokerFees";

/** ชื่อที่บันทึกเมื่อผู้ใช้เลือกโบรกที่ไม่อยู่ในรายการ (ไม่คำนวณค่าธรรมเนียมให้) */
export const OTHER_BROKER = "อื่น ๆ";

const LOGO_BASE = "/brokers/"; // ไฟล์อยู่ที่ public/brokers

export function BrokerLogo({ broker, className = "" }: { broker?: Broker; className?: string }) {
  const [failed, setFailed] = useState(false);
  const tile = broker?.logoOnDark ? "bg-slate-800" : "bg-white";
  return (
    <span className={`flex h-9 w-24 shrink-0 items-center justify-center rounded-md px-2 ${broker ? tile : "bg-muted"} ${className}`}>
      {broker && !failed ? (
        <img
          src={`${LOGO_BASE}${broker.logo}`}
          alt=""
          loading="lazy"
          className="max-h-6 max-w-full object-contain"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="text-xs text-muted-foreground">{broker ? broker.name.slice(0, 3) : "?"}</span>
      )}
    </span>
  );
}

const hasRate = (b: Broker) => b.plans.some((p) => p.rule !== null);

type Props = {
  /** ชื่อโบรกที่บันทึกอยู่ (real_accounts.broker) */
  value: string;
  /** เลือกแล้ว ส่งชื่อที่ต้องบันทึก (<= 40 ตัวอักษร) */
  onSelect: (name: string) => void;
  disabled?: boolean;
};

export default function BrokerPicker({ value, onSelect, disabled }: Props) {
  const current = findBroker(value);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const uid = useId();

  const items = useMemo(() => [...BROKERS.map((b) => ({ key: b.id, broker: b as Broker | undefined, name: b.name })), { key: "other", broker: undefined, name: OTHER_BROKER }], []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const openList = () => {
    const i = items.findIndex((x) => x.name === (current?.name ?? value));
    setActive(i >= 0 ? i : 0);
    setOpen(true);
  };
  const choose = (i: number) => {
    setOpen(false);
    if (items[i].name !== (current?.name ?? value)) onSelect(items[i].name);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openList();
      }
      return;
    }
    if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(items.length - 1); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(active); }
    else if (e.key === "Tab") setOpen(false);
  };

  const label = current?.name ?? (value || "เลือกโบรกเกอร์");

  return (
    <div ref={root} className="relative inline-block w-full max-w-sm text-sm">
      <button
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${uid}-list`}
        aria-activedescendant={open ? `${uid}-opt-${active}` : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKey}
        className="flex w-full items-center gap-3 rounded-xl border border-border bg-background px-3 py-2 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-60"
      >
        <BrokerLogo broker={current} />
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <span aria-hidden className="text-muted-foreground">{open ? "▴" : "▾"}</span>
      </button>

      {open && (
        <ul
          ref={list}
          id={`${uid}-list`}
          role="listbox"
          aria-label="โบรกเกอร์"
          className="absolute z-30 mt-1 max-h-80 w-full overflow-auto rounded-xl border border-border bg-card p-1 shadow-lg"
        >
          {items.map((it, i) => (
            <li
              key={it.key}
              id={`${uid}-opt-${i}`}
              data-i={i}
              role="option"
              aria-selected={it.name === (current?.name ?? value)}
              onMouseMove={(e) => { if ((e.movementX || e.movementY) && active !== i) setActive(i); }}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(i)}
              className={`flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 ${i === active ? "bg-accent" : ""}`}
            >
              <BrokerLogo broker={it.broker} />
              <span className="min-w-0 flex-1">
                <span className="block truncate">{it.name}</span>
                {it.broker && !hasRate(it.broker) && <span className="block text-xs text-amber-500">ยังไม่มีอัตรา กรอกเอง</span>}
                {!it.broker && <span className="block text-xs text-muted-foreground">กรอกค่าธรรมเนียมเอง</span>}
              </span>
              {it.name === (current?.name ?? value) && <span aria-hidden className="text-emerald-500">✓</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
