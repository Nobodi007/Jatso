import datetime as dt

from stocks import risk_api as A


def _cal(n=10):
    d, out = dt.date(2026, 10, 5), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _issue(sym="OLD", code="stale_price_beyond_limit"):
    return {"code": code, "symbol": sym, "first_date": "2026-10-12", "days": 3}


def test_no_data_vs_provider_error_are_told_apart():
    cal = _cal()
    out = A._diagnose_price_gaps([_issue("AAA", "missing_price"), _issue("BBB", "missing_price")],
                                 {}, cal, failed={"BBB"})
    by = {i["symbol"]: i for i in out}
    assert by["AAA"]["likely"] == "no_data" and by["AAA"]["last_close"] is None
    assert by["BBB"]["likely"] == "provider_error"


def test_history_that_stops_early_reports_last_close():
    cal = _cal()
    closes = {"OLD": {d: 10.0 for d in cal[:4]}}
    out = A._diagnose_price_gaps([_issue("OLD")], closes, cal, failed=set())[0]
    assert out["likely"] == "history_ends_early" and out["last_close"] == cal[3].isoformat()
    assert out["code"] == "stale_price_beyond_limit" and out["days"] == 3     # ฟิลด์เดิมคงอยู่


def test_gap_in_the_middle_is_not_called_a_delisting():
    cal = _cal()
    closes = {"GAP": {cal[0]: 5.0, cal[-1]: 6.0}}
    out = A._diagnose_price_gaps([_issue("GAP")], closes, cal, failed=set())[0]
    assert out["likely"] == "gap_in_history" and out["last_close"] == cal[-1].isoformat()


def test_zero_or_negative_prices_do_not_count_and_symbolless_issues_pass_through():
    cal = _cal()
    closes = {"BAD": {d: 0.0 for d in cal}}
    out = A._diagnose_price_gaps([_issue("BAD"), {"code": "other"}], closes, cal, failed=set())
    assert out[0]["likely"] == "no_data" and out[1] == {"code": "other"}
