"""ทดสอบความนิ่งของผล: (1) แบ่งช่วงเวลา (2) ขยับพารามิเตอร์ — รันกฎเดิมซ้ำ ไม่ปรับกฎให้ดีขึ้น

ข้อจำกัดที่ต้องบอกผู้ใช้ (ใส่ในผลลัพธ์ด้วย)
- ถ้ากฎถูกเลือก/ปรับหลังเห็นผลของทั้งช่วงนี้แล้ว การแบ่งช่วงไม่ใช่ out-of-sample จริง; ใช้ดูว่าผลกระจุกอยู่ช่วงเดียวหรือไม่
- out-of-sample จริงต้องล็อกกฎก่อนดูข้อมูลช่วงทดสอบ (เช่น ตั้งกฎจากข้อมูลถึงปีหนึ่ง แล้วดูปีถัดไปที่ยังไม่เคยเห็น)
- แต่ละช่วงเริ่มใหม่จากเงินสด ณ วันเริ่มช่วง (ตัวชี้วัดใช้ประวัติก่อนหน้าได้ตามปกติ ไม่แอบดูอนาคต)
"""
from __future__ import annotations

import copy
import math
from statistics import median

from ..data.validate import DataError
from ..engine import indicators as I
from ..engine.runner import run_backtest
from ..engine.strategy_runner import run_strategy

PERIOD_PARAMS = ("period", "fast", "slow", "signal", "k", "d", "smooth")
FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5)
STOP_RANGES = {"stop_loss_pct": (0.1, 90.0), "take_profit_pct": (0.1, 1000.0), "trailing_stop_pct": (0.1, 90.0)}


def _run(spec: dict, bars: dict, bench: list) -> dict:
    return run_strategy(spec, bars, bench) if spec.get("strategy") else run_backtest(spec, bars, bench)


def _brief(res: dict) -> dict:
    c = res["comparison"]
    g = lambda k, m: c[k][m]["value"]
    return {k: {"total_return": g(k, "total_return"), "cagr": g(k, "cagr"), "max_drawdown": g(k, "max_drawdown")}
            for k in ("portfolio", "buy_hold", "benchmark")} | {"trade_count": res["stats"]["trade_count"],
                                                                "time_in_market": res["stats"]["time_in_market"]}


# ------------------------------------------------------------------ แบ่งช่วงเวลา
def split_windows(dates: list[str], k: int) -> list[tuple[str, str]]:
    n = len(dates)
    out = []
    for i in range(k):
        a, b = i * n // k, (i + 1) * n // k - 1
        if b > a:
            out.append((dates[a], dates[b]))
    return out


def window_test(spec: dict, bars: dict, bench: list, dates: list[str], k: int) -> dict:
    rows, skipped = [], []
    for a, b in split_windows(dates, k):
        sub = {**spec, "start": a, "end": b}
        try:
            r = _brief(_run(sub, bars, bench))
        except DataError as e:
            skipped.append({"start": a, "end": b, "reason": str(e)})
            continue
        rows.append({"start": a, "end": b, **r})
    tr = lambda r, k_: r[k_]["total_return"]
    used = [r for r in rows if all(tr(r, x) is not None for x in ("portfolio", "buy_hold", "benchmark"))]
    summary = {
        "windows": len(used),
        "positive": sum(1 for r in used if tr(r, "portfolio") > 0),
        "beat_benchmark": sum(1 for r in used if tr(r, "portfolio") > tr(r, "benchmark")),
        "beat_buy_hold": sum(1 for r in used if tr(r, "portfolio") > tr(r, "buy_hold")),
        "worst_return": min((tr(r, "portfolio") for r in used), default=None),
        "best_return": max((tr(r, "portfolio") for r in used), default=None),
    }
    return {"windows": rows, "skipped": skipped, "summary": summary}


# ------------------------------------------------------------------ ขยับพารามิเตอร์
def _scale_ind(o: dict, f: float) -> bool:
    d = I.REGISTRY[o["ind"]]
    p = dict(o["params"])
    for spec_p in d.params:
        if spec_p.name in PERIOD_PARAMS:
            v = int(round(p[spec_p.name] * f))
            p[spec_p.name] = int(min(max(v, spec_p.lo), spec_p.hi))
    if o["ind"] == "macd" and p["fast"] >= p["slow"]:
        p["slow"] = p["fast"] + 1
    if o["ind"] == "stoch" and p["smooth"] > p["k"]:
        p["smooth"] = p["k"]
    try:
        o["params"] = I.normalize_params(o["ind"], p)
    except ValueError:
        return False
    return True


