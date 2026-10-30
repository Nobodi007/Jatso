import asyncio
from datetime import datetime, timedelta, timezone

from backtest_lab import config as C
from backtest_lab.api import handlers as H
from backtest_lab.db.run_store import MemoryRunStore
from backtest_lab.tests.test_handlers import SPEC, finish, services


def old(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_memory_store_deletes_only_own_finished_old_runs():
    st = MemoryRunStore()
    mk = lambda email, status, days: st.update(email, (r := st.create(email, {}, "h", "v"))["id"], {"status": status, "created_at": old(days)}) or r["id"]
    a_old_done, a_old_failed = mk("a@x.com", "done", 40), mk("a@x.com", "failed", 40)
    a_old_running, a_new_done = mk("a@x.com", "running", 40), mk("a@x.com", "done", 1)
    b_old_done = mk("b@x.com", "done", 40)
    n = st.delete_finished_before("a@x.com", old(C.RETENTION_DAYS))
    assert n == 2
    assert st.get("a@x.com", a_old_done) is None and st.get("a@x.com", a_old_failed) is None
    assert st.get("a@x.com", a_old_running) and st.get("a@x.com", a_new_done)          # กำลังรัน/ยังไม่หมดอายุ -> คงไว้
    assert st.get("b@x.com", b_old_done)                                                # ของคนอื่นไม่ถูกแตะ


def test_create_and_list_prune_and_free_the_quota():
    async def go():
        s = services()
        for i in range(C.MAX_STORED_RUNS_PER_USER):
            r = s.run_store.create("a@x.com", {}, f"h{i}", "v")
            s.run_store.update("a@x.com", r["id"], {"status": "done", "created_at": old(45)})
        keep = s.run_store.create("b@x.com", {}, "hb", "v")
        s.run_store.update("b@x.com", keep["id"], {"status": "done", "created_at": old(45)})
        st, out = await H.create_run(s, "a@x.com", {"spec": SPEC})              # เต็ม 50 แต่ทั้งหมดหมดอายุ -> ลบแล้วรันได้
        assert st == 202
        await finish(s)
        assert s.run_store.count("a@x.com") == 1
        assert s.run_store.get("b@x.com", keep["id"])                          # คนอื่นไม่ถูกลบ
        st, lst = await H.list_runs(s, "b@x.com")
        assert lst["runs"] == []                                               # เปิดประวัติก็ลบของตัวเองที่หมดอายุ
        assert H.meta()[1]["retention_days"] == C.RETENTION_DAYS
    asyncio.run(go())


def test_prune_failure_does_not_break_request():
    class Boom(MemoryRunStore):
        def delete_finished_before(self, email, cutoff_iso):
            raise RuntimeError("db down")

    async def go():
        s = services()
        s.run_store = Boom()
        st, _ = await H.create_run(s, "a@x.com", {"spec": SPEC})
        assert st == 202
        await finish(s)
    asyncio.run(go())
