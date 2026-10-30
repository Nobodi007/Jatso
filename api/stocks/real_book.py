"""พอร์ตจริง (กรอกเองจากรายการของโบรกเกอร์ เช่น Webull) 1 อีเมล = 1 บัญชี ไม่เชื่อมต่อบัญชีโบรกเกอร์

แยกจากพอร์ตจำลอง (stock_accounts / stock_trades) โดยสิ้นเชิง: ใช้ตาราง real_accounts, real_trades, real_cash_flows
ทุก endpoint กรองด้วยอีเมลจาก JWT เท่านั้น (service role ข้าม RLS ได้ จึงต้องกรองเองทุกครั้ง)

- GET  /api/stocks/real/account            บัญชี (null ถ้ายังไม่เคยกรอก)
- PUT  /api/stocks/real/account            ตั้งชื่อโบรกเกอร์ (สร้างบัญชีถ้ายังไม่มี)
- GET  /api/stocks/real/trades             รายการซื้อขาย (include_voided=true เพื่อดูที่ยกเลิกแล้ว)
- POST /api/stocks/real/trades             เพิ่มรายการ (ตรวจขายเกินที่ถือ / วันที่อนาคต / ซ้ำ)
- DELETE /api/stocks/real/trades/{id}      ยกเลิกรายการ (void ไม่ลบจริง ตรวจว่าสมุดยังสอดคล้อง)
- GET/POST/DELETE /api/stocks/real/cash-flows   เงินฝาก (+) / ถอน (−)
- GET  /api/stocks/real/summary            สถานะที่ถืออยู่ (ปรับ split แล้ว) และเงินสดคงเหลือเพื่อเทียบกับ Webull

กติกา: กรอกจำนวนและราคาตามที่เกิดขึ้นจริงในวันนั้น (ไม่ต้องปรับ split) ระบบปรับให้เอง
วันที่ = วันที่ตามเวลาสหรัฐ (ET) ซื้อขายหลังตลาดปิด (16:00 ET) ให้ติ๊ก after_close
Risk Center ของพอร์ตจริงอ่านจากตารางเหล่านี้ผ่าน risk_api (?portfolio=real) แคชรายงานแยกคีย์ และถูกล้างเมื่อมีการเขียน
"""
from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import ledger as L
from . import risk_data as rd
from .auth import current_email
from .db import sb
from .risk_api import report_key
from .risk_ratelimit import make_limiter

log = logging.getLogger("stocks.real_book")
router = APIRouter(prefix="/api/stocks/real", tags=["stock-real-book"])

_write = make_limiter(current_email, 30, 60, "real_write")
_read = make_limiter(current_email, 60, 60, "real_read")

SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
MIN_DATE = date(2010, 1, 1)
AFTER_CLOSE = time(16, 30)
MIDDAY = time(12, 0)
MAX_ROWS = 5000
MAX_QTY, MAX_PRICE, MAX_FEE, MAX_FLOW = 1e9, 1e7, 1e6, 1e9
BROKER_MAX, NOTE_MAX = 40, 200
DEFAULT_BROKER = "Webull"


class AccountIn(BaseModel):
    broker: str = Field(min_length=1, max_length=BROKER_MAX)


class TradeIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    qty: float = Field(gt=0, le=MAX_QTY)
    price: float = Field(gt=0, le=MAX_PRICE)
    fee: float = Field(default=0.0, ge=0, le=MAX_FEE)
    trade_date: date
    after_close: bool = False
    note: str | None = Field(default=None, max_length=NOTE_MAX)
    confirm_duplicate: bool = False


class FlowIn(BaseModel):
    flow_date: date
    amount: float = Field(le=MAX_FLOW, ge=-MAX_FLOW)   # บวก = ฝาก, ลบ = ถอน
    note: str | None = Field(default=None, max_length=NOTE_MAX)


