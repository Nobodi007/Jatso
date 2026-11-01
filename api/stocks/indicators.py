"""ตัวชี้วัด Technical แบบ TradingView (ค่าเริ่มต้นเดียวกัน) คำนวณจากแท่งรายวัน

ใช้ numpy อย่างเดียว ไม่พึ่ง TA-Lib / pandas
 - EMA / RMA(Wilder) ใช้ SMA เป็นค่าเริ่มต้น (เหมือน Pine `ta.ema` / `ta.rma`)
 - Stdev ของ Bollinger เป็นแบบ population (ddof=0) เหมือน TradingView
 - อาร์เรย์ทุกตัวเรียงจากเก่า → ใหม่ ค่าที่ยังคำนวณไม่ได้เป็น NaN
"""
from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as _win

NAN = float("nan")


# ───────────────────────── primitives ─────────────────────────

def _first_valid(x: np.ndarray) -> int:
    ok = np.flatnonzero(~np.isnan(x))
    return int(ok[0]) if ok.size else len(x)


def _tail(fn):
    """ให้ฟังก์ชันทำงานบนส่วนที่ไม่ใช่ NaN ของอาร์เรย์ แล้วเติม NaN นำหน้ากลับ"""
    def wrapped(x, *a, **k):
        x = np.asarray(x, dtype=float)
        s = _first_valid(x)
        out = np.full(len(x), np.nan)
        if s < len(x):
            out[s:] = fn(x[s:], *a, **k)
        return out
    return wrapped


@_tail
def sma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(x)
        out[n - 1:] = (cs[n - 1:] - np.concatenate(([0.0], cs[:-n]))) / n
    return out


