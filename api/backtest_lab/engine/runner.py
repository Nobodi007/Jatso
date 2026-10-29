"""Backtest Engine v1: พอร์ตสัดส่วนคงที่ + rebalance + ต้นทุน — ฟังก์ชันล้วน ไม่มี I/O

หลักการที่ล็อกไว้ (มี test)
- คำสั่งทุกรายการจับคู่ที่ "ราคาเปิด" ของวันทำการถัดจากวันที่ตัดสินใจ (ตัดสินใจจากราคาปิดวัน t -> ส่งที่เปิดวัน t+1)
- การซื้อเริ่มต้นเกิดที่ราคาเปิดวันทำการแรกที่ ≥ start; ผลตอบแทนวันแรกของพอร์ตและ S&P 500 จึงวัดจาก open->close ทั้งคู่
- baseline: (1) S&P 500 Price Index (2) Buy-and-Hold ของหุ้นชุดเดียวกัน น้ำหนักเริ่มต้นเท่ากัน ต้นทุนการซื้อเริ่มต้นเท่ากัน ไม่ปรับอีก
- ไม่มีดอกเบี้ยเงินสด, ไม่มีปันผล (Price Return), หุ้นเศษได้
- ถ้าหุ้นตัวใดมีข้อมูลเริ่มหลังวันเริ่ม: ปฏิเสธการรัน (ไม่กระจายน้ำหนักให้เงียบ ๆ)
"""
from __future__ import annotations

from datetime import date

from .. import config as C
from ..data.validate import DataError
from ..metrics import core as M
from ..metrics.extremes import best_worst_days, calendar_year_returns, worst_best_periods
from .execution import Account
from .rebalance import max_drift, should_rebalance

LABELS = ["hypothetical_backtest", "not_a_forecast", "price_return_only", "cash_earns_zero_interest"]


def _align(spec: dict, bars_by_symbol: dict, bench_bars: list[dict]):
    bench = {b["date"]: b for b in bench_bars}
    cal_all = sorted(bench)
    start, end = spec["start"], spec["end"]
    e0 = next((i for i, d in enumerate(cal_all) if d >= start), None)
    if e0 is None:
        raise DataError("benchmark_range", "ข้อมูล S&P 500 ไม่ครอบคลุมช่วงที่เลือก")
    if e0 == 0:
        raise DataError("benchmark_history", "ข้อมูล S&P 500 เริ่มต้นไม่เร็วพอก่อนวันเริ่ม (ต้องมีแท่งก่อนหน้าอย่างน้อย 1 วัน)")
    last = max((i for i, d in enumerate(cal_all) if d <= end), default=None)
    if last is None or last - e0 + 1 < C.MIN_TRADING_DAYS:
        raise DataError("too_short", f"ช่วงเวลาสั้นเกินไป (ต้องมีอย่างน้อย {C.MIN_TRADING_DAYS} วันทำการ)")
    cal = cal_all[e0:last + 1]
    base_date = cal_all[e0 - 1]

    opens: dict[str, list[float]] = {}
    closes: dict[str, list[float]] = {}
    filled: dict[str, int] = {}
    for p in spec["positions"]:
        sym = p["symbol"]
        bars = bars_by_symbol.get(sym) or []
        if not bars:
            raise DataError("no_data", f"{sym}: ไม่มีข้อมูลราคา")
        if bars[0]["date"] > cal[0]:
            raise DataError("late_start", f"{sym}: ข้อมูลเริ่มวันที่ {bars[0]['date']} ซึ่งหลังวันเริ่ม {cal[0]} "
                                          f"(เลือกวันเริ่มให้ไม่เร็วกว่านี้ หรือเอาหุ้นตัวนี้ออก)")
        bymap = {b["date"]: b for b in bars}
        prev_close = next((b["close"] for b in reversed(bars) if b["date"] < cal[0]), None)
        o, c, run, nfill = [], [], 0, 0
        for d in cal:
            b = bymap.get(d)
            if b is not None:
                o.append(b["open"]); c.append(b["close"]); prev_close, run = b["close"], 0
            else:
                if prev_close is None:
                    raise DataError("late_start", f"{sym}: ไม่มีราคาก่อนวันเริ่ม")
                run += 1; nfill += 1
                if run > C.MAX_FILL_DAYS:
                    raise DataError("data_gap", f"{sym}: ข้อมูลขาดหายต่อเนื่องเกิน {C.MAX_FILL_DAYS} วัน ณ {d}")
                o.append(prev_close); c.append(prev_close)
        opens[sym], closes[sym], filled[sym] = o, c, nfill
    return cal, base_date, bench, opens, closes, filled