def _bad(code: str, status: int = 400, **extra):
    return HTTPException(status, {"code": code, **extra})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _finite(x: float, lo: float, hi: float, *, lo_open: bool = False) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x) and (x > lo if lo_open else x >= lo) and x <= hi


def trade_ts(d: date, after_close: bool) -> datetime:
    """เวลาอ้างอิงของรายการ (UTC): ก่อนปิด = 12:00 ET (นับเป็นรอบวันนั้น), หลังปิด = 16:30 ET (นับเป็นรอบถัดไปตามกฎสมุดบัญชี)"""
    return datetime.combine(d, AFTER_CLOSE if after_close else MIDDAY, tzinfo=L.ET).astimezone(timezone.utc)


def flow_ts(d: date) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=L.ET).astimezone(timezone.utc)


def _row_view(r: dict) -> dict:
    ts = L.parse_ts(r["ts"])
    et = ts.astimezone(L.ET)
    return {**r, "trade_date": et.date().isoformat(), "after_close": et.time() >= L.MARKET_CLOSE}


# ------------------------------------------------------------------ data access (ทุกตัวกรองด้วย email)
async def _get_account(email: str) -> dict | None:
    rows = await sb("GET", "real_accounts", params={"email": f"eq.{email}", "select": "*", "limit": "1"})
    return rows[0] if rows else None


async def _ensure_account(email: str) -> dict:
    acc = await _get_account(email)
    if acc:
        return acc
    try:
        await sb("POST", "real_accounts", json={"email": email, "broker": DEFAULT_BROKER})
    except HTTPException as e:
        if e.status_code != 409:      # 409 = คำขอพร้อมกันสร้างไปแล้ว
            raise
    return await _get_account(email) or {"email": email, "broker": DEFAULT_BROKER}


async def _active(table: str, email: str, order: str) -> list[dict]:
    out, offset = [], 0
    while True:
        rows = await sb("GET", table, params={"email": f"eq.{email}", "voided_at": "is.null", "select": "*",
                                              "order": order, "limit": "1000", "offset": str(offset)}) or []
        if any(_norm_email(str(r.get("email") or "")) != email for r in rows):
            raise HTTPException(502, "user_data_isolation_check_failed")
        out.extend(rows)
        if len(rows) < 1000:
            return out
        offset += 1000


async def _active_trades(email: str) -> list[dict]:
    return await _active("real_trades", email, "ts.asc,id.asc")


async def _active_flows(email: str) -> list[dict]:
    return await _active("real_cash_flows", email, "flow_date.asc,id.asc")


def _invalidate(email: str) -> None:
    """ล้างแคชรายงาน Risk ของพอร์ตจริง เพื่อให้รายการที่เพิ่งกรอกสะท้อนทันที (คีย์ของพอร์ตจำลองไม่ถูกแตะ)"""
    rd.invalidate(report_key(email, "real"))


async def _audit(email: str, event: str, param: str, old, new) -> bool:
    try:
        await sb("POST", "audit_log", json=[{"ts": _now().isoformat(), "actor": email, "event": event,
                                             "param": param, "old_value": old, "new_value": new}],
                 prefer="return=minimal")
        return True
    except HTTPException as e:          # บันทึกรายการแล้ว แต่ audit พลาด ให้รู้ ไม่ปิดเงียบ
        log.error("audit_log write failed (%s): %s", event, e.detail)
        return False


# ------------------------------------------------------------------ ledger checks
def _positions_or_409(trade_rows: list[dict]) -> dict:
    try:
        return L.positions(L.to_trades(trade_rows))
    except L.LedgerError as e:
        raise _bad("ledger_inconsistent", 409, message=str(e))