def _walk(cond: dict):
    if "all" in cond or "any" in cond:
        for c in cond.get("all", cond.get("any")):
            yield from _walk(c)
    elif "not" in cond:
        yield from _walk(cond["not"])
    else:
        yield cond["left"]
        yield cond["right"]


def scaled_variant(spec: dict, family: str, f: float) -> dict | None:
    v = copy.deepcopy(spec)
    st = v["strategy"]
    if family == "indicators":
        found = False
        for c in (st["entry"], st["exit"]):
            if c is None:
                continue
            for o in _walk(c):
                if o["kind"] == "ind":
                    found = True
                    if not _scale_ind(o, f):
                        return None
        return v if found else None
    stops, found = st["stops"], False
    for k_, (lo, hi) in STOP_RANGES.items():
        if k_ in stops:
            found = True
            stops[k_] = float(min(max(stops[k_] * f, lo), hi))
    if "max_hold_days" in stops:
        found = True
        stops["max_hold_days"] = max(1, int(round(stops["max_hold_days"] * f)))
    return v if found else None


def sensitivity(spec: dict, bars: dict, bench: list, factors=FACTORS) -> dict:
    if not spec.get("strategy"):
        return {"available": False, "reason": "ไม่มีกลยุทธ์ (ไม่มีพารามิเตอร์ให้ขยับ)"}
    out: dict = {"available": True, "families": {}}
    for fam, label in (("indicators", "ช่วงเวลาของตัวชี้วัด"), ("stops", "ระดับ stop / ระยะถือ")):
        rows = []
        for f in factors:
            var = scaled_variant(spec, fam, f)
            if var is None:
                rows = []
                break
            try:
                b = _brief(_run(var, bars, bench))
            except DataError:
                continue
            rows.append({"factor": f, **b})
        if not rows:
            continue
        trs = [r["portfolio"]["total_return"] for r in rows if r["portfolio"]["total_return"] is not None]
        base = next((r for r in rows if r["factor"] == 1.0), None)
        neigh = [r["portfolio"]["total_return"] for r in rows if r["factor"] in (0.75, 1.25) and r["portfolio"]["total_return"] is not None]
        summ = {"min": min(trs), "max": max(trs), "median": median(trs),
                "beat_benchmark": sum(1 for r in rows if (r["portfolio"]["total_return"] or -9) > (r["benchmark"]["total_return"] or 9)),
                "variants": len(rows)} if trs else {}
        if base and neigh and base["portfolio"]["total_return"] is not None:
            b0 = base["portfolio"]["total_return"]
            drop = (b0 - sum(neigh) / len(neigh)) / max(abs(b0), 1e-9)
            summ["neighbor_drop"] = drop
            summ["fragile"] = bool(drop > 0.3)          # heuristic: ค่ารอบข้างต่ำกว่าฐานเกิน 30% -> ผลน่าจะเกาะอยู่ที่ค่าเดียว
        out["families"][fam] = {"label": label, "rows": rows, "summary": summ}
    if not out["families"]:
        return {"available": False, "reason": "ไม่มีพารามิเตอร์ที่ขยับได้"}
    out["note"] = ("fragile = ผลของพารามิเตอร์ข้างเคียง (×0.75, ×1.25) ต่ำกว่าค่าที่ใช้จริงเกิน 30% (เกณฑ์ประมาณการ ไม่ใช่การทดสอบทางสถิติ) "
                   "ผลที่ดีเฉพาะค่าเดียวมักเป็นสัญญาณ overfit")
    return out


def robustness(spec: dict, bars: dict, bench: list, dates: list[str], k: int, do_sens: bool) -> dict:
    return {
        "window_test": window_test(spec, bars, bench, dates, k),
        "sensitivity": sensitivity(spec, bars, bench) if do_sens else {"available": False, "reason": "ไม่ได้เลือกทดสอบ"},
        "caveats": [
            "ถ้ากฎถูกเลือกหลังเห็นผลของช่วงทั้งหมด การแบ่งช่วงไม่ใช่ out-of-sample จริง ใช้ดูว่าผลกระจุกอยู่ช่วงเดียวหรือไม่",
            "Out-of-sample จริง: ล็อกกฎจากข้อมูลช่วงแรก แล้วรันกับช่วงหลังที่ไม่เคยดูมาก่อน (ตั้งวันเริ่ม/สิ้นสุดของการรันใหม่)",
            "แต่ละช่วงเริ่มใหม่จากเงินสด ณ วันเริ่มช่วง ผลช่วงสั้นจึงผันผวนตามจังหวะเข้าซื้อ",
        ],
    }
