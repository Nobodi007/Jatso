import asyncio
import datetime as dt
from types import SimpleNamespace

import pytest
from stocks import real_book as R


class FakeDB:
    """จำลอง PostgREST เท่าที่ real_book ใช้: eq./is.null filter, insert, patch, order, limit"""
    def __init__(self):
        self.t = {"real_accounts": [], "real_trades": [], "real_cash_flows": [], "audit_log": []}
        self.seq = 0
        self.fail_audit = False

    def _match(self, row, params):
        for k, v in (params or {}).items():
            if k in ("select", "order", "limit", "offset"):
                continue
            if v.startswith("eq."):
                if str(row.get(k)) != v[3:]:
                    return False
            elif v == "is.null":
                if row.get(k) is not None:
                    return False
        return True

    async def sb(self, method, table, params=None, json=None, prefer=None, **kw):
        rows = self.t[table]
        if method == "GET":
            out = [r for r in rows if self._match(r, params)]
            order = (params or {}).get("order", "")
            if order.startswith("ts.desc") or order.startswith("flow_date.desc"):
                out.sort(key=lambda r: (str(r.get("ts") or r.get("flow_date")), r["id"]), reverse=True)
            elif order.startswith("ts.asc"):
                out.sort(key=lambda r: (str(r["ts"]), r["id"]))
            lim = int((params or {}).get("limit", 1000)); off = int((params or {}).get("offset", 0))
            return [dict(r) for r in out[off:off + lim]]
        if method == "POST":
            if table == "audit_log" and self.fail_audit:
                raise R.HTTPException(500, "boom")
            items = json if isinstance(json, list) else [json]
            saved = []
            for it in items:
                row = dict(it)
                if table == "real_accounts":
                    if any(r["email"] == row["email"] for r in rows):
                        raise R.HTTPException(409, "dup")
                elif table != "audit_log":
                    self.seq += 1
                    row["id"] = self.seq
                    row.setdefault("voided_at", None)
                rows.append(row)
                saved.append(dict(row))
            return saved
        if method == "PATCH":
            hit = [r for r in rows if self._match(r, params)]
            for r in hit:
                r.update(json)
            return [dict(r) for r in hit]
        raise AssertionError(method)


def _setup(monkeypatch, verify=True):
    db = FakeDB()
    monkeypatch.setattr(R, "sb", db.sb)

    async def fake_verify(sym):
        return verify

    monkeypatch.setattr(R, "_verify_symbol", fake_verify)
    return db


def _trade(**kw):
    d = dict(symbol="MU", side="buy", qty=10.0, price=95.0, fee=0.0, trade_date=dt.date(2026, 10, 20),
             after_close=False, note=None, confirm_duplicate=False)
    d.update(kw)
    return SimpleNamespace(**d)


def _flow(**kw):
    d = dict(flow_date=dt.date(2026, 10, 1), amount=5000.0, note=None)
    d.update(kw)
    return SimpleNamespace(**d)


def run(coro):
    return asyncio.run(coro)


def code_of(e):
    return e.value.detail["code"] if isinstance(e.value.detail, dict) else e.value.detail


def test_add_buy_creates_account_lazily_and_stores_et_midday_timestamp(monkeypatch):
    db = _setup(monkeypatch)
    out = run(R.add_trade(_trade(symbol=" mu "), email="A@B.C"))
    assert out["ok"] and out["trade"]["symbol"] == "MU" and out["trade"]["trade_date"] == "2026-10-20"
    assert out["trade"]["after_close"] is False
    assert db.t["real_accounts"][0]["email"] == "a@b.c" and db.t["real_accounts"][0]["broker"] == "Webull"
    assert db.t["real_trades"][0]["email"] == "a@b.c"
    ts = R.L.parse_ts(db.t["real_trades"][0]["ts"]).astimezone(R.L.ET)
    assert (ts.hour, ts.minute) == (12, 0)
    assert [a["event"] for a in db.t["audit_log"]] == ["real_trade_added"]


