import { useState, useEffect } from "react"
// ถ้าอยู่ใน App.tsx:
import { fetchMarketTickers, CoinIcon, formatTHB, type MarketTicker } from "../../App"
/* =========================================================
   วางทั้งก้อนนี้ในไฟล์ App.tsx "ก่อน" ฟังก์ชันหน้า Landing
   (ใช้ useState, useEffect, fetchMarketTickers, CoinIcon, formatTHB
    ที่มีอยู่ใน App.tsx แล้ว ไม่ต้อง import เพิ่ม)

   มี 2 ตัว:
   1) <HeroVisual />  = ลูกโลก + เหรียญ 3D ลอยหมุน + จุดแสงวิ่งเข้าหาเหรียญ
   2) <PriceTicker /> = แถบราคาเหรียญเลื่อนวนไม่รู้จบ
   ========================================================= */

const NB_CSS = `
@keyframes nb-float { 0%,100% { transform: translateY(-10px) } 50% { transform: translateY(12px) } }
@keyframes nb-spin { from { transform: rotateY(0deg) rotateX(-12deg) } to { transform: rotateY(360deg) rotateX(-12deg) } }
@keyframes nb-orbit { from { transform: rotate(0deg) } to { transform: rotate(360deg) } }
@keyframes nb-pulse { 0%,100% { opacity: .55; transform: scale(1) } 50% { opacity: .9; transform: scale(1.08) } }
@keyframes nb-travel { 0% { left: -6%; opacity: 0 } 12% { opacity: 1 } 70% { opacity: 1 } 100% { left: 38%; opacity: 0 } }
@keyframes nb-marquee { from { transform: translateX(0) } to { transform: translateX(-50%) } }

.nb-hero { position: relative; width: 100%; height: 440px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.nb-glow { position: absolute; width: 70%; aspect-ratio: 1; border-radius: 50%;
  background: radial-gradient(circle, rgba(16,185,129,.28) 0%, rgba(16,185,129,.08) 45%, transparent 70%);
  filter: blur(20px); animation: nb-pulse 6s ease-in-out infinite; }
.nb-globe { position: absolute; width: 380px; height: 380px; border-radius: 50%; opacity: .55;
  background:
    radial-gradient(circle at 35% 30%, rgba(255,255,255,.10), transparent 55%),
    repeating-linear-gradient(0deg, rgba(16,185,129,.20) 0 1px, transparent 1px 26px),
    repeating-linear-gradient(90deg, rgba(16,185,129,.20) 0 1px, transparent 1px 26px);
  box-shadow: inset -30px -30px 60px rgba(0,0,0,.65), 0 0 60px rgba(16,185,129,.12);
  mask-image: radial-gradient(circle, #000 55%, transparent 72%);
  -webkit-mask-image: radial-gradient(circle, #000 55%, transparent 72%); }
.nb-ring { position: absolute; width: 330px; height: 330px; border-radius: 50%;
  border: 1px dashed rgba(16,185,129,.35); animation: nb-orbit 28s linear infinite; }
.nb-ring::after { content: ""; position: absolute; top: -5px; left: 50%; width: 10px; height: 10px; border-radius: 50%;
  background: #34d399; box-shadow: 0 0 14px 4px rgba(52,211,153,.8); }
.nb-line { position: absolute; left: 0; top: 50%; width: 42%; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(52,211,153,.5)); }
.nb-spark { position: absolute; top: calc(50% - 9px); width: 18px; height: 18px; background: #34d399;
  clip-path: polygon(25% 5%, 75% 5%, 100% 50%, 75% 95%, 25% 95%, 0 50%);
  box-shadow: 0 0 20px 6px rgba(52,211,153,.7); filter: drop-shadow(0 0 8px #34d399); animation: nb-travel 4.5s ease-in-out infinite; }
.nb-stage { perspective: 900px; animation: nb-float 6s ease-in-out infinite; }
.nb-coin { position: relative; width: 150px; height: 150px; transform-style: preserve-3d; animation: nb-spin 9s linear infinite; }
.nb-face { position: absolute; inset: 0; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 84px; font-weight: 800; color: #052e22; backface-visibility: hidden;
  background: radial-gradient(circle at 30% 25%, #6ee7b7, #10b981 55%, #047857);
  border: 6px solid #34d399; box-shadow: inset 0 0 22px rgba(0,0,0,.35), 0 0 40px rgba(16,185,129,.45); }
.nb-edge { position: absolute; inset: 0; border-radius: 50%; background: #059669; border: 2px solid #047857; }

.nb-marquee { position: relative; overflow: hidden; border-block: 1px solid rgba(255,255,255,.08);
  mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent); }
.nb-track { display: flex; width: max-content; animation: nb-marquee 45s linear infinite; }
.nb-marquee:hover .nb-track { animation-play-state: paused; }

@media (prefers-reduced-motion: reduce) {
  .nb-stage, .nb-coin, .nb-ring, .nb-glow, .nb-spark, .nb-track { animation: none !important; }
}
@media (max-width: 768px) { .nb-hero { height: 320px } .nb-globe { width: 280px; height: 280px } .nb-ring { width: 250px; height: 250px } .nb-coin { width: 110px; height: 110px } .nb-face { font-size: 62px } }
`

export function HeroVisual() {
  const layers = [-8, -4, 0, 4, 8]
  return (
    <div className="nb-hero" aria-hidden="true">
      <style>{NB_CSS}</style>
      <div className="nb-glow" />
      <div className="nb-globe" />
      <div className="nb-ring" />
      <div className="nb-line" />
      <div className="nb-spark" />
      <div className="nb-stage">
        <div className="nb-coin">
          <div className="nb-face" style={{ transform: "translateZ(9px)" }}>₿</div>
          {layers.map((z) => (
            <div key={z} className="nb-edge" style={{ transform: `translateZ(${z}px)` }} />
          ))}
          <div className="nb-face" style={{ transform: "rotateY(180deg) translateZ(9px)" }}>₿</div>
        </div>
      </div>
    </div>
  )
}

export function PriceTicker() {
  const [rows, setRows] = useState<MarketTicker[]>([])

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const data = await fetchMarketTickers()
        if (alive) setRows([...data].sort((a, b) => b.volume * b.price - a.volume * a.price).slice(0, 14))
      } catch {
        // โหลดไม่ได้ก็ไม่แสดงแถบ
      }
    }
    load()
    const t = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  if (rows.length === 0) return null

  const items = [...rows, ...rows] // ซ้ำ 2 ชุดเพื่อให้วนต่อเนื่อง
  return (
    <div className="nb-marquee py-4">
      <style>{NB_CSS}</style>
      <div className="nb-track">
        {items.map((r, i) => (
          <div key={`${r.asset}-${i}`} className="mx-6 flex items-center gap-2.5 whitespace-nowrap">
            <CoinIcon asset={r.asset} size={24} />
            <span className="text-sm font-semibold">{r.asset}</span>
            <span className="text-sm tabular-nums text-muted-foreground">{formatTHB(r.price)}</span>
            <span className={`text-xs font-medium tabular-nums ${r.change >= 0 ? "text-emerald-500" : "text-red-500"}`}>
              {r.change >= 0 ? "▲ +" : "▼ "}
              {r.change.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
