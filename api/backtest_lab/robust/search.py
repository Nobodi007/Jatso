"""ค้นหาพารามิเตอร์แบบไม่หลอกตัวเอง: Parameter Sweep (heatmap) และ Walk-forward

หลักคิด (ต้องบอกผู้ใช้ตรงๆ)
- การปรับพารามิเตอร์ให้ผลย้อนหลังดีที่สุด "ไม่ใช่การหา edge" — ลองหลายชุดย่อมมีชุดที่ดูดีโดยบังเอิญ (winner's curse)
- Sweep ใช้ดูว่าผลดี "ทั้งพื้นที่" (plateau) หรือ "จุดเดียวโดดเด่น" (spike = น่าจะ overfit) ไม่ได้ใช้เลือกค่าที่ดีที่สุดไปเชื่อ
- Walk-forward คือตัวที่ให้ผล out-of-sample จริง: เลือกค่าจากช่วงฝึกเท่านั้น แล้วใช้กับช่วงถัดไปที่ไม่เคยเห็น รายงานเฉพาะผลช่วงทดสอบ
- ทุกการรันใช้ engine ตัวเดิมของ Backtest Lab (ไม่มีตรรกะซื้อขายซ้ำซ้อนที่นี่)
- ไม่แก้ spec เดิม; ตัวแปรที่ขยับต้องมาจากรายการ tunables ที่ระบบสร้างจาก spec (whitelist) เท่านั้น
"""
from __future__ import annotations

import copy
import itertools
import math
from datetime import date
from typing import Callable

from ..data.validate import DataError
from ..engine import indicators as I
from ..engine.rules import MAX_HOLD_DAYS
from .stability import STOP_RANGES, _run, split_windows

METRICS = ("calmar", "cagr", "total_return", "sortino")
METRIC_LABEL = {"calmar": "Calmar (CAGR ÷ |Max DD|)", "cagr": "CAGR", "total_return": "ผลตอบแทนรวม", "sortino": "Sortino"}
MAX_PARAMS = 2
MAX_VALUES = 9
MAX_CELLS = 49                    # ขอบเขตจำนวนการรันต่อ sweep (7×7)
MAX_WF_RUNS = 160                 # ขอบเขตรวมของ walk-forward = folds × (เซลล์ + 2)
MIN_FOLD_DAYS = 60                # วันทำการขั้นต่ำต่อบล็อก
MIN_ANNUAL_DAYS = 370             # ช่วงที่คำนวณ CAGR/Calmar ได้ (ระบบหลักไม่ annualize ถ้าสั้นกว่า 1 ปี)
PLATEAU_NEIGHBOR = 0.8            # เกณฑ์ประมาณการ (ไม่ใช่การทดสอบทางสถิติ)
SPIKE_NEIGHBOR = 0.6


class SearchError(ValueError):
    """พารามิเตอร์ของคำขอไม่ถูกต้อง (ข้อความไทย)"""


class Aborted(Exception):
    """หมดเวลา/ถูกยกเลิก — หยุดคำนวณ"""