def run_backtest(spec: dict, bars_by_symbol: dict[str, list[dict]], bench_bars: list[dict]) -> dict:
    cal, base_date, bench, opens, closes, filled = _align(spec, bars_by_symbol, bench_bars)
    N = len(cal)
    capital = spec["initial_capital"]
    targets = {p["symbol"]: p["weight"] for p in spec["positions"]}
    rb_cfg = spec["rebalance"]
    comm, slip = spec["costs"]["commission_bps"], spec["costs"]["slippage_bps"]

    acct, bh = Account(capital, comm, slip), Account(capital, comm, slip)
    for sym, w in targets.items():
        for a in (acct, bh):
            a.buy_outlay(sym, opens[sym][0], capital * w, cal[0], "initial")

    eq, bh_eq, invested = [], [], []
    rebalances: list[dict] = []
    pending: str | None = None
    for k in range(N):
        d = cal[k]
        if pending is not None:                                    # คำสั่งที่ตัดสินใจจากปิดวัน k-1 -> จับคู่ที่เปิดวัน k
            op = {s: opens[s][k] for s in targets}
            v_open = acct.value(op)
            deltas = {s: targets[s] * v_open - acct.shares.get(s, 0.0) * op[s] for s in targets}
            for s, dv in deltas.items():
                if dv < 0:
                    acct.sell_qty(s, op[s], -dv / op[s], d, "rebalance")
            need = {s: dv * (1 + slip / 1e4) * (1 + comm / 1e4) for s, dv in deltas.items() if dv > 0}
            tot = sum(need.values())
            scale = min(1.0, max(acct.cash, 0.0) / tot) if tot > 0 else 1.0
            for s, outlay in need.items():
                acct.buy_outlay(s, op[s], outlay * scale, d, "rebalance")
            rebalances.append({"date": d, "trigger": pending})
            pending = None

        cl = {s: closes[s][k] for s in targets}
        v = acct.value(cl)
        eq.append(v)
        bh_eq.append(bh.value(cl))
        invested.append((v - acct.cash) / v if v > 0 else 0.0)

        nxt = cal[k + 1] if k + 1 < N else None
        if nxt is not None:
            w_now = {s: acct.shares.get(s, 0.0) * cl[s] / v for s in targets}
            pending = should_rebalance(rb_cfg["mode"], rb_cfg["frequency"], rb_cfg["threshold_pct"],
                                       date.fromisoformat(d), date.fromisoformat(nxt), w_now, targets)

    # ----- ผลตอบแทนรายวัน (index 0 = วันแรก วัดจากเงินตั้งต้น/ราคาเปิด) -----
    def rets(vals, first_base):
        return [vals[0] / first_base - 1.0] + [vals[i] / vals[i - 1] - 1.0 for i in range(1, len(vals))]

    bclose = [bench[d]["close"] for d in cal]
    rp, rbh = rets(eq, capital), rets(bh_eq, capital)
    rb = rets(bclose, bench[cal[0]]["open"])
    dates = [date.fromisoformat(base_date)] + [date.fromisoformat(d) for d in cal]
    dates_r = dates[1:]
    rf = None
    if spec["risk_free_annual"] is not None:
        rf = [M.daily_rate(spec["risk_free_annual"])] * N

    an = M.analyze(rp, rb, rf, dates)
    an_bh = M.analyze(rbh, rb, rf, dates)
    an_b = M.analyze(rb, None, rf, dates)
    an.pop("series", None)

    def brief(a):
        return {"total_return": a["performance"]["portfolio_return"], "cagr": a["performance"]["cagr"],
                "volatility": a["performance"]["volatility"], "max_drawdown": a["tail"]["max_drawdown"],
                "sharpe": a["risk_adjusted"]["sharpe"], "sortino": a["risk_adjusted"]["sortino"],
                "calmar": a["risk_adjusted"]["calmar"]}

    bcum, w = [], 1.0
    for x in rb:                                             # ใช้ rb ชุดเดียวกับตัวชี้วัด (แหล่งความจริงเดียว)
        w *= 1.0 + x
        bcum.append(w - 1.0)
    series = [{"date": d, "portfolio": eq[i] / capital - 1.0, "buy_hold": bh_eq[i] / capital - 1.0,
               "benchmark": bcum[i]} for i, d in enumerate(cal)]

    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    mean_eq = sum(eq) / N
    trades = acct.trades
    stats = {
        "final_value": eq[-1], "buy_hold_final_value": bh_eq[-1], "initial_capital": capital,
        "trade_count": sum(1 for t in trades if t["reason"] != "initial"),
        "rebalance_count": len(rebalances),
        "commission_paid": acct.commission_paid, "slippage_cost": acct.slippage_cost,
        "total_cost": acct.commission_paid + acct.slippage_cost,
        "total_cost_pct_of_initial": (acct.commission_paid + acct.slippage_cost) / capital,
        "turnover_annual_one_way": (acct.traded_notional / 2.0) / mean_eq / years,
        "time_in_market": sum(invested) / N,
        "final_weights": {s: acct.shares.get(s, 0.0) * closes[s][-1] / eq[-1] for s in targets},
    }
    return {
        "period": {"base_date": base_date, "first_trade_date": cal[0], "last_date": cal[-1], "trading_days": N},
        "comparison": {"portfolio": brief(an), "buy_hold": brief(an_bh), "benchmark": brief(an_b)},
        "analysis": an, "analysis_buy_hold": {"performance": an_bh["performance"], "tail": {
            "max_drawdown": an_bh["tail"]["max_drawdown"]}},
        "series": series,
        "extremes": {"days": best_worst_days(rp, rb, dates_r), "weeks": worst_best_periods(rp, rb, dates_r, "W"),
                     "months": worst_best_periods(rp, rb, dates_r, "M")},
        "calendar_years": calendar_year_returns({"portfolio": rp, "buy_hold": rbh, "benchmark": rb}, dates_r),
        "trades": trades[:C.MAX_TRADES_IN_RESULT], "trades_truncated": len(trades) > C.MAX_TRADES_IN_RESULT,
        "rebalances": rebalances, "stats": stats,
        "data_quality": {"filled_days": filled},
        "labels": LABELS,
        "conventions": {
            "execution": "ตัดสินใจจากราคาปิดวัน t จับคู่ที่ราคาเปิดวัน t+1; ซื้อเริ่มต้นที่ราคาเปิดวันแรก",
            "costs": {"commission_bps": comm, "slippage_bps": slip,
                      "note": "ค่า default ของระบบ: commission 0 bps, slippage 5 bps (ผู้ใช้ปรับได้)"},
            "return_method": "Price Return (split-adjusted ไม่รวมปันผล) ทั้งพอร์ตและ S&P 500 Price Index (^GSPC)",
            "cash": "เงินสดไม่ได้ดอกเบี้ย", "fractional_shares": True,
            "turnover": "one-way รายปี = (Σ มูลค่าซื้อขายหลังซื้อเริ่มต้น / 2) / มูลค่าพอร์ตเฉลี่ย / จำนวนปี",
            "risk_free": "ใช้ค่าที่ผู้ใช้ระบุเท่านั้น (ถ้าไม่ระบุ Sharpe/Alpha จะเป็น unavailable)",
            "metrics_method": M.METHOD_VERSION, "trading_days_per_year": M.TRADING_DAYS},
    }
