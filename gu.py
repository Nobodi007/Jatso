"""
XSpring Dealer Suite — Single-File Build
=========================================
รวม calculation engine + Streamlit UI ไว้ในไฟล์เดียว แต่ยังแยก "ชั้น" ชัดเจน

LAYERS
------
  0. CONFIG & CONSTANTS     ค่าคงที่ของโมเดล (override ได้ด้วย config.yaml)
  1. ENGINE / PURE LOGIC    คณิตศาสตร์ล้วน ไม่แตะ streamlit / network
  2. DATA LAYER             yfinance / cache / CSV export
  3. UI THEME & COMPONENTS  CSS, metric card, timeline, gauge, TradingView
  4. AUDIT TRAIL            log การเปลี่ยนพารามิเตอร์
  5. APP                    sidebar + 4 tabs + AI FAB (อยู่ใน main() ทั้งหมด)
  PHASE 2. CORE BUSINESS VALUE scenario/stress, snapshots, config compare, exports, ratios
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
import copy
import xml.etree.ElementTree as ET
import html as _html
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Optional
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

MODEL_VERSION = "1.7.0"

try:
    import yaml
except ImportError:
    yaml = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import plotly.graph_objects as go
    import streamlit as st
    import streamlit.components.v1 as components
    import yfinance as yf
    HAS_UI = True
except ImportError:
    go = st = components = yf = None
    HAS_UI = False

try:
    _HERE = Path(__file__).resolve().parent
except NameError:
    _HERE = Path.cwd()

HAS_FRAGMENT = bool(HAS_UI and hasattr(st, "fragment"))


def _fragment(fn):
    return st.fragment(fn) if HAS_FRAGMENT else fn


def _rerun_fragment() -> None:
    if HAS_FRAGMENT:
        try:
            st.rerun(scope="fragment")
        except Exception:
            st.rerun()
    else:
        st.rerun()


# =========================================================================
# LAYER 0 — CONFIG & CONSTANTS
# =========================================================================

GLOBAL_EXCHANGE_FEE_PRESET = {
    "Binance": 0.10,
    "Coinbase": 0.60,
    "Kraken": 0.26,
    "OKX": 0.10,
    "กำหนดเอง (Custom)": 0.10,
}
LOCAL_EXCHANGES = ["Bitkub"]

SUPPORTED_ASSETS = [
    "BTC", "ETH", "SOL", "DOGE", "ADA", "HBAR", "LINK", "XLM", "XRP", "USDT", "USDC",
]
STABLECOINS = ["USDT", "USDC"]

COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana",
    "DOGE": "Dogecoin", "ADA": "Cardano", "HBAR": "Hedera",
    "LINK": "Chainlink", "XLM": "Stellar", "XRP": "XRP",
    "USDT": "Tether", "USDC": "USD Coin", "THB": "Thai Baht"
}

# ใช้ Base64 SVG ธงชาติไทยที่ถูกต้อง (แดง-ขาว-น้ำเงิน-ขาว-แดง)
THB_LOGO_SVG = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48Y2xpcFBhdGggaWQ9ImMiPjxjaXJjbGUgY3g9IjUwIiBjeT0iNTAiIHI9IjUwIi8+PC9jbGlwUGF0aD48ZyBjbGlwLXBhdGg9InVybCgjYykiPjxyZWN0IHdpZHRoPSIxMDAiIGhlaWdodD0iMTciIGZpbGw9IiNFRDFDMjQiLz48cmVjdCB5PSIxNyIgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxNyIgZmlsbD0iI2ZmZiIvPjxyZWN0IHk9IjM0IiB3aWR0aD0iMTAwIiBoZWlnaHQ9IjMyIiBmaWxsPSIjMjQxRDRGIi8+PHJlY3QgeT0iNjYiIHdpZHRoPSIxMDAiIGhlaWdodD0iMTciIGZpbGw9IiNmZmYiLz48cmVjdCB5PSI4MyIgd2lkdGg9IjEwMCIgaGVpZ2h0PSIxNyIgZmlsbD0iI0VEMUMyNCIvPjwvZz48L3N2Zz4="

# ข้อมูลผู้พัฒนา (แสดงมุมซ้ายบน)
DEV_NAME = "Thiraphat Niyom"
DEV_LINKEDIN = "https://www.linkedin.com/in/thiraphat-niyom-11044727b"
DEV_AVATAR_B64 = "data:image/jpeg;base64,ใส่_BASE64_ของรูป_IMG_2908_ตรงนี้"

COIN_LOGOS = {s: f"https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/{s.lower()}.png" for s in SUPPORTED_ASSETS}
COIN_LOGOS["THB"] = THB_LOGO_SVG

_LOGO_BG = {"BTC": "#F7931A", "ETH": "#627EEA", "SOL": "#9945FF", "DOGE": "#C2A633",
            "ADA": "#0033AD", "HBAR": "#3a3a3a", "LINK": "#2A5ADA", "XLM": "#14B6E7",
            "XRP": "#23292F", "USDT": "#26A17B", "USDC": "#2775CA"}

LOCAL_TRADING_FEE_PCT = 0.0025
MIN_TRADE_THB = 50.0
WITHDRAWAL_FEE_TABLE = {
    "BTC": 0.00002, "ETH": 0.0004, "ADA": 1.5, "DOGE": 4, "LINK": 0.063,
    "USDT": 4, "XLM": 0.004, "SOL": 0.001, "HBAR": 0.06, "USDC": 1.2, "XRP": 0.2,
}

TV_LOCAL_SYMBOL = {
    "BTC": "BITKUB:BTCTHB", "ETH": "BITKUB:ETHTHB", "SOL": "BITKUB:SOLTHB",
    "DOGE": "BITKUB:DOGETHB", "ADA": "BITKUB:ADATHB", "XRP": "BITKUB:XRPTHB",
    "LINK": "BITKUB:LINKTHB", "XLM": "BITKUB:XLMTHB", "HBAR": "BITKUB:HBARTHB",
    "USDT": "BITKUB:USDTTHB", "USDC": "BITKUB:USDCTHB",
}
TV_GLOBAL_SYMBOL = {a: f"BINANCE:{a}USDT" for a in SUPPORTED_ASSETS}
TV_GLOBAL_SYMBOL["USDT"] = "BINANCE:USDTTRY"
TV_GLOBAL_SYMBOL["USDC"] = "BINANCE:USDCUSDT"

Z_SCORE_MAP = {90: 1.2816, 95: 1.645, 99: 2.326, 99.9: 3.09}

HOT_WALLET_NC_RATE = 1.00
COLD_DOMESTIC_NC_RATE = 0.01
HOT_WALLET_CAP = 0.50
HOT_WALLET_CAP_LIAB_THRESHOLD = 1_000_000_000

FALLBACK_USDTHB = 35.5
MIN_RISK_SAMPLE_DAYS = 30
RISK_SAMPLE_WARN_DAYS = 180

THB_WD_FEE_SCB = 20.0
THB_WD_FEE_OTHER_SMALL = 20.0
THB_WD_FEE_OTHER_LARGE = 70.0
THB_WD_LARGE_THRESHOLD = 2_000_000.0

NC_FIXED_MIN_CUSTODIAN_THB = 25_000_000.0
NC_FIXED_MIN_NON_CUSTODIAN_THB = 5_000_000.0

GLOBAL_EXCHANGE_MAKER_FEE_PRESET: dict[str, float] = {}

UI_DEFAULTS: dict[str, float] = {
    "dealer_spread_pct": 0.5,
    "local_premium_pct": 0.1,
    "fx_limit_usd": 5_000_000.0,
    "impact_penalty_pct": 0.5,
}

FX_PROXY: dict[str, Any] = {
    "enabled": False,
    "url": "",
    "symbol": "USDT_THB",
    "resolution": "1D",
}

class ConfigError(ValueError):
    pass

CONFIG_ENV_VAR = "XSPRING_CONFIG"
DEFAULT_CONFIG_PATH = _HERE / "config.yaml"
CONFIG_INFO: dict[str, Any] = {"source": None, "sha256": None, "applied_keys": []}

_SCALAR_SPECS: dict[str, tuple[str, Optional[float], Optional[float]]] = {
    "local_trading_fee_pct": ("float", 0.0, 0.05),
    "min_trade_thb": ("float", 0.0, None),
    "hot_wallet_nc_rate": ("float", 0.0, 1.0),
    "cold_domestic_nc_rate": ("float", 0.0, 1.0),
    "hot_wallet_cap": ("float", 0.0, 1.0),
    "hot_wallet_cap_liab_threshold": ("float", 0.0, None),
    "fallback_usdthb": ("float", 1.0, None),
    "min_risk_sample_days": ("int", 2, None),
    "risk_sample_warn_days": ("int", 2, None),
    "thb_wd_fee_scb": ("float", 0.0, None),
    "thb_wd_fee_other_small": ("float", 0.0, None),
    "thb_wd_fee_other_large": ("float", 0.0, None),
    "thb_wd_large_threshold": ("float", 0.0, None),
    "nc_fixed_min_custodian_thb": ("float", 0.0, None),
    "nc_fixed_min_non_custodian_thb": ("float", 0.0, None),
}

_MAP_SPECS: dict[str, tuple[float, Optional[float]]] = {
    "global_exchange_fee_preset": (0.0, 100.0),
    "global_exchange_maker_fee_preset": (0.0, 100.0),
    "withdrawal_fee_table": (0.0, None),
}

_UI_DEFAULT_SPECS: dict[str, tuple[float, Optional[float]]] = {
    "dealer_spread_pct": (0.0, 100.0),
    "local_premium_pct": (-100.0, 100.0),
    "fx_limit_usd": (1.0, None),
    "impact_penalty_pct": (0.0, 100.0),
}
_FX_PROXY_KEYS = {"enabled", "url", "symbol", "resolution"}


def _num(name: str, v: Any, kind: str, lo: Optional[float], hi: Optional[float]) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{name}: ต้องเป็นตัวเลข (ได้ {v!r})")
    f = float(v)
    if not math.isfinite(f):
        raise ConfigError(f"{name}: ต้องเป็นตัวเลขจำกัด (ได้ {v!r})")
    if kind == "int" and f != int(f):
        raise ConfigError(f"{name}: ต้องเป็นจำนวนเต็ม (ได้ {v!r})")
    if lo is not None and f < lo:
        raise ConfigError(f"{name}: ต้อง >= {lo} (ได้ {v!r})")
    if hi is not None and f > hi:
        raise ConfigError(f"{name}: ต้อง <= {hi} (ได้ {v!r})")
    return int(f) if kind == "int" else f

def validate_config(doc: Mapping[str, Any]) -> dict[str, Any]:
    valid_keys = (set(_SCALAR_SPECS) | set(_MAP_SPECS) | {"ui_defaults", "fx_proxy"})
    unknown = sorted(set(doc) - valid_keys)
    if unknown:
        raise ConfigError(f"key ที่ไม่รู้จักใน config: {unknown} — key ที่ใช้ได้: {sorted(valid_keys)}")

    out: dict[str, Any] = {}
    for key, (kind, lo, hi) in _SCALAR_SPECS.items():
        if key in doc:
            out[key] = _num(key, doc[key], kind, lo, hi)

    for key, (lo, hi) in _MAP_SPECS.items():
        if key in doc:
            m = doc[key]
            if not isinstance(m, Mapping) or not m:
                raise ConfigError(f"{key}: ต้องเป็น map ที่ไม่ว่าง")
            out[key] = {str(k): _num(f"{key}.{k}", v, "float", lo, hi) for k, v in m.items()}

    if "ui_defaults" in doc:
        u = doc["ui_defaults"]
        if not isinstance(u, Mapping):
            raise ConfigError("ui_defaults: ต้องเป็น map")
        bad = sorted(set(u) - set(_UI_DEFAULT_SPECS))
        if bad:
            raise ConfigError(f"ui_defaults: key ไม่รู้จัก {bad} — ใช้ได้: {sorted(_UI_DEFAULT_SPECS)}")
        out["ui_defaults"] = {k: _num(f"ui_defaults.{k}", v, "float", *_UI_DEFAULT_SPECS[k]) for k, v in u.items()}

    if "fx_proxy" in doc:
        f = doc["fx_proxy"]
        if not isinstance(f, Mapping):
            raise ConfigError("fx_proxy: ต้องเป็น map")
        bad = sorted(set(f) - _FX_PROXY_KEYS)
        if bad:
            raise ConfigError(f"fx_proxy: key ไม่รู้จัก {bad} — ใช้ได้: {sorted(_FX_PROXY_KEYS)}")
        fx: dict[str, Any] = {}
        if "enabled" in f:
            if not isinstance(f["enabled"], bool):
                raise ConfigError("fx_proxy.enabled: ต้องเป็น true/false")
            fx["enabled"] = f["enabled"]
        for k in ("url", "symbol", "resolution"):
            if k in f:
                if not isinstance(f[k], str):
                    raise ConfigError(f"fx_proxy.{k}: ต้องเป็นข้อความ")
                fx[k] = f[k].strip()
        if fx.get("url") and not fx["url"].lower().startswith("https://"):
            raise ConfigError("fx_proxy.url: ต้องขึ้นต้นด้วย https://")
        if fx.get("enabled") and not (fx.get("url") or FX_PROXY["url"]):
            raise ConfigError("fx_proxy.enabled = true แต่ยังไม่ได้ระบุ fx_proxy.url")
        out["fx_proxy"] = fx

    lo_d = out.get("min_risk_sample_days", MIN_RISK_SAMPLE_DAYS)
    hi_d = out.get("risk_sample_warn_days", RISK_SAMPLE_WARN_DAYS)
    if hi_d < lo_d:
        raise ConfigError("risk_sample_warn_days ต้อง >= min_risk_sample_days")
    return out

def apply_config(overrides: Mapping[str, Any]) -> None:
    g = globals()
    for key in _SCALAR_SPECS:
        if key in overrides:
            g[key.upper()] = overrides[key]
    for key in _MAP_SPECS:
        if key in overrides:
            g[key.upper()].update(overrides[key])
    UI_DEFAULTS.update(overrides.get("ui_defaults", {}))
    FX_PROXY.update(overrides.get("fx_proxy", {}))

def load_external_config(path: Optional[str] = None) -> tuple[dict[str, Any], Optional[Path], Optional[str]]:
    explicit = path or os.environ.get(CONFIG_ENV_VAR)
    p = Path(explicit) if explicit else DEFAULT_CONFIG_PATH
    if not p.is_file():
        if explicit:
            raise ConfigError(f"ไม่พบไฟล์ config: {p}")
        return {}, None, None
    if yaml is None:
        raise ConfigError(f"พบ {p.name} แต่ยังไม่ได้ติดตั้ง PyYAML — pip install pyyaml")
    raw = p.read_bytes()
    try:
        doc = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"อ่าน {p.name} ไม่ได้ (YAML ผิดรูปแบบ): {e}") from e
    if not isinstance(doc, dict):
        raise ConfigError(f"{p.name}: ระดับบนสุดต้องเป็น map")
    return validate_config(doc), p, hashlib.sha256(raw).hexdigest()[:12]

def _bootstrap_config() -> None:
    overrides, path, sha = load_external_config()
    apply_config(overrides)
    CONFIG_INFO.update(source=str(path) if path else None, sha256=sha,
                       applied_keys=sorted(overrides))

_bootstrap_config()


# =========================================================================
# LAYER 1 — ENGINE / PURE LOGIC
# =========================================================================

def fmt_num(value: Any, force_sign: bool = False) -> str:
    value = 0.0 if pd.isna(value) else float(value)
    sign = "- " if value < 0 else ("+ " if force_sign else "")
    v = abs(value)
    if v >= 1_000_000_000:
        num = f"{v / 1_000_000_000:,.2f}B"
    elif v >= 1_000_000:
        num = f"{v / 1_000_000:,.2f}M"
    elif v >= 1_000:
        num = f"{v / 1_000:,.1f}K"
    else:
        num = f"{v:,.2f}"
    return f"{sign}{num}"

def fmt_baht(value: Any, force_sign: bool = False) -> str:
    return f"฿ {fmt_num(value, force_sign)}"

def fmt_coin(value: float, symbol: str = "") -> str:
    v = abs(float(value))
    d = 6 if v < 1 else (4 if v < 1000 else 2)
    return f"{value:,.{d}f}" + (f" {symbol}" if symbol else "")

def calc_thb_withdrawal_fee(amount_thb: float, bank_type: str,
                            ktb_fee_thb: float = 15.0) -> float:
    if bank_type == "KTB (กรุงไทย)":
        return ktb_fee_thb
    if bank_type == "SCB":
        return THB_WD_FEE_SCB
    if amount_thb <= THB_WD_LARGE_THRESHOLD:
        return THB_WD_FEE_OTHER_SMALL
    return THB_WD_FEE_OTHER_LARGE

def apply_fx_limit(hedge_usd: pd.Series, index: pd.DatetimeIndex,
                   fx_limit: float) -> tuple[np.ndarray, np.ndarray]:
    allowed, usage, used, cur_month = [], [], 0.0, None
    for ts, cost in zip(index, hedge_usd.values):
        m = ts.to_period("M")
        if m != cur_month:
            cur_month, used = m, 0.0
        if used + cost <= fx_limit:
            used += cost
            allowed.append(1)
        else:
            allowed.append(0)
        usage.append(used)
    return np.array(allowed), np.array(usage)

def _risk_stats(r: pd.Series) -> Optional[dict[str, Any]]:
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < MIN_RISK_SAMPLE_DAYS:
        return None
    q01, q05 = np.percentile(r, 1), np.percentile(r, 5)
    tail = r[r <= q01]
    return {
        "returns": r,
        "sigma_d": float(r.std()),
        "ann_vol": float(r.std() * np.sqrt(365)),
        "var95": float(max(-q05, 0)),
        "var99": float(max(-q01, 0)),
        "es99": float(max(-tail.mean(), 0)) if len(tail) else float(max(-q01, 0)),
        "worst": float(max(-r.min(), 0)),
        "worst_date": r.idxmin(),
        "n_obs": int(len(r)),
        "insufficient_sample": len(r) < RISK_SAMPLE_WARN_DAYS,
    }

def risk_profile(px: pd.Series) -> Optional[dict[str, Any]]:
    return _risk_stats(np.log(px / px.shift(1)))

def safety_stock_factor(net_bias: float, flow_cv: float, lag_days: float,
                        z_alpha: float) -> float:
    return (max(0.0, net_bias) * lag_days
            + z_alpha * flow_cv * np.sqrt(lag_days)) / 30.0

def crypto_haircut(es99: float, lag_days: float) -> float:
    return float(min(es99 * np.sqrt(lag_days), 0.95))

def blended_custody_rate(hot_pct: float, cold_domestic_pct: float,
                         cold_foreign_rate: float) -> float:
    return (hot_pct * HOT_WALLET_NC_RATE
            + (1 - hot_pct) * (cold_domestic_pct * COLD_DOMESTIC_NC_RATE
                               + (1 - cold_domestic_pct) * cold_foreign_rate))

def nc_snapshot(stock_thb: float, total_capital: float, cex_margin: float,
                liab: float, h_crypto: float, h_cex: float, fixed_min_nc: float,
                trading_risk_rate: float, daily_volume_thb: float,
                custody_rate: float) -> dict[str, float]:
    cash = total_capital - stock_thb
    actual = cash + stock_thb * (1 - h_crypto) + cex_margin * (1 - h_cex) - liab
    trading_nc = trading_risk_rate * daily_volume_thb
    custody_nc = stock_thb * custody_rate
    required = fixed_min_nc + trading_nc + custody_nc
    return {
        "cash": cash,
        "actual": actual,
        "required": required,
        "buffer": actual - required,
        "trading_nc": trading_nc,
        "custody_nc": custody_nc,
    }

def blend_hedge_fee(taker_fee: float, maker_fee: float, maker_ratio: float) -> float:
    r = min(max(float(maker_ratio), 0.0), 1.0)
    return taker_fee * (1.0 - r) + maker_fee * r

def default_maker_fee_pct(exchange: str) -> float:
    return GLOBAL_EXCHANGE_MAKER_FEE_PRESET.get(
        exchange, GLOBAL_EXCHANGE_FEE_PRESET.get(exchange, 0.0))

def depth_participation(order_usd: float, market_depth_usd: float) -> float:
    if not market_depth_usd or market_depth_usd <= 0 or order_usd <= 0:
        return 0.0
    return float(order_usd) / float(market_depth_usd)

def market_impact_rate(order_usd: float, market_depth_usd: float,
                       impact_penalty: float) -> float:
    if impact_penalty is None or impact_penalty <= 0:
        return 0.0
    return depth_participation(order_usd, market_depth_usd) * float(impact_penalty)

def align_usdthb(official: pd.Series, index: pd.DatetimeIndex,
                 proxy: Optional[pd.Series] = None) -> tuple[pd.Series, pd.Series]:
    off = official.astype(float).reindex(index)
    is_official = off.notna().to_numpy()
    fx_arr = off.ffill().bfill().to_numpy(dtype=float).copy()
    src = np.where(is_official, "official", "stale").astype(object)

    if proxy is not None and len(proxy):
        px = proxy.astype(float).reindex(index).ffill().to_numpy(dtype=float)
        pos = np.where(is_official, np.arange(len(index), dtype=float), np.nan)
        anchor = pd.Series(pos).ffill().to_numpy()
        cand = np.where(~is_official & ~np.isnan(anchor))[0]
        if len(cand):
            a_idx = anchor[cand].astype(int)
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = px[cand] / px[a_idx]
            ok = np.isfinite(ratio) & (ratio > 0)
            fx_arr[cand[ok]] = fx_arr[a_idx[ok]] * ratio[ok]
            src[cand[ok]] = "proxy"

    return (pd.Series(fx_arr, index=index, name="USDTHB"),
            pd.Series(src, index=index, name="FX_Source"))

def parse_udf_history(payload: Any) -> pd.Series:
    if not isinstance(payload, Mapping) or payload.get("s") != "ok":
        raise ValueError("response ไม่ใช่รูปแบบ UDF history ที่ s == 'ok'")
    t, c = payload.get("t"), payload.get("c")
    if not t or not c or len(t) != len(c):
        raise ValueError("response ไม่มีข้อมูลเวลา/ราคาปิด หรือความยาวไม่เท่ากัน")
    idx = pd.to_datetime(list(t), unit="s", utc=True).tz_convert(None).normalize()
    s = pd.Series(pd.to_numeric(pd.Series(list(c)), errors="coerce").to_numpy(),
                  index=idx, dtype=float)
    s = s[~s.index.duplicated(keep="last")].dropna()
    s = s[s > 0].sort_index()
    if s.empty:
        raise ValueError("ไม่มีแถวราคาที่ใช้ได้หลังทำความสะอาด")
    return s

def sim_defaults(asset_name: str, start_date_val: Any, spot_usd: float,
                 usdthb: float, target_stock_thb: float) -> dict[str, Any]:
    coin_price = spot_usd * usdthb
    return {
        "asset": asset_name,
        "inv_coins": {asset_name: (target_stock_thb / coin_price) if coin_price > 0 else 0.0},
        "target_thb": target_stock_thb,
        "fx_used_usd": 0.0,
        "fx_used_usd_by_month": {},
        "cex_used_thb": 0.0,
        "pnl_thb": 0.0,
        "unhedged_thb": 0.0,
        "orders": [],
        "current_date": start_date_val,
        "customer_coins": {},
        "customer_thb": 1000000.0, 
        "open_orders": [],
    }

def sim_config_signature(ctx: Mapping[str, Any], target_stock_thb: float,
                         start_date: Any, end_date: Any) -> tuple:
    keys = [
        "asset", "local_premium", "spread", "hedge_fee",
        "fx_limit", "slip_sens", "include_fee_rev",
        "wd_markup", "bank_type", "ktb_wd_fee", "ktb_fx_bps",
        "capital", "cex_margin", "cex_liquidity_thb", "liab",
        "fixed_min_nc", "trading_risk_rate", "daily_volume_thb", "custody_rate",
        "hot_breach", "market_depth_usd", "impact_penalty",
    ]
    values = []
    for key in keys:
        value = ctx.get(key)
        is_number = isinstance(value, (int, float, np.integer, np.floating))
        if is_number and not isinstance(value, bool):
            value = round(float(value), 10)
        values.append(value)
    values.append(round(float(target_stock_thb), 2))
    values.append(str(start_date))
    values.append(str(end_date))
    return tuple(values)

def sim_normalize_state(sim: Any, asset: str, start_date_val: Any,
                        spot_usd: float, usdthb: float,
                        target_stock_thb: float) -> dict[str, Any]:
    if not isinstance(sim, dict):
        return sim_defaults(asset, start_date_val, spot_usd, usdthb, target_stock_thb)

    sim.setdefault("asset", asset)
    sim.setdefault("target_thb", target_stock_thb)
    sim.setdefault("fx_used_usd", 0.0)
    sim.setdefault("fx_used_usd_by_month", {})
    sim.setdefault("cex_used_thb", 0.0)
    sim.setdefault("pnl_thb", 0.0)
    sim.setdefault("unhedged_thb", 0.0)
    sim.setdefault("orders", [])
    sim.setdefault("current_date", start_date_val)
    sim.setdefault("customer_coins", {})
    sim.setdefault("customer_thb", 1000000.0)
    sim.setdefault("open_orders", [])

    sim.setdefault("inv_coins", {})
    if not isinstance(sim["inv_coins"], dict):
        sim["inv_coins"] = {sim.get("asset", asset): float(sim["inv_coins"])}

    coin_price = spot_usd * usdthb
    if asset not in sim["inv_coins"]:
        sim["inv_coins"][asset] = target_stock_thb / coin_price if coin_price > 0 else 0.0

    if not isinstance(sim["customer_coins"], dict):
        sim["customer_coins"] = {}
    clean_coins: dict[str, float] = {}
    for sym, qty in sim["customer_coins"].items():
        try:
            q = float(qty)
            if np.isfinite(q) and q > 0:
                clean_coins[sym] = q
        except (TypeError, ValueError):
            continue
    sim["customer_coins"] = clean_coins

    for key in ("fx_used_usd", "cex_used_thb", "pnl_thb", "unhedged_thb"):
        try:
            sim[key] = float(sim[key])
            if not np.isfinite(sim[key]):
                sim[key] = 0.0
        except (TypeError, ValueError):
            sim[key] = 0.0

    sim["asset"] = asset
    sim["target_thb"] = float(target_stock_thb)
    return sim

def execute_order(
    sim: dict[str, Any], side: str, amount_thb: float, order_date: pd.Timestamp,
    px_row: pd.Series, ctx: Mapping[str, Any], affect_wallet: bool = True,
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    p = ctx
    side = "buy" if side == "buy" else "sell"
    current_asset = sim["asset"]

    try:
        amount_thb = float(amount_thb)
    except (TypeError, ValueError):
        amount_thb = 0.0

    spot = float(px_row["Global_USD"])
    fx = float(px_row["USDTHB"])
    daily_vol = float(px_row["Volatility_Pct"])
    coin_price_global = spot * fx

    if spot <= 0 or fx <= 0 or coin_price_global <= 0:
        blocked = dict(n=1, t="ไม่สามารถสร้างราคาได้", s="block",
                       note="ราคา Global หรือ USD/THB ไม่ถูกต้อง")
        return [blocked], None

    mid = coin_price_global * (1 + p["local_premium"])
    quote = mid * (1 + p["spread"]) if side == "buy" else mid * (1 - p["spread"])
    steps = []

    if amount_thb < MIN_TRADE_THB:
        steps.append(dict(
            n=1, t="คำสั่งถูกปฏิเสธ", s="block",
            note=f"มูลค่าต่ำกว่าขั้นต่ำ {MIN_TRADE_THB:,.0f} บาท/คำสั่ง ระบบไม่รับออเดอร์",
        ))
        return steps, None

    steps.append(dict(
        n=1, t="ตั้งราคาให้ลูกค้า", s="pass",
        note=(f"ดึงราคาย้อนหลัง ณ วันที่ {order_date.strftime('%Y-%m-%d')} "
              "มาเป็นฐาน + Local Premium + Dealer Spread"),
        rows=[
            ("วันที่จำลองออเดอร์", order_date.strftime("%Y-%m-%d")),
            ("ราคาโลก (USD)", f"$ {spot:,.2f}"),
            ("x อัตราแลกเปลี่ยน USD/THB", f"{fx:,.2f}"),
            (f"+ Local Premium {p['local_premium'] * 100:.2f}%", f"฿ {mid:,.2f}"),
            (f"{'+' if side == 'buy' else '-'} Dealer Spread {p['spread'] * 100:.2f}%",
             f"฿ {quote:,.2f}"),
        ],
        total=("ราคาที่ลูกค้าได้", f"฿ {quote:,.2f}"),
    ))

    trading_fee = amount_thb * LOCAL_TRADING_FEE_PCT
    settlement_thb = max(0.0, amount_thb - trading_fee)
    # Buy : ค่าธรรมเนียมหักจากเงินที่จ่าย -> ได้เหรียญจาก settlement
    # Sell: amount_thb = มูลค่าเหรียญที่ขาย (gross) -> ส่งมอบเหรียญเต็มจำนวน
    #       แล้วได้เงินหลังหักค่าธรรมเนียม
    coins = (amount_thb if side == "sell" else settlement_thb) / quote

    if coins <= 0:
        steps.append(dict(n=2, t="จับคู่และส่งมอบ", s="block",
                          note="จำนวนเหรียญที่คำนวณได้ไม่เป็นบวก"))
        return steps, None

    inv_before = float(sim["inv_coins"].get(current_asset, 0.0))
    target_coins = (float(sim["target_thb"]) / coin_price_global
                    if coin_price_global > 0 else 0.0)
    inv_after_customer = inv_before - coins if side == "buy" else inv_before + coins
    
    month_str = order_date.strftime("%Y-%m")
    fx_month_dict = sim.setdefault("fx_used_usd_by_month", {})
    month_used = float(fx_month_dict.get(month_str, 0.0))

    if side == "buy":
        required_topup_coins = max(0.0, target_coins - inv_after_customer)
        fx_left_usd = max(0.0, float(p["fx_limit"]) - month_used)
        if spot > 0 and p["hedge_fee"] >= 0:
            max_hedge_by_fx = fx_left_usd / (spot * (1 + p["hedge_fee"]))
        else:
            max_hedge_by_fx = 0.0
        feasible_hedge_coins = min(required_topup_coins, max_hedge_by_fx)

        if inv_after_customer + feasible_hedge_coins < -1e-12:
            steps.append(dict(
                n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="block",
                note=("สต็อกที่มีอยู่ + ความสามารถ hedge ที่เหลือไม่เพียงพอ "
                      "จึงไม่ส่งมอบเหรียญที่ไม่มีอยู่จริง"),
                rows=[
                    ("มูลค่าคำสั่ง", fmt_baht(amount_thb)),
                    (f"ค่าธรรมเนียมซื้อขาย {LOCAL_TRADING_FEE_PCT * 100:.2f}%",
                     "- " + fmt_baht(trading_fee)),
                    ("เหรียญที่ต้องส่งมอบ", fmt_coin(coins, current_asset)),
                    ("สต็อกก่อน", fmt_coin(inv_before, current_asset)),
                    ("FX quotaเหลือ (เดือนนี้)", f"$ {fx_left_usd:,.0f}"),
                    ("สูงสุดที่ hedge ได้ด้วย FX",
                     fmt_coin(feasible_hedge_coins, current_asset)),
                ],
                total=("สถานะ", "Reject — Inventory/FX ไม่พอ"),
            ))
            record = {
                "วันที่": order_date.strftime("%Y-%m-%d"),
                "ฝั่ง": "ซื้อ",
                "เหรียญ": current_asset,
                "มูลค่า (บาท)": amount_thb,
                "ราคาที่ลูกค้าได้": quote,
                "เหรียญที่ส่งมอบ": 0.0,
                "Hedge (เหรียญ)": 0.0,
                "Hedge (USD)": 0.0,
                "CEX Liquidity ใช้ (บาท)": 0.0,
                "Unhedged (บาท)": 0.0,
                "Market Edge": 0.0,
                "รายได้": 0.0,
                "ต้นทุน": 0.0,
                "กำไรออเดอร์": 0.0,
                "สต็อกคงเหลือ": inv_before,
                "FX ใช้สะสม (USD)": month_used,
                "CEX Liquidity ใช้สะสม (บาท)": sim["cex_used_thb"],
                "NC Buffer": np.nan,
                "ผลด่าน": "Reject — Inventory/FX ไม่พอ",
            }
            return steps, record

    steps.append(dict(
        n=2, t="จับคู่และส่งมอบเข้ากระเป๋า", s="pass",
        note=("ลูกค้าชำระเงินบาทและได้รับเหรียญจาก inventory" if side == "buy"
              else "รับเหรียญจากลูกค้าและจ่ายเงินบาทตามราคาที่ quote"),
        rows=[
            ("มูลค่าที่ลูกค้าใส่", fmt_baht(amount_thb)),
            (f"ค่าธรรมเนียมซื้อขาย {LOCAL_TRADING_FEE_PCT * 100:.2f}%",
             "- " + fmt_baht(trading_fee)),
            ("ฐาน settlementหลังค่าธรรมเนียม", fmt_baht(settlement_thb)),
        ],
        total=("เหรียญที่ลูกค้าได้" if side == "buy" else "เหรียญที่ลูกค้าส่งมอบ",
               fmt_coin(coins, current_asset)),
    ))

    sim["inv_coins"][current_asset] = inv_after_customer
    short_coins = max(0.0, target_coins - sim["inv_coins"][current_asset])
    excess_coins = max(0.0, sim["inv_coins"][current_asset] - target_coins)

    steps.append(dict(
        n=3, t="ตัด/รับสต็อก",
        s="warn" if (short_coins > 0 or excess_coins > 0) else "pass",
        note=("Buy ลด inventory ก่อน แล้วค่อยเติมกลับด้วย hedge" if side == "buy"
              else "Sell เพิ่ม inventory ก่อน แล้วค่อยขายส่วนเกินบน CEX"),
        rows=[
            ("สต็อกก่อนออเดอร์", fmt_coin(inv_before, current_asset)),
            ("การเปลี่ยนแปลง",
             ("- " if side == "buy" else "+ ") + fmt_coin(coins, current_asset)),
            ("สต็อกหลังรับ/ส่งมอบ", fmt_coin(sim["inv_coins"][current_asset], current_asset)),
            ("Target Stock", fmt_coin(target_coins, current_asset)),
            ("Short / Excess",
             fmt_coin(short_coins if side == "buy" else excess_coins, current_asset)),
        ],
        total=("มูลค่าสต็อกปัจจุบัน",
               fmt_baht(max(0.0, sim["inv_coins"][current_asset]) * coin_price_global)),
    ))

    hedge_required_coins = short_coins if side == "buy" else excess_coins
    cex_used_thb_this_order = 0.0

    if side == "buy":
        fx_left_usd = max(0.0, float(p["fx_limit"]) - month_used)
        if spot > 0 and p["hedge_fee"] >= 0:
            max_hedge_by_fx = fx_left_usd / (spot * (1 + p["hedge_fee"]))
        else:
            max_hedge_by_fx = 0.0
        hedged_coins = min(hedge_required_coins, max_hedge_by_fx)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)

        hedge_thb = hedged_coins * coin_price_global
        hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
        sim["fx_used_usd"] += hedge_usd
        fx_month_dict[month_str] = month_used + hedge_usd
        
        if hedge_required_coins > 0:
            sim["inv_coins"][current_asset] += hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        hedge_status = fx_status
        if residual_unhedged_coins <= 1e-12:
            hedge_note = "เติม inventory กลับถึง target ด้วยการซื้อบน Global CEX"
        else:
            hedge_note = ("FX quota ไม่พอสำหรับเติม inventory ทั้งหมด "
                          "จึงเหลือ exposure ค้างบางส่วน")
        cex_liquidity_left = max(
            0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
    else:
        cex_liquidity_left = max(
            0.0, float(p["cex_liquidity_thb"]) - float(sim["cex_used_thb"]))
        max_hedge_by_cex = (cex_liquidity_left / coin_price_global
                            if coin_price_global > 0 else 0.0)
        hedged_coins = min(hedge_required_coins, max_hedge_by_cex)
        residual_unhedged_coins = max(0.0, hedge_required_coins - hedged_coins)

        hedge_thb = hedged_coins * coin_price_global
        hedge_usd = hedged_coins * spot * (1 + p["hedge_fee"])
        cex_used_thb_this_order = hedge_thb
        sim["cex_used_thb"] += cex_used_thb_this_order
        sim["inv_coins"][current_asset] -= hedged_coins
        sim["unhedged_thb"] += residual_unhedged_coins * coin_price_global

        fx_status = "pass"
        hedge_status = "pass" if residual_unhedged_coins <= 1e-12 else "warn"
        if residual_unhedged_coins <= 1e-12:
            hedge_note = "ขาย inventory ส่วนเกินบน Global CEX โดยใช้ CEX liquidity"
        else:
            hedge_note = ("CEX liquidity ไม่พอขาย inventory ส่วนเกินทั้งหมด "
                          "จึงเหลือ long exposure ค้าง")
        fx_left_usd = max(0.0, float(p["fx_limit"]) - month_used)

    steps.append(dict(
        n=4, t="ระบบตัดสินใจ Hedge อัตโนมัติ", s=hedge_status, note=hedge_note,
        rows=[
            ("ปริมาณที่ต้อง hedge", fmt_coin(hedge_required_coins, current_asset)),
            ("Hedge สำเร็จ", fmt_coin(hedged_coins, current_asset)),
            ("มูลค่า hedge", fmt_baht(hedge_thb)),
            ("Residual Unhedged", fmt_coin(residual_unhedged_coins, current_asset)),
            ("Direction", "Buy บน CEX" if side == "buy" else "Sell บน CEX"),
        ],
        total=("สถานะ",
               "Hedge ครบ" if residual_unhedged_coins <= 1e-12 else "Hedge บางส่วน"),
    ))

    unhedged_thb_this_order = residual_unhedged_coins * coin_price_global

    if side == "buy":
        if residual_unhedged_coins <= 1e-12:
            gate_note = "Buy-side hedge ใช้ outbound FX quota"
        else:
            gate_note = ("โควตา outbound เหลือไม่พอ "
                         "จึงเหลือ inventory exposure ที่ยังไม่ได้ hedge")
        steps.append(dict(
            n=5, t="ด่าน FX Limit — Outbound", s=fx_status, note=gate_note,
            rows=[
                ("FX ใช้ก่อนออเดอร์ (เดือนนี้)", f"$ {month_used:,.0f}"),
                ("ออเดอร์นี้ใช้", f"$ {hedge_usd:,.0f}"),
                ("FX ใช้สะสมเดือนนี้", f"$ {month_used + hedge_usd:,.0f}"),
                ("FX Limit ต่อเดือน", f"$ {p['fx_limit']:,.0f}"),
                ("FX เหลือเดือนนี้", f"$ {max(0.0, p['fx_limit'] - (month_used + hedge_usd)):,.0f}"),
            ],
            total=("ส่วนที่ยัง Unhedged", fmt_baht(unhedged_thb_this_order)),
        ))
    else:
        steps.append(dict(
            n=5, t="ด่าน CEX Liquidity — Sell-side",
            s=fx_status if residual_unhedged_coins <= 1e-12 else "warn",
            note="Sell-side hedge ใช้ CEX liquidity เดิม ไม่กิน outbound FX quota",
            rows=[
                ("CEX Liquidity ก่อนออเดอร์",
                 fmt_baht(cex_liquidity_left + cex_used_thb_this_order)),
                ("ใช้ hedge ออเดอร์นี้", fmt_baht(cex_used_thb_this_order)),
                ("ใช้สะสม", fmt_baht(sim["cex_used_thb"])),
                ("CEX Liquidity เหลือ",
                 fmt_baht(max(0.0, p["cex_liquidity_thb"] - sim["cex_used_thb"]))),
                ("FX ใช้สะสมเดือนนี้", f"$ {month_used:,.0f}"),
            ],
            total=("ส่วนที่ยัง Unhedged", fmt_baht(unhedged_thb_this_order)),
        ))

    stock_thb = max(0.0, sim["inv_coins"][current_asset]) * coin_price_global
    nc = nc_snapshot(
        stock_thb, p["capital"], p["cex_margin"], p["liab"],
        p["h_crypto"], p["h_cex"], p["fixed_min_nc"],
        p["trading_risk_rate"], p["daily_volume_thb"], p["custody_rate"],
    )

    if nc["buffer"] < 0:
        nc_status = "block"
    elif nc["buffer"] < 0.5 * nc["required"] or p["hot_breach"]:
        nc_status = "warn"
    else:
        nc_status = "pass"

    if nc_status == "pass":
        nc_note = "หลังออเดอร์ยังมี NC buffer เป็นบวกตาม planning model"
    else:
        nc_note = "NC/Capital เป็น planning model; ไม่ใช่ตัวรับรอง compliance อัตโนมัติ"

    steps.append(dict(
        n=6, t="ด่านเงินกองทุนสภาพคล่องสุทธิ (Planning Model)", s=nc_status,
        note=nc_note,
        rows=[
            ("สต็อกหลัง hedge", fmt_baht(stock_thb)),
            ("Cash ใน NC Model", fmt_baht(nc["cash"])),
            ("CEX Margin หลัง haircut",
             fmt_baht(p["cex_margin"] * (1 - p["h_cex"]))),
            ("NC ที่มีจริง", fmt_baht(nc["actual"])),
            ("NC ขั้นต่ำที่ต้องดำรง", fmt_baht(nc["required"])),
        ],
        total=("NC Buffer", fmt_baht(nc["buffer"], force_sign=True)),
    ))

    if side == "buy":
        market_edge = coins * (quote - coin_price_global)
    else:
        market_edge = coins * (coin_price_global - quote)

    fee_rev = trading_fee if p["include_fee_rev"] else 0.0

    wd_markup_rev = 0.0
    if side == "buy":
        wd_base = (p["wd_fee_per_coin"] * coins * coin_price_global
                   + calc_thb_withdrawal_fee(amount_thb, p["bank_type"], p["ktb_wd_fee"]))
        wd_markup_rev = wd_base * p["wd_markup"]

    depth_usd = float(p.get("market_depth_usd") or 0.0)
    impact_pen = float(p.get("impact_penalty") or 0.0)
    depth_on = depth_usd > 0 and impact_pen > 0
    hedge_part = 0.0
    impact_cost = 0.0
    if hedged_coins > 0:
        ktb_fx_benefit = hedge_thb * (p["ktb_fx_bps"] / 10000.0)
        hedge_fee_cost = hedge_thb * p["hedge_fee"]
        hedge_order_usd = hedged_coins * spot
        hedge_part = depth_participation(hedge_order_usd, depth_usd)
        impact_cost = hedge_thb * market_impact_rate(hedge_order_usd, depth_usd,
                                                     impact_pen)
        slippage_cost = hedge_thb * daily_vol * p["slip_sens"] + impact_cost
    else:
        ktb_fx_benefit = 0.0
        hedge_fee_cost = 0.0
        slippage_cost = 0.0

    revenue = market_edge + fee_rev + wd_markup_rev + ktb_fx_benefit
    cost = hedge_fee_cost + slippage_cost
    net = revenue - cost
    sim["pnl_thb"] += net

    if side == "buy":
        pnl_note = "P&L มาจาก realized quote-vs-global edge + fee หักต้นทุน hedge/slippage"
    else:
        pnl_note = ("Sell-side P&L สะท้อนส่วนต่างระหว่างราคาที่รับซื้อจากลูกค้า"
                    "กับราคาที่ขายต่อบน Global CEX")

    net_bps = (net / amount_thb * 10000) if amount_thb else 0.0

    steps.append(dict(
        n=7, t="กำไรขาดทุนของ Dealer ในออเดอร์นี้",
        s="pass" if net >= 0 else "warn", note=pnl_note,
        rows=[
            ("Market Edge จาก Quote vs Global",
             ("+ " if market_edge >= 0 else "- ") + fmt_baht(abs(market_edge))),
            ("ค่าธรรมเนียมซื้อขาย", "+ " + fmt_baht(fee_rev)),
            ("Markup ค่าธรรมเนียมถอน", "+ " + fmt_baht(wd_markup_rev)),
            ("KTB FX Benefit", "+ " + fmt_baht(ktb_fx_benefit)),
            ("ค่าธรรมเนียม CEX", "- " + fmt_baht(hedge_fee_cost)),
            ("Slippage", "- " + fmt_baht(slippage_cost)),
        ] + ([
            (f"  └ ส่วน Market Impact (กิน depth {hedge_part * 100:,.1f}%)",
             "- " + fmt_baht(impact_cost)),
        ] if depth_on else []),
        total=("กำไรสุทธิ",
               f"{fmt_baht(net, force_sign=True)} ({net_bps:,.1f} bps)"),
    ))

    if nc_status == "pass" and residual_unhedged_coins <= 1e-12:
        gate_result = "ผ่าน"
    elif nc_status != "block":
        gate_result = "เฝ้าระวัง"
    else:
        gate_result = "NC ไม่พอ"

    if affect_wallet:
        coins_book = sim.setdefault("customer_coins", {})
        cash_now = float(sim.get("customer_thb", 1000000.0))
        if side == "buy":
            coins_book[current_asset] = coins_book.get(current_asset, 0.0) + coins
            sim["customer_thb"] = cash_now - amount_thb
        else:
            coins_book[current_asset] = max(0.0, coins_book.get(current_asset, 0.0) - coins)
            sim["customer_thb"] = cash_now + settlement_thb

    record = {
        "วันที่": order_date.strftime("%Y-%m-%d"),
        "ฝั่ง": "ซื้อ" if side == "buy" else "ขาย",
        "เหรียญ": current_asset,
        "มูลค่า (บาท)": amount_thb,
        "ราคาที่ลูกค้าได้": quote,
        "เหรียญที่ส่งมอบ": coins,
        "Hedge (เหรียญ)": hedged_coins,
        "Hedge (USD)": hedge_usd,
        "CEX Liquidity ใช้ (บาท)": cex_used_thb_this_order,
        "Unhedged (บาท)": unhedged_thb_this_order,
        "Market Edge": market_edge,
        "รายได้": revenue,
        "ต้นทุน": cost,
        "กำไรออเดอร์": net,
        "สต็อกคงเหลือ": sim["inv_coins"][current_asset],
        "FX ใช้สะสม (USD)": month_used + hedge_usd if side == "buy" else month_used,
        "CEX Liquidity ใช้สะสม (บาท)": sim["cex_used_thb"],
        "NC Buffer": nc["buffer"],
        "ผลด่าน": gate_result,
    }
    sim["orders"].append(record)
    return steps, record


def _letter_logo(sym: str) -> str:
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           f"<circle cx='50' cy='50' r='50' fill='{_LOGO_BG.get(sym, '#5e6673')}'/>"
           f"<text x='50' y='50' text-anchor='middle' dominant-baseline='central' "
           f"font-family='Arial,sans-serif' font-size='{38 if len(sym) <= 3 else 28}' "
           f"font-weight='700' fill='#fff'>{sym[:4]}</text></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

def get_coin_logo(symbol: str) -> str:
    return COIN_LOGOS.get(symbol) or _letter_logo(symbol)

def coin_icon_html(sym: str, size: int = 28) -> str:
    layers = f"url({get_coin_logo(sym)}),url({_letter_logo(sym)})"
    return (f'<span style="display:inline-block;width:{size}px;height:{size}px;'
            f'min-width:{size}px;border-radius:50%;background-color:#2b3139;'
            f'background-image:{layers};background-size:cover;background-position:center;"></span>')


NAV_LABELS = [
    "📊 5-Year Backtest Simulator",
    "🧮 Liquidity & Capital Planner",
    "🛒 Exchange UI Simulator",
    "📰 ข่าวคริปโท",
    "💼 กระเป๋าเงิน (Wallet)",
]
NAV_EXCHANGE = NAV_LABELS[2]
NAV_NEWS = NAV_LABELS[3]

def _go_to_exchange(sym: str) -> None:
    st.session_state["bt_asset"] = sym
    st.session_state["main_nav"] = NAV_EXCHANGE
    st.session_state["main_nav_tabs"] = NAV_EXCHANGE
    st.session_state.pop("main_nav_tabs_news", None)


# =========================================================================
# LAYER 2 — DATA LAYER (network / IO / export)
# =========================================================================

def _cache_data(*dargs, **dkwargs):
    def decorator(fn):
        if HAS_UI:
            return st.cache_data(*dargs, **dkwargs)(fn)
        return fn

    if dargs and callable(dargs[0]) and not dkwargs:
        fn, dargs = dargs[0], ()
        return fn if not HAS_UI else st.cache_data(fn)
    return decorator


def _normalize_index(d: pd.DataFrame) -> pd.DataFrame:
    idx = pd.to_datetime(d.index)
    try:
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
    except (TypeError, AttributeError):
        pass
    d.index = idx.normalize()
    return d


@_cache_data(ttl=3600, show_spinner=False)
def fetch_fx_proxy_series(start: Any, end: Any) -> tuple[Optional[pd.Series], Optional[str]]:
    if not (FX_PROXY["enabled"] and FX_PROXY["url"]):
        return None, "FX proxy ไม่ได้เปิดใช้ใน config"
    try:
        t0 = int(pd.Timestamp(start).tz_localize("UTC").timestamp())
        t1 = int(pd.Timestamp(end).tz_localize("UTC").timestamp()) + 86400
        qs = urllib.parse.urlencode({
            "symbol": FX_PROXY["symbol"], "resolution": FX_PROXY["resolution"],
            "from": t0, "to": t1,
        })
        url = FX_PROXY["url"] + ("&" if "?" in FX_PROXY["url"] else "?") + qs
        req = urllib.request.Request(url, headers={"User-Agent": "XSpringDealerSuite"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return parse_udf_history(payload), None
    except Exception as e:
        return None, f"ดึง FX proxy ไม่สำเร็จ: {e}"


@_cache_data(ttl=60, show_spinner="กำลังโหลดข้อมูลราคาย้อนหลัง…")
def fetch_price_data(ticker: str, start: Any, end: Any,
                     use_fx_proxy: bool = False) -> tuple[pd.DataFrame, Optional[str]]:
    try:
        end_incl = pd.Timestamp(end) + pd.Timedelta(days=1)
        # ดาวน์โหลดราคาเหรียญ + USD/THB พร้อมกัน ลดเวลารอจาก network 2 รอบเหลือรอบเดียว
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_crypto = ex.submit(
                yf.download, f"{ticker}-USD", start=start, end=end_incl,
                auto_adjust=False, progress=False
            )
            f_fx = ex.submit(
                yf.download, "THB=X", start=start, end=end_incl,
                auto_adjust=False, progress=False
            )
            raw = f_crypto.result()
            fx_raw = f_fx.result()
    except Exception as e:
        return pd.DataFrame(), f"ดึงข้อมูลไม่สำเร็จ: {e}"

    if raw is None or raw.empty:
        return pd.DataFrame(), f"ไม่พบข้อมูลราคาของ {ticker}-USD ในช่วงที่เลือก"
    if fx_raw is None or fx_raw.empty:
        return pd.DataFrame(), "ไม่พบข้อมูลเรท USD/THB (THB=X) ในช่วงที่เลือก"

    for d in (raw, fx_raw):
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)

    raw, fx_raw = _normalize_index(raw), _normalize_index(fx_raw)
    raw = raw[~raw.index.duplicated(keep="last")]
    fx_raw = fx_raw[~fx_raw.index.duplicated(keep="last")]

    vol_col = "Volume" if "Volume" in raw.columns else None
    df = raw[["Close", "High", "Low"]].copy()
    df.columns = ["Global_USD", "Day_High", "Day_Low"]
    df["Volume_USD"] = raw[vol_col].astype(float) if vol_col else 0.0
    
    proxy = None
    if use_fx_proxy:
        proxy, _proxy_err = fetch_fx_proxy_series(start, end)
    df["USDTHB"], df["FX_Source"] = align_usdthb(fx_raw["Close"].dropna(), df.index, proxy)
    df = df.dropna()
    if df.empty:
        return pd.DataFrame(), "ข้อมูลที่ได้ว่างเปล่าหลังทำความสะอาด"

    df["Volatility_Pct"] = (df["Day_High"] - df["Day_Low"]) / df["Global_USD"]
    return df, None


@_cache_data(ttl=60, show_spinner=False)
def fetch_market_overview(tickers: list[str]) -> pd.DataFrame:
    def _one(t: str) -> Optional[dict[str, Any]]:
        try:
            data = yf.download(f"{t}-USD", period="2d", interval="1h", progress=False)
            if data.empty:
                return None
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            last_price = float(data["Close"].iloc[-1])
            prev_price = float(data["Close"].iloc[0])
            pct_change = (last_price - prev_price) / prev_price * 100 if prev_price else 0
            volume_24h = float(data["Volume"].tail(24).sum())
            return {
                "symbol": t,
                "price_usd": last_price,
                "pct_change": pct_change,
                "volume": volume_24h,
            }
        except Exception:
            return None

    # เดิมยิงทีละเหรียญ ทำให้ 11 เหรียญรอ network ต่อกันยาวมาก
    # เปลี่ยนเป็น parallel requests เพื่อลดเวลาโหลดหน้า Wallet/Exchange
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as ex:
        rows = [row for row in ex.map(_one, tickers) if row is not None]
    return pd.DataFrame(rows)


@_cache_data(ttl=900, show_spinner=False)
def _fetch_latest_usdthb() -> Optional[float]:
    fx_raw = yf.download("THB=X", period="5d", auto_adjust=False, progress=False)
    if fx_raw is None or fx_raw.empty:
        return None
    if isinstance(fx_raw.columns, pd.MultiIndex):
        fx_raw.columns = fx_raw.columns.get_level_values(0)
    val = fx_raw["Close"].dropna()
    return float(val.iloc[-1]) if not val.empty else None


def get_reference_usdthb(preferred_df: Optional[pd.DataFrame] = None) -> tuple[float, bool]:
    if (preferred_df is not None and not preferred_df.empty
            and "USDTHB" in preferred_df):
        return float(preferred_df["USDTHB"].iloc[-1]), False
    try:
        rate = _fetch_latest_usdthb()
    except Exception:
        rate = None
    if rate is not None:
        return rate, False
    return FALLBACK_USDTHB, True


@_cache_data(show_spinner=False)
def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv().encode("utf-8-sig")


def to_csv_bytes_with_assumptions(df: pd.DataFrame, assumptions: Mapping[str, Any],
                                  report_title: str) -> bytes:
    exported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        f"# {report_title}",
        f"# Model version,{MODEL_VERSION}",
        f"# Config file,{CONFIG_INFO['source'] or 'built-in defaults'}",
        f"# Config sha256,{CONFIG_INFO['sha256'] or '-'}",
        f"# Exported at (UTC),{exported_at}",
        "# --- Assumptions / Parameters used for this export ---",
    ]
    for k, v in assumptions.items():
        if isinstance(v, (dict, list)):
            v_str = json.dumps(v, ensure_ascii=False)
        else:
            v_str = str(v)
        lines.append(f"# {k},{v_str}")
    lines.append("# --- Data ---")
    return ("\n".join(lines) + "\n" + df.to_csv()).encode("utf-8-sig")


# =========================================================================
# LAYER 3 — UI THEME & COMPONENTS
# =========================================================================

THEME_CSS = """
<style>
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 98% !important; }
    .xs-hero {
        background: linear-gradient(135deg, #0b0e11 0%, #181a20 50%, #1e2329 100%);
        border: 1px solid #2b3139;
        border-radius: 12px; padding: 1.5rem 1.75rem; margin-bottom: 1.25rem;
    }
    .xs-hero h1 { margin:0; font-size:1.9rem; font-weight:800; color:#EAECEF;
                  letter-spacing:-0.5px; }
    .xs-hero p  { margin:.4rem 0 0 0; color:#848e9c; font-size:0.92rem; }
    .xs-pill {
        display:inline-block; background:rgba(14,203,129,0.1); color:#0ecb81;
        border:1px solid rgba(14,203,129,0.2); border-radius:4px;
        padding:2px 10px; font-size:0.75rem; font-weight:600;
        margin-right:6px; margin-top:10px;
    }
    .xs-ver { color:#5e6673; font-size:.7rem; margin-top:8px; }

    /* Sleek Exchange Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 16px; border-bottom: 1px solid #2b3139; padding-bottom: 0px; }
    .stTabs [data-baseweb="tab"] {
        height: 36px; padding: 0 4px; background: transparent; border: none;
        border-radius: 0; font-weight: 600; color: #848e9c; margin-bottom: -1px;
    }
    .stTabs [aria-selected="true"] {
        background: transparent !important; color: #EAECEF !important; border-bottom: 2px solid #0ecb81 !important;
    }

    div[data-testid="stMetricValue"] { font-size:1.4rem; color: #EAECEF; }
    .xs-sec {
        font-size:1.05rem; font-weight:700; color:#EAECEF;
        border-left:3px solid #0ecb81; padding-left:10px; margin:1.2rem 0 .6rem 0;
    }
    iframe { border-radius: 8px; }

    .xs-gauge { margin:0 0 .35rem 0; }
    .xs-gauge .top { display:flex; justify-content:space-between; font-size:.8rem;
                     color:#848e9c; margin-bottom:5px; }
    .xs-gauge .top b { color:#EAECEF; font-variant-numeric:tabular-nums; }
    .xs-gauge .track { height:6px; background:#2b3139; border-radius:2px; overflow:hidden; }
    .xs-gauge .fill { height:100%; border-radius:2px; transition:width .4s ease; }
    .xs-gauge .sub { font-size:.74rem; color:#5e6673; margin-top:4px; }

    .xs-tl { position:relative; padding-left:24px; }
    .xs-tl::before { content:""; position:absolute; left:7px; top:14px; bottom:14px;
                     width:2px; background:#2b3139; }
    .xs-tl .xs-step { position:relative; --c:#0ecb81; border:1px solid #2b3139;
                      border-radius:8px; padding:12px 16px; margin-bottom:10px;
                      background:#181a20; }
    .xs-tl .xs-step.warn  { --c:#fcd535; }
    .xs-tl .xs-step.block { --c:#f6465d; }
    .xs-tl .xs-step::before {
        content:attr(data-n); position:absolute; left:-24px; top:11px;
        width:18px; height:18px; border-radius:50%; background:#181a20;
        border:2px solid var(--c); color:#EAECEF; font-size:.65rem; font-weight:700;
        display:flex; align-items:center; justify-content:center;
    }
    .xs-step h4 { margin:0 0 2px 0; font-size:.9rem; color:#EAECEF; font-weight:600;
                  display:flex; justify-content:space-between; gap:12px;
                  align-items:baseline; }
    .xs-step .xs-tag { font-size:.65rem; font-weight:600; padding:2px 8px;
                       border-radius:4px; white-space:nowrap; }
    .xs-step.pass  .xs-tag { background:rgba(14,203,129,.1);  color:#0ecb81; }
    .xs-step.warn  .xs-tag { background:rgba(252,213,53,.1); color:#fcd535; }
    .xs-step.block .xs-tag { background:rgba(246,70,93,.1);  color:#f6465d; }
    .xs-step p  { margin:4px 0 0 0; color:#848e9c; font-size:.8rem; }
    .xs-row { display:flex; justify-content:space-between; gap:14px; padding:3px 0;
              border-bottom:1px dashed #2b3139; font-size:.8rem; color:#b7bdc6; }
    .xs-row:last-child { border-bottom:none; }
    .xs-row b { color:#EAECEF; font-variant-numeric:tabular-nums; }
    .xs-tot { border-top:1px solid #2b3139; margin-top:6px; padding-top:7px; font-weight:600; }
    .xs-audit-row { font-size:.75rem; color:#b7bdc6; border-bottom:1px dashed #2b3139;
                    padding:4px 0; }
    .xs-audit-row b { color:#fcd535; }
    .xs-foot { color:#5e6673; font-size:.7rem; text-align:center; margin-top:2.5rem;
               padding-top:1rem; border-top:1px solid #2b3139; }

    /* Custom Exchange Simulator UI Styling */
    .ex-header { display: flex; justify-content: space-between; align-items: center; background: #181a20; padding: 12px 24px; border-bottom: 1px solid #2b3139; margin-bottom: 16px; border-radius: 8px; }
    .ex-stat { display: flex; flex-direction: column; }
    .ex-stat-label { font-size: 0.75rem; color: #848e9c; }
    .ex-stat-val { font-size: 0.9rem; font-weight: 600; color: #EAECEF; }
    .ex-green { color: #0ecb81 !important; }
    .ex-red { color: #f6465d !important; }

    .oe-tabs { display: flex; gap: 16px; border-bottom: 1px solid #2b3139; padding-bottom: 8px; margin-bottom: 16px; }
    .oe-tab { font-size: 0.9rem; font-weight: 600; color: #848e9c; cursor: pointer; }
    .oe-tab.active { color: #EAECEF; border-bottom: 2px solid #fcd535; padding-bottom: 6px; margin-bottom: -8px; }
    .oe-bal { display: flex; justify-content: space-between; font-size: 0.8rem; color: #848e9c; margin-bottom: 16px; }

    /* ---------- Market list (Bitkub style) ---------- */
    [class*="st-key-mkrow_"] {
        position: relative !important;
        border-bottom: 1px solid #1f2329;
        cursor: pointer;
    }
    [class*="st-key-mkrow_"]:hover { background: #2b3139; }
    [class*="st-key-mkrow_"] > [data-testid="stVerticalBlock"] { gap: 0 !important; }

    /* ปุ่มจริงถูกดึงออกจาก flow แล้วซ่อน วางทับแถว */
    [class*="st-key-fav_"], [class*="st-key-sel_"] {
        position: absolute !important;
        top: 0 !important; bottom: 0 !important; margin: 0 !important; height: 100% !important;
    }
    [class*="st-key-fav_"] { left: 0 !important; width: 36px !important; z-index: 10 !important; }
    [class*="st-key-sel_"] { left: 36px !important; right: 0 !important; width: auto !important; z-index: 9 !important; }

    /* ทำให้ overlay คลุมทั้งแถวจริง ๆ: กว้าง+สูง 100% ทุกชั้นของ wrapper ปุ่ม */
    [class*="st-key-fav_"] *, [class*="st-key-sel_"] * {
        width: 100% !important; height: 100% !important; margin: 0 !important; padding: 0 !important;
    }
    [class*="st-key-fav_"] button, [class*="st-key-sel_"] button {
        display: block !important; border: none !important; background: transparent !important;
        color: transparent !important; opacity: 0 !important; cursor: pointer !important;
    }
    
    /* บังคับไม่ให้ข้อความดักจับการคลิก */
    [class*="st-key-mkrow_"] .mk-row, [class*="st-key-mkrow_"] .mk-row * { 
        pointer-events: none !important; 
    }

    .mk-head, .mk-row { display: flex; align-items: center; }
    .mk-head { font-size: .72rem; color: #848e9c; padding: 6px 8px 6px 0; }
    .mk-row { padding: 8px 8px 8px 0; }
    .mk-star { width: 36px; flex-shrink: 0; text-align: center; font-size: 1.15rem; color: #5e6673; }
    .mk-star.on { color: #fcd535; }
    .mk-asset { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; }
    .mk-asset > div { min-width: 0; }
    .mk-sym { font-weight: 700; color: #EAECEF; font-size: .9rem; line-height: 1.15; white-space: nowrap; }
    .mk-sym span { color: #848e9c; font-weight: 500; }
    .mk-name { font-size: .68rem; color: #848e9c; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .mk-vol { color: #b7bdc6; }
    .mk-right { flex-shrink: 0; margin-left: 8px; text-align: right; }
    .mk-price { font-weight: 700; color: #EAECEF; font-size: .88rem; line-height: 1.15;
                white-space: nowrap; font-variant-numeric: tabular-nums; }
    .mk-pct { font-size: .75rem; font-weight: 600; white-space: nowrap;
              font-variant-numeric: tabular-nums; }
    .mk-sel { background: #0a5c33 !important; }

    /* Wallet Tab Styles */
    .wl-box { background: #181a20; border: 1px solid #2b3139; border-radius: 8px; padding: 20px; }
    .wl-total-val { font-size: 2.2rem; font-weight: 700; color: #EAECEF; font-variant-numeric: tabular-nums; margin: 4px 0; }
    .st-key-wl_table { gap: 0 !important; }
    .st-key-wlhead { padding: 12px 16px 8px; background: #181a20; border: 1px solid #2b3139; border-radius: 8px 8px 0 0; }
    .wl-h { font-size: 0.75rem; color: #848e9c; }
    [class*="st-key-wlrow_"] { padding: 8px 16px; background: #181a20; border: 1px solid #2b3139; border-top: none; }
    [class*="st-key-wlrow_"]:hover { background: #2b3139; }
    [class*="st-key-wlbtn_"] button { justify-content: flex-start; padding: 0; color: #EAECEF !important; font-weight: 700; }
    .wl-cell { color: #EAECEF; font-size: 0.85rem; text-align: right; font-variant-numeric: tabular-nums; }
    .wl-acts { display: flex; justify-content: flex-end; gap: 16px; font-weight: 600; }
    .wl-acts span:not(:last-child) { color: #0ecb81; }
    .wl-name { line-height: 1.2; color: #EAECEF; font-weight: 600; font-size: 0.9rem; }
    .wl-name span { font-size: 0.7rem; color: #848e9c; font-weight: 500; }

    /* ---------- แปลง Main Navigation Radio ให้เป็น Tabs ตามรูป ---------- */
    .st-key-main_nav [role="radiogroup"] {
        gap: 16px !important; 
        flex-wrap: nowrap !important;
        border-bottom: 1px solid #2b3139 !important; 
        padding-bottom: 0px !important; 
        margin-bottom: 16px !important;
    }
    
    .st-key-main_nav label[data-baseweb="radio"] {
        background: transparent !important; 
        border: none !important;
        padding: 0 4px 6px 4px !important; 
        margin: 0 0 -1px 0 !important;
        border-radius: 0 !important; 
        border-bottom: 2px solid transparent !important;
        align-items: center !important;
        cursor: pointer !important;
    }
    
    /* ซ่อนปุ่มกลม (Radio Circle) เด็ดขาด 100% */
    .st-key-main_nav label[data-baseweb="radio"] > div:first-child {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
    }
    
    /* ปรับแต่งข้อความเริ่มต้น (สีเทา) */
    .st-key-main_nav label[data-baseweb="radio"] p {
        font-weight: 600 !important; 
        color: #848e9c !important; 
        font-size: 0.95rem !important;
        margin: 0 !important;
    }
    
    /* Hover State (ข้อความสีแดงตอนเอาเมาส์ชี้แบบในรูป) */
    .st-key-main_nav label[data-baseweb="radio"]:hover p {
        color: #ff4b4b !important;
    }
    
    /* Active State (เส้นใต้สีเขียว ข้อความสีขาว สำหรับแท็บที่ถูกเลือก) */
    .st-key-main_nav label[data-baseweb="radio"]:has(input:checked) {
        border-bottom: 2px solid #0ecb81 !important;
    }
    .st-key-main_nav label[data-baseweb="radio"]:has(input:checked) p {
        color: #EAECEF !important;
    }
    
    /* ---------- แปลง Order Type Radio ให้เป็น Tabs แบบ Main Nav ---------- */
    .st-key-op_type [role="radiogroup"] {
        gap: 16px !important; 
        flex-wrap: nowrap !important;
        border-bottom: 1px solid #2b3139 !important; 
        padding-bottom: 0px !important; 
        margin-bottom: 16px !important;
    }
    .st-key-op_type label[data-baseweb="radio"] {
        background: transparent !important; 
        border: none !important;
        padding: 0 4px 6px 4px !important; 
        margin: 0 0 -1px 0 !important;
        border-radius: 0 !important; 
        border-bottom: 2px solid transparent !important;
        align-items: center !important;
        cursor: pointer !important;
    }
    .st-key-op_type label[data-baseweb="radio"] > div:first-child {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
        opacity: 0 !important;
    }
    .st-key-op_type label[data-baseweb="radio"] p {
        font-weight: 600 !important; 
        color: #848e9c !important; 
        font-size: 0.95rem !important;
        margin: 0 !important;
    }
    .st-key-op_type label[data-baseweb="radio"]:hover p {
        color: #ff4b4b !important;
    }
    .st-key-op_type label[data-baseweb="radio"]:has(input:checked) {
        border-bottom: 2px solid #0ecb81 !important;
    }
    .st-key-op_type label[data-baseweb="radio"]:has(input:checked) p {
        color: #EAECEF !important;
    }

    /* ---------- Order panel (Bitkub-style) ---------- */
    .op-tabs { display:flex; gap:28px; border-bottom:1px solid #2b3139; margin-bottom:14px; }
    .op-tab { font-size:1rem; font-weight:600; color:#848e9c; padding:8px 4px; }
    .op-tab.active { color:#EAECEF; border-bottom:2px solid #0ecb81; margin-bottom:-1px; }
    .op-row { display:flex; justify-content:space-between; font-size:.85rem; color:#848e9c; margin-bottom:6px; min-height: 1.5rem; }
    .op-row b { color:#0ecb81; font-weight:600; font-variant-numeric:tabular-nums; }
    .op-row.mut b { color:#848e9c; font-weight:500; }
    .op-ro { display:flex; justify-content:space-between; align-items:center; background:#181a20;
             border:1px solid #2b3139; border-radius:6px; padding:12px 14px; margin:8px 0;
             font-size:.88rem; color:#b7bdc6; }
    .op-ro b { color:#EAECEF; font-variant-numeric:tabular-nums; }
    .op-warn { color:#f6465d; font-size:.78rem; margin:2px 0 6px; min-height: 1.4rem; }
    .st-key-op_buy_btn button, .st-key-op_sell_btn button {
        width:100% !important; padding:12px !important; font-weight:700 !important;
        color:#fff !important; border:none !important; }
    .st-key-op_buy_btn button  { background:#0ecb81 !important; }
    .st-key-op_sell_btn button { background:#f6465d !important; }
    .st-key-op_buy_btn button:disabled, .st-key-op_sell_btn button:disabled { opacity:.35 !important; }
    .st-key-op_buy_amt input, [class*="st-key-op_sell_qty_"] input { height: 2.6rem; }
    
    /* ปุ่ม ฝาก / ถอน / ••• ในตาราง Wallet */
    .wl-act { text-align:center; font-weight:600; font-size:.85rem; color:#0ecb81; }
    .wl-act.wl-more { color:#EAECEF; }
    .st-key-wl_deposit button { padding:0 !important; justify-content:center; background:transparent !important; border:none !important; }
    .st-key-wl_deposit button, .st-key-wl_deposit button p { color:#0ecb81 !important; font-weight:600 !important; font-size:.85rem !important; }
    
    /* ---------- AI Chat (ปุ่มลอย + ฟองแชท) ---------- */
    .st-key-ai_fab {
        position: fixed !important; bottom: 72px; right: 24px;
        z-index: 999990; width: auto !important;
    }
    .st-key-ai_fab button {
        border-radius: 999px !important; padding: 10px 20px !important;
        background: #0ecb81 !important; border: none !important;
        box-shadow: 0 8px 24px rgba(14,203,129,.35) !important;
    }
    .st-key-ai_fab button, .st-key-ai_fab button * {
        color: #0b0e11 !important; font-weight: 700 !important;
    }
    .st-key-ai_fab button:hover { background: #12e08f !important; }
    div[data-testid="stPopoverBody"] {
        width: min(420px, 92vw) !important; background: #181a20 !important;
        border: 1px solid #2b3139 !important; border-radius: 14px !important;
    }
    .st-key-ai_fab [data-testid="stForm"] { border: none !important; padding: 0 !important; }
    .ai-row { display: flex; margin: 6px 0; }
    .ai-row.user { justify-content: flex-end; }
    .ai-row.bot  { justify-content: flex-start; }
    .ai-bub { max-width: 82%; padding: 9px 13px; font-size: .86rem; line-height: 1.5; word-wrap: break-word; }
    .ai-row.user .ai-bub { background: #0ecb81; color: #0b0e11; border-radius: 14px 14px 4px 14px; }
    .ai-row.bot  .ai-bub { background: #2b3139; color: #EAECEF; border-radius: 14px 14px 14px 4px; }
    .ai-empty { color: #848e9c; font-size: .82rem; text-align: center; padding: 28px 8px; }
    
    [class*="st-key-ai_sug_"] button {
        justify-content: flex-start !important; text-align: left !important;
        background: #20242b !important; border: 1px solid #2b3139 !important;
        border-radius: 10px !important; padding: 8px 12px !important;
        min-height: 0 !important;
    }
    [class*="st-key-ai_sug_"] button, [class*="st-key-ai_sug_"] button * {
        color: #EAECEF !important; font-size: .82rem !important; font-weight: 500 !important;
    }
    [class*="st-key-ai_sug_"] button:hover { border-color: #0ecb81 !important; }
</style>
"""

def _sv_tuple():
    try:
        nums = re.findall(r"\d+", st.__version__)
        return (int(nums[0]), int(nums[1]))
    except Exception:
        return (1, 40)

if HAS_UI and _sv_tuple() >= (1, 49):
    WIDE = {"width": "stretch"}
else:
    WIDE = {"use_container_width": True}

def _reformat_comma_key(key):
    raw = st.session_state.get(key, "")
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
        st.session_state[key] = f"{num:,.0f}" if num == int(num) else f"{num:,.2f}"
    except ValueError:
        pass

def comma_number_input(label, value, min_value=None, key=None, help=None, disabled=False):
    if key not in st.session_state:
        st.session_state[key] = f"{value:,.0f}"
    st.text_input(label, key=key, help=help, disabled=disabled,
                  on_change=_reformat_comma_key, args=(key,))
    cleaned = st.session_state[key].replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
    except ValueError:
        num = float(value)
    if min_value is not None and num < min_value:
        num = float(min_value)
    return num

def colored_metric(label, display_value, raw_value=None, sub_text=None, font_size="1.5rem"):
    if raw_value is None:
        color = "#EAECEF"
    else:
        color = "#0ecb81" if raw_value >= 0 else "#f6465d"
    if sub_text:
        sub = (f'<div style="font-size:.75rem;color:{color};opacity:.85;'
               f'margin-top:3px;">{sub_text}</div>')
    else:
        sub = ""
    st.markdown(
        f'<div style="padding:.35rem 0 .6rem 0;">'
        f'<div style="font-size:.8rem;color:#848e9c;margin-bottom:4px;">{label}</div>'
        f'<div style="font-size:{font_size};font-weight:700;color:{color};'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
        f'line-height:1.25;">{display_value}</div>{sub}</div>',
        unsafe_allow_html=True,
    )

def metric_card(col, label, value, raw_value=None, sub_text=None, font_size="1.5rem"):
    with col:
        with st.container(border=True):
            colored_metric(label, value, raw_value, sub_text, font_size)

def section(title):
    st.markdown(f'<div class="xs-sec">{title}</div>', unsafe_allow_html=True)

def verdict_box(ok, title, detail, warn=False):
    if warn and ok:
        bg, bd, ic = "rgba(252,213,53,.1)", "#fcd535", "⚠️"
    elif ok:
        bg, bd, ic = "rgba(14,203,129,.1)", "#0ecb81", "✅"
    else:
        bg, bd, ic = "rgba(246,70,93,.1)", "#f6465d", "🚨"
    st.markdown(
        f"<div style='background:{bg};border-left:3px solid {bd};border-radius:4px;"
        f"padding:10px 14px;margin-bottom:10px;'>"
        f"<div style='font-weight:600;color:{bd};font-size:.9rem;'>{ic} {title}</div>"
        f"<div style='color:#b7bdc6;font-size:.8rem;margin-top:4px;'>{detail}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

def gauge_bar(label, used, limit, value_text="", sub="", warn_at=0.70, crit_at=0.90):
    if limit is None or limit <= 0:
        pct = 1.5 if used > 0 else 0.0
    else:
        pct = max(0.0, used / limit)
    if pct < warn_at:
        color = "#0ecb81"
    elif pct < crit_at:
        color = "#fcd535"
    else:
        color = "#f6465d"
    width = min(pct, 1.0) * 100
    text = value_text or f"{pct * 100:.0f}%"
    sub_html = f"<div class='sub'>{sub}</div>" if sub else ""
    st.markdown(
        f"<div class='xs-gauge'>"
        f"<div class='top'><span>{label}</span>"
        f"<b style='color:{color}'>{text}</b></div>"
        f"<div class='track'><div class='fill' "
        f"style='width:{width:.1f}%;background:{color};'></div></div>"
        f"{sub_html}</div>",
        unsafe_allow_html=True,
    )

def step_html(number, title, status, note="", rows=None, total=None):
    tag = {"pass": "ผ่าน", "warn": "เฝ้าระวัง", "block": "ติดด่าน"}[status]
    body = ""
    if rows:
        body += "".join(
            f"<div class='xs-row'><span>{k}</span><b>{v}</b></div>" for k, v in rows
        )
    if total:
        body += (f"<div class='xs-row xs-tot'><span>{total[0]}</span>"
                 f"<b>{total[1]}</b></div>")
    note_html = f"<p>{note}</p>" if note else ""
    body_html = f"<div style='margin-top:8px'>{body}</div>" if body else ""
    return (f"<div class='xs-step {status}' data-n='{number}'>"
            f"<h4><span>{title}</span><span class='xs-tag'>{tag}</span></h4>"
            f"{note_html}{body_html}</div>")

def render_timeline(steps):
    ordered = sorted(steps, key=lambda x: x["n"])
    html = "".join(
        step_html(s["n"], s["t"], s["s"], s.get("note", ""),
                  s.get("rows"), s.get("total"))
        for s in ordered
    )
    st.markdown(f"<div class='xs-tl'>{html}</div>", unsafe_allow_html=True)

_BINANCE_CHECK_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:transparent;color:#EAECEF;
  font-family:"Source Sans Pro",-apple-system,"Segoe UI",Roboto,sans-serif;}
.box{border:1px solid #2b3139;border-radius:8px;padding:12px 16px;font-size:.82rem;}
.row{display:flex;justify-content:space-between;padding:4px 0;
  border-bottom:1px dashed #2b3139;color:#b7bdc6;}
.row:last-child{border-bottom:none;}
.row b{color:#EAECEF;font-variant-numeric:tabular-nums;}
.up{color:#0ecb81}.dn{color:#f6465d}.mut{color:#5e6673}
.tag{font-size:.68rem;font-weight:600;padding:2px 8px;border-radius:4px;
  background:rgba(14,203,129,.1);color:#0ecb81;margin-left:6px;}
.tag.stale{background:rgba(246,70,93,.1);color:#f6465d;}
.note{color:#5e6673;font-size:.7rem;margin-top:6px;}
</style></head><body>
<div class="box">
  <div class="row"><span>💹 ราคาจริงจาก Binance (live)</span>
    <b id="bn-price">กำลังโหลด…</b></div>
  <div class="row"><span>ราคาที่โมเดลใช้ในการ Hedge</span>
    <b>$__MODEL_PRICE__</b></div>
  <div class="row"><span>ส่วนต่าง (Model vs Binance)</span>
    <b id="bn-diff">—</b></div>
  <div class="note" id="bn-note">ดึงจากเบราว์เซอร์ของคุณโดยตรง ณ ขณะเปิดดูหน้านี้ · ไม่ auto-refresh</div>
</div>
<script>
const SYMBOL = "__ASSET__USDT";
const MODEL_PRICE = __MODEL_PRICE__;

async function run(){
  try{
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 8000);
    const r = await fetch("https://fapi.binance.com/fapi/v1/ticker/price?symbol=" + SYMBOL,
                          {signal: ac.signal});
    clearTimeout(t);
    if(!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    const px = parseFloat(d.price);
    if (!Number.isFinite(px)) throw new Error("invalid price");
    document.getElementById("bn-price").innerHTML =
      "$" + px.toLocaleString("en-US", {minimumFractionDigits:2, maximumFractionDigits:2});

    if (MODEL_PRICE > 0){
      const diffPct = (MODEL_PRICE - px) / px * 100;
      const cls = diffPct >= 0 ? "up" : "dn";
      document.getElementById("bn-diff").innerHTML =
        '<span class="' + cls + '">' + (diffPct >= 0 ? "+" : "") + diffPct.toFixed(3) + "%</span>";
    }
    document.getElementById("bn-note").innerHTML =
      "อัปเดต " + new Date().toLocaleTimeString("th-TH", {hour12:false}) +
      " (เวลาเครื่องคุณ) · ดึงจากเบราว์เซอร์ของคุณโดยตรง ณ ขณะเปิดดูหน้านี้";
  } catch(e){
    document.getElementById("bn-price").innerHTML =
      '<span class="mut">ดึงไม่ได้ (' + e.message + ')</span>';
    document.getElementById("bn-diff").innerHTML = '<span class="mut">—</span>';
  }
}
run();
</script></body></html>"""


def render_binance_price_check(asset: str, model_price_usd: float) -> None:
    """แสดงราคาจริงจาก Binance เทียบกับราคาที่โมเดลใช้ hedge
    ดึงครั้งเดียวเมื่อ component ถูก render; ไม่มี timer/auto-refresh"""
    if asset in STABLECOINS:
        return
    try:
        model_price = float(model_price_usd)
    except (TypeError, ValueError):
        model_price = 0.0
    if not math.isfinite(model_price) or model_price < 0:
        model_price = 0.0
    asset = str(asset or "").upper().strip()
    if not re.fullmatch(r"[A-Z0-9]{1,20}", asset):
        return
    html = (
        _BINANCE_CHECK_HTML
        .replace("__ASSET__", asset)
        .replace("__MODEL_PRICE__", f"{model_price:.2f}")
    )
    components.html(html, height=110, scrolling=False)

def render_tradingview(symbol, container_id, height=500, interval="D", studies=None):
    studies_js = str(studies or []).replace("'", '"')
    html = f"""
    <div id="{container_id}" style="height:{height}px;width:100%;"></div>
    <script src="https://s3.tradingview.com/tv.js"></script>
    <script>
      (function draw() {{
        var el = document.getElementById("{container_id}");
        if (!el || el.offsetHeight === 0 || typeof TradingView === "undefined") {{
          return setTimeout(draw, 300);
        }}
        new TradingView.widget({{
          "container_id": "{container_id}",
          "symbol": "{symbol}",
          "interval": "{interval}",
          "timezone": "Asia/Bangkok",
          "theme": "dark",
          "style": "1",
          "locale": "th_TH",
          "width": "100%",
          "height": {height},
          "toolbar_bg": "#181a20",
          "enable_publishing": false,
          "hide_side_toolbar": false,
          "allow_symbol_change": true,
          "studies": {studies_js},
          "overrides": {{
            "paneProperties.background": "#181a20",
            "paneProperties.backgroundType": "solid",
            "paneProperties.vertGridProperties.color": "#2b3139",
            "paneProperties.horzGridProperties.color": "#2b3139",
            "mainSeriesProperties.candleStyle.upColor": "#0ecb81",
            "mainSeriesProperties.candleStyle.downColor": "#f6465d",
            "mainSeriesProperties.candleStyle.borderUpColor": "#0ecb81",
            "mainSeriesProperties.candleStyle.borderDownColor": "#f6465d",
            "mainSeriesProperties.candleStyle.wickUpColor": "#0ecb81",
            "mainSeriesProperties.candleStyle.wickDownColor": "#f6465d"
          }}
        }});
      }})();
    </script>"""
    components.html(html, height=height + 8)

def render_tv_panel(asset: str) -> None:
    tv_mode = st.radio(
        "มุมมองกราฟ",
        ["กระดานไทย (Bitkub)", "กระดานโลก (Binance)", "เทียบ 2 กระดาน"],
        horizontal=True, key="tv_mode_bt",
    )
    local_sym = TV_LOCAL_SYMBOL.get(asset, f"BITKUB:{asset}THB")
    global_sym = TV_GLOBAL_SYMBOL.get(asset, f"BINANCE:{asset}USDT")

    if tv_mode == "กระดานไทย (Bitkub)":
        render_tradingview(local_sym, f"tv_bt_local_{asset}", 520,
                           studies=["RSI@tv-basicstudies"])
    elif tv_mode == "กระดานโลก (Binance)":
        render_tradingview(global_sym, f"tv_bt_global_{asset}", 520,
                           studies=["RSI@tv-basicstudies"])
    else:
        g1, g2 = st.columns(2)
        with g1:
            st.caption(f"🇹🇭 ราคาจริงฝั่งไทย — `{local_sym}`")
            render_tradingview(local_sym, f"tv_cmp_local_{asset}", 420)
        with g2:
            st.caption(f"🌐 ราคาโลก — `{global_sym}`")
            render_tradingview(global_sym, f"tv_cmp_global_{asset}", 420)


# =========================================================================
# LAYER 4 — DATA STATE & AUDIT TRAIL (Supabase-backed, local-file fallback)
# =========================================================================

try:
    from supabase import create_client, Client as _SupabaseClient
    HAS_SUPABASE_LIB = True
except ImportError:
    _SupabaseClient = None
    HAS_SUPABASE_LIB = False

_supabase_client: Optional["_SupabaseClient"] = None
_supabase_checked = False


def _get_supabase() -> Optional["_SupabaseClient"]:
    """คืน Supabase client ถ้าตั้งค่าไว้ครบ; ถ้าไม่มีคืน None (จะ fallback ไปไฟล์ local)"""
    global _supabase_client, _supabase_checked
    if _supabase_checked:
        return _supabase_client
    _supabase_checked = True
    if not HAS_SUPABASE_LIB:
        return None
    try:
        cfg = st.secrets.get("supabase", {})
        url, key = cfg.get("url", ""), cfg.get("key", "")
        if not (url and key):
            return None
        _supabase_client = create_client(url, key)
    except Exception:
        _supabase_client = None
    return _supabase_client


PROFILE_STATE_ENV_VAR = "XSPRING_PROFILE_STATE"

def profile_state_path() -> Path:
    return Path(os.environ.get(PROFILE_STATE_ENV_VAR) or (_HERE / "user_profiles.json"))

def load_profiles() -> dict[str, dict[str, str]]:
    if is_guest_mode():
        return {}
    sb = _get_supabase()
    if sb is not None:
        try:
            res = sb.table("user_profiles").select("*").execute()
            return {
                row["email"]: {
                    "display_name": row.get("display_name") or row["email"],
                    "avatar_b64": row.get("avatar_b64") or "",
                    "role": _normalize_role(row.get("role")),
                }
                for row in (res.data or [])
            }
        except Exception:
            pass

    p = profile_state_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    for v in raw.values():
        if isinstance(v, dict):
            v["role"] = _normalize_role(v.get("role"))
    return raw


def save_profile(email: str, display_name: str, avatar_b64: Optional[str] = None,
                 role: Optional[str] = None) -> None:
    if is_guest_mode():
        return
    email = str(email or "").strip().lower()
    existing = load_profiles()
    if role is None:
        prev_role = existing.get(email, {}).get("role")
        role = _normalize_role(prev_role) if prev_role else default_role_for_new_user(email, existing)
    else:
        role = _normalize_role(role)

    sb = _get_supabase()
    if sb is not None:
        try:
            sb.table("user_profiles").upsert({
                "email": email,
                "display_name": display_name,
                "avatar_b64": avatar_b64,
                "role": role,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            return
        except Exception:
            pass

    p = profile_state_path()
    profiles = existing
    profiles[email] = {"display_name": display_name, "avatar_b64": avatar_b64, "role": role}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def set_user_role(email: str, role: str) -> None:
    prof = load_profiles().get(email, {"display_name": email, "avatar_b64": ""})
    save_profile(email, prof.get("display_name", email), prof.get("avatar_b64", ""), role=role)


# =========================================================================
# LAYER 4b — ROLE-BASED PERMISSIONS
# =========================================================================

ROLE_VIEWER = "viewer"
ROLE_TRADER = "trader"
ROLE_ADMIN = "admin"
ROLE_ORDER = [ROLE_VIEWER, ROLE_TRADER, ROLE_ADMIN]
ROLE_LABEL_TH = {
    ROLE_VIEWER: "👁️ Viewer (ดูอย่างเดียว)",
    ROLE_TRADER: "💼 Trader (ซื้อขายได้)",
    ROLE_ADMIN: "🛡️ Admin (จัดการระบบ)",
}

# Guest / Demo mode: ใช้ session_state เท่านั้นและห้ามแตะ persistence backend
GUEST_ROLE = ROLE_TRADER

def is_guest_mode() -> bool:
    return bool(st.session_state.get("guest_mode", False))

def _guest_email() -> str:
    st.session_state.setdefault("guest_id", uuid.uuid4().hex[:8])
    return f"guest-{st.session_state['guest_id']}@guest.local"

def _start_guest_session() -> None:
    st.session_state.clear()
    st.session_state["guest_mode"] = True
    st.session_state["guest_id"] = uuid.uuid4().hex[:8]
    st.session_state["current_role"] = GUEST_ROLE
    st.rerun()

def _end_guest_session() -> None:
    # ล้าง session ทั้งหมดทันที — ข้อมูล Guest ไม่เคยถูกเขียนลง Supabase/ไฟล์
    st.session_state.clear()
    st.rerun()

ADMIN_EMAILS_ENV_VAR = "XSPRING_ADMIN_EMAILS"


def _admin_bootstrap_emails() -> set[str]:
    try:
        v = st.secrets.get("admin_emails", "")
    except Exception:
        v = ""
    v = str(v or os.environ.get(ADMIN_EMAILS_ENV_VAR, "")).strip().lower()
    return {e.strip() for e in v.split(",") if e.strip()}


def _normalize_role(role: Any) -> str:
    r = str(role or "").strip().lower()
    return r if r in ROLE_ORDER else ROLE_VIEWER


def role_at_least(role: str, min_role: str) -> bool:
    return ROLE_ORDER.index(_normalize_role(role)) >= ROLE_ORDER.index(min_role)


def default_role_for_new_user(email: str, existing_profiles: Mapping[str, dict]) -> str:
    email = str(email or "").strip().lower()
    # Public Google login: only explicitly configured admin_emails get Admin.
    # Never promote the first/only user to Admin automatically.
    if email in _admin_bootstrap_emails():
        return ROLE_ADMIN
    return ROLE_VIEWER


def current_role() -> str:
    return _normalize_role(st.session_state.get("current_role", ROLE_VIEWER))


def can_trade() -> bool:
    return role_at_least(current_role(), ROLE_TRADER)


def can_admin() -> bool:
    return role_at_least(current_role(), ROLE_ADMIN)


def can_edit_config() -> bool:
    return role_at_least(current_role(), ROLE_TRADER)


AUDIT_LOG_ENV_VAR = "XSPRING_AUDIT_LOG"
AUDIT_ACTOR_ENV_VAR = "XSPRING_USER"

def audit_log_path() -> Path:
    return Path(os.environ.get(AUDIT_LOG_ENV_VAR) or (_HERE / "audit_log.jsonl"))

def _json_safe(v: Any) -> Any:
    if v is None or isinstance(v, (str, bool)):
        return v
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return float(f"{f:.12g}") if math.isfinite(f) else None
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, Mapping):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return str(v)

def build_audit_records(prev: Optional[Mapping[str, Any]], current: Mapping[str, Any], *,
                        session_id: str, actor: str = "unknown",
                        now: Optional[datetime] = None) -> list[dict[str, Any]]:
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    base = {
        "ts": ts, "session_id": session_id, "actor": actor,
        "model_version": MODEL_VERSION, "config_sha256": CONFIG_INFO["sha256"],
    }
    if prev is None:
        return [{**base, "event": "session_start", "params": _json_safe(dict(current))}]
    records = []
    for key, new_val in current.items():
        old_val = prev.get(key)
        if old_val != new_val:
            records.append({**base, "event": "param_change", "param": key,
                            "old": _json_safe(old_val), "new": _json_safe(new_val)})
    return records

def append_audit_records(records: list[dict[str, Any]], path: Optional[Path] = None) -> None:
    if is_guest_mode() or not records:
        return

    sb = _get_supabase()
    if sb is not None:
        try:
            rows = [{
                "ts": r["ts"],
                "session_id": r.get("session_id"),
                "actor": r.get("actor"),
                "model_version": r.get("model_version"),
                "config_sha256": r.get("config_sha256"),
                "event": r.get("event"),
                "param": r.get("param"),
                "old_value": r.get("old"),
                "new_value": r.get("new"),
                "params": r.get("params"),
            } for r in records]
            sb.table("audit_log").insert(rows).execute()
            return
        except Exception:
            pass  # ตกไป fallback local

    p = Path(path) if path else audit_log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

def read_audit_records(path: Optional[Path] = None, limit: Optional[int] = None) -> list[dict[str, Any]]:
    if is_guest_mode():
        return []
    sb = _get_supabase()
    if sb is not None:
        try:
            q = sb.table("audit_log").select("*").order("ts", desc=True)
            if limit:
                q = q.limit(limit)
            res = q.execute()
            rows = res.data or []
            out = []
            for r in rows[::-1]:  # คืนเรียงเก่า->ใหม่ เหมือนของเดิม
                out.append({
                    "ts": r["ts"], "session_id": r.get("session_id"),
                    "actor": r.get("actor"), "model_version": r.get("model_version"),
                    "config_sha256": r.get("config_sha256"), "event": r.get("event"),
                    "param": r.get("param"), "old": r.get("old_value"),
                    "new": r.get("new_value"), "params": r.get("params"),
                })
            return out
        except Exception:
            pass  # ตกไป fallback local

    p = Path(path) if path else audit_log_path()
    if not p.is_file():
        return []
    out = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-limit:] if limit else out


SIM_STATE_ENV_VAR = "XSPRING_SIM_STATE"

def sim_state_path() -> Path:
    return Path(os.environ.get(SIM_STATE_ENV_VAR) or (_HERE / "sim_state.json"))

def save_sim_state(sim: Any, path: Optional[Path] = None) -> None:
    if is_guest_mode() or not isinstance(sim, dict):
        return

    sb = _get_supabase()
    if sb is not None:
        try:
            sb.table("sim_state").upsert({
                "actor": _current_actor(),
                "data": _json_safe(sim),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            return
        except Exception:
            pass  # ตกไป fallback local

    p = Path(path) if path else sim_state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(_json_safe(sim), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)

def load_sim_state(path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    if is_guest_mode():
        return None
    sb = _get_supabase()
    if sb is not None:
        try:
            res = (sb.table("sim_state")
                     .select("data")
                     .eq("actor", _current_actor())
                     .limit(1)
                     .execute())
            if res.data:
                d = res.data[0]["data"]
                if isinstance(d, dict) and d.get("current_date"):
                    try:
                        d["current_date"] = pd.to_datetime(d["current_date"])
                    except (ValueError, TypeError):
                        d.pop("current_date", None)
                return d
        except Exception:
            pass  # ตกไป fallback local

    p = Path(path) if path else sim_state_path()
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict):
        return None
    if d.get("current_date"):
        try:
            d["current_date"] = pd.to_datetime(d["current_date"])
        except (ValueError, TypeError):
            d.pop("current_date", None)
    return d


FAV_STATE_ENV_VAR = "XSPRING_FAV_STATE"

def fav_state_path() -> Path:
    return Path(os.environ.get(FAV_STATE_ENV_VAR) or (_HERE / "favorites.json"))

def save_favorites(favs: Any, path: Optional[Path] = None) -> None:
    if is_guest_mode():
        return
    clean = [s for s in (favs or []) if s in SUPPORTED_ASSETS]

    sb = _get_supabase()
    if sb is not None:
        try:
            sb.table("favorites").upsert({
                "actor": _current_actor(),
                "symbols": clean,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            return
        except Exception:
            pass  # ตกไป fallback local

    p = Path(path) if path else fav_state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean), encoding="utf-8")
    os.replace(tmp, p)

def load_favorites(path: Optional[Path] = None) -> list[str]:
    if is_guest_mode():
        return []
    sb = _get_supabase()
    if sb is not None:
        try:
            res = (sb.table("favorites")
                     .select("symbols")
                     .eq("actor", _current_actor())
                     .limit(1)
                     .execute())
            if res.data:
                d = res.data[0]["symbols"]
                return [s for s in d if s in SUPPORTED_ASSETS] if isinstance(d, list) else []
        except Exception:
            pass  # ตกไป fallback local

    p = Path(path) if path else fav_state_path()
    if not p.is_file():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [s for s in d if s in SUPPORTED_ASSETS] if isinstance(d, list) else []


def _current_actor() -> str:
    try:
        email = getattr(st.user, "email", None)
        if email:
            return str(email)
    except Exception:
        pass
    return os.environ.get(AUDIT_ACTOR_ENV_VAR) or "unknown"

def _audit_log_param_changes(current_params: Mapping[str, Any]) -> None:
    prev = st.session_state.get("audit_prev_params")
    if "audit_log" not in st.session_state:
        st.session_state.audit_log = []
    if "audit_session_id" not in st.session_state:
        st.session_state.audit_session_id = uuid.uuid4().hex[:12]

    if prev is not None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, new_val in current_params.items():
            old_val = prev.get(key)
            if old_val != new_val:
                st.session_state.audit_log.append({
                    "เวลา": now,
                    "พารามิเตอร์": key,
                    "ค่าเดิม": old_val,
                    "ค่าใหม่": new_val,
                })

    records = build_audit_records(prev, current_params,
                                  session_id=st.session_state.audit_session_id,
                                  actor=_current_actor())
    try:
        append_audit_records(records)
        st.session_state.audit_write_error = None
    except OSError as e:
        st.session_state.audit_write_error = f"{audit_log_path()}: {e}"
    st.session_state.audit_prev_params = dict(current_params)

def render_audit_log_sidebar():
    if not can_admin():
        return
    log = st.session_state.get("audit_log", [])
    title = f"🧾 Audit Log — การเปลี่ยนพารามิเตอร์ ({len(log)})"
    with st.expander(title, expanded=False):
        sb = _get_supabase()
        backend_label = "Supabase (cloud database)" if sb is not None else f"ไฟล์ local `{audit_log_path()}`"
        st.caption(
            f"Model v{MODEL_VERSION} · บันทึกอัตโนมัติทุกครั้งที่พารามิเตอร์ที่มีผล"
            f"ต่อการคำนวณเปลี่ยนค่า · เก็บลง: {backend_label} · ช่อง actor จะมีชื่อผู้ใช้ก็ต่อเมื่อแอปตั้ง "
            "authentication หรือกำหนด env XSPRING_USER (ไม่งั้นเป็น 'unknown')"
        )
        err = st.session_state.get("audit_write_error")
        if err:
            st.error(f"⚠️ เขียน audit log ไม่สำเร็จ — {err}")
        if not log:
            st.caption("ยังไม่มีการเปลี่ยนพารามิเตอร์ในเซสชันนี้")
            return
        for row in log[-10:][::-1]:
            st.markdown(
                f"<div class='xs-audit-row'>{row['เวลา']} — "
                f"<b>{row['พารามิเตอร์']}</b>: "
                f"{row['ค่าเดิม']} → {row['ค่าใหม่']}</div>",
                unsafe_allow_html=True,
            )
        st.download_button(
            "⬇️ ดาวน์โหลด Audit Log ฉบับเต็ม (CSV)",
            to_csv_bytes(pd.DataFrame(log)),
            "xspring_audit_log.csv",
            "text/csv",
            **WIDE,
        )


def render_role_admin_panel() -> None:
    """เรียกจากภายใน with st.sidebar เท่านั้น"""
    if not can_admin():
        return
    with st.expander("🛡️ จัดการสิทธิ์ผู้ใช้ (Admin)", expanded=False):
        profiles = load_profiles()
        if not profiles:
            st.caption("ยังไม่มีผู้ใช้ในระบบ")
            return
        my_email = str(getattr(st.user, "email", "") or "").strip().lower()
        for email, prof in sorted(profiles.items()):
            role = _normalize_role(prof.get("role"))
            c1, c2, c3 = st.columns([3, 3, 1])
            c1.markdown(
                f"**{prof.get('display_name', email)}**<br>"
                f"<span style='font-size:.72rem;color:#848e9c'>{email}</span>",
                unsafe_allow_html=True,
            )
            new_role = c2.selectbox(
                "role", ROLE_ORDER, index=ROLE_ORDER.index(role),
                format_func=lambda r: ROLE_LABEL_TH[r],
                key=f"role_sel_{email}", label_visibility="collapsed",
                disabled=(email == my_email),
            )
            if c3.button("💾", key=f"role_save_{email}",
                         disabled=(email == my_email or new_role == role)):
                set_user_role(email, new_role)
                st.rerun()
        st.caption("Admin เปลี่ยน role ของตัวเองไม่ได้")


# =========================================================================
# UNDO / ROLLBACK ออเดอร์ล่าสุด
# =========================================================================

UNDO_STACK_MAX = 20


def _push_undo_snapshot(sim: dict) -> None:
    """เก็บ snapshot ก่อน execute_order เพื่อย้อนกลับออเดอร์ของลูกค้าได้"""
    stack = st.session_state.setdefault("undo_stack", [])
    stack.append(copy.deepcopy(sim))
    if len(stack) > UNDO_STACK_MAX:
        stack.pop(0)


def can_undo() -> bool:
    return bool(st.session_state.get("undo_stack"))


def peek_last_order() -> Optional[dict[str, Any]]:
    """ดูออเดอร์ล่าสุดที่จะถูกยกเลิก ถ้ามี"""
    orders = st.session_state.get("sim", {}).get("orders", [])
    return orders[-1] if orders else None


def undo_last_order() -> Optional[dict[str, Any]]:
    """คืน sim กลับไปเป็น snapshot ก่อนออเดอร์ล่าสุด 1 รายการ"""
    stack = st.session_state.get("undo_stack", [])
    if not stack:
        return None

    current_sim = st.session_state.get("sim", {})
    cur_orders = current_sim.get("orders", [])

    prev_sim = stack.pop()
    prev_orders = prev_sim.get("orders", [])

    cancelled_order = cur_orders[-1] if len(cur_orders) > len(prev_orders) else None

    st.session_state["sim"] = prev_sim
    st.session_state["sim_steps"] = []
    return cancelled_order


def _do_undo() -> None:
    cancelled = undo_last_order()
    if cancelled:
        st.session_state["undo_toast"] = cancelled
    st.rerun(scope="app")


def render_undo_button(asset: str) -> None:
    """แสดงปุ่ม Undo ใต้ order panel เมื่อมีออเดอร์ของลูกค้าให้ย้อนกลับ"""
    last = peek_last_order()
    if not can_undo() or last is None:
        return

    side_th = last.get("ฝั่ง", "?")
    coin = last.get("เหรียญ", asset)
    amt = last.get("มูลค่า (บาท)", 0.0)
    with st.container(border=True):
        st.caption(f"ออเดอร์ล่าสุด: {side_th} {coin} · {fmt_baht(amt)}")
        st.button(
            "↩️ ยกเลิกออเดอร์ล่าสุด (Undo)",
            key="undo_last_order_btn",
            on_click=_do_undo,
            **WIDE,
        )

    toast = st.session_state.pop("undo_toast", None)
    if toast:
        st.toast(
            f"ยกเลิกออเดอร์ {toast.get('ฝั่ง', '')} {toast.get('เหรียญ', '')} "
            f"{fmt_baht(toast.get('มูลค่า (บาท)', 0.0))} สำเร็จ",
            icon="↩️",
        )


# =========================================================================
# LAYER 5 — APP
# =========================================================================

def build_sidebar() -> dict[str, Any]:
    RO = not can_edit_config()
    with st.sidebar:
        st.markdown("### ⚙️ Backtest Settings")
        if RO:
            st.info("🔒 บัญชี Viewer — ดูค่าพารามิเตอร์ได้ แก้ไขไม่ได้ ติดต่อ Admin เพื่อขอสิทธิ์ Trader")

        asset = st.selectbox("เลือกเหรียญ", SUPPORTED_ASSETS, key="bt_asset")
        if asset in STABLECOINS:
            st.warning(f"⚠️ {asset} เป็น Stablecoin — ใช้กลยุทธ์ Depeg Arbitrage + Carry Yield")

        with st.expander("🌐 กระดานซื้อขาย", expanded=True):
            global_exchange = st.selectbox(
                "กระดานโลกที่ใช้ Hedge",
                list(GLOBAL_EXCHANGE_FEE_PRESET.keys()),
                key="bt_global_exchange",
            )
            st.selectbox("กระดานไทยอ้างอิงราคาลูกค้า", LOCAL_EXCHANGES,
                         key="bt_local_exchange")

        with st.expander("📅 ช่วงเวลา Backtest", expanded=True):
            today = pd.Timestamp.now().date()
            preset_days = {
                "1 เดือน": 30, "3 เดือน": 90, "6 เดือน": 180,
                "1 ปี": 365, "3 ปี": 365 * 3, "5 ปี": 365 * 5,
            }
            preset = st.radio(
                "เลือกช่วงเวลาด่วน",
                ["กำหนดเอง", "1 เดือน", "3 เดือน", "6 เดือน", "1 ปี", "3 ปี", "5 ปี"],
                index=6, horizontal=True, key="bt_preset",
            )
            if preset != "กำหนดเอง":
                preset_start = today - pd.Timedelta(days=preset_days[preset])
                preset_end = today
            else:
                preset_start = today - pd.Timedelta(days=365 * 5)
                preset_end = today

            min_day = pd.Timestamp("2015-01-01").date()
            ca, cb = st.columns(2)
            with ca:
                start_date = st.date_input(
                    "เริ่มต้น", value=preset_start, min_value=min_day,
                    max_value=today, disabled=(preset != "กำหนดเอง"),
                )
            with cb:
                end_date = st.date_input(
                    "สิ้นสุด", value=preset_end, min_value=min_day,
                    max_value=today, disabled=(preset != "กำหนดเอง"),
                )
            if preset != "กำหนดเอง":
                start_date, end_date = preset_start, preset_end

        dates_ok = start_date < end_date
        if not dates_ok:
            st.error("❌ วันเริ่มต้นต้องมาก่อนวันสิ้นสุด")

        if FX_PROXY["enabled"] and FX_PROXY["url"]:
            use_fx_proxy = st.checkbox(
                f"ใช้ {FX_PROXY['symbol']} เป็น proxy ของ USD/THB ช่วงตลาด FX ปิด",
                value=False, key="bt_use_fx_proxy",
                help=("เสาร์-อาทิตย์/วันหยุดจะใช้ 'อัตราการเปลี่ยน' ของ proxy คูณเข้ากับ"
                      "เรทวันทำการล่าสุด (ไม่ใช้ระดับราคาของ proxy ตรง ๆ) · "
                      "ปิด = ใช้เรทค้างแบบเดิม"))
        else:
            use_fx_proxy = False

        with st.expander("💰 พารามิเตอร์ Dealer", expanded=True):
            trade_vol = comma_number_input(
                "ปริมาณซื้อขายลูกค้า/วัน (USD eq.)", value=100000, key="bt_trade_vol", disabled=RO)
            dealer_spread = st.number_input(
                "Dealer Spread ที่เก็บจากลูกค้า (%)",
                value=float(UI_DEFAULTS["dealer_spread_pct"]), step=0.1,
                key="bt_spread", disabled=RO) / 100

            if "bt_prev_gx" not in st.session_state:
                st.session_state.bt_prev_gx = global_exchange
            if "bt_hedge_fee" not in st.session_state:
                st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
            if "bt_hedge_fee_maker" not in st.session_state:
                st.session_state.bt_hedge_fee_maker = default_maker_fee_pct(global_exchange)
            if st.session_state.bt_prev_gx != global_exchange:
                st.session_state.bt_hedge_fee = GLOBAL_EXCHANGE_FEE_PRESET[global_exchange]
                st.session_state.bt_hedge_fee_maker = default_maker_fee_pct(global_exchange)
                st.session_state.bt_prev_gx = global_exchange

            hedge_fee_taker = st.number_input(
                "ค่าธรรมเนียม Global CEX — Taker (%)", key="bt_hedge_fee",
                step=0.01, disabled=RO) / 100
            hedge_fee_maker = st.number_input(
                "ค่าธรรมเนียม Global CEX — Maker (%)", key="bt_hedge_fee_maker",
                step=0.01, disabled=RO,
                help=("ค่าตั้งต้น = เท่า Taker จนกว่าจะตั้ง maker presetใน config.yaml "
                      "หรือแก้ช่องนี้ตามเทียร์บัญชีจริง")) / 100
            maker_ratio = st.slider(
                "สัดส่วน Hedge ที่ทำเป็น Maker / Limit (%)", 0, 100, 0,
                key="bt_maker_ratio",
                disabled=RO,
                help=("0 = hedgeแบบ Taker ทั้งหมด (โมเดลเดิม) · ยังไม่จำลองความเสี่ยง"
                      "ที่ Limit order ไม่ถูก fill จึงยิ่งสูงยิ่งมองโลกในแง่ดี")) / 100

            hedge_fee = blend_hedge_fee(hedge_fee_taker, hedge_fee_maker, maker_ratio)
            if maker_ratio > 0:
                st.caption(f"ค่าธรรมเนียม Hedge เฉลี่ยที่ใช้คำนวณ: **{hedge_fee * 100:.4f}%**")
            fx_limit_max = comma_number_input(
                "FX Limit ต่อเดือน (USD)", value=UI_DEFAULTS["fx_limit_usd"],
                min_value=1, key="bt_fx_limit", disabled=RO)
            local_premium = st.number_input(
                "Local Premium/Discount ฝั่งไทย (%)",
                value=float(UI_DEFAULTS["local_premium_pct"]), step=0.1,
                key="bt_local_premium", disabled=RO) / 100

        with st.expander("💳 ค่าธรรมเนียมกระดานไทย"):
            include_trading_fee_revenue = st.checkbox(
                "รวมรายได้ค่าธรรมเนียมซื้อขาย 0.25%", value=True, key="bt_inc_fee", disabled=RO)
            withdrawal_fee_markup_pct = st.slider(
                "Markup ค่าธรรมเนียมถอน (%)", 0, 200, 0, key="bt_wd_markup", disabled=RO) / 100
            settlements_per_day = st.number_input(
                "รอบถอนเหรียญให้ลูกค้า/วัน", value=1, min_value=1, step=1,
                key="bt_settle_per_day", disabled=RO)
            bank_type = st.selectbox(
                "ธนาคารปลายทางถอนบาท", ["SCB", "ธนาคารอื่น", "KTB (กรุงไทย)"],
                key="bt_bank", disabled=RO)

        with st.expander("🏦 สิทธิพิเศษ KTB", expanded=bank_type.startswith("KTB")):
            use_ktb_fx = st.checkbox(
                "ใช้เรทแลกเปลี่ยน USD/THB พิเศษจาก KTB", value=True, key="bt_use_ktb", disabled=RO)
            if use_ktb_fx:
                ktb_fx_spread_bps = st.number_input(
                    "ส่วนต่างเรทที่ดีกว่าตลาด (bps)", value=15.0, step=1.0,
                    min_value=0.0, key="bt_ktb_bps", disabled=RO)
            else:
                ktb_fx_spread_bps = 0.0
            ktb_wd_fee_thb = st.number_input(
                "ค่าธรรมเนียมถอนบาท KTB (บาท)", value=15.0, step=1.0,
                min_value=0.0, key="bt_ktb_wd", disabled=RO)

        if asset in STABLECOINS:
            with st.expander("🪙 กลยุทธ์ Stablecoin", expanded=True):
                peg_target = st.number_input(
                    "Peg Target (USD)", value=1.00, step=0.01, key="bt_peg", disabled=RO)
                depeg_capture_pct = st.slider(
                    "Depeg Arbitrage Capture (%)", 0, 100, 80, key="bt_depeg", disabled=RO) / 100
                carry_apy = st.number_input(
                    "Carry Yield APY (%)", value=4.0, step=0.5, key="bt_carry", disabled=RO) / 100
            slippage_sensitivity = 0.0
            market_depth_usd, impact_penalty = 0.0, 0.0
        else:
            with st.expander("📉 Execution Model", expanded=True):
                slippage_sensitivity = st.number_input(
                    "Slippage Sensitivity (% ของ Volatility)", value=10.0,
                    step=1.0, key="bt_slip", disabled=RO) / 100
                market_depth_usd = comma_number_input(
                    "Market Depth ฝั่งที่ต้องกิน (USD) — 0 = ปิด", value=0,
                    min_value=0, key="bt_depth",
                    disabled=RO,
                    help=("มูลค่า order book บน Global CEX ภายในช่วงราคาที่ใช้ประเมิน "
                          "ต้องหาจากกระดานจริงของเหรียญนี้ — ไม่มีค่ามาตรฐาน · "
                          "0 = ใช้ slippage แบบเดิม (สัดส่วนของ volatility อย่างเดียว)"))
                impact_penalty = st.number_input(
                    "Impact Penalty (% ราคาเสียเพิ่ม เมื่อออเดอร์กิน depth 100%)",
                    value=float(UI_DEFAULTS["impact_penalty_pct"]), step=0.1,
                    min_value=0.0, key="bt_impact_pen", disabled=RO,
                    help=("Slippage = Base + (Order ÷ Depth) × Penalty · ถ้านับ depth "
                          "ภายใน ±1% ของราคากลาง Penalty ≈ 0.5%")) / 100
            peg_target, depeg_capture_pct, carry_apy = 1.0, 0.0, 0.0

        st.divider()
        st.markdown("### 🏛️ งบดุลและ Flow")

        with st.expander("📥 Flow Assumptions", expanded=False):
            monthly_volume_thb = comma_number_input(
                "ปริมาณธุรกรรมลูกค้าต่อเดือน (THB)", value=80_000_000,
                min_value=0, key="fl_monthly_vol", disabled=RO)
            net_bias_pct = st.slider(
                "Net Flow Bias (+/-)", -100, 100, 15, key="fl_bias", disabled=RO) / 100
            flow_cv_pct = st.slider(
                "ความผันผวนของปริมาณต่อวัน (CV, %)", 10, 150, 50, key="fl_cv", disabled=RO) / 100
            settlement_days = st.number_input(
                "Settlement Lag (วัน)", value=1, min_value=1, max_value=10,
                step=1, key="fl_lag", disabled=RO)
            confidence = st.select_slider(
                "Confidence Level ของ Safety Stock",
                options=[90, 95, 99, 99.9], value=99, key="fl_conf", disabled=RO)
            z_alpha = Z_SCORE_MAP[confidence]

        with st.expander("💼 Capital Pool", expanded=False):
            total_capital_thb = comma_number_input(
                "เงินทุนสภาพคล่องรวม (THB)", value=150_000_000,
                min_value=0, key="cp_total_capital", disabled=RO)
            cex_margin_thb = comma_number_input(
                "เงินทุนบนกระดานโลก / CEX Margin (THB)", value=30_000_000,
                min_value=0, key="cp_cex_margin", disabled=RO)
            liab_thb = comma_number_input(
                "หนี้สินต่อลูกค้า (THB)", value=100_000_000,
                min_value=1, key="cp_liab", disabled=RO)
            cex_margin_asset = st.selectbox(
                "สินทรัพย์ Margin บนกระดานโลก",
                ["Stablecoin", "เหรียญเดียวกับที่เทรด"], key="cp_margin_asset", disabled=RO)
            cex_counterparty_haircut = st.number_input(
                "Counterparty Haircut (%)", value=2.0, step=0.5,
                min_value=0.0, key="cp_cp_haircut", disabled=RO) / 100

        with st.expander("⚖️ เกณฑ์เงินกองทุน ก.ล.ต.", expanded=False):
            is_custodian = st.checkbox(
                "เก็บรักษาทรัพย์สินลูกค้า", value=True, key="nc_custodian", disabled=RO)
            fixed_min_nc = (NC_FIXED_MIN_CUSTODIAN_THB if is_custodian
                            else NC_FIXED_MIN_NON_CUSTODIAN_THB)
            trading_risk_rate = st.number_input(
                "อัตรา NC ความเสี่ยงซื้อขาย (%)", value=2.0, step=0.1,
                min_value=0.0, key="nc_trading_rate", disabled=RO) / 100
            cold_foreign_rate = st.number_input(
                "อัตรา NC cold wallet ต่างประเทศ (%)", value=1.5, step=0.5,
                min_value=1.0, key="nc_cold_foreign", disabled=RO) / 100
            hot_wallet_pct = st.slider(
                "สัดส่วนสต็อกใน Hot Wallet (%)", 0, 100, 30, key="nc_hot", disabled=RO) / 100
            cold_domestic_split_pct = st.slider(
                "สัดส่วน Cold Wallet ฝากในประเทศ (%)", 0, 100, 80,
                key="nc_cold_dom", disabled=RO) / 100

        st.divider()
        _audit_log_param_changes(dict(
            asset=asset, global_exchange=global_exchange,
            start_date=str(start_date), end_date=str(end_date),
            trade_vol=trade_vol, dealer_spread=dealer_spread,
            hedge_fee=hedge_fee, hedge_fee_taker=hedge_fee_taker,
            hedge_fee_maker=hedge_fee_maker, maker_ratio=maker_ratio,
            market_depth_usd=market_depth_usd, impact_penalty=impact_penalty,
            use_fx_proxy=use_fx_proxy, fx_limit_max=fx_limit_max,
            local_premium=local_premium,
            include_trading_fee_revenue=include_trading_fee_revenue,
            withdrawal_fee_markup_pct=withdrawal_fee_markup_pct,
            bank_type=bank_type, use_ktb_fx=use_ktb_fx,
            ktb_fx_spread_bps=ktb_fx_spread_bps, ktb_wd_fee_thb=ktb_wd_fee_thb,
            slippage_sensitivity=slippage_sensitivity,
            monthly_volume_thb=monthly_volume_thb, net_bias_pct=net_bias_pct,
            flow_cv_pct=flow_cv_pct, settlement_days=settlement_days,
            confidence=confidence, total_capital_thb=total_capital_thb,
            cex_margin_thb=cex_margin_thb, liab_thb=liab_thb,
            cex_margin_asset=cex_margin_asset,
            cex_counterparty_haircut=cex_counterparty_haircut,
            is_custodian=is_custodian, trading_risk_rate=trading_risk_rate,
            cold_foreign_rate=cold_foreign_rate, hot_wallet_pct=hot_wallet_pct,
            cold_domestic_split_pct=cold_domestic_split_pct,
        ))
        render_audit_log_sidebar()
        render_role_admin_panel()

    daily_volume_thb = monthly_volume_thb / 30.0
    custody_rate_blended = blended_custody_rate(
        hot_wallet_pct, cold_domestic_split_pct, cold_foreign_rate)
    hot_wallet_cap_breach = ((liab_thb < HOT_WALLET_CAP_LIAB_THRESHOLD)
                             and (hot_wallet_pct > HOT_WALLET_CAP))

    return dict(
        asset=asset, global_exchange=global_exchange,
        start_date=start_date, end_date=end_date, dates_ok=dates_ok,
        trade_vol=trade_vol, dealer_spread=dealer_spread, hedge_fee=hedge_fee,
        hedge_fee_taker=hedge_fee_taker, hedge_fee_maker=hedge_fee_maker,
        maker_ratio=maker_ratio, market_depth_usd=market_depth_usd,
        impact_penalty=impact_penalty, use_fx_proxy=use_fx_proxy,
        fx_limit_max=fx_limit_max, local_premium=local_premium,
        include_trading_fee_revenue=include_trading_fee_revenue,
        withdrawal_fee_markup_pct=withdrawal_fee_markup_pct,
        settlements_per_day=settlements_per_day, bank_type=bank_type,
        use_ktb_fx=use_ktb_fx, ktb_fx_spread_bps=ktb_fx_spread_bps,
        ktb_wd_fee_thb=ktb_wd_fee_thb,
        peg_target=peg_target, depeg_capture_pct=depeg_capture_pct,
        carry_apy=carry_apy, slippage_sensitivity=slippage_sensitivity,
        monthly_volume_thb=monthly_volume_thb, daily_volume_thb=daily_volume_thb,
        net_bias_pct=net_bias_pct, flow_cv_pct=flow_cv_pct,
        settlement_days=settlement_days, confidence=confidence, z_alpha=z_alpha,
        total_capital_thb=total_capital_thb, cex_margin_thb=cex_margin_thb,
        liab_thb=liab_thb, cex_margin_asset=cex_margin_asset,
        cex_counterparty_haircut=cex_counterparty_haircut,
        is_custodian=is_custodian, fixed_min_nc=fixed_min_nc,
        trading_risk_rate=trading_risk_rate, cold_foreign_rate=cold_foreign_rate,
        hot_wallet_pct=hot_wallet_pct,
        cold_domestic_split_pct=cold_domestic_split_pct,
        custody_rate_blended=custody_rate_blended,
        hot_wallet_cap_breach=hot_wallet_cap_breach,
    )


# =========================================================================
# PHASE 2 — CORE BUSINESS VALUE
# Scenario / Stress · Historical Snapshot · Config Compare · PDF/Excel ·
# Sharpe / Sortino
# =========================================================================


def _backtest_frame(cfg: dict[str, Any], data: pd.DataFrame,
                    shock_pct: float = 0.0, shock_days: int = 0,
                    shock_path: Optional[np.ndarray] = None) -> pd.DataFrame:
    """สร้าง backtest ledger แบบ pure-ish เพื่อให้ baseline/scenario ใช้สูตรชุดเดียวกัน"""
    bt = data.copy()
    if shock_path is not None and len(shock_path) and not bt.empty:
        # ใช้เส้นทาง % รายวัน (เช่น preset วิกฤติจริง) แทน shock แบบแบนราบ
        n = min(len(shock_path), len(bt))
        mult = np.cumprod(1.0 + np.asarray(shock_path[:n], dtype=float) / 100.0)
        bt.iloc[:n, bt.columns.get_loc("Global_USD")] *= mult
    elif shock_pct and shock_days > 0 and not bt.empty:
        n = min(int(shock_days), len(bt))
        bt.iloc[:n, bt.columns.get_loc("Global_USD")] *= (1.0 + float(shock_pct))

    asset = cfg["asset"]
    trade_vol = float(cfg["trade_vol"])
    hedge_fee = float(cfg["hedge_fee"])
    bt["Local_THB"] = bt["Global_USD"] * bt["USDTHB"] * (1 + cfg["local_premium"])
    bt["Coin_Volume"] = trade_vol / bt["Global_USD"].replace(0, np.nan)
    bt["Gross_Notional_THB"] = bt["Coin_Volume"] * bt["Local_THB"]
    bt["Spread_Revenue_THB"] = bt["Gross_Notional_THB"] * cfg["dealer_spread"]
    bt["FX_Basis_PnL_THB"] = trade_vol * bt["USDTHB"] * cfg["local_premium"]
    bt["Hedge_Fee_Cost_THB"] = trade_vol * hedge_fee * bt["USDTHB"]
    bt["Hedge_Notional_USD"] = trade_vol * (1 + hedge_fee)
    bt["KTB_FX_Benefit_THB"] = trade_vol * bt["USDTHB"] * (cfg["ktb_fx_spread_bps"] / 10000.0)
    if asset in STABLECOINS:
        bt["Depeg_Deviation"] = cfg["peg_target"] - bt["Global_USD"]
        bt["Depeg_PnL_THB"] = bt["Coin_Volume"] * bt["Depeg_Deviation"] * bt["USDTHB"] * cfg["depeg_capture_pct"]
        bt["Carry_Yield_THB"] = trade_vol * (cfg["carry_apy"] / 365) * bt["USDTHB"]
        bt["Slippage_Cost_THB"] = 0.0
    else:
        bt["Depeg_Deviation"] = 0.0
        bt["Depeg_PnL_THB"] = 0.0
        bt["Carry_Yield_THB"] = 0.0
        impact_rate = market_impact_rate(trade_vol, cfg["market_depth_usd"], cfg["impact_penalty"])
        bt["Slippage_Cost_THB"] = (trade_vol * bt["Volatility_Pct"] * cfg["slippage_sensitivity"] * bt["USDTHB"]
                                   + trade_vol * impact_rate * bt["USDTHB"])
    bt["Trading_Fee_Revenue_THB"] = (bt["Gross_Notional_THB"] * LOCAL_TRADING_FEE_PCT
                                      if cfg["include_trading_fee_revenue"] else 0.0)
    wd_network_cost = WITHDRAWAL_FEE_TABLE.get(asset, 0.0) * bt["Global_USD"] * bt["USDTHB"] * cfg["settlements_per_day"]
    bt["Withdrawal_Fee_Markup_Revenue_THB"] = wd_network_cost * cfg["withdrawal_fee_markup_pct"]
    bt["THB_WD_Fee"] = bt["USDTHB"].map(lambda fx: calc_thb_withdrawal_fee(
        trade_vol * fx, cfg["bank_type"], cfg["ktb_wd_fee_thb"]))
    bt["THB_Fee_Markup_Revenue_THB"] = bt["THB_WD_Fee"] * cfg["settlements_per_day"] * cfg["withdrawal_fee_markup_pct"]
    bt["Fee_Revenue_THB"] = bt["Trading_Fee_Revenue_THB"] + bt["Withdrawal_Fee_Markup_Revenue_THB"] + bt["THB_Fee_Markup_Revenue_THB"]
    bt["Revenue_THB"] = (bt["Spread_Revenue_THB"] + bt["FX_Basis_PnL_THB"] + bt["Fee_Revenue_THB"]
                         + bt["Depeg_PnL_THB"] + bt["Carry_Yield_THB"] + bt["KTB_FX_Benefit_THB"])
    bt["Cost_THB"] = bt["Hedge_Fee_Cost_THB"] + bt["Slippage_Cost_THB"]
    bt["Daily_PnL_THB"] = bt["Revenue_THB"] - bt["Cost_THB"]
    allowed, usage = apply_fx_limit(bt["Hedge_Notional_USD"], bt.index, cfg["fx_limit_max"])
    bt["Trade_Allowed"] = allowed
    bt["Current_FX_Usage"] = usage
    bt["FX_Limit_Hit"] = 1 - allowed
    bt["Actual_Daily_PnL"] = np.where(allowed == 1, bt["Daily_PnL_THB"], 0.0)
    bt["Actual_Cum_PnL"] = bt["Actual_Daily_PnL"].cumsum()
    return bt


def _performance_ratios(pnl: pd.Series) -> tuple[float, float]:
    r = pd.Series(pnl, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < 2 or float(r.std(ddof=1)) == 0:
        return 0.0, 0.0
    mean = float(r.mean())
    std = float(r.std(ddof=1))
    sharpe = mean / std * math.sqrt(252.0)
    downside = r[r < 0]
    dstd = float(downside.std(ddof=1)) if len(downside) >= 2 else 0.0
    sortino = mean / dstd * math.sqrt(252.0) if dstd > 0 else 0.0
    return sharpe, sortino


def _backtest_metrics(bt: pd.DataFrame) -> dict[str, Any]:
    traded = bt[bt["Trade_Allowed"] == 1]
    pnl = bt["Actual_Daily_PnL"]
    total = float(bt["Actual_Cum_PnL"].iloc[-1]) if not bt.empty else 0.0
    peak = bt["Actual_Cum_PnL"].cummax() if not bt.empty else pd.Series(dtype=float)
    dd = float((bt["Actual_Cum_PnL"] - peak).min()) if not bt.empty else 0.0
    sharpe, sortino = _performance_ratios(pnl)
    traded_days = int(bt["Trade_Allowed"].sum()) if not bt.empty else 0
    win_days = int((pnl > 0).sum()) if not bt.empty else 0
    return {
        "net_pnl": total,
        "revenue": float(traded["Revenue_THB"].sum()) if not traded.empty else 0.0,
        "cost": float(traded["Cost_THB"].sum()) if not traded.empty else 0.0,
        "max_drawdown": dd,
        "win_rate": win_days / traded_days * 100 if traded_days else 0.0,
        "fx_hit_days": int(bt["FX_Limit_Hit"].sum()) if not bt.empty else 0,
        "traded_days": traded_days,
        "sharpe": sharpe,
        "sortino": sortino,
    }


def _scenario_result(cfg: dict[str, Any], data: pd.DataFrame, shock_pct: float = 0.0,
                     shock_days: int = 0, shock_path: Optional[np.ndarray] = None) -> dict[str, Any]:
    bt = _backtest_frame(cfg, data, shock_pct=shock_pct, shock_days=shock_days, shock_path=shock_path)
    return {"frame": bt, **_backtest_metrics(bt)}


def _snapshot_payload(cfg: dict[str, Any], data: pd.DataFrame) -> dict[str, Any]:
    built = build_dealer_ctx(cfg, data)
    if built is None:
        return {}
    ctx, target = built
    asset = cfg["asset"]
    last = data.iloc[-1]
    nc = nc_snapshot(target, ctx["capital"], ctx["cex_margin"], ctx["liab"],
                     ctx["h_crypto"], ctx["h_cex"], ctx["fixed_min_nc"],
                     ctx["trading_risk_rate"], ctx["daily_volume_thb"], ctx["custody_rate"])
    return {
        "snapshot_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": _current_actor(), "asset": asset,
        "price_usd": float(last["Global_USD"]), "usdthb": float(last["USDTHB"]),
        "required_stock_thb": float(target), "total_capital_thb": float(ctx["capital"]),
        "cex_margin_thb": float(ctx["cex_margin"]), "liab_thb": float(ctx["liab"]),
        "nc_actual": float(nc["actual"]), "nc_required": float(nc["required"]),
        "nc_buffer": float(nc["buffer"]), "config": _json_safe(cfg),
    }


def save_nc_snapshot(cfg: dict[str, Any], data: pd.DataFrame) -> bool:
    payload = _snapshot_payload(cfg, data)
    if not payload:
        return False
    st.session_state.setdefault("nc_snapshots", []).append(payload)
    st.session_state["nc_snapshots"] = st.session_state["nc_snapshots"][-100:]
    if is_guest_mode():
        return False
    sb = _get_supabase()
    if sb is not None:
        try:
            sb.table("nc_snapshots").insert(payload).execute()
            return True
        except Exception:
            pass
    p = _HERE / "nc_snapshots.json"
    try:
        old = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []
        old = old if isinstance(old, list) else []
        old.append(payload)
        p.write_text(json.dumps(old[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return False


def load_nc_snapshots(limit: int = 100) -> list[dict[str, Any]]:
    if is_guest_mode():
        return list(st.session_state.get("nc_snapshots", []))[-limit:]
    sb = _get_supabase()
    if sb is not None:
        try:
            res = (sb.table("nc_snapshots").select("*").order("snapshot_at", desc=True).limit(limit).execute())
            return list(reversed(res.data or []))
        except Exception:
            pass
    return list(st.session_state.get("nc_snapshots", []))[-limit:]


def _config_for_compare(cfg: dict[str, Any]) -> dict[str, Any]:
    keys = ["asset", "dealer_spread", "hedge_fee", "local_premium", "fx_limit_max",
            "trade_vol", "slippage_sensitivity", "market_depth_usd", "impact_penalty",
            "monthly_volume_thb", "total_capital_thb", "cex_margin_thb", "liab_thb"]
    return {k: cfg.get(k) for k in keys}


# =========================================================================
# PHASE 2.5 — Monte Carlo · Crisis Replay · Correlation · Hedge Comparator
# =========================================================================

CRISIS_PRESETS: dict[str, dict[str, Any]] = {
    "LUNA / UST Collapse (พ.ค. 2022)": {
        "desc": "Terra/UST depeg ลาก BTC/ETH ร่วงแรงต่อเนื่องราว 10 วัน (ค่าประมาณจากทิศทางตลาดช่วงนั้น)",
        "daily_pct": [-2, -3, -5, -8, -6, -4, -3, 2, -2, 1],
    },
    "FTX Collapse (พ.ย. 2022)": {
        "desc": "ข่าว FTX ล้มละลายทำให้ตลาดคริปโทร่วงยาวและผันผวนสูงหลายวันติด",
        "daily_pct": [-4, -10, -5, -3, 2, -2, -3, 1, -2, 1, 2, -1],
    },
    "COVID Black Thursday (มี.ค. 2020)": {
        "desc": "BTC ร่วงกว่า 40% ภายในไม่กี่วันจาก panic sell-off ทั่วตลาดการเงินโลก",
        "desc_short": "แรงและเร็ว",
        "daily_pct": [-39, -15, 8, 5, -3],
    },
    "Crypto Winter 2018": {
        "desc": "ตลาดหมีลากยาวทั้งปี ราคาร่วงต่อเนื่องแบบค่อยเป็นค่อยไป ไม่มีวันเดียวที่พังหนัก",
        "daily_pct": [-3, -2, -4, -2, -3, -1, -2, -3, -1, -2, -3, -1,
                      -2, -4, -2, -1, -3, -2, -1, -2],
    },
}


def _monte_carlo_pnl(daily_pnl: pd.Series, n_sims: int, n_days: int,
                     method: str, seed: int, n_day_slices: int = 25,
                     n_bins: int = 40) -> dict[str, Any]:
    """Bootstrap หรือสุ่ม normal จาก Daily P&L จริงของ baseline เพื่อทำ fan chart
    + เตรียมข้อมูล 3D surface: กระจายตัวของ P&L ข้ามหลายวัน (ไม่ใช่แค่วันสุดท้าย)"""
    r = pd.Series(daily_pnl, dtype=float).replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
    if len(r) < 10:
        return {}
    rng = np.random.default_rng(int(seed))
    n_sims, n_days = int(n_sims), int(n_days)
    if method == "bootstrap":
        idx = rng.integers(0, len(r), size=(n_sims, n_days))
        sims = r[idx]
    else:
        mu, sigma = float(r.mean()), float(r.std())
        sims = rng.normal(mu, sigma, size=(n_sims, n_days))
    cum = np.cumsum(sims, axis=1)
    percentiles = {p: np.percentile(cum, p, axis=0) for p in (5, 25, 50, 75, 95)}
    final = cum[:, -1]

    # ---- เตรียมข้อมูลกราฟ 3D: histogram ของ P&L ในแต่ละ "วันตัดขวาง" ----
    day_idx = np.unique(np.linspace(0, n_days - 1, min(n_day_slices, n_days)).astype(int))
    lo, hi = np.percentile(cum[:, day_idx], [0.5, 99.5])
    if lo >= hi:
        hi = lo + 1.0
    bin_edges = np.linspace(lo, hi, n_bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    z_matrix = np.zeros((len(day_idx), n_bins))
    for i, di in enumerate(day_idx):
        counts, _ = np.histogram(cum[:, di], bins=bin_edges)
        z_matrix[i] = counts

    return {
        "percentiles": percentiles,
        "final_dist": final,
        "prob_loss_pct": float((final < 0).mean() * 100),
        "var95_final": float(max(0.0, -np.percentile(final, 5))),
        "expected_final": float(final.mean()),
        "best_final": float(final.max()),
        "worst_final": float(final.min()),
        "n_days": n_days,
        "n_sims": n_sims,
        "surface_days": (day_idx + 1).tolist(),
        "surface_bin_centers": bin_centers.tolist(),
        "surface_z": z_matrix.tolist(),
    }


def _render_monte_carlo(cfg: dict[str, Any], data: pd.DataFrame,
                        bt_baseline: Optional[pd.DataFrame]) -> None:
    with st.expander("🎲 Monte Carlo P&L Simulator", expanded=False):
        st.caption(
            "Bootstrap/สุ่ม resample จาก Daily P&L จริงของ baseline backtest "
            "เพื่อดูช่วงความน่าจะเป็นของกำไรในอนาคต — ไม่ใช่การพยากรณ์ราคา"
        )
        bt = bt_baseline if bt_baseline is not None else _backtest_frame(cfg, data)
        c1, c2, c3, c4 = st.columns(4)
        n_sims = c1.number_input("จำนวนรอบจำลอง", value=1000, min_value=100,
                                 max_value=5000, step=100, key="mc_nsims")
        n_days = c2.number_input("จำนวนวันข้างหน้า", value=90, min_value=10,
                                 max_value=365, step=10, key="mc_ndays")
        method = c3.selectbox(
            "วิธีสุ่ม", ["bootstrap", "normal"],
            format_func=lambda x: "Bootstrap (จากข้อมูลจริง)" if x == "bootstrap"
                                  else "Normal Distribution (GBM-like)",
            key="mc_method")
        seed = c4.number_input("Seed", value=7, step=1, key="mc_seed")

        if st.button("🎲 Run Monte Carlo", key="mc_run", **WIDE):
            st.session_state["mc_result"] = _monte_carlo_pnl(
                bt["Actual_Daily_PnL"], n_sims, n_days, method, seed)

        res = st.session_state.get("mc_result")
        if res:
            k = st.columns(4)
            metric_card(k[0], "Expected P&L (คาดหวัง)",
                       fmt_baht(res["expected_final"], True), res["expected_final"])
            metric_card(k[1], f"VaR 95% ({res['n_days']} วัน)",
                       fmt_baht(res["var95_final"]), -abs(res["var95_final"]))
            metric_card(k[2], "โอกาสขาดทุน", f"{res['prob_loss_pct']:.1f}%",
                       -1 if res["prob_loss_pct"] > 50 else 0)
            metric_card(k[3], "Best / Worst Case",
                       f"{fmt_baht(res['best_final'], True)} / {fmt_baht(res['worst_final'], True)}")

            x = list(range(1, res["n_days"] + 1))
            pct = res["percentiles"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=x + x[::-1], y=list(pct[95]) + list(pct[5])[::-1],
                fill="toself", fillcolor="rgba(14,203,129,0.10)",
                line=dict(width=0), name="P5–P95", hoverinfo="skip"))
            fig.add_trace(go.Scatter(
                x=x + x[::-1], y=list(pct[75]) + list(pct[25])[::-1],
                fill="toself", fillcolor="rgba(14,203,129,0.22)",
                line=dict(width=0), name="P25–P75", hoverinfo="skip"))
            fig.add_trace(go.Scatter(
                x=x, y=pct[50], line=dict(color="#0ecb81", width=2.5), name="Median (P50)"))
            fig.add_hline(y=0, line=dict(color="#848e9c", dash="dot"))
            fig.update_layout(
                template="plotly_dark", height=440, hovermode="x unified",
                margin=dict(t=30, b=20), yaxis_title="Cumulative P&L (THB)",
                xaxis_title="วันข้างหน้า", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=1.02, yanchor="bottom"))
            st.plotly_chart(fig, **WIDE)

            show_3d = st.checkbox("🌐 แสดงแบบ 3D (กระจายตัวของ P&L ข้ามหลายวัน)",
                                  value=True, key="mc_3d_toggle")

            if show_3d and res.get("surface_z"):
                days_arr = res["surface_days"]
                bins_arr = res["surface_bin_centers"]
                z = np.array(res["surface_z"])  # shape (n_day_slices, n_bins)
                fig_3d = go.Figure(data=[go.Surface(
                    x=days_arr, y=bins_arr, z=z.T,
                    colorscale="Rainbow", showscale=True,
                    colorbar=dict(title="ความถี่ (จำนวนรอบ)", thickness=12),
                    hovertemplate=("วันที่ %{x}<br>P&L: %{y:,.0f} THB<br>"
                                   "ความถี่: %{z}<extra></extra>"),
                )])
                fig_3d.update_layout(
                    title=dict(text="การกระจายตัวของ P&L ข้ามหลายวัน (3D)", font=dict(size=14)),
                    scene=dict(
                        xaxis_title="วันข้างหน้า",
                        yaxis_title="Cumulative P&L (THB)",
                        zaxis_title="ความถี่ (จำนวนรอบ)",
                        bgcolor="#181a20",
                    ),
                    template="plotly_dark", height=600,
                    margin=dict(l=0, r=0, b=0, t=40),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig_3d, **WIDE)
                st.caption(
                    "หมุน/ซูมเพื่อดู: แกน X = วันข้างหน้า, แกน Y = ระดับ Cumulative P&L (THB), "
                    "แกน Z/สี = ความถี่ที่ผลจำลองตกอยู่ระดับนั้น — เนินสูงตรงไหนคือผลลัพธ์ที่เป็นไปได้มากที่สุด "
                    "ณ วันนั้น สังเกตได้ว่าฐานการกระจายจะกว้างขึ้นเมื่อวันเวลาผ่านไป (ความไม่แน่นอนสะสม)"
                )
            else:
                fig_h = go.Figure(go.Histogram(x=res["final_dist"], nbinsx=50,
                                              marker_color="#0ecb81", opacity=0.8))
                fig_h.add_vline(x=0, line=dict(color="#f6465d", dash="dash"))
                fig_h.update_layout(
                    template="plotly_dark", height=280, margin=dict(t=20, b=20),
                    title=dict(text=f"การกระจายตัวของ P&L ที่วันที่ {res['n_days']}", font=dict(size=13)),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_h, **WIDE)


def _render_crisis_replay(cfg: dict[str, Any], data: pd.DataFrame,
                          bt_baseline: Optional[pd.DataFrame]) -> None:
    with st.expander("🔥 Historical Crisis Replay", expanded=False):
        st.caption(
            "จำลองราคาช่วงต้นของ backtest ให้เคลื่อนไหวตาม pattern เหตุการณ์วิกฤติจริงในอดีต "
            "(ค่าประมาณทิศทาง/ขนาดความรุนแรง ไม่ใช่ราคาย้อนหลังที่แม่นยำ 100%)"
        )
        names = list(CRISIS_PRESETS.keys())
        pick = st.selectbox("เลือกเหตุการณ์", names, key="crisis_pick")
        preset = CRISIS_PRESETS[pick]
        st.caption(f"📌 {preset['desc']}")
        path = preset["daily_pct"]
        cum_total = (float(np.prod([1 + p / 100 for p in path])) - 1) * 100
        st.caption(f"ระยะเวลา {len(path)} วัน · ผลรวมราคาโดยประมาณ {cum_total:+.1f}%")

        if st.button("🔥 Run Crisis Replay", key="crisis_run", **WIDE):
            st.session_state["crisis_result"] = _scenario_result(
                cfg, data, shock_path=np.array(path, dtype=float))
            st.session_state["crisis_name"] = pick

        cr = st.session_state.get("crisis_result")
        if cr:
            base = _backtest_metrics(bt_baseline if bt_baseline is not None else _backtest_frame(cfg, data))
            st.markdown(f"**ผลลัพธ์: {st.session_state.get('crisis_name', '')}**")
            st.dataframe(pd.DataFrame([
                {"Metric": "Net P&L", "Baseline": base["net_pnl"], "Crisis": cr["net_pnl"],
                 "Δ": cr["net_pnl"] - base["net_pnl"]},
                {"Metric": "Max Drawdown", "Baseline": base["max_drawdown"], "Crisis": cr["max_drawdown"],
                 "Δ": cr["max_drawdown"] - base["max_drawdown"]},
                {"Metric": "Sharpe", "Baseline": base["sharpe"], "Crisis": cr["sharpe"],
                 "Δ": cr["sharpe"] - base["sharpe"]},
                {"Metric": "Sortino", "Baseline": base["sortino"], "Crisis": cr["sortino"],
                 "Δ": cr["sortino"] - base["sortino"]},
                {"Metric": "FX Limit Hit (days)", "Baseline": base["fx_hit_days"], "Crisis": cr["fx_hit_days"],
                 "Δ": cr["fx_hit_days"] - base["fx_hit_days"]},
            ]), **WIDE)

            n_show = len(path) + 5
            fig = go.Figure(go.Scatter(
                x=cr["frame"].index[:n_show], y=cr["frame"]["Global_USD"].iloc[:n_show],
                line=dict(color="#f6465d", width=2), name="ราคาช่วง Crisis"))
            fig.update_layout(
                template="plotly_dark", height=280, margin=dict(t=20, b=20),
                title=dict(text="ราคาสินทรัพย์ช่วงเกิด Crisis (Simulated)", font=dict(size=13)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, **WIDE)


def _hedge_strategy_variants(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    taker = cfg["hedge_fee_taker"]
    maker = cfg["hedge_fee_maker"]
    return {
        "100% Taker (Instant Hedge)": dict(hedge_fee=taker, lag_days=0, lag_mult=0.0),
        "70% Maker / 30% Taker": dict(hedge_fee=blend_hedge_fee(taker, maker, 0.7), lag_days=0, lag_mult=0.0),
        "Delayed Hedge (lag 1 วัน)": dict(hedge_fee=taker, lag_days=1, lag_mult=1.0),
        "Delayed Hedge (lag 3 วัน)": dict(hedge_fee=taker, lag_days=3, lag_mult=1.0),
    }


def _backtest_frame_hedge_variant(cfg: dict[str, Any], data: pd.DataFrame,
                                  variant: dict[str, Any]) -> pd.DataFrame:
    """สร้าง backtest ตาม hedge strategy variant; Delayed Hedge ประมาณต้นทุนจาก
    adverse price move ระหว่างช่วงที่ยังไม่ได้ hedge (ยิ่ง lag นาน ยิ่งเสี่ยงราคาขยับสวนทาง)"""
    c2 = dict(cfg)
    c2["hedge_fee"] = variant["hedge_fee"]
    bt = _backtest_frame(c2, data)
    lag, mult = int(variant.get("lag_days", 0)), float(variant.get("lag_mult", 0.0))
    if lag > 0 and mult > 0:
        adverse_move = bt["Global_USD"].pct_change(periods=lag).abs().fillna(0.0)
        extra_cost = float(c2["trade_vol"]) * adverse_move * bt["USDTHB"] * mult
        bt["Cost_THB"] = bt["Cost_THB"] + extra_cost
        bt["Daily_PnL_THB"] = bt["Revenue_THB"] - bt["Cost_THB"]
        bt["Actual_Daily_PnL"] = np.where(bt["Trade_Allowed"] == 1, bt["Daily_PnL_THB"], 0.0)
        bt["Actual_Cum_PnL"] = bt["Actual_Daily_PnL"].cumsum()
    return bt


def _render_hedge_comparator(cfg: dict[str, Any], data: pd.DataFrame) -> None:
    with st.expander("⚖️ Hedge Strategy Comparator", expanded=False):
        st.caption(
            "เทียบผลลัพธ์ของกลยุทธ์ Hedge หลายแบบบนข้อมูลราคาชุดเดียวกัน · "
            "Delayed Hedge เป็นแบบจำลองประมาณต้นทุนจาก adverse price move "
            "ระหว่างที่ยังไม่ได้ hedge ไม่ใช่การจำลอง order book จริง"
        )
        variants = _hedge_strategy_variants(cfg)
        chosen = st.multiselect("เลือกกลยุทธ์ที่จะเทียบ", list(variants.keys()),
                                default=list(variants.keys()), key="hc_pick")
        if st.button("⚖️ Run Comparison", key="hc_run", **WIDE):
            results = {}
            for name in chosen:
                bt_v = _backtest_frame_hedge_variant(cfg, data, variants[name])
                m = _backtest_metrics(bt_v)
                m["frame"] = bt_v
                results[name] = m
            st.session_state["hc_results"] = results

        res = st.session_state.get("hc_results")
        if res:
            rows = [{"กลยุทธ์": k, "Net P&L": v["net_pnl"], "Total Cost": v["cost"],
                    "Max DD": v["max_drawdown"], "Sharpe": v["sharpe"], "Sortino": v["sortino"]}
                    for k, v in res.items()]
            st.dataframe(pd.DataFrame(rows).sort_values("Net P&L", ascending=False), **WIDE)

            colors = ["#0ecb81", "#3B82F6", "#fcd535", "#f6465d", "#9945FF"]
            fig = go.Figure()
            for i, (name, v) in enumerate(res.items()):
                fig.add_trace(go.Scatter(
                    x=v["frame"].index, y=v["frame"]["Actual_Cum_PnL"],
                    name=name, line=dict(color=colors[i % len(colors)], width=2)))
            fig.update_layout(
                template="plotly_dark", height=440, hovermode="x unified",
                margin=dict(t=30, b=20), yaxis_title="Cumulative P&L (THB)",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=1.02, yanchor="bottom"))
            st.plotly_chart(fig, **WIDE)


def _phase2_excel_bytes(frames: dict[str, pd.DataFrame], summary: pd.DataFrame) -> bytes:
    from openpyxl import Workbook
    from openpyxl.utils.dataframe import dataframe_to_rows
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    for row in dataframe_to_rows(summary, index=False, header=True): ws.append(row)
    for name, frame in frames.items():
        ws2 = wb.create_sheet(str(name)[:31])
        for row in dataframe_to_rows(frame.reset_index(), index=False, header=True): ws2.append(row)
    out = BytesIO(); wb.save(out); return out.getvalue()


def _phase2_pdf_bytes(title: str, summary: pd.DataFrame) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    out = BytesIO(); doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet(); story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    story.append(Paragraph(f"Model v{MODEL_VERSION} · Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}", styles["Normal"]))
    story.append(Spacer(1, 12))
    data = [list(summary.columns)] + summary.astype(str).values.tolist()
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#20242b")),
                           ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
                           ("FONTSIZE", (0,0), (-1,-1), 7), ("VALIGN", (0,0), (-1,-1), "TOP")]))
    story.append(t); doc.build(story); return out.getvalue()


def render_phase2_tools_top(cfg: dict[str, Any], data: pd.DataFrame,
                            bt_baseline: Optional[pd.DataFrame] = None) -> None:
    """เครื่องมือที่โชว์เร็ว ต่อจาก Performance Summary — Stress / Monte Carlo / Crisis / Hedge"""
    if data.empty:
        return
    with st.expander("🧪 Phase 2 — Scenario / Stress Test", expanded=False):
        st.caption("จำลอง shock ราคาสินทรัพย์ในช่วงต้นของช่วง backtest โดยไม่แก้ sim wallet จริง")
        c1, c2, c3 = st.columns(3)
        shock_pct = c1.number_input("Shock ราคา (%)", value=-30.0, step=5.0, key="p2_shock_pct")
        shock_days = c2.number_input("ระยะเวลา shock (วัน)", value=min(30, len(data)), min_value=1, max_value=max(1, len(data)), step=1, key="p2_shock_days")
        if c3.button("🧪 Run Stress Test", key="p2_run_stress", **WIDE):
            st.session_state["p2_stress_result"] = _scenario_result(cfg, data, shock_pct / 100.0, int(shock_days))
        sr = st.session_state.get("p2_stress_result")
        if sr:
            base = _backtest_metrics(bt_baseline if bt_baseline is not None else _backtest_frame(cfg, data))
            st.dataframe(pd.DataFrame([
                {"Metric":"Net P&L", "Baseline":base["net_pnl"], "Stress":sr["net_pnl"], "Δ":sr["net_pnl"]-base["net_pnl"]},
                {"Metric":"Max Drawdown", "Baseline":base["max_drawdown"], "Stress":sr["max_drawdown"], "Δ":sr["max_drawdown"]-base["max_drawdown"]},
                {"Metric":"Sharpe", "Baseline":base["sharpe"], "Stress":sr["sharpe"], "Δ":sr["sharpe"]-base["sharpe"]},
                {"Metric":"Sortino", "Baseline":base["sortino"], "Stress":sr["sortino"], "Δ":sr["sortino"]-base["sortino"]},
                {"Metric":"FX Limit Hit (days)", "Baseline":base["fx_hit_days"], "Stress":sr["fx_hit_days"], "Δ":sr["fx_hit_days"]-base["fx_hit_days"]},
            ]), **WIDE)

    _render_monte_carlo(cfg, data, bt_baseline)
    _render_crisis_replay(cfg, data, bt_baseline)
    _render_hedge_comparator(cfg, data)


def render_phase2_tools_bottom(cfg: dict[str, Any], data: pd.DataFrame,
                               bt_baseline: Optional[pd.DataFrame] = None) -> None:
    """เครื่องมือที่ควรอยู่ท้ายหน้า ต่อจาก P&L รายเดือน / Daily Ledger"""
    if data.empty:
        return
    with st.expander("🆚 Compare Config A / B", expanded=False):
        saved = st.session_state.setdefault("p2_configs", {})
        name = st.text_input("ชื่อ Config ที่ต้องการบันทึก", value="Config A", key="p2_cfg_name")
        if st.button("💾 บันทึก Config ปัจจุบัน", key="p2_save_cfg", **WIDE):
            saved[name.strip() or f"Config {len(saved)+1}"] = _config_for_compare(cfg)
            st.session_state["p2_configs"] = saved
        if saved:
            chosen = st.multiselect("เลือก Config ที่จะเปรียบเทียบ", list(saved.keys()), default=list(saved.keys())[:2], max_selections=4, key="p2_compare_sel")
            if len(chosen) >= 2:
                rows=[]
                for nm in chosen:
                    c = dict(cfg); c.update(saved[nm])
                    m = _backtest_metrics(_backtest_frame(c, data))
                    rows.append({"Config":nm, "Net P&L":m["net_pnl"], "Max DD":m["max_drawdown"], "Win Rate %":m["win_rate"], "Sharpe":m["sharpe"], "Sortino":m["sortino"], "FX Hit Days":m["fx_hit_days"]})
                st.dataframe(pd.DataFrame(rows), **WIDE)

    with st.expander("📸 Historical NC / Capital Snapshot", expanded=False):
        if st.button("📌 บันทึก Snapshot ตอนนี้", key="p2_snapshot", **WIDE):
            cloud = save_nc_snapshot(cfg, data)
            st.success("บันทึก Snapshot ลง Supabase แล้ว" if cloud else "บันทึก Snapshot แล้ว (local fallback)")
        snaps = load_nc_snapshots(50)
        if snaps:
            cols=["snapshot_at","actor","asset","required_stock_thb","nc_actual","nc_required","nc_buffer"]
            st.dataframe(pd.DataFrame(snaps)[[c for c in cols if c in pd.DataFrame(snaps).columns]], **WIDE)

    with st.expander("📄 Export PDF / Excel", expanded=False):
        base = _backtest_metrics(bt_baseline if bt_baseline is not None else _backtest_frame(cfg, data))
        summary = pd.DataFrame([{"Metric":k, "Value":v} for k,v in base.items() if k != "frame"])
        excel = _phase2_excel_bytes({"Backtest": bt_baseline if bt_baseline is not None else _backtest_frame(cfg, data)}, summary)
        pdf = _phase2_pdf_bytes(f"XSpring Dealer Suite — Phase 2 Report ({cfg['asset']})", summary)
        a,b=st.columns(2)
        a.download_button("⬇️ Excel Report", excel, "xspring_phase2_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **WIDE)
        b.download_button("⬇️ PDF Report", pdf, "xspring_phase2_report.pdf", "application/pdf", **WIDE)

# ---- 5.2 TAB 1 — BACKTEST ----------------------------------------------

def render_tab1(cfg: dict[str, Any], data: pd.DataFrame, data_err: Optional[str]) -> None:
    if data.empty:
        st.error(f"⚠️ {data_err or 'ไม่สามารถโหลดข้อมูลได้'}")
        return

    asset = cfg["asset"]
    trade_vol = cfg["trade_vol"]
    hedge_fee = cfg["hedge_fee"]

    bt = data.copy()
    bt["Local_THB"] = bt["Global_USD"] * bt["USDTHB"] * (1 + cfg["local_premium"])
    bt["Coin_Volume"] = trade_vol / bt["Global_USD"]
    bt["Gross_Notional_THB"] = bt["Coin_Volume"] * bt["Local_THB"]
    bt["Spread_Revenue_THB"] = bt["Gross_Notional_THB"] * cfg["dealer_spread"]
    bt["FX_Basis_PnL_THB"] = trade_vol * bt["USDTHB"] * cfg["local_premium"]
    bt["Hedge_Fee_Cost_THB"] = trade_vol * hedge_fee * bt["USDTHB"]
    bt["Hedge_Notional_USD"] = trade_vol * (1 + hedge_fee)
    bt["KTB_FX_Benefit_THB"] = (trade_vol * bt["USDTHB"]
                                * (cfg["ktb_fx_spread_bps"] / 10000.0))

    if asset in STABLECOINS:
        bt["Depeg_Deviation"] = cfg["peg_target"] - bt["Global_USD"]
        bt["Depeg_PnL_THB"] = (bt["Coin_Volume"] * bt["Depeg_Deviation"]
                               * bt["USDTHB"] * cfg["depeg_capture_pct"])
        bt["Carry_Yield_THB"] = trade_vol * (cfg["carry_apy"] / 365) * bt["USDTHB"]
        bt["Slippage_Cost_THB"] = 0.0
    else:
        bt["Depeg_Deviation"] = 0.0
        bt["Depeg_PnL_THB"] = 0.0
        bt["Carry_Yield_THB"] = 0.0
        impact_rate = market_impact_rate(trade_vol, cfg["market_depth_usd"],
                                         cfg["impact_penalty"])
        bt["Slippage_Cost_THB"] = (trade_vol * bt["Volatility_Pct"]
                                   * cfg["slippage_sensitivity"] * bt["USDTHB"]
                                   + trade_vol * impact_rate * bt["USDTHB"])

    if cfg["include_trading_fee_revenue"]:
        bt["Trading_Fee_Revenue_THB"] = bt["Gross_Notional_THB"] * LOCAL_TRADING_FEE_PCT
    else:
        bt["Trading_Fee_Revenue_THB"] = 0.0

    wd_network_cost = (WITHDRAWAL_FEE_TABLE.get(asset, 0.0) * bt["Global_USD"]
                       * bt["USDTHB"] * cfg["settlements_per_day"])
    bt["Withdrawal_Fee_Markup_Revenue_THB"] = (wd_network_cost
                                               * cfg["withdrawal_fee_markup_pct"])
    bt["THB_WD_Fee"] = bt["USDTHB"].map(
        lambda fx: calc_thb_withdrawal_fee(trade_vol * fx, cfg["bank_type"],
                                           cfg["ktb_wd_fee_thb"])
    )
    bt["THB_Fee_Markup_Revenue_THB"] = (bt["THB_WD_Fee"] * cfg["settlements_per_day"]
                                        * cfg["withdrawal_fee_markup_pct"])
    bt["Fee_Revenue_THB"] = (bt["Trading_Fee_Revenue_THB"]
                             + bt["Withdrawal_Fee_Markup_Revenue_THB"]
                             + bt["THB_Fee_Markup_Revenue_THB"])
    bt["Revenue_THB"] = (bt["Spread_Revenue_THB"] + bt["FX_Basis_PnL_THB"]
                         + bt["Fee_Revenue_THB"] + bt["Depeg_PnL_THB"]
                         + bt["Carry_Yield_THB"] + bt["KTB_FX_Benefit_THB"])
    bt["Cost_THB"] = bt["Hedge_Fee_Cost_THB"] + bt["Slippage_Cost_THB"]
    bt["Daily_PnL_THB"] = bt["Revenue_THB"] - bt["Cost_THB"]

    allowed, usage = apply_fx_limit(bt["Hedge_Notional_USD"], bt.index,
                                    cfg["fx_limit_max"])
    bt["Trade_Allowed"] = allowed
    bt["Current_FX_Usage"] = usage
    bt["FX_Limit_Hit"] = 1 - allowed
    bt["Actual_Daily_PnL"] = np.where(allowed == 1, bt["Daily_PnL_THB"], 0.0)
    bt["Actual_Cum_PnL"] = bt["Actual_Daily_PnL"].cumsum()

    traded = bt[bt["Trade_Allowed"] == 1]
    total_revenue_thb = traded["Revenue_THB"].sum()
    total_cost_thb = traded["Cost_THB"].sum()
    net_pnl_thb = bt["Actual_Cum_PnL"].iloc[-1]
    total_notional = traded["Gross_Notional_THB"].sum()
    margin_bps = (net_pnl_thb / total_notional * 10000) if total_notional else 0
    total_days = len(bt)
    traded_days = int(allowed.sum())
    limit_hit_days = int(bt["FX_Limit_Hit"].sum())
    win_days = int((bt["Actual_Daily_PnL"] > 0).sum())
    win_rate = win_days / traded_days * 100 if traded_days else 0
    avg_daily_pnl = traded["Daily_PnL_THB"].mean() if traded_days else 0
    best_day = bt["Actual_Daily_PnL"].max()
    worst_day = bt["Actual_Daily_PnL"].min()
    running_max = bt["Actual_Cum_PnL"].cummax()
    max_drawdown = (bt["Actual_Cum_PnL"] - running_max).min()
    dd_series = (bt["Actual_Cum_PnL"] - running_max) / running_max.where(running_max > 0)
    dd_pct = dd_series.min() * 100
    dd_pct = 0.0 if pd.isna(dd_pct) else dd_pct

    st.success(f"✅ โหลดข้อมูล **{asset}** สำเร็จ ({total_days} วัน | เทรดได้จริง {traded_days} วัน)")

    # ---- ราคาเรียลไทม์ ----
    section(f"📉 ราคาเรียลไทม์ — {asset}")
    render_tv_panel(asset)

    # ---- 3D Interactive Chart Feature ----
    section("🌐 มุมมองกราฟ 3D พิเศษ (3D Price Surface)")
    with st.expander("✨ เปิดดูกราฟ 3D สามมิติ (Interactive 3D Chart)", expanded=False):
        # ชื่อตัวเลือก -> (คอลัมน์, ชื่อแกน Z, รูปแบบ hover, ชื่อ colorbar)
        VIEW_3D = {
            "ความผันผวน (Volatility)": ("Vol_Pct", "ความผันผวน (%)", "%{z:.2f}%", "Volatility %"),
            "เปลี่ยนแปลง (%Change)": ("Chg_Pct", "%เปลี่ยนแปลงราคาปิด (Daily)", "%{z:+.2f}%", "%Chg"),
            "Volume": ("Vol_B", "Volume (พันล้าน USD)", "$%{z:,.2f}B", "Volume (B)"),
        }
        view_3d = st.selectbox("เลือกกราฟ 3D", list(VIEW_3D.keys()), key="bt_3d_view")
        z_col, z_title, z_hover, cbar_title = VIEW_3D[view_3d]
        
        st.caption("หมุนและซูมเพื่อดูความสัมพันธ์ระหว่าง เวลา, ราคาโลก (USD) และตัวชี้วัดที่เลือก")
        df_3d = bt.copy()
        df_3d["Vol_Pct"] = df_3d["Volatility_Pct"] * 100
        df_3d["Chg_Pct"] = df_3d["Global_USD"].pct_change() * 100
        df_3d["Vol_B"] = (df_3d["Volume_USD"] / 1e9) if "Volume_USD" in df_3d.columns else np.nan
        df_3d = df_3d.replace([np.inf, -np.inf], np.nan).dropna(subset=[z_col, "Global_USD"])
        
        if len(df_3d) > 0 and (z_col != "Vol_B" or df_3d["Vol_B"].sum() > 0):
            fig_3d = go.Figure(data=[go.Scatter3d(
                x=list(range(len(df_3d))),
                y=df_3d["Global_USD"],
                z=df_3d[z_col],
                mode="markers",
                marker=dict(
                    size=5,
                    color=df_3d[z_col],          # สีรุ้งตามค่าของแกน Z
                    colorscale="Rainbow",
                    opacity=0.9,
                    line=dict(width=0),
                    colorbar=dict(title=cbar_title, thickness=12),
                ),
                text=df_3d.index.strftime("%Y-%m-%d"),
                hovertemplate=("วันที่: %{text}<br>ราคา: $%{y:,.2f}<br>"
                               f"{view_3d}: {z_hover}<extra></extra>"),
            )])
            fig_3d.update_layout(
                title=dict(text=f"3D — {asset} (Time vs Price vs {view_3d})",
                           font=dict(size=14)),
                scene=dict(
                    xaxis_title="ลำดับเวลา (Time Steps)",
                    yaxis_title="ราคาโลก (USD)",
                    zaxis_title=z_title,
                    bgcolor="#181a20",
                ),
                template="plotly_dark",
                height=600,
                margin=dict(l=0, r=0, b=0, t=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_3d, **WIDE)
        else:
            st.info("ไม่มีข้อมูลสำหรับกราฟนี้ในช่วงเวลาที่เลือก (เช่น Volume เป็น 0 ทั้งช่วง)")

    # ---- Performance ----
    section("📈 Performance Summary")
    r1 = st.columns(4)
    metric_card(r1[0], "Net P&L (THB)", fmt_baht(net_pnl_thb, True), net_pnl_thb,
                f"{margin_bps:,.1f} bps ของ notional", "1.7rem")
    metric_card(r1[1], "Total Revenue", fmt_baht(total_revenue_thb),
                total_revenue_thb, "Spread + Fee + Basis + Carry")
    metric_card(r1[2], "Total Cost", fmt_baht(total_cost_thb),
                -abs(total_cost_thb), "Hedge Fee + Slippage")
    metric_card(r1[3], "Avg Daily P&L", fmt_baht(avg_daily_pnl, True),
                avg_daily_pnl, f"เฉลี่ยจาก {traded_days} วันที่เทรดได้")

    r2 = st.columns(4)
    metric_card(r2[0], "Best Day", fmt_baht(best_day, True), best_day)
    metric_card(r2[1], "Worst Day", fmt_baht(worst_day, True), worst_day)
    metric_card(r2[2], "Max Drawdown", fmt_baht(max_drawdown),
                max_drawdown if max_drawdown != 0 else -0.01,
                f"{dd_pct:.2f}% จาก peak")
    metric_card(r2[3], "Win Rate", f"{win_rate:.1f}%", None,
                f"{win_days}/{traded_days} วัน")

    r3 = st.columns(4)
    hit_pct = (limit_hit_days / total_days * 100) if total_days else 0
    metric_card(r3[0], "Gross Notional หมุนเวียน", fmt_baht(total_notional),
                None, "มูลค่าธุรกรรมรวม (ไม่ใช่กำไร)")
    metric_card(r3[1], "FX Limit Hit", f"{limit_hit_days} วัน",
                -1 if limit_hit_days else 0, f"{hit_pct:.1f}% ของช่วงเวลา")
    if asset in STABLECOINS:
        metric_card(r3[2], "Avg Depeg Deviation", f"{bt['Depeg_Deviation'].mean() * 100:+.3f}%")
        metric_card(r3[3], "Total Carry Yield", fmt_baht(traded["Carry_Yield_THB"].sum()), traded["Carry_Yield_THB"].sum())
    else:
        metric_card(r3[2], "Avg Daily Volatility", f"{bt['Volatility_Pct'].mean() * 100:.2f}%")
        metric_card(r3[3], "Total Slippage Cost", fmt_baht(traded["Slippage_Cost_THB"].sum()), -abs(traded["Slippage_Cost_THB"].sum()))

    sharpe, sortino = _performance_ratios(bt["Actual_Daily_PnL"])
    r4 = st.columns(2)
    metric_card(r4[0], "Sharpe Ratio", f"{sharpe:.2f}", sharpe, "annualized จาก Daily P&L")
    metric_card(r4[1], "Sortino Ratio", f"{sortino:.2f}", sortino, "annualized; downside deviation")

    render_phase2_tools_top(cfg, data, bt_baseline=bt)

    # ---- Waterfall ----
    section("💧 Revenue & Cost Waterfall")
    wf_labels = ["Spread Revenue", "FX Basis P&L", "Fee Revenue"]
    wf_values = [
        traded["Spread_Revenue_THB"].sum(),
        traded["FX_Basis_PnL_THB"].sum(),
        traded["Fee_Revenue_THB"].sum(),
    ]
    if cfg["use_ktb_fx"]:
        wf_labels.append("KTB FX Benefit")
        wf_values.append(traded["KTB_FX_Benefit_THB"].sum())
    if asset in STABLECOINS:
        wf_labels += ["Depeg Arbitrage", "Carry Yield"]
        wf_values += [traded["Depeg_PnL_THB"].sum(), traded["Carry_Yield_THB"].sum()]
    else:
        wf_labels.append("Slippage Cost")
        wf_values.append(-traded["Slippage_Cost_THB"].sum())
    wf_labels += ["Hedge Fee Cost", "Net P&L"]
    wf_values += [-traded["Hedge_Fee_Cost_THB"].sum(), 0]

    wf_text = [fmt_baht(v, True) for v in wf_values[:-1]]
    wf_text.append(fmt_baht(sum(wf_values[:-1]), True))
    measures = ["relative"] * (len(wf_labels) - 1) + ["total"]

    fig_wf = go.Figure(go.Waterfall(
        orientation="v", measure=measures, x=wf_labels, y=wf_values,
        text=wf_text, textposition="outside",
        connector={"line": {"color": "#374151"}},
        increasing={"marker": {"color": "#0ecb81"}},
        decreasing={"marker": {"color": "#f6465d"}},
        totals={"marker": {"color": "#3B82F6"}},
    ))
    fig_wf.update_layout(template="plotly_dark", height=440, showlegend=False,
                         margin=dict(t=40, b=20), yaxis_title="THB", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig_wf, **WIDE)

    # ---- Cumulative P&L ----
    section("📊 Cumulative P&L")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=bt.index, y=bt["Actual_Cum_PnL"], name="Cumulative P&L",
        line=dict(color="#0ecb81", width=2.2), fill="tozeroy",
        fillcolor="rgba(14,203,129,0.12)",
    ))
    fig.add_trace(go.Scatter(
        x=bt.index, y=running_max, name="Peak Equity",
        line=dict(color="#848e9c", width=1, dash="dot"),
    ))
    hits = bt[bt["FX_Limit_Hit"] == 1]
    if not hits.empty:
        fig.add_trace(go.Scatter(
            x=hits.index, y=hits["Actual_Cum_PnL"], mode="markers",
            name="FX Limit Hit",
            marker=dict(color="#f6465d", size=5, symbol="x"),
        ))
    fig.update_layout(
        title=(f"{asset} @ {cfg['global_exchange']} · {cfg['start_date']} → {cfg['end_date']}"),
        template="plotly_dark", hovermode="x unified", height=480,
        margin=dict(t=50, b=20), yaxis_title="THB",
        legend=dict(orientation="h", y=1.02, yanchor="bottom"),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, **WIDE)

    with st.expander("📅 P&L รายเดือน"):
        grouped = bt.groupby([bt.index.year, bt.index.month])["Actual_Daily_PnL"]
        m = grouped.sum().unstack(fill_value=0)
        m.columns = [f"{c:02d}" for c in m.columns]
        fig_hm = go.Figure(go.Heatmap(
            z=m.values, x=list(m.columns), y=[str(i) for i in m.index],
            colorscale=[[0, "#f6465d"], [0.5, "#181a20"], [1, "#0ecb81"]],
            zmid=0, texttemplate="%{z:,.0f}", textfont={"size": 9},
        ))
        fig_hm.update_layout(template="plotly_dark", height=60 * len(m) + 120,
                             margin=dict(t=20, b=20),
                             xaxis_title="เดือน", yaxis_title="ปี", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_hm, **WIDE)

    with st.expander("🔍 Daily Ledger (100 วันล่าสุด)"):
        cols = [
            "Global_USD", "Local_THB", "USDTHB", "Volatility_Pct",
            "Gross_Notional_THB", "Spread_Revenue_THB", "FX_Basis_PnL_THB",
            "KTB_FX_Benefit_THB", "Hedge_Fee_Cost_THB", "Slippage_Cost_THB",
            "Fee_Revenue_THB",
        ]
        if asset in STABLECOINS:
            cols += ["Depeg_Deviation", "Depeg_PnL_THB", "Carry_Yield_THB"]
        cols += ["Actual_Daily_PnL", "Current_FX_Usage", "FX_Limit_Hit"]

        preview = bt[cols].sort_index(ascending=False).head(100)
        st.dataframe(preview, height=400, **WIDE)

    render_ledger_anomaly_detector(cfg, bt)

    render_phase2_tools_bottom(cfg, data, bt_baseline=bt)


# ---- 5.3 TAB 2 — LIQUIDITY & CAPITAL PLANNER ---------------------------

# =========================================================================
# GLOBAL PERP VENUE TABLE (v3) — เทียบราคา/ปริมาณเทรดข้ามกระดานโลก
# ลำดับการดึงข้อมูล:
#   1) server ดึงตรงจากกระดานทั้ง 9 (ฟรี ไม่ใช้ key)
#   2) [ตัวเลือก] กระดานไหนล้ม + มี coinglass_api_key → ดึงผ่าน CoinGlass
#   3) กระดานที่ยังล้มอยู่ (เช่น Binance) → ให้ browser ของผู้ใช้ดึงเอง
#      ใช้ IP ผู้ใช้ จึงช่วยหลีกเลี่ยงข้อจำกัดภูมิภาคของ server
#
# จุดเรียกใน render_tab2 ยังเป็น render_perp_venue_table(asset) เหมือนเดิม
# =========================================================================

_VENUE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (XSpring-Dealer-Suite)",
    "Accept": "application/json",
}


def _http_json(
    url: str,
    payload: Optional[dict] = None,
    timeout: float = 6.0,
    extra_headers: Optional[dict] = None,
) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = dict(_VENUE_HEADERS)
    if data is not None:
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# แต่ละฟังก์ชันคืน (price_usd, chg24h_pct, turnover24h_usd)
def _pv_binance(b: str) -> tuple[float, float, float]:
    d = _http_json(
        f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={b}USDT"
    )
    return float(d["lastPrice"]), float(d["priceChangePercent"]), float(d["quoteVolume"])


def _pv_gate(b: str) -> tuple[float, float, float]:
    d = _http_json(
        f"https://api.gateio.ws/api/v4/futures/usdt/tickers?contract={b}_USDT"
    )[0]
    turn = d.get("volume_24h_quote") or d.get("volume_24h_settle") or d.get("volume_24h_usd")
    return float(d["last"]), float(d["change_percentage"]), float(turn)


def _pv_hyperliquid(b: str) -> tuple[float, float, float]:
    meta, ctxs = _http_json(
        "https://api.hyperliquid.xyz/info",
        {"type": "metaAndAssetCtxs"},
    )
    i = next(k for k, u in enumerate(meta["universe"]) if u["name"] == b)
    c = ctxs[i]
    px, prev = float(c["markPx"]), float(c["prevDayPx"])
    return px, (px / prev - 1) * 100, float(c["dayNtlVlm"])


def _pv_bitget(b: str) -> tuple[float, float, float]:
    d = _http_json(
        f"https://api.bitget.com/api/v2/mix/market/ticker"
        f"?symbol={b}USDT&productType=USDT-FUTURES"
    )["data"][0]
    turn = d.get("usdtVolume") or d.get("quoteVolume")
    return float(d["lastPr"]), float(d["change24h"]) * 100, float(turn)


def _pv_okx(b: str) -> tuple[float, float, float]:
    d = _http_json(
        f"https://www.okx.com/api/v5/market/ticker?instId={b}-USDT-SWAP"
    )["data"][0]
    last, op = float(d["last"]), float(d["open24h"])
    # OKX ให้ volCcy24h เป็นจำนวนเหรียญ (base) → คูณราคาล่าสุดให้เป็น USD
    return last, (last / op - 1) * 100, float(d["volCcy24h"]) * last


def _pv_aster(b: str) -> tuple[float, float, float]:
    # Aster ใช้ API รูปแบบเดียวกับ Binance Futures
    d = _http_json(
        f"https://fapi.asterdex.com/fapi/v1/ticker/24hr?symbol={b}USDT"
    )
    return float(d["lastPrice"]), float(d["priceChangePercent"]), float(d["quoteVolume"])


def _pv_deribit(b: str) -> tuple[float, float, float]:
    # Deribit perpetual เป็นสัญญา inverse (ราคาเป็น USD, margin เป็นเหรียญ)
    d = _http_json(
        f"https://www.deribit.com/api/v2/public/ticker"
        f"?instrument_name={b}-PERPETUAL"
    )["result"]
    return (
        float(d["last_price"]),
        float(d["stats"]["price_change"]),
        float(d["stats"]["volume_usd"]),
    )


def _pv_bitunix(b: str) -> tuple[float, float, float]:
    doc = _http_json(
        f"https://fapi.bitunix.com/api/v1/futures/market/tickers?symbols={b}USDT"
    )
    if str(doc.get("code")) != "0":
        raise RuntimeError(str(doc.get("msg") or "error")[:40])
    d = doc["data"][0]
    last, op = float(d["lastPrice"]), float(d["open"])
    if not (op > 0):
        raise ValueError("bad open")
    return last, (last / op - 1) * 100, float(d["quoteVol"])


# cg = คำนำหน้าชื่อกระดานใน CoinGlass (ตัวพิมพ์เล็ก ไม่มีจุด/ช่องว่าง)
_PERP_VENUES = [
    dict(
        name="Binance",
        cg="binance",
        bg="#F0B90B",
        fg="#0b0e11",
        tx="BN",
        logo="https://www.google.com/s2/favicons?domain=binance.com&sz=64",
        fn=_pv_binance,
        sym=lambda b: f"{b}USDT",
        url=lambda b: f"https://www.binance.com/en/futures/{b}USDT",
    ),
    dict(
        name="Gate",
        cg="gate",
        bg="#2354E6",
        fg="#ffffff",
        tx="G",
        logo="https://www.google.com/s2/favicons?domain=gate.com&sz=64",
        fn=_pv_gate,
        sym=lambda b: f"{b}_USDT",
        url=lambda b: f"https://www.gate.io/futures/USDT/{b}_USDT",
    ),
    dict(
        name="Hyperliquid",
        cg="hyperliquid",
        bg="#072723",
        fg="#97FCE4",
        tx="HL",
        logo="https://www.google.com/s2/favicons?domain=hyperliquid.xyz&sz=64",
        fn=_pv_hyperliquid,
        sym=lambda b: f"{b}",
        url=lambda b: f"https://app.hyperliquid.xyz/trade/{b}",
    ),
    dict(
        name="Bitget",
        cg="bitget",
        bg="#00F0FF",
        fg="#0b0e11",
        tx="BG",
        logo="https://www.google.com/s2/favicons?domain=bitget.com&sz=64",
        fn=_pv_bitget,
        sym=lambda b: f"{b}USDT",
        url=lambda b: f"https://www.bitget.com/futures/usdt/{b}USDT",
    ),
    dict(
        name="OKX",
        cg="okx",
        bg="#000000",
        fg="#ffffff",
        tx="OK",
        logo="https://www.google.com/s2/favicons?domain=okx.com&sz=64",
        fn=_pv_okx,
        sym=lambda b: f"{b}-USDT-SWAP",
        url=lambda b: f"https://www.okx.com/trade-swap/{b.lower()}-usdt-swap",
    ),
    dict(
        name="Bitunix",
        cg="bitunix",
        bg="#1F2A44",
        fg="#7CFFB2",
        tx="BU",
        logo="https://www.google.com/s2/favicons?domain=bitunix.com&sz=64",
        fn=_pv_bitunix,
        sym=lambda b: f"{b}USDT",
        url=lambda b: f"https://www.bitunix.com/contract-trade/{b}USDT",
        note="ฐานคำนวณ % ของ Bitunix อาจต่างจากกระดานอื่น",
    ),
    dict(
        name="Deribit",
        cg="deribit",
        bg="#0B7BE5",
        fg="#ffffff",
        tx="DB",
        logo="https://www.google.com/s2/favicons?domain=deribit.com&sz=64",
        fn=_pv_deribit,
        sym=lambda b: f"{b}-PERPETUAL",
        url=lambda b: f"https://www.deribit.com/futures/{b}-PERPETUAL",
        note="Deribit เป็นสัญญา inverse (margin เป็นเหรียญ) ไม่ใช่ USDT-margined",
    ),
    dict(
        name="Aster",
        cg="aster",
        bg="#E8B96A",
        fg="#0b0e11",
        tx="AS",
        logo="https://www.google.com/s2/favicons?domain=asterdex.com&sz=64",
        fn=_pv_aster,
        sym=lambda b: f"{b}USDT",
        url=lambda b: f"https://www.asterdex.com/en/futures/v1/{b}USDT",
    ),
]


# ---------- CoinGlass (ตัวกลาง) ----------
def _coinglass_key() -> str:
    try:
        k = st.secrets.get("coinglass_api_key", "")
    except Exception:
        k = ""
    return str(k or os.environ.get("COINGLASS_API_KEY", "")).strip()


@_cache_data(ttl=60, show_spinner=False)
def _cg_pairs(base: str, api_key: str) -> list[dict]:
    doc = _http_json(
        f"https://open-api-v4.coinglass.com/api/futures/pairs-markets?symbol={base}",
        timeout=8.0,
        extra_headers={"CG-API-KEY": api_key},
    )
    if str(doc.get("code")) != "0":
        raise RuntimeError(str(doc.get("msg") or "error")[:60])
    return doc.get("data") or []


def _cg_pick(
    rows: list[dict], v: dict, base: str
) -> Optional[tuple[float, float, float]]:
    """เลือกคู่ของกระดานนั้น; ถ้ามีหลายคู่ เลือกที่ volume สูงสุด"""
    ok_ids = {base + "USDT", base + "USDTSWAP"}
    if v["name"] == "Hyperliquid":
        ok_ids |= {base, base + "USDC"}
    if v["name"] == "Deribit":
        ok_ids |= {base + "PERPETUAL"}

    best = None
    for r in rows:
        exchange_name = re.sub(
            r"[^a-z0-9]", "", str(r.get("exchange_name", "")).lower()
        )
        if not exchange_name.startswith(v["cg"]):
            continue

        iid = re.sub(r"[^A-Z0-9]", "", str(r.get("instrument_id", "")).upper())
        if iid not in ok_ids:
            continue

        try:
            px = float(r["current_price"])
            chg = float(r["price_change_percent_24h"])
            vol = float(r.get("volume_usd") or 0)
        except (KeyError, TypeError, ValueError):
            continue

        if px > 0 and (best is None or vol > best[2]):
            best = (px, chg, vol)

    return best


@_cache_data(ttl=30, show_spinner=False)
def fetch_perp_venues(base: str = "BTC") -> tuple[pd.DataFrame, str]:
    """ดึงทุกกระดานพร้อมกัน → ตัวที่ล้มค่อยไปดึงผ่าน CoinGlass ถ้ามี key"""
    def one(v: dict) -> dict:
        row = dict(
            exchange=v["name"],
            symbol=v["sym"](base),
            url=v["url"](base),
            price=None,
            chg=None,
            turnover=None,
            err=None,
            via=None,
        )
        try:
            p, c, t = v["fn"](base)
            if not (p > 0):
                raise ValueError("bad price")
            row.update(price=p, chg=c, turnover=t)
        except urllib.error.HTTPError as e:
            row["err"] = f"HTTP {e.code}"
        except Exception as e:
            row["err"] = type(e).__name__
        return row

    with ThreadPoolExecutor(max_workers=len(_PERP_VENUES)) as ex:
        rows = list(ex.map(one, _PERP_VENUES))

    failed = [r for r in rows if r["err"]]
    if failed:
        key = _coinglass_key()
        cg_rows: list[dict] = []
        cg_err = ""

        if key:
            try:
                cg_rows = _cg_pairs(base, key)
            except urllib.error.HTTPError as e:
                cg_err = f"CoinGlass HTTP {e.code}"
            except Exception as e:
                cg_err = f"CoinGlass {type(e).__name__}: {e}"[:70]

        meta = {v["name"]: v for v in _PERP_VENUES}
        for r in failed:
            hit = _cg_pick(cg_rows, meta[r["exchange"]], base) if cg_rows else None
            if hit:
                r.update(
                    price=hit[0],
                    chg=hit[1],
                    turnover=hit[2],
                    err=None,
                    via="CoinGlass",
                )
            elif cg_err:
                r["err"] += f" → {cg_err}"
            elif key:
                r["err"] += " → CoinGlass ไม่พบคู่นี้"

    df = pd.DataFrame(rows).sort_values(
        "turnover", ascending=False, na_position="last"
    )
    return df.reset_index(drop=True), pd.Timestamp.now("Asia/Bangkok").strftime("%H:%M:%S")


_PV_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:transparent;color:#EAECEF;
  font-family:"Source Sans Pro",-apple-system,"Segoe UI",Roboto,sans-serif;}
.wrap{border:1px solid #2b3139;border-radius:8px;overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:.92rem;}
th{text-align:left;padding:10px 14px;color:#848e9c;font-weight:600;font-size:.78rem;
  border-bottom:1px solid #2b3139;background:#161a1e;}
td{padding:12px 14px;border-bottom:1px solid #2b3139;font-variant-numeric:tabular-nums;}
.ex{display:flex;align-items:center;gap:10px;font-weight:600;}
.logo{width:28px;height:28px;min-width:28px;border-radius:50%;
  border:1px solid #2b3139;background:#161a1e;object-fit:contain;display:block;padding:2px;box-sizing:border-box;}
.logo-fallback{display:none;align-items:center;justify-content:center;width:28px;height:28px;
  min-width:28px;border-radius:50%;border:1px solid #2b3139;font-size:.58rem;font-weight:800;}
.logo-wrap{width:28px;height:28px;min-width:28px;display:inline-flex;align-items:center;justify-content:center;}
.via{margin-left:4px;font-size:.62rem;font-weight:600;color:#848e9c;border:1px solid #2b3139;
  border-radius:4px;padding:0 4px;}
a{color:#4c9aff;text-decoration:none;}
.up{color:#0ecb81}.dn{color:#f6465d}.mut{color:#5e6673}
.note{color:#848e9c;font-size:.78rem;margin-top:8px;line-height:1.5;}
</style></head><body>
<div class="wrap"><table><thead><tr><th>Exchange</th><th>Symbol</th><th>Price($)</th>
<th>Chg 24H(%)</th><th>Turnover 24h</th></tr></thead><tbody id="tb"></tbody></table></div>
<div class="note" id="note"></div>
<script>
const D = __PAYLOAD__;
const BASE = D.base, rows = D.rows;
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtT = v => v>=1e9 ? '$'+(v/1e9).toFixed(2)+'B' : v>=1e6 ? '$'+(v/1e6).toFixed(2)+'M'
  : '$'+Math.round(v).toLocaleString('en-US');
const fmtP = v => v.toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1});

async function getJSON(url){
  const ac = new AbortController(), t = setTimeout(() => ac.abort(), 8000);
  try{
    const r = await fetch(url, {signal: ac.signal});
    if(!r.ok) throw new Error('HTTP '+r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

// กระดานที่มักถูกจำกัดจาก server → ให้ browser ของผู้ใช้ลองดึงเอง
const JOBS = {
  Binance: async () => {
    const d = await getJSON('https://fapi.binance.com/fapi/v1/ticker/24hr?symbol='+BASE+'USDT');
    return [+d.lastPrice, +d.priceChangePercent, +d.quoteVolume];
  },
};

function render(){
  const list = rows.slice().sort((a,b) => (b.turnover ?? -1) - (a.turnover ?? -1));
  document.getElementById('tb').innerHTML = list.map(r => {
    const via = r.via ? '<span class="via" title="ข้อมูลไม่ได้ดึงตรงจาก server">via '+esc(r.via)+'</span>' : '';
    let p, c, t;
    if(r.err){
      p = c = t = '<span class="mut" title="'+esc(r.err)+'">—</span>';
    } else {
      p = fmtP(r.price);
      c = '<span class="'+(r.chg>=0?'up':'dn')+'">'+(r.chg>=0?'+':'')+r.chg.toFixed(2)+'%</span>'
        + (r.note ? '<span class="mut" style="cursor:help" title="'+esc(r.note)+'"> *</span>' : '');
      t = fmtT(r.turnover);
    }
    const logo = r.logo
      ? ('<span class="logo-wrap"><img class="logo" src="'+esc(r.logo)+'" alt="'+esc(r.exchange)+' logo" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'inline-flex\';"><span class="logo-fallback" style="background:'+esc(r.bg)+';color:'+esc(r.fg)+'">'+esc(r.tx)+'</span></span>')
      : ('<span class="logo-wrap"><span class="logo-fallback" style="display:inline-flex;background:'+esc(r.bg)+';color:'+esc(r.fg)+'">'+esc(r.tx)+'</span></span>');
    return '<tr><td><div class="ex">'+logo+esc(r.exchange)+via+'</div></td>'
      +'<td><a href="'+esc(r.url)+'" target="_blank" rel="noopener">'+esc(r.symbol)+'</a></td>'
      +'<td>'+p+'</td><td>'+c+'</td><td>'+t+'</td></tr>';
  }).join('');

  const bad = rows.filter(r => r.err).map(r => r.exchange+' ('+r.err+')');
  const via = {};
  rows.forEach(r => { if(r.via) (via[r.via] = via[r.via]||[]).push(r.exchange); });

  let n = 'อัปเดต '+D.ts+' (เวลาไทย) · เรียงตาม Turnover';
  Object.keys(via).forEach(k => { n += ' · '+via[k].join(', ')+' ดึงผ่าน '+k; });
  if(bad.length) n += ' · ดึงไม่ได้: '+bad.join(', ');
  document.getElementById('note').textContent = n;
}

async function run(){
  render();
  const todo = rows.filter(r => r.err && JOBS[r.exchange]);
  await Promise.all(todo.map(async r => {
    try{
      const [p, c, t] = await JOBS[r.exchange]();
      if(!(isFinite(p) && p > 0 && isFinite(c) && isFinite(t))) throw new Error('bad data');
      Object.assign(r, {price:p, chg:c, turnover:t, err:null, via:'browser'});
    } catch(e){
      r.err += ' → browser: ' + (e && e.message ? e.message : 'fetch failed');
    }
    render();
  }));
}
run();
</script></body></html>"""


def render_perp_venue_table(base: str = "BTC") -> None:
    section(f"🌐 เทียบราคา {base} Perpetual ข้ามกระดานโลก")

    c_cap, c_btn = st.columns([8, 2])
    with c_btn:
        if st.button("🔄 รีเฟรช", key="pv_refresh", **WIDE):
            fetch_perp_venues.clear()

    df, ts = fetch_perp_venues(base)
    meta = {v["name"]: v for v in _PERP_VENUES}

    def _num(x: Any) -> Optional[float]:
        return None if pd.isna(x) else float(x)

    rows = []
    for _, r in df.iterrows():
        v = meta[r["exchange"]]
        rows.append(
            dict(
                exchange=r["exchange"],
                symbol=r["symbol"],
                url=r["url"],
                bg=v["bg"],
                fg=v["fg"],
                tx=v["tx"],
                logo=v.get("logo", ""),
                note=v.get("note"),
                price=_num(r["price"]),
                chg=_num(r["chg"]),
                turnover=_num(r["turnover"]),
                err=r["err"] if isinstance(r["err"], str) else None,
                via=r["via"] if isinstance(r["via"], str) else None,
            )
        )

    payload = json.dumps(
        dict(base=base, ts=ts, rows=rows),
        ensure_ascii=False,
    ).replace("</", "<\\/")

    components.html(
        _PV_HTML.replace("__PAYLOAD__", payload),
        height=90 + 52 * len(rows),
        scrolling=False,
    )

    c_cap.caption(
        f"อัปเดต {ts} (เวลาไทย) · กระดานที่ server ดึงไม่ได้ "
        "(เช่น Binance บน server ในสหรัฐฯ) จะให้เบราว์เซอร์ของคุณดึงเอง"
    )


# ============================================================
# NEWS LAYER (v5) — Server-side + category targeted fallback
# เฉพาะเหรียญใน SUPPORTED_ASSETS เท่านั้น
# ============================================================

NEWS_API_URL = "https://min-api.cryptocompare.com/data/v2/news/"
NEWS_ASSETS = [a for a in SUPPORTED_ASSETS if a not in STABLECOINS]
NEWS_ALIASES = {
    "BTC": ["BITCOIN"],
    "ETH": ["ETHEREUM", "ETHER"],
    "SOL": ["SOLANA"],
    "DOGE": ["DOGECOIN"],
    "ADA": ["CARDANO"],
    "HBAR": ["HEDERA", "HEDERA HASHGRAPH"],
    "LINK": ["CHAINLINK"],
    "XLM": ["STELLAR", "STELLAR LUMENS"],
    "XRP": ["RIPPLE"],
}


def _news_match_assets(item: dict) -> list[str]:
    """Match ข่าวกับเหรียญในระบบจาก category + title + body/description."""
    cats_raw = str(item.get("categories", "") or "")
    cats = {c.strip().upper() for c in re.split(r"[|,;]", cats_raw) if c.strip()}
    text = " ".join([
        str(item.get("title", "") or ""),
        str(item.get("body", "") or ""),
        str(item.get("description", "") or ""),
    ]).upper()
    hits = []
    for a in NEWS_ASSETS:
        terms = [a, COIN_NAMES.get(a, a)] + NEWS_ALIASES.get(a, [])
        if a in cats:
            hits.append(a)
            continue
        if any(re.search(rf"\b{re.escape(str(term).upper())}\b", text) for term in terms if term):
            hits.append(a)
    return hits


def _news_request(params: dict) -> list[dict]:
    """เรียก CryptoCompare และคืน Data; แยก exception เพื่อให้ fallback ทำงานต่อได้."""
    try:
        query = urllib.parse.urlencode(params)
        full_url = f"{NEWS_API_URL}?{query}"
        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": "Mozilla/5.0 (XSpring-Dealer-Suite/1.0)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        return raw.get("Data", []) or []
    except Exception:
        return []


NEWS_RSS_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
}

NEWS_PLACEHOLDER_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 640 360'>"
    "<rect width='640' height='360' rx='18' fill='#161a1e'/>"
    "<rect x='24' y='24' width='592' height='312' rx='14' fill='#1f242b' stroke='#2b3139'/>"
    "<path d='M150 258l100-104 72 72 56-58 112 90H150z' fill='#2b3139'/>"
    "<circle cx='432' cy='126' r='28' fill='#3a424d'/>"
    "<text x='320' y='304' text-anchor='middle' fill='#848e9c' "
    "font-family='Arial,sans-serif' font-size='24' font-weight='700'>CRYPTO NEWS</text>"
    "</svg>"
)
NEWS_PLACEHOLDER_URL = "data:image/svg+xml;base64," + base64.b64encode(
    NEWS_PLACEHOLDER_SVG.encode("utf-8")
).decode("ascii")


def _news_local_tag(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1].lower()


def _news_extract_image(node: ET.Element, desc: str = "") -> str:
    """ดึง thumbnail จาก RSS/Atom media:content, media:thumbnail, enclosure หรือ <img> ใน description."""
    for ch in node.iter():
        local = _news_local_tag(ch.tag)
        url = str(ch.attrib.get("url", "") or "").strip()
        if url and local in {"content", "thumbnail"}:
            media_type = str(ch.attrib.get("type", "") or "").lower()
            medium = str(ch.attrib.get("medium", "") or "").lower()
            if not media_type or media_type.startswith("image") or medium == "image":
                return url

    for ch in list(node):
        if _news_local_tag(ch.tag) == "enclosure":
            typ = str(ch.attrib.get("type", "") or "").lower()
            url = str(ch.attrib.get("url", "") or "").strip()
            if url and (typ.startswith("image") or not typ):
                return url

    m = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", desc or "", re.IGNORECASE)
    return _html.unescape(m.group(1)).strip() if m else ""


def _news_text_from_node(node: ET.Element, *names: str) -> str:
    wanted = {n.lower() for n in names}
    for ch in list(node):
        if _news_local_tag(ch.tag) in wanted:
            return _html.unescape("".join(ch.itertext())).strip()
    return ""


def _news_parse_rss(xml_bytes: bytes, source: str) -> list[dict]:
    """Parse RSS/Atom feed into the same normalized structure used by CryptoCompare."""
    try:
        root = ET.fromstring(xml_bytes)
    except (ET.ParseError, ValueError):
        return []

    items = []
    nodes = [n for n in root.iter() if _news_local_tag(n.tag) in {"item", "entry"}]
    for node in nodes:
        title = _news_text_from_node(node, "title")
        desc = _news_text_from_node(node, "description", "summary", "content", "encoded")
        url = _news_text_from_node(node, "link")
        if not url:
            for ch in list(node):
                if _news_local_tag(ch.tag) == "link" and ch.attrib.get("href"):
                    url = ch.attrib["href"]
                    break

        published_raw = (
            _news_text_from_node(node, "pubdate", "published", "updated", "date")
        )
        published_ts = 0
        if published_raw:
            try:
                published_ts = int(pd.Timestamp(published_raw).timestamp())
            except Exception:
                published_ts = 0

        items.append({
            "title": title,
            "url": url,
            "source": source,
            "description": desc,
            "imageurl": _news_extract_image(node, desc),
            "published_on": published_ts,
            "categories": " ".join(
                _html.unescape("".join(ch.itertext())).strip()
                for ch in list(node) if _news_local_tag(ch.tag) == "category"
            ),
        })
    return items


@_cache_data(ttl=600, show_spinner=False)
def fetch_crypto_news_rss(limit: int = 30) -> list[dict]:
    """ดึงข่าวจาก RSS feeds และคืนค่าเฉพาะข่าวที่เกี่ยวข้องกับเหรียญในระบบ."""
    out = []
    headers = {
        "User-Agent": "Mozilla/5.0 (XSpring-Dealer-Suite/1.0)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }

    for source, feed_url in NEWS_RSS_FEEDS.items():
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_bytes = resp.read()
            items = _news_parse_rss(xml_bytes, source)
            for item in items:
                if _news_match_assets(item):
                    out.append(item)
        except Exception:
            # RSS เป็นแหล่งเสริม ถ้า feed ใดล่มให้ CryptoCompare ทำงานต่อได้ตามปกติ
            continue

    seen = set()
    deduped = []
    for item in sorted(out, key=lambda x: x.get("published_on", 0), reverse=True):
        key = item.get("url") or item.get("title") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max(limit, 1):
            break

    return deduped


@_cache_data(ttl=600, show_spinner=False)
def fetch_crypto_news(limit: int = 30) -> list[dict]:
    """
    รวมข่าวจาก CryptoCompare + RSS แล้ว dedupe/filter ตามเหรียญในระบบ.
    RSS ใช้เป็นแหล่งเสริมเพื่อให้ CoinDesk/Cointelegraph มี thumbnail ได้เมื่อ feed มีรูป.
    """
    base = {"lang": "EN", "excludeCategories": "Sponsored"}
    raw_items = []

    if NEWS_ASSETS:
        raw_items.extend(_news_request({**base, "categories": ",".join(NEWS_ASSETS), "sortOrder": "latest"}))

    if len(raw_items) < max(10, limit):
        for asset in NEWS_ASSETS:
            got = _news_request({**base, "categories": asset, "sortOrder": "latest"})
            raw_items.extend(got[:20])
            if len(raw_items) >= max(60, limit * 2):
                break

    if not raw_items:
        raw_items = _news_request({**base, "sortOrder": "latest"})

    if raw_items:
        probe_matches = any(_news_match_assets(item) for item in raw_items)
        if not probe_matches:
            global_items = _news_request({**base, "sortOrder": "latest"})
            if global_items:
                raw_items.extend(global_items)

    # RSS จาก CoinDesk / Cointelegraph
    raw_rss = fetch_crypto_news_rss(limit=max(limit, 30))

    seen = set()
    news_list = []
    for item in raw_items + raw_rss:
        key = item.get("url") or item.get("guid") or item.get("title") or ""
        if not key or key in seen:
            continue
        seen.add(key)
        matched = _news_match_assets(item)
        if not matched:
            continue
        news_list.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": (item.get("source_info") or {}).get("name")
                      if isinstance(item.get("source_info"), dict)
                      else item.get("source", "Unknown"),
            "image_url": item.get("imageurl", ""),
            "published_ts": item.get("published_on", 0),
            "tags": sorted(matched),
        })

    news_list.sort(key=lambda x: x["published_ts"], reverse=True)
    return news_list[:limit]

def _news_time_ago(unix_ts: int) -> str:
    if not unix_ts:
        return ""
    delta = datetime.now(timezone.utc) - datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    secs = delta.total_seconds()
    if secs < 3600:
        return f"{int(secs // 60)} นาทีที่แล้ว"
    if secs < 86400:
        return f"{int(secs // 3600)} ชั่วโมงที่แล้ว"
    return f"{int(secs // 86400)} วันที่แล้ว"


def render_news_section(cfg: dict) -> None:
    st.markdown("### 📰 ข่าวคริปโท")

    news_items = fetch_crypto_news()

    if not news_items:
        st.warning("ยังดึงข่าวจากแหล่งข่าวไม่สำเร็จ หรือยังไม่มีข่าวที่ตรงกับเหรียญในระบบ")
        if st.button("🔄 รีเฟรชข่าว", key="news_refresh_empty"):
            fetch_crypto_news.clear()
            fetch_crypto_news_rss.clear()
            st.rerun()
        return

    c_cap, c_btn = st.columns([8, 2])
    with c_cap:
        st.caption(f"พบข่าวที่เกี่ยวข้อง {len(news_items)} ข่าว")
    with c_btn:
        if st.button("🔄 รีเฟรช", key="news_refresh", **WIDE):
            fetch_crypto_news.clear()
            fetch_crypto_news_rss.clear()
            st.rerun()

    for news in news_items:
        cols = st.columns([1, 4])
        with cols[0]:
            # ให้ทุกข่าวมี thumbnail เท่ากัน แม้ RSS entry ไม่มีรูปจริง
            st.image(
                news["image_url"] or NEWS_PLACEHOLDER_URL,
                use_container_width=True,
            )
        with cols[1]:
            title = news["title"] or "(ไม่มีหัวข้อข่าว)"
            url = news["url"]
            if url:
                st.markdown(f"**[{title}]({url})**")
            else:
                st.markdown(f"**{title}**")
            tag_str = " · ".join(news["tags"])
            st.caption(f"{news['source']} • {_news_time_ago(news['published_ts'])} • {tag_str}")
        st.divider()


# ============================================================
# FUND FLOW LAYER (v2) — ดึงผ่านเบราว์เซอร์ผู้ใช้
# เฉพาะเหรียญใน SUPPORTED_ASSETS เท่านั้น
# ============================================================

FUNDFLOW_ASSETS = [a for a in SUPPORTED_ASSETS if a not in STABLECOINS]

FUNDFLOW_TIMEFRAMES = {
    "5m":  {"interval": "1m", "limit": 5},
    "15m": {"interval": "1m", "limit": 15},
    "1h":  {"interval": "5m", "limit": 12},
    "2h":  {"interval": "15m", "limit": 8},
    "4h":  {"interval": "15m", "limit": 16},
    "6h":  {"interval": "30m", "limit": 12},
    "8h":  {"interval": "30m", "limit": 16},
    "1D":  {"interval": "1h", "limit": 24},
    "7D":  {"interval": "4h", "limit": 42},
    "30D": {"interval": "1d", "limit": 30},
}

# แมป symbol ในระบบ -> id ของ CoinGecko
COINGECKO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "HBAR": "hedera-hashgraph",
    "LINK": "chainlink",
    "XLM": "stellar",
    "XRP": "ripple",
}

_FUNDFLOW_HTML = r"""
<style>
  html,body{margin:0;padding:0;background:transparent;color:#EAECEF;
    font-family:"Source Sans Pro",-apple-system,"Segoe UI",Roboto,sans-serif;}
  .wrap{border:1px solid #2b3139;border-radius:8px;overflow-x:auto;}
  table{width:100%;border-collapse:collapse;font-size:.85rem;white-space:nowrap;}
  th{text-align:left;padding:9px 12px;color:#848e9c;font-weight:600;font-size:.72rem;
     border-bottom:1px solid #2b3139;background:#161a1e;position:sticky;top:0;}
  td{padding:10px 12px;border-bottom:1px solid #2b3139;font-variant-numeric:tabular-nums;}
  .sym{display:flex;align-items:center;gap:8px;font-weight:700;}
  .logo{width:22px;height:22px;border-radius:50%;}
  .up{color:#0ecb81;background:rgba(14,203,129,.07);}
  .dn{color:#f6465d;background:rgba(246,70,93,.07);}
  .mut{color:#5e6673;}
  .sig{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:700;font-size:.72rem;}
  .sig-strongin{background:#0ecb81;color:#0b0e11;}
  .sig-in{background:rgba(14,203,129,.18);color:#0ecb81;}
  .sig-neu{background:#2b3139;color:#848e9c;}
  .sig-out{background:rgba(246,70,93,.18);color:#f6465d;}
  .sig-strongout{background:#f6465d;color:#0b0e11;}
  .note{color:#848e9c;font-size:.75rem;margin-top:8px;line-height:1.5;}
</style>
<div class="wrap">
  <table>
    <thead><tr id="thead"></tr></thead>
    <tbody id="tb"></tbody>
  </table>
</div>
<div class="note" id="note">กำลังโหลดข้อมูล Fund Flow จากเบราว์เซอร์ของคุณ…</div>
<script>
const ASSETS = __ASSETS__;
const TFS = __TFS__;
const CG_MAP = __CGMAP__;
const TF_KEYS = Object.keys(TFS);

function fmtFlow(v){
  if (v === null || v === undefined || !isFinite(v)) return "—";
  const sign = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 1e9) return sign + (a/1e9).toFixed(2) + "B";
  if (a >= 1e6) return sign + (a/1e6).toFixed(2) + "M";
  if (a >= 1e3) return sign + (a/1e3).toFixed(2) + "K";
  return sign + a.toFixed(2);
}

async function getJSON(url, timeoutMs=8000){
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try{
    const r = await fetch(url, {signal: ac.signal});
    if(!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

async function fetchNetFlow(asset, interval, limit){
  const url = "https://api.binance.com/api/v3/klines?symbol=" + asset +
              "USDT&interval=" + interval + "&limit=" + limit;
  const kl = await getJSON(url);
  let net = 0;
  for(const k of kl){
    const quoteVol = parseFloat(k[7]);
    const takerBuyQuoteVol = parseFloat(k[10]);
    net += (2 * takerBuyQuoteVol) - quoteVol;
  }
  return net;
}

async function fetchMarketCaps(){
  const ids = ASSETS.map(a => CG_MAP[a]).filter(Boolean);
  if (!ids.length) return {};
  try{
    const url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=" + ids.join(",");
    const data = await getJSON(url);
    const idToSym = {};
    for(const sym in CG_MAP) idToSym[CG_MAP[sym]] = sym;
    const out = {};
    for(const item of data){
      const sym = idToSym[item.id];
      if (sym) out[sym] = item.market_cap || 0;
    }
    return out;
  } catch(e){ return {}; }
}

function signalOf(row){
  const vals = TF_KEYS.map(k => row[k]).filter(v => v !== null && v !== undefined && isFinite(v));
  if (!vals.length) return {score: 0, label: "No Data", cls: "sig-neu"};
  const pos = vals.filter(v => v > 0).length;
  const score = Math.round(((pos / vals.length) * 2 - 1) * 100);
  if (score >= 50) return {score, label: "Strong Inflow", cls: "sig-strongin"};
  if (score > 0)   return {score, label: "Net Inflow", cls: "sig-in"};
  if (score === 0) return {score, label: "Neutral", cls: "sig-neu"};
  if (score > -50) return {score, label: "Net Outflow", cls: "sig-out"};
  return {score, label: "Strong Outflow", cls: "sig-strongout"};
}

function renderHead(){
  let h = "<th>Symbol</th>";
  for (const k of TF_KEYS) h += "<th>" + k + "</th>";
  h += "<th>Market Cap</th><th>Fund Signal</th>";
  document.getElementById("thead").innerHTML = h;
}

function renderRows(rows, failed){
  const sorted = rows.slice().sort((a,b) => (b.marketCap||0) - (a.marketCap||0));
  document.getElementById("tb").innerHTML = sorted.map(r => {
    let cells = "";
    for (const k of TF_KEYS){
      const v = r[k];
      if (v === null || v === undefined || !isFinite(v)){
        cells += "<td class='mut'>—</td>";
      } else {
        cells += "<td class='" + (v >= 0 ? "up" : "dn") + "'>" + fmtFlow(v) + "</td>";
      }
    }
    const sig = signalOf(r);
    const mc = r.marketCap ? fmtFlow(r.marketCap) : "—";
    return "<tr><td class='sym'>" + esc(r.asset) + "</td>" + cells +
           "<td>" + mc + "</td>" +
           "<td><span class='sig " + sig.cls + "'>" + (sig.score>=0?"+":"") + sig.score + " " + sig.label + "</span></td></tr>";
  }).join("");
  const ts = new Date().toLocaleTimeString("th-TH", {hour12:false});
  let note = "อัปเดต " + ts + " · ดึงข้อมูลจากเบราว์เซอร์ของคุณโดยตรง (กัน Binance บล็อก IP server)";
  if (failed.length) note += " · ดึงไม่ได้: " + failed.join(", ");
  document.getElementById("note").textContent = note;
}

function esc(s){ return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

async function run(){
  renderHead();
  const caps = await fetchMarketCaps();
  const rows = [];
  const failed = [];

  await Promise.all(ASSETS.map(async (asset) => {
    const row = {asset, marketCap: caps[asset] || 0};
    await Promise.all(TF_KEYS.map(async (k) => {
      const cfg = TFS[k];
      try {
        row[k] = await fetchNetFlow(asset, cfg.interval, cfg.limit);
      } catch (e) {
        row[k] = null;
      }
    }));
    const hasAny = TF_KEYS.some(k => row[k] !== null && row[k] !== undefined);
    if (hasAny) rows.push(row);
    else failed.push(asset);
  }));

  renderRows(rows, failed);
}
run();
</script>
"""


def render_fund_flow_section(cfg: dict[str, Any] | None = None) -> None:
    """
    Render ตาราง Cryptocurrency Fund Flow โดยให้ browser ของผู้ใช้เรียก
    Binance Spot klines และ CoinGecko โดยตรง แทนการยิง API จาก Streamlit server.
    """
    st.markdown("### 💧 Cryptocurrency Fund Flow")
    st.caption(
        "Net Taker Buy/Sell Volume จาก Binance · เฉพาะเหรียญในระบบ · "
        "คำนวณที่เบราว์เซอร์ของคุณโดยตรง"
    )

    payload_html = (
        _FUNDFLOW_HTML
        .replace("__ASSETS__", json.dumps(FUNDFLOW_ASSETS, ensure_ascii=False))
        .replace("__TFS__", json.dumps(FUNDFLOW_TIMEFRAMES, ensure_ascii=False))
        .replace("__CGMAP__", json.dumps(COINGECKO_ID_MAP, ensure_ascii=False))
    )
    components.html(
        payload_html,
        height=90 + 46 * len(FUNDFLOW_ASSETS),
        scrolling=True,
    )


def render_tab2(cfg: dict[str, Any], data: pd.DataFrame, data_err: Optional[str]) -> None:
    st.markdown(
        "ตอบคำถามที่ผู้บริหารถามจริง:\n\n"
        "> **\"ถ้าธุรกรรมเดือนละ X ล้าน ต้องดำรงเหรียญเท่าไหร่ เงินสดเท่าไหร่ "
        "NC เหลือเท่าไหร่ ผ่านเกณฑ์ไหม และทุนที่มีรับได้สูงสุดกี่ล้าน\"**"
    )
    if not cfg["dates_ok"]:
        st.error("❌ ช่วงวันที่ในแถบซ้ายไม่ถูกต้อง")
        return

    asset = cfg["asset"]

    # --- FUND FLOW LAYER: อยู่ในแท็บ Liquidity ---
    with st.expander("💧 Cryptocurrency Fund Flow", expanded=False):
        render_fund_flow_section(cfg)

    section("🎛️ โหมดคำนวณความเสี่ยง")
    cp_mode = st.radio(
        "เลือกโหมด",
        ["Single-Asset (ใช้เหรียญที่เลือกในแถบซ้าย)", "Multi-Asset Portfolio"],
        horizontal=True, key="cp_mode",
    )

    rp = None
    risk_label = ""
    portfolio_price_frame = data if cp_mode.startswith("Single") else None

    if cp_mode.startswith("Single"):
        if data.empty:
            st.error(f"⚠️ โหลดข้อมูลไม่สำเร็จ: {data_err}")
        else:
            rp = risk_profile(data["Global_USD"])
            risk_label = asset
    else:
        ma_c1, _ma_c2 = st.columns([2, 1])
        with ma_c1:
            selected_assets = st.multiselect(
                "เลือกเหรียญในพอร์ต", SUPPORTED_ASSETS,
                default=["BTC", "ETH", "USDT"], key="cp_ma_assets",
            )
        if not selected_assets:
            st.info("เลือกอย่างน้อย 1 เหรียญ")
        else:
            wcols = st.columns(min(len(selected_assets), 6))
            default_w = round(100 / len(selected_assets))
            weights = {}
            for i, a_ in enumerate(selected_assets):
                with wcols[i % len(wcols)]:
                    weights[a_] = st.number_input(
                        f"{a_} (%)", value=default_w, min_value=0,
                        max_value=100, step=5, key=f"cp_w_{a_}",
                    )
            wsum = sum(weights.values())
            if wsum > 0:
                norm_w = {k: v / wsum for k, v in weights.items()}
                ret_map, price_map = {}, {}
                with st.spinner("กำลังโหลดราคาย้อนหลัง…"):
                    for a_ in selected_assets:
                        d_, _err = fetch_price_data(a_, cfg["start_date"],
                                                    cfg["end_date"])
                        if not d_.empty:
                            ret_map[a_] = np.log(
                                d_["Global_USD"] / d_["Global_USD"].shift(1))
                            price_map[a_] = d_
                if ret_map:
                    ret_df = pd.concat(ret_map, axis=1).dropna()
                    if len(ret_df) >= MIN_RISK_SAMPLE_DAYS:
                        port_w = np.array([norm_w.get(c, 0) for c in ret_df.columns])
                        rp = _risk_stats((ret_df * port_w).sum(axis=1))
                        risk_label = " + ".join(
                            f"{k} {norm_w[k] * 100:.0f}%" for k in ret_df.columns)
                        if price_map:
                            portfolio_price_frame = next(iter(price_map.values()))

                        if len(ret_df.columns) >= 2:
                            section("🔥 Correlation Heatmap (Daily Returns)")
                            corr = ret_df.corr()
                            fig_corr = go.Figure(go.Heatmap(
                                z=corr.values, x=list(corr.columns), y=list(corr.columns),
                                colorscale=[[0, "#f6465d"], [0.5, "#181a20"], [1, "#0ecb81"]],
                                zmin=-1, zmax=1, texttemplate="%{z:.2f}", textfont={"size": 11},
                            ))
                            fig_corr.update_layout(
                                template="plotly_dark", height=380, margin=dict(t=20, b=20),
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                            st.plotly_chart(fig_corr, **WIDE)
                            st.caption("ยิ่งใกล้ +1 = เคลื่อนไหวไปทางเดียวกันมาก (กระจายความเสี่ยงได้น้อย) · ใกล้ -1 = สวนทางกัน (ช่วยลดความเสี่ยงพอร์ตได้ดี)")

    if rp is None:
        return

    usdthb_now, usdthb_is_fallback = get_reference_usdthb(portfolio_price_frame)
    settlement_days = cfg["settlement_days"]
    h_crypto = crypto_haircut(rp["es99"], settlement_days)
    h_cex = cfg["cex_counterparty_haircut"] if cfg["cex_margin_asset"].startswith("Stablecoin") else h_crypto

    a_factor = safety_stock_factor(cfg["net_bias_pct"], cfg["flow_cv_pct"], settlement_days, cfg["z_alpha"])
    required_stock_thb = a_factor * cfg["monthly_volume_thb"]

    nc = nc_snapshot(
        required_stock_thb, cfg["total_capital_thb"], cfg["cex_margin_thb"],
        cfg["liab_thb"], h_crypto, h_cex, cfg["fixed_min_nc"],
        cfg["trading_risk_rate"], cfg["daily_volume_thb"],
        cfg["custody_rate_blended"],
    )
    cash_after_stock_thb = nc["cash"]
    nlc_thb = nc["actual"]
    required_nc_total = nc["required"]
    nc_buffer_thb = nc["buffer"]

    slope = (a_factor * (h_crypto + cfg["custody_rate_blended"]) + cfg["trading_risk_rate"] / 30.0)
    v_nc_thb = max(0.0, (cfg["total_capital_thb"] + cfg["cex_margin_thb"] * (1 - h_cex) - cfg["liab_thb"] - cfg["fixed_min_nc"]) / slope) if slope > 0 else float("inf")
    v_cash_thb = cfg["total_capital_thb"] / a_factor if a_factor > 0 else float("inf")

    capital_max_v_thb = min(v_nc_thb, v_cash_thb)
    fx_max_v_thb = cfg["fx_limit_max"] * usdthb_now
    overall_max_v_thb = min(capital_max_v_thb, fx_max_v_thb)
    binding_side = "ทุน / NC" if capital_max_v_thb < fx_max_v_thb else "FX Limit"

    section("🧾 สรุปผลสำหรับผู้บริหาร")
    ok_nc = (not pd.isna(nc_buffer_thb)) and (nc_buffer_thb >= 0)
    verdict_box(
        ok_nc,
        f"NC จริง {fmt_baht(nlc_thb)} (ต้องดำรงขั้นต่ำ {fmt_baht(required_nc_total)})",
        f"ต้องดองเหรียญ {fmt_baht(required_stock_thb)} เหลือเงินสด {fmt_baht(cash_after_stock_thb)}",
        warn=(nc_buffer_thb < 0.5 * required_nc_total),
    )

    section("📊 รายละเอียดตัวเลข")
    k1 = st.columns(4)
    metric_card(k1[0], "Required Safety Stock", fmt_baht(required_stock_thb), None, f"Haircut ที่ใช้ {h_crypto * 100:.2f}%")
    metric_card(k1[1], "เงินสดคงเหลือ", fmt_baht(cash_after_stock_thb), cash_after_stock_thb)
    metric_card(k1[2], "Net Capital (NC) จริง", fmt_baht(nlc_thb), nlc_thb)
    metric_card(k1[3], "NC ขั้นต่ำที่ต้องดำรง", fmt_baht(required_nc_total), nc_buffer_thb, f"ส่วนเกิน {fmt_baht(nc_buffer_thb, force_sign=True)}")

    st.markdown("<br>", unsafe_allow_html=True)
    render_perp_venue_table(asset)



# ---- 5.4 TAB 3 — TIME-TRAVEL ORDER SIMULATOR ---------------------------

def _toggle_fav(sym: str) -> None:
    favs = list(st.session_state.get("favorite_tickers", []))
    if sym in favs:
        favs.remove(sym)
    else:
        favs.append(sym)
    st.session_state["favorite_tickers"] = favs
    try:
        save_favorites(favs)
    except OSError:
        pass

def _select_asset(sym: str) -> None:
    # ต้องเซ็ตใน callback เพราะ bt_asset เป็น key ของ selectbox ใน sidebar
    st.session_state["bt_asset"] = sym


def render_market_column_view(df: pd.DataFrame, mode: str, current_asset: str, usdthb: float) -> None:
    if df.empty:
        st.markdown('<div style="padding:16px;color:#848e9c;font-size:.85rem;text-align:center;">ไม่มีข้อมูลตลาด</div>', unsafe_allow_html=True)
        return

    favs = st.session_state.get("favorite_tickers", [])
    if mode == "favorite":
        view = df[df["symbol"].isin(favs)].sort_values("volume", ascending=False)
        if view.empty:
            st.markdown('<div style="padding:32px 8px;color:#848e9c;text-align:center;">ยังไม่มีรายการโปรด<br><span style="font-size:.8rem;">(กดรูปดาว ☆ ที่แถวเหรียญเพื่อเพิ่ม)</span></div>', unsafe_allow_html=True)
            return
    elif mode == "volume":
        view = df.sort_values("volume", ascending=False)
    elif mode == "top_gain":
        view = df.sort_values("pct_change", ascending=False)
    elif mode == "top_loss":
        view = df.sort_values("pct_change", ascending=True)
    else:
        view = df

    st.markdown(
        '<div class="mk-head"><span style="width:36px"></span>'
        '<span style="flex:1">สินทรัพย์'
        + (' · ปริมาณ 24 ชม. (THB)' if mode == "volume" else '') +
        '</span><span style="text-align:right">ราคา (THB) / %</span></div>',
        unsafe_allow_html=True,
    )

    for _, row in view.iterrows():
        sym = str(row["symbol"])
        p_thb = float(row["price_usd"]) * usdthb
        pct = float(row["pct_change"])
        p_str = f"{p_thb:,.2f}" if p_thb >= 1 else f"{p_thb:,.4f}"
        c_class = "ex-green" if pct >= 0 else "ex-red"
        star_on = sym in favs
        sel_cls = " mk-sel" if sym == current_asset else ""
        vol_thb = float(row["volume"]) * usdthb   # yfinance crypto: Volume เป็นมูลค่า USD อยู่แล้ว -> คูณเรทเป็นบาท
        if mode == "volume":
            sub = f'<span class="mk-vol">Vol ฿{fmt_num(vol_thb)}</span>'
        else:
            sub = COIN_NAMES.get(sym, sym)

        html = (
            f'<div class="mk-row{sel_cls}">'
            f'<div class="mk-star{" on" if star_on else ""}">{"★" if star_on else "☆"}</div>'
            f'<div class="mk-asset">{coin_icon_html(sym, 26)}'
            f'<div><div class="mk-sym">{sym}<span>/THB</span></div>'
            f'<div class="mk-name">{sub}</div></div></div>'
            f'<div class="mk-right"><div class="mk-price">{p_str}</div>'
            f'<div class="mk-pct {c_class}">{"+" if pct >= 0 else ""}{pct:.2f}%</div></div>'
            f'</div>'
        )

        with st.container(key=f"mkrow_{mode}_{sym}"):
            st.markdown(html, unsafe_allow_html=True)
            st.button("fav", key=f"fav_{mode}_{sym}",
                      on_click=_toggle_fav, args=(sym,))
            st.button("select", key=f"sel_{mode}_{sym}",
                      on_click=_select_asset, args=(sym,))


def _fmt_comma_val(v: float) -> str:
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.2f}"


def _apply_pct(pct_key: str, target_key: str, base: float, kind: str) -> None:
    """ปุ่ม 25/50/75/100% -> ใส่จำนวนในช่อง แล้วเคลียร์ตัวเลือกให้กดซ้ำได้"""
    sel = st.session_state.get(pct_key)
    if not sel:
        return
    p = int(str(sel).rstrip("%")) / 100.0
    if kind == "buy":
        st.session_state[target_key] = _fmt_comma_val(math.floor(base * p * 100) / 100)
    else:
        st.session_state[target_key] = math.floor(base * p * 1e8) / 1e8
    st.session_state[pct_key] = None


def _submit_order(sim, side, amount_thb, data, order_date, ctx) -> None:
    if not can_trade():
        st.warning("🔒 บัญชี Viewer ไม่สามารถส่งคำสั่งซื้อขายได้")
        return
    _push_undo_snapshot(sim)
    steps, _rec = execute_order(sim, side, amount_thb, order_date,
                                data.loc[order_date], ctx)
    st.session_state.sim_steps = steps
    st.rerun(scope="app")


def _place_limit(side, amount_thb, qty, px) -> None:
    if not can_trade():
        return
    sim = st.session_state.sim
    sim.setdefault("open_orders", []).append(
        dict(id=uuid.uuid4().hex[:6], side=side, amount_thb=amount_thb, qty=qty, px=px))
    st.rerun(scope="app")


def _cancel_limit(oid: str) -> None:
    sim = st.session_state.sim
    sim["open_orders"] = [o for o in sim.get("open_orders", []) if o["id"] != oid]


def check_open_orders(sim, quote_buy, quote_sell, data, order_date, ctx) -> None:
    remaining = []
    for o in sim.get("open_orders", []):
        asset = ctx["asset"]
        if o["side"] == "buy":
            hit = quote_buy <= o["px"]
            amt = o["amount_thb"]
            ok = amt <= float(sim.get("customer_thb", 0.0)) + 1e-9
        else:
            hit = quote_sell >= o["px"]
            amt = o["qty"] * quote_sell
            ok = o["qty"] <= float(sim.get("customer_coins", {}).get(asset, 0.0)) + 1e-9

        if not hit:
            remaining.append(o)
        elif ok:
            _push_undo_snapshot(sim)
            execute_order(sim, o["side"], amt, order_date, data.loc[order_date], ctx)
        # hit แต่ยอดไม่พอ = ยกเลิกทิ้ง
    sim["open_orders"] = remaining

def run_random_batch(sim, cfg, ctx, target_stock_thb, coins, n_orders, seed,
                     amt_min, amt_max):
    """สุ่มออเดอร์ข้ามหลายเหรียญ: สุ่มเหรียญ + วันที่ + ฝั่ง + ยอดเงิน (THB)
    คืนค่า (steps ของออเดอร์สุดท้าย, จำนวนออเดอร์ต่อเหรียญ, เหรียญที่โหลดราคาไม่ได้)"""
    rng = np.random.default_rng(int(seed))
    lo = float(max(amt_min, MIN_TRADE_THB))
    hi = float(max(amt_max, lo))
    p_buy = 0.5 + cfg["net_bias_pct"] / 2.0
    frames, skipped = {}, []
    with st.spinner("กำลังโหลดราคาย้อนหลังของทุกเหรียญ…"):
        for c in coins:
            d, _err = fetch_price_data(c, cfg["start_date"], cfg["end_date"],
                                       use_fx_proxy=cfg["use_fx_proxy"])
            if d.empty:
                skipped.append(c)
            else:
                frames[c] = d
    if not frames:
        return [], {}, skipped

    # 1) วางแผนออเดอร์ทั้งหมดก่อน แล้วเรียงตามวันที่
    names = list(frames)
    plan = []
    for _ in range(int(n_orders)):
        c = names[int(rng.integers(len(names)))]
        idx = frames[c].index
        d = idx[int(rng.integers(len(idx)))]
        # สุ่มแบบ log-uniform ระหว่าง min-max จะได้มีทั้งออเดอร์เล็กและใหญ่
        amt = round(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))), 2)
        amt = max(amt, MIN_TRADE_THB)
        side = "buy" if rng.random() < p_buy else "sell"
        plan.append((d, c, side, amt))
    plan.sort(key=lambda x: x[0])

    # 2) เตรียม ctx และ inventory ต่อเหรียญ
    coin_ctx = {}
    for c, df_c in frames.items():
        rp = risk_profile(df_c["Global_USD"])
        h_c = (crypto_haircut(rp["es99"], cfg["settlement_days"])
               if rp else ctx["h_crypto"])
        h_x = (cfg["cex_counterparty_haircut"]
               if cfg["cex_margin_asset"].startswith("Stablecoin") else h_c)
        over = dict(asset=c, wd_fee_per_coin=WITHDRAWAL_FEE_TABLE.get(c, 0.0),
                    h_crypto=h_c, h_cex=h_x)
        if c in STABLECOINS:
            over.update(slip_sens=0.0, market_depth_usd=0.0, impact_penalty=0.0)
        coin_ctx[c] = {**ctx, **over}
        if c not in sim["inv_coins"]:
            last = df_c.iloc[-1]
            px = float(last["Global_USD"] * last["USDTHB"])
            sim["inv_coins"][c] = target_stock_thb / px if px > 0 else 0.0

    # 3) ยิงออเดอร์ (ไม่แตะกระเป๋าของผู้ใช้)
    saved_asset, saved_target = sim["asset"], sim["target_thb"]
    counts, last_steps = {}, []
    try:
        for d, c, side, amt in plan:
            sim["asset"] = c
            sim["target_thb"] = target_stock_thb   # เหรียญละ 1 กอง target เท่ากัน
            last_steps, _rec = execute_order(
                sim, side, amt, d, frames[c].loc[d], coin_ctx[c],
                affect_wallet=False)
            counts[c] = counts.get(c, 0) + 1
    finally:
        sim["asset"], sim["target_thb"] = saved_asset, saved_target
    return last_steps, counts, skipped


QUOTE_REFRESH_SEC = 15   # ปรับตรงนี้ได้ เช่น 10 / 30

def _frozen_mid(asset: str, mid_now: float) -> float:
    """คืนราคากลางที่ตรึงไว้ จะอัปเดตเมื่อครบ QUOTE_REFRESH_SEC วินาที หรือเปลี่ยนเหรียญ"""
    snap = st.session_state.get("quote_snap")
    now = time.time()
    if (not snap or snap["asset"] != asset
            or now - snap["ts"] >= QUOTE_REFRESH_SEC):
        snap = {"asset": asset, "mid": float(mid_now), "ts": now}
        st.session_state["quote_snap"] = snap
    return float(snap["mid"])


def render_order_panel(cfg, sim, asset, mid_now, data, current_date_val, ctx) -> None:
    trade_ok = can_trade()
    fee = LOCAL_TRADING_FEE_PCT
    quote_buy = mid_now * (1 + cfg["dealer_spread"])
    quote_sell = mid_now * (1 - cfg["dealer_spread"])
    cash = float(sim.get("customer_thb", 1_000_000.0))
    coin_bal = float(sim.get("customer_coins", {}).get(asset, 0.0))
    PCTS = ["25%", "50%", "75%", "100%"]

    order_type = st.radio("Order type", ["Limit", "Market"], horizontal=True,
                          key="op_type", label_visibility="collapsed")
    is_limit = order_type == "Limit"

    snap = st.session_state.get("quote_snap")
    if snap:
        st.caption(f"ราคาอัปเดตทุก {QUOTE_REFRESH_SEC} วินาที · ล่าสุด "
                   f"{pd.Timestamp.now(tz='Asia/Bangkok').strftime('%H:%M:%S')}")

    c_buy, c_sell = st.columns(2, gap="large")

    # ---------------- ฝั่งซื้อ ----------------
    with c_buy:
        st.markdown(
            f'<div class="op-row"><span>คงเหลือ</span><b>{cash:,.2f} THB</b></div>'
            f'<div class="op-row mut"><span>ค่าธรรมเนียม</span><b>{fee * 100:.2f}%</b></div>',
            unsafe_allow_html=True)
        buy_amt = comma_number_input("จำนวนที่ต้องจ่าย (THB)", value=500000,
                                     min_value=0, key="op_buy_amt")
        st.pills("สัดส่วนของเงินบาท", PCTS, key="op_pct_buy",
                 label_visibility="collapsed", on_change=_apply_pct,
                 args=("op_pct_buy", "op_buy_amt", cash, "buy"))

        buy_px = quote_buy
        if is_limit:
            buy_px = st.number_input("Limit price (THB)", min_value=0.0, format="%.4f",
                                     value=float(round(quote_buy, 4)), key=f"op_buy_px_{asset}")
        est_coins = buy_amt * (1 - fee) / buy_px if buy_px > 0 else 0.0
        
        st.markdown(
            f'<div class="op-ro"><span>ราคาต่อ {asset}</span><b>{buy_px:,.2f} THB</b></div>'
            f'<div class="op-ro"><span>{asset} จำนวนที่จะได้รับ</span>'
            f'<b>≈ {est_coins:,.8f} {asset}</b></div>',
            unsafe_allow_html=True)
            
        over_cash = buy_amt > cash + 1e-9
        st.markdown(
            f'<div class="op-warn">{"ยอดเงินบาทในกระเป๋าไม่พอ" if over_cash else "&nbsp;"}</div>',
            unsafe_allow_html=True)

        buy_clicked = st.button(f"ซื้อ (Buy) {asset}", key="op_buy_btn",
                                disabled=(buy_amt <= 0 or over_cash or not trade_ok), **WIDE)

    # ---------------- ฝั่งขาย ----------------
    with c_sell:
        qty_key = f"op_sell_qty_{asset}"
        st.session_state.setdefault(qty_key, 0.0)
        st.markdown(
            f'<div class="op-row"><span>คงเหลือ</span><b>{coin_bal:,.8f} {asset}</b></div>'
            f'<div class="op-row mut"><span>ค่าธรรมเนียม</span><b>{fee * 100:.2f}%</b></div>',
            unsafe_allow_html=True)
        sell_qty = st.number_input(f"จำนวนที่ต้องขาย ({asset})", min_value=0.0,
                                   format="%.8f", key=qty_key)
        st.pills("สัดส่วนของเหรียญ", PCTS, key="op_pct_sell",
                 label_visibility="collapsed", on_change=_apply_pct,
                 args=("op_pct_sell", qty_key, coin_bal, "sell"))

        sell_px = quote_sell
        if is_limit:
            sell_px = st.number_input("Limit price (THB)", min_value=0.0, format="%.4f",
                                      value=float(round(quote_sell, 4)), key=f"op_sell_px_{asset}")
        net_thb = sell_qty * sell_px * (1 - fee)
        
        st.markdown(
            f'<div class="op-ro"><span>ราคาต่อ {asset}</span><b>{sell_px:,.2f} THB</b></div>'
            f'<div class="op-ro"><span>THB จำนวนที่จะได้รับ</span>'
            f'<b>≈ {net_thb:,.2f} THB</b></div>',
            unsafe_allow_html=True)
            
        over_coin = sell_qty > coin_bal + 1e-9
        st.markdown(
            f'<div class="op-warn">{f"{asset} ในกระเป๋าไม่พอ" if over_coin else "&nbsp;"}</div>',
            unsafe_allow_html=True)

        sell_clicked = st.button(f"ขาย (Sell) {asset}", key="op_sell_btn",
                                 disabled=(sell_qty <= 0 or over_coin or not trade_ok), **WIDE)

    if not trade_ok:
        st.caption("🔒 บัญชี Viewer ไม่สามารถส่งคำสั่งซื้อขายได้ — ติดต่อ Admin เพื่อขอสิทธิ์ Trader")

    if buy_clicked:
        if is_limit:
            _place_limit("buy", float(buy_amt), 0.0, float(buy_px))
        else:
            _submit_order(sim, "buy", float(buy_amt), data, current_date_val, ctx)
    elif sell_clicked:
        if is_limit:
            _place_limit("sell", 0.0, float(sell_qty), float(sell_px))
        else:
            _submit_order(sim, "sell", float(sell_qty * quote_sell), data, current_date_val, ctx)

    # แสดงออเดอร์ที่รอจับคู่
    for o in sim.get("open_orders", []):
        c1, c2 = st.columns([5, 1])
        c1.caption(f"{o['side'].upper()} @ {o['px']:,.4f} — "
                   f"{o['amount_thb']:,.2f} THB" if o["side"] == "buy"
                   else f"SELL @ {o['px']:,.4f} — {o['qty']:.8f} {asset}")
        c2.button("Cancel", key=f"cx_{o['id']}", on_click=_cancel_limit, args=(o["id"],))

    render_undo_button(asset)


def _order_panel_live_body(cfg, sim, asset, mid_now, data, current_date_val, ctx):
    render_order_panel(cfg, sim, asset, _frozen_mid(asset, mid_now),
                       data, current_date_val, ctx)

if HAS_FRAGMENT:
    _order_panel_live = st.fragment(run_every=QUOTE_REFRESH_SEC)(_order_panel_live_body)
else:
    _order_panel_live = _order_panel_live_body

def _bo_fig(fig, h=300, title=""):
    fig.update_layout(template="plotly_dark", height=h, title=dict(text=title, font=dict(size=13)),
                      margin=dict(t=36, b=20, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      showlegend=False)
    return fig

def render_backoffice(sim, cfg, ctx, target_stock_thb, price_thb) -> None:
    orders = sim.get("orders", [])
    if not orders:
        st.info("ยังไม่มีออเดอร์ — กดซื้อ/ขาย หรือสุ่มออเดอร์เพื่อดูข้อมูลหลังบ้าน")
        return
    df = pd.DataFrame(orders)
    df.index = range(1, len(df) + 1)
    rej = df["ผลด่าน"].astype(str).str.startswith("Reject")
    ok = df[~rej]

    # ---------- คำนวณ ----------
    inv_rows = []
    for c, qty in sim["inv_coins"].items():
        px = float(price_thb.get(c, 0.0))
        val = float(qty) * px
        inv_rows.append({"เหรียญ": c, "จำนวน": float(qty), "มูลค่า (THB)": val,
                         "Target (THB)": target_stock_thb, "Exposure (THB)": val - target_stock_thb})
    inv = pd.DataFrame(inv_rows)
    pnl_c = ok.groupby("เหรียญ")["กำไรออเดอร์"].sum()
    cnt_c = df.groupby("เหรียญ").size()
    rej_c = df[rej].groupby("เหรียญ").size()
    inv["กำไร (THB)"] = inv["เหรียญ"].map(pnl_c).fillna(0.0)
    inv["ออเดอร์"] = inv["เหรียญ"].map(cnt_c).fillna(0).astype(int)
    inv["ถูกปฏิเสธ"] = inv["เหรียญ"].map(rej_c).fillna(0).astype(int)

    total_stock = float(inv["มูลค่า (THB)"].clip(lower=0).sum())
    total_target = target_stock_thb * max(1, len(inv))
    net_exposure = float(inv["Exposure (THB)"].sum())
    gross_exposure = float(inv["Exposure (THB)"].abs().sum())

    nc = nc_snapshot(total_stock, ctx["capital"], ctx["cex_margin"], ctx["liab"],
                     ctx["h_crypto"], ctx["h_cex"], ctx["fixed_min_nc"],
                     ctx["trading_risk_rate"], ctx["daily_volume_thb"], ctx["custody_rate"])
    nc_util = nc["required"] / nc["actual"] if nc["actual"] > 0 else 9.99

    gross_vol = float(ok["มูลค่า (บาท)"].sum())
    buy_vol = float(ok.loc[ok["ฝั่ง"] == "ซื้อ", "มูลค่า (บาท)"].sum())
    sell_vol = gross_vol - buy_vol
    revenue, cost = float(ok["รายได้"].sum()), float(ok["ต้นทุน"].sum())
    net_pnl = float(sim["pnl_thb"])

    wins = int((ok["กำไรออเดอร์"] > 0).sum())
    win_rate = wins / len(ok) * 100 if len(ok) else 0.0
    partial = int((ok["Unhedged (บาท)"] > 0).sum())
    hedge_cov = (1 - gross_exposure / total_target) * 100 if total_target > 0 else 100.0

    cur_m = pd.to_datetime(sim.get("current_date")).strftime("%Y-%m")
    fx_used = float(sim.get("fx_used_usd_by_month", {}).get(cur_m, 0.0))
    fx_lim = float(cfg["fx_limit_max"])
    cex_used, cex_lim = float(sim["cex_used_thb"]), float(ctx["cex_liquidity_thb"])

    # ---------- การ์ด แถว 1 ----------
    section("📦 สถานะหลังบ้าน")
    r1 = st.columns(4)
    metric_card(r1[0], f"สต็อกรวม {len(inv)} เหรียญ", fmt_baht(total_stock), None,
                f"{total_stock / total_target * 100:,.0f}% ของเป้า {fmt_baht(total_target)}")
    metric_card(r1[1], "โควตา Outbound FX ที่ใช้", f"$ {fx_used:,.0f}", None,
                f"เหลือ $ {max(0, fx_lim - fx_used):,.0f} จาก $ {fx_lim:,.0f}")
    metric_card(r1[2], "CEX Liquidity ที่ใช้", fmt_baht(cex_used), None,
                f"เหลือ {fmt_baht(max(0, cex_lim - cex_used))} จาก {fmt_baht(cex_lim)}")
    metric_card(r1[3], "กำไรสะสมของ Dealer", fmt_baht(net_pnl, True), net_pnl,
                f"{len(df)} ออเดอร์ · เฉลี่ย {fmt_baht(net_pnl / len(df), True)}/ออเดอร์")

    # ---------- การ์ด แถว 2 (เพิ่มใหม่) ----------
    r2 = st.columns(4)
    metric_card(r2[0], "Net Exposure (ส่วนต่างจาก target)", fmt_baht(net_exposure, True),
                -abs(net_exposure) if abs(net_exposure) > 1 else 0,
                f"Gross {fmt_baht(gross_exposure)} · Hedge Coverage {hedge_cov:,.1f}%")
    metric_card(r2[1], "Gross Volume", fmt_baht(gross_vol), None,
                f"ซื้อ {fmt_baht(buy_vol)} · ขาย {fmt_baht(sell_vol)}")
    metric_card(r2[2], "Revenue / Cost", fmt_baht(revenue - cost, True), revenue - cost,
                f"รายได้ {fmt_baht(revenue)} · ต้นทุน {fmt_baht(cost)}")
    metric_card(r2[3], "Win Rate / Reject", f"{win_rate:.1f}%", None,
                f"ปฏิเสธ {int(rej.sum())} · Hedge ไม่ครบ {partial} ออเดอร์")

    # ---------- Gauges ----------
    g = st.columns(4)
    with g[0]:
        gauge_bar("โควตา Outbound FX", fx_used, fx_lim, f"{fx_used / fx_lim * 100:.0f}%" if fx_lim else "-",
                  f"ใช้ ${fx_used:,.0f} / ${fx_lim:,.0f}")
    with g[1]:
        gauge_bar("CEX Liquidity", cex_used, cex_lim, f"{cex_used / cex_lim * 100:.0f}%" if cex_lim else "-",
                  f"ใช้ {fmt_baht(cex_used)} / {fmt_baht(cex_lim)}")
    with g[2]:
        gauge_bar("NC Utilization (NC ขั้นต่ำ ÷ NC จริง)", nc_util, 1.0, f"{nc_util * 100:.0f}%",
                  f"Buffer {fmt_baht(nc['buffer'], True)}")
    with g[3]:
        gauge_bar("Exposure ÷ Target", gross_exposure, total_target,
                  f"{gross_exposure / total_target * 100:.0f}%" if total_target else "-",
                  f"Gross {fmt_baht(gross_exposure)}")

    if ctx.get("hot_breach"):
        verdict_box(True, "Hot Wallet เกินเพดาน", "สัดส่วน Hot Wallet สูงกว่าเกณฑ์ที่กำหนด", warn=True)

    # ---------- ตารางต่อเหรียญ ----------
    section("🪙 สถานะรายเหรียญ")
    st.dataframe(inv.sort_values("มูลค่า (THB)", ascending=False).reset_index(drop=True),
                 height=min(420, 40 + 35 * len(inv)), **WIDE)

    # ---------- กราฟ ----------
    section("📈 กราฟหลังบ้าน")
    x = df.index
    c1, c2 = st.columns(2)
    f = go.Figure(go.Scatter(x=x, y=df["กำไรออเดอร์"].cumsum(), line=dict(color="#0ecb81", width=2),
                             fill="tozeroy", fillcolor="rgba(14,203,129,0.12)"))
    c1.plotly_chart(_bo_fig(f, 300, "กำไรสะสมรายออเดอร์ (THB)"), **WIDE)

    f = go.Figure(go.Scatter(x=x, y=df["FX ใช้สะสม (USD)"], line=dict(color="#3B82F6", width=2)))
    f.add_hline(y=fx_lim, line=dict(color="#f6465d", dash="dash"), annotation_text="FX Limit")
    c2.plotly_chart(_bo_fig(f, 300, "โควตา Outbound FX ที่ใช้ไป (USD)"), **WIDE)

    c3, c4 = st.columns(2)
    f = go.Figure(go.Scatter(x=x, y=df["CEX Liquidity ใช้สะสม (บาท)"], line=dict(color="#9945FF", width=2)))
    f.add_hline(y=cex_lim, line=dict(color="#f6465d", dash="dash"), annotation_text="CEX Liquidity")
    c3.plotly_chart(_bo_fig(f, 300, "CEX Liquidity ที่ใช้ไป (THB)"), **WIDE)

    f = go.Figure(go.Scatter(x=x, y=df["NC Buffer"], line=dict(color="#fcd535", width=2)))
    f.add_hline(y=0, line=dict(color="#f6465d", dash="dash"), annotation_text="ขั้นต่ำ")
    c4.plotly_chart(_bo_fig(f, 300, "NC Buffer หลังแต่ละออเดอร์ (THB)"), **WIDE)

    # --- กราฟที่เพิ่มใหม่ ---
    c5, c6 = st.columns(2)
    f = go.Figure(go.Bar(x=inv["เหรียญ"], y=inv["กำไร (THB)"],
                         marker_color=["#0ecb81" if v >= 0 else "#f6465d" for v in inv["กำไร (THB)"]]))
    c5.plotly_chart(_bo_fig(f, 300, "กำไรแยกตามเหรียญ (THB)"), **WIDE)

    f = go.Figure(go.Bar(x=inv["เหรียญ"], y=inv["Exposure (THB)"],
                         marker_color=["#fcd535" if v >= 0 else "#f6465d" for v in inv["Exposure (THB)"]]))
    f.add_hline(y=0, line=dict(color="#848e9c"))
    c6.plotly_chart(_bo_fig(f, 300, "Exposure แยกตามเหรียญ (+ถือเกิน / −ขาด)"), **WIDE)

    c7, c8 = st.columns(2)
    vol = ok.pivot_table(index="เหรียญ", columns="ฝั่ง", values="มูลค่า (บาท)", aggfunc="sum", fill_value=0)
    f = go.Figure()
    if "ซื้อ" in vol:
        f.add_trace(go.Bar(name="ซื้อ", x=vol.index, y=vol["ซื้อ"], marker_color="#0ecb81"))
    if "ขาย" in vol:
        f.add_trace(go.Bar(name="ขาย", x=vol.index, y=vol["ขาย"], marker_color="#f6465d"))
    f.update_layout(barmode="group")
    c7.plotly_chart(_bo_fig(f, 300, "Buy / Sell Volume แยกตามเหรียญ (THB)").update_layout(showlegend=True), **WIDE)

    rc = ok.groupby("เหรียญ")[["รายได้", "ต้นทุน"]].sum()
    f = go.Figure([go.Bar(name="รายได้", x=rc.index, y=rc["รายได้"], marker_color="#0ecb81"),
                   go.Bar(name="ต้นทุน", x=rc.index, y=-rc["ต้นทุน"], marker_color="#f6465d")])
    f.update_layout(barmode="relative")
    c8.plotly_chart(_bo_fig(f, 300, "Revenue vs Cost แยกตามเหรียญ (THB)").update_layout(showlegend=True), **WIDE)

    m = ok.assign(เดือน=pd.to_datetime(ok["วันที่"]).dt.to_period("M").astype(str)) \
          .groupby("เดือน")["Hedge (USD)"].sum()
    f = go.Figure(go.Bar(x=m.index, y=m.values, marker_color="#3B82F6"))
    f.add_hline(y=fx_lim, line=dict(color="#f6465d", dash="dash"), annotation_text="FX Limit/เดือน")
    st.plotly_chart(_bo_fig(f, 280, "การใช้ FX รายเดือนเทียบ Limit (USD)"), **WIDE)

    with st.expander("ดาวน์โหลดสมุดออเดอร์ (CSV)"):
        st.download_button("⬇️ Ledger CSV", to_csv_bytes(df), "xspring_ledger.csv", "text/csv", **WIDE)


def build_dealer_ctx(cfg: dict[str, Any], data: pd.DataFrame) -> Optional[tuple[dict[str, Any], float]]:
    """คำนวณ ctx และ target_stock_thb ร่วมกันสำหรับ order simulator และ alerts"""
    if data.empty:
        return None
    settlement_days = cfg["settlement_days"]
    asset = cfg["asset"]
    rp_sim = risk_profile(data["Global_USD"])
    if rp_sim is None:
        return None
    h_crypto_sim = crypto_haircut(rp_sim["es99"], settlement_days)
    h_cex_sim = (cfg["cex_counterparty_haircut"]
                 if cfg["cex_margin_asset"].startswith("Stablecoin") else h_crypto_sim)
    a_factor_sim = safety_stock_factor(cfg["net_bias_pct"], cfg["flow_cv_pct"],
                                       settlement_days, cfg["z_alpha"])
    target_stock_thb = a_factor_sim * cfg["monthly_volume_thb"]
    cex_liquidity_thb = max(0.0, float(cfg["cex_margin_thb"]))
    ctx = dict(
        asset=asset, local_premium=cfg["local_premium"], spread=cfg["dealer_spread"],
        hedge_fee=cfg["hedge_fee"], fx_limit=cfg["fx_limit_max"], slip_sens=cfg["slippage_sensitivity"],
        market_depth_usd=cfg["market_depth_usd"], impact_penalty=cfg["impact_penalty"],
        include_fee_rev=cfg["include_trading_fee_revenue"], wd_markup=cfg["withdrawal_fee_markup_pct"],
        wd_fee_per_coin=WITHDRAWAL_FEE_TABLE.get(asset, 0.0), bank_type=cfg["bank_type"],
        ktb_wd_fee=cfg["ktb_wd_fee_thb"], ktb_fx_bps=cfg["ktb_fx_spread_bps"],
        capital=cfg["total_capital_thb"], cex_margin=cfg["cex_margin_thb"],
        cex_liquidity_thb=cex_liquidity_thb, liab=cfg["liab_thb"],
        h_crypto=h_crypto_sim, h_cex=h_cex_sim, fixed_min_nc=cfg["fixed_min_nc"],
        trading_risk_rate=cfg["trading_risk_rate"], daily_volume_thb=cfg["daily_volume_thb"],
        custody_rate=cfg["custody_rate_blended"], hot_breach=cfg["hot_wallet_cap_breach"],
    )
    return ctx, target_stock_thb


def render_tab3(cfg: dict[str, Any], data: pd.DataFrame, data_err: Optional[str],
                price_lookup: Optional[dict[str, float]] = None,
                market_df: Optional[pd.DataFrame] = None) -> None:

    if data.empty:
        st.error(f"⚠️ ต้องโหลดราคาจริงก่อนถึงจะจำลองได้: {data_err or 'ไม่สามารถโหลดข้อมูลได้'}")
        return

    asset = cfg["asset"]
    built = build_dealer_ctx(cfg, data)
    if built is None:
        st.error(f"ข้อมูลย้อนหลังน้อยกว่า {MIN_RISK_SAMPLE_DAYS} วัน — กรุณาเลือกช่วงเวลาให้ยาวขึ้น")
        return
    ctx, target_stock_thb = built

    signature = sim_config_signature(ctx, target_stock_thb, cfg["start_date"], cfg["end_date"])

    if "sim" not in st.session_state:
        first_day = pd.to_datetime(data.index[-1])
        st.session_state.sim = sim_defaults(
            asset, first_day, data.loc[first_day, "Global_USD"],
            data.loc[first_day, "USDTHB"], target_stock_thb)
        st.session_state.sim_steps = []

    current_date_val = pd.to_datetime(data.index[-1])   # ราคาปัจจุบันเสมอ
    st.session_state.sim["current_date"] = current_date_val

    spot_usd_current = float(data.loc[current_date_val, "Global_USD"])
    usdthb_current = float(data.loc[current_date_val, "USDTHB"])

    sim = sim_normalize_state(st.session_state.sim, asset, current_date_val, spot_usd_current, usdthb_current, target_stock_thb)
    st.session_state.sim = sim

    mid_now = spot_usd_current * usdthb_current * (1 + cfg["local_premium"])
    
    check_open_orders(sim, mid_now * (1 + cfg["dealer_spread"]),
                      mid_now * (1 - cfg["dealer_spread"]), data, current_date_val, ctx)

    row_now = data.loc[current_date_val]
    fx_adj = usdthb_current * (1 + cfg["local_premium"])
    high_24h = float(row_now["Day_High"]) * fx_adj
    low_24h = float(row_now["Day_Low"]) * fx_adj
    vol_24h_thb = cfg["daily_volume_thb"]
    if market_df is not None and not market_df.empty:
        _r = market_df[market_df["symbol"] == asset]
        if not _r.empty:
            vol_24h_thb = float(_r["volume"].iloc[0]) * usdthb_current

    pct_24h = None
    if market_df is not None and not market_df.empty:
        m_row = market_df[market_df["symbol"] == asset]
        if not m_row.empty:
            pct_24h = float(m_row["pct_change"].iloc[0])
    if pct_24h is None:
        pct_txt, pct_cls = "เปลี่ยน 24H —", ""
    else:
        pct_txt = f"เปลี่ยน 24H {'+' if pct_24h >= 0 else ''}{pct_24h:.2f}%"
        pct_cls = "ex-green" if pct_24h >= 0 else "ex-red"

    # --- TOP HEADER BAR ---
    top_bar_html = f"""<div class="ex-header">
        <div style="display:flex; align-items:center; gap:12px;">
            {coin_icon_html(asset, 40)}
            <div class="ex-stat">
                <span style="font-size:1.4rem; font-weight:700; color:#EAECEF;">{asset}/THB</span>
                <span style="font-size:0.8rem; font-weight:600;" class="{pct_cls}">{pct_txt}</span>
            </div>
        </div>
        <div class="ex-stat"><span class="ex-stat-label">ราคาล่าสุด (THB)</span><span class="ex-stat-val ex-green">{mid_now:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">สูงสุด 24H (THB)</span><span class="ex-stat-val">{high_24h:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">ต่ำสุด 24H (THB)</span><span class="ex-stat-val">{low_24h:,.2f}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">ปริมาณ 24H (THB)</span><span class="ex-stat-val">{fmt_num(vol_24h_thb)}</span></div>
        <div class="ex-stat"><span class="ex-stat-label">วันที่ (ปัจจุบัน)</span><span class="ex-stat-val" style="color:#fcd535;">{current_date_val.strftime('%Y-%m-%d')}</span></div>
    </div>"""
    st.markdown(top_bar_html, unsafe_allow_html=True)

    # --- MAIN LAYOUT: Market | Chart + Order Panel + Tabs ---
    col_left, col_center = st.columns([2.6, 7.4], gap="small")

    with col_left:
        st.markdown('<div style="font-size:1.15rem; font-weight:700; color:#EAECEF; margin-bottom:12px; display:flex; align-items:center; gap:8px;">🌍 ภาพรวมตลาด (Market)</div>', unsafe_allow_html=True)
        m_df = market_df if market_df is not None else pd.DataFrame()
        sub1, sub2, sub3, sub4 = st.tabs(["⭐", "ปริมาณ", "▲ เพิ่ม", "▼ ลด"])
        for sub, mode in zip((sub1, sub2, sub3, sub4),
                             ("favorite", "volume", "top_gain", "top_loss")):
            with sub:
                try:
                    cont = st.container(height=480, border=False)
                except Exception:
                    cont = st.container()
                with cont:
                    render_market_column_view(m_df, mode, asset, usdthb_current)

    with col_center:
        local_sym = TV_LOCAL_SYMBOL.get(asset, f"BITKUB:{asset}THB")
        render_tradingview(local_sym, f"tv_center_{asset}", 460,
                           studies=["MAExp@tv-basicstudies"])

        with st.container(border=True):
            _order_panel_live(cfg, sim, asset, mid_now, data, current_date_val, ctx)

        with st.expander("🎲 เครื่องมือจำลอง — สุ่มออเดอร์ / รีเซ็ต", expanded=False):
            st.caption("สุ่มออเดอร์ = ลูกค้าคนอื่นในตลาด ไม่แตะกระเป๋าของคุณ · "
                       "สุ่มทั้งเหรียญ วันที่ ฝั่งซื้อ/ขาย และจำนวนเงิน · "
                       "รีเซ็ตจะล้างทุกอย่างรวมถึงกระเป๋า")
            coins_pick = st.multiselect("เหรียญที่ให้สุ่ม", SUPPORTED_ASSETS,
                                        default=SUPPORTED_ASSETS, key="sim_coins")
            b1, b2, b3 = st.columns(3)
            n_orders = b1.number_input("จำนวนออเดอร์สุ่ม", value=20, min_value=1,
                                       step=10, key="sim_n")
            seed = b2.number_input("Random seed", value=42, step=1, key="sim_seed")
            run_batch = b3.button("🎲 สุ่มออเดอร์ (Auto-Run)", key="sim_batch", disabled=not can_trade(), **WIDE)
            a1, a2 = st.columns(2)
            amt_min = a1.number_input("ยอดต่ำสุด/ออเดอร์ (THB)", value=50.0,
                                      min_value=float(MIN_TRADE_THB), step=50.0,
                                      key="sim_amt_min")
            amt_max = a2.number_input("ยอดสูงสุด/ออเดอร์ (THB)", value=100000.0,
                                      min_value=float(MIN_TRADE_THB), step=1000.0,
                                      key="sim_amt_max")
            reset = st.button("♻️ ล้างระบบใหม่", key="sim_reset", disabled=not can_trade(), **WIDE)
            summ = st.session_state.get("sim_batch_summary")
            if summ:
                st.caption(summ)

        if reset:
            first_day = pd.to_datetime(data.index[-1])
            st.session_state.sim = sim_defaults(
                asset, first_day, data.loc[first_day, "Global_USD"],
                data.loc[first_day, "USDTHB"], target_stock_thb)
            st.session_state.sim_signature = signature
            st.session_state.sim_steps = []
            
            st.session_state["favorite_tickers"] = []
            try:
                save_favorites([])
            except OSError:
                pass
                
            st.rerun()

        if run_batch:
            if not coins_pick:
                st.warning("เลือกอย่างน้อย 1 เหรียญ")
            else:
                steps_, counts, skipped = run_random_batch(
                    sim, cfg, ctx, target_stock_thb, coins_pick,
                    n_orders, seed, amt_min, amt_max)
                st.session_state.sim_steps = steps_
                txt = "สุ่มแล้ว: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                if skipped:
                    txt += f" · โหลดราคาไม่ได้: {', '.join(skipped)}"
                st.session_state.sim_batch_summary = txt
                st.rerun()


        st.markdown('<div style="margin-top:14px;"></div>', unsafe_allow_html=True)
        t_route, t_ledger, t_wallet = st.tabs(
            ["🚀 System Routing", "📒 สมุดออเดอร์ (Ledger)", "🏢 Back Office"])

        with t_route:
            steps_now = st.session_state.get("sim_steps", [])
            if not steps_now:
                st.info("ยังไม่มีออเดอร์ — กดซื้อ/ขายด้านบนเพื่อดูระบบเดินงานทีละด่าน")
            else:
                render_timeline(steps_now)
                render_binance_price_check(asset, spot_usd_current)

        with t_ledger:
            if not sim["orders"]:
                st.caption("ยังไม่มีข้อมูลการเทรด")
            else:
                led = pd.DataFrame(sim["orders"])
                if st.checkbox(f"แสดงเฉพาะ {asset}", key="led_only_asset"):
                    led = led[led["เหรียญ"] == asset]
                led.index = range(1, len(led) + 1)
                st.dataframe(led.sort_index(ascending=False), height=240, **WIDE)

        with t_wallet:
            price_thb = {r["symbol"]: float(r["price_usd"]) * usdthb_current
                         for _, r in (market_df if market_df is not None else pd.DataFrame()).iterrows()}
            price_thb[asset] = spot_usd_current * usdthb_current
            render_backoffice(sim, cfg, ctx, target_stock_thb, price_thb)


def _parse_amount(text: Any) -> float:
    try:
        v = float(str(text).replace(",", "").replace(" ", "").strip())
    except ValueError:
        return 0.0
    return v if math.isfinite(v) and v > 0 else 0.0


def _open_deposit() -> None:
    st.session_state["open_deposit"] = True
    st.session_state["dep_error"] = None


def _set_dep_amt(v: float) -> None:
    st.session_state["dep_amt"] = f"{v:,.0f}"


def _do_deposit() -> None:
    amt = _parse_amount(st.session_state.get("dep_amt", "0"))
    if amt <= 0:
        st.session_state["dep_error"] = "กรอกจำนวนเงินที่มากกว่า 0"
        return
    sim = st.session_state.get("sim")
    if not isinstance(sim, dict):
        sim = {"customer_thb": 1_000_000.0, "customer_coins": {}}
        st.session_state["sim"] = sim
    sim["customer_thb"] = float(sim.get("customer_thb", 1_000_000.0)) + amt
    st.session_state["dep_amt"] = "0"
    st.session_state["dep_error"] = None
    st.session_state["dep_done"] = amt


def _deposit_dialog_body() -> None:
    done = st.session_state.pop("dep_done", None)
    if done:
        st.session_state["dep_toast"] = done
        st.rerun()  # รีรันทั้งแอป: ปิดหน้าต่าง + อัปเดตยอดในตาราง

    sim = st.session_state.get("sim")
    cash = float(sim.get("customer_thb", 1_000_000.0)) if isinstance(sim, dict) else 1_000_000.0
    st.markdown(f"ยอดเงินบาทคงเหลือ: **{cash:,.2f} THB**")

    amt = comma_number_input("จำนวนเงินที่ต้องการฝาก (THB)", value=0,
                             min_value=0, key="dep_amt")
    quick = st.columns(4, gap="small")
    for col, v in zip(quick, (1_000, 10_000, 100_000, 1_000_000)):
        col.button(f"{v:,.0f}", key=f"dep_q_{v}", on_click=_set_dep_amt,
                   args=(float(v),), **WIDE)

    st.caption(f"ยอดหลังฝาก: {cash + amt:,.2f} THB · โหมดจำลอง เงินนี้ใช้ในกระเป๋าจำลองเท่านั้น")
    err = st.session_state.get("dep_error")
    if err:
        st.error(err)
    st.button("ยืนยันการฝาก", key="dep_confirm", type="primary",
              on_click=_do_deposit, **WIDE)


def deposit_dialog() -> None:
    # ห่อ st.dialog ตอนเรียกใช้ (ไม่ใช้ @decorator ระดับโมดูล)
    # เพื่อให้ import ไฟล์นี้ใน unittest ได้แม้ไม่มี streamlit
    st.dialog("ฝากเงินบาท")(_deposit_dialog_body)()


# ---- 5.5 TAB 4 — WALLET ------------------------------------------------

def render_tab4(cfg: dict[str, Any], data: pd.DataFrame, market_df: pd.DataFrame) -> None:
    if data.empty:
        st.error("⚠️ ไม่สามารถโหลดข้อมูลได้")
        return

    sim = st.session_state.get("sim", {})
    current_date_val = pd.to_datetime(data.index[-1])

    usdthb_current = float(data.loc[current_date_val, "USDTHB"])
    cust_thb = sim.get("customer_thb", 1000000.0)
    cust_coins = sim.get("customer_coins", {})

    price_thb_map = {"THB": 1.0}
    if market_df is not None and not market_df.empty:
        for _, row in market_df.iterrows():
            sym = str(row["symbol"])
            price_thb_map[sym] = float(row["price_usd"]) * usdthb_current
    price_thb_map[cfg["asset"]] = float(data.loc[current_date_val, "Global_USD"]) * usdthb_current

    total_thb = cust_thb
    for sym, qty in cust_coins.items():
        total_thb += qty * price_thb_map.get(sym, 0.0)

    total_usdt = total_thb / usdthb_current if usdthb_current > 0 else 0
    time_str = pd.Timestamp.now(tz="Asia/Bangkok").strftime("%H:%M:%S")

    # Header (ไม่มีปุ่มฝาก/ถอน/ประวัติ ตามที่ร้องขอ)
    st.markdown(
        f'<div style="margin-bottom:20px;">'
        f'<h2 style="margin:0; color:#EAECEF; font-size:1.8rem;">กระเป๋าเงิน</h2>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Total Box
    st.markdown(
        f'<div class="wl-box" style="margin-bottom:20px;">'
        f'<div style="font-size:0.9rem; color:#848e9c; font-weight:600;">มูลค่าทั้งหมด</div>'
        f'<div class="wl-total-val">{total_thb:,.2f} <span style="font-size:1.2rem; color:#848e9c;">THB</span></div>'
        f'<div style="font-size:0.9rem; color:#848e9c;">≈ {total_usdt:,.2f} USDT <span style="float:right; font-size:0.8rem;">อัปเดตล่าสุด: {time_str}</span></div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # Asset Table Title and Controls
    st.markdown(
        '<div style="display:flex; align-items:center; margin-bottom:16px; gap:8px;">'
        '<div style="width:3px; height:16px; background:#0ecb81; border-radius:2px;"></div>'
        '<div style="font-size:1.05rem; font-weight:700; color:#EAECEF;">สินทรัพย์</div>'
        '</div>',
        unsafe_allow_html=True
    )

    c_search, c_hide, c_pad = st.columns([2, 1.5, 6])
    with c_search:
        search_q = st.text_input("ค้นหา", label_visibility="collapsed", placeholder="🔍 ค้นหาสินทรัพย์")
    with c_hide:
        st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
        hide_small = st.checkbox("ซ่อนเหรียญที่มูลค่า < 1 บาท", value=False)

    # Asset List Construction
    assets_to_show = [{"sym": "THB", "qty": cust_thb, "price": 1.0, "val": cust_thb}]
    for sym in SUPPORTED_ASSETS:
        qty = cust_coins.get(sym, 0.0)
        price = price_thb_map.get(sym, 0.0)
        assets_to_show.append({"sym": sym, "qty": qty, "price": price, "val": qty * price})
        
    WL = [2.2, 1.5, 1.5, 1.5, 1.3]
    with st.container(key="wl_table"):
        with st.container(key="wlhead"):
            hc = st.columns(WL, vertical_alignment="center", gap="small")
            heads = ["สินทรัพย์ ↕", "มูลค่าทั้งหมด ↕", "จำนวนที่ใช้ได้ ↕", "รอดำเนินการ ↕", ""]
            aligns = ["left", "right", "right", "right", "right"]
            for col, txt, al in zip(hc, heads, aligns):
                col.markdown(f'<div class="wl-h" style="text-align:{al}">{txt}</div>',
                             unsafe_allow_html=True)
        for a in assets_to_show:
            sym = a["sym"]
            sub_name = COIN_NAMES.get(sym, "Thai Baht")
            if hide_small and a["val"] < 1.0:
                continue
            if search_q and search_q.lower() not in sym.lower() \
                    and search_q.lower() not in sub_name.lower():
                continue
            with st.container(key=f"wlrow_{sym}"):
                c_ast, c_val, c_qty, c_pend, c_act = st.columns(
                    WL, vertical_alignment="center", gap="small")
                with c_ast:
                    c_ic, c_nm = st.columns([1, 6], vertical_alignment="center", gap="small")
                    c_ic.markdown(coin_icon_html(sym, 28), unsafe_allow_html=True)
                    if sym == "THB":
                        c_nm.markdown('<div class="wl-name">THB<br><span>Thai Baht</span></div>',
                                      unsafe_allow_html=True)
                    else:
                        c_nm.button(f"{sym}  ·  {sub_name}", key=f"wlbtn_{sym}",
                                    type="tertiary", on_click=_go_to_exchange, args=(sym,),
                                    help=f"เปิดกราฟและหน้าเทรด {sym}")
                c_val.markdown(f'<div class="wl-cell">{a["val"]:,.2f}</div>', unsafe_allow_html=True)
                c_qty.markdown(f'<div class="wl-cell">{a["qty"]:,.6f}</div>', unsafe_allow_html=True)
                c_pend.markdown('<div class="wl-cell" style="color:#848e9c;">0.00</div>',
                                unsafe_allow_html=True)
                
                a_dep, a_wd, a_more = c_act.columns([1, 1, 0.7],
                                                    vertical_alignment="center", gap="small")
                if sym == "THB":
                    a_dep.button("ฝาก", key="wl_deposit", type="tertiary",
                                 on_click=_open_deposit, disabled=not can_trade(), **WIDE)
                else:
                    a_dep.markdown('<div class="wl-act">ฝาก</div>', unsafe_allow_html=True)
                a_wd.markdown('<div class="wl-act">ถอน</div>', unsafe_allow_html=True)
                a_more.markdown('<div class="wl-act wl-more">•••</div>', unsafe_allow_html=True)

    dep_toast = st.session_state.pop("dep_toast", None)
    if dep_toast:
        st.toast(f"ฝากเงิน {dep_toast:,.2f} THB สำเร็จ", icon="✅")
    if st.session_state.pop("open_deposit", False):
        deposit_dialog()

# ---------------- ฟังก์ชัน AI ----------------

AI_SYSTEM = (
    "คุณคือผู้ช่วยในแอป XSpring Dealer Suite (เครื่องมือจำลอง Backtest, วางแผนสภาพคล่องและเงินกองทุน NC, "
    "จำลองหน้าเทรด และกระเป๋าเงินจำลอง) ตอบเป็นภาษาไทย สั้น กระชับ ไม่เกิน 4-5 ประโยค ภาษาง่าย "
    "อธิบายความหมายของตัวเลขและวิธีใช้งานแอปได้ แต่ห้ามแนะนำว่าควรซื้อเหรียญไหน ห้ามให้คำแนะนำลงทุน "
    "และห้ามรับรอง compliance ถ้าถามนอกเรื่อง ให้ปฏิเสธสุภาพแล้วชวนกลับมาเรื่องแอป"
)

def ask_ai(messages, api_key, system_override: Optional[str] = None):
    AI_MODEL = "gemini-3-flash-preview"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent?key={api_key}"

    formatted_messages = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        formatted_messages.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "systemInstruction": {"parts": [{"text": system_override or AI_SYSTEM}]},
        "contents": formatted_messages,
        "generationConfig": {
            "maxOutputTokens": 1500,
            "thinkingConfig": {"thinkingLevel": "low"}
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"]

    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "ใช้โควตาฟรีครบชั่วคราว รอสักครู่แล้วลองใหม่"
        try:
            detail = json.loads(e.read().decode("utf-8"))["error"]["message"]
        except Exception:
            detail = ""
        return f"เรียก AI ไม่สำเร็จ (HTTP {e.code}) {detail}"

    except Exception as e:
        return f"ข้อผิดพลาดระบบ: {str(e)}"

# =========================================================================
# LEDGER ANOMALY DETECTOR — สถิติ (z-score) + AI สรุปเป็นภาษาคน
# =========================================================================

ANOMALY_AI_SYSTEM = (
    "คุณคือนักวิเคราะห์ความเสี่ยงของ Dealer คริปโท ได้รับรายการ anomaly ที่ระบบตรวจจับได้จาก order ledger "
    "(เช่น slippage พุ่ง, hedge fee พุ่ง, P&L ร่วงหนัก, reject rate สูงผิดปกติเป็นกลุ่ม) "
    "สรุปเป็นภาษาไทย กระชับ ไม่เกิน 6-8 ประโยค บอกว่าเกิดอะไรขึ้น ช่วงไหนน่าเป็นห่วงที่สุด และมีสาเหตุที่เป็นไปได้อะไรบ้าง "
    "พร้อมคำแนะนำเชิงปฏิบัติการทั่วไป (เช่น ตรวจสอบพารามิเตอร์ hedge, ทบทวน slippage sensitivity, ลด order size ชั่วคราว) "
    "ห้ามให้คำแนะนำการลงทุนหรือรับรอง compliance"
)


def ask_ai_anomaly(anomaly_summary_text: str, api_key: str) -> str:
    return ask_ai([{"role": "user", "content": anomaly_summary_text}], api_key,
                  system_override=ANOMALY_AI_SYSTEM)


def _rolling_zscore(s: pd.Series, window: int = 20, min_periods: int = 10) -> pd.Series:
    roll_mean = s.rolling(window, min_periods=min_periods).mean()
    roll_std = s.rolling(window, min_periods=min_periods).std().replace(0, np.nan)
    z = (s - roll_mean) / roll_std
    return z.fillna(0.0)


def detect_ledger_anomalies(bt: pd.DataFrame, z_threshold: float = 2.5,
                            reject_window: int = 7) -> pd.DataFrame:
    """สแกน Daily Ledger หา pattern ผิดปกติ: slippage/hedge fee พุ่ง, P&L ร่วงหนัก,
    reject rate (FX Limit Hit) สูงผิดปกติเป็นกลุ่ม, ความผันผวนพุ่ง"""
    if bt.empty or len(bt) < 15:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []

    def _flag(date, metric, value, z, kind, note, severity):
        rows.append(dict(date=date, metric=metric, value=value, z_score=float(z),
                         kind=kind, note=note, severity=severity))

    if "Slippage_Cost_THB" in bt.columns and bt["Slippage_Cost_THB"].abs().sum() > 0:
        z_slip = _rolling_zscore(bt["Slippage_Cost_THB"])
        for d, v, z in zip(bt.index, bt["Slippage_Cost_THB"], z_slip):
            if z >= z_threshold:
                sev = "critical" if z >= z_threshold * 1.6 else "warning"
                _flag(d, "Slippage Cost", v, z, "slippage",
                     f"Slippage วันนี้ {fmt_baht(v)} สูงกว่าค่าเฉลี่ยเคลื่อนที่ {z:.1f} SD", sev)

    if "Hedge_Fee_Cost_THB" in bt.columns:
        z_fee = _rolling_zscore(bt["Hedge_Fee_Cost_THB"])
        for d, v, z in zip(bt.index, bt["Hedge_Fee_Cost_THB"], z_fee):
            if z >= z_threshold:
                sev = "critical" if z >= z_threshold * 1.6 else "warning"
                _flag(d, "Hedge Fee Cost", v, z, "hedge_fee",
                     f"ต้นทุน Hedge Fee วันนี้ {fmt_baht(v)} สูงกว่าปกติ {z:.1f} SD", sev)

    if "Daily_PnL_THB" in bt.columns:
        z_pnl = _rolling_zscore(bt["Daily_PnL_THB"])
        for d, v, z in zip(bt.index, bt["Daily_PnL_THB"], z_pnl):
            if z <= -z_threshold:
                sev = "critical" if z <= -z_threshold * 1.6 else "warning"
                _flag(d, "Daily P&L", v, z, "pnl_crash",
                     f"P&L วันนี้ {fmt_baht(v, True)} ต่ำผิดปกติ {abs(z):.1f} SD จากค่าเฉลี่ย", sev)

    if "FX_Limit_Hit" in bt.columns:
        overall_rate = float(bt["FX_Limit_Hit"].mean())
        rolling_rate = bt["FX_Limit_Hit"].rolling(reject_window, min_periods=reject_window).mean()
        if overall_rate > 0:
            for d, rr in zip(bt.index, rolling_rate):
                if pd.notna(rr) and rr >= max(0.4, overall_rate * 2.5):
                    _flag(d, f"FX Limit Hit Rate ({reject_window}D)", rr * 100,
                         rr / max(overall_rate, 1e-9), "reject_cluster",
                         f"อัตราติด FX Limit ใน {reject_window} วันล่าสุด {rr*100:.0f}% "
                         f"สูงกว่าค่าเฉลี่ยทั้งช่วง ({overall_rate*100:.0f}%) มาก",
                         "critical" if rr >= 0.7 else "warning")

    if "Volatility_Pct" in bt.columns:
        z_vol = _rolling_zscore(bt["Volatility_Pct"])
        for d, v, z in zip(bt.index, bt["Volatility_Pct"], z_vol):
            if z >= z_threshold:
                _flag(d, "Volatility (High-Low)", v * 100, z, "volatility",
                     f"ความผันผวนรายวัน {v*100:.2f}% สูงกว่าปกติ {z:.1f} SD", "warning")

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("date", ascending=False)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)


_ANOMALY_KIND_LABEL = {
    "slippage": "💥 Slippage พุ่ง", "hedge_fee": "💸 Hedge Fee พุ่ง",
    "pnl_crash": "📉 P&L ร่วงหนัก", "reject_cluster": "🚫 Reject Rate สูงเป็นกลุ่ม",
    "volatility": "🌪️ ความผันผวนพุ่ง",
}
_ANOMALY_KIND_COLOR = {
    "slippage": "#f6465d", "hedge_fee": "#fcd535", "pnl_crash": "#f6465d",
    "reject_cluster": "#9945FF", "volatility": "#3B82F6",
}


def render_ledger_anomaly_detector(cfg: dict[str, Any], bt: pd.DataFrame) -> None:
    with st.expander("🕵️ Anomaly Detector — สแกนหา Pattern ผิดปกติใน Ledger", expanded=False):
        st.caption(
            "สแกน Daily Ledger อัตโนมัติด้วยสถิติ (rolling z-score) หา slippage/hedge fee ที่พุ่งผิดปกติ, "
            "P&L ร่วงหนัก, และช่วงที่ reject rate (FX Limit Hit) สูงผิดปกติเป็นกลุ่ม — จากนั้นให้ AI ช่วยสรุปได้"
        )
        c1, c2 = st.columns(2)
        z_th = c1.slider("ความไวในการจับ Anomaly (Z-score threshold)", 1.5, 4.0, 2.5, 0.1, key="anom_z")
        reject_win = c2.number_input("หน้าต่าง Reject Rate (วัน)", value=7, min_value=3,
                                     max_value=30, step=1, key="anom_win")

        if st.button("🕵️ สแกนหา Anomaly", key="anom_scan", **WIDE):
            st.session_state["anom_result"] = detect_ledger_anomalies(
                bt, z_threshold=z_th, reject_window=int(reject_win))
            st.session_state.pop("anom_ai_summary", None)

        anoms = st.session_state.get("anom_result")
        if anoms is None:
            return
        if anoms.empty:
            st.success("✅ ไม่พบ pattern ผิดปกติในช่วงเวลาที่เลือก")
            return

        n_crit = int((anoms["severity"] == "critical").sum())
        n_warn = int((anoms["severity"] == "warning").sum())
        k = st.columns(3)
        metric_card(k[0], "Anomaly ที่พบทั้งหมด", f"{len(anoms)}", None)
        metric_card(k[1], "ระดับ Critical", f"{n_crit}", -1 if n_crit else 0)
        metric_card(k[2], "ระดับ Warning", f"{n_warn}", 0)

        show = anoms.copy()
        show["ประเภท"] = show["kind"].map(_ANOMALY_KIND_LABEL).fillna(show["kind"])
        show_disp = show[["date", "ประเภท", "note", "severity"]].rename(
            columns={"date": "วันที่", "note": "รายละเอียด", "severity": "ระดับ"})
        st.dataframe(show_disp, height=min(360, 40 + 35 * len(show_disp)), **WIDE)

        fig = go.Figure()
        for kind, color in _ANOMALY_KIND_COLOR.items():
            sub = anoms[anoms["kind"] == kind]
            if not sub.empty:
                fig.add_trace(go.Scatter(
                    x=sub["date"], y=sub["z_score"], mode="markers",
                    name=_ANOMALY_KIND_LABEL.get(kind, kind),
                    marker=dict(size=9, color=color, symbol="x")))
        fig.add_hline(y=0, line=dict(color="#848e9c", dash="dot"))
        fig.update_layout(
            template="plotly_dark", height=320, margin=dict(t=20, b=20),
            yaxis_title="Z-score / Severity", title=dict(text="Anomaly Timeline", font=dict(size=13)),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", y=1.15, yanchor="bottom"))
        st.plotly_chart(fig, **WIDE)

        try:
            api_key = st.secrets["gemini_api_key"]
        except Exception:
            api_key = os.environ.get("GEMINI_API_KEY", "")

        if st.button("🤖 ให้ AI สรุปและวิเคราะห์", key="anom_ai_btn",
                    disabled=not bool(api_key), **WIDE):
            top = anoms.reindex(anoms["z_score"].abs().sort_values(ascending=False).index).head(25)
            lines = [f"{r['date']} · {_ANOMALY_KIND_LABEL.get(r['kind'], r['kind'])} · {r['note']}"
                    for _, r in top.iterrows()]
            prompt = (
                f"เหรียญ: {cfg['asset']} · พบ anomaly ทั้งหมด {len(anoms)} รายการ "
                f"(critical {n_crit}, warning {n_warn})\n\nรายการที่รุนแรงที่สุด 25 อันดับแรก:\n"
                + "\n".join(lines)
            )
            with st.spinner("AI กำลังวิเคราะห์…"):
                st.session_state["anom_ai_summary"] = ask_ai_anomaly(prompt, api_key)

        if not api_key:
            st.caption("🔒 ยังไม่ได้ตั้งค่า `gemini_api_key` — ใช้ได้เฉพาะการสแกนด้วยสถิติ")

        ai_txt = st.session_state.get("anom_ai_summary")
        if ai_txt:
            st.markdown(
                f'<div style="background:rgba(14,203,129,.06);border-left:3px solid #0ecb81;'
                f'border-radius:4px;padding:12px 16px;margin-top:8px;color:#EAECEF;'
                f'font-size:.88rem;line-height:1.7;white-space:pre-wrap;">🤖 {_html.escape(ai_txt)}</div>',
                unsafe_allow_html=True,
            )


AI_SUGGESTIONS = [
    "Max Drawdown กับ Win Rate ในหน้า Backtest หมายถึงอะไร",
    "FX Limit Hit คืออะไร และกระทบกำไรยังไง",
    "NC กับ NC Buffer คืออะไร ทำไมต้องดำรงขั้นต่ำ",
    "Hedge กับ Dealer Spread ทำงานยังไง",
    "หน้า Exchange UI Simulator ใช้ซื้อ/ขายและสุ่มออเดอร์ยังไง",
]

def _ai_queue(q: str) -> None:
    st.session_state["ai_pending"] = q

def _ai_bubble(role: str, text: str) -> str:
    t = _html.escape(str(text))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = t.replace("\n", "<br>")
    cls = "user" if role == "user" else "bot"
    return f'<div class="ai-row {cls}"><div class="ai-bub">{t}</div></div>'

def _ai_clear() -> None:
    st.session_state["chat_messages"] = []

def render_ai_fab() -> None:
    try:
        api_key = st.secrets["gemini_api_key"]
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        
    hist = st.session_state.setdefault("chat_messages", [])
    pending = st.session_state.pop("ai_pending", None)
    
    with st.container(key="ai_fab"):
        with st.popover("💬 ถาม AI"):
            if not api_key or api_key.startswith("AIza..."):
                st.warning("ยังไม่ได้ตั้ง `gemini_api_key` ใน Secrets")
                return
                
            box = st.container(height=380, border=False)
            with box:
                ph = st.empty()
                sug_ph = st.empty()
                
            def draw():
                if hist:
                    ph.markdown("".join(_ai_bubble(m["role"], m["content"]) for m in hist),
                                unsafe_allow_html=True)
                else:
                    ph.markdown('<div class="ai-empty">ลองกดคำถามด้านล่าง หรือพิมพ์เองได้เลย</div>',
                                unsafe_allow_html=True)
                                
            # ปุ่มคำถามตัวอย่าง (แสดงเฉพาะตอนยังไม่เริ่มคุย)
            if not hist and not pending:
                with sug_ph.container():
                    for i, s in enumerate(AI_SUGGESTIONS):
                        st.button(s, key=f"ai_sug_{i}", on_click=_ai_queue,
                                  args=(s,), **WIDE)
                                  
            with st.form("ai_form", clear_on_submit=True):
                c1, c2 = st.columns([5, 1.4], vertical_alignment="center")
                q = c1.text_input("พิมพ์ข้อความ", label_visibility="collapsed",
                                  placeholder="พิมพ์ข้อความ…")
                sent = c2.form_submit_button("ส่ง")
                
            question = q.strip() if (sent and q.strip()) else pending
            
            if question:
                sug_ph.empty()
                hist.append({"role": "user", "content": question})
                draw()
                with st.spinner("กำลังคิด…"):
                    ans = ask_ai(hist, api_key)
                hist.append({"role": "assistant", "content": ans})
            draw()
            
            if hist:
                st.button("🗑️ ล้างแชท", key="ai_clear", on_click=_ai_clear)

def compute_active_alerts(cfg: dict[str, Any], sim: Optional[dict[str, Any]],
                         data: pd.DataFrame, market_df: Optional[pd.DataFrame]) -> list[dict[str, str]]:
    """เช็ค NC Buffer / FX Limit / CEX Liquidity / Hot Wallet ของ sandbox รายผู้ใช้"""
    alerts: list[dict[str, str]] = []
    if not isinstance(sim, dict) or data.empty or not sim.get("orders"):
        return alerts
    built = build_dealer_ctx(cfg, data)
    if built is None:
        return alerts
    ctx, _target = built
    cur_date = pd.to_datetime(data.index[-1])
    usdthb_now = float(data.loc[cur_date, "USDTHB"])
    price_thb: dict[str, float] = {}
    if market_df is not None and not market_df.empty:
        for _, row in market_df.iterrows():
            price_thb[str(row["symbol"])] = float(row["price_usd"]) * usdthb_now
    price_thb[cfg["asset"]] = float(data.loc[cur_date, "Global_USD"]) * usdthb_now
    stock_thb = sum(max(0.0, float(qty)) * price_thb.get(c, 0.0)
                    for c, qty in sim.get("inv_coins", {}).items())
    nc = nc_snapshot(stock_thb, ctx["capital"], ctx["cex_margin"], ctx["liab"],
                     ctx["h_crypto"], ctx["h_cex"], ctx["fixed_min_nc"],
                     ctx["trading_risk_rate"], ctx["daily_volume_thb"], ctx["custody_rate"])
    if nc["buffer"] < 0:
        alerts.append(dict(level="critical", title="NC Buffer ติดลบ",
                           detail=f"ขาดเงินกองทุน {fmt_baht(abs(nc['buffer']))} จากขั้นต่ำ {fmt_baht(nc['required'])}"))
    elif nc["required"] > 0 and nc["buffer"] < 0.5 * nc["required"]:
        alerts.append(dict(level="warning", title="NC Buffer ใกล้ขั้นต่ำ",
                           detail=f"เหลือ Buffer {fmt_baht(nc['buffer'])} (ต่ำกว่า 50% ของขั้นต่ำ {fmt_baht(nc['required'])})"))
    cur_m = pd.to_datetime(sim.get("current_date", cur_date)).strftime("%Y-%m")
    fx_used = float(sim.get("fx_used_usd_by_month", {}).get(cur_m, 0.0))
    fx_lim = float(cfg["fx_limit_max"])
    if fx_lim > 0:
        fx_pct = fx_used / fx_lim
        if fx_pct >= 1.0:
            alerts.append(dict(level="critical", title="FX Limit เต็มแล้ว",
                               detail=f"ใช้ไป $ {fx_used:,.0f} จาก $ {fx_lim:,.0f} เดือนนี้"))
        elif fx_pct >= 0.9:
            alerts.append(dict(level="warning", title="FX Limit ใกล้เต็ม",
                               detail=f"ใช้ไปแล้ว {fx_pct * 100:.0f}% (${fx_used:,.0f} / ${fx_lim:,.0f})"))
    cex_used = float(sim.get("cex_used_thb", 0.0))
    cex_lim = float(ctx["cex_liquidity_thb"])
    if cex_lim > 0:
        cex_pct = cex_used / cex_lim
        if cex_pct >= 1.0:
            alerts.append(dict(level="critical", title="CEX Liquidity หมด",
                               detail=f"ใช้ไป {fmt_baht(cex_used)} จาก {fmt_baht(cex_lim)}"))
        elif cex_pct >= 0.9:
            alerts.append(dict(level="warning", title="CEX Liquidity ใกล้เต็ม",
                               detail=f"ใช้ไปแล้ว {cex_pct * 100:.0f}%"))
    if ctx.get("hot_breach"):
        alerts.append(dict(level="warning", title="Hot Wallet เกินเพดาน",
                           detail=f"สัดส่วน Hot Wallet {cfg['hot_wallet_pct'] * 100:.0f}% เกินเพดาน {HOT_WALLET_CAP * 100:.0f}%"))
    return alerts


def render_alert_banner(alerts: list[dict[str, str]]) -> None:
    if not alerts:
        return
    prev_keys = st.session_state.get("alert_prev_keys", set())
    cur_keys = {a["title"] for a in alerts}
    for a in alerts:
        if a["title"] not in prev_keys:
            st.toast(f"{a['title']} — {a['detail']}",
                     icon="🚨" if a["level"] == "critical" else "⚠️")
    st.session_state["alert_prev_keys"] = cur_keys
    for a in alerts:
        verdict_box(a["level"] != "critical", f"แจ้งเตือน: {a['title']}", a["detail"],
                    warn=(a["level"] == "warning"))


def _main_body() -> None:
    st.markdown(THEME_CSS, unsafe_allow_html=True)

    if is_guest_mode():
        st.session_state.setdefault("favorite_tickers", [])
        st.session_state["current_role"] = GUEST_ROLE
        email = _guest_email()
        d_name = f"Guest ({st.session_state.get('guest_id', '')})"
        avatar_b64 = ""
    else:
        if "sim" not in st.session_state:
            saved = load_sim_state()
            if saved:
                st.session_state["sim"] = saved

        if "favorite_tickers" not in st.session_state:
            st.session_state["favorite_tickers"] = load_favorites()

        email = getattr(st.user, 'email', '')
        user_prof = load_profiles().get(email, {})
        st.session_state["current_role"] = _normalize_role(user_prof.get("role"))
        d_name = user_prof.get("display_name", email)
        avatar_b64 = user_prof.get("avatar_b64", "")

    # ---- แสดงส่วนหัวด้านบนของหน้าหลัก ----
    top_l, top_news, top_r = st.columns([3.8, 4.4, 2.0])
    with top_l:
        st.markdown(
    f'<div style="display:flex;align-items:center;gap:12px;padding:6px 0;">'
    f'<img src="{DEV_AVATAR_B64}" width="40" height="40" '
    f'style="border-radius:50%;object-fit:cover;border:2px solid #2b3139;">'
    f'<div>'
    f'<div style="color:#EAECEF;font-weight:700;font-size:0.9rem;line-height:1.6;padding-top:2px;">ทำโดย {DEV_NAME}</div>'
    f'<a href="{DEV_LINKEDIN}" target="_blank" '
    f'style="color:#0ecb81;font-size:0.75rem;text-decoration:none;line-height:1.6;">🔗 ดูโปรไฟล์ LinkedIn</a>'
    f'</div></div>',
    unsafe_allow_html=True,
)
    with top_news:
        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
        news_active = st.session_state.get("main_nav") == NAV_NEWS
        # ปุ่มข่าวให้เล็กและอยู่กึ่งกลาง ไม่กินพื้นที่ทั้งคอลัมน์
        _, news_btn, _ = st.columns([1.6, 2.2, 1.6])
        with news_btn:
            if st.button(
                "📰 ข่าว",
                key="top_news_btn",
                type="primary" if news_active else "secondary",
                use_container_width=True,
            ):
                current = st.session_state.get("main_nav")
                if current in [x for x in NAV_LABELS if x != NAV_NEWS]:
                    st.session_state["news_last_tab"] = current
                st.session_state["main_nav"] = NAV_NEWS
                st.session_state.pop("main_nav_tabs_news", None)
                st.rerun()

    with top_r:
        if avatar_b64:
            img_src = f"data:image/png;base64,{avatar_b64}" if not avatar_b64.startswith("http") else avatar_b64
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;justify-content:flex-end;padding:6px 0;">'
                f'<div style="text-align:right;">'
                f'<div style="font-weight:bold;color:#EAECEF;font-size:0.9rem;">{d_name}</div>'
                f'<div style="font-size:0.72rem;color:#848e9c;">{email}</div>'
f'<div style="font-size:0.68rem;color:#0ecb81;">{ROLE_LABEL_TH[current_role()]}</div></div>'
                f'<img src="{img_src}" width="36" height="36" style="border-radius:50%;object-fit:cover;">'
                f'</div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="text-align:right;padding:6px 0;">'
                f'<div style="font-weight:bold;color:#EAECEF;font-size:0.9rem;">👤 {d_name}</div>'
                f'<div style="font-size:0.72rem;color:#848e9c;">{email}</div>'
                f'<div style="font-size:0.68rem;color:#0ecb81;">{ROLE_LABEL_TH[current_role()]}</div></div>',
                unsafe_allow_html=True)

    cfg = build_sidebar()

    with st.sidebar:
        st.divider()
        if is_guest_mode():
            st.button(
                "🚪 ออกจากระบบ Guest (ล้างข้อมูลทั้งหมด)",
                key="logout_btn",
                on_click=_end_guest_session,
                use_container_width=True,
            )
        else:
            st.button("ออกจากระบบ", key="logout_btn", on_click=st.logout, use_container_width=True)

    if not cfg["dates_ok"]:
        data, data_err = pd.DataFrame(), "ช่วงวันที่ไม่ถูกต้อง"
    else:
        data, data_err = fetch_price_data(cfg["asset"], cfg["start_date"],
                                          cfg["end_date"],
                                          use_fx_proxy=cfg["use_fx_proxy"])

    market_df = fetch_market_overview(SUPPORTED_ASSETS)
    render_alert_banner(compute_active_alerts(cfg, st.session_state.get("sim"), data, market_df))

    if "main_nav" not in st.session_state:
        st.session_state["main_nav"] = NAV_LABELS[0]

    # แถบเมนูหลักยังคงแสดงแท็บเดิมทั้งหมด ยกเว้นข่าวที่ย้ายไปเป็นปุ่มเล็กด้านบน
    # ใช้ key แยกจาก main_nav เพื่อให้ radio ไม่หายไปเมื่ออยู่หน้า News
    nav_labels_main = [label for label in NAV_LABELS if label != NAV_NEWS]
    current_nav = st.session_state.get("main_nav", nav_labels_main[0])
    if current_nav not in nav_labels_main and current_nav != NAV_NEWS:
        current_nav = nav_labels_main[0]
        st.session_state["main_nav"] = current_nav

    if current_nav == NAV_NEWS:
        # หน้า News: แสดงแท็บอื่นครบ แต่ไม่เลือกแท็บใดไว้
        # เพื่อให้ผู้ใช้กดกลับไปแท็บไหนก็ได้ รวมถึงแท็บแรก
        selected_nav = st.radio(
            "เมนูหลัก",
            nav_labels_main,
            horizontal=True,
            index=None,
            key="main_nav_tabs_news",
            label_visibility="collapsed",
        )
        nav = selected_nav if selected_nav else NAV_NEWS
        if selected_nav:
            st.session_state["main_nav"] = selected_nav
    else:
        default_idx = nav_labels_main.index(current_nav)
        selected_nav = st.radio(
            "เมนูหลัก",
            nav_labels_main,
            horizontal=True,
            index=default_idx,
            key="main_nav_tabs",
            label_visibility="collapsed",
        )
        nav = selected_nav
        st.session_state["main_nav"] = selected_nav

    if nav == NAV_LABELS[0]:
        render_tab1(cfg, data, data_err)
    elif nav == NAV_LABELS[1]:
        render_tab2(cfg, data, data_err)
    elif nav == NAV_LABELS[2]:
        render_tab3(cfg, data, data_err,
                    price_lookup={row["symbol"]: row["price_usd"] for _, row in market_df.iterrows()} if not market_df.empty else {},
                    market_df=market_df)
    elif nav == NAV_NEWS:
        render_news_section(cfg)
    else:
        render_tab4(cfg, data, market_df=market_df)

    render_ai_fab()

    st.markdown(
        f"<div class='xs-foot'>XSpring Dealer Suite · Model v{MODEL_VERSION} · "
        f"Config {CONFIG_INFO['sha256'] or 'built-in defaults'} · "
        "Planning model เพื่อการวางแผนภายในเท่านั้น "
        "ไม่ใช่เครื่องมือรับรอง compliance</div>",
        unsafe_allow_html=True,
    )


def show_profile_setup_page(email: str):
    st.subheader("ตั้งค่าโปรไฟล์ของคุณ")
    st.caption("ระบบต้องการข้อมูลพื้นฐานก่อนเข้าใช้งาน XSpring Dealer Suite")

    default_name = getattr(st.user, "name", email.split("@")[0])
    name_input = st.text_input("ชื่อที่แสดง (Display Name)", value=default_name)
    
    uploaded_file = st.file_uploader(
        "อัปโหลดรูปโปรไฟล์ (ถ้ามี)",
        type=["png", "jpg", "jpeg"],
        help="รองรับไฟล์ PNG, JPG ขนาดไม่เกิน 2MB"
    )
    
    avatar_b64 = ""
    if uploaded_file is not None:
        if Image is not None:
            img = Image.open(uploaded_file)
            img.thumbnail((200, 200))
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            avatar_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            st.image(img, caption="ตัวอย่างรูปที่จะบันทึก", width=120)
        else:
            st.error("ไม่สามารถจัดการรูปได้ กรุณาติดตั้งไลบรารี Pillow (pip install pillow)")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("💾 บันทึกโปรไฟล์", type="primary", use_container_width=True):
            save_profile(email, name_input, avatar_b64)
            st.success("บันทึกโปรไฟล์สำเร็จ!")
            st.rerun()
    with col2:
        if st.button("ออกจากระบบ", use_container_width=True):
            st.logout()


def _allowed_email() -> str:
    try:
        v = st.secrets.get("allowed_email", "")
    except Exception:
        v = ""
    return str(v or os.environ.get("XSPRING_EMAIL", "")).strip().lower()

def require_login() -> bool:
    if is_guest_mode():
        st.session_state["current_role"] = GUEST_ROLE
        return True

    try:
        logged_in = bool(st.user.is_logged_in)
    except Exception:
        st.error("Streamlit เวอร์ชันนี้ไม่รองรับ st.login — ต้องเป็น 1.42 ขึ้นไป")
        st.stop()
        
    if not logged_in:
        st.markdown(THEME_CSS, unsafe_allow_html=True)
        st.markdown("""
        <style>
            .block-container { padding-top: 2.4rem !important; }
            [data-testid="stHorizontalBlock"] { align-items: center; }
            body { background: radial-gradient(ellipse at 20% 20%, rgba(14,203,129,0.05), transparent 55%); }

            /* ---- ฝั่งซ้าย: แบรนด์ ---- */
            .login-brand { padding: 12px 32px 12px 8px; }
            .login-icon {
                width: 68px; height: 68px; margin-bottom: 22px;
                display:flex; align-items:center; justify-content:center;
                font-size: 2.1rem; border-radius: 20px;
                background: linear-gradient(135deg, #0ecb81 0%, #0a9c63 100%);
                box-shadow: 0 0 0 1px rgba(14,203,129,0.25),
                            0 12px 34px rgba(14,203,129,0.30),
                            0 0 60px rgba(14,203,129,0.15);
            }
            .login-kicker {
                display:inline-block; font-size:.68rem; font-weight:700;
                letter-spacing:.14em; color:#0ecb81; text-transform:uppercase;
                background:rgba(14,203,129,.08); border:1px solid rgba(14,203,129,.25);
                border-radius:20px; padding:4px 12px; margin-bottom:14px;
            }
            .login-title {
                font-size: 2.1rem; font-weight: 800; color:#EAECEF;
                letter-spacing: -0.8px; line-height:1.15; margin-bottom: 12px;
            }
            .login-title span { color:#0ecb81; }
            .login-sub { color:#848e9c; font-size: 0.92rem; margin-bottom: 30px; line-height:1.6; max-width: 420px; }
            .login-feats { display:flex; flex-direction:column; gap:10px; max-width: 440px; }
            .login-feat {
                display:flex; align-items:center; gap:12px;
                background: rgba(255,255,255,0.025);
                border: 1px solid #23262d; border-radius: 12px;
                padding: 12px 16px; font-size: 0.85rem; color:#c4cad3;
                transition: border-color .15s ease, transform .15s ease;
            }
            .login-feat:hover { border-color:#0ecb81; transform: translateX(3px); }
            .login-feat .ico {
                width:30px; height:30px; min-width:30px; border-radius:9px;
                display:flex; align-items:center; justify-content:center;
                font-size:.95rem; background:rgba(14,203,129,.1);
            }

            /* ---- ฝั่งขวา: การ์ดล็อกอิน (ห่อ container จริง) ---- */
            .st-key-login_card_box {
                background: linear-gradient(165deg, #15171c 0%, #191c22 55%, #1d2129 100%);
                border: 1px solid #262a32; border-radius: 20px;
                padding: 34px 30px 26px; max-width: 420px;
                box-shadow: 0 0 0 1px rgba(255,255,255,0.02) inset,
                            0 24px 70px rgba(0,0,0,0.55);
                position: relative; overflow: hidden;
            }
            .st-key-login_card_box::before {
                content:""; position:absolute; top:-40%; right:-30%;
                width:220px; height:220px; border-radius:50%;
                background: radial-gradient(circle, rgba(14,203,129,0.16), transparent 70%);
                pointer-events:none;
            }
            .login-card-head { font-size:1rem; font-weight:700; color:#EAECEF; margin-bottom:4px; }
            .login-card-sub { font-size:.78rem; color:#5e6673; margin-bottom:20px; }
            .login-or {
                display:flex; align-items:center; gap:12px;
                color:#4a4f57; font-size:.72rem; margin:16px 0; text-transform:uppercase; letter-spacing:.08em;
            }
            .login-or::before, .login-or::after { content:""; flex:1; height:1px; background:#262a32; }
            .login-foot { text-align:center; margin-top: 20px; font-size: 0.68rem; color:#454a52; }

            .st-key-login_google button {
                width: 100% !important; height: 50px !important;
                background: #ffffff !important; color:#14161a !important;
                border: none !important; border-radius: 12px !important;
                font-weight: 700 !important; font-size: 0.95rem !important;
                box-shadow: 0 6px 18px rgba(255,255,255,0.12) !important;
                transition: transform .15s ease, box-shadow .15s ease !important;
            }
            .st-key-login_google button:hover {
                transform: translateY(-1px) !important;
                box-shadow: 0 10px 26px rgba(255,255,255,0.22) !important;
            }
            .st-key-login_guest button {
                width: 100% !important; height: 46px !important;
                background: transparent !important; color:#c4cad3 !important;
                border: 1px solid #2b3139 !important; border-radius: 12px !important;
                font-weight: 600 !important; font-size: .88rem !important;
                transition: border-color .15s ease, color .15s ease !important;
            }
            .st-key-login_guest button:hover {
                border-color:#0ecb81 !important; color:#0ecb81 !important;
            }

            @media (max-width: 900px) {
                .block-container { padding-top: 1.2rem !important; }
                .login-brand { padding: 12px 8px; }
                .st-key-login_card_box { padding: 24px 20px 20px; max-width: none; }
                .login-title { font-size: 1.7rem; }
                .login-sub { margin-bottom: 20px; }
            }
        </style>
        """, unsafe_allow_html=True)

        col_l, col_r = st.columns([1.15, 1], gap="large")

        with col_l:
            st.markdown(f"""
            <div class="login-brand">
              <div class="login-icon">♻️</div>
              <div class="login-kicker">Crypto Dealer OS</div>
              <div class="login-title">XSpring <span>Dealer Suite</span></div>
              <div class="login-sub">
                ระบบจำลองและวางแผนสภาพคล่องสำหรับ Dealer คริปโท —
                ล็อกอินเพื่อเข้าใช้งาน Backtest, Liquidity Planner และ Exchange Simulator
              </div>
              <div class="login-feats">
                <div class="login-feat"><span class="ico">📊</span> Backtest ย้อนหลังสูงสุด 5 ปี พร้อมวิเคราะห์ P&amp;L</div>
                <div class="login-feat"><span class="ico">🧮</span> วางแผนเงินกองทุนและสภาพคล่องตามเกณฑ์ ก.ล.ต.</div>
                <div class="login-feat"><span class="ico">🛒</span> จำลองหน้าเทรดจริงพร้อมระบบ Hedge อัตโนมัติ</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        with col_r:
            with st.container(key="login_card_box"):
                st.markdown(
                    '<div class="login-card-head">เข้าสู่ระบบ</div>'
                    '<div class="login-card-sub">เลือกวิธีเข้าใช้งานด้านล่าง</div>',
                    unsafe_allow_html=True,
                )
                st.button(
                    "🔐  Continue with Google",
                    key="login_google",
                    on_click=st.login,
                    use_container_width=True,
                )
                st.markdown('<div class="login-or">หรือ</div>', unsafe_allow_html=True)
                st.button(
                    "👤 ทดลองใช้แบบ Guest (ไม่ต้องล็อกอิน)",
                    key="login_guest",
                    on_click=_start_guest_session,
                    use_container_width=True,
                )
                st.caption("โหมด Guest: ข้อมูลทั้งหมดจะหายทันทีเมื่อออกจากระบบ และไม่ถูกบันทึกไว้ที่ไหน")
                st.markdown(
                    f'<div class="login-foot">XSpring Dealer Suite · Model v{MODEL_VERSION}</div>',
                    unsafe_allow_html=True,
                )

        st.stop()

    allowed = _allowed_email()
    email = str(getattr(st.user, "email", "") or "").strip().lower()
    
    if not allowed:
        st.error("ยังไม่ได้ตั้ง allowed_email ใน secrets.toml — ระบบจึงปิดไว้ก่อน")
        if st.button("ออกจากระบบ", key="logout_err1"):
            st.logout()
        st.stop()
        
    allowed_list = [a.strip() for a in allowed.split(",")]
    if email not in allowed_list and allowed != "*":
        st.error(f"บัญชี {email} ไม่ได้รับอนุญาตให้ใช้งาน")
        if st.button("ออกจากระบบ", key="logout_err2"):
            st.logout()
        st.stop()

    # ---------- Profile Setup Flow ----------
    profiles = load_profiles()
    if email not in profiles:
        show_profile_setup_page(email)
        st.stop() # หยุดกระบวนการโหลดแอปหลักจนกว่าจะสร้างโปรไฟล์เสร็จ
    # ----------------------------------------
    
    return True

def main() -> None:
    st.set_page_config(
        page_title="XSpring Dealer Suite",
        page_icon="\u267b\ufe0f",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    if not require_login():
        st.stop()
    try:
        _main_body()
    finally:
        # finally ทำงานแม้มี st.rerun() ทำให้ทุกออเดอร์ถูกเซฟเสมอ
        try:
            save_sim_state(st.session_state.get("sim"))
        except Exception:
            pass

if __name__ == "__main__":
    if not HAS_UI:
        raise SystemExit("ต้องติดตั้ง UI stack ก่อน: pip install streamlit plotly yfinance pillow")
    main()
