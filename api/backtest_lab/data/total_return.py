"""โหมด Total Return (รวมปันผล)

วิธี
- หุ้น: ใช้ Adj Close ของ Yahoo (ปรับ split + ปันผล) สร้างราคา "ปรับปันผลย้อนหลัง" โดยคูณ open/high/low/close ด้วย f = adj_close/close ของวันนั้น
  => ผลตอบแทนรายวัน = (close_t + ปันผล_t)/close_{t-1} − 1 เท่ากับสมมติว่าปันผลถูกนำไปซื้อหุ้นเพิ่มทันทีที่ราคาปิดวัน ex-date
  ไม่รวมภาษีหัก ณ ที่จ่าย; ราคาที่ปรากฏในรายการซื้อขายเป็นราคาที่ปรับย้อนหลังแล้ว (ต่ำกว่าราคาที่เห็นจริงในอดีต)
- S&P 500: ใช้ ^SP500TR (Total Return Index) แต่ดัชนีนี้มี open ไม่น่าเชื่อถือ จึงสร้างแท่งสังเคราะห์:
  แท่งของ ^GSPC คูณด้วย r_t = TR_close_t / GSPC_close_t ของวันเดียวกัน -> ผลตอบแทนปิด-ปิดเท่า TR จริง และผลวันแรก (เปิด→ปิด) เท่าการเคลื่อนไหวของราคาในวันนั้น
- สัญญาณของกลยุทธ์ยังคำนวณจากราคาจริงที่ไม่ปรับปันผล (สิ่งที่ผู้ซื้อขายเห็นในตอนนั้น) ดู Market.signal_*
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .. import config as C
from .price_store import PriceStore
from .validate import DataError, clean_bars


def to_total_return(symbol: str, bars: list[dict]) -> list[dict]:
    if any("adj_close" not in b for b in bars):
        raise DataError("no_adjclose", f"{symbol}: แหล่งข้อมูลไม่ส่ง Adj Close ครบทุกวัน จึงคำนวณ Total Return ไม่ได้")
    out = []
    for b in bars:
        f = b["adj_close"] / b["close"]
        out.append({"date": b["date"], "open": b["open"] * f, "high": b["high"] * f, "low": b["low"] * f,
                    "close": b["adj_close"], "volume": b["volume"]})
    return out


def synthetic_tr_benchmark(gspc: list[dict], sptr: list[dict]) -> list[dict]:
    tr = {b["date"]: b["close"] for b in sptr}
    out = []
    for b in gspc:
        t = tr.get(b["date"])
        if t is None:
            continue
        r = t / b["close"]
        out.append({"date": b["date"], "open": b["open"] * r, "high": b["high"] * r, "low": b["low"] * r,
                    "close": t, "volume": b["volume"]})
    if not out or len(out) < 0.9 * len(gspc):
        raise DataError("benchmark_tr_unavailable",
                        "ไม่มีข้อมูล S&P 500 Total Return (^SP500TR) ครอบคลุมช่วงที่เลือก (ข้อมูลเริ่มประมาณปี 1988) "
                        "ลองเริ่มทดสอบให้หลังกว่านี้ หรือใช้โหมด Price Return")
    return out


@dataclass
class Market:
    bars: dict                       # ราคาที่ใช้ซื้อ/ขายและมูลค่า (โหมด total = ปรับปันผลแล้ว)
    bench: list                      # ราคา benchmark ที่ใช้เทียบผลตอบแทน
    snapshot: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    signal_bars: dict | None = None  # ราคาจริงไม่ปรับปันผลสำหรับตัวชี้วัด/กฎ (None = ใช้ bars)
    signal_bench: list | None = None


def load_market(spec: dict, price_store: PriceStore, fetch_from: date, end: date) -> Market:
    total = spec.get("return_mode") == "total"
    names = [p["symbol"] for p in spec["positions"]]
    raw, snapshot, issues = {}, [], []
    for sym in names + [C.BENCHMARK] + ([C.BENCHMARK_TR] if total else []):
        got, meta = price_store.get_bars(sym, fetch_from, end, need_adj=total and sym in names)
        cleaned, iss = clean_bars(sym, got)
        raw[sym] = cleaned
        issues.extend(iss)
        snapshot.append({**meta, "bars_used": len(cleaned)})
    gspc = raw.pop(C.BENCHMARK)
    if not total:
        return Market(raw, gspc, snapshot, issues)
    sptr = raw.pop(C.BENCHMARK_TR)
    adj = {s: to_total_return(s, b) for s, b in raw.items()}
    return Market(adj, synthetic_tr_benchmark(gspc, sptr), snapshot, issues, signal_bars=raw, signal_bench=gspc)
