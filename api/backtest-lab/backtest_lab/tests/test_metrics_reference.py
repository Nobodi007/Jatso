"""ค่าอ้างอิงของสูตรตัวชี้วัด — คัดลอกแนวทดสอบจาก tests/stocks/test_risk_engine.py (ไม่ import ของเดิม)"""
import math
from datetime import date, timedelta

import pytest

from backtest_lab.metrics import core as E

ap = lambda x, rel=1e-9: pytest.approx(x, rel=rel, abs=1e-12)
bench = lambda n=70: [0.01 * ((i % 7) - 3) for i in range(n)]


def test_cumulative_relative_cagr():
    assert E.cumulative_return([0.10, -0.05]) == ap(0.045)
    assert E.relative_wealth(0.20, 0.10) == ap(1.2 / 1.1 - 1)
    assert E.cagr(0.21, 730).value == ap(1.21 ** (365.25 / 730) - 1)
    m = E.cagr(0.05, 200)
    assert m.value is None and m.status == E.UNDEFINED


def test_volatility_known_and_insufficient():
    assert E.annualized_volatility([0.01, -0.01] * 10).value == ap(0.01 * math.sqrt(20 / 19) * math.sqrt(252))
    assert E.annualized_volatility([0.01] * 5).status == E.INSUFFICIENT


def test_beta_r2_exact():
    rb = bench(); out = E.beta_r2([2 * x for x in rb], rb)
    assert out["beta"].value == ap(2.0) and out["r_squared"].value == ap(1.0)


def test_beta_zero_benchmark_variance():
    assert E.beta_r2([0.01] * 70, [0.0] * 70)["beta"].status == E.UNDEFINED


def test_capm_alpha_beta_treynor():
    rb = bench(); out = E.capm_regression([0.0001 + 1.5 * x for x in rb], rb, [0.0] * 70)
    assert out["beta_capm"].value == ap(1.5)
    assert out["jensens_alpha"].value == ap(0.0252, rel=1e-6)
    assert out["treynor"].value == ap(0.0252 / 1.5, rel=1e-6)
    assert out["alpha_t_stat"].status == E.UNDEFINED


def test_sharpe_unavailable_and_zero_vol():
    assert E.sharpe_ratio([0.01] * 70, None).status == E.UNAVAILABLE
    assert E.sharpe_ratio([0.001] * 70, [0.0] * 70).status == E.UNDEFINED


def test_information_ratio_known():
    ir = E.information_ratio([0.002, 0.0] * 30, [0.0] * 60)
    assert ir.value == ap(math.sqrt(252 * 59 / 60))


def test_sortino_known():
    s = E.sortino_ratio([0.02, -0.01] * 30)
    assert s.value == ap(0.005 / math.sqrt(5e-5) * math.sqrt(252))


def test_capture_identity():
    rb = bench()
    assert E.capture_ratio(rb, rb, True).value == ap(1.0)
    assert E.capture_ratio(rb, rb, False).value == ap(1.0)


def test_drawdown_and_recovery():
    d = [date(2026, 1, 2) + timedelta(days=i) for i in range(4)]
    out = E.drawdown([0.10, -0.10, 1.21 / 0.99 - 1], d)
    assert out["max_drawdown"].value == ap(-0.10)
    ep = out["episode"]
    assert (ep["peak_date"], ep["trough_date"], ep["recovery_date"]) == (d[1], d[2], d[3])
    assert ep["recovery_trading_days"] == 1


def test_var_es_known():
    out = E.historical_var_es([(i - 50) / 1000 for i in range(100)])
    assert out["var"].value == ap(0.046) and out["es"].value == ap(0.048)
    assert out["var"].status == E.LIMITED
    assert E.historical_var_es([0.0] * 59)["var"].status == E.INSUFFICIENT


def test_misaligned_raises():
    with pytest.raises(ValueError):
        E.information_ratio([0.1] * 60, [0.1] * 59)


def test_monthly_compounding():
    d = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 2, 2)]
    b = {x["period"]: x["return"] for x in E.period_returns([0.1, 0.1, -0.5], d, "M")}
    assert b["2026-01"] == ap(0.21) and b["2026-02"] == ap(-0.5)
