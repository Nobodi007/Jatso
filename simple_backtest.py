"""
Simple Backtest — "ลองลงทุนย้อนหลัง" สำหรับคนทั่วไป
====================================================
โมดูลแยกไฟล์ ไม่ผูกกับ XSpring Dealer Suite (ไม่ import ไฟล์หลัก)

LAYERS
------
  1. ENGINE   pure logic (numpy/pandas ล้วน) — เทสต์ได้โดยไม่ต้องมี streamlit / network
  2. DATA     ดึงราคา THB (ใช้ fetch_fn ของแอปหลักได้ หรือ fallback เป็น yfinance เอง)
  3. UI       render_simple_backtest() — Streamlit

กลยุทธ์ที่รองรับ
  lump   ซื้อทีเดียวแล้วถือ
  dca    ทยอยซื้อ (รายวัน/สัปดาห์/เดือน)
  dip    ซื้อเพิ่มเมื่อราคาตกจากจุดสูงสุดล่าสุด X%
  trend  ถือเมื่อราคาอยู่เหนือเส้นค่าเฉลี่ย N วัน ขายเมื่อหลุด

หลักการที่ยึด
  - ไม่มี look-ahead: สัญญาณของ "วันนี้" ใช้ข้อมูลถึง "เมื่อวาน" เท่านั้น
  - หักค่าธรรมเนียม/spread ทุกครั้งที่ซื้อขาย
  - มูลค่าปลายทางคิดแบบ "ขายทั้งหมดวันนี้ ได้สุทธิเท่าไหร่"
  - เทียบกับ ถือเฉยๆ และ ฝากออมทรัพย์ เสมอ

ใช้งาน
  standalone : streamlit run simple_backtest.py
  ในแอปหลัก : from simple_backtest import render_simple_backtest
               render_simple_backtest(fetch_fn=fetch_price_data,
                                      assets=SUPPORTED_ASSETS,
                                      fee_pct=LOCAL_TRADING_FEE_PCT)
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

SB_VERSION = "1.0.0"

# =========================================================================
# LAYER 1 — ENGINE (pure)
# =========================================================================

DEFAULT_FEE_PCT = 0.0025          # ค่าธรรมเนียมเทรด Bitkub ~0.25% ต่อครั้ง
DEFAULT_SAVINGS_APY = 0.015       # ออมทรัพย์สมมติ 1.5% ต่อปี
PAIN_REFERENCE_THB = 100_000.0    # เงินสมมติสำหรับ "Pain meter"
WARMUP_DAYS = 400                 # ดึงข้อมูลย้อนก่อนวันเริ่มไว้คำนวณเส้นค่าเฉลี่ย ฯลฯ

STRATEGIES: dict[str, dict[str, str]] = {
    "lump": {
        "label": "💰 ซื้อทีเดียวแล้วถือ",
        "desc": "ซื้อทั้งก้อนวันแรก แล้วไม่ทำอะไรเลย",
    },
    "dca": {
        "label": "📅 ทยอยซื้อสม่ำเสมอ (DCA)",
        "desc": "ซื้อเท่าๆ กันทุกรอบ ไม่ต้องเดาจังหวะ",
    },
    "dip": {
        "label": "📉 ซื้อเพิ่มตอนราคาตก",
        "desc": "รอเงินสดไว้ แล้วทยอยซื้อเมื่อราคาตกจากจุดสูงสุดล่าสุดตามที่กำหนด",
    },
    "trend": {
        "label": "📈 ตามเทรนด์ (เส้นค่าเฉลี่ย)",
        "desc": "ถือเมื่อราคาเหนือเส้นค่าเฉลี่ย ขายออกเมื่อหลุดเส้น แล้วรอซื้อใหม่",
    },
}
FREQS = {"รายวัน": "D", "รายสัปดาห์": "W", "รายเดือน": "M"}


def default_params(strategy: str) -> dict[str, Any]:
    base: dict[str, Any] = {"amount": 100_000.0}
    if strategy == "dca":
        base.update(amount=1_000.0, freq="M")
    elif strategy == "dip":
        base.update(drop_pct=20.0, lookback=90, chunk_pct=25.0, cooldown=7)
    elif strategy == "trend":
        base.update(ma_window=200)
    return base


def dca_schedule(index: pd.DatetimeIndex, freq: str) -> set[int]:
    """ตำแหน่ง (positional) ของวันที่ต้องซื้อ DCA ภายใน index ที่ให้มา"""
    idx = pd.DatetimeIndex(index)
    if freq == "D":
        return set(range(len(idx)))
    out: set[int] = set()
    if freq == "W":
        last = None
        for i, d in enumerate(idx):
            if last is None or (d - last).days >= 7:
                out.add(i)
                last = d
        return out
    seen: set[tuple[int, int]] = set()          # "M"
    for i, d in enumerate(idx):
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            out.add(i)
    return out


def build_indicators(prices: pd.Series, strategy: str, params: dict[str, Any]) -> dict[str, np.ndarray]:
    """คำนวณสัญญาณบนราคาเต็ม (รวม warm-up) — ทุกค่า shift(1) เพื่อกัน look-ahead"""
    ind: dict[str, np.ndarray] = {}
    if strategy == "trend":
        w = int(params["ma_window"])
        ma = prices.rolling(w).mean()
        sig = (prices > ma) & ma.notna()
        ind["sig"] = sig.shift(1, fill_value=False).to_numpy(bool)
    elif strategy == "dip":
        lb = int(params["lookback"])
        high = prices.rolling(lb, min_periods=lb).max().shift(1)
        ind["high"] = high.to_numpy(float)
    return ind


def min_start_pos(strategy: str, params: dict[str, Any]) -> int:
    """วันแรกที่ 'ควร' เริ่มได้ (ต้องมีข้อมูล warm-up พอ)"""
    if strategy == "trend":
        return int(params["ma_window"]) + 1
    if strategy == "dip":
        return int(params["lookback"]) + 1
    return 0


def simulate(prices: pd.Series, i0: int, i1: int, strategy: str, params: dict[str, Any],
             ind: dict[str, np.ndarray], fee: float = DEFAULT_FEE_PCT, spread: float = 0.0,
             cash_apy: float = 0.0, record: bool = True) -> dict[str, Any]:
    """จำลองการลงทุนตั้งแต่ตำแหน่ง i0 ถึง i1 (รวมปลาย) บนราคา THB

    คืน dict: dates, value, invested, contrib, twr, trades, cost_thb, final_liquid, ...
    - value        มูลค่าพอร์ตรายวัน (ราคากลาง)
    - invested     เงินที่ใส่สะสม
    - twr          ดัชนีผลตอบแทนถ่วงเวลา (ไม่ถูกบิดเบือนจากการเติมเงิน) ใช้คำนวณ max drawdown
    - final_liquid มูลค่าถ้าขายทุกอย่างวันสุดท้าย หักค่าธรรมเนียม+spread แล้ว
    """
    p_arr = prices.to_numpy(float)
    idx = prices.index
    n = i1 - i0 + 1
    if n < 2:
        raise ValueError("ช่วงเวลาสั้นเกินไปสำหรับ backtest")
    amount = float(params["amount"])
    g_day = (1.0 + cash_apy) ** (1.0 / 365.0)
    sched = dca_schedule(idx[i0:i1 + 1], params.get("freq", "M")) if strategy == "dca" else set()

    value = np.zeros(n)
    invested = np.zeros(n)
    contrib = np.zeros(n)
    twr = np.ones(n)
    trades: list[tuple[Any, str, float, float]] = []
    cash = coins = cum = cost = 0.0
    prev_post, level, last_buy_k = 0.0, 1.0, -10**9
    n_buys = n_sells = 0

    def buy(spend: float, p: float) -> float:
        got = spend * (1.0 - fee) / (p * (1.0 + spread))
        return got, spend - got * p          # (coins, cost_thb)

    for k in range(n):
        i = i0 + k
        p = p_arr[i]
        if k > 0 and cash_apy:
            cash *= g_day ** (idx[i] - idx[i - 1]).days
        e_pre = coins * p + cash
        if k > 0 and prev_post > 0:
            level *= e_pre / prev_post
        twr[k] = level

        # 1) เติมเงิน
        c = 0.0
        if strategy == "dca":
            c = amount if k in sched else 0.0
        elif k == 0:
            c = amount
        cash += c
        cum += c
        contrib[k] = c

        # 2) ตัดสินใจซื้อ/ขาย
        spend = 0.0
        if strategy in ("lump", "dca"):
            spend = cash
        elif strategy == "dip":
            h = ind["high"][i]
            if (not math.isnan(h) and p <= h * (1.0 - params["drop_pct"] / 100.0)
                    and k - last_buy_k >= int(params["cooldown"])):
                spend = min(cash, amount * params["chunk_pct"] / 100.0)
        elif strategy == "trend":
            if ind["sig"][i]:
                spend = cash
            elif coins > 0:
                proceeds = coins * p * (1.0 - spread) * (1.0 - fee)
                cost += coins * p - proceeds
                if record:
                    trades.append((idx[i], "ขาย", proceeds, p))
                cash += proceeds
                coins = 0.0
                n_sells += 1

        if spend > 1e-9:
            got, cst = buy(spend, p)
            coins += got
            cash -= spend
            cost += cst
            last_buy_k = k
            n_buys += 1
            if record:
                trades.append((idx[i], "ซื้อ", spend, p))

        prev_post = coins * p + cash
        value[k] = prev_post
        invested[k] = cum

    p_last = p_arr[i1]
    final_liquid = cash + coins * p_last * (1.0 - spread) * (1.0 - fee)
    dates = idx[i0:i1 + 1]
    return {
        "dates": dates, "value": value, "invested": invested, "contrib": contrib, "twr": twr,
        "trades": pd.DataFrame(trades, columns=["วันที่", "ฝั่ง", "จำนวนเงิน (THB)", "ราคา (THB)"]) if record else None,
        "cost_thb": cost, "n_buys": n_buys, "n_sells": n_sells,
        "final_liquid": final_liquid, "total_invested": cum,
        "coins": coins, "cash": cash, "p_last": p_last,
    }


def _xirr(flows: list[tuple[pd.Timestamp, float]]) -> Optional[float]:
    """ผลตอบแทนต่อปีแบบ money-weighted (bisection) — None ถ้าคำนวณไม่ได้/สั้นเกิน"""
    if len(flows) < 2:
        return None
    t0 = flows[0][0]
    span = (flows[-1][0] - t0).days
    if span < 60:
        return None
    ts = np.array([(d - t0).days / 365.0 for d, _ in flows])
    cf = np.array([v for _, v in flows])

    def npv(r: float) -> float:
        return float(np.sum(cf / (1.0 + r) ** ts))

    lo, hi = -0.99, 50.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def _longest_run(mask: np.ndarray) -> int:
    best = run = 0
    for m in mask:
        run = run + 1 if m else 0
        best = max(best, run)
    return best


def savings_curve(dates: pd.DatetimeIndex, contrib: np.ndarray, apy: float) -> np.ndarray:
    """ถ้าเอาเงินก้อนเดียวกัน (เติมวันเดียวกัน) ไปฝากออมทรัพย์"""
    out = np.zeros(len(contrib))
    v = 0.0
    for k in range(len(contrib)):
        if k > 0:
            v *= (1.0 + apy) ** ((dates[k] - dates[k - 1]).days / 365.0)
        v += contrib[k]
        out[k] = v
    return out


def hold_curve(prices: pd.Series, dates: pd.DatetimeIndex, total: float,
               fee: float, spread: float) -> tuple[np.ndarray, float]:
    """ถ้าเอาเงินรวมทั้งหมดซื้อวันแรกแล้วถือเฉยๆ → (มูลค่ารายวัน, มูลค่าขายสุทธิวันสุดท้าย)"""
    p = prices.reindex(dates).to_numpy(float)
    coins = total * (1.0 - fee) / (p[0] * (1.0 + spread))
    return coins * p, coins * p[-1] * (1.0 - spread) * (1.0 - fee)


def summarize(sim: dict[str, Any], pain_ref: float = PAIN_REFERENCE_THB) -> dict[str, Any]:
    inv, fin = sim["total_invested"], sim["final_liquid"]
    profit = fin - inv
    twr = sim["twr"]
    mdd = float((twr / np.maximum.accumulate(twr) - 1.0).min())
    # ความเจ็บแบบคนทั่วไป: พอร์ตติดลบเทียบ "เงินที่ใส่จริง" ณ จุดแย่สุด / ติดลบต่อเนื่องนานสุด
    ratio = sim["value"] / np.maximum(sim["invested"], 1e-9)
    worst = float(ratio.min() - 1.0)
    underwater = _longest_run(ratio < 0.99)     # เผื่อ 1% กันเสียงรบกวนจาก fee วันแรก
    flows = [(d, -c) for d, c in zip(sim["dates"], sim["contrib"]) if c > 0]
    flows.append((sim["dates"][-1], fin))
    return {
        "invested": inv, "final": fin, "profit": profit,
        "return_pct": profit / inv * 100.0 if inv > 0 else 0.0,
        "xirr_pct": (lambda x: None if x is None else x * 100.0)(_xirr(flows)),
        "max_dd_pct": mdd * 100.0,                 # peak-to-trough ของตัวสินทรัพย์/พอร์ต (เทคนิค)
        "worst_loss_pct": worst * 100.0,           # ติดลบหนักสุดเทียบเงินที่ใส่
        "pain_left": pain_ref * (1.0 + worst),
        "underwater_days": underwater,
        "cost_thb": sim["cost_thb"], "n_buys": sim["n_buys"], "n_sells": sim["n_sells"],
        "days": len(sim["dates"]),
    }


def run_backtest(prices: pd.Series, start: Any, end: Any, strategy: str, params: dict[str, Any],
                 fee: float = DEFAULT_FEE_PCT, spread: float = 0.0,
                 savings_apy: float = DEFAULT_SAVINGS_APY, cash_earns_savings: bool = False,
                 ) -> dict[str, Any]:
    """เอนจินหลัก: รัน 1 กลยุทธ์ + benchmark ทั้ง 2 ตัว คืนทุกอย่างที่ UI ต้องใช้"""
    prices = prices[~prices.index.duplicated(keep="last")].sort_index().dropna()
    prices = prices[prices > 0]
    i0 = int(prices.index.searchsorted(pd.Timestamp(start)))
    i1 = int(prices.index.searchsorted(pd.Timestamp(end), side="right")) - 1
    if i1 - i0 < 2:
        raise ValueError("ไม่มีข้อมูลราคาในช่วงที่เลือก")
    ms = min_start_pos(strategy, params)
    warmup_short = i0 < ms
    if warmup_short:
        i0 = ms
        if i1 - i0 < 2:
            raise ValueError("ข้อมูลไม่พอสำหรับ warm-up ของกลยุทธ์นี้ — ลองเลื่อนวันเริ่มให้ช้าลงหรือปรับพารามิเตอร์")

    ind = build_indicators(prices, strategy, params)
    cash_apy = savings_apy if cash_earns_savings else 0.0
    sim = simulate(prices, i0, i1, strategy, params, ind, fee, spread, cash_apy)
    dates = sim["dates"]
    sav = savings_curve(dates, sim["contrib"], savings_apy)
    hold_val, hold_final = hold_curve(prices, dates, sim["total_invested"], fee, spread)
    inv = sim["total_invested"]
    return {
        "sim": sim, "stats": summarize(sim),
        "savings": {"curve": sav, "final": float(sav[-1]),
                    "return_pct": (float(sav[-1]) / inv - 1.0) * 100.0},
        "hold": {"curve": hold_val, "final": hold_final,
                 "return_pct": (hold_final / inv - 1.0) * 100.0},
        "start_used": dates[0], "end_used": dates[-1], "warmup_short": warmup_short,
        "prices": prices.loc[dates],
    }


def rolling_start_analysis(prices: pd.Series, strategy: str, params: dict[str, Any],
                           first_start: Any, last_end: Any, horizon_days: int, step_days: int = 7,
                           fee: float = DEFAULT_FEE_PCT, spread: float = 0.0,
                           savings_apy: float = DEFAULT_SAVINGS_APY) -> pd.DataFrame:
    """Time Machine: ลองเริ่มทุกๆ step_days วัน ถือ horizon_days วัน แล้วดูการกระจายของผล"""
    prices = prices[~prices.index.duplicated(keep="last")].sort_index().dropna()
    prices = prices[prices > 0]
    ind = build_indicators(prices, strategy, params)
    lo = max(int(prices.index.searchsorted(pd.Timestamp(first_start))), min_start_pos(strategy, params))
    hi_end = int(prices.index.searchsorted(pd.Timestamp(last_end), side="right")) - 1
    rows = []
    i = lo
    while i + horizon_days <= hi_end:
        sim = simulate(prices, i, i + horizon_days, strategy, params, ind, fee, spread, record=False)
        inv, fin = sim["total_invested"], sim["final_liquid"]
        sav = float(savings_curve(sim["dates"], sim["contrib"], savings_apy)[-1])
        rows.append({"start": prices.index[i], "return_pct": (fin / inv - 1.0) * 100.0,
                     "profit": fin - inv, "beat_savings": fin > sav})
        i += max(1, int(step_days))
    return pd.DataFrame(rows)


def time_machine_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}
    r = df["return_pct"]
    return {
        "n": len(df), "win_rate": float((r > 0).mean() * 100.0),
        "beat_savings_rate": float(df["beat_savings"].mean() * 100.0),
        "median": float(r.median()), "worst": float(r.min()), "best": float(r.max()),
        "p10": float(np.percentile(r, 10)), "p90": float(np.percentile(r, 90)),
        "worst_start": df.loc[r.idxmin(), "start"], "best_start": df.loc[r.idxmax(), "start"],
    }


def plain_verdicts(res: dict[str, Any], asset: str) -> list[tuple[str, str]]:
    """สรุปผลเป็นภาษาคน: [(level, text)] level ∈ ok / warn / info"""
    s, sv, hd = res["stats"], res["savings"], res["hold"]
    out: list[tuple[str, str]] = []
    if s["profit"] >= 0:
        out.append(("ok", f"เงินที่ใส่ {s['invested']:,.0f} บาท ขายวันนี้ได้สุทธิ {s['final']:,.0f} บาท "
                          f"(กำไร {s['profit']:,.0f} บาท, {s['return_pct']:+.1f}%)"))
    else:
        out.append(("warn", f"เงินที่ใส่ {s['invested']:,.0f} บาท ขายวันนี้ได้สุทธิ {s['final']:,.0f} บาท "
                            f"(ขาดทุน {abs(s['profit']):,.0f} บาท, {s['return_pct']:+.1f}%)"))
    d_sav = s["final"] - sv["final"]
    out.append(("ok" if d_sav >= 0 else "warn",
                f"เทียบกับฝากออมทรัพย์: {'ชนะ' if d_sav >= 0 else 'แพ้'} {abs(d_sav):,.0f} บาท"))
    d_hold = s["final"] - hd["final"]
    if abs(d_hold) > 1:
        out.append(("info", f"เทียบกับซื้อ {asset} ทีเดียวถือเฉยๆ ด้วยเงินก้อนเดียวกัน: "
                            f"{'ดีกว่า' if d_hold >= 0 else 'แย่กว่า'} {abs(d_hold):,.0f} บาท"))
    out.append(("info", f"ค่าธรรมเนียม/spread ที่จ่ายไปตลอดช่วงนี้ ~{s['cost_thb']:,.0f} บาท "
                        f"({s['n_buys']} ครั้งซื้อ, {s['n_sells']} ครั้งขาย)"))
    return out


# =========================================================================
# LAYER 2 — DATA
# =========================================================================

DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LINK", "XLM", "HBAR", "USDT", "USDC"]
FetchFn = Callable[..., "tuple[pd.DataFrame, Optional[str]]"]
_HOST_FETCH: Optional[FetchFn] = None       # ถูกตั้งโดย render_simple_backtest(fetch_fn=...)


def _flatten(d: pd.DataFrame) -> pd.DataFrame:
    if isinstance(d.columns, pd.MultiIndex):
        d = d.copy()
        d.columns = d.columns.get_level_values(0)
    d = d.copy()
    d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
    return d[~d.index.duplicated(keep="last")]


def _default_fetch(ticker: str, start: Any, end: Any) -> tuple[pd.DataFrame, Optional[str]]:
    """fallback เมื่อไม่ได้ส่ง fetch_fn จากแอปหลัก: yfinance ราคา USD × USDTHB"""
    try:
        import yfinance as yf
        end_incl = pd.Timestamp(end) + pd.Timedelta(days=1)
        raw = yf.download(f"{ticker}-USD", start=start, end=end_incl, auto_adjust=False, progress=False)
        fx = yf.download("THB=X", start=start, end=end_incl, auto_adjust=False, progress=False)
    except Exception as e:  # noqa: BLE001
        return pd.DataFrame(), f"ดึงข้อมูลไม่สำเร็จ: {e}"
    if raw is None or raw.empty:
        return pd.DataFrame(), f"ไม่พบข้อมูลราคาของ {ticker}"
    if fx is None or fx.empty:
        return pd.DataFrame(), "ไม่พบข้อมูลเรท USD/THB"
    raw, fx = _flatten(raw), _flatten(fx)
    df = pd.DataFrame({"Global_USD": raw["Close"]})
    df["USDTHB"] = fx["Close"].reindex(df.index).ffill().bfill()
    return df.dropna(), None


def load_thb_prices(asset: str, start: Any, end: Any, premium: float = 0.0,
                    fetch_fn: Optional[FetchFn] = None) -> tuple[Optional[pd.Series], Optional[str]]:
    """ราคา THB รายวัน = USD × USDTHB × (1+premium) — ดึงย้อน warm-up ก่อนวันเริ่มให้ด้วย"""
    fn = fetch_fn or _default_fetch
    s0 = (pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)).date()
    df, err = fn(asset, s0, end)
    if err or df is None or df.empty:
        return None, err or "ไม่พบข้อมูล"
    px = (df["Global_USD"].astype(float) * df["USDTHB"].astype(float) * (1.0 + premium)).dropna()
    return px.rename(f"{asset}_THB"), None


# =========================================================================
# LAYER 3 — UI (Streamlit)
# =========================================================================

def _cached_prices(asset: str, start_s: str, end_s: str, premium: float) -> tuple[Optional[pd.Series], Optional[str]]:
    return load_thb_prices(asset, start_s, end_s, premium, fetch_fn=_HOST_FETCH)


def _get_cached_loader():
    import streamlit as st
    return st.cache_data(ttl=1800, show_spinner=False)(_cached_prices)


def _thai_date(d: pd.Timestamp) -> str:
    months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    return f"{d.day} {months[d.month - 1]} {d.year + 543}"


def _sentence(asset: str, strategy: str, params: dict[str, Any], start: date) -> str:
    when = f"ตั้งแต่ {_thai_date(pd.Timestamp(start))}"
    a = f"{params['amount']:,.0f} บาท"
    if strategy == "lump":
        return f"ถ้าฉัน **ซื้อ {asset} ทีเดียว {a}** {when} แล้วถือเฉยๆ…"
    if strategy == "dca":
        fr = {"D": "ทุกวัน", "W": "ทุกสัปดาห์", "M": "ทุกเดือน"}[params["freq"]]
        return f"ถ้าฉัน **ซื้อ {asset} ครั้งละ {a} {fr}** {when}…"
    if strategy == "dip":
        return (f"ถ้าฉันมีเงิน {a} รอไว้ แล้ว **ซื้อ {asset} เพิ่มทุกครั้งที่ราคาตก {params['drop_pct']:.0f}%** "
                f"จากจุดสูงสุด {params['lookback']} วัน {when}…")
    return (f"ถ้าฉัน **ถือ {asset} เมื่อราคาอยู่เหนือเส้นค่าเฉลี่ย {params['ma_window']} วัน "
            f"และขายเมื่อหลุดเส้น** ด้วยเงิน {a} {when}…")


def _card(st, label: str, value: str, sub: str = "", tone: str = "neutral") -> None:
    color = {"good": "#0ecb81", "bad": "#f6465d", "neutral": "#eaecef"}[tone]
    st.markdown(
        f"<div style='background:#1e2329;border:1px solid #2b3139;border-radius:12px;padding:14px 16px;'>"
        f"<div style='color:#848e9c;font-size:.8rem'>{label}</div>"
        f"<div style='color:{color};font-size:1.6rem;font-weight:700;line-height:1.3'>{value}</div>"
        f"<div style='color:#848e9c;font-size:.78rem'>{sub}</div></div>",
        unsafe_allow_html=True)


def _equity_chart(go, res: dict[str, Any], asset: str):
    sim = res["sim"]
    x = sim["dates"]
    fig = go.Figure()
    fig.add_scatter(x=x, y=sim["value"], name="พอร์ตของฉัน", line=dict(color="#f0b90b", width=3))
    fig.add_scatter(x=x, y=res["hold"]["curve"], name=f"ซื้อ {asset} ทีเดียวถือเฉยๆ",
                    line=dict(color="#5b8def", width=1.6, dash="dot"))
    fig.add_scatter(x=x, y=res["savings"]["curve"], name="ฝากออมทรัพย์",
                    line=dict(color="#0ecb81", width=1.6, dash="dash"))
    fig.add_scatter(x=x, y=sim["invested"], name="เงินที่ใส่", line=dict(color="#848e9c", width=1.2, shape="hv"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=420, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      yaxis_title="บาท", legend=dict(orientation="h", y=1.1))
    return fig


def _render_time_machine(st, go, prices: pd.Series, strategy: str, params: dict[str, Any], start: date,
                         end: date, fee: float, spread: float, apy: float) -> None:
    c1, c2 = st.columns(2)
    horizon_m = c1.select_slider("ถือนานเท่าไหร่", options=[3, 6, 12, 24, 36], value=12,
                                 format_func=lambda m: f"{m} เดือน", key="sb_tm_h")
    step = c2.select_slider("ลองเริ่มทุกๆ", options=[3, 7, 14, 30], value=7,
                            format_func=lambda d: f"{d} วัน", key="sb_tm_s")
    horizon_days = int(horizon_m * 30.4)
    first = max(pd.Timestamp(start), prices.index.min())
    with st.spinner("กำลังลองเริ่มจากหลายๆ วัน…"):
        df = rolling_start_analysis(prices, strategy, params, first, end, horizon_days, step, fee, spread, apy)
    if df.empty:
        st.info("ช่วงข้อมูลสั้นกว่าระยะเวลาถือ — ลองขยายวันเริ่มให้เก่าขึ้นหรือลดระยะเวลาถือ")
        return
    s = time_machine_summary(df)
    a, b, c, d = st.columns(4)
    with a:
        _card(st, "โอกาสได้กำไร", f"{s['win_rate']:.0f}%", f"จาก {s['n']} วันเริ่มที่ลอง",
              "good" if s["win_rate"] >= 50 else "bad")
    with b:
        _card(st, "ผลกลางๆ (median)", f"{s['median']:+.1f}%", f"ถือ {horizon_m} เดือน",
              "good" if s["median"] >= 0 else "bad")
    with c:
        _card(st, "โชคร้ายสุด", f"{s['worst']:+.1f}%", f"เริ่ม {_thai_date(s['worst_start'])}", "bad")
    with d:
        _card(st, "โชคดีสุด", f"{s['best']:+.1f}%", f"เริ่ม {_thai_date(s['best_start'])}", "good")
    st.caption(f"ชนะฝากออมทรัพย์ในสัดส่วน {s['beat_savings_rate']:.0f}% ของวันเริ่มที่ลอง · "
               f"80% ของผลอยู่ระหว่าง {s['p10']:+.0f}% ถึง {s['p90']:+.0f}%")

    fig = go.Figure()
    fig.add_scatter(x=df["start"], y=df["return_pct"], mode="lines", line=dict(color="#f0b90b", width=2),
                    name="ผลตอบแทน %")
    fig.add_hline(y=0, line_color="#848e9c", line_dash="dot")
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=300, margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_title="วันที่เริ่มลงทุน", yaxis_title=f"ผลตอบแทนถือ {horizon_m} เดือน (%)")
    st.plotly_chart(fig, use_container_width=True)

    if len(df) >= 12:
        t = df.assign(y=df["start"].dt.year, m=df["start"].dt.month)
        pv = t.pivot_table(index="y", columns="m", values="return_pct", aggfunc="median")
        hm = go.Figure(go.Heatmap(z=pv.values, x=[f"{m}" for m in pv.columns], y=[str(y) for y in pv.index],
                                  colorscale="RdYlGn", zmid=0, colorbar=dict(title="%")))
        hm.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", height=280,
                         margin=dict(l=10, r=10, t=30, b=10), xaxis_title="เดือนที่เริ่ม (1–12)", yaxis_title="ปี",
                         title=f"ผลตอบแทน (%) ถ้าเริ่มเดือนนี้แล้วถือ {horizon_m} เดือน")
        st.plotly_chart(hm, use_container_width=True)


def render_simple_backtest(fetch_fn: Optional[FetchFn] = None, assets: Optional[list[str]] = None,
                           fee_pct: float = DEFAULT_FEE_PCT, premium: float = 0.0,
                           spread_pct: float = 0.0) -> None:
    """วาดหน้า 'ลองลงทุนย้อนหลัง' ทั้งหน้า

    fetch_fn   : ฟังก์ชัน (ticker, start, end) -> (DataFrame[Global_USD, USDTHB], err)
                 ส่ง fetch_price_data ของแอปหลักมาได้ ไม่ส่งก็ใช้ yfinance เอง
    fee_pct    : ค่าธรรมเนียมต่อครั้ง เป็นสัดส่วน (0.0025 = 0.25%)
    premium    : ส่วนต่างราคาไทยเทียบตลาดโลก (0.001 = 0.1%)
    spread_pct : spread ของร้านรับแลก เป็นสัดส่วน (ปกติ 0 สำหรับคนทั่วไป)
    """
    import plotly.graph_objects as go
    import streamlit as st

    global _HOST_FETCH
    _HOST_FETCH = fetch_fn
    load = _get_cached_loader()
    assets = assets or DEFAULT_ASSETS

    st.markdown("## 🎯 ลองลงทุนย้อนหลัง")
    st.caption("ดูว่าถ้าลงทุนแบบนี้ในอดีต ผลจะออกมาเป็นยังไง — ราคาเป็นบาท หักค่าธรรมเนียมแล้ว "
               "และเทียบกับการฝากออมทรัพย์/ถือเฉยๆ ให้เสมอ")

    # ---------- ฟอร์ม ----------
    c1, c2, c3 = st.columns([1, 1, 1])
    asset = c1.selectbox("เหรียญ", assets, key="sb_asset")
    today = date.today()

    # ---------- ช่วงเวลาย้อนหลัง ----------
    # ใช้รูปแบบเดียวกับแท็บ 5-Year Backtest Simulator:
    # เลือกช่วงเวลาด่วนก่อน แล้วค่อยเปิด "กำหนดเอง" หากต้องการระบุวันเอง
    _SB_DATE_UI_VERSION = "2026-09-25-v5-backtest-preset"
    if st.session_state.get("sb_date_ui_version") != _SB_DATE_UI_VERSION:
        for _k in (
            "sb_start", "sb_end", "sb_start_v2", "sb_end_v2",
            "sb_start_v3", "sb_end_v3", "sb_start_v4", "sb_end_v4",
            "sb_start_year", "sb_start_month", "sb_start_day",
            "sb_end_year", "sb_end_month", "sb_end_day",
            "sb_start_date", "sb_end_date", "sb_preset",
        ):
            st.session_state.pop(_k, None)
        st.session_state["sb_date_ui_version"] = _SB_DATE_UI_VERSION

    preset_days = {
        "1 เดือน": 30,
        "3 เดือน": 90,
        "6 เดือน": 180,
        "1 ปี": 365,
        "3 ปี": 365 * 3,
        "5 ปี": 365 * 5,
    }
    preset = st.radio(
        "เลือกช่วงเวลาด่วน",
        ["กำหนดเอง", "1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "3 ปี", "5 ปี"],
        index=6, horizontal=True, key="sb_preset",
    )

    if preset != "กำหนดเอง":
        start = today - timedelta(days=preset_days[preset])
        end = today
    else:
        min_day = date(2015, 1, 1)
        default_start = today - timedelta(days=365 * 5)
        default_end = today
        ca, cb = st.columns(2)
        with ca:
            start = st.date_input(
                "เริ่มต้น", value=default_start, min_value=min_day,
                max_value=today, key="sb_start_date",
            )
        with cb:
            end = st.date_input(
                "สิ้นสุด", value=default_end, min_value=min_day,
                max_value=today, key="sb_end_date",
            )

    if start >= end:
        st.error("❌ วันเริ่มต้นต้องมาก่อนวันสิ้นสุด")
        return

    keys = list(STRATEGIES)
    strategy = st.radio("เลือกวิธีลงทุน", keys, format_func=lambda k: STRATEGIES[k]["label"],
                        horizontal=True, key="sb_strategy")
    st.caption(STRATEGIES[strategy]["desc"])

    params = default_params(strategy)
    p1, p2, p3 = st.columns(3)
    if strategy == "lump":
        params["amount"] = p1.number_input("เงินลงทุน (บาท)", 100.0, 1e9, 100_000.0, 1_000.0, key="sb_amt_lump")
    elif strategy == "dca":
        params["amount"] = p1.number_input("ซื้อครั้งละ (บาท)", 50.0, 1e8, 1_000.0, 100.0, key="sb_amt_dca")
        fr = p2.selectbox("ซื้อทุก", list(FREQS), index=2, key="sb_freq")
        params["freq"] = FREQS[fr]
    elif strategy == "dip":
        params["amount"] = p1.number_input("เงินสดที่เตรียมไว้ (บาท)", 1_000.0, 1e9, 100_000.0, 1_000.0, key="sb_amt_dip")
        params["drop_pct"] = p2.slider("ซื้อเมื่อราคาตกจากจุดสูงสุด (%)", 5, 60, 20, key="sb_drop")
        params["chunk_pct"] = p3.slider("ซื้อครั้งละกี่ % ของเงินสด", 5, 100, 25, key="sb_chunk")
        with st.expander("ตั้งค่าเพิ่มเติม"):
            params["lookback"] = st.slider("จุดสูงสุดนับย้อนหลัง (วัน)", 30, 365, 90, key="sb_lb")
            params["cooldown"] = st.slider("เว้นอย่างน้อยกี่วันระหว่างการซื้อ", 1, 60, 7, key="sb_cd")
    else:
        params["amount"] = p1.number_input("เงินลงทุน (บาท)", 100.0, 1e9, 100_000.0, 1_000.0, key="sb_amt_trend")
        params["ma_window"] = p2.slider("เส้นค่าเฉลี่ย (วัน)", 20, 300, 200, key="sb_ma")

    with st.expander("⚙️ ค่าธรรมเนียมและสมมติฐาน"):
        a1, a2, a3 = st.columns(3)
        with_fee = a1.toggle("รวมค่าธรรมเนียมเทรด", value=True, key="sb_fee_on")
        fee = a1.number_input("ค่าธรรมเนียมต่อครั้ง (%)", 0.0, 5.0, fee_pct * 100.0, 0.05, key="sb_fee",
                              disabled=not with_fee) / 100.0 if with_fee else 0.0
        spread = a2.number_input("Spread ร้านรับแลก (%)", 0.0, 5.0, spread_pct * 100.0, 0.1, key="sb_spread") / 100.0
        apy = a3.number_input("ดอกเบี้ยออมทรัพย์เทียบ (%/ปี)", 0.0, 10.0, DEFAULT_SAVINGS_APY * 100.0, 0.1,
                              key="sb_apy") / 100.0
        cash_sav = a3.toggle("เงินสดที่รอซื้อได้ดอกเบี้ยด้วย", value=False, key="sb_cash_sav")

    st.markdown(_sentence(asset, strategy, params, start))

    # ---------- ข้อมูล + รัน ----------
    with st.spinner(f"กำลังดึงราคา {asset}…"):
        prices, err = load(asset, str(start), str(end), premium)
    if err or prices is None:
        st.error(f"❌ {err or 'ดึงราคาไม่สำเร็จ'}")
        return
    if prices.index.min() > pd.Timestamp(start) + pd.Timedelta(days=5):
        st.info(f"ℹ️ {asset} มีข้อมูลตั้งแต่ {_thai_date(prices.index.min())} เท่านั้น — เริ่มนับจากวันนั้น")

    try:
        res = run_backtest(prices, start, end, strategy, params, fee, spread, apy, cash_sav)
    except ValueError as e:
        st.warning(f"⚠️ {e}")
        return
    if res["warmup_short"]:
        st.info(f"ℹ️ กลยุทธ์นี้ต้องใช้ข้อมูลย้อนหลังก่อนเริ่ม จึงเริ่มจริงวันที่ {_thai_date(res['start_used'])}")

    s = res["stats"]
    tone = "good" if s["profit"] >= 0 else "bad"

    # ---------- ผลลัพธ์ ----------
    st.markdown("### ผลลัพธ์")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        _card(st, "เงินที่ใส่", f"฿{s['invested']:,.0f}", f"{s['days']:,} วัน")
    with m2:
        _card(st, "ขายวันนี้ได้สุทธิ", f"฿{s['final']:,.0f}", "หักค่าธรรมเนียมขายแล้ว", tone)
    with m3:
        _card(st, "กำไร/ขาดทุน", f"{s['return_pct']:+.1f}%", f"฿{s['profit']:+,.0f}", tone)
    with m4:
        _card(st, "เฉลี่ยต่อปี", "—" if s["xirr_pct"] is None else f"{s['xirr_pct']:+.1f}%",
              "ช่วงสั้นเกินคำนวณ" if s["xirr_pct"] is None else "ถ่วงตามวันที่ใส่เงินจริง", tone)

    for lvl, txt in plain_verdicts(res, asset):
        {"ok": st.success, "warn": st.warning, "info": st.info}[lvl](txt)

    st.plotly_chart(_equity_chart(go, res, asset), use_container_width=True)

    # ---------- Pain meter ----------
    st.markdown("### 😰 ทนไหวไหม")
    q1, q2 = st.columns(2)
    with q1:
        _card(st, "ขาดทุนหนักสุดระหว่างทาง", f"{s['worst_loss_pct']:.1f}%",
              f"ถ้าใส่ {PAIN_REFERENCE_THB:,.0f} ณ จุดแย่สุดจะเหลือ ~{s['pain_left']:,.0f} บาท", "bad")
    with q2:
        _card(st, "ติดลบต่อเนื่องนานสุด", f"{s['underwater_days']:,} วัน",
              f"≈ {s['underwater_days'] / 30.4:.1f} เดือน ที่พอร์ตมูลค่าต่ำกว่าเงินที่ใส่", "bad")
    st.caption("ถามตัวเองว่า: ถ้าเห็นตัวเลขนี้จริงในพอร์ต จะยังถือต่อได้ไหม? "
               "ถ้าไม่ไหว ให้ลดเงินลงทุนหรือเลือกวิธีที่ทยอยซื้อ")

    # ---------- ตารางเทียบ ----------
    st.markdown("### เทียบกับทางเลือกอื่น (เงินก้อนเดียวกัน)")
    cmp_df = pd.DataFrame([
        {"ทางเลือก": STRATEGIES[strategy]["label"], "มูลค่าปลายทาง (฿)": s["final"], "กำไร (฿)": s["profit"],
         "ผลตอบแทน (%)": s["return_pct"]},
        {"ทางเลือก": f"ซื้อ {asset} ทีเดียวถือเฉยๆ", "มูลค่าปลายทาง (฿)": res["hold"]["final"],
         "กำไร (฿)": res["hold"]["final"] - s["invested"], "ผลตอบแทน (%)": res["hold"]["return_pct"]},
        {"ทางเลือก": f"ฝากออมทรัพย์ {apy * 100:.1f}%/ปี", "มูลค่าปลายทาง (฿)": res["savings"]["final"],
         "กำไร (฿)": res["savings"]["final"] - s["invested"], "ผลตอบแทน (%)": res["savings"]["return_pct"]},
    ])
    st.dataframe(cmp_df.style.format({"มูลค่าปลายทาง (฿)": "{:,.0f}", "กำไร (฿)": "{:+,.0f}",
                                       "ผลตอบแทน (%)": "{:+.1f}"}),
                 hide_index=True, use_container_width=True)

    trades = res["sim"]["trades"]
    if trades is not None and not trades.empty:
        with st.expander(f"📋 รายการซื้อขายทั้งหมด ({len(trades):,} รายการ)"):
            st.dataframe(trades.style.format({"จำนวนเงิน (THB)": "{:,.0f}", "ราคา (THB)": "{:,.2f}"}),
                         hide_index=True, use_container_width=True)
            st.download_button("⬇️ ดาวน์โหลด CSV", trades.to_csv(index=False).encode("utf-8-sig"),
                               f"simple_backtest_{asset}_{strategy}.csv", "text/csv")

    # ---------- Time Machine ----------
    st.markdown("### ⏳ Time Machine — ถ้าเริ่มคนละวัน ผลต่างกันแค่ไหน")
    st.caption("ผลข้างบนคือ 'เริ่มวันเดียว' ซึ่งอาจโชคดี/โชคร้ายเป็นพิเศษ ลองเริ่มจากหลายๆ วันแล้วดูภาพรวมจะซื่อสัตย์กว่า")
    if st.toggle("เปิด Time Machine", value=False, key="sb_tm_on"):
        _render_time_machine(st, go, prices, strategy, params, start, end, fee, spread, apy)

    # ---------- คำเตือน ----------
    st.markdown("---")
    st.caption(
        "⚠️ ผลในอดีตไม่รับประกันอนาคต · ข้อมูลมีเฉพาะเหรียญที่ยังอยู่รอดถึงวันนี้ (survivorship bias) "
        "ทำให้ภาพรวมดูดีกว่าความจริง · ไม่ได้รวมภาษี ค่าโอน และ slippage ตอนตลาดผันผวนหนัก · "
        f"ใช้เพื่อการเรียนรู้เท่านั้น ไม่ใช่คำแนะนำการลงทุน (Simple Backtest v{SB_VERSION})")


# =========================================================================
# Standalone entry:  streamlit run simple_backtest.py
# =========================================================================

if __name__ == "__main__":
    try:
        import streamlit as st
        st.set_page_config(page_title="ลองลงทุนย้อนหลัง", page_icon="🎯", layout="wide")
        render_simple_backtest()
    except ImportError:
        print("ต้องติดตั้ง streamlit / plotly / yfinance ก่อน:  pip install streamlit plotly yfinance")
