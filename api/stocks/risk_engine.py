"""
Jatso US Stock Risk Engine
==========================
Standalone, read-only analytics for US-equity portfolio return series.

This module does not connect to Supabase, call market-data providers, place orders,
or modify balances. Integrate it with the existing backend only after validating
the real stock_trades schema and the portfolio valuation/cash-flow logic.

Inputs:
  portfolio_returns: iterable of daily portfolio returns as decimals (0.01 = 1%)
  benchmark_returns: iterable of benchmark daily returns aligned to the same dates
  risk_free_daily: daily risk-free return as a decimal (default 0.0)

Missing-data policy:
  - Returns must be finite decimal values.
  - Portfolio and benchmark series must already be aligned by date.
  - Invalid or insufficient input raises ValueError instead of inventing data.

Annualization assumes 252 trading days.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence


TRADING_DAYS_PER_YEAR = 252


def _clean_returns(values: Iterable[float], name: str) -> list[float]:
    result: list[float] = []
    for i, value in enumerate(values):
        try:
            x = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}[{i}] is not numeric") from exc
        if not math.isfinite(x):
            raise ValueError(f"{name}[{i}] must be finite")
        if x <= -1.0:
            raise ValueError(f"{name}[{i}] must be greater than -1.0")
        result.append(x)
    return result


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _sample_std(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _covariance(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    if len(a) != len(b) or len(a) < 2:
        return None
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    return sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / (len(a) - 1)


def cumulative_return(returns: Iterable[float]) -> Optional[float]:
    """Geometrically compounded return: product(1+r_t)-1."""
    rs = _clean_returns(returns, "returns")
    if not rs:
        return None
    wealth = 1.0
    for r in rs:
        wealth *= 1.0 + r
    return wealth - 1.0


def annualized_volatility(returns: Iterable[float]) -> Optional[float]:
    """Sample standard deviation of daily returns times sqrt(252)."""
    rs = _clean_returns(returns, "returns")
    std = _sample_std(rs)
    return std * math.sqrt(TRADING_DAYS_PER_YEAR) if std is not None else None


def sharpe_ratio(
    returns: Iterable[float],
    risk_free_daily: float = 0.0,
) -> Optional[float]:
    """Annualized Sharpe using daily arithmetic excess returns."""
    rs = _clean_returns(returns, "returns")
    rf = float(risk_free_daily)
    if not math.isfinite(rf):
        raise ValueError("risk_free_daily must be finite")
    excess = [r - rf for r in rs]
    std = _sample_std(excess)
    mean = _mean(excess)
    if std is None or std == 0 or mean is None:
        return None
    return mean / std * math.sqrt(TRADING_DAYS_PER_YEAR)


def sortino_ratio(
    returns: Iterable[float],
    minimum_acceptable_daily_return: float = 0.0,
) -> Optional[float]:
    """Annualized Sortino; downside deviation uses all observations vs MAR."""
    rs = _clean_returns(returns, "returns")
    mar = float(minimum_acceptable_daily_return)
    if not math.isfinite(mar):
        raise ValueError("minimum_acceptable_daily_return must be finite")
    if not rs:
        return None
    downside_sq = [min(0.0, r - mar) ** 2 for r in rs]
    downside_deviation = math.sqrt(sum(downside_sq) / len(downside_sq))
    if downside_deviation == 0:
        return None
    return (_mean([r - mar for r in rs]) or 0.0) / downside_deviation * math.sqrt(
        TRADING_DAYS_PER_YEAR
    )


def beta_and_correlation(
    portfolio_returns: Iterable[float],
    benchmark_returns: Iterable[float],
) -> dict[str, Optional[float]]:
    """Beta = Cov(portfolio, benchmark) / Var(benchmark); correlation uses sample std."""
    p = _clean_returns(portfolio_returns, "portfolio_returns")
    b = _clean_returns(benchmark_returns, "benchmark_returns")
    if len(p) != len(b):
        raise ValueError("portfolio_returns and benchmark_returns must have equal length")
    cov = _covariance(p, b)
    var_b = _sample_std(b)
    var_b = var_b * var_b if var_b is not None else None
    std_p, std_b = _sample_std(p), _sample_std(b)
    corr = None
    if std_p not in (None, 0) and std_b not in (None, 0) and cov is not None:
        corr = cov / (std_p * std_b)
        # Guard tiny floating-point excursions beyond [-1, 1].
        corr = max(-1.0, min(1.0, corr))
    beta = cov / var_b if cov is not None and var_b not in (None, 0) else None
    return {"beta": beta, "correlation": corr}


def information_ratio(
    portfolio_returns: Iterable[float],
    benchmark_returns: Iterable[float],
) -> Optional[float]:
    """Annualized mean active daily return divided by sample tracking error."""
    p = _clean_returns(portfolio_returns, "portfolio_returns")
    b = _clean_returns(benchmark_returns, "benchmark_returns")
    if len(p) != len(b):
        raise ValueError("portfolio_returns and benchmark_returns must have equal length")
    if not p:
        return None
    active = [x - y for x, y in zip(p, b)]
    tracking_error_daily = _sample_std(active)
    mean_active = _mean(active)
    if tracking_error_daily in (None, 0) or mean_active is None:
        return None
    return mean_active / tracking_error_daily * math.sqrt(TRADING_DAYS_PER_YEAR)


def tracking_error(
    portfolio_returns: Iterable[float],
    benchmark_returns: Iterable[float],
) -> Optional[float]:
    """Annualized sample standard deviation of daily active returns."""
    p = _clean_returns(portfolio_returns, "portfolio_returns")
    b = _clean_returns(benchmark_returns, "benchmark_returns")
    if len(p) != len(b):
        raise ValueError("portfolio_returns and benchmark_returns must have equal length")
    active = [x - y for x, y in zip(p, b)]
    std = _sample_std(active)
    return std * math.sqrt(TRADING_DAYS_PER_YEAR) if std is not None else None


def drawdown_series(returns: Iterable[float]) -> list[float]:
    """Drawdown from the running peak of compounded wealth; starts from wealth=1."""
    rs = _clean_returns(returns, "returns")
    wealth = 1.0
    peak = 1.0
    result: list[float] = []
    for r in rs:
        wealth *= 1.0 + r
        peak = max(peak, wealth)
        result.append(wealth / peak - 1.0)
    return result


def max_drawdown(returns: Iterable[float]) -> Optional[float]:
    """Most negative drawdown, e.g. -0.25 means a 25% peak-to-trough loss."""
    dd = drawdown_series(returns)
    return min(dd) if dd else None


def historical_var_es(
    returns: Iterable[float],
    confidence: float = 0.95,
) -> dict[str, Optional[float]]:
    """
    Historical one-period VaR and Expected Shortfall, expressed as positive losses.
    VaR is the empirical loss quantile using linear interpolation.
    ES is the average loss at or beyond the VaR threshold.
    """
    rs = _clean_returns(returns, "returns")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if not rs:
        return {"var": None, "expected_shortfall": None}
    losses = sorted(-r for r in rs)
    position = (len(losses) - 1) * confidence
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    var = losses[lower] + (losses[upper] - losses[lower]) * (position - lower)
    tail = [loss for loss in losses if loss >= var]
    es = sum(tail) / len(tail) if tail else var
    return {"var": max(0.0, var), "expected_shortfall": max(0.0, es)}


def analyze_returns(
    portfolio_returns: Iterable[float],
    benchmark_returns: Optional[Iterable[float]] = None,
    risk_free_daily: float = 0.0,
) -> dict[str, object]:
    """
    Compute a compact risk summary from already aligned daily return series.
    Does not calculate TWR from trades; that requires validated cash-flow/valuation data.
    """
    p = _clean_returns(portfolio_returns, "portfolio_returns")
    result: dict[str, object] = {
        "observations": len(p),
        "cumulative_return": cumulative_return(p),
        "annualized_volatility": annualized_volatility(p),
        "sharpe_ratio": sharpe_ratio(p, risk_free_daily),
        "sortino_ratio": sortino_ratio(p, risk_free_daily),
        "max_drawdown": max_drawdown(p),
        "historical_var_95": historical_var_es(p, 0.95)["var"],
        "historical_expected_shortfall_95": historical_var_es(p, 0.95)["expected_shortfall"],
        "annualization_days": TRADING_DAYS_PER_YEAR,
        "return_basis": "daily_simple_returns",
        "benchmark": None,
    }
    if benchmark_returns is not None:
        b = _clean_returns(benchmark_returns, "benchmark_returns")
        if len(p) != len(b):
            raise ValueError("portfolio_returns and benchmark_returns must have equal length")
        result["benchmark"] = {
            "cumulative_return": cumulative_return(b),
            "annualized_volatility": annualized_volatility(b),
            **beta_and_correlation(p, b),
            "tracking_error": tracking_error(p, b),
            "information_ratio": information_ratio(p, b),
        }
    return result
