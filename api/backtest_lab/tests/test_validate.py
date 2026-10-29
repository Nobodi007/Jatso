import pytest

from backtest_lab.data.validate import DataError, clean_bars
from backtest_lab.tests.helpers import mk_bars


def test_sorts_dedupes_and_drops_bad_rows():
    bars = mk_bars("2024-01-01", 5, lambda i: 100 + i)
    rows = [bars[3], bars[1], bars[1], {"date": "2024-01-20", "open": -1, "high": 1, "low": 1, "close": 1}, {"foo": 1}]
    out, issues = clean_bars("AAA", rows)
    assert [b["date"] for b in out] == sorted({b["date"] for b in out}) and len(out) == 2
    assert any(i["code"] == "dropped_rows" and i["count"] == 2 for i in issues)


def test_empty_raises():
    with pytest.raises(DataError) as e:
        clean_bars("AAA", [])
    assert e.value.code == "no_data"


def test_flags_unadjusted_split_and_gap():
    bars = mk_bars("2024-01-01", 20, lambda i: 400.0 if i < 10 else 100.0)     # 4:1 ที่ยังไม่ปรับ
    _, issues = clean_bars("AAA", bars)
    assert any(i["code"] == "possible_unadjusted_split" and i["ratio"] == 4.0 for i in issues)
    gap = mk_bars("2024-01-01", 3, lambda i: 100.0) + mk_bars("2024-03-01", 3, lambda i: 100.0)
    _, issues = clean_bars("AAA", gap)
    assert any(i["code"] == "gap" for i in issues)


def test_normal_prices_have_no_issues():
    bars = mk_bars("2024-01-01", 30, lambda i: 100 * 1.01 ** i)
    assert clean_bars("AAA", bars)[1] == []