def cash_warnings(trade_rows: list[dict], flow_rows: list[dict]) -> tuple[float, list[dict]]:
    """ยอดเงินสดคงเหลือ และคำเตือนถ้าเงินสดเคยติดลบ (ไม่บล็อก: อาจกรอกรายการซื้อก่อนรายการฝาก)"""
    events = [(t.ts, L.cash_delta(t)) for t in L.to_trades(trade_rows)]
    events += [(flow_ts(date.fromisoformat(str(f["flow_date"]))), float(f["amount"])) for f in flow_rows]
    events.sort(key=lambda e: e[0])
    bal, first_neg = 0.0, None
    for ts, d in events:
        bal += d
        if bal < -0.005 and first_neg is None:
            first_neg = {"code": "negative_cash", "date": ts.astimezone(L.ET).date().isoformat(), "balance": round(bal, 2)}
    return round(bal, 2), ([first_neg] if first_neg else [])


async def _verify_symbol(sym: str) -> bool | None:
    """True = พบ, False = ไม่พบแน่นอน (404), None = ตรวจไม่ได้ตอนนี้ (ผู้ให้บริการขัดข้อง ไม่บล็อก แต่เตือน)"""
    from .router import get_quote
    try:
        q = await get_quote(sym)
        return bool(q and float(q.get("price") or 0) > 0)
    except HTTPException as e:
        return False if e.status_code == 404 else None
    except Exception:
        return None


def _check_trade(b: TradeIn) -> tuple[str, datetime]:
    sym = str(b.symbol or "").strip().upper()
    if not SYMBOL_RE.match(sym):
        raise _bad("invalid_symbol")
    if b.side not in ("buy", "sell"):
        raise _bad("invalid_side")
    if not (_finite(b.qty, 0, MAX_QTY, lo_open=True) and _finite(b.price, 0, MAX_PRICE, lo_open=True)
            and _finite(b.fee, 0, MAX_FEE)):
        raise _bad("invalid_amount")
    if b.note is not None and len(b.note) > NOTE_MAX:
        raise _bad("note_too_long")
    if b.trade_date < MIN_DATE:
        raise _bad("date_too_early", min_date=MIN_DATE.isoformat())
    ts = trade_ts(b.trade_date, bool(b.after_close))
    if ts > _now():
        raise _bad("trade_in_future")
    return sym, ts


# ------------------------------------------------------------------ account
@router.get("/account")
async def get_account(email: str = Depends(_read)):
    email = _norm_email(email)
    return {"account": await _get_account(email)}


@router.put("/account")
async def put_account(body: AccountIn, email: str = Depends(_write)):
    email = _norm_email(email)
    broker = (body.broker or "").strip()
    if not 1 <= len(broker) <= BROKER_MAX:
        raise _bad("invalid_broker")
    await _ensure_account(email)
    rows = await sb("PATCH", "real_accounts", params={"email": f"eq.{email}"},
                    json={"broker": broker, "updated_at": _now().isoformat()}, prefer="return=representation")
    return {"ok": True, "account": rows[0] if rows else await _get_account(email)}


# ------------------------------------------------------------------ trades
@router.get("/trades")
async def list_trades(include_voided: bool = False, limit: int = Query(200, ge=1, le=1000),
                      email: str = Depends(_read)):
    email = _norm_email(email)
    params = {"email": f"eq.{email}", "select": "*", "order": "ts.desc,id.desc", "limit": str(limit)}
    if not include_voided:
        params["voided_at"] = "is.null"
    rows = await sb("GET", "real_trades", params=params) or []
    if any(_norm_email(str(r.get("email") or "")) != email for r in rows):
        raise HTTPException(502, "user_data_isolation_check_failed")
    return {"trades": [_row_view(r) for r in rows]}


