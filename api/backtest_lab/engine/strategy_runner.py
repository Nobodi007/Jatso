"""Strategy Engine (B2): กฎเข้า/ออกต่อหุ้น + stop + rebalance ระหว่างช่อง (sleeve) — ฟังก์ชันล้วน ไม่มี I/O

โมเดล
- แต่ละหุ้นในพอร์ตคือ "ช่อง" (sleeve) เงินตั้งต้น = weight × capital; ช่องอยู่ในสถานะ ถือหุ้นเต็มช่อง หรือ ถือเงินสด; ผลรวมน้ำหนัก <1 ส่วนที่เหลือเป็นเงินสดกลาง
- สัญญาณประเมินจาก "ราคาปิด" วัน t (ใช้ข้อมูลถึง t เท่านั้น) -> จับคู่ที่ "ราคาเปิด" วัน t+1 ; การตัดสินใจก่อนวันแรกใช้ปิดของ base_date
- stop (stop_loss / trailing / take_profit) ตรวจ intrabar จากราคา high/low ของวันนั้น: ราคาเปิดทะลุระดับ (gap) -> จับคู่ที่เปิด; ไม่งั้นจับคู่ที่ระดับ stop
  ถ้า stop-loss/trailing กับ take-profit เป็นไปได้ในแท่งเดียวกัน ถือว่า stop ถูกก่อน (สมมติแบบระมัดระวัง ไม่มีข้อมูลระดับนาทีให้รู้ลำดับจริง)
  trailing อิงจุดสูงสุด (high) จนถึงแท่ง "ก่อนหน้า" เท่านั้น แล้วค่อยอัปเดตหลังตรวจ
- หลังโดน stop จะไม่เข้าใหม่จนกว่าเงื่อนไข entry จะเป็นเท็จอย่างน้อย 1 แท่ง (กัน re-entry ทันทีบนสัญญาณเดิม)
- ถ้าไม่ระบุ exit: ออกเมื่อ entry เป็นเท็จ "ที่รู้ค่าแน่" (ไม่ใช่ NaN)
- rebalance (ถ้าเปิด) ปรับมูลค่าช่องกลับเข้าน้ำหนักเป้าหมาย โดยโอนเงินสดระหว่างช่องฟรี และซื้อ/ขายหุ้นเฉพาะช่องที่ถืออยู่
- Baseline: S&P 500 และ Buy-and-Hold ของหุ้น/น้ำหนักเดียวกัน (ซื้อที่เปิดวันแรก)
"""
from __future__ import annotations

from datetime import date

from .. import config as C
from ..metrics import core as M
from ..metrics.extremes import best_worst_days, calendar_year_returns, worst_best_periods
from . import rules
from .execution import Account
from .rebalance import should_rebalance
from .runner import LABELS, _align


class _Sleeve:
    def __init__(self, sym, weight, cash, comm, slip):
        self.sym, self.w = sym, weight
        self.acct = Account(cash, comm, slip)
        self.in_pos = False
        self.entry_px = self.hwm = 0.0
        self.hold = 0
        self.blocked = False
        self.pend = None                 # None | ("entry",) | ("exit", reason)
        self.trip = None
        self.entry_date = None


def _hl(bars, cal, closes_s):
    bymap = {b["date"]: b for b in bars}
    hi, lo = [], []
    for k, d in enumerate(cal):
        b = bymap.get(d)
        hi.append(b["high"] if b else closes_s[k])
        lo.append(b["low"] if b else closes_s[k])
    return hi, lo


def _signals(spec, bars_by_symbol, bench_bars, ext_dates):
    """คืน {sym: (entry_true[j], exit_true[j], entry_false_known[j])} สำหรับ j=0..N (0 = base_date)"""
    st = spec["strategy"]
    out = {}
    for p in spec["positions"]:
        s = p["symbol"]
        bars = bars_by_symbol[s]
        ent = rules.evaluate(st["entry"], bars, bench_bars)
        ex = rules.evaluate(st["exit"], bars, bench_bars) if st["exit"] else None
        idx, j = [], -1
        for d in ext_dates:
            while j + 1 < len(bars) and bars[j + 1]["date"] <= d:
                j += 1
            idx.append(j)
        e_true = [i >= 0 and ent[i] is True for i in idx]
        e_false = [i >= 0 and ent[i] is False for i in idx]
        if ex is None:
            x_true = e_false
        else:
            x_true = [i >= 0 and ex[i] is True for i in idx]
        out[s] = (e_true, x_true, [not v for v in e_true], bars[0]["date"] if bars else None)
    return out


