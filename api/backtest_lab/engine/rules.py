"""ภาษากฎเงื่อนไข (Rule language) — JSON ที่ตรวจแบบ whitelist แล้วประเมินเป็นรายแท่ง ไม่มี eval/exec

Operand (ซ้าย/ขวาของการเปรียบเทียบ)
  {"ind": "ema", "period": 200}                       # ตัวชี้วัด (พารามิเตอร์ใส่ข้างกัน; output / source ระบุได้)
  {"ind": "macd", "output": "hist"}
  {"price": "close"}                                  # close|open|high|low|volume
  {"value": 30}                                       # ค่าคงที่
  ตัวปรับ (ใช้ได้กับ ind/price): "shift": n (ย้อนหลัง n แท่ง), "mult": k (คูณ), "of": "benchmark" (คำนวณบน S&P 500 แทนหุ้นตัวนั้น)

Condition
  {"op": ">|>=|<|<=|cross_above|cross_below", "left": operand, "right": operand}
  {"all": [cond, ...]}   {"any": [cond, ...]}   {"not": cond}

กฎเหล็ก
- ค่า ณ แท่ง i อ่านข้อมูลถึงแท่ง i เท่านั้น (indicator ผ่าน property test) -> สัญญาณเกิดหลังปิดวัน i และถูกจับคู่ที่เปิดวัน i+1 โดย runner
- ค่าที่ยังคำนวณไม่ได้ (NaN) ให้ผลเป็น None (ไม่ทราบ) แบบ Kleene logic; ณ จุดตัดสินใจ None ถือเป็น "ไม่เป็นจริง"
"""
from __future__ import annotations

import json
import math
from typing import Any, Optional

from . import indicators as I

OPS = (">", ">=", "<", "<=", "cross_above", "cross_below")
PRICE_FIELDS = ("close", "open", "high", "low", "volume")
MAX_NODES, MAX_DEPTH, MAX_OPERANDS, MAX_SHIFT = 24, 5, 12, 252
MAX_HOLD_DAYS = 5000
NAN = float("nan")


class RuleError(ValueError):
    """กฎไม่ถูกต้อง (ข้อความภาษาไทย)"""


# ---------------------------------------------------------------- validation
def _operand(raw: Any, where: str) -> dict:
    if not isinstance(raw, dict):
        raise RuleError(f"{where}: operand ต้องเป็น object")
    raw = dict(raw)
    shift = raw.pop("shift", 0)
    mult = raw.pop("mult", 1.0)
    of = raw.pop("of", "self")
    if isinstance(shift, bool) or not isinstance(shift, int) or not (0 <= shift <= MAX_SHIFT):
        raise RuleError(f"{where}.shift ต้องเป็นจำนวนเต็ม 0–{MAX_SHIFT}")
    if isinstance(mult, bool) or not isinstance(mult, (int, float)) or not math.isfinite(mult) or not (-1000 <= mult <= 1000):
        raise RuleError(f"{where}.mult ต้องเป็นตัวเลข")
    if of not in ("self", "benchmark"):
        raise RuleError(f"{where}.of ต้องเป็น benchmark หรือไม่ระบุ")
    kinds = [k for k in ("ind", "price", "value") if k in raw]
    if len(kinds) != 1:
        raise RuleError(f"{where}: ต้องมีหนึ่งในคีย์ ind / price / value")
    kind = kinds[0]
    if kind == "value":
        v = raw.pop("value")
        if raw:
            raise RuleError(f"{where}: value ห้ามมีคีย์อื่น")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise RuleError(f"{where}.value ต้องเป็นตัวเลข")
        if shift or of != "self":
            raise RuleError(f"{where}: ค่าคงที่ใช้ shift/of ไม่ได้")
        return {"kind": "const", "value": float(v) * float(mult)}
    if kind == "price":
        f = raw.pop("price")
        if raw:
            raise RuleError(f"{where}: price ห้ามมีคีย์อื่น ({', '.join(sorted(raw))})")
        if f not in PRICE_FIELDS:
            raise RuleError(f"{where}.price ต้องเป็นหนึ่งใน {', '.join(PRICE_FIELDS)}")
        return {"kind": "price", "field": f, "shift": shift, "mult": float(mult), "of": of}
    key = raw.pop("ind")
    if key not in I.REGISTRY:
        raise RuleError(f"{where}: ไม่รู้จักตัวชี้วัด '{key}' (รองรับ: {', '.join(I.REGISTRY)})")
    d = I.REGISTRY[key]
    output = raw.pop("output", d.outputs[0])
    if output not in d.outputs:
        raise RuleError(f"{where}: {key} มี output {', '.join(d.outputs)} (ไม่มี '{output}')")
    try:
        params = I.normalize_params(key, raw)
    except ValueError as e:
        raise RuleError(f"{where}: {e}")
    return {"kind": "ind", "ind": key, "params": params, "output": output, "shift": shift, "mult": float(mult), "of": of}


