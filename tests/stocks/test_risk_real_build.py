"""_build ทั้งเส้นทาง: พอร์ตจริง (กรอกเอง + เงินฝาก/ถอน) และพอร์ตจำลอง (ต้องไม่เปลี่ยน)"""
import asyncio
import datetime as dt

import pytest
from stocks import ledger as L
from stocks import risk_api as API


def recent_days(n):
    d = dt.datetime.now(L.ET).date() - dt.timedelta(days=1)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return sorted(out)


def bars(days, closes):
    return [{"date": d.isoformat(), "close": c, "low": c * 0.98, "high": c * 1.02} for d, c in zip(days, closes)]


def patch_market(monkeypatch, days):
    n = len(days)
    spy = [4000 * (1.003 ** i) for i in range(n)]
    aaa = [100 * (1.01 ** i) * (1 + 0.004 * ((-1) ** i)) for i in range(n)]

    async def eod(sym, a, b):
        return bars(days, spy if sym == API.rd.BENCHMARK else aaa)

    async def rf(a, b):
        return {}

    async def splits(sym):
        return []

    monkeypatch.setattr(API.rd, "eod", eod)
    monkeypatch.setattr(API.rd, "risk_free", rf)
    monkeypatch.setattr(API.rd, "splits", splits)
    return aaa


def ts_of(d):
    return f"{d.isoformat()}T15:00:00+00:00"


def test_real_portfolio_end_to_end(monkeypatch):
    days = recent_days(45)
    aaa = patch_market(monkeypatch, days)
    d0, d1, d2 = days[3], days[3], days[20]
    rows = [{"id": 1, "symbol": "AAA", "side": "buy", "qty": 10.0, "price": aaa[3], "fee": 0.0, "ts": ts_of(d0)},
            {"id": 2, "symbol": "AAA", "side": "buy", "qty": 5.0, "price": aaa[20], "fee": 1.0, "ts": ts_of(d2)}]
    flows = [{"id": 1, "flow_date": d1.isoformat(), "amount": 1500.0},
             {"id": 2, "flow_date": d2.isoformat(), "amount": 800.0},
             {"id": 3, "flow_date": days[30].isoformat(), "amount": -300.0}]

    async def acc(email):
        return {"email": email}

    async def trs(email):
        return rows

    async def fls(email):
        return flows

    async def paper_acc(email):
        raise AssertionError("พอร์ตจริงห้ามอ่านบัญชีจำลอง")

    monkeypatch.setattr(API.rd, "real_account", acc)
    monkeypatch.setattr(API.rd, "real_trades", trs)
    monkeypatch.setattr(API.rd, "real_flows", fls)
    monkeypatch.setattr(API.rd, "account", paper_acc)

    rep = asyncio.run(API._build("a@b.c", "real"))
    meta = rep["meta"]
    assert meta["data_status"] in ("ok", "ok_with_warnings") and meta["portfolio"] == "real"
    assert meta["account_type"] == "real_portfolio_manual_entry"
    codes = {w.get("code") for w in meta["warnings"]}
    assert "cash_reconciliation_mismatch" not in codes and "no_capital_on_some_days" not in codes
    nav = rep["nav_series"]
    assert nav[0]["nav"] == 0.0 and nav[0]["date"] < d0.isoformat()          # ฐานก่อนเริ่ม NAV = 0
    by = {p["date"]: p for p in nav}
    assert by[d1.isoformat()]["flow"] == 1500.0 and by[days[30].isoformat()]["flow"] == -300.0
    # ผลตอบแทนพอร์ต = ผลตอบแทนถ่วงเวลาที่คำนวณจากสมุดบัญชีเอง ไม่ใช่ NAV_end/NAV_0
    pts = [L.NavPoint(dt.date.fromisoformat(p["date"]), p["nav"], p["cash"], None, (), p["flow"]) for p in nav]
    total = 1.0
    for x in L.returns_from_nav(pts):
        total *= 1 + x
    got = rep["analysis"]["performance"]["portfolio_return"]["value"]
    assert got == pytest.approx(total - 1, abs=1e-9)
    assert rep["attribution"]["sum_check"]["ok"] and rep["attribution"]["external_flows"] is True
    assert rep["pnl"]["check"]["ok"]                                          # realized+unrealized−ค่าธรรมเนียม = NAV − เงินทุนสุทธิ
    assert rep["exposure_ctx"]["holdings"]["AAA"]["qty"] == pytest.approx(15.0)


