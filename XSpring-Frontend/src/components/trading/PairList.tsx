"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Ticker, dp, fetchTickers, fmt, splitSymbol } from "@/lib/market";

// ใส่คู่ที่เว็บมึงมี
const PAIRS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT"];

export default function PairList({ active }: { active: string }) {
  const [list, setList] = useState<Ticker[]>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    const load = () => fetchTickers(PAIRS).then(setList).catch(console.error);
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  const shown = list.filter((t) => t.symbol.includes(q.toUpperCase()));

  return (
    <div className="bg-[#0f0f0f] p-4">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ค้นหา"
        className="mb-3 w-full rounded-md bg-[#1a1a1a] px-3 py-2 text-sm outline-none placeholder:text-zinc-500" />
      <div className="grid grid-cols-3 pb-2 text-xs text-zinc-500">
        <span>คู่เทรด</span><span className="text-right">ราคา</span><span className="text-right">เปลี่ยน</span>
      </div>
      {shown.map((t) => {
        const { base, quote } = splitSymbol(t.symbol);
        return (
          <Link key={t.symbol} href={`/trade/${t.symbol}`}
            className={`grid grid-cols-3 py-1.5 text-xs hover:bg-white/5 ${t.symbol === active ? "bg-white/5" : ""}`}>
            <span className="text-white">{base}<span className="text-zinc-500">/{quote}</span></span>
            <span className="text-right text-zinc-200">{fmt(t.last, dp(t.last))}</span>
            <span className={`text-right ${t.changePct >= 0 ? "text-[#13c38b]" : "text-[#f6465d]"}`}>
              {t.changePct >= 0 ? "+" : ""}{t.changePct.toFixed(2)}%
            </span>
          </Link>
        );
      })}
    </div>
  );
}
