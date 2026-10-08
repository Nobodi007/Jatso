from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
from threading import RLock
from collections import defaultdict, deque
from functools import lru_cache
from typing import Optional
import hmac
import hashlib
import time
import importlib.util
import os
import math
import json
import urllib.parse
import urllib.request

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

import pandas as pd


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Dealer Suite API",
    version="1.4.0",
)


# =========================================================
# CORS
# =========================================================
# ใช้ allow_origins=["*"] เพราะ frontend production อาจมี origin
# ที่เปลี่ยนได้ เช่น deployment/preview URL
# ไม่เปิด credentials เพราะ API นี้ไม่ได้ใช้ cookie authentication
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# GU.PY
# =========================================================

GU_PATH = Path(__file__).resolve().parent.parent / "gu.py"

ORDER_LOCK = RLock()
# Optional idempotency protection for order retries/double-clicks.
_IDEMPOTENCY_LOCK = RLock()
_IDEMPOTENCY_RESULTS = {}
_IDEMPOTENCY_TTL_SECONDS = 10 * 60

def _cleanup_idempotency_cache(now: float) -> None:
    expired = [
        key for key, item in _IDEMPOTENCY_RESULTS.items()
        if now - item["created_at"] >= _IDEMPOTENCY_TTL_SECONDS
    ]
    for key in expired:
        _IDEMPOTENCY_RESULTS.pop(key, None)

def _get_idempotent_result(actor: str, key: str, fingerprint: str = ""):
    if not key:
        return None
    now = time.monotonic()
    cache_key = (str(actor), str(key))
    with _IDEMPOTENCY_LOCK:
        _cleanup_idempotency_cache(now)
        item = _IDEMPOTENCY_RESULTS.get(cache_key)
        if item and item.get("fingerprint") and fingerprint and item["fingerprint"] != fingerprint:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key ถูกใช้กับคำสั่งคนละรายการ",
            )
        return item["result"] if item else None

def _store_idempotent_result(actor: str, key: str, result: dict, fingerprint: str = "") -> None:
    if not key:
        return
    now = time.monotonic()
    with _IDEMPOTENCY_LOCK:
        _cleanup_idempotency_cache(now)
        _IDEMPOTENCY_RESULTS[(str(actor), str(key))] = {
            "created_at": now,
            "fingerprint": fingerprint,
            "result": result,
        }



# Lightweight in-memory API rate limiter.
_RATE_LIMIT_LOCK = RLock()
_RATE_LIMIT_BUCKETS = defaultdict(deque)
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_GENERAL = 120
_RATE_LIMIT_ORDER = 30


def _rate_limit_key(request: Request, x_api_key: str) -> str:
    host = request.client.host if request.client else "unknown"
    fingerprint = hashlib.sha256(str(x_api_key).encode("utf-8")).hexdigest()[:16]
    return f"{host}:{fingerprint}"


def _internal_server_error(message: str, exc: Exception, status_code: int = 500) -> HTTPException:
    """Log technical details server-side without exposing internals to clients."""
    print(f"[api] {message}: {type(exc).__name__}: {exc}")
    return HTTPException(status_code=status_code, detail=message)


def _idempotency_fingerprint(asset: str, side: str, amount_thb: float) -> str:
    raw = f"{str(asset).upper().strip()}|{str(side).lower().strip()}|{float(amount_thb):.12g}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _idempotency_key_hash(key: str) -> str:
    return hashlib.sha256(str(key).encode("utf-8")).hexdigest()


def _check_rate_limit(request: Request, x_api_key: str) -> None:
    limit = _RATE_LIMIT_ORDER if request.url.path == "/api/order" else _RATE_LIMIT_GENERAL
    now = time.monotonic()
    key = _rate_limit_key(request, x_api_key)

    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS[key]
        cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = max(1, int(_RATE_LIMIT_WINDOW_SECONDS - (now - bucket[0])))
            raise HTTPException(
                status_code=429,
                detail={
                    "message": "คำขอมากเกินไป กรุณารอสักครู่แล้วลองใหม่",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)


@lru_cache(maxsize=1)
def load_gu():
    """
    Load the existing gu.py engine (cached, โหลดครั้งเดียว).

    IMPORTANT:
    Do not create a replacement engine or fallback state.
    """
    if not GU_PATH.exists():
        raise FileNotFoundError(f"ไม่พบ gu.py ที่ {GU_PATH}")

    spec = importlib.util.spec_from_file_location("xspring_gu", GU_PATH)

    if spec is None or spec.loader is None:
        raise ImportError("โหลด gu.py ไม่สำเร็จ")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


# =========================================================
# AUTH
# =========================================================

def require_api_key(
    request: Request,
    x_api_key: str = Header(default=""),
):
    expected = os.environ.get("DEALER_API_KEY", "").strip()

    if not expected or not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    _check_rate_limit(request, x_api_key)


# =========================================================
# GOOGLE LOGIN / SESSION
# =========================================================
# Flow: Frontend ส่ง Google ID token มาที่ POST /api/auth/google
#       -> verify กับ Google -> เช็ค email ใน user_profiles (allowlist)
#       -> ออก session JWT ของระบบเอง (HS256)
# endpoint ที่แตะข้อมูลบัญชี (portfolio/orders/order) บังคับ Bearer token
# และใช้ email ใน token เป็น actor เท่านั้น
# =========================================================

AUTH_JWT_TTL_SECONDS = 12 * 3600


class GoogleLoginRequest(BaseModel):
    credential: str = Field(..., min_length=10, max_length=4096)


def _jwt_secret() -> str:
    secret = os.environ.get("AUTH_JWT_SECRET", "").strip()

    if len(secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="ยังไม่ได้ตั้ง AUTH_JWT_SECRET (อย่างน้อย 32 ตัวอักษร)",
        )

    return secret


def require_user(authorization: str = Header(default="")) -> str:
    """Strict: ต้องมี Bearer token ที่ถูกต้อง คืนค่า email ของผู้ใช้"""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="กรุณาเข้าสู่ระบบ",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:].strip()

    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Session หมดอายุหรือไม่ถูกต้อง",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = str(payload.get("sub") or "").strip()

    if not email:
        raise HTTPException(status_code=401, detail="Session ไม่ถูกต้อง")

    return email


