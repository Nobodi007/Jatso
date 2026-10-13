"""
bot_rules.py — ตัวประเมินกฎบอทเทรด (ไม่พึ่ง Streamlit / FastAPI / engine ใดๆ)

หลักการ
  * กลยุทธ์เก็บเป็นข้อมูล (dict/JSON) ไม่ใช่โค้ด  ->  validate_spec() ตรวจแบบ whitelist
  * ตัดสินใจจากข้อมูลถึง "แท่งก่อนหน้า" เท่านั้น (shift 1) แล้วเข้าซื้อ/ขายที่ราคาแท่งปัจจุบัน
    backtest() กับ live_decision() ใช้ decide() ตัวเดียวกัน ผลย้อนหลังจึงตรงกับบอทจริง
  * Spot แบบ long เท่านั้น ถือได้ทีละ 1 ตำแหน่ง (ไม่ซื้อเพิ่ม ไม่ short ไม่ leverage)
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# ขอบเขตที่อนุญาต (whitelist)
# ---------------------------------------------------------------------------
IND_LIMITS = {"sma": (2, 400), "ema": (2, 400), "rsi": (2, 100), "roc": (1, 365)}
OPS = (">", "<", "crosses_above", "crosses_below")
MAX_CONDS = 6
VALUE_MAX = 1e9
LIMITS = {
    "take_profit_pct": (0.5, 1000.0),
    "stop_loss_pct": (0.5, 100.0),
    "pct_of_cash": (1.0, 100.0),
    "fixed_thb": (50.0, 100_000_000.0),
}
MIN_TRADE_THB = 50.0
DEFAULT_FEE = 0.0025  # ตรงกับ LOCAL_TRADING_FEE_PCT ของหน้า Exchange (ปรับได้ตอนเรียก)


class RuleError(ValueError):
    """กฎไม่ถูกต้อง (ข้อความเป็นภาษาไทย แสดงให้ผู้ใช้ได้เลย)"""


# ---------------------------------------------------------------------------
# ตรวจกฎ
# ---------------------------------------------------------------------------
def _num(x: Any, name: str, lo: float, hi: float) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise RuleError(f"{name} ต้องเป็นตัวเลข")
    v = float(x)
    if not math.isfinite(v) or v < lo or v > hi:
        raise RuleError(f"{name} ต้องอยู่ระหว่าง {lo:g} ถึง {hi:g}")
    return v


def _operand(o: Any, where: str) -> dict:
    if not isinstance(o, dict):
        raise RuleError(f"{where}: รูปแบบไม่ถูกต้อง")
    if ("ind" in o) == ("value" in o):
        raise RuleError(f"{where}: ต้องระบุ indicator หรือค่าตัวเลข อย่างใดอย่างหนึ่ง")
    if "value" in o:
        return {"value": _num(o["value"], f"{where} ค่าตัวเลข", -VALUE_MAX, VALUE_MAX)}
    ind = o["ind"]
    if ind == "price":
        return {"ind": "price"}
    if ind not in IND_LIMITS:
        raise RuleError(f"{where}: ไม่รองรับ indicator '{ind}'")
    lo, hi = IND_LIMITS[ind]
    p = o.get("period")
    if isinstance(p, bool) or not isinstance(p, (int, float)) or int(p) != p:
        raise RuleError(f"{where}: period ต้องเป็นจำนวนเต็ม")
    p = int(p)
    if p < lo or p > hi:
        raise RuleError(f"{where}: period ของ {ind} ต้องอยู่ระหว่าง {lo} ถึง {hi}")
    return {"ind": ind, "period": p}


def _group(g: Any, where: str, required: bool) -> dict:
    if g is None:
        g = {}
    if not isinstance(g, dict):
        raise RuleError(f"{where}: รูปแบบไม่ถูกต้อง")
    op = g.get("op", "all")
    if op not in ("all", "any"):
        raise RuleError(f"{where}: op ต้องเป็น all หรือ any")
    conds = g.get("conds", [])
    if not isinstance(conds, list) or len(conds) > MAX_CONDS:
        raise RuleError(f"{where}: ใส่เงื่อนไขได้สูงสุด {MAX_CONDS} ข้อ")
    if required and not conds:
        raise RuleError(f"{where}: ต้องมีเงื่อนไขอย่างน้อย 1 ข้อ")
    clean = []
    for i, c in enumerate(conds, 1):
        tag = f"{where} ข้อ {i}"
        if not isinstance(c, dict):
            raise RuleError(f"{tag}: รูปแบบไม่ถูกต้อง")
        if c.get("op") not in OPS:
            raise RuleError(f"{tag}: ตัวเปรียบเทียบไม่ถูกต้อง")
        left, right = _operand(c.get("left"), f"{tag} ซ้าย"), _operand(c.get("right"), f"{tag} ขวา")
        if "value" in left and "value" in right:
            raise RuleError(f"{tag}: ต้องมี indicator อย่างน้อยหนึ่งฝั่ง")
        clean.append({"left": left, "op": c["op"], "right": right})
    return {"op": op, "conds": clean}


def validate_spec(spec: Any) -> dict:
    """คืนกฎที่ทำความสะอาดแล้ว หรือ raise RuleError"""
    if not isinstance(spec, dict):
        raise RuleError("รูปแบบกลยุทธ์ไม่ถูกต้อง")
    asset = str(spec.get("asset", "")).upper().strip()
    if not re.fullmatch(r"[A-Z0-9]{2,20}", asset):
        raise RuleError("ชื่อเหรียญไม่ถูกต้อง")

    entry = _group(spec.get("entry"), "เงื่อนไขซื้อ", required=True)

    ex_raw = spec.get("exit") or {}
    if not isinstance(ex_raw, dict):
        raise RuleError("เงื่อนไขขาย: รูปแบบไม่ถูกต้อง")
    exit_ = _group(ex_raw, "เงื่อนไขขาย", required=False)
    for key in ("take_profit_pct", "stop_loss_pct"):
        v = ex_raw.get(key)
        exit_[key] = None if v in (None, "") else _num(v, key, *LIMITS[key])
    if not exit_["conds"] and exit_["take_profit_pct"] is None and exit_["stop_loss_pct"] is None:
        raise RuleError("ต้องมีเงื่อนไขขายอย่างน้อย 1 อย่าง (เงื่อนไข, Take-profit หรือ Stop-loss)")

    sz = spec.get("sizing") or {"type": "pct_of_cash", "value": 10}
    if not isinstance(sz, dict) or sz.get("type") not in ("pct_of_cash", "fixed_thb"):
        raise RuleError("ขนาดออเดอร์ไม่ถูกต้อง")
    sizing = {"type": sz["type"], "value": _num(sz.get("value"), "ขนาดออเดอร์", *LIMITS[sz["type"]])}

    return {"asset": asset, "entry": entry, "exit": exit_, "sizing": sizing}


# ---------------------------------------------------------------------------
# Indicator & เงื่อนไข
# ---------------------------------------------------------------------------
def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up, dn = d.clip(lower=0.0), (-d).clip(lower=0.0)
    au = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = au / ad.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    flat = ad == 0.0
    rsi = rsi.where(~flat, np.where(au > 0.0, 100.0, 50.0))
    return rsi.where(au.notna() & ad.notna())


def operand_series(close: pd.Series, o: dict) -> pd.Series:
    if "value" in o:
        return pd.Series(float(o["value"]), index=close.index)
    ind, n = o["ind"], o.get("period")
    if ind == "price":
        return close
    if ind == "sma":
        return close.rolling(n, min_periods=n).mean()
    if ind == "ema":
        return close.ewm(span=n, adjust=False, min_periods=n).mean()
    if ind == "rsi":
        return _rsi(close, n)
    return close.pct_change(n) * 100.0  # roc


def cond_series(close: pd.Series, c: dict) -> pd.Series:
    L, R = operand_series(close, c["left"]), operand_series(close, c["right"])
    op = c["op"]
    if op == ">":
        s = L > R
    elif op == "<":
        s = L < R
    elif op == "crosses_above":
        s = (L > R) & (L.shift(1) <= R.shift(1))
    else:
        s = (L < R) & (L.shift(1) >= R.shift(1))
    return s.fillna(False).astype(bool)


def group_series(close: pd.Series, g: dict) -> pd.Series:
    if not g["conds"]:
        return pd.Series(False, index=close.index)
    parts = [cond_series(close, c).to_numpy() for c in g["conds"]]
    arr = np.logical_and.reduce(parts) if g["op"] == "all" else np.logical_or.reduce(parts)
    return pd.Series(arr, index=close.index)


def signals(close: pd.Series, spec: dict) -> tuple[pd.Series, pd.Series]:
    """(entry, exit) ของแต่ละแท่ง = ผลจากข้อมูลถึงแท่งก่อนหน้า (shift 1) กันเห็นอนาคต"""
    ent = group_series(close, spec["entry"]).shift(1, fill_value=False)
    ex = group_series(close, spec["exit"]).shift(1, fill_value=False)
    return ent.astype(bool), ex.astype(bool)


# ---------------------------------------------------------------------------
# ตัวตัดสินใจ (ใช้ร่วมกันทั้ง backtest และบอทจริง)
# ---------------------------------------------------------------------------
def decide(holding: bool, entry_sig: bool, exit_sig: bool,
           pnl_pct: Optional[float], spec: dict) -> tuple[str, str]:
    """คืน (action, เหตุผล) โดย action = 'buy' | 'sell' | 'hold'"""
    if holding:
        ex = spec["exit"]
        if pnl_pct is not None:
            if ex["stop_loss_pct"] is not None and pnl_pct <= -ex["stop_loss_pct"]:
                return "sell", f"Stop-loss {pnl_pct:+.2f}%"
            if ex["take_profit_pct"] is not None and pnl_pct >= ex["take_profit_pct"]:
                return "sell", f"Take-profit {pnl_pct:+.2f}%"
        if exit_sig:
            return "sell", "เข้าเงื่อนไขขาย"
        return "hold", ""
    if entry_sig:
        return "buy", "เข้าเงื่อนไขซื้อ"
    return "hold", ""


def order_size(spec: dict, cash: float) -> float:
    sz = spec["sizing"]
    amt = cash * sz["value"] / 100.0 if sz["type"] == "pct_of_cash" else min(sz["value"], cash)
    return amt if amt >= MIN_TRADE_THB else 0.0


def position_pnl_pct(coins: float, cost_thb: float, last_mid: float,
                     spread: float, fee: float) -> float:
    """กำไร/ขาดทุนสุทธิถ้าขายตอนนี้ (หักส่วนต่างราคาและค่าธรรมเนียม)"""
    if cost_thb <= 0:
        return 0.0
    return (coins * last_mid * (1.0 - spread) * (1.0 - fee) / cost_thb - 1.0) * 100.0


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def backtest(mid: pd.Series, spec: dict, capital: float,
             spread: float = 0.0, fee: float = DEFAULT_FEE) -> dict:
    """
    mid = ราคากลางเป็นบาทรายแท่ง (Global_USD*USDTHB*(1+premium))  index เป็นวันที่
    ต้นทุนเดียวกับหน้า Exchange: ซื้อที่ mid*(1+spread) ขายที่ mid*(1-spread) และหัก fee ทั้งสองขา
    """
    spec = validate_spec(spec)
    mid = pd.Series(mid).astype(float).dropna()
    if len(mid) < 10:
        raise RuleError("ข้อมูลราคาน้อยกว่า 10 แท่ง ทดสอบย้อนหลังไม่ได้")
    capital = _num(capital, "เงินลงทุน", 100.0, 1e11)

    ent, ex = signals(mid, spec)
    m, e_arr, x_arr = mid.to_numpy(), ent.to_numpy(), ex.to_numpy()
    n = len(m)
    buy_px, sell_px = m * (1.0 + spread), m * (1.0 - spread)

    cash, coins, cost = capital, 0.0, 0.0
    equity = np.zeros(n)
    trades: list[dict] = []

    for i in range(n):
        holding = coins > 0.0
        pnl = position_pnl_pct(coins, cost, m[i - 1], spread, fee) if holding and i >= 1 else None
        action, reason = decide(holding, bool(e_arr[i]), bool(x_arr[i]), pnl, spec)

        if action == "sell":
            proceeds = coins * sell_px[i] * (1.0 - fee)
            trades.append({"date": mid.index[i], "side": "sell", "price": float(sell_px[i]),
                           "amount_thb": float(proceeds), "reason": reason,
                           "pnl_pct": float((proceeds / cost - 1.0) * 100.0)})
            cash, coins, cost = cash + proceeds, 0.0, 0.0
        elif action == "buy":
            amt = order_size(spec, cash)
            if amt > 0.0 and buy_px[i] > 0.0:
                coins = amt * (1.0 - fee) / buy_px[i]
                cash -= amt
                cost = amt
                trades.append({"date": mid.index[i], "side": "buy", "price": float(buy_px[i]),
                               "amount_thb": float(amt), "reason": reason, "pnl_pct": None})

        equity[i] = cash + coins * sell_px[i] * (1.0 - fee)

    eq = pd.Series(equity, index=mid.index)
    max_dd = float(((eq / eq.cummax()) - 1.0).min() * 100.0)
    closed = [t for t in trades if t["side"] == "sell"]
    wins = sum(1 for t in closed if t["pnl_pct"] > 0)
    return {
        "equity": eq,
        "final": float(eq.iloc[-1]),
        "return_pct": float((eq.iloc[-1] / capital - 1.0) * 100.0),
        "max_dd": max_dd,
        "trades": trades,
        "n_trades": len(trades),
        "n_closed": len(closed),
        "win_rate": float(wins / len(closed) * 100.0) if closed else None,
        "holding_at_end": coins > 0.0,
        "cash_left": float(cash),
    }


# ---------------------------------------------------------------------------
# ตัดสินใจสำหรับบอทจริง (แท่งล่าสุดของ mid = ราคาปัจจุบัน)
# ---------------------------------------------------------------------------
def live_decision(mid: pd.Series, spec: dict, position: Optional[dict],
                  spread: float = 0.0, fee: float = DEFAULT_FEE) -> dict:
    """
    position = None (ยังไม่ถือ)  หรือ {"coins": จำนวนเหรียญที่ "บอทตัวนี้" ซื้อ, "cost_thb": เงินที่จ่ายไป}
    คืน {"action", "reason", "bar", "pnl_pct"}  ใช้ตรรกะเดียวกับ backtest ทุกประการ
    """
    spec = validate_spec(spec)
    mid = pd.Series(mid).astype(float).dropna()
    if len(mid) < 3:
        return {"action": "hold", "reason": "ข้อมูลไม่พอ", "bar": None, "pnl_pct": None}
    ent, ex = signals(mid, spec)
    holding = bool(position and position.get("coins", 0.0) > 0.0)
    pnl = None
    if holding:
        pnl = position_pnl_pct(position["coins"], position["cost_thb"], float(mid.iloc[-2]), spread, fee)
    action, reason = decide(holding, bool(ent.iloc[-1]), bool(ex.iloc[-1]), pnl, spec)
    return {"action": action, "reason": reason, "bar": str(mid.index[-1])[:10], "pnl_pct": pnl}


# ---------------------------------------------------------------------------
# แปลงกฎเป็นประโยคภาษาไทย (ไว้แสดงในหน้า UI)
# ---------------------------------------------------------------------------
_OP_TH = {">": "มากกว่า", "<": "น้อยกว่า", "crosses_above": "ตัดขึ้นเหนือ", "crosses_below": "ตัดลงต่ำกว่า"}


def _operand_th(o: dict) -> str:
    if "value" in o:
        return f"{o['value']:g}"
    ind, n = o["ind"], o.get("period")
    return {"price": "ราคา", "sma": f"SMA {n}", "ema": f"EMA {n}",
            "rsi": f"RSI({n})", "roc": f"% เปลี่ยนแปลง {n} แท่ง"}[ind]


def _group_th(g: dict) -> str:
    sep = " และ " if g["op"] == "all" else " หรือ "
    return sep.join(f"{_operand_th(c['left'])} {_OP_TH[c['op']]} {_operand_th(c['right'])}" for c in g["conds"])


def spec_to_text(spec: dict) -> str:
    s = validate_spec(spec)
    sz = s["sizing"]
    size = f"{sz['value']:g}% ของเงินสด" if sz["type"] == "pct_of_cash" else f"{sz['value']:,.0f} บาท"
    ex = s["exit"]
    outs = []
    if ex["conds"]:
        outs.append(_group_th(ex))
    if ex["take_profit_pct"] is not None:
        outs.append(f"กำไรถึง {ex['take_profit_pct']:g}%")
    if ex["stop_loss_pct"] is not None:
        outs.append(f"ขาดทุนถึง {ex['stop_loss_pct']:g}%")
    return f"ซื้อ {s['asset']} {size} เมื่อ {_group_th(s['entry'])}; ขายเมื่อ {' หรือ '.join(outs)}"


# ---------------------------------------------------------------------------
# เทมเพลตสำเร็จรูป
# ---------------------------------------------------------------------------
def _c(left, op, right):
    return {"left": left, "op": op, "right": right}


_P = {"ind": "price"}
_RSI14 = {"ind": "rsi", "period": 14}

TEMPLATES: dict[str, dict] = {
    "oversold_bounce": {
        "name": "Oversold Bounce", "desc": "ซื้อเมื่อ RSI ต่ำกว่า 30 ขายเมื่อ RSI เกิน 70",
        "spec": {"asset": "BTC", "entry": {"op": "all", "conds": [_c(_RSI14, "<", {"value": 30})]},
                 "exit": {"op": "any", "conds": [_c(_RSI14, ">", {"value": 70})], "take_profit_pct": None, "stop_loss_pct": 10},
                 "sizing": {"type": "pct_of_cash", "value": 20}}},
    "golden_cross": {
        "name": "Golden Cross", "desc": "ซื้อเมื่อ EMA 20 ตัดขึ้นเหนือ EMA 50 ขายเมื่อตัดลง",
        "spec": {"asset": "BTC",
                 "entry": {"op": "all", "conds": [_c({"ind": "ema", "period": 20}, "crosses_above", {"ind": "ema", "period": 50})]},
                 "exit": {"op": "any", "conds": [_c({"ind": "ema", "period": 20}, "crosses_below", {"ind": "ema", "period": 50})],
                          "take_profit_pct": None, "stop_loss_pct": 12},
                 "sizing": {"type": "pct_of_cash", "value": 50}}},
    "momentum_breakout": {
        "name": "Momentum Breakout", "desc": "ซื้อเมื่อราคาขึ้นเกิน 10% ใน 20 แท่ง ขายเมื่อโมเมนตัมกลับเป็นลบ",
        "spec": {"asset": "BTC", "entry": {"op": "all", "conds": [_c({"ind": "roc", "period": 20}, ">", {"value": 10})]},
                 "exit": {"op": "any", "conds": [_c({"ind": "roc", "period": 20}, "<", {"value": 0})],
                          "take_profit_pct": 20, "stop_loss_pct": 8},
                 "sizing": {"type": "pct_of_cash", "value": 30}}},
    "buy_the_dip": {
        "name": "Buy the Dip", "desc": "ซื้อเมื่อราคาลงเกิน 10% ใน 7 แท่ง ขายเมื่อกำไร 8% หรือขาดทุน 6%",
        "spec": {"asset": "BTC", "entry": {"op": "all", "conds": [_c({"ind": "roc", "period": 7}, "<", {"value": -10})]},
                 "exit": {"op": "any", "conds": [], "take_profit_pct": 8, "stop_loss_pct": 6},
                 "sizing": {"type": "pct_of_cash", "value": 25}}},
    "trend_filter": {
        "name": "Trend + Filter", "desc": "ซื้อเมื่อราคาอยู่เหนือ SMA 50 และ RSI ไม่เกิน 70 ขายเมื่อราคาหลุด SMA 50",
        "spec": {"asset": "BTC",
                 "entry": {"op": "all", "conds": [_c(_P, ">", {"ind": "sma", "period": 50}), _c(_RSI14, "<", {"value": 70})]},
                 "exit": {"op": "any", "conds": [_c(_P, "<", {"ind": "sma", "period": 50})], "take_profit_pct": None, "stop_loss_pct": 10},
                 "sizing": {"type": "pct_of_cash", "value": 50}}},
}
