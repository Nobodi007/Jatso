from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
import importlib.util
import os
import math

import pandas as pd

app = FastAPI(
    title="Dealer Suite API",
    version="1.1.0",
)

# server.py is expected to live in the api/ directory and gu.py at repo root.
GU_PATH = Path(__file__).resolve().parent.parent / "gu.py"

# Prevent two concurrent orders from loading the same wallet snapshot and
# overwriting each other in Supabase.
ORDER_LOCK = RLock()


def load_gu():
    if not GU_PATH.exists():
        raise FileNotFoundError(f"ไม่พบ gu.py ที่ {GU_PATH}")

    import streamlit as st  # gu.py itself uses Streamlit state/persistence

    spec = importlib.util.spec_from_file_location("xspring_gu", GU_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("โหลด gu.py ไม่สำเร็จ")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OrderRequest(BaseModel):
    asset: str
    side: str
    amount_thb: float
    # Optional customer-facing quote. If omitted, the existing engine calculates
    # the quote from Global_USD x USDTHB + local premium + dealer spread.
    quote_thb: float | None = None


def _safe_float(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _actor():
    actor = str(os.environ.get("XSPRING_USER", "") or "").strip()
    if not actor:
        raise HTTPException(
            status_code=503,
            detail="ยังไม่ได้ตั้ง XSPRING_USER สำหรับบัญชี API — หยุดไว้เพื่อป้องกันการเขียนพอร์ตผิดบัญชี",
        )
    return actor


def _sync_gu_actor(gu, actor: str) -> None:
    """
    Make FastAPI use the exact same actor identity that gu.py uses for
    sim_state persistence.

    gu.py's load_sim_state() checks st.user.email first and then the
    XSPRING_REPORT_ACTOR environment variable. Render/FastAPI has no
    Streamlit signed-in user, so explicitly bridge XSPRING_USER -> the
    existing persistence actor variable.

    This only sets process-local identity; it never creates or saves state.
    """
    actor = str(actor or "").strip()
    if not actor:
        raise HTTPException(
            status_code=503,
            detail="ไม่พบ actor สำหรับโหลด Portfolio — หยุดเพื่อป้องกันการอ่าน/เขียนผิดบัญชี",
        )

    # Use the exact XSPRING_USER identity expected by the current gu.py.
    os.environ["XSPRING_USER"] = actor


def _set_api_role(gu, actor: str):
    """
    Bridge the existing gu.py RBAC into FastAPI.

    Priority:
      1. user_profiles.role for XSPRING_USER
      2. XSPRING_API_ROLE as an explicit deployment fallback

    We never silently promote an unknown API caller to Trader.
    """
    import streamlit as st

    role = None

    # Prefer the same Supabase user_profiles table used by gu.py.
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
        role = str(os.environ.get("XSPRING_API_ROLE", "viewer") or "").strip().lower()

    if role not in {"viewer", "trader", "admin"}:
        role = "viewer"

    st.session_state["guest_mode"] = False
    st.session_state["current_role"] = role
    return role


def _remote_config(gu, actor: str) -> dict:
    """
    Read the same dealer_remote_config row used by the existing application.
    Missing/failed remote config is not fatal; gu.py's existing UI defaults
    remain the fallback.
    """
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


def _api_cfg(gu, asset: str, actor: str) -> dict:
    """
    Reproduce the defaults from gu.py's build_sidebar() without invoking
    Streamlit widgets, then overlay the user's persisted dealer_remote_config.
    """
    ui = getattr(gu, "UI_DEFAULTS", {}) or {}
    exchanges = list(getattr(gu, "GLOBAL_EXCHANGE_FEE_PRESET", {}).keys())
    exchange = exchanges[0] if exchanges else "Binance"

    remote = _remote_config(gu, actor)

    remote_asset = str(remote.get("asset") or asset).upper()
    if remote_asset in getattr(gu, "SUPPORTED_ASSETS", []):
        asset = remote_asset

    exchange = str(remote.get("exchange") or exchange)
    fee_map = getattr(gu, "GLOBAL_EXCHANGE_FEE_PRESET", {})
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
    z_alpha = getattr(gu, "Z_SCORE_MAP", {}).get(confidence)
    if z_alpha is None:
        z_alpha = getattr(gu, "Z_SCORE_MAP", {}).get(99, 2.576)

    is_custodian = bool(remote.get("custodian", True))
    fixed_min_nc = (
        getattr(gu, "NC_FIXED_MIN_CUSTODIAN_THB", 25_000_000.0)
        if is_custodian
        else getattr(gu, "NC_FIXED_MIN_NON_CUSTODIAN_THB", 5_000_000.0)
    )

    cex_margin_asset = str(remote.get("margin_asset") or "Stablecoin")
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
            remote.get("spread"),
            ui.get("dealer_spread_pct", 0.5),
        ) / 100.0,
        "hedge_fee": hedge_fee,
        "hedge_fee_taker": taker_pct / 100.0,
        "hedge_fee_maker": maker_pct / 100.0,
        "maker_ratio": maker_ratio,
        "market_depth_usd": _safe_float(remote.get("depth"), 0.0),
        "impact_penalty": _safe_float(
            remote.get("impact_penalty"),
            ui.get("impact_penalty_pct", 0.5),
        ) / 100.0,
        "use_fx_proxy": False,
        "fx_limit_max": _safe_float(
            remote.get("fx_limit"),
            ui.get("fx_limit_usd", 5_000_000.0),
        ),
        "local_premium": _safe_float(
            remote.get("premium"),
            ui.get("local_premium_pct", 0.1),
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
        "slippage_sensitivity": 0.10 if asset not in getattr(gu, "STABLECOINS", set()) else 0.0,
        "monthly_volume_thb": monthly_volume,
        "daily_volume_thb": monthly_volume / 30.0,
        "net_bias_pct": _safe_float(remote.get("net_bias"), 15.0) / 100.0,
        "flow_cv_pct": _safe_float(remote.get("flow_cv"), 50.0) / 100.0,
        "settlement_days": settlement_days,
        "confidence": confidence,
        "z_alpha": z_alpha,
        "total_capital_thb": _safe_float(remote.get("capital"), 150_000_000.0),
        "cex_margin_thb": _safe_float(remote.get("margin"), 30_000_000.0),
        "liab_thb": _safe_float(remote.get("liab"), 100_000_000.0),
        "cex_margin_asset": cex_margin_asset,
        "cex_counterparty_haircut": _safe_float(remote.get("cp_haircut"), 2.0) / 100.0,
        "is_custodian": is_custodian,
        "fixed_min_nc": fixed_min_nc,
        "trading_risk_rate": _safe_float(remote.get("trading_risk"), 2.0) / 100.0,
        "cold_foreign_rate": cold_foreign_rate,
        "hot_wallet_pct": hot_wallet_pct,
        "cold_domestic_split_pct": cold_domestic_pct,
        "hedge_trigger_pct": _safe_float(remote.get("hedge_trigger"), 0.0) / 100.0,
        "hedge_vol_block_pct": _safe_float(remote.get("hedge_vol_block"), 0.0) / 100.0,
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


def _load_market_frame(gu, asset: str):
    # The engine's build_dealer_ctx/risk_profile needs historical Global_USD,
    # USDTHB and Volatility_Pct. Use the same gu.py data layer, not a new price
    # calculation in FastAPI.
    end = pd.Timestamp.now().normalize()
    start = end - pd.Timedelta(days=365)
    data, err = gu.fetch_price_data(asset, start, end, use_fx_proxy=False)
    if data is None or data.empty:
        raise HTTPException(
            status_code=503,
            detail=f"โหลดข้อมูลตลาดสำหรับ {asset} ไม่สำเร็จ: {err or 'ไม่มีข้อมูล'}",
        )
    return data


def _load_existing_sim(gu):
    """
    Load the existing portfolio for the API actor.

    Primary path remains gu.load_sim_state() so the real gu.py persistence
    logic stays the source of truth. If Streamlit's runtime cannot expose
    st.secrets/session state under FastAPI, use the same Supabase sim_state
    row through the server's own credentials. This is READ-ONLY and strictly
    scoped to XSPRING_USER; it never creates a wallet or chooses another user.
    """
    sim = None

    try:
        sim = gu.load_sim_state()
    except Exception as exc:
        try:
            gu.st.session_state["sim_state_load_error"] = str(exc)
        except Exception:
            pass

    if isinstance(sim, dict):
        try:
            gu.st.session_state["sim_state_loaded_ok"] = True
            gu.st.session_state["sim_state_source"] = (
                gu.st.session_state.get("sim_state_source") or "supabase"
            )
            gu.st.session_state["sim_state_actor"] = _actor()
        except Exception:
            pass
        return sim

    actor = _actor().strip()
    url = str(os.environ.get("SUPABASE_URL", "") or "").strip()
    key = str(
        os.environ.get("SUPABASE_SECRET_KEY", "")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or os.environ.get("SUPABASE_KEY", "")
        or ""
    ).strip()

    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "โหลด Portfolio เดิมไม่สำเร็จ",
                "reason": "Render ไม่มี SUPABASE_URL/SUPABASE_KEY ที่ใช้สำหรับอ่าน sim_state",
            },
        )

    try:
        query = urllib.parse.urlencode({
            "select": "data,actor,updated_at",
            "actor": f"eq.{actor}",
            "limit": "1",
        })
        endpoint = f"{url.rstrip('/')}/rest/v1/sim_state?{query}"
        req = urllib.request.Request(
            endpoint,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))

        if isinstance(rows, list) and rows:
            row = rows[0]
            row_actor = str(row.get("actor") or "").strip()
            if row_actor.lower() != actor.lower():
                raise HTTPException(
                    status_code=503,
                    detail="พบ sim_state แต่ actor ไม่ตรงกับบัญชี API — หยุดเพื่อป้องกันการอ่านผิดบัญชี",
                )

            data = row.get("data")
            if isinstance(data, str):
                data = json.loads(data)

            if isinstance(data, dict):
                try:
                    gu.st.session_state["sim_state_loaded_ok"] = True
                    gu.st.session_state["sim_state_source"] = "supabase_rest_api"
                    gu.st.session_state["sim_state_actor"] = row_actor
                    gu.st.session_state.pop("sim_state_load_error", None)
                except Exception:
                    pass
                return data

            raise HTTPException(
                status_code=503,
                detail="พบ sim_state ของบัญชีนี้ แต่ช่อง data ไม่ใช่ JSON object — ไม่เขียนทับข้อมูล",
            )

        raise HTTPException(
            status_code=503,
            detail="ไม่พบ sim_state ของบัญชี teerapat30204@gmail.com — ไม่สร้างพอร์ตใหม่",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "อ่าน sim_state จาก Supabase ไม่สำเร็จ",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )


def _portfolio_response(gu, sim, px_row):
    price_thb = _safe_float(px_row["Global_USD"]) * _safe_float(px_row["USDTHB"])
    snap = gu.portfolio_snapshot(sim, {str(sim.get("asset")): price_thb})
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


@app.get("/")
def root():
    return {"service": "Dealer Suite API", "status": "online"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


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


@app.get("/api/portfolio")
def portfolio():
    """
    Read-only portfolio check.

    IMPORTANT:
    - Uses the exact XSPRING_USER -> XSPRING_USER bridge used by gu.py.
    - Calls gu.load_sim_state() only.
    - Never creates a default wallet.
    - Never saves/mutates sim_state.
    """
    try:
        gu = load_gu()
        actor = _actor()
        _sync_gu_actor(gu, actor)

        sim = _load_existing_sim(gu)

        asset = str(sim.get("asset") or "BTC").upper().strip()
        if asset not in getattr(gu, "SUPPORTED_ASSETS", []):
            asset = "BTC"

        data = _load_market_frame(gu, asset)
        order_date = pd.Timestamp(data.index[-1])
        px_row = data.loc[order_date]

        return {
            "status": "ok",
            "actor": actor,
            "sim_state_source": getattr(gu, "st", None).session_state.get("sim_state_source"),
            "sim_state_actor": getattr(gu, "st", None).session_state.get("sim_state_actor"),
            "as_of": order_date.isoformat(),
            "asset": asset,
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


@app.post("/api/order")
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

            if asset not in gu.SUPPORTED_ASSETS:
                raise HTTPException(status_code=400, detail=f"ไม่รองรับเหรียญ {asset}")
            if side not in ("buy", "sell"):
                raise HTTPException(status_code=400, detail="side ต้องเป็น buy หรือ sell")
            if amount_thb < float(getattr(gu, "MIN_TRADE_THB", 50)):
                raise HTTPException(
                    status_code=400,
                    detail=f"ยอดขั้นต่ำคือ {getattr(gu, 'MIN_TRADE_THB', 50)} บาท",
                )

            if not gu.can_trade():
                raise HTTPException(
                    status_code=403,
                    detail=f"บัญชี {actor} ไม่มีสิทธิ์ Trader (role={role})",
                )

            data = _load_market_frame(gu, asset)
            order_date = pd.Timestamp(data.index[-1])
            px_row = data.loc[order_date]

            cfg = _api_cfg(gu, asset, actor)
            built = gu.build_dealer_ctx(cfg, data)
            if built is None:
                raise HTTPException(
                    status_code=503,
                    detail="สร้าง Dealer context จาก market history ไม่สำเร็จ",
                )
            ctx, target_stock_thb = built

            sim = _load_existing_sim(gu)
            sim = gu.sim_normalize_state(
                sim,
                asset,
                order_date,
                float(px_row["Global_USD"]),
                float(px_row["USDTHB"]),
                float(target_stock_thb),
            )
            # The existing engine is multi-asset; the selected API asset is the
            # asset for this transaction, while the customer's other holdings
            # remain untouched.
            sim["asset"] = asset
            sim["target_thb"] = float(target_stock_thb)
            gu.ensure_portfolio_ledger(sim)

            customer_thb = _safe_float(sim.get("customer_thb"), 0.0)
            customer_coins = sim.setdefault("customer_coins", {})
            held_qty = _safe_float(customer_coins.get(asset), 0.0)

            if side == "buy" and amount_thb > customer_thb + 1e-9:
                raise HTTPException(
                    status_code=400,
                    detail=f"ยอด THB ใน Wallet ไม่พอ: มี {customer_thb:,.2f} บาท",
                )

            # execute_order itself historically assumes the UI has already
            # checked sell quantity. Do that check here so the API cannot create
            # a negative customer balance by selling coins the customer lacks.
            # We use the engine's own quote when no explicit quote was supplied.
            if side == "sell" and held_qty <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Wallet ไม่มี {asset} สำหรับขาย",
                )

            forced_quote = (
                _safe_float(order.quote_thb, 0.0)
                if order.quote_thb is not None
                else None
            )
            if forced_quote is not None and forced_quote <= 0:
                forced_quote = None

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

            # execute_order can return a Reject record. Do not persist a rejected
            # transaction as a successful order.
            result = str(rec.get("ผลด่าน", ""))
            if result.lower().startswith("reject"):
                return {
                    "status": "rejected",
                    "asset": asset,
                    "side": side,
                    "amount_thb": amount_thb,
                    "order": rec,
                    "steps": steps,
                }

            # Same persistence function as the existing Streamlit Exchange.
            gu.save_sim_state(sim)
            save_error = getattr(gu.st, "session_state", {}).get("sim_state_save_error")
            if save_error:
                # Do not claim success when the wallet was mutated only in memory.
                raise HTTPException(
                    status_code=503,
                    detail={
                        "message": "Engine ประมวลผลแล้ว แต่บันทึก Portfolio ถาวรไม่สำเร็จ",
                        "save_error": save_error,
                        "order": rec,
                    },
                )

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