@app.post("/api/auth/google")
def auth_google(body: GoogleLoginRequest, request: Request):
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()

    if not client_id:
        raise HTTPException(status_code=503, detail="ยังไม่ได้ตั้ง GOOGLE_CLIENT_ID")

    # กัน brute-force / spam ที่ endpoint นี้ (ไม่มี API key ให้ใช้เป็น key)
    _check_rate_limit(request, "auth-google")

    try:
        info = google_id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            client_id,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Google token ไม่ถูกต้อง")

    if not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="อีเมลยังไม่ได้ยืนยันกับ Google")

    # เก็บ email ตามที่ Google ส่งมา (ตรงกับ st.user.email ที่แอป Streamlit เก่าใช้เป็น actor
    # ใน sim_state) ส่วนการเทียบสิทธิ์ใช้ตัวพิมพ์เล็ก
    email = str(info.get("email") or "").strip()
    email_key = email.lower()

    if not email:
        raise HTTPException(status_code=401, detail="ไม่พบอีเมลใน Google token")

    # Allowlist: ใช้กติกาเดียวกับ gu.py (require_login)
    # XSPRING_EMAIL = อีเมลคั่นด้วย comma หรือ "*" ; ไม่ตั้ง = ปิดระบบ
    allowed_raw = os.environ.get("XSPRING_EMAIL", "").strip().lower()

    if not allowed_raw:
        raise HTTPException(
            status_code=503,
            detail="ยังไม่ได้ตั้ง XSPRING_EMAIL — ระบบจึงปิดไว้ก่อน",
        )

    allowed_list = {a.strip() for a in allowed_raw.split(",") if a.strip()}

    if allowed_raw != "*" and email_key not in allowed_list:
        raise HTTPException(
            status_code=403,
            detail="อีเมลนี้ยังไม่ได้รับอนุญาตให้ใช้งาน",
        )

    # Role: ใช้จาก user_profiles ถ้ามี ไม่งั้นเหมือน default_role_for_new_user ใน gu.py
    # (อยู่ใน XSPRING_ADMIN_EMAILS = admin นอกนั้น viewer)
    role = None

    try:
        gu = load_gu()
        sb = gu._get_supabase()

        if sb is not None:
            res = (
                sb.table("user_profiles")
                .select("email,role")
                .eq("email", email_key)
                .limit(1)
                .execute()
            )

            if res.data:
                role = str(res.data[0].get("role") or "").strip().lower()
    except Exception:
        role = None  # โหลด role ไม่ได้ -> ตกไปใช้ค่า default (สิทธิ์ต่ำสุด)

    if role not in {"viewer", "trader", "admin"}:
        admin_emails = {
            e.strip()
            for e in os.environ.get("XSPRING_ADMIN_EMAILS", "").lower().split(",")
            if e.strip()
        }
        role = "admin" if email_key in admin_emails else "viewer"

    token = jwt.encode(
        {
            "sub": email,
            "role": role,
            "iat": int(time.time()),
            "exp": int(time.time()) + AUTH_JWT_TTL_SECONDS,
        },
        _jwt_secret(),
        algorithm="HS256",
    )

    return {
        "token": token,
        "user": {
            "email": email,
            "name": info.get("name"),
            "picture": info.get("picture"),
            "role": role,
        },
    }


# =========================================================
# REQUEST MODEL
# =========================================================

class OrderRequest(BaseModel):
    # Validate at the API boundary before the trading engine is touched.
    asset: str = Field(..., min_length=1, max_length=20)
    side: str = Field(..., min_length=1, max_length=8)
    amount_thb: float = Field(..., gt=0, le=1_000_000_000_000)
    # รับไว้เพื่อไม่ให้ frontend เดิมพัง แต่ server ไม่ใช้ค่านี้
    quote_thb: Optional[float] = Field(default=None, ge=0, le=1_000_000_000_000)


# =========================================================
# SAFE FLOAT
# =========================================================

def _safe_float(value, default=0.0):
    try:
        value = float(value)

        if math.isfinite(value):
            return value

        return default

    except (TypeError, ValueError):
        return default


# =========================================================
# ACTOR
# =========================================================

def _actor(user_email: str):
    """
    Actor = email ของผู้ใช้ที่ล็อกอิน (มาจาก session token ที่ verify แล้ว)

    ไม่ fallback ไป XSPRING_USER อีกต่อไป เพื่อไม่ให้มีทางเข้าบัญชีโดยไม่ล็อกอิน
    """
    actor = str(user_email or "").strip()

    if not actor:
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบ")

    return actor


def _sync_gu_actor(gu, actor: str) -> None:
    """Synchronize both actor env vars before gu.py reads persistent state."""
    actor = str(actor or "").strip()

    if not actor:
        raise HTTPException(
            status_code=503,
            detail="ไม่พบ actor สำหรับโหลด Portfolio",
        )

    os.environ["XSPRING_USER"] = actor
    os.environ["XSPRING_REPORT_ACTOR"] = actor


# =========================================================
# ROLE
# =========================================================

def _set_api_role(gu, actor: str):
    import streamlit as st

    role = None

    try:
        sb = gu._get_supabase()

        if sb is not None:
            res = (
                sb.table("user_profiles")
                .select("email,role")
                .eq("email", actor)
                .limit(1)
                .execute()
            )

            if res.data:
                role = str(res.data[0].get("role") or "").strip().lower()

    except Exception:
        role = None

        # viewer เก่า / ค่าว่าง / ค่าแปลก ทั้งหมด -> trader
    if role not in {"trader", "admin"}:
        role = str(
            os.environ.get("XSPRING_API_ROLE", "trader") or ""
        ).strip().lower()

    if role not in {"trader", "admin"}:
        role = "trader"

    st.session_state["guest_mode"] = False
    st.session_state["current_role"] = role

    return role


# =========================================================
# REMOTE CONFIG
# =========================================================

def _remote_config(gu, actor: str) -> dict:
    try:
        sb = gu._get_supabase()

        if sb is None:
            return {}

        res = (
            sb.table("dealer_remote_config")
            .select("config,updated_at")
            .eq("actor", actor.strip().lower())
            .limit(1)
            .execute()
        )

        if not res.data:
            return {}

        cfg = res.data[0].get("config") or {}

        return cfg if isinstance(cfg, dict) else {}

    except Exception:
        return {}


# =========================================================
# API CONFIG
# =========================================================

