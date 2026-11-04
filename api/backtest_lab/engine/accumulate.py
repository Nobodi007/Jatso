"""โหมดทยอยสะสม: DCA (ซื้อตามรอบ) + Buy-the-dip (ซื้อเมื่อราคาลงจากสูงสุด N วัน) + เงื่อนไข indicator (when) — ฟังก์ชันล้วน ไม่มี I/O

โมเดลที่ล็อกไว้ (มี test)
- แต่ละหุ้นมี "ช่อง" ของตัวเอง เงินตั้งต้นช่อง = weight × เงินต้น เริ่มเป็นเงินสด (ลงทุนทันทีเท่า initial_invest_pct) แล้วทยอยซื้อ; ไม่มีการขาย
- เงินใหม่ (contribution) เข้าที่ราคาเปิดวันทำการแรกของงวด (ไม่รวมวันแรกของการทดสอบ) แบ่งเข้าช่องตามน้ำหนักเป้าหมายที่ปรับให้รวม 1
- สัญญาณทุกอย่างตัดสินจากราคาปิดวันก่อนหน้า จับคู่ที่ราคาเปิดวันนี้ (ไม่มี look-ahead); ตารางงวด (วันทำการแรกของสัปดาห์/เดือน/ไตรมาส) รู้ล่วงหน้าจากปฏิทินได้
- dip: ปิดวันก่อนหน้า ≤ สูงสุดของราคาปิด lookback_days วันทำการ (รวมวันนั้น) × (1 − drop_pct%) และห่างจากการซื้อ dip ครั้งก่อน ≥ cooldown_days
- when (ถ้ามี) ต้องจริงด้วยทั้ง schedule และ dip; ค่า NaN/ไม่ทราบ = ไม่ซื้อ
- เพดาน max_invested_per_stock = เงินซื้อสะสมต่อหุ้น (รวมค่าคอม) ซื้อได้เท่าที่เหลือในเพดาน
- เงินสดที่รอซื้อไม่มีดอกเบี้ย (ลดผลตอบแทนเทียบการลงทันที — ผลจริงของ DCA)
- ผลตอบแทนที่ใช้คำนวณตัวชี้วัด = ถ่วงเวลา (TWR): r_t = V_t / (V_{t−1} + เงินใหม่วัน t) − 1 ; ผลทางเงินจริงดูที่ profit / IRR
- baseline "ลงทันที": เงินต้นและเงินใหม่ทุกก้อนซื้อตามน้ำหนักเป้าหมายทันทีที่เงินเข้า ; benchmark: S&P 500 ด้วยกระแสเงินเดียวกัน
"""
from __future__ import annotations

from datetime import date

from .. import config as C
from ..metrics import attribution as ATT, core as M, exposure as EXP
from ..metrics.extremes import best_worst_days, calendar_year_returns, worst_best_periods
from . import rules
from .execution import Account
from .runner import LABELS, _align, resolve_rf


