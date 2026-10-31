import asyncio
import datetime as dt
from datetime import date

import pytest

from backtest_lab import config as C
from backtest_lab.api import handlers as H
from backtest_lab.data.price_store import MemoryBackend, PriceStore
from backtest_lab.data.total_return import synthetic_tr_benchmark, to_total_return
from backtest_lab.data.validate import DataError, clean_bars
from backtest_lab.db.run_store import MemoryRunStore
from backtest_lab.engine.runner import run_backtest
from backtest_lab.engine.spec import SpecError, spec_hash, validate_spec
from backtest_lab.engine.strategy_runner import run_strategy
from backtest_lab.jobs.limiter import RateLimiter
from backtest_lab.jobs.runner_pool import RunPool
from backtest_lab.tests.helpers import mk_bars, spec
from backtest_lab.tests.test_handlers import finish

G, GB = 1.0005, 1.0003             # อัตราโตรายวันของ adj_close (ปันผลจำลอง) และส่วนต่าง TR ของดัชนี
NB = 400


def with_adj(bars, growth):
    return [{**b, "adj_close": b["close"] * growth ** i} for i, b in enumerate(bars)]


# ------------------------------------------------------------------ transform
def test_to_total_return_scales_ohlc_by_adj_ratio():
    bars = [{"date": "2024-01-02", "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 5, "adj_close": 5.5}]
    out = to_total_return("X", bars)[0]
    assert out == {"date": "2024-01-02", "open": 5.0, "high": 6.0, "low": 4.5, "close": 5.5, "volume": 5}
    with pytest.raises(DataError) as e:
        to_total_return("X", [{"date": "d", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}])
    assert e.value.code == "no_adjclose"


def test_synthetic_tr_benchmark_close_to_close_is_tr_and_open_scaled_same_day():
    g = mk_bars("2024-01-01", 50, lambda i: (100 + i, 101 + i))
    tr = mk_bars("2024-01-01", 50, lambda i: 1000 * 1.001 ** i)           # open ไม่น่าเชื่อถือ ต้องไม่ถูกใช้
    out = synthetic_tr_benchmark(g, tr)
    assert [b["close"] for b in out] == [b["close"] for b in tr]
    for b, gb, t in zip(out, g, tr):
        r = t["close"] / gb["close"]
        assert b["open"] == pytest.approx(gb["open"] * r, rel=1e-12)
        assert b["close"] / b["open"] == pytest.approx(gb["close"] / gb["open"], rel=1e-12)     # ผลวันแรก o→c = การเคลื่อนไหวราคาจริง
    with pytest.raises(DataError) as e:
        synthetic_tr_benchmark(g, tr[:10])
    assert e.value.code == "benchmark_tr_unavailable"


def test_clean_bars_keeps_valid_adj_only():
    b = [{"date": "2024-01-02", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 1, "adj_close": 1.2},
         {"date": "2024-01-03", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 1, "adj_close": -3},
         {"date": "2024-01-04", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 1}]
    out, issues = clean_bars("X", b)
    assert [("adj_close" in x) for x in out] == [True, False, False] and not issues


# ------------------------------------------------------------------ spec
def test_spec_return_mode():
    base = {"start": "2024-02-01", "end": "2024-12-01", "initial_capital": 1000, "positions": [{"symbol": "AAA", "weight": 1}]}
    a = validate_spec(base)
    assert "return_mode" not in a and validate_spec({**base, "return_mode": "price"}) == a      # hash เดิมไม่เปลี่ยน
    t = validate_spec({**base, "return_mode": "total"})
    assert t["return_mode"] == "total" and spec_hash(t) != spec_hash(a)
    with pytest.raises(SpecError):
        validate_spec({**base, "return_mode": "dividends"})


# ------------------------------------------------------------------ signals ใช้ราคาจริง ไม่ใช่ราคาปรับปันผล
def test_signals_use_signal_bars_not_adjusted_execution_prices():
    raw = mk_bars("2023-12-28", 145, lambda i: 200)
    adj = [{**b, "open": b["open"] * 0.5, "high": b["high"] * 0.5, "low": b["low"] * 0.5, "close": b["close"] * 0.5} for b in raw]
    bench = mk_bars("2023-12-28", 145, lambda i: 100 * 1.0005 ** i)
    sp = spec([{"symbol": "AAA", "weight": 1.0}], "2024-01-02", "2024-06-28",
              strategy={"entry": {"op": ">", "left": {"price": "close"}, "right": {"value": 150}}})
    none = run_strategy(sp, {"AAA": adj}, bench)                                     # สัญญาณจากราคาปรับ (100 < 150) -> ไม่เข้า
    with_sig = run_strategy(sp, {"AAA": adj}, bench, signal_bars={"AAA": raw})       # สัญญาณจากราคาจริง (200 > 150) -> เข้า
    assert none["trades"] == [] and with_sig["trades"][0]["side"] == "buy"
    assert with_sig["trades"][0]["price"] == 100                                     # แต่ซื้อ/ขายที่ราคาปรับปันผล


# ------------------------------------------------------------------ price store
class DivProv:
    """ผู้ให้บริการปลอม: ราคาจริงนิ่ง, adj_close ปรับตามปันผลที่ 'เกิดขึ้นแล้ว'"""
    name = "yahoo"

    def __init__(self, with_adj_field=True):
        self.divs = 0
        self.calls = 0
        self.adj_field = with_adj_field
        self.bars = mk_bars("2024-01-01", 120, lambda i: 100)

    def get_bars(self, symbol, start, end):
        self.calls += 1
        out = []
        for i, b in enumerate(self.bars):
            if not (start.isoformat() <= b["date"] <= end.isoformat()):
                continue
            x = dict(b)
            if self.adj_field:
                x["adj_close"] = 100 * (0.99 ** self.divs)                   # ปันผลใหม่ (หลังวันที่ cache) ลดสเกล adj_close ของทุกแท่งในอดีต
            out.append(x)
        return out


def test_new_dividend_forces_full_refetch_and_rescales_history():
    prov = DivProv()
    clock = [date(2024, 6, 20)]
    now = lambda: dt.datetime(clock[0].year, clock[0].month, clock[0].day, 12, tzinfo=dt.timezone.utc)
    ps = PriceStore(prov, MemoryBackend(), ttl_seconds=-1, now_fn=now)
    bars, _ = ps.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 20), need_adj=True)
    assert bars[0]["adj_close"] == 100.0
    calls_before = prov.calls
    prov.divs = 1                                                    # มีปันผลใหม่ -> adj_close ของแท่งเก่าเปลี่ยน
    clock[0] = date(2024, 6, 21)
    bars, meta = ps.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 20), need_adj=True)
    assert prov.calls == calls_before + 2 and meta["refreshed"]       # refresh (พบว่าสเกลเปลี่ยน) + ดึงเต็มใหม่
    assert bars[0]["adj_close"] == pytest.approx(99.0)               # ประวัติเก่าไม่ค้างสเกลเดิม