def run_strategy(spec: dict, bars_by_symbol: dict[str, list[dict]], bench_bars: list[dict],
                 signal_bars: dict[str, list[dict]] | None = None, signal_bench: list[dict] | None = None) -> dict:
    """signal_bars/signal_bench: ราคาที่ใช้คำนวณตัวชี้วัด/กฎ (โหมด Total Return ใช้ราคาจริงไม่ปรับปันผล) — ไม่ระบุ = ใช้ชุดเดียวกับราคาซื้อขาย"""
    cal, base_date, bench, opens, closes, filled = _align(spec, bars_by_symbol, bench_bars)
    N = len(cal)
    capital = spec["initial_capital"]
    st = spec["strategy"]
    stops = st["stops"]
    comm, slip = spec["costs"]["commission_bps"], spec["costs"]["slippage_bps"]
    rb_cfg = spec["rebalance"]
    targets = {p["symbol"]: p["weight"] for p in spec["positions"]}
    syms = list(targets)

    ext_dates = [base_date] + cal
    sig = _signals(spec, signal_bars or bars_by_symbol, signal_bench or bench_bars, ext_dates)
    highs, lows = {}, {}
    for s in syms:
        highs[s], lows[s] = _hl(bars_by_symbol[s], cal, closes[s])

    sleeves = {s: _Sleeve(s, targets[s], capital * targets[s], comm, slip) for s in syms}
    idle = [capital * (1.0 - sum(targets.values()))]
    bh = Account(capital, comm, slip)
    for s in syms:
        bh.buy_outlay(s, opens[s][0], capital * targets[s], cal[0], "initial")

    trips: list[dict] = []
    rebalances: list[dict] = []
    reason_counts: dict[str, int] = {}

    def buy(sl, d, outlay, px, reason):
        n0 = len(sl.acct.trades)
        sl.acct.buy_outlay(sl.sym, px, outlay, d, reason)
        if len(sl.acct.trades) > n0 and sl.trip is not None:
            t = sl.acct.trades[-1]
            sl.trip["cash_in"] += t["notional"] + t["commission"]
            sl.trip["shares_bought"] += t["shares"]

    def sell(sl, d, qty, px, reason):
        n0 = len(sl.acct.trades)
        sl.acct.sell_qty(sl.sym, px, qty, d, reason)
        if len(sl.acct.trades) > n0 and sl.trip is not None:
            t = sl.acct.trades[-1]
            sl.trip["cash_out"] += t["notional"] - t["commission"]

    def open_trip(sl, d, k):
        sl.trip = {"symbol": sl.sym, "entry_date": d, "entry_price": None, "cash_in": 0.0, "cash_out": 0.0,
                   "shares_bought": 0.0, "bar_open": k}

    def close_trip(sl, d, k, reason):
        t = sl.trip
        sl.trip = None
        if t is None or t["cash_in"] <= 0:
            return
        t["exit_date"], t["exit_reason"], t["open"] = d, reason, False
        t["return"] = t["cash_out"] / t["cash_in"] - 1.0
        t["pnl"] = t["cash_out"] - t["cash_in"]
        t["holding_days"] = k - t.pop("bar_open") + 1
        t["exit_price"] = sl.acct.trades[-1]["price"]
        trips.append(t)
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    def flat_out(sl, d, k, px, reason):
        sell(sl, d, sl.acct.shares.get(sl.sym, 0.0), px, reason)
        sl.in_pos = False
        close_trip(sl, d, k, reason)
        if reason in ("stop_loss", "trailing_stop", "take_profit"):
            sl.blocked = True

    # ตัดสินใจก่อนวันแรกจากปิดของ base_date
    for s in syms:
        if sig[s][0][0]:
            sleeves[s].pend = ("entry",)

    eq, bh_eq, invested = [], [], []
    pending_rb: str | None = None
    for k in range(N):
        d = cal[k]
        # 1) จับคู่คำสั่งจากสัญญาณที่เปิดวัน k
        for s in syms:
            sl = sleeves[s]
            if sl.pend is None:
                continue
            p, sl.pend = sl.pend, None
            o = opens[s][k]
            if p[0] == "entry" and not sl.in_pos:
                open_trip(sl, d, k)
                buy(sl, d, sl.acct.cash, o, "entry")
                if sl.acct.shares.get(s, 0.0) > 0:
                    sl.in_pos, sl.entry_px, sl.hwm, sl.hold = True, o, o, 0
                    sl.trip["entry_price"] = sl.acct.trades[-1]["price"]
                else:
                    sl.trip = None
            elif p[0] == "exit" and sl.in_pos:
                flat_out(sl, d, k, o, p[1])
        # 2) rebalance ที่ตัดสินใจเมื่อวาน (หลังเข้า/ออก)
        if pending_rb is not None:
            _rebalance(sleeves, idle, {s: opens[s][k] for s in syms}, targets, d, slip, comm, buy, sell)
            rebalances.append({"date": d, "trigger": pending_rb})
            pending_rb = None
        # 3) stop intrabar
        for s in syms:
            sl = sleeves[s]
            if not sl.in_pos:
                continue
            o, h, l = opens[s][k], highs[s][k], lows[s][k]
            prot = []
            if "stop_loss_pct" in stops:
                prot.append((sl.entry_px * (1 - stops["stop_loss_pct"] / 100), "stop_loss"))
            if "trailing_stop_pct" in stops:
                prot.append((sl.hwm * (1 - stops["trailing_stop_pct"] / 100), "trailing_stop"))
            fill = None
            if prot:
                lvl, why = max(prot)
                if o <= lvl:
                    fill = (o, why)
                elif l <= lvl:
                    fill = (lvl, why)
            if fill is None and "take_profit_pct" in stops:
                tp = sl.entry_px * (1 + stops["take_profit_pct"] / 100)
                if o >= tp:
                    fill = (o, "take_profit")
                elif h >= tp:
                    fill = (tp, "take_profit")
            if fill is not None:
                flat_out(sl, d, k, fill[0], fill[1])
            else:
                sl.hwm = max(sl.hwm, h)
        # 4) มูลค่าปิดวัน
        cl = {s: closes[s][k] for s in syms}
        vals = {s: sleeves[s].acct.value(cl) for s in syms}
        v = sum(vals.values()) + idle[0]
        eq.append(v)
        bh_eq.append(bh.value(cl))
        invested.append(sum(sleeves[s].acct.shares.get(s, 0.0) * cl[s] for s in syms) / v if v > 0 else 0.0)
        # 5) สัญญาณหลังปิด -> คำสั่งสำหรับเปิดวัน k+1
        if k + 1 < N:
            j = k + 1
            for s in syms:
                sl = sleeves[s]
                e_true, x_true, e_not = sig[s][0], sig[s][1], sig[s][2]
                if sl.in_pos:
                    sl.hold += 1
                    if "max_hold_days" in stops and sl.hold >= stops["max_hold_days"]:
                        sl.pend = ("exit", "max_hold")
                    elif x_true[j]:
                        sl.pend = ("exit", "signal_exit")
                else:
                    if sl.blocked and e_not[j]:
                        sl.blocked = False
                    elif not sl.blocked and e_true[j]:
                        sl.pend = ("entry",)
            w_now = {s: vals[s] / v for s in syms} if v > 0 else dict(targets)
            pending_rb = should_rebalance(rb_cfg["mode"], rb_cfg["frequency"], rb_cfg["threshold_pct"],
                                          date.fromisoformat(d), date.fromisoformat(cal[k + 1]), w_now, targets)

    # ตำแหน่งที่ยังเปิดอยู่ ณ วันสุดท้าย (ไม่ขายเทียม)
    open_trips = []
    for s in syms:
        sl = sleeves[s]
        if sl.in_pos and sl.trip and sl.trip["cash_in"] > 0:
            t = sl.trip
            mv = sl.acct.shares.get(s, 0.0) * closes[s][-1]
            t.update({"exit_date": None, "exit_reason": "open_at_end", "open": True,
                      "return": (t["cash_out"] + mv) / t["cash_in"] - 1.0, "pnl": t["cash_out"] + mv - t["cash_in"],
                      "holding_days": N - t.pop("bar_open"), "exit_price": closes[s][-1]})
            open_trips.append(t)

    # ----- ผลตอบแทน/ตัวชี้วัด (สูตรเดียวกับ B1) -----
    def rets(vals_, first_base):
        return [vals_[0] / first_base - 1.0] + [vals_[i] / vals_[i - 1] - 1.0 for i in range(1, len(vals_))]

    bclose = [bench[d]["close"] for d in cal]
    rp, rbh = rets(eq, capital), rets(bh_eq, capital)
    rb = rets(bclose, bench[cal[0]]["open"])
    dates = [date.fromisoformat(base_date)] + [date.fromisoformat(d) for d in cal]
    dates_r = dates[1:]
    rf = [M.daily_rate(spec["risk_free_annual"])] * N if spec["risk_free_annual"] is not None else None
    an, an_bh, an_b = M.analyze(rp, rb, rf, dates), M.analyze(rbh, rb, rf, dates), M.analyze(rb, None, rf, dates)
    an.pop("series", None)

    def brief(a):
        return {"total_return": a["performance"]["portfolio_return"], "cagr": a["performance"]["cagr"],
                "volatility": a["performance"]["volatility"], "max_drawdown": a["tail"]["max_drawdown"],
                "sharpe": a["risk_adjusted"]["sharpe"], "sortino": a["risk_adjusted"]["sortino"],
                "calmar": a["risk_adjusted"]["calmar"]}

    bcum, w = [], 1.0
    for x in rb:
        w *= 1.0 + x
        bcum.append(w - 1.0)
    series = [{"date": d, "portfolio": eq[i] / capital - 1.0, "buy_hold": bh_eq[i] / capital - 1.0,
               "benchmark": bcum[i]} for i, d in enumerate(cal)]

    all_trades = [t for s in syms for t in sleeves[s].acct.trades]
    order = {d: i for i, d in enumerate(cal)}
    all_trades.sort(key=lambda t: order[t["date"]])
    commission = sum(sleeves[s].acct.commission_paid for s in syms)
    slippage = sum(sleeves[s].acct.slippage_cost for s in syms)
    traded = sum(sleeves[s].acct.traded_notional for s in syms)
    years = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    mean_eq = sum(eq) / N
    final_w = {s: sleeves[s].acct.shares.get(s, 0.0) * closes[s][-1] / eq[-1] for s in syms}

    all_trips = sorted(trips + open_trips, key=lambda t: t["entry_date"])
    stats = {
        "final_value": eq[-1], "buy_hold_final_value": bh_eq[-1], "initial_capital": capital,
        "trade_count": len(all_trades), "rebalance_count": len(rebalances),
        "commission_paid": commission, "slippage_cost": slippage, "total_cost": commission + slippage,
        "total_cost_pct_of_initial": (commission + slippage) / capital,
        "turnover_annual_one_way": (traded / 2.0) / mean_eq / years,
        "time_in_market": sum(invested) / N, "final_weights": final_w,
    }
    first_sig = {}
    for s in syms:
        e_true = sig[s][0]
        first_sig[s] = next((ext_dates[j] for j, v in enumerate(e_true) if v), None)
    return {
        "mode": "strategy",
        "period": {"base_date": base_date, "first_trade_date": cal[0], "last_date": cal[-1], "trading_days": N},
        "comparison": {"portfolio": brief(an), "buy_hold": brief(an_bh), "benchmark": brief(an_b)},
        "analysis": an, "analysis_buy_hold": {"performance": an_bh["performance"], "tail": {
            "max_drawdown": an_bh["tail"]["max_drawdown"]}},
        "series": series,
        "extremes": {"days": best_worst_days(rp, rb, dates_r), "weeks": worst_best_periods(rp, rb, dates_r, "W"),
                     "months": worst_best_periods(rp, rb, dates_r, "M")},
        "calendar_years": calendar_year_returns({"portfolio": rp, "buy_hold": rbh, "benchmark": rb}, dates_r),
        "trades": all_trades[:C.MAX_TRADES_IN_RESULT], "trades_truncated": len(all_trades) > C.MAX_TRADES_IN_RESULT,
        "rebalances": rebalances, "stats": stats,
        "strategy_result": {"trips": all_trips[:C.MAX_TRADES_IN_RESULT], "trip_stats": trip_stats(trips, open_trips),
                            "first_entry_signal": first_sig, "exit_reasons": reason_counts},
        "data_quality": {"filled_days": filled},
        "labels": LABELS + ["strategy_rules_chosen_with_hindsight_risk"],
        "conventions": {
            "execution": "สัญญาณจากราคาปิดวัน t จับคู่ที่ราคาเปิดวัน t+1; stop ตรวจ intrabar (gap -> ราคาเปิด, ไม่งั้น -> ระดับ stop); "
                         "stop-loss ถูกก่อน take-profit เมื่อเป็นไปได้ทั้งคู่ในแท่งเดียวกัน; หลังโดน stop ต้องรอ entry เป็นเท็จก่อนเข้าใหม่",
            "sleeves": "แต่ละหุ้นมีเงินช่องของตัวเอง (weight × เงินต้น) ถือหุ้นเต็มช่องหรือเงินสด; rebalance ปรับมูลค่าช่องเข้าน้ำหนักเป้าหมาย",
            "costs": {"commission_bps": comm, "slippage_bps": slip,
                      "note": "ค่า default ของระบบ: commission 0 bps, slippage 5 bps (ผู้ใช้ปรับได้)"},
            "return_method": "Price Return (split-adjusted ไม่รวมปันผล) ทั้งพอร์ตและ S&P 500 Price Index (^GSPC)",
            "cash": "เงินสดไม่ได้ดอกเบี้ย", "fractional_shares": True,
            "trip_return": "ผลตอบแทนต่อรอบ = เงินที่ได้คืนสุทธิ / เงินที่ลงสุทธิรวมค่าคอม (นับการเพิ่ม/ลดจาก rebalance ในรอบนั้น)",
            "turnover": "one-way รายปี = (Σ มูลค่าซื้อขาย / 2) / มูลค่าพอร์ตเฉลี่ย / จำนวนปี (นับการเข้าซื้อทุกครั้งของกลยุทธ์)",
            "risk_free": "ใช้ค่าที่ผู้ใช้ระบุเท่านั้น (ถ้าไม่ระบุ Sharpe/Alpha จะเป็น unavailable)",
            "metrics_method": M.METHOD_VERSION, "trading_days_per_year": M.TRADING_DAYS},
    }


