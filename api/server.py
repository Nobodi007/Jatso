from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from threading import RLock
from functools import lru_cache
from typing import Optional
import hmac
import importlib.util
import os
import math

import pandas as pd


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Dealer Suite API",
    version="1.3.1",
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

def require_api_key(x_api_key: str = Header(default="")):
    expected = os.environ.get("DEALER_API_KEY", "").strip()

    if not expected or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


# =========================================================
# REQUEST MODEL
# =========================================================

class OrderRequest(BaseModel):
    asset: str
    side: str
    amount_thb: float
    # รับไว้เพื่อไม่ให้ frontend เดิมพัง แต่ server ไม่ใช้ค่านี้
    quote_thb: Optional[float] = None


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

def _actor():
    """
    Resolve the persistent account actor.

    Priority:
        1. XSPRING_USER
        2. XSPRING_REPORT_ACTOR

    IMPORTANT: Never invent a new actor.
    """
    user_actor = str(os.environ.get("XSPRING_USER", "") or "").strip()
    report_actor = str(os.environ.get("XSPRING_REPORT_ACTOR", "") or "").strip()

    actor = user_actor or report_actor

    if not actor:
        raise HTTPException(
            status_code=503,
            detail=(
                "ยังไม่ได้ตั้ง XSPRING_USER หรือ "
                "XSPRING_REPORT_ACTOR สำหรับบัญชี API "
                "— หยุดไว้เพื่อป้องกันการอ่าน/เขียนผิดบัญชี"
            ),
        )

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

    if role not in {"viewer", "trader", "admin"}:
        role = str(
            os.environ.get("XSPRING_API_ROLE", "viewer") or ""
        ).strip().lower()

    if role not in {"viewer", "trader", "admin"}:
        role = "viewer"

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

def _portfolio_response(gu, sim, px_row):
    """Build a snapshot using live THB prices for every held asset."""
    selected_asset = str(sim.get("asset") or "").upper().strip()
    selected_price_thb = (
        _safe_float(px_row.get("Global_USD"))
        * _safe_float(px_row.get("USDTHB"))
    )

    price_map = {}
    if selected_asset and selected_price_thb > 0:
        price_map[selected_asset] = selected_price_thb

    held_assets = set()
    customer_coins = sim.get("customer_coins", {})
    if isinstance(customer_coins, dict):
        for asset, qty in customer_coins.items():
            if _safe_float(qty) > 1e-12:
                held_assets.add(str(asset).upper().strip())

    for tx in sim.get("portfolio_ledger", []) or []:
        if not isinstance(tx, dict):
            continue
        asset = str(tx.get("asset") or "").upper().strip()
        if asset and asset != "THB":
            held_assets.add(asset)

    usdthb = _safe_float(px_row.get("USDTHB"))
    if usdthb <= 0:
        try:
            usdthb, _ = gu.get_reference_usdthb()
        except Exception:
            usdthb = 0.0

    remaining = sorted(a for a in held_assets if a not in price_map)
    if remaining:
        try:
            overview = gu.fetch_market_overview(remaining)
        except Exception:
            overview = pd.DataFrame()
        if overview is not None and not overview.empty and usdthb > 0:
            for _, row in overview.iterrows():
                asset = str(row.get("symbol") or "").upper().strip()
                usd_price = _safe_float(row.get("price_usd"))
                if asset and usd_price > 0:
                    price_map[asset] = usd_price * usdthb

    snap = gu.portfolio_snapshot(sim, price_map)
    return {
        "cash_thb": snap["cash_thb"],
        "market_value_thb": snap["market_value_thb"],
        "total_value_thb": snap["total_value_thb"],
        "realized_pnl_thb": snap["realized_pnl_thb"],
        "unrealized_pnl_thb": snap["unrealized_pnl_thb"],
        "total_pnl_thb": snap["total_pnl_thb"],
        "pnl_pct": snap["pnl_pct"],
        "fees_thb": snap["fees_thb"],
        "holdings": snap["rows"],
    }


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

@app.get("/api/engine/status")
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
        raise HTTPException(
            status_code=500,
            detail={
                "gu_loaded": False,
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )


# =========================================================
# GET PORTFOLIO
# =========================================================

@app.get("/api/portfolio")
def portfolio():
    with ORDER_LOCK:
        try:
            gu = load_gu()

            # Resolve the EXISTING actor, then make gu.py use the same one.
            actor = _actor()
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

            data = _load_market_frame(gu, asset)

            order_date = pd.Timestamp(data.index[-1])
            px_row = data.loc[order_date]

            return {
                "status": "ok",
                "actor": actor,
                "asset": asset,
                "as_of": order_date.isoformat(),
                "portfolio": _portfolio_response(gu, sim, px_row),
            }

        except HTTPException:
            raise

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
            )


# =========================================================
# CREATE ORDER
# =========================================================

@app.post("/api/order", dependencies=[Depends(require_api_key)])
def create_order(order: OrderRequest):
    with ORDER_LOCK:
        try:
            gu = load_gu()

            actor = _actor()
            _sync_gu_actor(gu, actor)

            role = _set_api_role(gu, actor)

            asset = order.asset.upper().strip()
            side = order.side.lower().strip()
            amount_thb = _safe_float(order.amount_thb, -1.0)

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

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

            result = str(rec.get("ผลด่าน", ""))

            # -------------------------------------------------
            # REJECT
            # -------------------------------------------------

            if result.lower().startswith("reject"):
                return {
                    "status": "rejected",
                    "asset": asset,
                    "side": side,
                    "amount_thb": amount_thb,
                    "order": rec,
                    "steps": steps,
                }

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
                        "save_error": save_error,
                        "order": rec,
                    },
                )

            # -------------------------------------------------
            # SUCCESS
            # -------------------------------------------------

            return {
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

        except HTTPException:
            raise

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
            )