def test_old_cache_without_adj_is_refetched_once_only_when_needed():
    prov = DivProv(with_adj_field=False)
    ps = PriceStore(prov, MemoryBackend(), ttl_seconds=10**9, now_fn=lambda: dt.datetime(2024, 6, 20, tzinfo=dt.timezone.utc))
    ps.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 20))
    n = prov.calls
    ps.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 20))           # โหมด price ไม่ดึงซ้ำ
    assert prov.calls == n
    prov.adj_field = True
    _, meta = ps.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 20), need_adj=True)
    assert prov.calls == n + 1 and meta["refreshed"]
    ps.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 20), need_adj=True)
    assert prov.calls == n + 1                                       # มี adj แล้วไม่ดึงอีก


# ------------------------------------------------------------------ end-to-end
GSPC = mk_bars("2023-12-01", NB, lambda i: (100 * 1.0004 ** i, 100 * 1.0004 ** i * 1.001))
SPTR = [{**b, "open": 1.0, "close": b["close"] * GB ** i} for i, b in enumerate(GSPC)]       # open ไม่น่าเชื่อถือโดยตั้งใจ
AAA = with_adj(mk_bars("2023-12-01", NB, lambda i: 50), G)                                    # ราคาจริงนิ่ง ผลตอบแทนทั้งหมดมาจากปันผล


