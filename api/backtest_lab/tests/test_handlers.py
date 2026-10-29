import asyncio
import time
from datetime import datetime, timedelta, timezone

from backtest_lab import config as C
from backtest_lab.api import handlers as H
from backtest_lab.data.price_store import MemoryBackend, PriceStore
from backtest_lab.data.provider_base import ProviderError
from backtest_lab.db.run_store import MemoryRunStore
from backtest_lab.jobs.limiter import RateLimiter
from backtest_lab.jobs.runner_pool import RunPool
from backtest_lab.service import reconcile
from backtest_lab.tests.helpers import mk_bars

BENCH = mk_bars("2023-12-01", 400, lambda i: 100 * 1.0004 ** i)
AAA = mk_bars("2023-12-01", 400, lambda i: 50 * 1.001 ** i)
SPEC = {"start": "2024-02-01", "end": "2025-02-28", "initial_capital": 100000,
        "positions": [{"symbol": "AAA", "weight": 0.8}], "costs": {"commission_bps": 0, "slippage_bps": 5}}


class Prov:
    name = "yahoo"

    def __init__(self, delay=0.0, fail=False):
        self.delay, self.fail, self.calls = delay, fail, 0

    def get_bars(self, symbol, start, end):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise ProviderError("down")
        src = BENCH if symbol == "^GSPC" else AAA if symbol == "AAA" else []
        return [b for b in src if start.isoformat() <= b["date"] <= end.isoformat()]


def services(prov=None, limit=6, timeout=30):
    prov = prov or Prov()
    return H.Services(MemoryRunStore(), PriceStore(prov, MemoryBackend()), RunPool(2, timeout), RateLimiter(limit, 600))


async def finish(s):
    await asyncio.gather(*list(s.tasks))


def test_happy_path_and_user_isolation():
    async def go():
        s = services()
        st, out = await H.create_run(s, "a@x.com", {"spec": SPEC})
        assert st == 202 and out["status"] == "queued"
        await finish(s)
        st, run = await H.get_run(s, "a@x.com", out["id"])
        assert st == 200 and run["status"] == "done" and "email" not in run
        res = run["result"]
        assert res["engine_version"] == C.ENGINE_VERSION and "hypothetical_backtest" in res["labels"]
        assert any(w["code"] == "survivorship_bias" for w in res["warnings"])
        assert {x["symbol"] for x in res["data_snapshot"]} == {"AAA", "^GSPC"}
        assert (await H.get_run(s, "b@x.com", out["id"]))[0] == 404               # คนอื่นอ่านไม่ได้
        assert (await H.delete_run(s, "b@x.com", out["id"]))[0] == 404
        assert (await H.list_runs(s, "b@x.com"))[1]["runs"] == []
        assert len((await H.list_runs(s, "a@x.com"))[1]["runs"]) == 1
        assert (await H.delete_run(s, "a@x.com", out["id"]))[0] == 200
    asyncio.run(go())


def test_validation_duplicate_and_rate_limit():
    async def go():
        s = services(Prov(delay=0.2), limit=2)
        assert (await H.create_run(s, "a@x.com", {}))[0] == 400
        assert (await H.create_run(s, "a@x.com", {"spec": {**SPEC, "positions": []}}))[0] == 400
        st1, o1 = await H.create_run(s, "a@x.com", {"spec": SPEC})
        st2, o2 = await H.create_run(s, "a@x.com", {"spec": SPEC})                  # spec เดียวกันที่ยังรันอยู่
        assert st1 == 202 and st2 == 200 and o2.get("duplicate") and o2["id"] == o1["id"]
        other = {**SPEC, "initial_capital": 200000}
        assert (await H.create_run(s, "a@x.com", {"spec": other}))[0] == 202
        third = {**SPEC, "initial_capital": 300000}
        assert (await H.create_run(s, "a@x.com", {"spec": third}))[0] == 429       # เกินโควตา 2 ครั้ง
        assert (await H.create_run(s, "b@x.com", {"spec": third}))[0] == 202        # ผู้ใช้อื่นไม่ถูกกระทบ
        await finish(s)
    asyncio.run(go())


def test_stored_run_cap():
    async def go():
        s = services()
        for _ in range(C.MAX_STORED_RUNS_PER_USER):
            s.run_store.create("a@x.com", {}, "h", "v")
        assert (await H.create_run(s, "a@x.com", {"spec": SPEC}))[0] == 409
    asyncio.run(go())


def test_provider_failure_and_unknown_symbol_become_clean_errors():
    async def go():
        s = services(Prov(fail=True))
        _, o = await H.create_run(s, "a@x.com", {"spec": SPEC}); await finish(s)
        run = (await H.get_run(s, "a@x.com", o["id"]))[1]
        assert run["status"] == "failed" and run["error"]["code"] == "provider_error"
        s2 = services()
        sp = {**SPEC, "positions": [{"symbol": "NOPE", "weight": 0.5}]}
        _, o = await H.create_run(s2, "a@x.com", {"spec": sp}); await finish(s2)
        run = (await H.get_run(s2, "a@x.com", o["id"]))[1]
        assert run["status"] == "failed" and run["error"]["code"] == "provider_error" and "NOPE" in run["error"]["message"]
    asyncio.run(go())


def test_timeout_marks_failed_and_late_result_cannot_overwrite():
    async def go():
        s = services(Prov(delay=0.4), timeout=0.1)
        _, o = await H.create_run(s, "a@x.com", {"spec": SPEC}); await finish(s)
        assert (await H.get_run(s, "a@x.com", o["id"]))[1]["error"]["code"] == "timeout"
        await asyncio.sleep(1.5)                                                     # thread เดิมคำนวณจบทีหลัง
        run = (await H.get_run(s, "a@x.com", o["id"]))[1]
        assert run["status"] == "failed" and run["result"] is None                   # ไม่ถูกเขียนทับด้วยผลเก่า
    asyncio.run(go())


def test_reconcile_closes_stuck_runs():
    st = MemoryRunStore()
    row = st.create("a@x.com", {}, "h", "v")
    later = datetime.now(timezone.utc) + timedelta(seconds=C.RUN_TIMEOUT_SECONDS + 300)
    out = reconcile(row, st, "a@x.com", now=later)
    assert out["status"] == "failed" and out["error"]["code"] == "interrupted"
    assert st.get("a@x.com", row["id"])["status"] == "failed"
    fresh = st.create("a@x.com", {}, "h2", "v")
    assert reconcile(fresh, st, "a@x.com")["status"] == "queued"


def test_meta_exposes_limits_and_disclaimer():
    st, m = H.meta()
    assert st == 200 and m["limits"]["max_symbols"] == C.MAX_SYMBOLS and "ไม่ใช่การพยากรณ์" in m["notice"]