class _Counter:
    def __init__(self):
        self.nodes = 0
        self.operands: set[str] = set()


def _cond(raw: Any, where: str, depth: int, cnt: _Counter) -> dict:
    if depth > MAX_DEPTH:
        raise RuleError(f"{where}: ซ้อนเงื่อนไขลึกเกิน {MAX_DEPTH} ชั้น")
    cnt.nodes += 1
    if cnt.nodes > MAX_NODES:
        raise RuleError(f"เงื่อนไขซับซ้อนเกินไป (เกิน {MAX_NODES} โหนด)")
    if not isinstance(raw, dict):
        raise RuleError(f"{where}: เงื่อนไขต้องเป็น object")
    keys = set(raw)
    if keys <= {"all", "any"} and len(keys) == 1:
        k = next(iter(keys))
        items = raw[k]
        if not isinstance(items, list) or not (1 <= len(items) <= 12):
            raise RuleError(f"{where}.{k} ต้องเป็นรายการ 1–12 เงื่อนไข")
        return {k: [_cond(x, f"{where}.{k}[{i}]", depth + 1, cnt) for i, x in enumerate(items)]}
    if keys == {"not"}:
        return {"not": _cond(raw["not"], f"{where}.not", depth + 1, cnt)}
    if keys == {"op", "left", "right"}:
        if raw["op"] not in OPS:
            raise RuleError(f"{where}.op ต้องเป็นหนึ่งใน {', '.join(OPS)}")
        left, right = _operand(raw["left"], f"{where}.left"), _operand(raw["right"], f"{where}.right")
        for o in (left, right):
            if o["kind"] != "const":
                cnt.operands.add(_okey(o))
        if len(cnt.operands) > MAX_OPERANDS:
            raise RuleError(f"ใช้ตัวชี้วัด/ราคาต่างกันเกิน {MAX_OPERANDS} แบบ")
        return {"op": raw["op"], "left": left, "right": right}
    raise RuleError(f"{where}: เงื่อนไขต้องเป็น all / any / not หรือ {{op,left,right}}")


def _okey(o: dict) -> str:
    base = {k: o[k] for k in o if k not in ("shift", "mult")}
    return json.dumps(base, sort_keys=True)


STOP_KEYS = {"stop_loss_pct": (0.1, 90.0), "take_profit_pct": (0.1, 1000.0), "trailing_stop_pct": (0.1, 90.0)}