def test_real_portfolio_without_account_or_activity(monkeypatch):
    days = recent_days(30)
    patch_market(monkeypatch, days)

    async def none(email):
        return None

    monkeypatch.setattr(API.rd, "real_account", none)
    assert asyncio.run(API._build("a@b.c", "real"))["meta"]["data_status"] == "no_account"

    async def acc(email):
        return {"email": email}

    async def empty(email):
        return []

    async def only_deposit(email):
        return [{"id": 1, "flow_date": days[2].isoformat(), "amount": 1000.0}]

    monkeypatch.setattr(API.rd, "real_account", acc)
    monkeypatch.setattr(API.rd, "real_trades", empty)
    monkeypatch.setattr(API.rd, "real_flows", only_deposit)
    assert asyncio.run(API._build("a@b.c", "real"))["meta"]["data_status"] == "no_activity"


def test_real_portfolio_with_a_zero_capital_day_is_reported_not_crashed(monkeypatch):
    days = recent_days(30)
    patch_market(monkeypatch, days)

    async def flat(sym, a, b):                   # ราคานิ่ง 100 เพื่อให้ถอนหมดพอดี
        return bars(days, [4000.0 if sym == API.rd.BENCHMARK else 100.0] * len(days))

    monkeypatch.setattr(API.rd, "eod", flat)

    async def acc(email):
        return {"email": email}

    async def trs(email):
        return [{"id": 1, "symbol": "AAA", "side": "buy", "qty": 1.0, "price": 100.0, "fee": 0.0, "ts": ts_of(days[2])},
                {"id": 2, "symbol": "AAA", "side": "sell", "qty": 1.0, "price": 100.0, "fee": 0.0, "ts": ts_of(days[10])}]

    async def fls(email):                         # ฝาก 100 ซื้อ 1 หุ้น แล้ววันที่ 10 ขายและถอนหมด: ต้นวัน 11 ไม่มีทุน
        return [{"id": 1, "flow_date": days[2].isoformat(), "amount": 100.0},
                {"id": 2, "flow_date": days[10].isoformat(), "amount": -100.0}]

    monkeypatch.setattr(API.rd, "real_account", acc)
    monkeypatch.setattr(API.rd, "real_trades", trs)
    monkeypatch.setattr(API.rd, "real_flows", fls)
    rep = asyncio.run(API._build("a@b.c", "real"))
    assert rep["meta"]["data_status"] == "insufficient_data"
    assert "no_capital_on_some_days" in {w.get("code") for w in rep["meta"]["warnings"]}
    assert rep["nav_series"]                       # ยังคืนอนุกรม NAV ให้ดูได้ ไม่ล้มทั้งรายงาน


def test_paper_portfolio_path_is_unchanged(monkeypatch):
    days = recent_days(40)
    aaa = patch_market(monkeypatch, days)
    rows = [{"id": 1, "symbol": "AAA", "side": "buy", "qty": 10.0, "price": aaa[5], "fee": 1.0, "ts": ts_of(days[5])}]
    cash = 10000.0 - 10 * aaa[5] - 1.0

    async def acc(email):
        return {"email": email, "initial_cash": 10000.0, "cash": cash, "inception_at": ts_of(days[5])}

    async def trs(email):
        return rows

    async def real_boom(email):
        raise AssertionError("พอร์ตจำลองห้ามอ่านตารางพอร์ตจริง")

    monkeypatch.setattr(API.rd, "account", acc)
    monkeypatch.setattr(API.rd, "active_trades", trs)
    monkeypatch.setattr(API.rd, "real_account", real_boom)
    rep = asyncio.run(API._build("a@b.c"))
    assert rep["meta"]["portfolio"] == "paper" and rep["meta"]["account_type"] == "paper_trading"
    assert rep["meta"]["return_method"] == "daily time-weighted price return; split-adjusted; net of fees; excludes dividends"
    assert {w.get("code") for w in rep["meta"]["warnings"]} .isdisjoint({"cash_reconciliation_mismatch", "no_capital_on_some_days"})
    assert all(p["flow"] == 0.0 for p in rep["nav_series"]) and rep["attribution"]["external_flows"] is False
    assert rep["nav_series"][0]["nav"] == pytest.approx(10000.0)             # ฐาน = วันทำการก่อนเริ่ม NAV = เงินตั้งต้นเต็ม
    # บัญชีจำลองที่เงินสดไม่ตรงสมุดต้องยังเตือนเหมือนเดิม
    async def bad_acc(email):
        return {"email": email, "initial_cash": 10000.0, "cash": cash + 50.0, "inception_at": ts_of(days[5])}

    monkeypatch.setattr(API.rd, "account", bad_acc)
    rep2 = asyncio.run(API._build("a@b.c", "paper"))
    assert "cash_reconciliation_mismatch" in {w.get("code") for w in rep2["meta"]["warnings"]}


def test_invalid_portfolio_is_rejected():
    with pytest.raises(API.HTTPException) as e:
        asyncio.run(API._report("a@b.c", "other"))
    assert e.value.status_code == 400