def _api_cfg(gu, asset: str, actor: str) -> dict:
    ui = getattr(gu, "UI_DEFAULTS", {}) or {}
    fee_map = getattr(gu, "GLOBAL_EXCHANGE_FEE_PRESET", {})
    exchanges = list(fee_map.keys())

    exchange = exchanges[0] if exchanges else "Binance"

    remote = _remote_config(gu, actor)

    remote_asset = str(remote.get("asset") or asset).upper()

    if remote_asset in getattr(gu, "SUPPORTED_ASSETS", []):
        asset = remote_asset

    exchange = str(remote.get("exchange") or exchange)

    if exchange not in fee_map:
        exchange = exchanges[0] if exchanges else exchange

    maker_ratio = _safe_float(remote.get("maker_ratio"), 0.0) / 100.0

    taker_pct = _safe_float(remote.get("hedge_taker"), fee_map.get(exchange, 0.0))

    maker_pct = _safe_float(
        remote.get("hedge_maker"),
        gu.default_maker_fee_pct(exchange),
    )

    hedge_fee = gu.blend_hedge_fee(
        taker_pct / 100.0,
        maker_pct / 100.0,
        maker_ratio,
    )

    monthly_volume = _safe_float(remote.get("monthly_volume"), 80_000_000.0)

    settlement_days = int(_safe_float(remote.get("lag"), 1))

    confidence = _safe_float(remote.get("confidence"), 99.0)

    z_map = getattr(gu, "Z_SCORE_MAP", {})
    z_alpha = z_map.get(confidence)

    if z_alpha is None:
        z_alpha = z_map.get(99, 2.576)

    is_custodian = bool(remote.get("custodian", True))

    fixed_min_nc = (
        getattr(gu, "NC_FIXED_MIN_CUSTODIAN_THB", 25_000_000.0)
        if is_custodian
        else getattr(gu, "NC_FIXED_MIN_NON_CUSTODIAN_THB", 5_000_000.0)
    )

    cex_margin_asset = str(remote.get("margin_asset", "Stablecoin"))

    if cex_margin_asset not in {"Stablecoin", "เหรียญเดียวกับที่เทรด"}:
        cex_margin_asset = "Stablecoin"

    hot_wallet_pct = _safe_float(remote.get("hot_wallet"), 30.0) / 100.0
    cold_domestic_pct = _safe_float(remote.get("cold_domestic"), 80.0) / 100.0
    cold_foreign_rate = _safe_float(remote.get("cold_foreign"), 1.5) / 100.0

    cfg = {
        "asset": asset,
        "global_exchange": exchange,
        "trade_vol": _safe_float(remote.get("trade_vol"), 100_000.0),
        "dealer_spread": _safe_float(
            remote.get("spread", ui.get("dealer_spread_pct", 0.5))
        ) / 100.0,
        "hedge_fee": hedge_fee,
        "hedge_fee_taker": taker_pct / 100.0,
        "hedge_fee_maker": maker_pct / 100.0,
        "maker_ratio": maker_ratio,
        "market_depth_usd": _safe_float(remote.get("depth"), 0.0),
        "impact_penalty": _safe_float(
            remote.get("impact_penalty", ui.get("impact_penalty_pct", 0.5))
        ) / 100.0,
        "use_fx_proxy": False,
        "fx_limit_max": _safe_float(
            remote.get("fx_limit", ui.get("fx_limit_usd", 5_000_000.0))
        ),
        "local_premium": _safe_float(
            remote.get("premium", ui.get("local_premium_pct", 0.1))
        ) / 100.0,
        "include_trading_fee_revenue": True,
        "withdrawal_fee_markup_pct": 0.0,
        "settlements_per_day": 1,
        "bank_type": "SCB",
        "use_ktb_fx": True,
        "ktb_fx_spread_bps": 15.0,
        "ktb_wd_fee_thb": 15.0,
        "peg_target": 1.0,
        "depeg_capture_pct": 0.80,
        "carry_apy": 0.04,
        "slippage_sensitivity": (
            0.10 if asset not in getattr(gu, "STABLECOINS", set()) else 0.0
        ),
        "monthly_volume_thb": monthly_volume,
        "daily_volume_thb": monthly_volume / 30.0,
        "net_bias_pct": _safe_float(remote.get("net_bias", 15.0)) / 100.0,
        "flow_cv_pct": _safe_float(remote.get("flow_cv", 50.0)) / 100.0,
        "settlement_days": settlement_days,
        "confidence": confidence,
        "z_alpha": z_alpha,
        "total_capital_thb": _safe_float(remote.get("capital", 150_000_000.0)),
        "cex_margin_thb": _safe_float(remote.get("margin", 30_000_000.0)),
        "liab_thb": _safe_float(remote.get("liab", 100_000_000.0)),
        "cex_margin_asset": cex_margin_asset,
        "cex_counterparty_haircut": _safe_float(
            remote.get("cp_haircut", 2.0)
        ) / 100.0,
        "is_custodian": is_custodian,
        "fixed_min_nc": fixed_min_nc,
        "trading_risk_rate": _safe_float(
            remote.get("trading_risk", 2.0)
        ) / 100.0,
        "cold_foreign_rate": cold_foreign_rate,
        "hot_wallet_pct": hot_wallet_pct,
        "cold_domestic_split_pct": cold_domestic_pct,
        "hedge_trigger_pct": _safe_float(
            remote.get("hedge_trigger", 0.0)
        ) / 100.0,
        "hedge_vol_block_pct": _safe_float(
            remote.get("hedge_vol_block", 0.0)
        ) / 100.0,
    }

    cfg["custody_rate_blended"] = gu.blended_custody_rate(
        cfg["hot_wallet_pct"],
        cfg["cold_domestic_split_pct"],
        cfg["cold_foreign_rate"],
    )

    cfg["hot_wallet_cap_breach"] = (
        cfg["liab_thb"] < getattr(gu, "HOT_WALLET_CAP_LIAB_THRESHOLD", 1_000_000_000.0)
        and cfg["hot_wallet_pct"] > getattr(gu, "HOT_WALLET_CAP", 0.50)
    )

    return cfg


# =========================================================
# MARKET DATA
# =========================================================

def _load_market_frame(gu, asset: str):
    end = pd.Timestamp.now().normalize()
    start = end - pd.Timedelta(days=365)

    data, err = gu.fetch_price_data(
        asset,
        start,
        end,
        use_fx_proxy=False,
    )

    if data is None or data.empty:
        raise HTTPException(
            status_code=503,
            detail=(
                f"โหลดข้อมูลตลาดสำหรับ {asset} "
                f"ไม่สำเร็จ: {err or 'ไม่มีข้อมูล'}"
            ),
        )

    return data


# =========================================================
# LOAD EXISTING PORTFOLIO
# =========================================================

def _load_existing_sim(gu):
    """Load the existing persisted portfolio without creating a new one."""
    sim = gu.load_sim_state()

    # SAFETY: never create/fallback/overwrite a portfolio here.
    if not isinstance(sim, dict):
        try:
            session_state = getattr(gu.st, "session_state", {})
        except Exception:
            session_state = {}

        def _diag(name: str) -> str:
            try:
                return str(session_state.get(name, "") or "")
            except Exception:
                return ""

        diagnostic = {
            "sim_state_load_error": _diag("sim_state_load_error"),
            "sim_state_rest_error": _diag("sim_state_rest_error"),
            "sim_state_source": _diag("sim_state_source"),
            "sim_state_actor": _diag("sim_state_actor"),
            "x_spring_user": os.environ.get("XSPRING_USER", ""),
            "x_spring_report_actor": os.environ.get("XSPRING_REPORT_ACTOR", ""),
            "gu_file": str(getattr(gu, "__file__", "")),
            "supabase_url_configured": bool(os.environ.get("SUPABASE_URL", "").strip()),
            "supabase_service_role_configured": bool(
                os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            ),
        }

        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "ไม่สามารถโหลด Portfolio เดิมจาก Supabase ได้ — "
                    "ไม่สร้างพอร์ตใหม่เพื่อป้องกันข้อมูลเดิมถูกเขียนทับ"
                ),
                "diagnostic": diagnostic,
            },
        )

    return sim


# =========================================================
# PORTFOLIO RESPONSE
# =========================================================