def test_after_close_trade_belongs_to_next_session(monkeypatch):
    db = _setup(monkeypatch)
    out = run(R.add_trade(_trade(after_close=True), email="a@b.c"))
    assert out["trade"]["after_close"] is True and out["trade"]["trade_date"] == "2026-10-20"
    ts = R.L.parse_ts(db.t["real_trades"][0]["ts"])
    assert R.L.session_date(ts) == dt.date(2026, 10, 21)          # กฎสมุดบัญชีเดียวกับพอร์ตจำลอง


def test_oversell_is_rejected_and_nothing_is_written(monkeypatch):
    db = _setup(monkeypatch)
    run(R.add_trade(_trade(qty=10), email="a@b.c"))
    with pytest.raises(R.HTTPException) as e:
        run(R.add_trade(_trade(side="sell", qty=11, trade_date=dt.date(2026, 10, 21)), email="a@b.c"))
    assert e.value.status_code == 409 and code_of(e) == "ledger_inconsistent"
    assert len(db.t["real_trades"]) == 1
    # ขายก่อนซื้อ (เวลาเรียงตามวันที่ ไม่ใช่ลำดับกรอก) ก็ผิด
    with pytest.raises(R.HTTPException) as e2:
        run(R.add_trade(_trade(side="sell", qty=5, trade_date=dt.date(2026, 10, 19)), email="a@b.c"))
    assert code_of(e2) == "ledger_inconsistent"
    run(R.add_trade(_trade(side="sell", qty=10, trade_date=dt.date(2026, 10, 21)), email="a@b.c"))


def test_backdated_buy_can_be_entered_after_the_sell(monkeypatch):
    db = _setup(monkeypatch)
    # กรอกย้อนหลัง: ขายก่อน (ยังไม่มีของ) ถูกปฏิเสธ แต่กรอกซื้อก่อนแล้วค่อยขายได้เสมอ
    run(R.add_trade(_trade(qty=4, trade_date=dt.date(2026, 10, 5)), email="a@b.c"))
    run(R.add_trade(_trade(side="sell", qty=4, trade_date=dt.date(2026, 10, 9)), email="a@b.c"))
    run(R.add_trade(_trade(qty=6, trade_date=dt.date(2026, 10, 7)), email="a@b.c"))   # แทรกกลาง ยังสอดคล้อง
    assert len(db.t["real_trades"]) == 3


def test_validation_rejects_bad_input(monkeypatch):
    _setup(monkeypatch)
    bad = [(_trade(symbol="bad symbol"), "invalid_symbol"), (_trade(symbol="1AB"), "invalid_symbol"),
           (_trade(qty=0), "invalid_amount"), (_trade(qty=float("nan")), "invalid_amount"),
           (_trade(price=-1), "invalid_amount"), (_trade(fee=-0.1), "invalid_amount"),
           (_trade(price=float("inf")), "invalid_amount"), (_trade(side="short"), "invalid_side"),
           (_trade(trade_date=dt.date(2009, 12, 31)), "date_too_early"),
           (_trade(trade_date=dt.date.today() + dt.timedelta(days=2)), "trade_in_future"),
           (_trade(note="x" * 201), "note_too_long")]
    for body, code in bad:
        with pytest.raises(R.HTTPException) as e:
            run(R.add_trade(body, email="a@b.c"))
        assert e.value.status_code == 400 and code_of(e) == code, code


def test_unknown_symbol_rejected_but_provider_outage_only_warns(monkeypatch):
    db = _setup(monkeypatch, verify=False)
    with pytest.raises(R.HTTPException) as e:
        run(R.add_trade(_trade(symbol="ZZZZ"), email="a@b.c"))
    assert e.value.status_code == 404 and code_of(e) == "symbol_not_found" and not db.t["real_trades"]
    _setup(monkeypatch, verify=None)
    out = run(R.add_trade(_trade(symbol="MU"), email="a@b.c"))
    assert {"code": "symbol_unverified", "symbol": "MU"} in out["warnings"]


