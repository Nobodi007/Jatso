import base64
import gzip
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backtest_lab.data.price_store import (FileBackend, LayeredBackend, MemoryBackend, PriceStore, SupabaseBackend)
from backtest_lab.data.provider_base import ProviderError
from backtest_lab.tests.helpers import mk_bars

T0 = datetime(2024, 6, 3, 12, 0, tzinfo=timezone.utc)


class FakeProvider:
    name = "fake"

    def __init__(self, bars):
        self.bars, self.calls, self.fail = bars, [], False

    def get_bars(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if self.fail:
            raise ProviderError("down")
        return [b for b in self.bars if start.isoformat() <= b["date"] <= end.isoformat()]


class Clock:
    def __init__(self, t): self.t = t
    def __call__(self): return self.t


def store(bars, backend=None, ttl=3600):
    clk, prov = Clock(T0), FakeProvider(bars)
    return PriceStore(prov, backend or MemoryBackend(), ttl_seconds=ttl, now_fn=clk), prov, clk


BARS = mk_bars("2024-01-01", 120, lambda i: 100 + i)            # ถึงประมาณ 2024-06-14


def test_first_call_fetches_full_then_cache_hits_within_ttl():
    s, prov, clk = store([b for b in BARS if b["date"] <= "2024-05-31"])
    bars, meta = s.get_bars("AAA", date(2024, 2, 1), date(2024, 3, 1))
    assert len(prov.calls) == 1 and prov.calls[0][1] == date(1980, 1, 1)
    assert bars[0]["date"] >= "2024-02-01" and bars[-1]["date"] <= "2024-03-01" and meta["refreshed"] and not meta["stale"]
    s.get_bars("AAA", date(2024, 2, 1), date(2024, 3, 1))
    assert len(prov.calls) == 1                                  # ไม่ยิงซ้ำ


def test_incremental_refresh_after_ttl_appends_only_new_bars():
    s, prov, clk = store([b for b in BARS if b["date"] <= "2024-05-31"])
    s.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 1))
    prov.bars = BARS                                              # มีแท่งใหม่ (ถึง ~14 มิ.ย.)
    clk.t = datetime(2024, 6, 20, 12, 0, tzinfo=timezone.utc)      # เวลาผ่านไปแล้วจนมีแท่งใหม่ให้ดึง
    bars, meta = s.get_bars("AAA", date(2024, 1, 1), date(2024, 12, 31))
    assert len(prov.calls) == 2 and prov.calls[1][1] == date(2024, 5, 31) - timedelta(days=7)    # ดึงเฉพาะส่วนท้าย
    assert bars[-1]["date"] == BARS[-1]["date"] and len(bars) == len(BARS) and meta["refreshed"]


def test_overlap_mismatch_triggers_full_refetch_split_case():
    old = [b for b in BARS if b["date"] <= "2024-05-31"]
    s, prov, clk = store(old)
    s.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 1))
    # เกิด split 2:1 -> ผู้ให้บริการปรับราคาเก่าทั้งหมด
    prov.bars = [{**b, "open": b["open"] / 2, "high": b["high"] / 2, "low": b["low"] / 2, "close": b["close"] / 2} for b in BARS]
    clk.t = datetime(2024, 6, 20, 12, 0, tzinfo=timezone.utc)
    bars, _ = s.get_bars("AAA", date(2024, 1, 1), date(2024, 12, 31))
    assert prov.calls[-1][1] == date(1980, 1, 1)                  # ดึงเต็มใหม่
    assert bars[0]["close"] == pytest.approx(BARS[0]["close"] / 2)  # ราคาเก่าถูกปรับแล้ว ไม่ปะปนของเก่า


def test_refresh_failure_serves_stale_with_flag():
    s, prov, clk = store([b for b in BARS if b["date"] <= "2024-05-31"])
    s.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 1))
    clk.t = T0 + timedelta(hours=5); prov.fail = True
    bars, meta = s.get_bars("AAA", date(2024, 1, 1), date(2024, 6, 1))
    assert meta["stale"] and len(bars) > 0


def test_first_fetch_empty_or_failing_raises():
    s, prov, _ = store([])
    with pytest.raises(ProviderError):
        s.get_bars("DELISTED", date(2024, 1, 1), date(2024, 2, 1))
    s2, prov2, _ = store(BARS); prov2.fail = True
    with pytest.raises(ProviderError):
        s2.get_bars("AAA", date(2024, 1, 1), date(2024, 2, 1))


def test_file_backend_roundtrip(tmp_path):
    b = FileBackend(str(tmp_path))
    assert b.get("^GSPC") is None
    entry = {"symbol": "^GSPC", "bars": [1, 2]}
    b.put("^GSPC", entry)
    assert b.get("^GSPC") == entry
    s, prov, _ = store(BARS, backend=b)
    s.get_bars("AAA", date(2024, 1, 1), date(2024, 2, 1))
    s2 = PriceStore(prov, FileBackend(str(tmp_path)), now_fn=Clock(T0))      # instance ใหม่ ใช้ cache บนดิสก์
    n = len(prov.calls)
    s2.get_bars("AAA", date(2024, 1, 1), date(2024, 2, 1))
    assert len(prov.calls) == n


def test_supabase_backend_roundtrip_with_fake_request():
    table = {}

    def req(method, tbl, params=None, json_body=None, prefer=None):
        assert tbl == "bt_price_cache"
        if method == "POST":
            table[json_body["symbol"]] = json_body
            assert prefer == "resolution=merge-duplicates"
            return None
        sym = params["symbol"].removeprefix("eq.")
        return [table[sym]] if sym in table else []

    sb = SupabaseBackend(req)
    assert sb.get("AAA") is None
    s, prov, _ = store(BARS, backend=sb)
    s.get_bars("AAA", date(2024, 1, 1), date(2024, 2, 1))
    row = table["AAA"]
    assert {"symbol", "source", "first_date", "last_date", "fetched_at", "payload"} == set(row)
    assert json.loads(gzip.decompress(base64.b64decode(row["payload"])))["bars"][0]["date"] == BARS[0]["date"]
    s.get_bars("AAA", date(2024, 1, 1), date(2024, 2, 1))
    assert len(prov.calls) == 1


def test_layered_backend_reads_back_once():
    reads = []

    class Back(MemoryBackend):
        def get(self, symbol):
            reads.append(symbol)
            return super().get(symbol)

    back = Back(); back.put("AAA", {"x": 1})
    lb = LayeredBackend(MemoryBackend(), back)
    lb.get("AAA"); lb.get("AAA"); lb.get("AAA")
    assert reads.count("AAA") == 1                                # ลด egress: อ่านจาก backend ถาวรครั้งเดียว