@_tail
def _recursive(x, alpha, n):
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    out[n - 1] = x[:n].mean()
    for i in range(n, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def ema(x, n):
    return _recursive(x, 2.0 / (n + 1), n)


def rma(x, n):
    return _recursive(x, 1.0 / n, n)


@_tail
def wma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        w = np.arange(1, n + 1, dtype=float)
        out[n - 1:] = _win(x, n) @ w / w.sum()
    return out


def hma(x, n):
    half, root = max(n // 2, 1), max(int(round(math.sqrt(n))), 1)
    return wma(2 * wma(x, half) - wma(x, n), root)


def rolling_max(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = _win(x, n).max(axis=1)
    return out


def rolling_min(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = _win(x, n).min(axis=1)
    return out


def rolling_sum(x, n):
    return sma(x, n) * n


def rolling_std(x, n):  # population
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = _win(x, n).std(axis=1)
    return out


def shift(x, k=1):
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:-k]
    return out


def last(x, back=0):
    i = len(x) - 1 - back
    if i < 0:
        return NAN
    v = float(x[i])
    return v if math.isfinite(v) else NAN


def true_range(h, l, c):
    pc = shift(c)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    return tr


# ───────────────────────── indicators ─────────────────────────

def rsi(c, n=14):
    ch = np.diff(c, prepend=np.nan)
    gain = np.where(np.isnan(ch), np.nan, np.maximum(ch, 0.0))
    loss = np.where(np.isnan(ch), np.nan, np.maximum(-ch, 0.0))
    ag, al = rma(gain, n), rma(loss, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(al == 0, 100.0, 100.0 - 100.0 / (1.0 + ag / al))
    out[np.isnan(ag) | np.isnan(al)] = np.nan
    return out


def stoch(h, l, c, k=14, ks=3, ds=3):
    hh, ll = rolling_max(h, k), rolling_min(l, k)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.where(hh - ll > 0, 100.0 * (c - ll) / (hh - ll), np.nan)
    kk = sma(raw, ks)
    return kk, sma(kk, ds)


def stoch_rsi(c, rl=14, sl=14, ks=3, ds=3):
    r = rsi(c, rl)
    hh, ll = rolling_max(r, sl), rolling_min(r, sl)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.where(hh - ll > 0, 100.0 * (r - ll) / (hh - ll), np.nan)
    kk = sma(raw, ks)
    return kk, sma(kk, ds)


def cci(h, l, c, n=20):
    tp = (h + l + c) / 3.0
    out = np.full(len(tp), np.nan)
    if len(tp) >= n:
        w = _win(tp, n)
        m = w.mean(axis=1)
        md = np.abs(w - m[:, None]).mean(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[n - 1:] = np.where(md > 0, (tp[n - 1:] - m) / (0.015 * md), 0.0)
    return out


def williams_r(h, l, c, n=14):
    hh, ll = rolling_max(h, n), rolling_min(l, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(hh - ll > 0, -100.0 * (hh - c) / (hh - ll), np.nan)


def roc(c, n=9):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * (c / shift(c, n) - 1.0)


def momentum(c, n=10):
    return c - shift(c, n)


def awesome(h, l):
    m = (h + l) / 2.0
    return sma(m, 5) - sma(m, 34)


def ultimate(h, l, c, a=7, b=14, d=28):
    pc = shift(c)
    lo = np.minimum(l, pc)
    bp = c - lo
    tr = np.maximum(h, pc) - lo
    out = []
    for n in (a, b, d):
        with np.errstate(divide="ignore", invalid="ignore"):
            out.append(rolling_sum(bp, n) / rolling_sum(tr, n))
    return 100.0 * (4 * out[0] + 2 * out[1] + out[2]) / 7.0


def mfi(h, l, c, v, n=14):
    tp = (h + l + c) / 3.0
    raw = tp * v
    d = np.diff(tp, prepend=np.nan)
    pos = np.where(d > 0, raw, 0.0)
    neg = np.where(d < 0, raw, 0.0)
    ps, ns = rolling_sum(pos[1:], n), rolling_sum(neg[1:], n)
    with np.errstate(divide="ignore", invalid="ignore"):
        m = np.where(ns == 0, 100.0, 100.0 - 100.0 / (1.0 + ps / ns))
    m[np.isnan(ps) | np.isnan(ns)] = np.nan
    return np.concatenate(([np.nan], m))


def cmf(h, l, c, v, n=20):
    rng = h - l
    with np.errstate(divide="ignore", invalid="ignore"):
        mfv = np.where(rng > 0, ((c - l) - (h - c)) / rng * v, 0.0)
        return rolling_sum(mfv, n) / rolling_sum(v, n)


def dmi(h, l, c, n=14):
    up = np.diff(h, prepend=np.nan)
    dn = -np.diff(l, prepend=np.nan)
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdm[0] = mdm[0] = np.nan
    atr = rma(true_range(h, l, c), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * rma(pdm, n) / atr
        mdi = 100.0 * rma(mdm, n) / atr
        dx = np.where(pdi + mdi > 0, 100.0 * np.abs(pdi - mdi) / (pdi + mdi), 0.0)
    dx[np.isnan(pdi) | np.isnan(mdi)] = np.nan
    return pdi, mdi, rma(dx, n)


def aroon(h, l, n=14):
    up = np.full(len(h), np.nan)
    dn = np.full(len(h), np.nan)
    if len(h) > n:
        wh, wl = _win(h, n + 1), _win(l, n + 1)
        # ถ้าราคาเท่ากันให้ถือแท่งล่าสุด (เหมือน TradingView)
        ih = n - np.argmax(wh[:, ::-1], axis=1)   # 0..n → ตำแหน่งในหน้าต่าง
        il = n - np.argmax(wl[:, ::-1], axis=1)
        up[n:] = 100.0 * ih / n
        dn[n:] = 100.0 * il / n
    return up, dn


def psar(h, l, start=0.02, inc=0.02, mx=0.2):
    """คืน (sar, uptrend:bool) ของแท่งล่าสุด"""
    n = len(h)
    if n < 3:
        return NAN, True
    up = h[1] >= h[0]
    sar = l[0] if up else h[0]
    ep = h[1] if up else l[1]
    af = start
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < sar:
                up, sar, ep, af = False, ep, l[i], start
            elif h[i] > ep:
                ep, af = h[i], min(af + inc, mx)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > sar:
                up, sar, ep, af = True, ep, h[i], start
            elif l[i] < ep:
                ep, af = l[i], min(af + inc, mx)
    return float(sar), up


def bollinger(c, n=20, k=2.0):
    mid = sma(c, n)
    sd = rolling_std(c, n)
    up, lo = mid + k * sd, mid - k * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        pb = np.where(up - lo > 0, (c - lo) / (up - lo), np.nan)
        bw = 100.0 * (up - lo) / mid
    return mid, up, lo, pb, bw


def vwma(c, v, n):
    with np.errstate(divide="ignore", invalid="ignore"):
        return sma(c * v, n) / sma(v, n)


def macd(c, fast=12, slow=26, sig=9):
    m = ema(c, fast) - ema(c, slow)
    s = ema(m, sig)
    return m, s, m - s


def cross_days(a, b, direction: str, lookback: int):
    """จำนวนแท่งนับจากครั้งล่าสุดที่ a ตัด b (up/down) ถ้าสถานะปัจจุบันยังเป็นด้านนั้นและเกิดภายใน lookback"""
    n = len(a)
    if n < 3:
        return NAN
    cur = a[-1] - b[-1]
    if not math.isfinite(cur) or cur == 0:
        return NAN
    if (direction == "up") != (cur > 0):
        return NAN
    for k in range(0, min(lookback, n - 2) + 1):
        i = n - 1 - k
        d0, d1 = a[i - 1] - b[i - 1], a[i] - b[i]
        if not (math.isfinite(d0) and math.isfinite(d1)):
            return NAN
        if direction == "up" and d0 <= 0 < d1:
            return float(k)
        if direction == "down" and d0 >= 0 > d1:
            return float(k)
    return NAN


# ───────────────────────── pivots ─────────────────────────

def pivots(o, h, l, c):
    """ระดับ pivot จากแท่งล่าสุด (ใช้เป็นแนวสำหรับวันซื้อขายถัดไป)"""
    O, H, L, C = o, h, l, c
    R = H - L
    out = {}
    p = (H + L + C) / 3
    out["classic"] = {"P": p, "R1": 2 * p - L, "S1": 2 * p - H}
    out["fibonacci"] = {"P": p, "R1": p + 0.382 * R, "S1": p - 0.382 * R}
    pw = (H + L + 2 * C) / 4
    out["woodie"] = {"P": pw, "R1": 2 * pw - L, "S1": 2 * pw - H}
    out["camarilla"] = {"P": p, "R1": C + 1.1 * R / 12, "S1": C - 1.1 * R / 12}
    x = H + 2 * L + C if C < O else (2 * H + L + C if C > O else H + L + 2 * C)
    out["demark"] = {"P": x / 4, "R1": x / 2 - L, "S1": x / 2 - H}
    return out


# ───────────────────────── candlesticks ─────────────────────────

def candles(o, h, l, c) -> dict[str, int]:
    """แพทเทิร์นที่แท่งล่าสุด (1 = เจอ, 0 = ไม่เจอ) กติกาแบบมาตรฐานทั่วไป ไม่ใช่ชุดเดียวกับ TradingView เป๊ะ"""
    n = len(c)
    z = {k: 0 for k in CANDLE_IDS}
    if n < 8:
        return z
    body = np.abs(c - o)
    rng = h - l
    up_w = h - np.maximum(o, c)
    lo_w = np.minimum(o, c) - l
    avg_body = float(body[-11:-1].mean()) if n >= 11 else float(body[:-1].mean())
    avg_rng = float(rng[-11:-1].mean()) if n >= 11 else float(rng[:-1].mean())
    g = lambda i: c[i] > o[i]
    r = lambda i: c[i] < o[i]
    down = c[-2] < c[-7]
    uptr = c[-2] > c[-7]
    b0, r0 = body[-1], rng[-1]
    if r0 <= 0:
        return z

    z["doji"] = int(b0 <= 0.1 * r0)
    small_up, small_lo = up_w[-1] <= 0.15 * r0, lo_w[-1] <= 0.15 * r0
    long_lo, long_up = lo_w[-1] >= 2 * b0 and b0 > 0, up_w[-1] >= 2 * b0 and b0 > 0
    z["hammer"] = int(long_lo and small_up and down)
    z["hangingMan"] = int(long_lo and small_up and uptr)
    z["invertedHammer"] = int(long_up and small_lo and down)
    z["shootingStar"] = int(long_up and small_lo and uptr)
    z["marubozuWhite"] = int(g(-1) and b0 >= 0.9 * r0 and r0 >= avg_rng)
    z["marubozuBlack"] = int(r(-1) and b0 >= 0.9 * r0 and r0 >= avg_rng)

    p_mid = (o[-2] + c[-2]) / 2
    z["bullEngulfing"] = int(r(-2) and g(-1) and o[-1] <= c[-2] and c[-1] >= o[-2] and body[-1] > body[-2])
    z["bearEngulfing"] = int(g(-2) and r(-1) and o[-1] >= c[-2] and c[-1] <= o[-2] and body[-1] > body[-2])
    z["bullHarami"] = int(r(-2) and g(-1) and body[-2] >= avg_body and o[-1] > c[-2] and c[-1] < o[-2] and body[-1] < body[-2])
    z["bearHarami"] = int(g(-2) and r(-1) and body[-2] >= avg_body and o[-1] < c[-2] and c[-1] > o[-2] and body[-1] < body[-2])
    z["piercing"] = int(r(-2) and g(-1) and body[-2] >= avg_body and o[-1] < c[-2] and p_mid < c[-1] < o[-2])
    z["darkCloud"] = int(g(-2) and r(-1) and body[-2] >= avg_body and o[-1] > c[-2] and o[-2] < c[-1] < p_mid)

    mid3 = (o[-3] + c[-3]) / 2
    star_small = body[-2] <= 0.3 * body[-3]
    z["morningStar"] = int(r(-3) and body[-3] >= avg_body and star_small and max(o[-2], c[-2]) < c[-3] and g(-1) and c[-1] > mid3)
    z["eveningStar"] = int(g(-3) and body[-3] >= avg_body and star_small and min(o[-2], c[-2]) > c[-3] and r(-1) and c[-1] < mid3)

    def three(fn, sign):
        ok = all(fn(i) for i in (-3, -2, -1))
        if not ok:
            return 0
        for i in (-2, -1):
            if sign * (c[i] - c[i - 1]) <= 0:
                return 0
            if not (min(o[i - 1], c[i - 1]) <= o[i] <= max(o[i - 1], c[i - 1])):
                return 0
        wick = (up_w if sign > 0 else lo_w)
        return int(all(wick[i] <= 0.3 * body[i] for i in (-3, -2, -1)) and all(body[i] >= 0.5 * avg_body for i in (-3, -2, -1)))

    z["threeWhiteSoldiers"] = three(g, +1)
    z["threeBlackCrows"] = three(r, -1)
    return z


CANDLE_IDS = [
    "doji", "hammer", "invertedHammer", "hangingMan", "shootingStar", "marubozuWhite", "marubozuBlack",
    "bullEngulfing", "bearEngulfing", "bullHarami", "bearHarami", "piercing", "darkCloud",
    "morningStar", "eveningStar", "threeWhiteSoldiers", "threeBlackCrows",
]


# ───────────────────────── ratings (สไตล์ TradingView) ─────────────────────────

def _sgn(buy: bool, sell: bool) -> int:
    return 1 if buy else (-1 if sell else 0)


def ratings(ctx: dict) -> tuple[float, float, float]:
    """คะแนนรวม -1..+1 : (MA rating, Oscillator rating, Technical rating)
    >0.5 Strong Buy, >0.1 Buy, ±0.1 Neutral, <-0.1 Sell, <-0.5 Strong Sell
    ลอกตรรกะการโหวตของ TradingView เท่าที่เอกสารระบุ ยกเว้น Ichimoku ที่ยังไม่รวม ผลจึงอาจต่างจากเว็บเขาเล็กน้อย
    """
    px = ctx["close"]
    ma_votes = []
    for key in ("sma10", "sma20", "sma30", "sma50", "sma100", "sma200",
                "ema10", "ema20", "ema30", "ema50", "ema100", "ema200", "vwma20", "hma9"):
        v = ctx.get(key)
        if v is not None and math.isfinite(v):
            ma_votes.append(_sgn(v < px, v > px))

    o = []
    rs, rs1 = ctx["rsi"], ctx["rsi_prev"]
    if math.isfinite(rs) and math.isfinite(rs1):
        o.append(_sgn(rs < 30 and rs > rs1, rs > 70 and rs < rs1))
    k, d, k1, d1 = ctx["stK"], ctx["stD"], ctx["stK_prev"], ctx["stD_prev"]
    if all(map(math.isfinite, (k, d))):
        o.append(_sgn(k < 20 and d < 20 and k > d, k > 80 and d > 80 and k < d))
    cc, cc1 = ctx["cci"], ctx["cci_prev"]
    if math.isfinite(cc) and math.isfinite(cc1):
        o.append(_sgn(cc < -100 and cc > cc1, cc > 100 and cc < cc1))
    adx, pdi, mdi, pdi1, mdi1 = ctx["adx"], ctx["pdi"], ctx["mdi"], ctx["pdi_prev"], ctx["mdi_prev"]
    if all(map(math.isfinite, (adx, pdi, mdi, pdi1, mdi1))):
        o.append(_sgn(adx > 20 and pdi1 < mdi1 and pdi > mdi, adx > 20 and pdi1 > mdi1 and pdi < mdi))
    ao, ao1, ao2 = ctx["ao"], ctx["ao_prev"], ctx["ao_prev2"]
    if all(map(math.isfinite, (ao, ao1, ao2))):
        o.append(_sgn((ao > 0 and ao1 < 0) or (ao > 0 and ao1 > 0 and ao > ao1 and ao1 < ao2),
                      (ao < 0 and ao1 > 0) or (ao < 0 and ao1 < 0 and ao < ao1 and ao1 > ao2)))
    mo, mo1 = ctx["mom"], ctx["mom_prev"]
    if math.isfinite(mo) and math.isfinite(mo1):
        o.append(_sgn(mo > mo1, mo < mo1))
    m, s = ctx["macd"], ctx["macd_sig"]
    if math.isfinite(m) and math.isfinite(s):
        o.append(_sgn(m > s, m < s))
    sk, sd_, = ctx["srK"], ctx["srD"]
    if math.isfinite(sk) and math.isfinite(sd_):
        o.append(_sgn(sk < 20 and sd_ < 20 and sk > sd_, sk > 80 and sd_ > 80 and sk < sd_))
    wr, wr1 = ctx["wr"], ctx["wr_prev"]
    if math.isfinite(wr) and math.isfinite(wr1):
        o.append(_sgn(wr < -80 and wr > wr1, wr > -20 and wr < wr1))
    bull, bear, bull1, bear1, e13, e13p = (ctx[x] for x in ("bull", "bear", "bull_prev", "bear_prev", "ema13", "ema13_prev"))
    if all(map(math.isfinite, (bull, bear, bull1, bear1, e13, e13p))):
        o.append(_sgn(e13 > e13p and bear < 0 and bear > bear1, e13 < e13p and bull > 0 and bull < bull1))
    uo = ctx["uo"]
    if math.isfinite(uo):
        o.append(_sgn(uo > 70, uo < 30))

    ma_r = float(np.mean(ma_votes)) if ma_votes else NAN
    os_r = float(np.mean(o)) if o else NAN
    allv = ma_votes + o
    tech_r = float(np.mean(allv)) if allv else NAN
    return ma_r, os_r, tech_r