def period_key(d: date, freq: str):
    if freq == "weekly":
        y, w, _ = d.isocalendar()
        return (y, w)
    if freq == "monthly":
        return (d.year, d.month)
    return (d.year, (d.month - 1) // 3)


def is_period_start(cal: list[str], k: int, freq: str) -> bool:
    """วันทำการ k เป็นวันแรกของงวดหรือไม่ (วันแรกของการทดสอบถือเป็นต้นงวด — ใช้กับ schedule เท่านั้น)"""
    if k == 0:
        return True
    return period_key(date.fromisoformat(cal[k]), freq) != period_key(date.fromisoformat(cal[k - 1]), freq)


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """อัตราผลตอบแทนถ่วงเงิน (annualized, day-count 365.25) ; flows: เงินใส่ = ลบ, มูลค่าปลายทาง = บวก"""
    if not flows or not any(v < 0 for _, v in flows) or not any(v > 0 for _, v in flows):
        return None
    t0 = min(d for d, _ in flows)

    def f(r):
        return sum(v / (1.0 + r) ** ((d - t0).days / 365.25) for d, v in flows)
    lo, hi = -0.9999, 1.0
    while f(hi) > 0 and hi < 1e6:
        hi *= 2
    if f(lo) * f(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _signals(spec, bars_by_symbol, bench_bars, ext_dates):
    """{sym: (when_ok[j], dip_ok[j])} ; j = 0..N ตรงกับ ext_dates (0 = base_date) = ข้อมูลถึงปิดวัน ext_dates[j]"""
    acc = spec["accumulate"]
    dip = acc["dip"]
    out = {}
    for p in spec["positions"]:
        s = p["symbol"]
        bars = bars_by_symbol[s]
        idx, j = [], -1
        for d in ext_dates:
            while j + 1 < len(bars) and bars[j + 1]["date"] <= d:
                j += 1
            idx.append(j)
        if acc["when"] is not None:
            w = rules.evaluate(acc["when"], bars, bench_bars)
            when_ok = [i >= 0 and w[i] is True for i in idx]
        else:
            when_ok = [i >= 0 for i in idx]
        dip_ok = [False] * len(idx)
        if dip:
            L = dip["lookback_days"]
            cl = [b["close"] for b in bars]
            thr = 1.0 - dip["drop_pct"] / 100.0
            hh = [None] * len(cl)
            for i in range(L - 1, len(cl)):
                hh[i] = max(cl[i - L + 1:i + 1])
            dip_ok = [i >= 0 and hh[i] is not None and cl[i] <= hh[i] * thr for i in idx]
        out[s] = (when_ok, dip_ok)
    return out


def run_accumulation(spec: dict, bars_by_symbol: dict[str, list[dict]], bench_bars: list[dict],
                     signal_bars: dict[str, list[dict]] | None = None, signal_bench: list[dict] | None = None,
                     rates: dict | None = None) -> dict:
    cal, base_date, bench, opens, closes, filled = _align(spec, bars_by_symbol, bench_bars)
    N = len(cal)
    capital = spec["initial_capital"]
    acc = spec["accumulate"]
    comm, slip = spec["costs"]["commission_bps"], spec["costs"]["slippage_bps"]
    targets = {p["symbol"]: p["weight"] for p in spec["positions"]}
    syms = list(targets)
    wsum = sum(targets.values())
    wn = {s: targets[s] / wsum for s in syms}                    # น้ำหนักที่ปรับให้รวม 1 (ใช้แบ่งเงินใหม่/ยอด DCA)
    ext_dates = [base_date] + cal
    sig = _signals(spec, signal_bars or bars_by_symbol, signal_bench or bench_bars, ext_dates)

    sleeves = {s: Account(capital * targets[s], comm, slip) for s in syms}
    idle = capital * (1.0 - wsum)
    bh = Account(capital, comm, slip)                             # baseline: ลงทันที
    for s in syms:
        bh.buy_outlay(s, opens[s][0], capital * targets[s], cal[0], "initial")

    cap_usd = acc["max_invested_per_stock"]
    spent = {s: 0.0 for s in syms}
    last_dip = {s: -10 ** 9 for s in syms}
    counts = {"initial": 0, "schedule": 0, "dip": 0}
    blocked = {"no_cash": 0, "cap": 0}
    flows = [0.0] * N
    eq, bh_eq, invested = [], [], []

    def buy(s, k, want, reason):
        if want <= 0:
            return False
        room = cap_usd - spent[s] if cap_usd is not None else float("inf")
        if room < C.MIN_TRADE_NOTIONAL:
            blocked["cap"] += 1
            return False
        if sleeves[s].cash < C.MIN_TRADE_NOTIONAL:
            blocked["no_cash"] += 1
            return False
        amt = min(want, sleeves[s].cash, room)
        n0 = len(sleeves[s].trades)
        sleeves[s].buy_outlay(s, opens[s][k], amt, cal[k], reason)
        if len(sleeves[s].trades) == n0:
            return False
        t = sleeves[s].trades[-1]
        spent[s] += t["notional"] + t["commission"]
        counts[reason] += 1
        return True

    for k in range(N):
        d = cal[k]
        # 1) เงินใหม่เข้า (ที่เปิดวัน k)
        if acc["contribution"] and k > 0 and is_period_start(cal, k, acc["contribution"]["frequency"]):
            amt = acc["contribution"]["amount"]
            flows[k] = amt
            for s in syms:
                sleeves[s].cash += amt * wn[s]
            for s in syms:                                         # baseline ลงทันที ด้วยเงินก้อนเดียวกัน
                bh.cash += amt * wn[s]
                bh.buy_outlay(s, opens[s][k], amt * wn[s], d, "contribution")
        # 2) ซื้อ (สัญญาณจากปิดวัน k-1 = ดัชนี k ใน sig)
        for s in syms:
            when_ok, dip_ok = sig[s][0][k], sig[s][1][k]
            if k == 0 and acc["initial_invest_pct"] > 0:
                buy(s, k, sleeves[s].cash * acc["initial_invest_pct"] / 100.0, "initial")
            if acc["schedule"] and when_ok and is_period_start(cal, k, acc["schedule"]["frequency"]):
                buy(s, k, acc["schedule"]["amount"] * wn[s], "schedule")
            if acc["dip"] and when_ok and dip_ok and k - last_dip[s] >= acc["dip"]["cooldown_days"]:
                if buy(s, k, acc["dip"]["amount"], "dip"):
                    last_dip[s] = k
        # 3) มูลค่าปิดวัน
        cl = {s: closes[s][k] for s in syms}
        v = sum(sleeves[s].value(cl) for s in syms) + idle
        eq.append(v)
        bh_eq.append(bh.value(cl))
        invested.append(sum(sleeves[s].shares.get(s, 0.0) * cl[s] for s in syms) / v if v > 0 else 0.0)

    def twr(vals):
        out = [vals[0] / (capital + flows[0]) - 1.0]
        for i in range(1, len(vals)):
            out.append(vals[i] / (vals[i - 1] + flows[i]) - 1.0)
        return out

    bclose = [bench[d]["close"] for d in cal]
    rp, rbh = twr(eq), twr(bh_eq)
    rb = [bclose[0] / bench[cal[0]]["open"] - 1.0] + [bclose[i] / bclose[i - 1] - 1.0 for i in range(1, N)]
    dates = [date.fromisoformat(base_date)] + [date.fromisoformat(x) for x in cal]
    dates_r = dates[1:]
    rf, rf_info = resolve_rf(spec, rates, dates, N)
    an, an_bh, an_b = M.analyze(rp, rb, rf, dates), M.analyze(rbh, rb, rf, dates), M.analyze(rb, None, rf, dates)
    an.pop("series", None)

    def brief(a):
        return {"total_return": a["performance"]["portfolio_return"], "cagr": a["performance"]["cagr"],
                "volatility": a["performance"]["volatility"], "max_drawdown": a["tail"]["max_drawdown"],
                "sharpe": a["risk_adjusted"]["sharpe"], "sortino": a["risk_adjusted"]["sortino"],
                "calmar": a["risk_adjusted"]["calmar"]}

    # ----- กระแสเงินจริง / IRR / benchmark ด้วยกระแสเงินเดียวกัน -----
    total_contrib = sum(flows)
    total_in = capital + total_contrib
    cash_flows = [(date.fromisoformat(cal[0]), -capital)] + [(date.fromisoformat(cal[k]), -flows[k]) for k in range(N) if flows[k] > 0]
    units = capital / bench[cal[0]]["open"] + sum(flows[k] / bench[cal[k]]["open"] for k in range(N) if flows[k] > 0)
    bench_final = units * bclose[-1]
    span_days = (dates[-1] - date.fromisoformat(cal[0])).days
    end_d = date.fromisoformat(cal[-1])

    def mwr(final):
        return xirr(cash_flows + [(end_d, final)]) if span_days >= 365 else None

    cum, w_ = [], 1.0
    for x in rb:
        w_ *= 1.0 + x
        cum.append(w_ - 1.0)
    cp, ch, cinv, money = [], [], [], capital
    pw = hw = 1.0
    for i in range(N):
        pw *= 1.0 + rp[i]
        hw *= 1.0 + rbh[i]
        money += flows[i]
        cp.append(pw - 1.0)
        ch.append(hw - 1.0)
        cinv.append(money)
    series = [{"date": cal[i], "portfolio": cp[i], "buy_hold": ch[i], "benchmark": cum[i],
               "value": eq[i], "invested": cinv[i]} for i in range(N)]

    all_trades = [t for s in syms for t in sleeves[s].trades]
    order = {x: i for i, x in enumerate(cal)}
    all_trades.sort(key=lambda t: order[t["date"]])
    commission = sum(sleeves[s].commission_paid for s in syms)
    slippage = sum(sleeves[s].slippage_cost for s in syms)
    traded = sum(sleeves[s].traded_notional for s in syms)
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    mean_eq = sum(eq) / N
    final_w = {s: sleeves[s].shares.get(s, 0.0) * closes[s][-1] / eq[-1] for s in syms}

    attr = ATT.build(syms, all_trades, cal, closes, capital, eq, rp, flows)
    attr.pop("_daily_contrib")
    expo = EXP.build(targets, closes, {r["symbol"]: r["avg_weight"] for r in attr["positions"]},
                     {r["symbol"]: r["final_value"] for r in attr["positions"]})

    per_stock = []
    for s in syms:
        sh = sleeves[s].shares.get(s, 0.0)
        mv = sh * closes[s][-1]
        per_stock.append({"symbol": s, "invested": spent[s], "shares": sh, "avg_cost": (spent[s] / sh) if sh > 0 else None,
                          "market_value": mv, "return_on_cost": (mv / spent[s] - 1.0) if spent[s] > 0 else None,
                          "cash_left": sleeves[s].cash, "buys": sum(1 for t in sleeves[s].trades if t["side"] == "buy")})
    stats = {
        "final_value": eq[-1], "buy_hold_final_value": bh_eq[-1], "initial_capital": capital,
        "total_contributed": total_contrib, "total_invested": total_in,
        "profit": eq[-1] - total_in, "profit_pct_invested": (eq[-1] - total_in) / total_in,
        "buy_hold_profit": bh_eq[-1] - total_in, "benchmark_final_value": bench_final, "benchmark_profit": bench_final - total_in,
        "money_weighted_return": mwr(eq[-1]), "buy_hold_money_weighted_return": mwr(bh_eq[-1]),
        "benchmark_money_weighted_return": mwr(bench_final),
        "trade_count": len(all_trades), "rebalance_count": 0,
        "commission_paid": commission, "slippage_cost": slippage, "total_cost": commission + slippage,
        "total_cost_pct_of_initial": (commission + slippage) / total_in,
        "turnover_annual_one_way": (traded / 2.0) / mean_eq / years,
        "time_in_market": sum(invested) / N, "final_weights": final_w,
    }
    return {
        "attribution": attr, "exposure": expo, "mode": "accumulate",
        "period": {"base_date": base_date, "first_trade_date": cal[0], "last_date": cal[-1], "trading_days": N},
        "comparison": {"portfolio": brief(an), "buy_hold": brief(an_bh), "benchmark": brief(an_b)},
        "analysis": an, "analysis_buy_hold": {"performance": an_bh["performance"], "tail": {"max_drawdown": an_bh["tail"]["max_drawdown"]}},
        "series": series,
        "extremes": {"days": best_worst_days(rp, rb, dates_r), "weeks": worst_best_periods(rp, rb, dates_r, "W"),
                     "months": worst_best_periods(rp, rb, dates_r, "M")},
        "calendar_years": calendar_year_returns({"portfolio": rp, "buy_hold": rbh, "benchmark": rb}, dates_r),
        "trades": all_trades[:C.MAX_TRADES_IN_RESULT], "trades_truncated": len(all_trades) > C.MAX_TRADES_IN_RESULT,
        "rebalances": [], "stats": stats,
        "accumulate_result": {"buy_counts": counts, "blocked": blocked, "per_stock": per_stock,
                              "cash_left_total": sum(sleeves[s].cash for s in syms) + idle,
                              "contribution_events": sum(1 for x in flows if x > 0)},
        "data_quality": {"filled_days": filled}, "risk_free": rf_info,
        "labels": LABELS + ["accumulation_rules_chosen_with_hindsight_risk"],
        "conventions": {
            "execution": "สัญญาณจากราคาปิดวันก่อนหน้า จับคู่ที่ราคาเปิดวันนี้; งวด DCA = วันทำการแรกของสัปดาห์/เดือน/ไตรมาส; ไม่มีการขาย",
            "returns": "ตัวชี้วัดความเสี่ยง/ผลตอบแทน (Sharpe, drawdown, CAGR ฯลฯ) ใช้ผลตอบแทนถ่วงเวลา r_t = V_t/(V_{t−1}+เงินใหม่วัน t)−1 "
                       "ส่วนกำไรเป็นเงิน/IRR วัดจากกระแสเงินจริง (profit, money_weighted_return)",
            "baseline": "ลงทันที = เงินต้นและเงินใหม่ทุกก้อนซื้อตามน้ำหนักเป้าหมายทันทีที่เงินเข้า; benchmark = S&P 500 ด้วยกระแสเงินชุดเดียวกัน ซื้อที่ราคาเปิด (ไม่มีต้นทุน)",
            "dip": "ปิดวันก่อนหน้า ≤ สูงสุดของราคาปิด N วันทำการ × (1 − drop%) และห่างจาก dip ครั้งก่อน ≥ cooldown; ซื้อได้เท่าเงินสดในช่อง/เพดานที่เหลือ",
            "contribution": "เงินใหม่เข้าวันทำการแรกของงวด (ไม่รวมวันแรกของการทดสอบ) แบ่งเข้าช่องตามน้ำหนักเป้าหมายที่ปรับให้รวม 1",
            "costs": {"commission_bps": comm, "slippage_bps": slip,
                      "note": "ค่า default ของระบบ: commission 0 bps, slippage 5 bps (ผู้ใช้ปรับได้)"},
            "return_method": "Price Return (split-adjusted ไม่รวมปันผล) ทั้งพอร์ตและ S&P 500 Price Index (^GSPC)",
            "cash": "เงินสดที่รอซื้อไม่ได้ดอกเบี้ย", "fractional_shares": True,
            "turnover": "one-way รายปี = (Σ มูลค่าซื้อ / 2) / มูลค่าพอร์ตเฉลี่ย / จำนวนปี",
            "risk_free": ("อัตรา T-bill 3 เดือน (FMP) รายวัน ใช้ค่าของวันทำการก่อนหน้า (ไม่มี look-ahead)" if spec.get("risk_free_source") == "tbill" else "ใช้ค่าที่ผู้ใช้ระบุเท่านั้น (ถ้าไม่ระบุ Sharpe/Alpha จะเป็น unavailable)"),
            "metrics_method": M.METHOD_VERSION, "trading_days_per_year": M.TRADING_DAYS},
    }