def _check(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise Aborted()


# ------------------------------------------------------------------ สถิติจากเส้นมูลค่า (ใช้ร่วมกับ baseline)
def path_metrics(values: list[float], start_value: float, first_date: str, last_date: str) -> dict:
    """values = มูลค่าปิดรายวันต่อเนื่อง; สูตรเดียวกับระบบหลัก: CAGR=(1+R)^(365.25/D)-1 (ไม่ annualize ถ้า D<365 วัน)"""
    R = values[-1] / start_value - 1.0
    D = (date.fromisoformat(last_date) - date.fromisoformat(first_date)).days
    cagr = None
    if D >= 365 and 1.0 + R > 0:
        cagr = (1.0 + R) ** (365.25 / D) - 1.0
    peak, mdd = start_value, 0.0
    for v in values:
        if v > peak:
            peak = v
        else:
            dd = v / peak - 1.0
            if dd < mdd:
                mdd = dd
    calmar = cagr / abs(mdd) if (cagr is not None and mdd < -1e-12) else None
    return {"total_return": R, "cagr": cagr, "max_drawdown": mdd, "calmar": calmar}


# ------------------------------------------------------------------ tunables (whitelist ของสิ่งที่ขยับได้)
def _op_str(o: dict) -> str:
    k = o["kind"]
    if k == "const":
        return f"{o['value']:g}"
    if k == "price":
        return o["field"] + (f"[-{o['shift']}]" if o.get("shift") else "") + (" (S&P)" if o.get("of") == "benchmark" else "")
    d = I.REGISTRY[o["ind"]]
    args = ",".join(format(o["params"][p.name], "g") for p in d.params)
    s = o["ind"].upper() + "(" + args + ")"
    if len(d.outputs) > 1:
        s += f".{o['output']}"
    return s + (" (S&P)" if o.get("of") == "benchmark" else "")


def _leaves(cond: dict, path: list):
    if "all" in cond or "any" in cond:
        k = "all" if "all" in cond else "any"
        for i, c in enumerate(cond[k]):
            yield from _leaves(c, path + [k, i])
    elif "not" in cond:
        yield from _leaves(cond["not"], path + ["not"])
    else:
        yield path, cond


def _suggest(cur: float, integer: bool, lo, hi):
    if cur == 0:
        return None
    a, b = sorted((cur * 0.5, cur * 1.5))
    if integer:
        a, b = int(round(a)), int(round(b))
    if lo is not None:
        a = max(a, lo)
    if hi is not None:
        b = min(b, hi)
    if not a < b:
        return None
    return {"min": a, "max": b, "steps": 5}


def tunables(spec: dict) -> list[dict]:
    """รายการตัวแปรที่ขยับได้ของกลยุทธ์ใน spec: พารามิเตอร์ตัวชี้วัด, ค่าคงที่ในเงื่อนไข, ระดับ stop"""
    st = spec.get("strategy")
    if not st:
        return []
    out: list[dict] = []
    for side, label in (("entry", "เข้า"), ("exit", "ออก")):
        cond = st.get(side)
        if not cond:
            continue
        for path, leaf in _leaves(cond, [side]):
            text = f"{_op_str(leaf['left'])} {leaf['op']} {_op_str(leaf['right'])}"
            for pos in ("left", "right"):
                o = leaf[pos]
                base = path + [pos]
                if o["kind"] == "ind":
                    d = I.REGISTRY[o["ind"]]
                    for p in d.params:
                        cur = o["params"][p.name]
                        out.append({"id": ".".join(map(str, base + ["params", p.name])), "path": base + ["params", p.name],
                                    "kind": "ind_param", "group": side, "integer": p.integer, "lo": p.lo, "hi": p.hi,
                                    "current": cur, "label": f"{o['ind'].upper()}.{p.name} · เงื่อนไข{label}: {text}",
                                    "suggest": _suggest(cur, p.integer, p.lo, p.hi)})
                elif o["kind"] == "const":
                    cur = o["value"]
                    out.append({"id": ".".join(map(str, base + ["value"])), "path": base + ["value"], "kind": "const",
                                "group": side, "integer": False, "lo": None, "hi": None, "current": cur,
                                "label": f"ค่าคงที่ {cur:g} · เงื่อนไข{label}: {text}", "suggest": _suggest(cur, False, None, None)})
    stops = st.get("stops") or {}
    names = {"stop_loss_pct": "Stop-loss (%)", "take_profit_pct": "Take-profit (%)", "trailing_stop_pct": "Trailing stop (%)"}
    for k, (lo, hi) in STOP_RANGES.items():
        if k in stops:
            out.append({"id": f"stops.{k}", "path": ["stops", k], "kind": "stop", "group": "stops", "integer": False,
                        "lo": lo, "hi": hi, "current": stops[k], "label": names[k], "suggest": _suggest(stops[k], False, lo, hi)})
    if "max_hold_days" in stops:
        out.append({"id": "stops.max_hold_days", "path": ["stops", "max_hold_days"], "kind": "stop", "group": "stops",
                    "integer": True, "lo": 1, "hi": MAX_HOLD_DAYS, "current": stops["max_hold_days"],
                    "label": "ถือนานสุด (วันทำการ)", "suggest": _suggest(stops["max_hold_days"], True, 1, MAX_HOLD_DAYS)})
    return out


def public_tunables(spec: dict) -> list[dict]:
    return [{k: v for k, v in t.items() if k != "path"} for t in tunables(spec)]


def _num(x, name: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise SearchError(f"{name} ต้องเป็นตัวเลข")
    return float(x)


def build_values(t: dict, req: dict) -> list:
    """สร้างชุดค่าที่จะทดลองของตัวแปรหนึ่งตัว: ระบุ values=[...] หรือ min/max/steps; ตรวจช่วงตามชนิดตัวแปร"""
    name = t["label"]
    if "values" in req:
        raw = req["values"]
        if not isinstance(raw, list):
            raise SearchError(f"{name}: values ต้องเป็นรายการ")
        vals = [_num(v, name) for v in raw]
    else:
        lo_, hi_ = _num(req.get("min"), f"{name} (min)"), _num(req.get("max"), f"{name} (max)")
        steps = req.get("steps")
        if isinstance(steps, bool) or not isinstance(steps, int) or not (2 <= steps <= MAX_VALUES):
            raise SearchError(f"{name}: steps ต้องเป็นจำนวนเต็ม 2–{MAX_VALUES}")
        if not lo_ < hi_:
            raise SearchError(f"{name}: min ต้องน้อยกว่า max")
        vals = [lo_ + (hi_ - lo_) * i / (steps - 1) for i in range(steps)]
    out: list = []
    for v in vals:
        v = int(round(v)) if t["integer"] else round(v, 6)
        if t["lo"] is not None and v < t["lo"] or t["hi"] is not None and v > t["hi"]:
            raise SearchError(f"{name}: ค่า {v:g} อยู่นอกช่วงที่รองรับ ({t['lo']:g}–{t['hi']:g})")
        if v not in out:
            out.append(v)
    out.sort()
    if not 2 <= len(out) <= MAX_VALUES:
        raise SearchError(f"{name}: ต้องมี 2–{MAX_VALUES} ค่าที่ต่างกัน (ได้ {len(out)} ค่า)")
    return out


def parse_selection(spec: dict, params) -> tuple[list[dict], list[list]]:
    """คืน (tunables ที่เลือก, ชุดค่าของแต่ละตัว) — id ต้องอยู่ใน whitelist ที่สร้างจาก spec"""
    if not isinstance(params, list) or not (1 <= len(params) <= MAX_PARAMS):
        raise SearchError(f"ต้องเลือกพารามิเตอร์ 1–{MAX_PARAMS} ตัว")
    by_id = {t["id"]: t for t in tunables(spec)}
    if not by_id:
        raise SearchError("รันนี้ไม่มีกลยุทธ์ (ไม่มีพารามิเตอร์ให้ค้นหา)")
    chosen, grids, seen = [], [], set()
    for p in params:
        if not isinstance(p, dict) or p.get("id") not in by_id:
            raise SearchError("พารามิเตอร์ที่เลือกไม่อยู่ในรายการของกลยุทธ์นี้")
        if p["id"] in seen:
            raise SearchError("เลือกพารามิเตอร์ซ้ำ")
        seen.add(p["id"])
        t = by_id[p["id"]]
        chosen.append(t)
        grids.append(build_values(t, p))
    return chosen, grids


def _get(root, path):
    for k in path:
        root = root[k]
    return root


def make_variant(spec: dict, chosen: list[dict], values: tuple) -> dict | None:
    """สร้าง spec ตัวแปรหนึ่งชุด (ไม่แก้ของเดิม); คืน None ถ้าชุดค่านั้นผิดกติกา (เช่น MACD fast ≥ slow)"""
    v = copy.deepcopy(spec)
    st = v["strategy"]
    touched: list[list] = []
    for t, val in zip(chosen, values):
        path = t["path"]
        parent = _get(st, path[:-1])
        if t["kind"] == "stop":
            if path[-1] == "max_hold_days":
                parent[path[-1]] = int(val)
            else:
                lo, hi = STOP_RANGES[path[-1]]
                if not lo <= val <= hi:
                    return None
                parent[path[-1]] = float(val)
        elif t["kind"] == "const":
            parent[path[-1]] = float(val)
        else:
            parent[path[-1]] = int(val) if t["integer"] else float(val)
            if path[:-2] not in touched:
                touched.append(path[:-2])
    for p in touched:
        o = _get(st, p)
        try:
            o["params"] = I.normalize_params(o["ind"], o["params"])
        except ValueError:
            return None
    return v


# ------------------------------------------------------------------ ดึงตัวเลขจากผลรัน
def _val(res: dict, who: str, m: str):
    x = res["comparison"][who].get(m)
    return None if x is None else x.get("value")


def _mset(res: dict, who: str = "portfolio") -> dict:
    return {m: _val(res, who, m) for m in ("total_return", "cagr", "max_drawdown", "calmar", "sortino")}


def _run_safe(spec: dict, mk):
    try:
        return _run(spec, mk), None
    except DataError as e:
        return None, str(e)


# ------------------------------------------------------------------ Parameter Sweep
def _neighbors(i: int, j: int, ni: int, nj: int):
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            if (a or b) and 0 <= i + a < ni and 0 <= j + b < nj:
                yield i + a, j + b


def sweep(spec: dict, mk, chosen: list[dict], grids: list[list], metric: str, cancel=None) -> dict:
    if metric not in METRICS:
        raise SearchError(f"metric ต้องเป็นหนึ่งใน {', '.join(METRICS)}")
    ni, nj = len(grids[0]), (len(grids[1]) if len(grids) > 1 else 1)
    if ni * nj > MAX_CELLS:
        raise SearchError(f"จำนวนเซลล์ {ni * nj} เกินขอบเขต {MAX_CELLS} (ลดจำนวนค่าในแต่ละแกน)")
    cur = tuple(t["current"] for t in chosen)
    cells: dict[tuple, dict] = {}
    ref: dict = {}
    for (i, a), (j, b) in itertools.product(enumerate(grids[0]), enumerate(grids[1] if len(grids) > 1 else [None])):
        _check(cancel)
        vals = (a,) if b is None else (a, b)
        params = {t["id"]: v for t, v in zip(chosen, vals)}
        cell = {"i": i, "j": j, "params": params, "metrics": None, "trades": None, "time_in_market": None, "reason": None}
        var = make_variant(spec, chosen, vals)
        if var is None:
            cell["reason"] = "ชุดค่านี้ผิดกติกาของตัวชี้วัด"
        else:
            res, err = _run_safe(var, mk)
            if res is None:
                cell["reason"] = err
            else:
                cell["metrics"] = _mset(res)
                cell["trades"] = res["stats"]["trade_count"]
                cell["time_in_market"] = res["stats"]["time_in_market"]
                if not ref:
                    ref = {"buy_hold": _mset(res, "buy_hold"), "benchmark": _mset(res, "benchmark")}
        cells[(i, j)] = cell
    valid = [c for c in cells.values() if c["metrics"] is not None]
    scored = [c for c in valid if c["metrics"][metric] is not None]
    if not valid:
        raise SearchError("ไม่มีเซลล์ใดคำนวณได้: " + next((c["reason"] for c in cells.values() if c["reason"]), "ข้อมูลไม่พอ"))
    summary: dict = {"cells": ni * nj, "valid_cells": len(valid), "scored_cells": len(scored)}
    best = None
    if scored:
        # เสมอกัน -> เลือกเซลล์ที่อยู่ใกล้กลางตารางที่สุด (พื้นผิวเรียบจะไม่ถูกตีความว่าเป็น "ขอบ")
        centre = lambda c: abs(c["i"] - (ni - 1) / 2) / ni + abs(c["j"] - (nj - 1) / 2) / nj
        best = max(scored, key=lambda c: (c["metrics"][metric], -centre(c)))
        bv = best["metrics"][metric]
        vals_m = sorted(c["metrics"][metric] for c in scored)
        summary.update({"best_value": bv, "median_value": vals_m[len(vals_m) // 2], "worst_value": vals_m[0]})
        nb = [cells[n]["metrics"][metric] for n in _neighbors(best["i"], best["j"], ni, nj)
              if cells[n]["metrics"] is not None and cells[n]["metrics"][metric] is not None]
        summary["neighbor_ratio"] = (sum(nb) / len(nb)) / bv if (nb and bv > 0) else None
        summary["frac_ge_half_best"] = sum(1 for c in scored if c["metrics"][metric] >= 0.5 * bv) / len(scored) if bv > 0 else None
        summary["best_on_edge"] = bool(best["i"] in (0, ni - 1) or (nj > 1 and best["j"] in (0, nj - 1)))
        tr = lambda c: c["metrics"]["total_return"]
        summary["frac_positive"] = sum(1 for c in valid if tr(c) is not None and tr(c) > 0) / len(valid)
        bh, bm = ref["buy_hold"]["total_return"], ref["benchmark"]["total_return"]
        summary["frac_beat_buy_hold"] = sum(1 for c in valid if tr(c) is not None and bh is not None and tr(c) > bh) / len(valid)
        summary["frac_beat_benchmark"] = sum(1 for c in valid if tr(c) is not None and bm is not None and tr(c) > bm) / len(valid)
        nr, fh = summary["neighbor_ratio"], summary["frac_ge_half_best"]
        if bv <= 0:
            verdict = "no_profit"
        elif nr is not None and nr < SPIKE_NEIGHBOR:
            verdict = "spike"
        elif summary["best_on_edge"]:
            verdict = "edge"                       # ค่าดีที่สุดอยู่ขอบตาราง: จุดที่ดีกว่าอาจอยู่นอกช่วงที่ทดลอง ยังบอกว่าเป็นที่ราบไม่ได้
        elif nr is not None and nr >= PLATEAU_NEIGHBOR and fh is not None and fh >= 0.5:
            verdict = "plateau"
        else:
            verdict = "mixed"
        summary["verdict"] = verdict
    else:
        summary["verdict"] = "no_metric"
    base = next(({"i": c["i"], "j": c["j"]} for c in cells.values()
                 if tuple(c["params"][t["id"]] for t in chosen) == cur), None)
    return {
        "kind": "sweep", "metric": metric, "metric_label": METRIC_LABEL[metric],
        "axes": [{"id": t["id"], "label": t["label"], "values": g, "current": t["current"]} for t, g in zip(chosen, grids)],
        "cells": list(cells.values()), "reference": ref,
        "best": None if best is None else {"i": best["i"], "j": best["j"], "params": best["params"], "metrics": best["metrics"]},
        "base": base, "summary": summary, "trials": ni * nj,
        "note": ("plateau = เซลล์รอบค่าที่ดีที่สุดให้ผลใกล้เคียง (เฉลี่ย ≥ 80% ของค่าสูงสุด และ ≥ ครึ่งของเซลล์มีผล ≥ 50% ของค่าสูงสุด); "
                 "spike = เซลล์รอบข้างเฉลี่ยต่ำกว่า 60% ของค่าสูงสุด น่าจะ overfit; "
                 "edge = ค่าดีที่สุดอยู่ขอบตาราง (ควรขยายช่วงแล้วดูใหม่); no_profit = ไม่มีเซลล์ที่ผลเป็นบวก — "
                 "เกณฑ์เหล่านี้เป็นค่าประมาณ ไม่ใช่การทดสอบทางสถิติ"),
        "caveats": [
            f"ผลทุกเซลล์คำนวณบนข้อมูลช่วงเดียวกัน (in-sample); ค่าที่ดีที่สุดจาก {ni * nj} เซลล์ย่อมสูงกว่าที่คาดได้จริง (winner's curse) อย่าเลือกใช้ค่านั้นโดยตรง",
            "ถ้าค่าที่ดีที่สุดอยู่ขอบตาราง แปลว่าจุดที่ดีกว่าอาจอยู่นอกช่วงที่ทดลอง และยิ่งขยับยิ่ง overfit",
            "ใช้ผลนี้ตอบเพียงว่า 'ผลเกาะอยู่ที่ค่าเดียวหรือดีทั้งย่าน' — ส่วนการพิสูจน์ว่าใช้ได้ในอนาคตต้องใช้ Walk-forward",
        ],
    }


# ------------------------------------------------------------------ Walk-forward
def _chain(parts: list[list[dict]], key: str) -> list[tuple[str, float]]:
    out, v0 = [], 1.0
    for series in parts:
        for p in series:
            out.append((p["date"], v0 * (1.0 + p[key])))
        v0 = v0 * (1.0 + series[-1][key])
    return out


def _chain_metrics(path: list[tuple[str, float]], first_date: str) -> dict:
    return path_metrics([v for _, v in path], 1.0, first_date, path[-1][0])


def _span_days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def walk_forward(spec: dict, mk, dates: list[str], chosen: list[dict], grids: list[list], metric: str,
                 folds: int, anchored: bool, cancel=None) -> dict:
    if metric not in METRICS:
        raise SearchError(f"metric ต้องเป็นหนึ่งใน {', '.join(METRICS)}")
    if not (2 <= folds <= 6):
        raise SearchError("folds ต้องเป็นจำนวนเต็ม 2–6")
    blocks = split_windows(dates, folds + 1)
    if len(blocks) < folds + 1:
        raise SearchError("ช่วงเวลาสั้นเกินไปสำหรับจำนวน fold ที่เลือก")
    idx = {d: i for i, d in enumerate(dates)}
    if any(idx[b] - idx[a] + 1 < MIN_FOLD_DAYS for a, b in blocks):
        raise SearchError(f"แต่ละบล็อกต้องมีอย่างน้อย {MIN_FOLD_DAYS} วันทำการ — ลดจำนวน fold หรือขยายช่วงเวลา")
    if metric in ("cagr", "calmar") and any(_span_days(a, b) < MIN_ANNUAL_DAYS for a, b in blocks):
        raise SearchError("บล็อกสั้นกว่า 1 ปี คำนวณ CAGR/Calmar ไม่ได้ — ใช้ total_return หรือลดจำนวน fold")

    combos = []
    for vals in itertools.product(*grids):
        var = make_variant(spec, chosen, vals)
        if var is not None:
            combos.append((vals, var))
    if len(combos) < 2:
        raise SearchError("มีชุดค่าที่ใช้ได้น้อยกว่า 2 ชุด")
    if folds * (len(combos) + 2) > MAX_WF_RUNS:
        raise SearchError(f"จำนวนการรัน {folds * (len(combos) + 2)} เกินขอบเขต {MAX_WF_RUNS} (ลด fold หรือจำนวนค่า)")

    fold_rows, oos_parts, fixed_parts, bh_parts, bm_parts = [], [], [], [], []
    for f in range(folds):
        tr_a = blocks[0][0] if anchored else blocks[f][0]
        tr_b, (te_a, te_b) = blocks[f][1], blocks[f + 1]
        best, tried = None, 0
        for vals, var in combos:
            _check(cancel)
            res, _ = _run_safe({**var, "start": tr_a, "end": tr_b}, mk)
            if res is None:
                continue
            tried += 1
            m = _val(res, "portfolio", metric)
            if m is not None and (best is None or m > best[0]):
                best = (m, vals, var)
        row = {"fold": f + 1, "train": [tr_a, tr_b], "test": [te_a, te_b], "trials": tried}
        if best is None:
            row["skipped"] = "ไม่มีชุดค่าที่คำนวณผลช่วงฝึกได้"
            fold_rows.append(row)
            continue
        _check(cancel)
        sel, _ = _run_safe({**best[2], "start": te_a, "end": te_b}, mk)
        fix, _ = _run_safe({**spec, "start": te_a, "end": te_b}, mk)
        if sel is None or fix is None:
            row["skipped"] = "รันช่วงทดสอบไม่สำเร็จ"
            fold_rows.append(row)
            continue
        row.update({"chosen": {t["id"]: v for t, v in zip(chosen, best[1])}, "is_value": best[0],
                    "oos_value": _val(sel, "portfolio", metric), "oos": _mset(sel), "fixed_oos": _mset(fix),
                    "buy_hold_oos": _mset(sel, "buy_hold"), "benchmark_oos": _mset(sel, "benchmark")})
        fold_rows.append(row)
        oos_parts.append(sel["series"])
        fixed_parts.append(fix["series"])
        bh_parts.append(sel["series"])
        bm_parts.append(sel["series"])
    used = [r for r in fold_rows if "chosen" in r]
    if not used:
        raise SearchError("ไม่มี fold ใดคำนวณได้")
    first = used[0]["test"][0]
    stitched = {
        "walk_forward": _chain_metrics(_chain(oos_parts, "portfolio"), first),
        "fixed_params": _chain_metrics(_chain(fixed_parts, "portfolio"), first),
        "buy_hold": _chain_metrics(_chain(bh_parts, "buy_hold"), first),
        "benchmark": _chain_metrics(_chain(bm_parts, "benchmark"), first),
    }
    curve = {k: _chain(p, key) for k, (p, key) in {"walk_forward": (oos_parts, "portfolio"), "fixed_params": (fixed_parts, "portfolio"),
                                                      "buy_hold": (bh_parts, "buy_hold"), "benchmark": (bm_parts, "benchmark")}.items()}
    step = max(1, len(curve["walk_forward"]) // 400)
    curves = {"dates": [d for d, _ in curve["walk_forward"][::step]]}
    curves.update({k: [v - 1.0 for _, v in c[::step]] for k, c in curve.items()})
    is_v = [r["is_value"] for r in used if r["is_value"] is not None]
    oos_v = [r["oos_value"] for r in used if r["oos_value"] is not None]
    summary = {
        "folds_used": len(used), "folds": folds, "anchored": anchored, "trials": folds * len(combos),
        "mean_is": sum(is_v) / len(is_v) if is_v else None, "mean_oos": sum(oos_v) / len(oos_v) if oos_v else None,
        "oos_vs_is_ratio": None,
        "folds_positive": sum(1 for r in used if (r["oos"]["total_return"] or 0) > 0),
        "folds_beat_buy_hold": sum(1 for r in used if (r["oos"]["total_return"] or -9) > (r["buy_hold_oos"]["total_return"] or 9)),
        "folds_beat_fixed": sum(1 for r in used if (r["oos"]["total_return"] or -9) > (r["fixed_oos"]["total_return"] or 9)),
    }
    if summary["mean_is"] and summary["mean_is"] > 0 and summary["mean_oos"] is not None:
        summary["oos_vs_is_ratio"] = summary["mean_oos"] / summary["mean_is"]
    stab = {}
    for t in chosen:
        seq = [r["chosen"][t["id"]] for r in used]
        stab[t["id"]] = {"label": t["label"], "chosen": seq, "distinct": len(set(seq)),
                         "changes": sum(1 for a, b in zip(seq, seq[1:]) if a != b)}
    return {
        "kind": "walk_forward", "metric": metric, "metric_label": METRIC_LABEL[metric], "anchored": anchored,
        "axes": [{"id": t["id"], "label": t["label"], "values": g, "current": t["current"]} for t, g in zip(chosen, grids)],
        "folds": fold_rows, "stitched": stitched, "curves": curves, "param_stability": stab, "summary": summary,
        "caveats": [
            "ผล out-of-sample คำนวณจากช่วงทดสอบต่อกัน แต่ละช่วงเลือกค่าจากข้อมูลก่อนหน้าเท่านั้น (ไม่แอบดูอนาคต)",
            "ถ้ากฎ/ช่วงพารามิเตอร์ที่ให้ค้นหาถูกเลือกหลังเห็นผลทั้งช่วงแล้ว ผลนี้ยังมีอคติบางส่วน (ผู้ใช้เองก็เป็นส่วนหนึ่งของการค้นหา)",
            "ช่วงทดสอบแต่ละช่วงเริ่มจากเงินสด ณ วันเริ่มช่วง และต่อเส้นผลด้วยการคูณผลตอบแทนแต่ละช่วง (ไม่รวมผลข้ามคืนระหว่างรอยต่อช่วง)",
            "จำนวนรอบซื้อขายในแต่ละช่วงทดสอบอาจน้อยมาก ผลต่อช่วงจึงผันผวน — ดูภาพรวมทุกช่วง ไม่ใช่ช่วงเดียว",
        ],
    }
