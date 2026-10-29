"""ประกอบงาน 1 รอบ: ดึงราคา (ผ่าน cache) -> ตรวจ -> engine -> เก็บผล — sync ทั้งหมด (เรียกจาก thread)"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone

from . import config as C
from .data.price_store import PriceStore
from .data.provider_base import ProviderError
from .data.validate import DataError, clean_bars
from .db.run_store import RunStore, now_iso
from .engine.runner import run_backtest
from .engine.spec import SpecError, spec_hash

log = logging.getLogger("backtest_lab")

WARN_SURVIVORSHIP = {
    "code": "survivorship_bias", "severity": "medium",
    "message": "ข้อมูลไม่รวมหุ้นที่ถูกถอนจากตลาด/ล้มละลายในอดีต ผลย้อนหลังจึงมีแนวโน้มดีกว่าความเป็นจริง"}


def _warnings(spec: dict, snapshot: list[dict], issues: list[dict], filled: dict) -> list[dict]:
    w = [dict(WARN_SURVIVORSHIP),
         {"code": "price_return_only", "severity": "info",
          "message": "ผลตอบแทนเป็น Price Return ไม่รวมเงินปันผล (ทั้งพอร์ตและ S&P 500)"}]
    if any(s["source"] == "yahoo" for s in snapshot):
        w.append({"code": "unofficial_source", "severity": "info",
                  "message": "ข้อมูลราคามาจาก Yahoo Finance (แหล่งไม่เป็นทางการ) ควรตรวจสอบก่อนใช้ตัดสินใจ"})
    for s in snapshot:
        if s["stale"]:
            w.append({"code": "stale_data", "severity": "medium", "symbol": s["symbol"],
                      "message": f"{s['symbol']}: อัปเดตราคาล่าสุดไม่สำเร็จ ใช้ข้อมูลที่ cache ไว้เมื่อ {s['fetched_at']}"})
    for i in issues:
        if i["code"] == "possible_unadjusted_split":
            w.append({"code": i["code"], "severity": "high", "symbol": i["symbol"],
                      "message": f"{i['symbol']}: ราคาปิดกระโดดประมาณ {i['ratio']}x วันที่ {i['date']} อาจเป็น split ที่ยังไม่ถูกปรับ ผลอาจคลาดเคลื่อนมาก"})
        elif i["code"] == "gap":
            w.append({"code": "data_gap", "severity": "low", "symbol": i["symbol"],
                      "message": f"{i['symbol']}: ข้อมูลขาดช่วง {i['from']} → {i['to']} ({i['days']} วัน)"})
        elif i["code"] in ("ohlc_inconsistent", "dropped_rows"):
            w.append({"code": i["code"], "severity": "low", "symbol": i["symbol"],
                      "message": f"{i['symbol']}: พบแท่งราคาผิดปกติ {i['count']} แท่ง"})
    for sym, n in filled.items():
        if n:
            w.append({"code": "filled_days", "severity": "low", "symbol": sym,
                      "message": f"{sym}: ไม่มีราคา {n} วัน ใช้ราคาปิดล่าสุดเติมแทน"})
    if spec["risk_free_annual"] is None:
        w.append({"code": "risk_free_missing", "severity": "info",
                  "message": "ไม่ได้ระบุ risk-free rate: Sharpe และ Alpha มาตรฐานจะเป็น unavailable (ระบบไม่สมมติค่าเอง)"})
    return w


def build_result(spec: dict, price_store: PriceStore) -> dict:
    start, end = date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"])
    fetch_from = start - timedelta(days=30)                # ต้องมีแท่งก่อนวันเริ่ม (วันฐาน + seed สำหรับเติมช่องว่าง)
    bars, snapshot, issues = {}, [], []
    for sym in [p["symbol"] for p in spec["positions"]] + [C.BENCHMARK]:
        raw, meta = price_store.get_bars(sym, fetch_from, end)
        cleaned, iss = clean_bars(sym, raw)
        bars[sym] = cleaned
        issues.extend(iss)
        snapshot.append({**meta, "bars_used": len(cleaned)})
    bench = bars.pop(C.BENCHMARK)
    result = run_backtest(spec, bars, bench)
    filled = result["data_quality"]["filled_days"]
    result["data_quality"]["issues"] = issues
    result["data_snapshot"] = snapshot
    result["warnings"] = _warnings(spec, snapshot, issues, filled)
    result["engine_version"] = C.ENGINE_VERSION
    result["spec_hash"] = spec_hash(spec)
    return result


def _fail(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def execute_run(run_id: str, email: str, spec: dict, run_store: RunStore, price_store: PriceStore,
                cancel: threading.Event) -> None:
    run_store.update(email, run_id, {"status": "running", "started_at": now_iso()})
    fields: dict
    try:
        fields = {"status": "done", "result": build_result(spec, price_store), "error": None}
    except (SpecError, DataError) as e:
        fields = {"status": "failed", "error": _fail(getattr(e, "code", "invalid_spec"), str(e))}
    except ProviderError as e:
        log.warning("provider error run=%s: %s", run_id, type(e).__name__)
        fields = {"status": "failed", "error": _fail("provider_error", f"ดึงข้อมูลราคาไม่สำเร็จ: {e}")}
    except Exception:                                      # ไม่เปิดรายละเอียดภายในให้ผู้ใช้
        log.exception("backtest run failed run=%s", run_id)
        fields = {"status": "failed", "error": _fail("internal_error", "เกิดข้อผิดพลาดภายในระบบ")}
    if cancel.is_set():                                    # timeout ไปแล้ว ห้ามเขียนทับ
        return
    fields["finished_at"] = now_iso()
    run_store.update(email, run_id, fields)


def mark_timeout(run_id: str, email: str, run_store: RunStore) -> None:
    run_store.update(email, run_id, {"status": "failed", "finished_at": now_iso(),
                                     "error": _fail("timeout", f"รันนานเกิน {C.RUN_TIMEOUT_SECONDS} วินาที ลองลดจำนวนหุ้นหรือช่วงเวลา")})


def reconcile(run: dict, run_store: RunStore, email: str, now: datetime | None = None) -> dict:
    """งานที่ค้าง queued/running เกินเวลา (เช่น เซิร์ฟเวอร์รีสตาร์ตกลางคัน) -> ปิดเป็น failed"""
    if run.get("status") in ("queued", "running"):
        now = now or datetime.now(timezone.utc)
        try:
            age = (now - datetime.fromisoformat(str(run["created_at"]).replace("Z", "+00:00"))).total_seconds()
        except (KeyError, ValueError):
            return run
        if age > C.RUN_TIMEOUT_SECONDS + 120:
            err = _fail("interrupted", "งานถูกหยุดกลางคัน (เซิร์ฟเวอร์รีสตาร์ตหรือหมดเวลา) กรุณารันใหม่")
            run_store.update(email, run["id"], {"status": "failed", "error": err, "finished_at": now_iso()})
            run = {**run, "status": "failed", "error": err}
    return run
