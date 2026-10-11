export type Candle = { time: number; open: number; high: number; low: number; close: number; volume: number };
export type Level = [price: number, qty: number];
export type Book = { bids: Level[]; asks: Level[] };
export type Trade = { id: number; price: number; qty: number; time: number; isBuyerMaker: boolean };
export type Ticker = {
  symbol: string; last: number; change: number; changePct: number;
  high: number; low: number; volBase: number; volQuote: number;
};

// ===== เปลี่ยนแหล่งข้อมูลตรงนี้ =====
const REST = "https://api.binance.com/api/v3";
const WS = "wss://stream.binance.com:9443/stream?streams=";

const QUOTES = ["USDT", "FDUSD", "USDC", "THB", "BTC", "ETH"];
export function splitSymbol(s: string) {
  const q = QUOTES.find((q) => s.endsWith(q)) ?? s.slice(-4);
  return { base: s.slice(0, -q.length), quote: q };
}

export function dp(p: number) {
  if (p >= 100) return 2;
  if (p >= 1) return 4;
  if (p >= 0.01) return 5;
  return 8;
}
export const fmt = (n: number, d = 2) =>
  Number.isFinite(n) ? n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) : "-";

const toLevel = (l: [string, string]): Level => [+l[0], +l[1]];
const mapTicker = (t: any): Ticker => ({
  symbol: t.symbol ?? t.s,
  last: +(t.lastPrice ?? t.c),
  change: +(t.priceChange ?? t.p),
  changePct: +(t.priceChangePercent ?? t.P),
  high: +(t.highPrice ?? t.h),
  low: +(t.lowPrice ?? t.l),
  volBase: +(t.volume ?? t.v),
  volQuote: +(t.quoteVolume ?? t.q),
});

export async function fetchCandles(symbol: string, interval: string, limit = 300): Promise<Candle[]> {
  const r = await fetch(`${REST}/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`);
  const d: any[] = await r.json();
  return d.map((k) => ({ time: k[0] / 1000, open: +k[1], high: +k[2], low: +k[3], close: +k[4], volume: +k[5] }));
}

export async function fetchTicker(symbol: string): Promise<Ticker> {
  const r = await fetch(`${REST}/ticker/24hr?symbol=${symbol}`);
  return mapTicker(await r.json());
}

export async function fetchTickers(symbols: string[]): Promise<Ticker[]> {
  const q = encodeURIComponent(JSON.stringify(symbols));
  const r = await fetch(`${REST}/ticker/24hr?symbols=${q}`);
  return (await r.json()).map(mapTicker);
}

export async function fetchDepth(symbol: string, limit = 20): Promise<Book> {
  const r = await fetch(`${REST}/depth?symbol=${symbol}&limit=${limit}`);
  const d = await r.json();
  return { bids: d.bids.map(toLevel), asks: d.asks.map(toLevel) };
}

export async function fetchTrades(symbol: string, limit = 50): Promise<Trade[]> {
  const r = await fetch(`${REST}/trades?symbol=${symbol}&limit=${limit}`);
  const d: any[] = await r.json();
  return d.reverse().map((t) => ({ id: t.id, price: +t.price, qty: +t.qty, time: t.time, isBuyerMaker: t.isBuyerMaker }));
}

type Handlers = {
  onTicker: (t: Ticker) => void;
  onCandle: (c: Candle) => void;
  onDepth: (b: Book) => void;
  onTrade: (t: Trade) => void;
};

export function subscribe(symbol: string, interval: string, h: Handlers) {
  const s = symbol.toLowerCase();
  const url = WS + [`${s}@ticker`, `${s}@kline_${interval}`, `${s}@depth20@100ms`, `${s}@trade`].join("/");
  let ws: WebSocket;
  let closed = false;
  let retry: ReturnType<typeof setTimeout>;

  const connect = () => {
    ws = new WebSocket(url);
    ws.onmessage = (e) => {
      const { stream, data } = JSON.parse(e.data);
      if (stream.endsWith("@ticker")) h.onTicker(mapTicker(data));
      else if (stream.includes("@kline")) {
        const k = data.k;
        h.onCandle({ time: k.t / 1000, open: +k.o, high: +k.h, low: +k.l, close: +k.c, volume: +k.v });
      } else if (stream.includes("@depth")) h.onDepth({ bids: data.bids.map(toLevel), asks: data.asks.map(toLevel) });
      else if (stream.endsWith("@trade"))
        h.onTrade({ id: data.t, price: +data.p, qty: +data.q, time: data.T, isBuyerMaker: data.m });
    };
    ws.onclose = () => { if (!closed) retry = setTimeout(connect, 3000); };
  };
  connect();

  return () => { closed = true; clearTimeout(retry); ws?.close(); };
}
