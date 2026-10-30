"""Indicator Library — คำนวณเองจาก OHLCV (ไม่พึ่ง endpoint indicator ของ Provider, ไม่พึ่ง TA-Lib)

กติกาที่ล็อกไว้ (มี test)
- ค่า ณ แท่ง i ใช้ข้อมูลถึงแท่ง i เท่านั้น: compute(bars[:i+1])[i] == compute(bars)[i]  (property test ทุกตัว)
- ช่วงอุ่นเครื่องยังไม่พอ -> NaN (เงื่อนไขที่เจอ NaN ถือว่า "ไม่เป็นจริง")
- Wilder smoothing สำหรับ RSI / ATR / ADX ; EMA seed ด้วย SMA ของ n ค่าแรก ; Bollinger ใช้ส่วนเบี่ยงเบนมาตรฐานประชากร (ddof=0)
- Donchian = สูงสุด/ต่ำสุดของ n แท่ง "ก่อนหน้า" (ไม่รวมแท่งปัจจุบัน) เพื่อให้ close > donchian.upper เป็นสัญญาณ breakout ได้จริง

เพิ่ม indicator ใหม่: ประกาศ IndicatorDef ใน REGISTRY (พร้อม warmup) แล้วเพิ่ม test ใน test_indicators.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

NAN = float("nan")
SOURCES = ("close", "open", "high", "low", "volume")


def isnan(x: float) -> bool:
    return x != x


# ---------------------------------------------------------------- primitives
def _col(bars: list[dict], key: str) -> list[float]:
    return [float(b[key]) for b in bars]


def _sma(x: list[float], n: int) -> list[float]:
    out = [NAN] * len(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if any(isnan(v) for v in w):
            continue
        out[i] = math.fsum(w) / n
    return out


def _ema(x: list[float], n: int) -> list[float]:
    """seed = SMA ของ n ค่าแรกที่ไม่ใช่ NaN ; รองรับ NaN นำหน้า (เช่น signal line ของ MACD)"""
    out = [NAN] * len(x)
    f = next((i for i, v in enumerate(x) if not isnan(v)), None)
    if f is None or len(x) - f < n:
        return out
    a = 2.0 / (n + 1.0)
    prev = math.fsum(x[f:f + n]) / n
    out[f + n - 1] = prev
    for i in range(f + n, len(x)):
        prev = a * x[i] + (1.0 - a) * prev
        out[i] = prev
    return out


def _wma(x: list[float], n: int) -> list[float]:
    out = [NAN] * len(x)
    den = n * (n + 1) / 2.0
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        if any(isnan(v) for v in w):
            continue
        out[i] = math.fsum((j + 1) * v for j, v in enumerate(w)) / den
    return out


def _wilder_avg(x: list[float], n: int, start: int) -> list[float]:
    """ค่าเฉลี่ยแบบ Wilder: ค่าแรก (ที่ index start+n-1) = mean(x[start:start+n]) แล้ว avg=(prev*(n-1)+x)/n"""
    out = [NAN] * len(x)
    if len(x) - start < n:
        return out
    prev = math.fsum(x[start:start + n]) / n
    out[start + n - 1] = prev
    for i in range(start + n, len(x)):
        prev = (prev * (n - 1) + x[i]) / n
        out[i] = prev
    return out


def _true_range(h: list[float], l: list[float], c: list[float]) -> list[float]:
    tr = [NAN] * len(c)
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


def _roll_max(x: list[float], n: int, lag: int = 0) -> list[float]:
    """max ของ n ค่าที่จบที่ i-lag (lag=1 -> ไม่รวมแท่งปัจจุบัน)"""
    out = [NAN] * len(x)
    for i in range(n - 1 + lag, len(x)):
        out[i] = max(x[i - lag - n + 1:i - lag + 1])
    return out


def _roll_min(x: list[float], n: int, lag: int = 0) -> list[float]:
    out = [NAN] * len(x)
    for i in range(n - 1 + lag, len(x)):
        out[i] = min(x[i - lag - n + 1:i - lag + 1])
    return out


# ---------------------------------------------------------------- indicators
def i_sma(bars, p, out):  return _sma(_col(bars, p["source"]), int(p["period"]))
def i_ema(bars, p, out):  return _ema(_col(bars, p["source"]), int(p["period"]))
def i_wma(bars, p, out):  return _wma(_col(bars, p["source"]), int(p["period"]))


def i_roc(bars, p, out):
    x, n = _col(bars, p["source"]), int(p["period"])
    r = [NAN] * len(x)
    for i in range(n, len(x)):
        if x[i - n] != 0:
            r[i] = (x[i] / x[i - n] - 1.0) * 100.0
    return r


def i_stddev(bars, p, out):
    x, n = _col(bars, p["source"]), int(p["period"])
    r = [NAN] * len(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        m = math.fsum(w) / n
        r[i] = math.sqrt(math.fsum((v - m) ** 2 for v in w) / n)
    return r


def i_rsi(bars, p, out):
    x, n = _col(bars, p["source"]), int(p["period"])
    N = len(x)
    res = [NAN] * N
    if N <= n:
        return res
    gain = [NAN] * N
    loss = [NAN] * N
    for i in range(1, N):
        d = x[i] - x[i - 1]
        gain[i], loss[i] = (d if d > 0 else 0.0), (-d if d < 0 else 0.0)
    ag, al = _wilder_avg(gain, n, 1), _wilder_avg(loss, n, 1)
    for i in range(n, N):
        if isnan(ag[i]) or isnan(al[i]):
            continue
        if al[i] == 0:
            res[i] = 100.0 if ag[i] > 0 else NAN              # ราคานิ่งสนิท -> นิยามไม่ได้
        else:
            res[i] = 100.0 - 100.0 / (1.0 + ag[i] / al[i])
    return res


def i_macd(bars, p, out):
    c = _col(bars, p["source"])
    f, s, g = _ema(c, int(p["fast"])), _ema(c, int(p["slow"])), int(p["signal"])
    line = [NAN if isnan(a) or isnan(b) else a - b for a, b in zip(f, s)]
    sig = _ema(line, g)
    if out == "macd":
        return line
    if out == "signal":
        return sig
    return [NAN if isnan(a) or isnan(b) else a - b for a, b in zip(line, sig)]


def i_bbands(bars, p, out):
    c, n, k = _col(bars, p["source"]), int(p["period"]), float(p["mult"])
    mid, sd = _sma(c, n), i_stddev(bars, {"source": p["source"], "period": n}, "")
    if out == "middle":
        return mid
    sign = 1.0 if out == "upper" else -1.0
    return [NAN if isnan(m) or isnan(s) else m + sign * k * s for m, s in zip(mid, sd)]


def i_atr(bars, p, out):
    h, l, c = _col(bars, "high"), _col(bars, "low"), _col(bars, "close")
    return _wilder_avg(_true_range(h, l, c), int(p["period"]), 1)


def i_stoch(bars, p, out):
    h, l, c = _col(bars, "high"), _col(bars, "low"), _col(bars, "close")
    k, d, sm = int(p["k"]), int(p["d"]), int(p["smooth"])
    hh, ll = _roll_max(h, k), _roll_min(l, k)
    raw = [NAN] * len(c)
    for i in range(len(c)):
        if not isnan(hh[i]) and hh[i] != ll[i]:
            raw[i] = 100.0 * (c[i] - ll[i]) / (hh[i] - ll[i])
    slow_k = raw if sm == 1 else _sma(raw, sm)
    return slow_k if out == "k" else _sma(slow_k, d)


def i_adx(bars, p, out):
    h, l, c = _col(bars, "high"), _col(bars, "low"), _col(bars, "close")
    n, N = int(p["period"]), len(c)
    tr = _true_range(h, l, c)
    pdm, mdm = [NAN] * N, [NAN] * N
    for i in range(1, N):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0

    def wsum(x):                                              # Wilder sum: S_t = S_{t-1} - S_{t-1}/n + x_t
        o = [NAN] * N
        if N - 1 < n:
            return o
        s = math.fsum(x[1:n + 1])
        o[n] = s
        for i in range(n + 1, N):
            s = s - s / n + x[i]
            o[i] = s
        return o

    st, sp, sm = wsum(tr), wsum(pdm), wsum(mdm)
    pdi, mdi, dx = [NAN] * N, [NAN] * N, [NAN] * N
    for i in range(n, N):
        if st[i] and not isnan(st[i]):
            pdi[i], mdi[i] = 100.0 * sp[i] / st[i], 100.0 * sm[i] / st[i]
            tot = pdi[i] + mdi[i]
            dx[i] = 100.0 * abs(pdi[i] - mdi[i]) / tot if tot else 0.0
    if out == "plus_di":
        return pdi
    if out == "minus_di":
        return mdi
    return _wilder_avg(dx, n, n)


def i_donchian(bars, p, out):
    n = int(p["period"])
    up, lo = _roll_max(_col(bars, "high"), n, 1), _roll_min(_col(bars, "low"), n, 1)
    if out == "upper":
        return up
    if out == "lower":
        return lo
    return [NAN if isnan(a) else (a + b) / 2.0 for a, b in zip(up, lo)]


def i_cci(bars, p, out):
    h, l, c, n = _col(bars, "high"), _col(bars, "low"), _col(bars, "close"), int(p["period"])
    tp = [(a + b + d) / 3.0 for a, b, d in zip(h, l, c)]
    r = [NAN] * len(c)
    for i in range(n - 1, len(c)):
        w = tp[i - n + 1:i + 1]
        m = math.fsum(w) / n
        md = math.fsum(abs(v - m) for v in w) / n
        if md > 0:
            r[i] = (tp[i] - m) / (0.015 * md)
    return r


def i_willr(bars, p, out):
    h, l, c, n = _col(bars, "high"), _col(bars, "low"), _col(bars, "close"), int(p["period"])
    hh, ll = _roll_max(h, n), _roll_min(l, n)
    r = [NAN] * len(c)
    for i in range(len(c)):
        if not isnan(hh[i]) and hh[i] != ll[i]:
            r[i] = -100.0 * (hh[i] - c[i]) / (hh[i] - ll[i])
    return r


# ---------------------------------------------------------------- registry
@dataclass(frozen=True)
class Param:
    name: str
    default: float
    lo: float
    hi: float
    integer: bool = True


@dataclass(frozen=True)
class IndicatorDef:
    key: str
    label: str
    params: tuple
    outputs: tuple
    compute: Callable
    warmup: Callable[[dict], int]            # จำนวนแท่งที่ควรมีก่อนวันเริ่มเพื่อให้ค่านิ่ง (EMA/Wilder ใช้ ~5 เท่าของ period)
    uses_source: bool = False                # รับ source = close/open/high/low/volume
    description: str = ""


P_N = lambda d=14, hi=400: Param("period", d, 2, hi)

REGISTRY: dict[str, IndicatorDef] = {d.key: d for d in [
    IndicatorDef("sma", "SMA (ค่าเฉลี่ยเคลื่อนที่แบบง่าย)", (P_N(20),), ("value",), i_sma, lambda p: int(p["period"]), True),
    IndicatorDef("ema", "EMA (ค่าเฉลี่ยเคลื่อนที่แบบเอ็กซ์โปเนนเชียล)", (P_N(20),), ("value",), i_ema, lambda p: 5 * int(p["period"]), True),
    IndicatorDef("wma", "WMA (ถ่วงน้ำหนักเชิงเส้น)", (P_N(20),), ("value",), i_wma, lambda p: int(p["period"]), True),
    IndicatorDef("rsi", "RSI (Wilder)", (P_N(14, 100),), ("value",), i_rsi, lambda p: 5 * int(p["period"]) + 1, True),
    IndicatorDef("macd", "MACD", (Param("fast", 12, 2, 200), Param("slow", 26, 3, 400), Param("signal", 9, 2, 200)),
                 ("macd", "signal", "hist"), i_macd, lambda p: 5 * int(p["slow"]) + int(p["signal"]), True),
    IndicatorDef("bbands", "Bollinger Bands", (P_N(20), Param("mult", 2.0, 0.1, 10.0, False)),
                 ("upper", "middle", "lower"), i_bbands, lambda p: int(p["period"]), True),
    IndicatorDef("atr", "ATR (Wilder)", (P_N(14, 100),), ("value",), i_atr, lambda p: 5 * int(p["period"]) + 1),
    IndicatorDef("stoch", "Stochastic", (Param("k", 14, 2, 100), Param("d", 3, 1, 50), Param("smooth", 3, 1, 50)),
                 ("k", "d"), i_stoch, lambda p: int(p["k"]) + int(p["smooth"]) + int(p["d"])),
    IndicatorDef("adx", "ADX / DMI (Wilder)", (P_N(14, 100),), ("adx", "plus_di", "minus_di"), i_adx, lambda p: 8 * int(p["period"])),
    IndicatorDef("donchian", "Donchian Channel (n แท่งก่อนหน้า)", (P_N(20),), ("upper", "middle", "lower"), i_donchian, lambda p: int(p["period"]) + 1),
    IndicatorDef("roc", "ROC (% เปลี่ยนแปลงใน n แท่ง)", (P_N(12),), ("value",), i_roc, lambda p: int(p["period"]), True),
    IndicatorDef("cci", "CCI", (P_N(20),), ("value",), i_cci, lambda p: int(p["period"])),
    IndicatorDef("willr", "Williams %R", (P_N(14, 100),), ("value",), i_willr, lambda p: int(p["period"])),
    IndicatorDef("stddev", "ส่วนเบี่ยงเบนมาตรฐาน (ความผันผวน)", (P_N(20),), ("value",), i_stddev, lambda p: int(p["period"]), True),
]}


def normalize_params(key: str, raw: dict) -> dict:
    """เติม default + ตรวจช่วงค่า; คืน dict พารามิเตอร์ (รวม source ถ้ารับ) — raise ValueError ข้อความไทย"""
    d = REGISTRY[key]
    allowed = {p.name for p in d.params} | ({"source"} if d.uses_source else set())
    extra = set(raw) - allowed - {"ind", "output"}
    if extra:
        raise ValueError(f"{key}: พารามิเตอร์ที่ไม่รองรับ {', '.join(sorted(extra))}")
    out: dict = {}
    for p in d.params:
        v = raw.get(p.name, p.default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"{key}.{p.name} ต้องเป็นตัวเลข")
        if p.integer and float(v) != int(v):
            raise ValueError(f"{key}.{p.name} ต้องเป็นจำนวนเต็ม")
        if not (p.lo <= v <= p.hi):
            raise ValueError(f"{key}.{p.name} ต้องอยู่ระหว่าง {p.lo:g} ถึง {p.hi:g}")
        out[p.name] = int(v) if p.integer else float(v)
    if d.uses_source:
        src = raw.get("source", "close")
        if src not in SOURCES:
            raise ValueError(f"{key}.source ต้องเป็นหนึ่งใน {', '.join(SOURCES)}")
        out["source"] = src
    if key == "macd" and out["fast"] >= out["slow"]:
        raise ValueError("macd.fast ต้องน้อยกว่า macd.slow")
    if key == "stoch" and out["smooth"] > out["k"]:
        raise ValueError("stoch.smooth ต้องไม่เกิน stoch.k")
    return out


def compute(bars: list[dict], key: str, params: dict, output: str) -> list[float]:
    d = REGISTRY[key]
    return d.compute(bars, params, output)


def catalogue() -> list[dict]:
    """รายการสำหรับ UI (ส่งผ่าน /meta)"""
    return [{"key": d.key, "label": d.label, "outputs": list(d.outputs), "uses_source": d.uses_source,
             "params": [{"name": p.name, "default": p.default, "min": p.lo, "max": p.hi, "integer": p.integer} for p in d.params]}
            for d in REGISTRY.values()]
