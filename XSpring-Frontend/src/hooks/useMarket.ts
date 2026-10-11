"use client";
import { useEffect, useRef, useState } from "react";
import { Book, Candle, Ticker, Trade, fetchCandles, fetchDepth, fetchTicker, fetchTrades, subscribe } from "@/lib/market";

export function useMarket(symbol: string, interval: string) {
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [live, setLive] = useState<Candle | null>(null);
  const [book, setBook] = useState<Book>({ bids: [], asks: [] });
  const [trades, setTrades] = useState<Trade[]>([]);
  const buf = useRef<Trade[]>([]);

  useEffect(() => {
    let alive = true;
    setCandles([]); setLive(null);

    Promise.all([fetchTicker(symbol), fetchCandles(symbol, interval), fetchDepth(symbol), fetchTrades(symbol)])
      .then(([t, c, d, tr]) => {
        if (!alive) return;
        setTicker(t); setCandles(c); setBook(d); setTrades(tr);
      })
      .catch(console.error);

    const unsub = subscribe(symbol, interval, {
      onTicker: setTicker,
      onCandle: setLive,
      onDepth: setBook,
      onTrade: (t) => buf.current.unshift(t),
    });

    // รวม trade ทุก 300ms กันเว็บกระตุก (คู่ที่เทรดเยอะจะมีหลายร้อยรายการ/วินาที)
    const flush = setInterval(() => {
      if (!buf.current.length) return;
      const items = buf.current; buf.current = [];
      setTrades((p) => [...items, ...p].slice(0, 50));
    }, 300);

    return () => { alive = false; unsub(); clearInterval(flush); };
  }, [symbol, interval]);

  return { ticker, candles, live, book, trades };
}