def validate_strategy(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise RuleError("strategy ต้องเป็น object")
    extra = set(raw) - {"entry", "exit", "stops"}
    if extra:
        raise RuleError(f"strategy มีฟิลด์ที่ไม่รองรับ: {', '.join(sorted(extra))}")
    if "entry" not in raw:
        raise RuleError("strategy ต้องมี entry (เงื่อนไขเข้าซื้อ)")
    cnt = _Counter()
    entry = _cond(raw["entry"], "entry", 1, cnt)
    ex = None
    if raw.get("exit") is not None:
        ex = _cond(raw["exit"], "exit", 1, cnt)
    stops_raw = raw.get("stops") or {}
    if not isinstance(stops_raw, dict) or set(stops_raw) - (set(STOP_KEYS) | {"max_hold_days"}):
        raise RuleError("stops รูปแบบไม่ถูกต้อง")
    stops: dict = {}
    for k, (lo, hi) in STOP_KEYS.items():
        v = stops_raw.get(k)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not (lo <= v <= hi):
            raise RuleError(f"stops.{k} ต้องอยู่ระหว่าง {lo:g} ถึง {hi:g}")
        stops[k] = float(v)
    mh = stops_raw.get("max_hold_days")
    if mh is not None:
        if isinstance(mh, bool) or not isinstance(mh, int) or not (1 <= mh <= MAX_HOLD_DAYS):
            raise RuleError(f"stops.max_hold_days ต้องเป็นจำนวนเต็ม 1–{MAX_HOLD_DAYS}")
        stops["max_hold_days"] = mh
    return {"entry": entry, "exit": ex, "stops": stops}


# ---------------------------------------------------------------- warm-up
def _operands(cond: dict):
    if "all" in cond or "any" in cond:
        for c in cond.get("all", cond.get("any")):
            yield from _operands(c)
    elif "not" in cond:
        yield from _operands(cond["not"])
    else:
        yield cond["left"]
        yield cond["right"]


def warmup_bars(strategy: dict) -> int:
    """จำนวนแท่ง (วันทำการ) ก่อนวันเริ่มที่ควรมี เพื่อให้ตัวชี้วัดพร้อมตั้งแต่วันแรก"""
    w = 0
    for c in (strategy["entry"], strategy["exit"]):
        if c is None:
            continue
        for o in _operands(c):
            if o["kind"] == "ind":
                w = max(w, I.REGISTRY[o["ind"]].warmup(o["params"]) + o["shift"] + 2)
            elif o["kind"] == "price":
                w = max(w, o["shift"] + 2)
    return w


# ---------------------------------------------------------------- evaluation
def _series(o: dict, bars: list[dict], bench: list[dict], cache: dict) -> list[float]:
    if o["kind"] == "const":
        return [o["value"]] * len(bars)
    src = bench if o["of"] == "benchmark" else bars
    key = (o["of"], _okey(o))
    base = cache.get(key)
    if base is None:
        if o["kind"] == "price":
            base = [float(b[o["field"]]) for b in src]
        else:
            base = I.compute(src, o["ind"], o["params"], o["output"])
        cache[key] = base
    return base


def _shifted(base: list[float], shift: int, mult: float) -> list[float]:
    n = len(base)
    out = [NAN] * n
    for i in range(shift, n):
        v = base[i - shift]
        out[i] = v * mult if v == v else NAN
    return out


def evaluate(cond: dict, bars: list[dict], bench_bars: Optional[list[dict]] = None, _cache: Optional[dict] = None,
             _bench_idx: Optional[list[int]] = None) -> list[Optional[bool]]:
    """คืนรายการ True/False/None ยาวเท่า bars; ตัวชี้วัด 'of': 'benchmark' ถูกจัดแนวตามวันที่ (ใช้ค่าแท่งล่าสุดที่ ≤ วันนั้น)"""
    cache = {} if _cache is None else _cache
    bench_bars = bench_bars or []
    if _bench_idx is None:
        _bench_idx = _align_idx(bars, bench_bars)
    return _eval(cond, bars, bench_bars, cache, _bench_idx)


def _align_idx(bars: list[dict], bench: list[dict]) -> list[int]:
    out, j = [], -1
    for b in bars:
        while j + 1 < len(bench) and bench[j + 1]["date"] <= b["date"]:
            j += 1
        out.append(j)
    return out


def _operand_values(o: dict, bars, bench, cache, bidx) -> list[float]:
    base = _series(o, bars, bench, cache)
    if o["kind"] == "const":
        return base
    if o["of"] == "benchmark":
        # ค่าของ benchmark ณ แท่งหุ้น i = ค่า benchmark แท่งล่าสุดที่ไม่เกินวันเดียวกัน แล้วจึงเลื่อน shift ในหน่วยแท่ง benchmark
        out = []
        for i in range(len(bars)):
            j = bidx[i] - o["shift"]
            v = base[j] if 0 <= j < len(base) else NAN
            out.append(v * o["mult"] if v == v else NAN)
        return out
    return _shifted(base, o["shift"], o["mult"])


def _eval(cond, bars, bench, cache, bidx) -> list[Optional[bool]]:
    n = len(bars)
    if "all" in cond or "any" in cond:
        is_all = "all" in cond
        parts = [_eval(c, bars, bench, cache, bidx) for c in cond["all" if is_all else "any"]]
        out: list[Optional[bool]] = []
        for i in range(n):
            vals = [p[i] for p in parts]
            if is_all:
                out.append(False if any(v is False for v in vals) else (None if any(v is None for v in vals) else True))
            else:
                out.append(True if any(v is True for v in vals) else (None if any(v is None for v in vals) else False))
        return out
    if "not" in cond:
        return [None if v is None else (not v) for v in _eval(cond["not"], bars, bench, cache, bidx)]
    op = cond["op"]
    L = _operand_values(cond["left"], bars, bench, cache, bidx)
    R = _operand_values(cond["right"], bars, bench, cache, bidx)
    out = []
    for i in range(n):
        a, b = L[i], R[i]
        if a != a or b != b:
            out.append(None)
        elif op == ">":
            out.append(a > b)
        elif op == ">=":
            out.append(a >= b)
        elif op == "<":
            out.append(a < b)
        elif op == "<=":
            out.append(a <= b)
        else:
            if i == 0 or L[i - 1] != L[i - 1] or R[i - 1] != R[i - 1]:
                out.append(None)
            elif op == "cross_above":
                out.append(L[i - 1] <= R[i - 1] and a > b)
            else:
                out.append(L[i - 1] >= R[i - 1] and a < b)
    return out
