"""Technical screener: ทะเบียนตัวชี้วัด + คำนวณทุกตัว + ลูปพื้นหลัง

screener.py นำ TECH_GROUPS / TECH_METRICS ไปต่อท้ายทะเบียนเดิม และเรียก get(symbol) เพื่อเอาค่ามาผสมกับแถว
ค่าทุกตัวคำนวณจาก "ราคาปิดรายวันล่าสุด" (ไม่ใช่ real-time)
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, timedelta

import numpy as np

from . import bars
from . import indicators as ind

log = logging.getLogger("stocks.technicals")

# ───────────────────────── ทะเบียน ─────────────────────────

TECH_GROUPS = [
    ("T1", "Moving Average (ราคาห่างจากเส้น %)"),
    ("T2", "เทรนด์ / ทิศทาง"),
    ("T3", "Oscillator / โมเมนตัม"),
    ("T4", "ความผันผวน"),
    ("T5", "ราคา & วอลุ่ม"),
    ("T6", "Pivot Points (ราคาห่างจากระดับ %)"),
    ("T7", "แพทเทิร์นแท่งเทียน"),
    ("T8", "คะแนนรวม (Rating)"),
]

TECH_METRICS: list[dict] = []


def _add(id, label, group, unit, ph="", tip=""):
    TECH_METRICS.append({"id": id, "label": label, "group": group, "tier": "tech",
                         "unit": unit, "ph": ph, "tip": tip})


# T1
for _p in (10, 20, 30, 50, 100, 200):
    _add(f"distSma{_p}", f"SMA {_p}", "T1", "pct", "เช่น 0 (อยู่เหนือเส้น)", f"(ราคาปิด ÷ SMA{_p} − 1) × 100  ค่าบวก = ราคาอยู่เหนือเส้น")
for _p in (10, 20, 30, 50, 100, 200):
    _add(f"distEma{_p}", f"EMA {_p}", "T1", "pct", "เช่น 0", f"ราคาปิดห่างจาก EMA{_p} (%)")
for _p in (9, 21, 50):
    _add(f"distHma{_p}", f"Hull MA {_p}", "T1", "pct", "เช่น 0", f"ราคาปิดห่างจาก Hull MA({_p}) (%)")
for _p in (20, 50):
    _add(f"distVwma{_p}", f"VWMA {_p}", "T1", "pct", "เช่น 0", f"ราคาปิดห่างจาก Volume-weighted MA({_p}) (%)")
_add("goldenCrossDays", "Golden Cross (SMA50 ตัดขึ้น SMA200) กี่วันก่อน", "T1", "days", "เช่น 10 (ไม่เกิน)",
     "จำนวนวันทำการนับจากที่ SMA50 ตัดขึ้นเหนือ SMA200 (ต้องยังอยู่เหนือ และเกิดภายใน 120 วัน) ใส่ช่อง 'ไม่เกิน'")
_add("deathCrossDays", "Death Cross (SMA50 ตัดลง SMA200) กี่วันก่อน", "T1", "days", "เช่น 10 (ไม่เกิน)",
     "จำนวนวันทำการนับจากที่ SMA50 ตัดลงต่ำกว่า SMA200 (ยังต่ำอยู่ และเกิดภายใน 120 วัน)")

# T2
_add("macd", "MACD (12,26)", "T2", "num", "เช่น 0", "EMA12 − EMA26 หน่วยเป็นราคา")
_add("macdSignal", "MACD Signal (9)", "T2", "num")
_add("macdHist", "MACD Histogram", "T2", "num", "เช่น 0", "MACD − Signal  ค่าบวก = โมเมนตัมขาขึ้น")
_add("macdBullDays", "MACD ตัดขึ้นเหนือ Signal กี่วันก่อน", "T2", "days", "เช่น 3 (ไม่เกิน)", "ภายใน 30 วัน และยังอยู่เหนือ Signal")
_add("macdBearDays", "MACD ตัดลงใต้ Signal กี่วันก่อน", "T2", "days", "เช่น 3 (ไม่เกิน)", "ภายใน 30 วัน และยังอยู่ใต้ Signal")
_add("sarDist", "Parabolic SAR (ราคาห่างจาก SAR %)", "T2", "pct", "เช่น 0", "ค่าบวก = ราคาอยู่เหนือ SAR (เทรนด์ขึ้น) ค่าลบ = เทรนด์ลง")
_add("adx", "ADX (14)", "T2", "num", "เช่น 25", "ความแรงของเทรนด์ ไม่บอกทิศทาง >25 = เทรนด์ชัด")
_add("plusDI", "+DI (14)", "T2", "num", "", "Directional Movement Index ฝั่งขึ้น")
_add("minusDI", "−DI (14)", "T2", "num", "", "Directional Movement Index ฝั่งลง")
_add("aroonUp", "Aroon Up (14)", "T2", "num", "เช่น 70")
_add("aroonDown", "Aroon Down (14)", "T2", "num", "เช่น 30")
_add("donchianPos", "ตำแหน่งในช่อง Donchian 20 วัน (%)", "T2", "num", "เช่น 95 (ใกล้ทะลุขึ้น)", "0 = ที่ต่ำสุด 20 วัน, 100 = ที่สูงสุด 20 วัน")
_add("bullPower", "Bull Power (Elder, 13)", "T2", "num", "", "High − EMA13")
_add("bearPower", "Bear Power (Elder, 13)", "T2", "num", "", "Low − EMA13")

# T3
_add("rsi", "RSI (14)", "T3", "num", "เช่น 30 (ไม่เกิน)", "<30 มักถือว่า oversold, >70 overbought")
_add("stochK", "Stochastic %K (14,3,3)", "T3", "num", "เช่น 20")
_add("stochD", "Stochastic %D", "T3", "num", "เช่น 20")
_add("stochRsiK", "Stochastic RSI %K", "T3", "num", "เช่น 20", "TradingView: RSI 14, Stoch 14, smooth 3,3 (สเกล 0–100)")
_add("stochRsiD", "Stochastic RSI %D", "T3", "num", "เช่น 20")
_add("cci", "CCI (20)", "T3", "num", "เช่น -100 (ไม่เกิน)")
_add("williamsR", "Williams %R (14)", "T3", "num", "เช่น -80 (ไม่เกิน)", "ช่วง −100 ถึง 0")
_add("roc", "Rate of Change (9) %", "T3", "pct", "เช่น 5")
_add("momentum", "Momentum (10)", "T3", "num", "เช่น 0")
_add("ao", "Awesome Oscillator", "T3", "num", "เช่น 0")
_add("uo", "Ultimate Oscillator", "T3", "num", "เช่น 30 (ไม่เกิน)", "Larry Williams 7/14/28")
_add("mfi", "Money Flow Index (14)", "T3", "num", "เช่น 20 (ไม่เกิน)", "RSI ที่ถ่วงด้วยวอลุ่ม")
_add("cmf", "Chaikin Money Flow (20)", "T3", "num", "เช่น 0.1", "ช่วง −1 ถึง +1  ค่าบวก = แรงซื้อ")

# T4
_add("atr", "ATR (14)", "T4", "usd", "", "Average True Range (Wilder)")
_add("atrPct", "ATR % ของราคา", "T4", "pct", "เช่น 3")
_add("adr", "Average Daily Range (14)", "T4", "usd", "", "ค่าเฉลี่ย High − Low")
_add("adrPct", "Average Daily Range % (20)", "T4", "pct", "เช่น 3", "สูตร TradingView: 100 × (SMA(High/Low, 20) − 1)")
_add("bbPercentB", "Bollinger %B (20,2)", "T4", "num", "เช่น 1 (ทะลุขอบบน)", "0 = ขอบล่าง, 1 = ขอบบน, >1 = ทะลุบน, <0 = ทะลุล่าง")
_add("bbWidth", "Bollinger Bandwidth %", "T4", "pct", "เช่น 5 (ไม่เกิน = บีบตัว)", "(บน − ล่าง) ÷ กลาง × 100  ค่าต่ำ = ตลาดนิ่ง/ก่อนระเบิด")

# T5
_add("perf1w", "ผลตอบแทน 1 สัปดาห์", "T5", "pct", "เช่น 5")
_add("perf1m", "ผลตอบแทน 1 เดือน", "T5", "pct", "เช่น 10")
_add("perf3m", "ผลตอบแทน 3 เดือน", "T5", "pct", "เช่น 15")
_add("perf6m", "ผลตอบแทน 6 เดือน", "T5", "pct", "เช่น 20")
_add("perfYtd", "ผลตอบแทน YTD", "T5", "pct", "เช่น 10")
_add("perf1y", "ผลตอบแทน 1 ปี", "T5", "pct", "เช่น 20")
_add("relVolume", "Relative Volume (วอลุ่มวันล่าสุด ÷ เฉลี่ย 20 วัน)", "T5", "x", "เช่น 2", "≥2 = วอลุ่มพุ่งเทียบปกติ")
_add("gapPct", "Gap เปิดเทียบปิดก่อนหน้า %", "T5", "pct", "เช่น 3")
_add("distVwap20", "ห่างจาก VWAP 20 วัน (%)", "T5", "pct", "เช่น 0",
     "VWAP แบบสะสม 20 วันจากแท่งรายวัน (ไม่ใช่ VWAP ภายในวันแบบ TradingView ซึ่งต้องใช้ข้อมูลรายนาที)")

# T6
_PIV = [("classic", "Classic"), ("fibonacci", "Fibonacci"), ("woodie", "Woodie"), ("camarilla", "Camarilla"), ("demark", "DeMark")]
for _k, _n in _PIV:
    for _lv in ("P", "R1", "S1"):
        _add(f"pivot{_k.capitalize()}{_lv}", f"{_n} · {_lv}", "T6", "pct", "เช่น 0",
             f"ราคาปิดห่างจากระดับ {_lv} ของ Pivot {_n} (%) คำนวณจากแท่งล่าสุด = แนวของวันถัดไป")

# T7
_CANDLE_LABEL = {
    "doji": "Doji", "hammer": "Hammer (ขาลงก่อนหน้า)", "invertedHammer": "Inverted Hammer", "hangingMan": "Hanging Man",
    "shootingStar": "Shooting Star", "marubozuWhite": "Marubozu ขาว (ขึ้นเต็มแท่ง)", "marubozuBlack": "Marubozu ดำ (ลงเต็มแท่ง)",
    "bullEngulfing": "Bullish Engulfing", "bearEngulfing": "Bearish Engulfing", "bullHarami": "Bullish Harami",
    "bearHarami": "Bearish Harami", "piercing": "Piercing Line", "darkCloud": "Dark Cloud Cover",
    "morningStar": "Morning Star", "eveningStar": "Evening Star", "threeWhiteSoldiers": "Three White Soldiers",
    "threeBlackCrows": "Three Black Crows",
}
for _k in ind.CANDLE_IDS:
    _add(f"cs_{_k}", _CANDLE_LABEL[_k], "T7", "flag", "", "เจอที่แท่งล่าสุด (กติกามาตรฐาน อาจต่างจาก TradingView เล็กน้อย)")

# T8
_RATE_TIP = "สเกล −1 ถึง +1  >0.5 Strong Buy · >0.1 Buy · ±0.1 Neutral · <−0.1 Sell · <−0.5 Strong Sell (ตรรกะโหวตสไตล์ TradingView ยังไม่รวม Ichimoku)"
_add("techRating", "Technical Rating", "T8", "score", "เช่น 0.1 (ตั้งแต่)", _RATE_TIP)
_add("maRating", "Moving Averages Rating", "T8", "score", "เช่น 0.5", _RATE_TIP)
_add("oscRating", "Oscillators Rating", "T8", "score", "เช่น 0.1", _RATE_TIP)

TECH_IDS = [m["id"] for m in TECH_METRICS]


# ───────────────────────── คำนวณ ─────────────────────────

def _pct(a, b):
    try:
        return (a / b - 1.0) * 100.0 if b else math.nan
    except (TypeError, ZeroDivisionError):
        return math.nan


def compute(b: dict) -> dict | None:
    d, o, h, l, c, v = (b[k] for k in ("d", "o", "h", "l", "c", "v"))
    n = len(c)
    if n < 35:
        return None
    px = float(c[-1])
    r: dict = {}
    L = ind.last

    # Moving averages
    ctx: dict = {"close": px}
    for p in (10, 20, 30, 50, 100, 200):
        s, e = ind.sma(c, p), ind.ema(c, p)
        r[f"distSma{p}"], r[f"distEma{p}"] = _pct(px, L(s)), _pct(px, L(e))
        ctx[f"sma{p}"], ctx[f"ema{p}"] = L(s), L(e)
    for p in (9, 21, 50):
        m = ind.hma(c, p)
        r[f"distHma{p}"] = _pct(px, L(m))
        if p == 9:
            ctx["hma9"] = L(m)
    for p in (20, 50):
        m = ind.vwma(c, v, p)
        r[f"distVwma{p}"] = _pct(px, L(m))
        if p == 20:
            ctx["vwma20"] = L(m)
    s50, s200 = ind.sma(c, 50), ind.sma(c, 200)
    r["goldenCrossDays"] = ind.cross_days(s50, s200, "up", 120)
    r["deathCrossDays"] = ind.cross_days(s50, s200, "down", 120)

    # Trend
    mc, ms, mh = ind.macd(c)
    r["macd"], r["macdSignal"], r["macdHist"] = L(mc), L(ms), L(mh)
    r["macdBullDays"] = ind.cross_days(mc, ms, "up", 30)
    r["macdBearDays"] = ind.cross_days(mc, ms, "down", 30)
    ctx["macd"], ctx["macd_sig"] = L(mc), L(ms)
    sar, _up = ind.psar(h, l)
    r["sarDist"] = _pct(px, sar)
    pdi, mdi, adx = ind.dmi(h, l, c)
    r["adx"], r["plusDI"], r["minusDI"] = L(adx), L(pdi), L(mdi)
    ctx.update(adx=L(adx), pdi=L(pdi), mdi=L(mdi), pdi_prev=L(pdi, 1), mdi_prev=L(mdi, 1))
    au, ad = ind.aroon(h, l)
    r["aroonUp"], r["aroonDown"] = L(au), L(ad)
    hh, ll = ind.rolling_max(h, 20), ind.rolling_min(l, 20)
    r["donchianPos"] = 100.0 * (px - L(ll)) / (L(hh) - L(ll)) if L(hh) > L(ll) else math.nan
    e13 = ind.ema(c, 13)
    bull, bear = h - e13, l - e13
    r["bullPower"], r["bearPower"] = L(bull), L(bear)
    ctx.update(bull=L(bull), bear=L(bear), bull_prev=L(bull, 1), bear_prev=L(bear, 1), ema13=L(e13), ema13_prev=L(e13, 1))

    # Oscillators
    rs = ind.rsi(c)
    sk, sd = ind.stoch(h, l, c)
    srk, srd = ind.stoch_rsi(c)
    cc = ind.cci(h, l, c)
    wr = ind.williams_r(h, l, c)
    mo = ind.momentum(c, 10)
    ao = ind.awesome(h, l)
    uo = ind.ultimate(h, l, c)
    r["rsi"], r["stochK"], r["stochD"] = L(rs), L(sk), L(sd)
    r["stochRsiK"], r["stochRsiD"] = L(srk), L(srd)
    r["cci"], r["williamsR"] = L(cc), L(wr)
    r["roc"] = L(ind.roc(c, 9))
    r["momentum"], r["ao"], r["uo"] = L(mo), L(ao), L(uo)
    r["mfi"], r["cmf"] = L(ind.mfi(h, l, c, v)), L(ind.cmf(h, l, c, v))
    ctx.update(rsi=L(rs), rsi_prev=L(rs, 1), stK=L(sk), stD=L(sd), stK_prev=L(sk, 1), stD_prev=L(sd, 1),
               cci=L(cc), cci_prev=L(cc, 1), ao=L(ao), ao_prev=L(ao, 1), ao_prev2=L(ao, 2),
               mom=L(mo), mom_prev=L(mo, 1), srK=L(srk), srD=L(srd), wr=L(wr), wr_prev=L(wr, 1), uo=L(uo))

    # Volatility
    tr = ind.true_range(h, l, c)
    atr = L(ind.rma(tr, 14))
    r["atr"], r["atrPct"] = atr, (100.0 * atr / px if px else math.nan)
    r["adr"] = L(ind.sma(h - l, 14))
    with np.errstate(divide="ignore", invalid="ignore"):
        r["adrPct"] = 100.0 * (L(ind.sma(h / l, 20)) - 1.0)
    _, _, _, pb, bw = ind.bollinger(c)
    r["bbPercentB"], r["bbWidth"] = L(pb), L(bw)

    # Price & volume
    for key, k in (("perf1w", 5), ("perf1m", 21), ("perf3m", 63), ("perf6m", 126), ("perf1y", 252)):
        r[key] = _pct(px, float(c[-1 - k])) if n > k else math.nan
    prior = np.flatnonzero(d < f"{str(d[-1])[:4]}-01-01")
    r["perfYtd"] = _pct(px, float(c[prior[-1]])) if prior.size else math.nan
    avgv = float(v[-21:-1].mean()) if n >= 21 else 0.0
    r["relVolume"] = float(v[-1]) / avgv if avgv > 0 else math.nan
    r["gapPct"] = _pct(float(o[-1]), float(c[-2]))
    tp = (h + l + c) / 3.0
    sv = float(v[-20:].sum())
    r["distVwap20"] = _pct(px, float((tp[-20:] * v[-20:]).sum()) / sv) if sv > 0 else math.nan

    # Pivots
    pv = ind.pivots(float(o[-1]), float(h[-1]), float(l[-1]), px)
    for k, _ in _PIV:
        for lv in ("P", "R1", "S1"):
            r[f"pivot{k.capitalize()}{lv}"] = _pct(px, pv[k][lv])

    # Candles
    for k, val in ind.candles(o, h, l, c).items():
        r[f"cs_{k}"] = val

    # Ratings
    r["maRating"], r["oscRating"], r["techRating"] = ind.ratings(ctx)

    out = {}
    for k, val in r.items():
        if isinstance(val, (int, np.integer)):
            out[k] = int(val)
        else:
            out[k] = float(val) if val is not None and math.isfinite(val) else None
    return out


# ───────────────────────── สถานะในหน่วยความจำ + ลูป ─────────────────────────

_tech: dict[str, dict] = {}
_info: dict = {"asOf": None, "count": 0}


def get(symbol: str) -> dict | None:
    return _tech.get(symbol)


def info() -> dict:
    return {**_info, **{k: bars.STATUS[k] for k in ("mode", "phase", "done", "total", "error", "splitsOk")}}


def _compute_all(symbols: list[str]) -> tuple[dict, str | None]:
    data = bars.load_all(set(symbols))
    cutoff = (date.today() - timedelta(days=10)).isoformat()
    out, newest = {}, ""
    for s, b in data.items():
        if not len(b["c"]) or str(b["d"][-1]) < cutoff:     # ไม่มีแท่งใหม่ ≥10 วัน = เลิกซื้อขาย/ข้อมูลค้าง
            continue
        try:
            r = compute(b)
        except Exception:  # noqa: BLE001 - ตัวเดียวพังไม่ควรล้มทั้งชุด
            log.exception("technicals failed for %s", s)
            continue
        if r:
            out[s] = r
            newest = max(newest, str(b["d"][-1]))
    return out, (newest or None)


async def recompute(symbols: list[str]):
    res, newest = await asyncio.to_thread(_compute_all, symbols)
    _tech.clear()
    _tech.update(res)
    _info.update(asOf=newest, count=len(res))
    log.info("technicals: %d symbols, as of %s", len(res), newest)


async def loop(get_universe):
    bars.init_db()
    try:
        await recompute(get_universe())       # เปิดเครื่องมา ใช้ข้อมูลที่เก็บไว้ก่อน ไม่ต้องรอดึงใหม่
    except Exception:  # noqa: BLE001
        log.exception("technicals initial compute failed")
    while True:
        try:
            if await bars.run_once(get_universe()) or not _tech:
                await recompute(get_universe())
        except Exception:  # noqa: BLE001
            log.exception("technicals loop failed")
        await asyncio.sleep(1800)
