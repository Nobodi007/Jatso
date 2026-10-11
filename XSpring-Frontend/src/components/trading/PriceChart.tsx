import { useEffect, useRef } from "react"
import { createChart, ColorType } from "lightweight-charts"
import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts"
import { dp } from "../../lib/market"
import type { Candle } from "../../lib/market"

const G = "#13c38b", R = "#f6465d";
export const INTERVALS = [
  { label: "15นาที", v: "15m" }, { label: "1ชั่วโมง", v: "1h" }, { label: "4ชั่วโมง", v: "4h" },
  { label: "1วัน", v: "1d" }, { label: "1สัปดาห์", v: "1w" },
];

export default function PriceChart({ candles, live, interval, onInterval }:
  { candles: Candle[]; live: Candle | null; interval: string; onInterval: (v: string) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const wrap = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const cs = useRef<ISeriesApi<"Candlestick"> | null>(null)
  const vs = useRef<ISeriesApi<"Histogram"> | null>(null)

  useEffect(() => {
    if (!el.current) return;
    const c = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#71717a" },
      grid: { vertLines: { color: "#18181b" }, horzLines: { color: "#18181b" } },
      rightPriceScale: { borderColor: "#27272a" },
      timeScale: { borderColor: "#27272a", timeVisible: true },
      crosshair: { mode: CrosshairMode.Normal },
    });
    cs.current = c.addCandlestickSeries({ upColor: G, downColor: R, borderVisible: false, wickUpColor: G, wickDownColor: R });
    cs.current.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.25 } });
    vs.current = c.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "" });
    vs.current.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chart.current = c;
    return () => c.remove();
  }, []);

  useEffect(() => {
    if (!candles.length || !cs.current || !vs.current) return;
    const p = dp(candles[candles.length - 1].close);
    cs.current.applyOptions({ priceFormat: { type: "price", precision: p, minMove: 1 / 10 ** p } });
    cs.current.setData(candles.map((c) => ({ ...c, time: c.time as UTCTimestamp })));
    vs.current.setData(candles.map((c) => ({
      time: c.time as UTCTimestamp, value: c.volume, color: c.close >= c.open ? G + "80" : R + "80",
    })));
    chart.current?.timeScale().fitContent();
  }, [candles]);

  useEffect(() => {
    if (!live || !cs.current || !vs.current || !candles.length) return;
    if (live.time < candles[candles.length - 1].time) return;
    cs.current.update({ ...live, time: live.time as UTCTimestamp });
    vs.current.update({ time: live.time as UTCTimestamp, value: live.volume, color: live.close >= live.open ? G + "80" : R + "80" });
  }, [live, candles]);

  return (
    <div className="flex h-full flex-col bg-[#0f0f0f]">
      <div className="flex items-center gap-4 border-b border-[#1c1c1c] px-4 py-2 text-sm">
        <span className="text-zinc-500">เวลา</span>
        {INTERVALS.map((i) => (
          <button key={i.v} onClick={() => onInterval(i.v)}
            className={interval === i.v ? "text-[#13c38b]" : "text-zinc-400 hover:text-white"}>
            {i.label}
          </button>
        ))}
      </div>
      <div ref={el} className="min-h-0 flex-1" />
    </div>
  );
}
