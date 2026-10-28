import type { CSSProperties } from "react";
import "./CoinsOverlay.css";

type Coin = {
  sym: string;
  img: string;
  pos: CSSProperties; // ตำแหน่งเป็น % รอบรูปแล็ปท็อป
  glow: string; // "r,g,b"
  dur: number;
  delay: number;
  size?: number; // px
  full?: boolean; // โลโก้เป็นวงกลมเต็มอยู่แล้ว
};

type CoinStyle = CSSProperties & {
  "--s": string;
  "--c": string;
  "--d": string;
  "--dl": string;
};

const COINS: Coin[] = [
  { sym: "NVDA",  img: "/coins/nvda.png",  pos: { left: "-4%", top: "2%" },      glow: "118,185,0",   dur: 6,   delay: 0,  full: true },
  { sym: "MSFT",  img: "/coins/msft.png",  pos: { left: "34%", top: "-6%" },     glow: "0,164,239",   dur: 7,   delay: -2, size: 78 },
  { sym: "GOOGL", img: "/coins/googl.png", pos: { left: "-6%", top: "46%" },     glow: "66,133,244",  dur: 5.5, delay: -1, size: 86 },
  { sym: "BTC",   img: "/coins/btc.png",   pos: { right: "-4%", top: "30%" },    glow: "247,147,26",  dur: 6.5, delay: -3, size: 100, full: true },
  { sym: "ETH",   img: "/coins/eth.png",   pos: { right: "10%", bottom: "-4%" }, glow: "130,150,255", dur: 7.5, delay: -4, size: 84, full: true },
  { sym: "SOL",   img: "/coins/sol.png",   pos: { left: "30%", bottom: "-8%" },  glow: "153,69,255",  dur: 6,   delay: -5, size: 76, full: true },
];

// ค่าตัวอย่าง ส่งข้อมูลจริงผ่าน prop changes ได้ เช่น changes={{ BTC: 1.2, NVDA: -0.8 }}
const DEMO: Record<string, number> = { NVDA: 2.4, MSFT: 1.9, GOOGL: -0.6, BTC: 1.8, ETH: 2.2, SOL: -1.2 };

type Props = {
  changes?: Record<string, number>;
  showTags?: boolean;
};

export default function CoinsOverlay({ changes = DEMO, showTags = true }: Props) {
  return (
    <div className="coins" aria-hidden="true">
      {COINS.map((c) => {
        const v = changes[c.sym];
        const style: CoinStyle = {
          ...c.pos,
          "--s": `${c.size ?? 92}px`,
          "--c": `rgba(${c.glow},.45)`,
          "--d": `${c.dur}s`,
          "--dl": `${c.delay}s`,
        };
        return (
          <div key={c.sym} className="coin" style={style}>
            <span className="orb">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className={c.full ? "full" : ""} src={c.img} alt="" />
            </span>
            {showTags && typeof v === "number" && (
              <span className="tag">
                {c.sym}{" "}
                <b className={v >= 0 ? "up" : "dn"}>
                  {v >= 0 ? "+" : ""}
                  {v.toFixed(1)}%
                </b>
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