@router.post("/trades")
async def add_trade(body: TradeIn, email: str = Depends(_write)):
    email = _norm_email(email)
    sym, ts = _check_trade(body)
    existing = await _active_trades(email)
    if len(existing) >= MAX_ROWS:
        raise _bad("too_many_trades", 409, max=MAX_ROWS)
    warnings: list[dict] = []
    ok = await _verify_symbol(sym)
    if ok is False:
        raise _bad("symbol_not_found", 404, symbol=sym)
    if ok is None:
        warnings.append({"code": "symbol_unverified", "symbol": sym})

    iso = ts.isoformat()
    if not body.confirm_duplicate and any(
            r["symbol"].upper() == sym and r["side"] == body.side and L.parse_ts(r["ts"]) == ts
            and math.isclose(float(r["qty"]), body.qty, rel_tol=1e-9) and math.isclose(float(r["price"]), body.price, rel_tol=1e-9)
            for r in existing):
        raise _bad("duplicate_trade", 409, hint="send confirm_duplicate=true if this is a separate fill")

    candidate = {"id": 10**12, "symbol": sym, "side": body.side, "qty": body.qty, "price": body.price,
                 "fee": body.fee, "ts": iso}
    _positions_or_409(existing + [candidate])            # ขายเกินที่ถือ ณ เวลานั้น = ปฏิเสธ
    await _ensure_account(email)
    saved = await sb("POST", "real_trades", prefer="return=representation",
                     json=[{"email": email, "symbol": sym, "side": body.side, "qty": body.qty, "price": body.price,
                            "fee": body.fee, "ts": iso, "note": (body.note or None)}])
    row = saved[0] if saved else candidate
    _invalidate(email)
    flows = await _active_flows(email)
    _, cw = cash_warnings(existing + [{**candidate, "id": row.get("id", candidate["id"])}], flows)
    audited = await _audit(email, "real_trade_added", f"{row.get('id')}:{sym}:{body.side}", None,
                           round(body.qty * body.price, 2))
    return {"ok": True, "trade": _row_view(row), "warnings": warnings + cw, "audit_written": audited}


@router.delete("/trades/{trade_id}")
async def void_trade(trade_id: int, email: str = Depends(_write)):
    email = _norm_email(email)
    existing = await _active_trades(email)
    target = next((r for r in existing if int(r["id"]) == trade_id), None)
    if target is None:
        raise _bad("trade_not_found", 404)
    rest = [r for r in existing if int(r["id"]) != trade_id]
    _positions_or_409(rest)                              # ยกเลิกรายการซื้อที่มีการขายตามมา = ปฏิเสธ
    rows = await sb("PATCH", "real_trades",
                    params={"id": f"eq.{trade_id}", "email": f"eq.{email}", "voided_at": "is.null"},
                    json={"voided_at": _now().isoformat()}, prefer="return=representation")
    if not rows:
        raise _bad("trade_not_found", 404)
    _invalidate(email)
    flows = await _active_flows(email)
    _, cw = cash_warnings(rest, flows)
    audited = await _audit(email, "real_trade_voided", f"{trade_id}:{target['symbol']}:{target['side']}",
                           round(float(target["qty"]) * float(target["price"]), 2), None)
    return {"ok": True, "warnings": cw, "audit_written": audited}


# ------------------------------------------------------------------ cash flows
def _check_flow(b: FlowIn) -> None:
    if not (isinstance(b.amount, (int, float)) and math.isfinite(b.amount) and b.amount != 0 and abs(b.amount) <= MAX_FLOW):
        raise _bad("invalid_amount")
    if b.note is not None and len(b.note) > NOTE_MAX:
        raise _bad("note_too_long")
    if b.flow_date < MIN_DATE:
        raise _bad("date_too_early", min_date=MIN_DATE.isoformat())
    if flow_ts(b.flow_date) > _now():
        raise _bad("flow_in_future")


@router.get("/cash-flows")
async def list_flows(include_voided: bool = False, limit: int = Query(200, ge=1, le=1000),
                     email: str = Depends(_read)):
    email = _norm_email(email)
    params = {"email": f"eq.{email}", "select": "*", "order": "flow_date.desc,id.desc", "limit": str(limit)}
    if not include_voided:
        params["voided_at"] = "is.null"
    rows = await sb("GET", "real_cash_flows", params=params) or []
    if any(_norm_email(str(r.get("email") or "")) != email for r in rows):
        raise HTTPException(502, "user_data_isolation_check_failed")
    return {"cash_flows": rows}


