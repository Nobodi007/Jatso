from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import importlib.util
from pathlib import Path

app = FastAPI(
    title="XSpring Dealer Suite API",
    version="1.0.0",
)

GU_PATH = Path(__file__).resolve().parent.parent / "gu.py"


def load_gu():
    if not GU_PATH.exists():
        raise FileNotFoundError(f"ไม่พบ gu.py ที่ {GU_PATH}")

    import streamlit as st

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


@app.get("/")
def root():
    return {
        "service": "XSpring Dealer Suite API",
        "status": "online",
    }


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
            "supported_assets": getattr(
                gu,
                "SUPPORTED_ASSETS",
                [],
            ),
            "has_execute_order": callable(
                getattr(gu, "execute_order", None)
            ),
            "has_can_trade": callable(
                getattr(gu, "can_trade", None)
            ),
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


@app.post("/api/order")
def create_order(order: OrderRequest):
    try:
        gu = load_gu()

        asset = order.asset.upper()
        side = order.side.lower()
        amount_thb = float(order.amount_thb)

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

        if amount_thb < float(getattr(gu, "MIN_TRADE_THB", 50)):
            raise HTTPException(
                status_code=400,
                detail=f"ยอดขั้นต่ำคือ {getattr(gu, 'MIN_TRADE_THB', 50)} บาท",
            )

        if not gu.can_trade():
            raise HTTPException(
                status_code=403,
                detail="ระบบไม่อนุญาตให้ซื้อขายในขณะนี้",
            )

        return {
            "status": "ready",
            "message": "โหลด gu.py และ execute_order สำเร็จ",
            "asset": asset,
            "side": side,
            "amount_thb": amount_thb,
            "execute_order": True,
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
