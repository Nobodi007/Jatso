"""เงินฝาก/ถอนภายนอก (พอร์ตจริง): ผลตอบแทนถ่วงเวลา, attribution, P&L และต้องไม่กระทบพอร์ตจำลอง (ไม่มี flows)"""
import datetime as dt

import pytest
from stocks import ledger as L
from stocks import risk_alerts as RA
from stocks import risk_attribution as A
from stocks import risk_api as API


def cal(n, start=dt.date(2026, 10, 5)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def row(i, sym, side, qty, price, day, fee=0.0, hour="15"):
    return {"id": i, "symbol": sym, "side": side, "qty": qty, "price": price, "fee": fee,
            "ts": f"{day.isoformat()}T{hour}:00:00+00:00"}


def flow(i, day, amount):
    return {"id": i, "flow_date": day.isoformat(), "amount": amount}


def px_of(closes, c):
    return {s: [closes[s][d] for d in c] for s in closes}


# ------------------------------------------------------------------ พอร์ตจำลองต้องได้ตัวเลขเดิมเป๊ะ (golden จากโค้ดก่อนแก้)
def test_paper_results_unchanged_golden():
    c = cal(5)
    closes = {"AAA": dict(zip(c, [100.0, 103.0, 99.0, 104.0, 108.0])), "BBB": dict(zip(c, [50.0, 49.0, 52.0, 51.0, 55.0]))}
    rows = [row(1, "AAA", "buy", 10, 100.0, c[0], 1.0), row(2, "BBB", "buy", 20, 49.5, c[1]),
            row(3, "AAA", "sell", 4, 104.5, c[3], 1.0)]
    t = L.to_trades(rows)
    nav, _ = L.build_nav(t, 10000.0, c, closes)
    assert [p.nav for p in nav] == [9999.0, 10019.0, 10039.0, 10070.0, 10174.0]
    assert all(p.flow == 0.0 for p in nav)
    assert L.returns_from_nav(nav) == [0.0020002000200018966, 0.0019962072063079983,
                                      0.0030879569678254892, 0.010327706057596808]
    a = A.attribution(t, c, px_of(closes, c), nav)
    assert {r["symbol"]: r["contribution"] for r in a["positions"]} == {"BBB": 0.012001200120012002, "AAA": 0.006400640064006401}
    assert a["execution"]["value"] == -0.0008000800080008001 and a["fees"]["value"] == -0.00010001000100010001
    assert a["cash_drag"]["value"] == -0.10011528936595697 and a["portfolio_return"] == 0.017501750175017428
    assert a["external_flows"] is False and a["sum_check"]["ok"]


# ------------------------------------------------------------------ build_nav / returns
def test_deposit_is_not_counted_as_return():
    c = cal(4)
    closes = {"AAA": dict(zip(c, [100.0] * 4))}                              # ราคานิ่ง
    nav, _ = L.build_nav([], 1000.0, c, closes, flows=L.to_flows([flow(1, c[2], 500.0)]))
    assert [p.nav for p in nav] == [1000.0, 1000.0, 1500.0, 1500.0]
    assert [p.flow for p in nav] == [0.0, 0.0, 500.0, 0.0]
    assert L.returns_from_nav(nav) == [0.0, 0.0, 0.0]                        # ไม่ใช่ +50%


def test_withdrawal_and_weekend_flow_takes_effect_next_trading_day():
    c = cal(6)                                                               # จันทร์ 5 ต.ค. ... จันทร์ 12 ต.ค.
    sat = dt.date(2026, 10, 10)
    assert sat not in c
    nav, _ = L.build_nav([], 1000.0, c, {}, flows=L.to_flows([flow(1, sat, -400.0)]))
    by = {p.date: p for p in nav}
    assert by[dt.date(2026, 10, 9)].nav == 1000.0 and by[dt.date(2026, 10, 12)].flow == -400.0
    assert by[dt.date(2026, 10, 12)].nav == 600.0 and L.returns_from_nav(nav)[-1] == 0.0


def test_flows_on_or_before_base_day_are_part_of_the_opening_balance():
    c = cal(3)
    nav, _ = L.build_nav([], 0.0, c, {}, flows=L.to_flows([flow(1, c[0] - dt.timedelta(days=30), 700.0), flow(2, c[0], 300.0)]))
    assert nav[0].nav == 1000.0 and all(p.flow == 0.0 for p in nav)


def test_twr_with_a_mid_period_deposit_matches_hand_calculation():
    c = cal(5)
    closes = {"AAA": dict(zip(c, [100.0, 100.0, 110.0, 110.0, 121.0]))}
    rows = [row(1, "AAA", "buy", 10, 100.0, c[0]),                           # ซื้อ 10 หุ้นด้วยเงิน 1,000
            row(2, "AAA", "buy", 5, 110.0, c[2])]                            # ฝากเพิ่ม 550 ที่ต้นวัน c[2] แล้วซื้อที่ 110
    nav, _ = L.build_nav(L.to_trades(rows), 0.0, c, closes,
                         flows=L.to_flows([flow(1, c[0], 1000.0), flow(2, c[2], 550.0)]))
    r = L.returns_from_nav(nav)
    # c[0]=ฐาน NAV=1000 · c[1] 0% · c[2]: หุ้น 10 ตัว 100→110 และเงินฝาก 550 อยู่เป็นเงินสดทั้งวันแล้วซื้อ ณ ราคาปิด
    # NAV2 = 15×110 = 1650, ทุนที่ทำงานต้นวัน = 1000 + 550 → r2 = 1650/1550 − 1
    assert r[0] == 0.0 and r[1] == pytest.approx(1650 / 1550 - 1)
    # c[3] 0% · c[4] +10% (15 หุ้น)
    assert r[2] == 0.0 and r[3] == pytest.approx(0.10)
    # ผลตอบแทนสะสมต้องไม่รวมเงินฝาก: ต่างจากการนับ NAV ล้วน (1815/1000 − 1 = 81.5%) อย่างมาก
    total = 1.0
    for x in r:
        total *= 1 + x
    assert total - 1 == pytest.approx((1650 / 1550) * 1.10 - 1) and total - 1 < 0.2


def test_no_capital_day_raises_instead_of_dividing_by_zero():
    c = cal(4)
    nav, _ = L.build_nav([], 1000.0, c, {}, flows=L.to_flows([flow(1, c[1], -1000.0)]))
    assert nav[1].nav == 0.0
    with pytest.raises(L.LedgerError):
        L.returns_from_nav(nav[1:])                                         # ต้นวัน NAV = 0 และไม่มีเงินเข้า
    nav2, _ = L.build_nav([], 0.0, c, {}, flows=L.to_flows([flow(1, c[1], 100.0)]))
    assert L.returns_from_nav(nav2) == [0.0, 0.0, 0.0]                      # ฐาน NAV = 0 แต่ฝากเข้ามาต้นวัน = มีทุน


def test_to_flows_validation_and_order():
    out = L.to_flows([flow(2, dt.date(2026, 10, 6), 5.0), flow(1, dt.date(2026, 10, 6), -1.0), flow(3, dt.date(2026, 10, 1), 9.0)])
    assert [f.id for f in out] == [3, 1, 2]
    for bad in ({"id": 1, "flow_date": "2026-10-01", "amount": 0}, {"id": 1, "flow_date": "x", "amount": 1},
                {"id": 1, "flow_date": "2026-10-01", "amount": float("nan")}, {"flow_date": "2026-10-01", "amount": 1}):
        with pytest.raises(L.LedgerError):
            L.to_flows([bad])


# ------------------------------------------------------------------ attribution ต้องรวมได้ตรงแม้มีเงินเข้าออก
def _real_case():
    c = cal(8)
    closes = {"AAA": dict(zip(c, [100, 102, 101, 105, 103, 108, 107, 111.0])),
              "BBB": dict(zip(c, [40, 41, 39, 38, 42, 44, 43, 45.0]))}
    rows = [row(1, "AAA", "buy", 10, 100.0, c[0], 0.0), row(2, "BBB", "buy", 20, 40.5, c[1], 1.0),
            row(3, "AAA", "buy", 5, 104.0, c[3], 0.0), row(4, "BBB", "sell", 10, 41.0, c[5], 1.0)]
    flows = [flow(1, c[0], 2500.0), flow(2, c[3], 1000.0), flow(3, c[6], -600.0)]
    t = L.to_trades(rows)
    nav, _ = L.build_nav(t, 0.0, [dt.date(2026, 10, 2)] + c, closes, flows=L.to_flows(flows))   # ฐานก่อนเริ่ม NAV=0
    return c, closes, t, nav, flows


def test_attribution_sum_check_holds_with_deposits_and_withdrawals():
    c, closes, t, nav, flows = _real_case()
    cc = [dt.date(2026, 10, 2)] + c
    cl = {s: {**v, cc[0]: v[c[0]]} for s, v in closes.items()}
    px = {s: [cl[s][d] for d in cc] for s in cl}
    assert nav[0].nav == 0.0 and nav[1].flow == 2500.0
    a = A.attribution(t, cc, px, nav)
    assert a["external_flows"] is True and a["sum_check"]["ok"] and abs(a["sum_check"]["residual"]) < 1e-9
    r = L.returns_from_nav(nav)
    total = 1.0
    for x in r:
        total *= 1 + x
    assert a["portfolio_return"] == pytest.approx(total - 1, abs=1e-12)        # ผลตอบแทนถ่วงเวลา ไม่ใช่ NAV_end/NAV_0
    assert a["n_obs"] == len(cc) - 1 and a["cash_drag"]["memo"] is True


def test_pnl_breakdown_reconciles_with_net_deposits():
    c, closes, t, nav, flows = _real_case()
    prices = {s: closes[s][c[-1]] for s in closes}
    capital = sum(f["amount"] for f in flows)                                    # เงินตั้งต้น 0 + ฝาก/ถอนสุทธิ
    out = A.pnl_breakdown(L.positions(t), prices, capital, nav[-1].nav)
    assert out["check"]["ok"] and abs(out["check"]["difference"]) < 0.01
    # ถ้าไม่หักเงินฝาก (ใช้ 0) ต้องไม่ตรง: พิสูจน์ว่าเช็กนี้ไวต่อเงินฝากจริง
    assert not A.pnl_breakdown(L.positions(t), prices, 0.0, nav[-1].nav)["check"]["ok"]


# ------------------------------------------------------------------ alert ขาดทุนรายวันต้องไม่นับเงินฝาก
def test_daily_loss_ignores_deposits_and_withdrawals():
    series = [{"date": "2026-10-06", "nav": 1000.0, "flow": 0.0}, {"date": "2026-10-07", "nav": 1500.0, "flow": 500.0}]
    assert RA._last_daily_return(series)["value"] == pytest.approx(0.0)         # ไม่ใช่ +50%
    series[1] = {"date": "2026-10-07", "nav": 450.0, "flow": -500.0}
    assert RA._last_daily_return(series)["value"] == pytest.approx(-0.1)        # ถอน 500 แล้วขาดทุนจริง 10% ของทุน 500
    assert RA._last_daily_return([{"date": "a", "nav": 100.0}, {"date": "b", "nav": 97.0}])["value"] == pytest.approx(-0.03)  # ไม่มี flow = เดิม
    assert RA._last_daily_return([{"date": "a", "nav": 100.0}, {"date": "b", "nav": 50.0, "flow": -100.0}]) is None  # ทุน = 0


# ------------------------------------------------------------------ คีย์แคช
def test_report_cache_keys_keep_paper_key_and_separate_real():
    assert API.report_key("a@b.c") == "report:a@b.c" == API.report_key("a@b.c", "paper")   # stock_book ล้างแคชด้วยคีย์นี้
    assert API.report_key("a@b.c", "real") == "report:real:a@b.c"