class TrProv:
    name = "yahoo"

    def get_bars(self, symbol, start, end):
        src = {"^GSPC": GSPC, "^SP500TR": SPTR, "AAA": AAA}.get(symbol, [])
        return [b for b in src if start.isoformat() <= b["date"] <= end.isoformat()]


def services():
    return H.Services(MemoryRunStore(), PriceStore(TrProv(), MemoryBackend()), RunPool(2, 30), RateLimiter(50, 600))


SPEC = {"start": "2024-02-01", "end": "2025-02-28", "initial_capital": 100000, "positions": [{"symbol": "AAA", "weight": 1.0}],
        "costs": {"commission_bps": 0, "slippage_bps": 0}}


def run_spec(s, body):
    async def go():
        st, out = await H.create_run(s, "a@x.com", {"spec": body})
        assert st == 202, out
        await finish(s)
        st, run = await H.get_run(s, "a@x.com", out["id"])
        return run
    return asyncio.run(go())


def test_end_to_end_total_vs_price():
    s = services()
    price = run_spec(s, SPEC)["result"]
    total = run_spec(s, {**SPEC, "return_mode": "total"})["result"]
    assert price["comparison"]["portfolio"]["total_return"]["value"] == pytest.approx(0, abs=1e-12)     # ราคานิ่ง = ไม่มีผลตอบแทน
    first, last = total["period"]["first_trade_date"], total["period"]["last_date"]
    idx = {b["date"]: i for i, b in enumerate(AAA)}
    assert total["comparison"]["portfolio"]["total_return"]["value"] == pytest.approx(G ** (idx[last] - idx[first]) - 1, rel=1e-9)
    # benchmark: close-to-close = ดัชนี TR ; วันแรก o→c เท่าการเคลื่อนไหวของ ^GSPC ในวันนั้น
    gi = {b["date"]: i for i, b in enumerate(GSPC)}
    g0, gl = GSPC[gi[first]], gi[last]
    tr_last = SPTR[gl]["close"]
    r0 = SPTR[gi[first]]["close"] / g0["close"]
    assert total["comparison"]["benchmark"]["total_return"]["value"] == pytest.approx(tr_last / (g0["open"] * r0) - 1, rel=1e-9)
    assert "total_return_dividends_reinvested" in total["labels"] and "price_return_only" not in total["labels"]
    assert total["return_mode"] == "total" and "Total Return" in total["conventions"]["return_method"]
    codes = {w["code"] for w in total["warnings"]}
    assert "total_return_mode" in codes and "price_return_only" not in codes
    assert "price_return_only" in price["labels"] and "return_mode" not in price
    assert {x["symbol"] for x in total["data_snapshot"]} == {"AAA", "^GSPC", "^SP500TR"}


def test_total_mode_with_strategy_runs_and_missing_adj_is_clean_error():
    s = services()
    rule = {"entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 5}}}
    run = run_spec(s, {**SPEC, "return_mode": "total", "strategy": rule})
    assert run["status"] == "done" and run["result"]["mode"] == "strategy"

    class NoAdj(TrProv):
        def get_bars(self, symbol, start, end):
            return [{k: v for k, v in b.items() if k != "adj_close"} for b in super().get_bars(symbol, start, end)]
    s2 = H.Services(MemoryRunStore(), PriceStore(NoAdj(), MemoryBackend()), RunPool(2, 30), RateLimiter(50, 600))
    bad = run_spec(s2, {**SPEC, "return_mode": "total"})
    assert bad["status"] == "failed" and bad["error"]["code"] == "no_adjclose"