def trip_stats(closed: list[dict], open_: list[dict]) -> dict:
    n = len(closed)
    out = {"closed_trades": n, "open_at_end": len(open_)}
    if n == 0:
        return out
    wins = [t for t in closed if t["pnl"] > 0]
    loss = [t for t in closed if t["pnl"] <= 0]
    gp, gl = sum(t["pnl"] for t in wins), -sum(t["pnl"] for t in loss)
    streak = best = 0
    for t in sorted(closed, key=lambda t: t["exit_date"]):
        streak = streak + 1 if t["pnl"] <= 0 else 0
        best = max(best, streak)
    out.update({
        "win_rate": len(wins) / n,
        "avg_win": sum(t["return"] for t in wins) / len(wins) if wins else None,
        "avg_loss": sum(t["return"] for t in loss) / len(loss) if loss else None,
        "profit_factor": gp / gl if gl > 0 else None,        # None = ไม่มีรอบขาดทุน (นิยามไม่ได้)
        "expectancy": sum(t["return"] for t in closed) / n,
        "avg_holding_days": sum(t["holding_days"] for t in closed) / n,
        "best_trade": max(t["return"] for t in closed), "worst_trade": min(t["return"] for t in closed),
        "max_consecutive_losses": best,
    })
    return out


def _rebalance(sleeves, idle, op, targets, d, slip, comm, buy, sell):
    syms = list(sleeves)
    V = sum(sleeves[s].acct.value(op) for s in syms) + idle[0]
    T = {s: targets[s] * V for s in syms}
    idle_t = (1.0 - sum(targets.values())) * V
    # ขายส่วนเกินในช่องที่ถือหุ้น
    for s in syms:
        sl = sleeves[s]
        sv = sl.acct.shares.get(s, 0.0) * op[s]
        if sl.in_pos and sv > T[s] + C.MIN_TRADE_NOTIONAL:
            sell(sl, d, (sv - T[s]) / op[s], op[s], "rebalance")
    sv = {s: sleeves[s].acct.shares.get(s, 0.0) * op[s] for s in syms}
    excess = {s: sleeves[s].acct.cash - (T[s] - sv[s]) for s in syms}
    ex_idle = idle[0] - idle_t
    pos = sum(x for x in list(excess.values()) + [ex_idle] if x > 0)
    neg = -sum(x for x in list(excess.values()) + [ex_idle] if x < 0)
    if pos > 0 and neg > 0:
        give, get = min(1.0, neg / pos), min(1.0, pos / neg)
        for s in syms:
            x = excess[s]
            sleeves[s].acct.cash -= x * give if x > 0 else x * get
        idle[0] -= ex_idle * give if ex_idle > 0 else ex_idle * get
    for s in syms:
        sl = sleeves[s]
        gap = T[s] - sv[s]
        if sl.in_pos and gap > C.MIN_TRADE_NOTIONAL and sl.acct.cash > C.MIN_TRADE_NOTIONAL:
            buy(sl, d, min(gap * (1 + slip / 1e4) * (1 + comm / 1e4), sl.acct.cash), op[s], "rebalance")
