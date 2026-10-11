"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { dp, splitSymbol } from "@/lib/market";

const TABS = ["ลิมิตออเดอร์", "มาร์เก็ตออเดอร์", "สต็อปลิมิตออเดอร์"];

export default function OrderForm({ symbol, last }: { symbol: string; last?: number }) {
  const { base, quote } = splitSymbol(symbol);
  const [tab, setTab] = useState(0);
  const [buyPrice, setBuyPrice] = useState("");
  const [sellPrice, setSellPrice] = useState("");

  useEffect(() => {
    if (last && !buyPrice) {
      setBuyPrice(last.toFixed(dp(last)));
      setSellPrice(last.toFixed(dp(last)));
    }
  }, [last]); // eslint-disable-line

  const Field = ({ label, unit, value, onChange, disabled }:
    { label: string; unit: string; value?: string; onChange?: (v: string) => void; disabled?: boolean }) => (
    <label className="flex items-center rounded-md bg-[#1a1a1a] px-3 py-2.5 text-sm">
      <span className="text-zinc-500">{label}</span>
      <input value={value ?? ""} disabled={disabled} onChange={(e) => onChange?.(e.target.value)}
        placeholder={disabled ? "ราคาตลาด" : ""}
        className="flex-1 bg-transparent text-right text-white outline-none placeholder:text-zinc-500" />
      <span className="ml-2 text-white">{unit}</span>
    </label>
  );

  const Side = ({ side }: { side: "buy" | "sell" }) => (
    <div className="flex flex-1 flex-col gap-3">
      <div className="flex justify-between text-xs text-zinc-500">
        <span>ยอดคงเหลือ</span><span>- {side === "buy" ? quote : base}</span>
      </div>
      {tab === 2 && <Field label="ราคาสต็อป" unit={quote} />}
      <Field label="ราคา" unit={quote} disabled={tab === 1}
        value={side === "buy" ? buyPrice : sellPrice}
        onChange={side === "buy" ? setBuyPrice : setSellPrice} />
      <Field label="จำนวน" unit={base} />
      <input type="range" defaultValue={0} className={side === "buy" ? "accent-[#13c38b]" : "accent-[#f6465d]"} />
      <div className="rounded-md bg-[#1f1f1f] py-3 text-center text-sm">
        <Link href="/login" className="text-[#13c38b]">เข้าสู่ระบบ</Link>
        <span className="text-zinc-300"> หรือ </span>
        <Link href="/register" className="text-[#13c38b]">สมัครตอนนี้</Link>
      </div>
    </div>
  );

  return (
    <div className="bg-[#0f0f0f]">
      <div className="border-b border-[#1c1c1c] px-4">
        <span className="inline-block border-b-2 border-[#13c38b] px-4 py-3 text-sm text-white">Spot</span>
      </div>
      <div className="p-4">
        <div className="mb-4 flex gap-4 text-sm">
          {TABS.map((t, i) => (
            <button key={t} onClick={() => setTab(i)} className={tab === i ? "text-[#13c38b]" : "text-zinc-400"}>{t}</button>
          ))}
        </div>
        <div className="flex gap-6"><Side side="buy" /><Side side="sell" /></div>
      </div>
    </div>
  );
}