def _fetch_bitkub_ticker_prices(assets: set[str]) -> dict[str, float]:
    """Fetch current THB prices directly from Bitkub public ticker.

    Prefer one all-market request so a temporary per-symbol response format
    cannot silently turn a real holding into price=0 (which would look like
    a -100% portfolio). Fall back to per-symbol requests only when needed.
    """
    requested = {
        str(a).upper().strip()
        for a in assets
        if str(a).upper().strip() and str(a).upper().strip() != "THB"
    }
    prices: dict[str, float] = {}
    url = "https://api.bitkub.com/api/market/ticker"

    def _parse_payload(payload):
        if not isinstance(payload, dict):
            return

        for key, row in payload.items():
            if not isinstance(row, dict):
                continue

            symbol = str(key).upper().strip()
            if symbol.startswith("THB_"):
                asset = symbol[4:]
            elif symbol.endswith("_THB"):
                asset = symbol[:-4]
            else:
                continue

            if asset not in requested:
                continue

            value = _safe_float(row.get("last"))
            if value > 0:
                prices[asset] = value

    # Primary path: Bitkub returns the public ticker map in one request.
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Dealer-Suite/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        _parse_payload(payload)
    except Exception as exc:
        print(f"[portfolio] Bitkub all-ticker request failed: {exc}")

    # Fallback: request any still-missing asset explicitly.
    for asset in sorted(requested - set(prices)):
        try:
            params = urllib.parse.urlencode({"sym": f"THB_{asset}"})
            request = urllib.request.Request(
                f"{url}?{params}",
                headers={
                    "User-Agent": "Dealer-Suite/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))

            row = payload.get(f"THB_{asset}") or payload.get(f"{asset}_THB")
            if isinstance(row, dict):
                value = _safe_float(row.get("last"))
                if value > 0:
                    prices[asset] = value
        except Exception as exc:
            print(f"[portfolio] Bitkub price failed for {asset}: {exc}")

    return prices



def _order_raw_time(order: dict):
    """Pick the best timestamp source of an order record.

    Priority: ISO `timestamp` (has timezone) -> `time` -> `วันที่`+`เวลา`
    (date AND clock together) -> `เวลา` -> `วันที่`.
    A clock-only `เวลา` (HH:MM:SS) must never be parsed alone: pandas would
    attach *today's* date, which shifts old orders to the wrong day.
    """
    ts = order.get("timestamp") or order.get("time")
    if ts:
        return ts
    d = str(order.get("วันที่") or "").strip()
    t = str(order.get("เวลา") or "").strip()
    if d and t:
        if "T" in t or len(t) > 8:  # already a full datetime
            return t
        return f"{d} {t}"
    return t or d or ""


SIDE_TH_TO_EN = {"ซื้อ": "BUY", "ขาย": "SELL"}


def _normalize_side(value) -> str:
    raw = str(value or "").strip()
    return SIDE_TH_TO_EN.get(raw, raw.upper())


def _recompute_realized_pnl_from_orders(sim: dict) -> float:
    """Recompute realized P&L from the immutable filled-order history.

    Do not trust a stale/corrupted realized_pnl_thb field in an old portfolio
    ledger. BUY/SELL order history is the source of truth for execution P&L.
    """
    orders = sim.get("orders", []) if isinstance(sim, dict) else []
    if not isinstance(orders, list):
        return 0.0

    rows = []
    for idx, order in enumerate(orders):
        if not isinstance(order, dict):
            continue

        status = str(
            order.get("สถานะ")
            or order.get("status")
            or "Filled"
        ).strip().lower()
        if status not in {"filled", "fill", "completed", "executed", "success", "successful"}:
            continue

        asset = str(
            order.get("เหรียญ")
            or order.get("asset")
            or order.get("symbol")
            or ""
        ).strip().upper()
        side = str(
            order.get("ฝั่ง")
            or order.get("side")
            or ""
        ).strip().upper()

        if side in {"ซื้อ", "BUY"}:
            side = "BUY"
        elif side in {"ขาย", "SELL"}:
            side = "SELL"
        else:
            continue

        qty = _safe_float(
            order.get("เหรียญที่ส่งมอบ")
            if order.get("เหรียญที่ส่งมอบ") is not None
            else order.get("quantity")
        )
        gross = _safe_float(
            order.get("มูลค่า (บาท)")
            if order.get("มูลค่า (บาท)") is not None
            else order.get("amount_thb")
        )
        price = _safe_float(
            order.get("ราคาที่ลูกค้าได้")
            if order.get("ราคาที่ลูกค้าได้") is not None
            else order.get("price_thb")
        )

        if not asset or qty <= 0 or gross <= 0 or price <= 0:
            continue

        timestamp = _order_raw_time(order)
        try:
            ts = pd.to_datetime(timestamp, errors="coerce", utc=True)
            if pd.isna(ts):
                ts = pd.Timestamp("1970-01-01", tz="UTC")
        except Exception:
            ts = pd.Timestamp("1970-01-01", tz="UTC")

        rows.append((ts, idx, asset, side, qty, gross, price))

    rows.sort(key=lambda x: (x[0], x[1]))

    qty_map: dict[str, float] = {}
    cost_map: dict[str, float] = {}
    realized = 0.0

    for _, _, asset, side, qty, gross, price in rows:
        if side == "BUY":
            old_qty = qty_map.get(asset, 0.0)
            old_cost = cost_map.get(asset, 0.0)
            new_qty = old_qty + qty
            cost_map[asset] = (
                (old_qty * old_cost + gross) / new_qty
                if new_qty > 0
                else 0.0
            )
            qty_map[asset] = new_qty
        else:
            old_qty = qty_map.get(asset, 0.0)
            avg_cost = cost_map.get(asset, 0.0)
            sold_qty = min(qty, old_qty) if old_qty > 0 else 0.0

            if sold_qty > 0:
                realized += gross * (sold_qty / qty) - sold_qty * avg_cost
                qty_map[asset] = max(0.0, old_qty - sold_qty)
                if qty_map[asset] <= 1e-12:
                    qty_map[asset] = 0.0
                    cost_map[asset] = 0.0

    return realized


def _portfolio_response(gu, sim, px_row=None):
    """Build Portfolio using direct Bitkub THB prices; never depend on USD/THB."""
    held_assets: set[str] = set()
    selected_asset = str(sim.get("asset") or "").upper().strip()
    if selected_asset and selected_asset != "THB":
        held_assets.add(selected_asset)

    for source in (sim.get("customer_coins"), sim.get("inv_coins")):
        if isinstance(source, dict):
            for asset, qty in source.items():
                if _safe_float(qty) > 1e-12:
                    name = str(asset).upper().strip()
                    if name and name != "THB":
                        held_assets.add(name)

    for tx in sim.get("portfolio_ledger", []) or []:
        if not isinstance(tx, dict):
            continue
        asset = str(tx.get("asset") or "").upper().strip()
        if asset and asset != "THB":
            held_assets.add(asset)

    price_map = _fetch_bitkub_ticker_prices(held_assets)

    # Never silently value a real holding at zero. That would make the UI
    # report a fake -100% P/L when Bitkub market data is temporarily unavailable.
    missing_prices = sorted(asset for asset in held_assets if asset not in price_map)
    if missing_prices:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "โหลดราคาพอร์ตจาก Bitkub ไม่ครบ — ไม่แสดงค่า -100% ปลอม",
                "missing_assets": missing_prices,
                "source": "Bitkub Public Ticker",
            },
        )

    snap = gu.portfolio_snapshot(sim, price_map)

    # Recalculate realized P&L from the actual filled-order history.
    # This repairs legacy ledger rows that can carry an incorrect
    # realized_pnl_thb (which was producing the spurious -10M figure).
    realized_pnl = _recompute_realized_pnl_from_orders(sim)
    unrealized_pnl = _safe_float(snap.get("unrealized_pnl_thb"), 0.0)
    total_pnl = realized_pnl + unrealized_pnl
    invested_cost = _safe_float(snap.get("invested_cost_thb"), 0.0)
    pnl_pct = (total_pnl / invested_cost * 100.0) if invested_cost > 0 else 0.0

    return {
        "cash_thb": snap["cash_thb"],
        "market_value_thb": snap["market_value_thb"],
        "total_value_thb": snap["total_value_thb"],
        "realized_pnl_thb": realized_pnl,
        "unrealized_pnl_thb": unrealized_pnl,
        "total_pnl_thb": total_pnl,
        "pnl_pct": pnl_pct,
        "fees_thb": snap["fees_thb"],
        "holdings": snap["rows"],
    }