def test_duplicate_needs_explicit_confirmation(monkeypatch):
    db = _setup(monkeypatch)
    run(R.add_trade(_trade(), email="a@b.c"))
    with pytest.raises(R.HTTPException) as e:
        run(R.add_trade(_trade(), email="a@b.c"))
    assert e.value.status_code == 409 and code_of(e) == "duplicate_trade"
    run(R.add_trade(_trade(confirm_duplicate=True), email="a@b.c"))
    assert len(db.t["real_trades"]) == 2


def test_void_buy_that_was_later_sold_is_rejected_and_void_is_scoped_to_owner(monkeypatch):
    db = _setup(monkeypatch)
    buy = run(R.add_trade(_trade(qty=10), email="a@b.c"))["trade"]
    run(R.add_trade(_trade(side="sell", qty=10, trade_date=dt.date(2026, 10, 22)), email="a@b.c"))
    with pytest.raises(R.HTTPException) as e:
        run(R.void_trade(buy["id"], email="a@b.c"))
    assert e.value.status_code == 409 and code_of(e) == "ledger_inconsistent"
    assert all(r["voided_at"] is None for r in db.t["real_trades"])
    # คนอื่นยกเลิกรายการของเราไม่ได้ (ไม่รั่วว่ามีรายการนี้อยู่)
    with pytest.raises(R.HTTPException) as e2:
        run(R.void_trade(buy["id"], email="evil@x.y"))
    assert e2.value.status_code == 404 and code_of(e2) == "trade_not_found"


def test_void_sell_then_buy_and_audit(monkeypatch):
    db = _setup(monkeypatch)
    buy = run(R.add_trade(_trade(qty=10), email="a@b.c"))["trade"]
    sell = run(R.add_trade(_trade(side="sell", qty=10, trade_date=dt.date(2026, 10, 22)), email="a@b.c"))["trade"]
    run(R.void_trade(sell["id"], email="a@b.c"))
    run(R.void_trade(buy["id"], email="a@b.c"))
    assert all(r["voided_at"] for r in db.t["real_trades"])
    assert [a["event"] for a in db.t["audit_log"]][-2:] == ["real_trade_voided", "real_trade_voided"]
    assert run(R.list_trades(include_voided=False, limit=50, email="a@b.c"))["trades"] == []
    assert len(run(R.list_trades(include_voided=True, limit=50, email="a@b.c"))["trades"]) == 2


def test_users_only_see_their_own_data(monkeypatch):
    db = _setup(monkeypatch)
    run(R.add_trade(_trade(symbol="MU"), email="a@b.c"))
    run(R.add_trade(_trade(symbol="META"), email="x@y.z"))
    mine = run(R.list_trades(include_voided=False, limit=50, email="a@b.c"))["trades"]
    assert [t["symbol"] for t in mine] == ["MU"]
    assert run(R.get_account(email="nobody@x.y"))["account"] is None
    # ตารางปนผู้ใช้ (ข้อมูลเสีย) ต้องไม่ถูกส่งออก
    db.t["real_trades"].append({"id": 99, "email": "x@y.z", "symbol": "ZZ", "side": "buy", "qty": 1, "price": 1,
                                "fee": 0, "ts": "2026-10-01T16:00:00+00:00", "voided_at": None})
    real = db.sb
    async def leaky(method, table, params=None, **kw):
        out = await real(method, table, params=params, **kw)
        if method == "GET" and table == "real_trades":
            return out + [dict(db.t["real_trades"][-1])]
        return out
    monkeypatch.setattr(R, "sb", leaky)
    with pytest.raises(R.HTTPException) as e:
        run(R.list_trades(include_voided=False, limit=50, email="a@b.c"))
    assert e.value.status_code == 502


