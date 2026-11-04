"""เลือก engine ตาม spec: accumulate (DCA/dip) > strategy (กฎเข้า/ออก) > พอร์ตสัดส่วนคงที่"""
from __future__ import annotations

from .accumulate import run_accumulation
from .runner import run_backtest
from .strategy_runner import run_strategy


def run_any(spec: dict, bars: dict, bench: list, signal_bars=None, signal_bench=None, rates=None) -> dict:
    if spec.get("accumulate"):
        return run_accumulation(spec, bars, bench, signal_bars, signal_bench, rates)
    if spec.get("strategy"):
        return run_strategy(spec, bars, bench, signal_bars, signal_bench, rates)
    return run_backtest(spec, bars, bench, rates)