# ORDERBOOK — BITKUB PUBLIC MARKET DATA
# =========================================================

BITKUB_SYMBOL_MAP = {
    "BTC": "BTC_THB",
    "ETH": "ETH_THB",
    "SOL": "SOL_THB",
    "DOGE": "DOGE_THB",
    "ADA": "ADA_THB",
    "HBAR": "HBAR_THB",
    "LINK": "LINK_THB",
    "XLM": "XLM_THB",
    "XRP": "XRP_THB",
}


def _fetch_bitkub_orderbook(symbol: str, limit: int = 20):
    """Fetch a THB orderbook snapshot from Bitkub's public V3 API."""
    safe_limit = max(1, min(int(limit), 100))
    params = urllib.parse.urlencode({
        "sym": symbol,
        "lmt": safe_limit,
    })

    url = f"https://api.bitkub.com/api/v3/market/depth?{params}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Dealer-Suite/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read().decode("utf-8")

    payload = json.loads(raw)

    if not isinstance(payload, dict):
        raise ValueError("Bitkub orderbook response ไม่ถูกต้อง")

    if _safe_float(payload.get("error"), 0.0) != 0.0:
        raise ValueError(
            f"Bitkub orderbook error={payload.get('error')}"
        )

    result = payload.get("result") or {}
    bids = result.get("bids") or []
    asks = result.get("asks") or []

    if not bids and not asks:
        raise ValueError("Bitkub ไม่มีข้อมูล bids/asks")

    return bids, asks


@app.get("/api/orderbook", dependencies=[Depends(require_api_key)])
def orderbook(
    asset: str = "BTC",
    limit: int = 20,
):
    try:
        asset = str(asset or "BTC").strip().upper()

        if asset not in BITKUB_SYMBOL_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"ไม่รองรับ Orderbook สำหรับ {asset}",
            )

        symbol = BITKUB_SYMBOL_MAP[asset]

        try:
            safe_limit = max(1, min(int(limit), 100))
        except (TypeError, ValueError):
            safe_limit = 20

        bids_raw, asks_raw = _fetch_bitkub_orderbook(
            symbol,
            safe_limit,
        )

        # Bitkub depth already returns THB prices, so there is no
        # Binance/USDT/USDTHB conversion in the Orderbook path.
        def normalize_level(row):
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                return None

            price_thb = _safe_float(row[0])
            quantity = _safe_float(row[1])

            if price_thb <= 0 or quantity <= 0:
                return None

            return {
                "price_thb": price_thb,
                "quantity": quantity,
                "total_thb": price_thb * quantity,
            }

        bids = [
            level
            for row in bids_raw
            if (level := normalize_level(row)) is not None
        ][:safe_limit]

        asks = [
            level
            for row in asks_raw
            if (level := normalize_level(row)) is not None
        ][:safe_limit]

        # Bitkub's API returns bids/asks as price + size. Keep the
        # exchange ordering, but calculate the best levels explicitly.
        best_bid = max(
            (level["price_thb"] for level in bids),
            default=0.0,
        )
        best_ask = min(
            (level["price_thb"] for level in asks),
            default=0.0,
        )

        spread_thb = (
            best_ask - best_bid
            if best_bid > 0 and best_ask > 0
            else 0.0
        )

        spread_pct = (
            spread_thb / best_bid * 100
            if best_bid > 0
            else 0.0
        )

        mid_price_thb = (
            (best_bid + best_ask) / 2
            if best_bid > 0 and best_ask > 0
            else 0.0
        )

        return {
            "status": "ok",
            "asset": asset,
            "symbol": symbol,
            "quote": "THB",
            "source": "Bitkub",
            "timestamp": pd.Timestamp.now(
                tz="Asia/Bangkok"
            ).isoformat(),
            "best_bid_thb": best_bid,
            "best_ask_thb": best_ask,
            "mid_price_thb": mid_price_thb,
            "spread_thb": spread_thb,
            "spread_pct": spread_pct,
            "bids": bids,
            "asks": asks,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise _internal_server_error(
            "โหลด Bitkub Orderbook ไม่สำเร็จ",
            e,
            status_code=503,
        )
# =========================================================
# MARKETS (Market Hub) — proxy Bitkub ticker ให้ Frontend ไม่ติด CORS
# =========================================================

MARKET_HUB_ASSETS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "HBAR", "LINK", "XLM"]

_MARKETS_CACHE_LOCK = RLock()
_MARKETS_CACHE = {"ts": 0.0, "rows": []}
_MARKETS_CACHE_TTL_SECONDS = 5