def test_cash_flows_validation_and_negative_cash_warning(monkeypatch):
    db = _setup(monkeypatch)
    for bad in (_flow(amount=0), _flow(amount=float("nan")), _flow(flow_date=dt.date(2009, 1, 1)),
                _flow(flow_date=dt.date.today() + dt.timedelta(days=3))):
        with pytest.raises(R.HTTPException) as e:
            run(R.add_flow(bad, email="a@b.c"))
        assert e.value.status_code == 400
    # ซื้อก่อนฝาก: อนุญาตแต่เตือนว่าเงินสดติดลบ
    out = run(R.add_trade(_trade(qty=10, price=100.0, trade_date=dt.date(2026, 10, 20)), email="a@b.c"))
    assert out["warnings"][0]["code"] == "negative_cash" and out["warnings"][0]["balance"] == -1000.0
    out = run(R.add_flow(_flow(flow_date=dt.date(2026, 10, 1), amount=5000.0), email="a@b.c"))
    assert out["warnings"] == []                                      # ฝากย้อนหลังแล้วเงินสดไม่ติดลบ
    w = run(R.void_flow(out["cash_flow"]["id"], email="a@b.c"))
    assert w["warnings"][0]["code"] == "negative_cash"                # ยกเลิกเงินฝากแล้วติดลบอีก
    with pytest.raises(R.HTTPException) as e:
        run(R.void_flow(out["cash_flow"]["id"], email="a@b.c"))       # ยกเลิกซ้ำ = ไม่พบ
    assert e.value.status_code == 404


def test_cash_balance_and_withdrawal(monkeypatch):
    trades = [{"id": 1, "symbol": "MU", "side": "buy", "qty": 10, "price": 100.0, "fee": 1.0, "ts": "2026-10-20T16:00:00+00:00"},
              {"id": 2, "symbol": "MU", "side": "sell", "qty": 4, "price": 110.0, "fee": 0.5, "ts": "2026-10-22T16:00:00+00:00"}]
    flows = [{"flow_date": "2026-10-01", "amount": 5000.0}, {"flow_date": "2026-10-25", "amount": -200.0}]
    bal, warn = R.cash_warnings(trades, flows)
    assert bal == pytest.approx(5000 - 1001 + 439.5 - 200) and warn == []


def test_summary_positions_cash_and_audit_failure_is_reported(monkeypatch):
    db = _setup(monkeypatch)
    db.fail_audit = True
    out = run(R.add_flow(_flow(), email="a@b.c"))
    assert out["ok"] and out["audit_written"] is False                # บันทึกสำเร็จ แต่แจ้งว่า audit พลาด
    db.fail_audit = False
    run(R.add_trade(_trade(symbol="MU", qty=10, price=100.0, fee=1.0), email="a@b.c"))
    run(R.add_trade(_trade(symbol="META", qty=2, price=500.0, trade_date=dt.date(2026, 10, 21)), email="a@b.c"))
    run(R.add_trade(_trade(symbol="MU", side="sell", qty=4, price=110.0, trade_date=dt.date(2026, 10, 22)), email="a@b.c"))

    async def no_split(rows):
        return R.L.to_trades(rows), []

    monkeypatch.setattr(R, "_adjusted", no_split)
    s = run(R.summary(email="a@b.c"))
    by = {p["symbol"]: p for p in s["positions"]}
    assert by["MU"]["qty"] == pytest.approx(6) and by["MU"]["avg_cost"] == pytest.approx(100.0)
    assert by["META"]["qty"] == pytest.approx(2)
    assert s["realized_gross"] == pytest.approx(40.0) and s["counts"] == {"trades": 3, "cash_flows": 1}
    assert s["cash_balance"] == pytest.approx(5000 - 1001 - 1000 + 440)


def test_broker_name_and_account_update(monkeypatch):
    db = _setup(monkeypatch)
    out = run(R.put_account(SimpleNamespace(broker="  Webull TH "), email="a@b.c"))
    assert out["account"]["broker"] == "Webull TH"
    with pytest.raises(R.HTTPException):
        run(R.put_account(SimpleNamespace(broker="x" * 41), email="a@b.c"))
    with pytest.raises(R.HTTPException):
        run(R.put_account(SimpleNamespace(broker="   "), email="a@b.c"))
    assert len(db.t["real_accounts"]) == 1