@router.post("/cash-flows")
async def add_flow(body: FlowIn, email: str = Depends(_write)):
    email = _norm_email(email)
    _check_flow(body)
    flows = await _active_flows(email)
    if len(flows) >= MAX_ROWS:
        raise _bad("too_many_cash_flows", 409, max=MAX_ROWS)
    await _ensure_account(email)
    saved = await sb("POST", "real_cash_flows", prefer="return=representation",
                     json=[{"email": email, "flow_date": body.flow_date.isoformat(),
                            "amount": body.amount, "note": (body.note or None)}])
    row = saved[0] if saved else {"flow_date": body.flow_date.isoformat(), "amount": body.amount}
    _invalidate(email)
    trades = await _active_trades(email)
    _, cw = cash_warnings(trades, flows + [row])
    audited = await _audit(email, "real_cash_flow_added", f"flow:{row.get('id')}", None, body.amount)
    return {"ok": True, "cash_flow": row, "warnings": cw, "audit_written": audited}


@router.delete("/cash-flows/{flow_id}")
async def void_flow(flow_id: int, email: str = Depends(_write)):
    email = _norm_email(email)
    flows = await _active_flows(email)
    target = next((f for f in flows if int(f["id"]) == flow_id), None)
    if target is None:
        raise _bad("cash_flow_not_found", 404)
    rows = await sb("PATCH", "real_cash_flows",
                    params={"id": f"eq.{flow_id}", "email": f"eq.{email}", "voided_at": "is.null"},
                    json={"voided_at": _now().isoformat()}, prefer="return=representation")
    if not rows:
        raise _bad("cash_flow_not_found", 404)
    _invalidate(email)
    trades = await _active_trades(email)
    _, cw = cash_warnings(trades, [f for f in flows if int(f["id"]) != flow_id])
    audited = await _audit(email, "real_cash_flow_voided", f"flow:{flow_id}", float(target["amount"]), None)
    return {"ok": True, "warnings": cw, "audit_written": audited}


# ------------------------------------------------------------------ summary (เทียบกับ Webull)
async def _adjusted(rows: list[dict]):
    from .stock_book import _adjusted as adjusted   # ปรับ split แบบเดียวกับพอร์ตจำลอง (best effort)
    return await adjusted(rows)


@router.get("/summary")
async def summary(email: str = Depends(_read)):
    email = _norm_email(email)
    acc = await _get_account(email)
    trade_rows = await _active_trades(email)
    flows = await _active_flows(email)
    _positions_or_409(trade_rows)
    cash, cw = cash_warnings(trade_rows, flows)
    try:
        trades, split_warnings = await _adjusted(trade_rows)
        pos = L.positions(trades)
    except L.LedgerError as e:
        raise _bad("ledger_inconsistent", 409, message=str(e))
    rows = [{"symbol": s, "qty": p.qty, "avg_cost": p.avg_cost, "realized_gross": p.realized_pnl_gross, "fees": p.fees}
            for s, p in sorted(pos.items()) if p.qty > L.QTY_EPS]
    return {"account": acc, "positions": rows, "cash_balance": cash,
            "realized_gross": round(sum(p.realized_pnl_gross for p in pos.values()), 2),
            "fees_paid": round(sum(p.fees for p in pos.values()), 2),
            "counts": {"trades": len(trade_rows), "cash_flows": len(flows)},
            "warnings": cw + [{"code": "splits_unavailable", "detail": w} for w in split_warnings],
            "note": "จำนวนและต้นทุนเฉลี่ยปรับ split แล้ว เทียบกับหน้าถือครองใน Webull ได้ · ยังไม่รวมปันผล"}