def _fetch_bitkub_markets() -> list[dict]:
    request = urllib.request.Request(
        "https://api.bitkub.com/api/market/ticker",
        headers={
            "User-Agent": "Dealer-Suite/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("Bitkub ticker response ไม่ถูกต้อง")

    rows = []
    for asset in MARKET_HUB_ASSETS:
        row = payload.get(f"THB_{asset}") or payload.get(f"{asset}_THB")
        if not isinstance(row, dict):
            continue

        last = _safe_float(row.get("last"))
        if last <= 0:
            continue

        rows.append({
            "asset": asset,
            "last_thb": last,
            "change_pct": _safe_float(row.get("percentChange")),
            "high_24h_thb": _safe_float(row.get("high24hr")),
            "low_24h_thb": _safe_float(row.get("low24hr")),
            "volume_base": _safe_float(row.get("baseVolume")),
            "bid_thb": _safe_float(row.get("highestBid")),
            "ask_thb": _safe_float(row.get("lowestAsk")),
        })

    if not rows:
        raise ValueError("ไม่พบข้อมูลตลาดจาก Bitkub")

    return rows


@app.get("/api/markets", dependencies=[Depends(require_api_key)])
def markets():
    now = time.monotonic()

    with _MARKETS_CACHE_LOCK:
        if _MARKETS_CACHE["rows"] and now - _MARKETS_CACHE["ts"] < _MARKETS_CACHE_TTL_SECONDS:
            return {"status": "ok", "markets": _MARKETS_CACHE["rows"]}

    try:
        rows = _fetch_bitkub_markets()
    except Exception as exc:
        # ถ้า Bitkub ล่มชั่วคราว ให้ใช้ข้อมูลล่าสุดที่แคชไว้ (ถ้ามี)
        with _MARKETS_CACHE_LOCK:
            if _MARKETS_CACHE["rows"]:
                return {"status": "ok", "markets": _MARKETS_CACHE["rows"]}
        raise _internal_server_error("โหลดข้อมูลตลาดไม่สำเร็จ", exc, 502)

    with _MARKETS_CACHE_LOCK:
        _MARKETS_CACHE["ts"] = now
        _MARKETS_CACHE["rows"] = rows

    return {"status": "ok", "markets": rows}
# =========================================================
# ROOT / HEALTH
# =========================================================

@app.get("/")
def root():
    return {
        "service": "Dealer Suite API",
        "status": "online",
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


# =========================================================
# ENGINE STATUS
# =========================================================

@app.get("/api/engine/status", dependencies=[Depends(require_api_key)])
def engine_status():
    try:
        gu = load_gu()

        return {
            "status": "ok",
            "gu_loaded": True,
            "gu_path": str(GU_PATH),
            "supported_assets": getattr(gu, "SUPPORTED_ASSETS", []),
            "has_execute_order": callable(getattr(gu, "execute_order", None)),
            "has_can_trade": callable(getattr(gu, "can_trade", None)),
        }

    except Exception as e:
        raise _internal_server_error(
            "Engine status ตรวจสอบไม่สำเร็จ",
            e,
        )


# =========================================================
# GET PORTFOLIO
# =========================================================

@app.get("/api/portfolio", dependencies=[Depends(require_api_key)])
def portfolio(user: str = Depends(require_user)):
    with ORDER_LOCK:
        try:
            gu = load_gu()

            # Resolve the actor from the verified session, then make gu.py use it.
            actor = _actor(user)
            _sync_gu_actor(gu, actor)

            # READ ONLY. ห้ามสร้าง wallet / ตั้งค่าเริ่มต้น / save / เขียนทับ
            sim = _load_existing_sim(gu)

            asset = str(sim.get("asset") or "BTC").upper().strip()

            requested_asset = str(
                os.environ.get("XSPRING_PORTFOLIO_ASSET", "") or ""
            ).strip().upper()

            if requested_asset and requested_asset in getattr(
                gu, "SUPPORTED_ASSETS", []
            ):
                asset = requested_asset

# Portfolio valuation uses Bitkub THB prices directly.
            # It must not depend on Yahoo Finance or USD/THB (THB=X).
            now_bkk = pd.Timestamp.now(tz=BANGKOK_TZ)

            return {
                "status": "ok",
                "actor": actor,
                "asset": asset,
                "as_of": now_bkk.isoformat(),
                "portfolio": _portfolio_response(gu, sim),
            }

        except HTTPException:
            raise

        except Exception as e:
            raise _internal_server_error(
                "เกิดข้อผิดพลาดภายใน API",
                e,
            )

# =========================================================
# CHAT (AI ASSISTANT) — read-only, never places orders
# =========================================================

CHAT_SYSTEM = (
    "คุณคือผู้ช่วยของ XSpring Dealer Suite ตอบเป็นภาษาไทย "
    "ตอบสั้นมาก ไม่เกิน 2 ประโยค ไม่เกิน 40 คำ ห้ามใช้ markdown หรือ bullet "
    "ใช้เฉพาะตัวเลขใน portfolio_context ห้ามเดาหรือสร้างตัวเลขเอง "
    "ถ้าไม่มีข้อมูลให้บอกว่าไม่มีข้อมูล "
    "ห้ามแนะนำให้ซื้อหรือขาย และคุณไม่สามารถสั่งซื้อขายแทนผู้ใช้ได้"
)


class ChatTurn(BaseModel):
    role: str = Field(..., max_length=12)
    content: str = Field(..., min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    history: list[ChatTurn] = Field(default_factory=list)


def _chat_context() -> dict:
    """Compact portfolio snapshot. Any failure -> empty context, chat still works."""
    try:
        with ORDER_LOCK:
            gu = load_gu()
            actor = _actor()
            _sync_gu_actor(gu, actor)
            sim = _load_existing_sim(gu)
            pf = _portfolio_response(gu, sim)

        return {
            "cash_thb": pf.get("cash_thb"),
            "total_value_thb": pf.get("total_value_thb"),
            "total_pnl_thb": pf.get("total_pnl_thb"),
            "pnl_pct": pf.get("pnl_pct"),
            "holdings": [
                {
                    "asset": h.get("asset"),
                    "qty": h.get("qty"),
                    "avg_cost": h.get("avg_cost"),
                    "price": h.get("price"),
                    "unrealized_pnl": h.get("unrealized_pnl"),
                    "allocation_pct": h.get("allocation_pct"),
                }
                for h in (pf.get("holdings") or [])
            ],
        }
    except Exception:
        import traceback
        traceback.print_exc()
        return {}


@app.post("/api/chat", dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ยังไม่ได้ตั้ง GEMINI_API_KEY บน Backend",
        )

    # สร้าง context ก่อน (ใช้ lock สั้น ๆ) แล้วค่อยเรียก Gemini นอก lock
    # เพื่อไม่ให้การรอ AI ไปบล็อกการส่งคำสั่งซื้อขาย
    context = _chat_context()

    messages = []
    for turn in req.history[-6:]:
        role = "assistant" if turn.role == "assistant" else "user"
        messages.append({"role": role, "content": turn.content})
    messages.append({"role": "user", "content": req.message.strip()})

    system = (
        CHAT_SYSTEM
        + "\n\nportfolio_context:\n"
        + json.dumps(context, ensure_ascii=False)
    )

    try:
        gu = load_gu()
        answer = str(gu.ask_ai(messages, api_key, system_override=system) or "").strip()
    except Exception as e:
        raise _internal_server_error("เรียก AI ไม่สำเร็จ", e)

    if len(answer) > 240:
        answer = answer[:237].rstrip() + "…"

    return {"status": "ok", "answer": answer or "ไม่ได้รับคำตอบจาก AI"}

# =========================================================
# ORDER TIMESTAMP NORMALIZATION
# =========================================================

BANGKOK_TZ = "Asia/Bangkok"

def _display_order_timestamp(value):
    """Return an order timestamp in Bangkok time.

    New records contain an explicit timezone and are left untouched.
    Legacy records in this ledger may have been written with a +2 hour
    clock error; only timestamps that are implausibly in the future are
    shifted back two hours for display. This also handles midnight rollover.
    """
    if value in (None, ""):
        return ""
    raw = str(value).strip()
    try:
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.isna(ts):
            return raw

        now = pd.Timestamp.now(tz=BANGKOK_TZ)

        if getattr(ts, "tzinfo", None) is None:
            # Naive legacy timestamps are interpreted as Bangkok local time.
            ts = ts.tz_localize(BANGKOK_TZ)
        else:
            ts = ts.tz_convert(BANGKOK_TZ)

        # The affected legacy rows are exactly two hours ahead of the real
        # Bangkok clock. Do not touch valid current/past timestamps.
        if ts > now + pd.Timedelta(minutes=5) and ts - pd.Timedelta(hours=2) <= now + pd.Timedelta(minutes=5):
            ts = ts - pd.Timedelta(hours=2)

        return ts.isoformat()
    except Exception:
        return raw


# =========================================================
# ORDER HISTORY
# =========================================================

@app.get("/api/orders", dependencies=[Depends(require_api_key)])
def order_history(
    limit: int = 100,
    asset: str = "",
    user: str = Depends(require_user),
):
    with ORDER_LOCK:
        try:
            gu = load_gu()
            actor = _actor(user)
            _sync_gu_actor(gu, actor)
            sim = _load_existing_sim(gu)

            raw_orders = sim.get("orders", [])
            if not isinstance(raw_orders, list):
                raw_orders = []

            asset_filter = str(asset or "").strip().upper()
            rows = []

            for idx, order in enumerate(raw_orders):
                if not isinstance(order, dict):
                    continue

                row_asset = str(
                    order.get("เหรียญ")
                    or order.get("asset")
                    or order.get("symbol")
                    or ""
                ).strip().upper()

                if asset_filter and row_asset != asset_filter:
                    continue

                side = _normalize_side(
                    order.get("ฝั่ง")
                    or order.get("side")
                    or ""
                )

                status = str(
                    order.get("สถานะ")
                    or order.get("status")
                    or "Filled"
                ).strip()

                order_id = str(
                    order.get("Order ID")
                    or order.get("order_id")
                    or order.get("id")
                    or f"ORDER-{idx + 1:06d}"
                )

                timestamp = _display_order_timestamp(_order_raw_time(order))

                amount = _safe_float(
                    order.get("มูลค่า (บาท)")
                    if order.get("มูลค่า (บาท)") is not None
                    else order.get("amount_thb"),
                    0.0,
                )
                quote = _safe_float(
                    order.get("ราคาที่ลูกค้าได้")
                    if order.get("ราคาที่ลูกค้าได้") is not None
                    else order.get("price_thb"),
                    0.0,
                )
                quantity = _safe_float(
                    order.get("เหรียญที่ส่งมอบ")
                    if order.get("เหรียญที่ส่งมอบ") is not None
                    else order.get("quantity"),
                    0.0,
                )
                fee = _safe_float(
                    order.get("ค่าธรรมเนียม")
                    if order.get("ค่าธรรมเนียม") is not None
                    else order.get("fee_thb"),
                    0.0,
                )

                rows.append({
                    "order_id": order_id,
                    "timestamp": timestamp,
                    "date": order.get("วันที่") or "",
                    "asset": row_asset,
                    "side": side,
                    "status": status,
                    "type": str(order.get("ประเภท") or order.get("type") or "MARKET"),
                    "amount_thb": amount,
                    "quote_thb": quote,
                    "quantity": quantity,
                    "fee_thb": fee,
                    "exchange": str(order.get("Exchange") or order.get("exchange") or "—"),
                    "source": str(order.get("Source") or order.get("source") or "Web"),
                })

            # Normalize every timestamp to UTC before sorting.
            # This prevents: Cannot compare tz-naive and tz-aware timestamps.
            def sort_key(item):
                # Use the actual ledger index as a tie-breaker.
                # gu.execute_order() records a date-only value for some orders,
                # so multiple orders can legitimately have the same timestamp
                # after normalization. The newest appended ledger row must still
                # appear first in Order History.
                row, original_index = item

                try:
                    value = row.get("timestamp") or row.get("date") or ""
                    if not value:
                        ts = pd.Timestamp("1970-01-01", tz="UTC")
                    else:
                        ts = pd.to_datetime(
                            value,
                            errors="coerce",
                            utc=True,
                        )

                        if pd.isna(ts):
                            ts = pd.Timestamp("1970-01-01", tz="UTC")

                    return (ts, original_index)
                except Exception:
                    return (
                        pd.Timestamp("1970-01-01", tz="UTC"),
                        original_index,
                    )

            # Keep original ledger position so a newly appended order wins
            # when several records have the same date / missing time.
            rows_with_index = list(zip(rows, range(len(rows))))
            rows_with_index.sort(key=sort_key, reverse=True)
            rows = [row for row, _ in rows_with_index]

            try:
                safe_limit = max(1, min(int(limit), 500))
            except (TypeError, ValueError):
                safe_limit = 100

            rows = rows[:safe_limit]

            return {
                "status": "ok",
                "actor": actor,
                "count": len(rows),
                "orders": rows,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise _internal_server_error(
                "เกิดข้อผิดพลาดภายใน API",
                e,
            )


# =========================================================
# CREATE ORDER
# =========================================================

@app.post("/api/order", dependencies=[Depends(require_api_key)])
def create_order(
    order: OrderRequest,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
    user: str = Depends(require_user),
):
    with ORDER_LOCK:
        try:
            gu = load_gu()

            actor = _actor(user)
            _sync_gu_actor(gu, actor)

            idempotency_key = str(idempotency_key or "").strip()
            if len(idempotency_key) > 200:
                raise HTTPException(
                    status_code=400,
                    detail="Idempotency-Key ยาวเกินกำหนด",
                )

            role = _set_api_role(gu, actor)

            asset = order.asset.upper().strip()
            side = order.side.lower().strip()
            amount_thb = _safe_float(order.amount_thb, -1.0)
            idempotency_fingerprint = _idempotency_fingerprint(asset, side, amount_thb)

            cached_result = _get_idempotent_result(
                actor,
                idempotency_key,
                idempotency_fingerprint,
            )
            if cached_result is not None:
                return cached_result

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

            if not asset or len(asset) > 20:
                raise HTTPException(
                    status_code=400,
                    detail="asset ไม่ถูกต้อง",
                )

            if side not in ("buy", "sell"):
                raise HTTPException(
                    status_code=400,
                    detail="side ต้องเป็น buy หรือ sell",
                )

            if not math.isfinite(amount_thb) or amount_thb <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="amount_thb ต้องเป็นตัวเลขที่มากกว่า 0",
                )

            if asset not in gu.SUPPORTED_ASSETS:
                raise HTTPException(
                    status_code=400,
                    detail=f"ไม่รองรับเหรียญ {asset}",
                )

            if side not in ("buy", "sell"):
                raise HTTPException(
                    status_code=400,
                    detail="side ต้องเป็น buy หรือ sell",
                )

            min_trade = float(getattr(gu, "MIN_TRADE_THB", 50))

            if amount_thb < min_trade:
                raise HTTPException(
                    status_code=400,
                    detail=f"ยอดขั้นต่ำคือ {min_trade:g} บาท",
                )

            if not gu.can_trade():
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"บัญชี {actor} ไม่มีสิทธิ์ Trader "
                        f"(role={role})"
                    ),
                )

            # -------------------------------------------------
            # MARKET DATA
            # -------------------------------------------------

            data = _load_market_frame(gu, asset)

            order_date = pd.Timestamp(data.index[-1])
            px_row = data.loc[order_date]

            # -------------------------------------------------
            # DEALER CONFIG
            # -------------------------------------------------

            cfg = _api_cfg(gu, asset, actor)

            built = gu.build_dealer_ctx(cfg, data)

            if built is None:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "สร้าง Dealer context "
                        "จาก market history ไม่สำเร็จ"
                    ),
                )

            ctx, target_stock_thb = built

            # -------------------------------------------------
            # LOAD EXISTING PORTFOLIO (never create a new wallet)
            # -------------------------------------------------

            sim = _load_existing_sim(gu)

            # Persistent idempotency guard: if a previous request was saved
            # successfully but the server restarted before the in-memory cache
            # could be reused, do not execute the same order twice.
            if idempotency_key:
                key_hash = _idempotency_key_hash(idempotency_key)
                existing_orders = sim.get("orders", [])
                if isinstance(existing_orders, list):
                    for existing_order in reversed(existing_orders):
                        if not isinstance(existing_order, dict):
                            continue
                        if str(existing_order.get("idempotency_key_hash") or "") != key_hash:
                            continue
                        if str(existing_order.get("idempotency_fingerprint") or "") != idempotency_fingerprint:
                            raise HTTPException(
                                status_code=409,
                                detail="Idempotency-Key ถูกใช้กับคำสั่งคนละรายการ",
                            )
                        existing_asset = str(
                            existing_order.get("เหรียญ")
                            or existing_order.get("asset")
                            or asset
                        ).upper()
                        existing_side = str(
                            existing_order.get("side")
                            or existing_order.get("ด้าน")
                            or side
                        ).lower()
                        existing_qty = existing_order.get("เหรียญที่ส่งมอบ")
                        existing_quote = existing_order.get("ราคาที่ลูกค้าได้")
                        existing_response = {
                            "status": "filled",
                            "actor": actor,
                            "asset": existing_asset,
                            "side": existing_side,
                            "amount_thb": amount_thb,
                            "quote_thb": existing_quote,
                            "quantity": existing_qty,
                            "order": existing_order,
                            "steps": [],
                            "portfolio": _portfolio_response(gu, sim),
                        }
                        _store_idempotent_result(
                            actor,
                            idempotency_key,
                            existing_response,
                            idempotency_fingerprint,
                        )
                        return existing_response

            sim = gu.sim_normalize_state(
                sim,
                asset,
                order_date,
                float(px_row["Global_USD"]),
                float(px_row["USDTHB"]),
                float(target_stock_thb),
            )

            sim["asset"] = asset
            sim["target_thb"] = float(target_stock_thb)

            gu.ensure_portfolio_ledger(sim)

            # -------------------------------------------------
            # WALLET CHECKS
            # -------------------------------------------------

            customer_thb = _safe_float(sim.get("customer_thb"), 0.0)

            customer_coins = sim.setdefault("customer_coins", {})

            held_qty = _safe_float(customer_coins.get(asset), 0.0)

            market_price_thb = (
                _safe_float(px_row["Global_USD"])
                * _safe_float(px_row["USDTHB"])
            )

            if side == "buy" and amount_thb > customer_thb + 1e-9:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"ยอด THB ใน Wallet ไม่พอ: "
                        f"มี {customer_thb:,.2f} บาท"
                    ),
                )

            if side == "sell" and held_qty <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Wallet ไม่มี {asset} สำหรับขาย",
                )

            if side == "sell" and market_price_thb > 0:
                held_value_thb = held_qty * market_price_thb

                if amount_thb > held_value_thb + 1e-9:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"ยอดขายเกินจำนวน {asset} ที่ถืออยู่: "
                            f"มูลค่าปัจจุบันประมาณ "
                            f"{held_value_thb:,.2f} บาท"
                        ),
                    )

            # -------------------------------------------------
            # FORCED QUOTE
            # -------------------------------------------------

            forced_quote = None  # ไม่รับราคาจาก client

            # -------------------------------------------------
            # EXECUTE
            # -------------------------------------------------

            # Keep order_date for market/portfolio calculations.
            # execution_time is the REAL time this API accepted the order.
            execution_time = pd.Timestamp.now(tz="Asia/Bangkok")

            steps, rec = gu.execute_order(
                sim,
                side,
                amount_thb,
                order_date,
                px_row,
                ctx,
                affect_wallet=True,
                forced_quote=forced_quote,
            )

            if rec is None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "คำสั่งไม่ผ่าน engine",
                        "steps": steps,
                    },
                )

            # gu.execute_order() ใช้ order_date เป็นวันที่ของ market data
            # ซึ่งเป็น date-only จึงไม่ควรเอาไปแสดงเป็นเวลา execution
            # (เช่น 2026-10-05 จะถูก browser แปลงเป็น 07:00 ในไทย)
            # เก็บเวลา execution จริงลงทั้ง rec และรายการที่ engine append
            # เข้า sim["orders"] โดยตรง เพื่อให้ /api/orders อ่านค่าจริงได้แน่นอน
            execution_iso = execution_time.isoformat()
            rec["เวลา"] = execution_iso
            rec["timestamp"] = execution_iso
            rec["วันที่"] = execution_time.strftime("%Y-%m-%d")
            if idempotency_key:
                rec["idempotency_key_hash"] = _idempotency_key_hash(idempotency_key)
                rec["idempotency_fingerprint"] = idempotency_fingerprint

            # execute_order() บางเวอร์ชันอาจ append สำเนา rec เข้า ledger
            # ดังนั้นแก้ entry ใน sim["orders"] โดยตรงด้วย
            ledger_orders = sim.get("orders")
            if isinstance(ledger_orders, list) and ledger_orders:
                rec_order_id = str(
                    rec.get("Order ID")
                    or rec.get("order_id")
                    or rec.get("id")
                    or ""
                )
                target = None
                if rec_order_id:
                    for ledger_order in reversed(ledger_orders):
                        if isinstance(ledger_order, dict):
                            ledger_id = str(
                                ledger_order.get("Order ID")
                                or ledger_order.get("order_id")
                                or ledger_order.get("id")
                                or ""
                            )
                            if ledger_id == rec_order_id:
                                target = ledger_order
                                break
                if target is None and isinstance(ledger_orders[-1], dict):
                    target = ledger_orders[-1]

                if target is not None:
                    target["เวลา"] = execution_iso
                    target["timestamp"] = execution_iso
                    target["วันที่"] = execution_time.strftime("%Y-%m-%d")
                    if idempotency_key:
                        target["idempotency_key_hash"] = _idempotency_key_hash(idempotency_key)
                        target["idempotency_fingerprint"] = idempotency_fingerprint

            result = str(rec.get("ผลด่าน", ""))

            # -------------------------------------------------
            # REJECT
            # -------------------------------------------------

            if result.lower().startswith("reject"):
                rejected_response = {
                    "status": "rejected",
                    "asset": asset,
                    "side": side,
                    "amount_thb": amount_thb,
                    "order": rec,
                    "steps": steps,
                }
                _store_idempotent_result(actor, idempotency_key, rejected_response, idempotency_fingerprint)
                return rejected_response

            # -------------------------------------------------
            # SAVE ONLY AFTER SUCCESS
            # -------------------------------------------------

            # ล้าง error เก่าก่อน เพราะ gu ถูก cache ข้าม request
            gu.st.session_state.pop("sim_state_save_error", None)

            gu.save_sim_state(sim)

            save_error = getattr(gu.st, "session_state", {}).get(
                "sim_state_save_error"
            )

            if save_error:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "message": (
                            "Engine ประมวลผลแล้ว "
                            "แต่บันทึก Portfolio "
                            "ถาวรไม่สำเร็จ"
                        ),
                        "retryable": True,
                        "order": rec,
                    },
                )

            # -------------------------------------------------
            # SUCCESS
            # -------------------------------------------------

            filled_response = {
                "status": "filled",
                "actor": actor,
                "asset": asset,
                "side": side,
                "amount_thb": amount_thb,
                "quote_thb": rec.get("ราคาที่ลูกค้าได้"),
                "quantity": rec.get("เหรียญที่ส่งมอบ"),
                "order": rec,
                "steps": steps,
                "portfolio": _portfolio_response(gu, sim, px_row),
            }
            _store_idempotent_result(actor, idempotency_key, filled_response, idempotency_fingerprint)
            return filled_response

        except HTTPException:
            raise

        except Exception as e:
            raise _internal_server_error(
                "เกิดข้อผิดพลาดภายใน API",
                e,
            )
