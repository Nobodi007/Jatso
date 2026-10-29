import pytest

from backtest_lab.engine.spec import SpecError, spec_hash, validate_spec

OK = {"start": "2020-01-02", "end": "2024-12-31", "initial_capital": 50000,
      "positions": [{"symbol": "aapl", "weight": 0.5}, {"symbol": "MSFT", "weight": 0.3}]}


def test_valid_normalizes_and_defaults():
    s = validate_spec(OK)
    assert [p["symbol"] for p in s["positions"]] == ["AAPL", "MSFT"]
    assert s["rebalance"]["mode"] == "none"
    assert s["costs"] == {"commission_bps": 0.0, "slippage_bps": 5.0}
    assert s["risk_free_annual"] is None


def bad(**kw):
    d = {**OK, **kw}
    with pytest.raises(SpecError):
        validate_spec(d)


def test_rejections():
    bad(positions=[])
    bad(positions=[{"symbol": "AAPL", "weight": 0.7}, {"symbol": "MSFT", "weight": 0.4}])    # รวม > 100%
    bad(positions=[{"symbol": "AAPL", "weight": 0.5}, {"symbol": "AAPL", "weight": 0.2}])    # ซ้ำ
    bad(positions=[{"symbol": "^GSPC", "weight": 0.5}])                                        # ดัชนีไม่ใช่หุ้น
    bad(positions=[{"symbol": "AAPL", "weight": float("nan")}])
    bad(positions=[{"symbol": "AAPL", "weight": True}])
    bad(positions=[{"symbol": "S%d" % i, "weight": 0.01} for i in range(31)])                  # เกิน 30 ตัว
    bad(start="2025-01-01", end="2024-01-01")
    bad(end="2999-01-01")
    bad(start="1950-01-01")
    bad(initial_capital=10)
    bad(rebalance={"mode": "calendar"})                                                         # ขาด frequency
    bad(rebalance={"mode": "threshold"})                                                        # ขาด threshold
    bad(rebalance={"mode": "weekly"})
    bad(costs={"slippage_bps": 99999})
    bad(unknown_field=1)
    bad(risk_free_annual=3)


def test_hash_stable_and_order_independent():
    a = validate_spec(OK)
    b = validate_spec({**OK, "positions": list(OK["positions"])})
    assert spec_hash(a) == spec_hash(b)
    assert spec_hash(a) != spec_hash(validate_spec({**OK, "initial_capital": 50001}))
