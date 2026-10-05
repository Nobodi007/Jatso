from fastapi import FastAPI, HTTPException
import importlib.util
import os
from pathlib import Path

app = FastAPI(
    title="XSpring Dealer Suite API",
    version="1.0.0",
)

GU_PATH = Path(__file__).resolve().parent.parent / "gu.py"


def load_gu():
    """
    โหลด gu.py สำหรับ API โดยเตรียม Streamlit
    ให้พร้อมก่อน import business logic
    """
    if not GU_PATH.exists():
        raise FileNotFoundError(f"ไม่พบ gu.py ที่ {GU_PATH}")

    import streamlit as st

    # บางเวอร์ชัน/โหมดของ gu.py ใช้ st.cache_data ตอน import
    # ตรวจสอบให้แน่ใจว่า cache_data มีอยู่ก่อนโหลด gu.py
    if not hasattr(st, "cache_data"):
        raise RuntimeError(
            "Streamlit ที่ Render ใช้งานไม่มี st.cache_data"
        )

    spec = importlib.util.spec_from_file_location(
        "xspring_gu",
        GU_PATH,
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            "ไม่สามารถสร้าง module spec สำหรับ gu.py ได้"
        )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


@app.get("/")
def root():
    return {
        "service": "XSpring Dealer Suite API",
        "status": "online",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
    }


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
