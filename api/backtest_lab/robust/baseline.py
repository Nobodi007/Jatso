"""เทียบกลยุทธ์กับ "การสุ่มจังหวะ" ที่อยู่ในตลาดเท่ากัน — ตอบว่าผลนี้ดีกว่าโชคหรือไม่

สมมติฐานว่าง (null): ไม่มีข้อมูลในจังหวะเข้า-ออก
วิธี: ต่อหุ้นแต่ละตัว ใช้ "จำนวนรอบ" และ "ระยะเวลาถือแต่ละรอบ" เท่าที่กลยุทธ์ทำจริง แล้วสุ่มสลับลำดับรอบและสุ่มตำแหน่งวางบนประวัติราคาจริงของหุ้นตัวนั้น
(ไม่ซ้อนทับกัน) จากนั้นคำนวณพอร์ตจากราคาจริงด้วยโครงเดียวกัน (ช่องเงินแยกต่อหุ้น เงินสดไม่มีดอกเบี้ย หักค่าคอม+slippage ต่อรอบ)
เทียบ metric ของกลยุทธ์จริงกับการแจกแจงของพอร์ตสุ่ม; p = สัดส่วนที่ "สุ่มได้ผลดีเท่ากันหรือดีกว่า" = (นับ+1)/(จำนวนครั้ง+1)

ข้อจำกัดที่ต้องบอกผู้ใช้
- ทดสอบเฉพาะ "จังหวะ/กติกาการออก" ไม่ได้ทดสอบว่าการเลือกหุ้นเองโชคดีหรือไม่ (หุ้นที่เลือกหลังเห็นผลย่อมดูดีทั้งกลยุทธ์จริงและสุ่ม)
- เป็นแบบจำลองแบบประมาณ: ผลตอบแทนรายวันแบบ close-to-close ต่อวันที่ถือ, ไม่จำลอง rebalance, stop ระหว่างวันถูกแทนด้วยระยะถือ
  ระบบจึงรันแบบจำลองกับรอบจริงซ้ำและรายงานความคลาดเคลื่อนต่อผลจริง (replication) ให้ดูเสมอ
- ไม่ได้ปรับ p ตามจำนวนชุดกฎที่ผู้ใช้ลองมาก่อนโดยอัตโนมัติ: ใส่ trials เพื่อปรับแบบ Bonferroni (ขอบเขตบนที่ปลอดภัย)
"""
from __future__ import annotations

import math
import random

from ..engine.runner import _align
from . import montecarlo as MC
from .search import METRIC_LABEL, SearchError, _check, path_metrics

MIN_SIMS = 100
MAX_SIMS = 3000
MAX_WORK = 50_000_000             # sims × จำนวนหุ้น × จำนวนวัน (กันกินเวลา CPU)
STAT_KEYS = ("total_return", "cagr", "max_drawdown", "calmar")
BASELINE_METRICS = ("calmar", "cagr", "total_return")
HIST_BINS = 24
FEW_TRIPS = 10


def _growth(opens: list[float], closes: list[float]) -> list[float]:
    """G[0]=1; G[i+1] = ปัจจัยสะสมถึงราคาปิดวัน i (วัน 0 นับจากราคาเปิด เพราะซื้อที่ราคาเปิดวันแรกได้)"""
    g, prev = [1.0], opens[0]
    for c in closes:
        g.append(g[-1] * (c / prev))
        prev = c
    return g


def _trips_by_symbol(result: dict, cal_idx: dict, n: int, syms: list[str]) -> tuple[dict, int]:
    sr = result["strategy_result"]
    ts = sr["trip_stats"]
    if len(sr["trips"]) < ts["closed_trades"] + ts["open_at_end"]:
        raise SearchError("รอบซื้อขายมากกว่าที่ระบบเก็บไว้ในผลรัน (ข้อมูลรอบไม่ครบ) จึงทำการเทียบนี้ไม่ได้ — ลดช่วงเวลาหรือจำนวนหุ้น")
    out: dict[str, list[tuple[int, int]]] = {s: [] for s in syms}
    zero = 0
    for t in sr["trips"]:
        s = t["symbol"]
        if s not in out or t["entry_date"] not in cal_idx or (t["exit_date"] is not None and t["exit_date"] not in cal_idx):
            raise SearchError("ข้อมูลรอบซื้อขายไม่ตรงกับวันที่ของผลรัน")
        e = cal_idx[t["entry_date"]]
        x = n if t["exit_date"] is None else cal_idx[t["exit_date"]]
        if x <= e:
            zero += 1                       # ซื้อและขายในวันเดียว (stop ในวันที่ซื้อ): ไม่มีวันถือให้สุ่ม
            continue
        out[s].append((e, x))
    for v in out.values():
        v.sort()
    return out, zero


def _values(plan: dict, G: dict, caps: dict, idle: float, n: int, costfac: float, buyfac: float | None = None) -> list[float]:
    """มูลค่าพอร์ตรายวันตามแผนรอบซื้อขาย (e,x) = ถือวัน e..x-1 แบบ close-to-close; ช่องเงินแยกต่อหุ้น"""
    total = [idle] * n
    for s, ivs in plan.items():
        g, cv, pos, vals = G[s], caps[s], 0, []
        for e, x in ivs:
            if e > pos:
                vals.extend([cv] * (e - pos))
            # รอบที่ยังถืออยู่ ณ วันสุดท้าย engine ไม่ได้ขาย -> จ่ายต้นทุนฝั่งซื้อเท่านั้น (ครึ่งหนึ่งของรอบเต็ม)
            k = cv * (costfac if x < n else (math.sqrt(costfac) if buyfac is None else buyfac)) / g[e]
            vals.extend([k * v for v in g[e + 1:x + 1]])
            cv = k * g[x]
            pos = x
        if n > pos:
            vals.extend([cv] * (n - pos))
        total = [a + b for a, b in zip(total, vals)]
    return total


def _place(durs: list[int], n: int, rng: random.Random) -> list[tuple[int, int]]:
    k = len(durs)
    if k == 0:
        return []
    free = n - sum(durs)
    order = durs[:]
    rng.shuffle(order)
    cuts = sorted(rng.sample(range(free + k), k))          # stars & bars: แจกวันว่างเป็น k+1 ช่องแบบสุ่มสม่ำเสมอ
    gaps = [cuts[0]] + [cuts[i] - cuts[i - 1] - 1 for i in range(1, k)]
    pos, out = 0, []
    for g, d in zip(gaps, order):
        e = pos + g
        out.append((e, e + d))
        pos = e + d
    return out


def _hist(vals: list[float], actual: float | None) -> dict:
    lo, hi = min(vals), max(vals)
    if actual is not None:
        lo, hi = min(lo, actual), max(hi, actual)
    if hi - lo < 1e-12:
        hi = lo + 1e-9
    w = (hi - lo) / HIST_BINS
    counts = [0] * HIST_BINS
    for v in vals:
        counts[min(HIST_BINS - 1, int((v - lo) / w))] += 1
    return {"edges": [lo + w * i for i in range(HIST_BINS + 1)], "counts": counts}


def verdict_text(head: dict) -> str:
    """สรุปผลเทียบการสุ่ม: แยก 3 กรณี ดีกว่าสุ่มจริง / แยกจากโชคไม่ได้ / ต่ำกว่าการสุ่ม (ไม่ใช่แค่ "แยกจากโชคไม่ได้")"""
    if head["p_bonferroni"] < 0.05:
        return "แยกจากโชคได้ที่ระดับ 5% (ยังไม่ได้พิสูจน์ว่าจะใช้ได้ในอนาคต)"
    if head["beats_fraction"] <= 0.05:
        return ("ต่ำกว่าการสุ่มที่ระดับ 5% — จังหวะเข้า/ออกของกฎทำให้ผลแย่กว่าการสุ่มจังหวะ "
                "(ไม่ใช่แค่แยกจากโชคไม่ได้ แต่แย่กว่าสุ่มจริง)")
    if head["beats_fraction"] < 0.5:
        return "ต่ำกว่าค่ากลางของการสุ่ม และยังแยกจากโชคไม่ได้ที่ระดับ 5% — ไม่มีหลักฐานว่าจังหวะของกฎช่วยได้"
    return "ยังแยกจากโชคไม่ได้ที่ระดับ 5% — ผลที่เห็นอาจเกิดจากการเลือกหุ้น/ช่วงเวลา มากกว่าจังหวะของกฎ"


def random_baseline(spec: dict, mk, result: dict, metric: str, sims: int, seed: int, trials: int = 1, cancel=None) -> dict:
    if not spec.get("strategy") or result.get("mode") != "strategy":
        raise SearchError("รันนี้ไม่มีกลยุทธ์ (พอร์ตถือเฉยๆ) จึงไม่มีจังหวะให้เทียบกับการสุ่ม")
    if metric not in BASELINE_METRICS:
        raise SearchError(f"metric ต้องเป็นหนึ่งใน {', '.join(BASELINE_METRICS)}")
    cal, base_date, _bench, opens, closes, _filled = _align(spec, mk.bars, mk.bench)
    n = len(cal)
    series = result["series"]
    if len(series) != n or [x["date"] for x in series] != cal:
        raise SearchError("วันที่ของผลรันไม่ตรงกับข้อมูลราคาปัจจุบัน — รันใหม่อีกครั้ง")
    syms = [p["symbol"] for p in spec["positions"]]
    capital = spec["initial_capital"]
    caps = {p["symbol"]: capital * p["weight"] for p in spec["positions"]}
    idle = capital - sum(caps.values())
    sims = min(sims, MAX_SIMS, MAX_WORK // max(1, len(syms) * n))
    if sims < MIN_SIMS:
        raise SearchError("ข้อมูลใหญ่เกินไปสำหรับการจำลอง (จำนวนหุ้น × จำนวนวัน) — ลดช่วงเวลาหรือจำนวนหุ้น")

    trips, zero = _trips_by_symbol(result, {d: i for i, d in enumerate(cal)}, n, syms)
    total_trips = sum(len(v) for v in trips.values())
    if total_trips == 0:
        raise SearchError("กลยุทธ์ไม่มีรอบซื้อขายเลย จึงไม่มีอะไรให้เทียบกับการสุ่ม")
    G = {s: _growth(opens[s], closes[s]) for s in syms}
    cm, sl = spec["costs"]["commission_bps"] / 1e4, spec["costs"]["slippage_bps"] / 1e4
    # สูตรเดียวกับ engine/execution.py: ซื้อ qty = เงิน/(open(1+s)(1+c)); ขายได้ qty×open(1-s)(1-c)
    buyfac = 1.0 / ((1.0 + sl) * (1.0 + cm))
    costfac = buyfac * (1.0 - sl) * (1.0 - cm)
    durs = {s: [x - e for e, x in v] for s, v in trips.items()}

    first, last = base_date, cal[-1]
    real_vals = [capital * (1.0 + p["portfolio"]) for p in series]
    actual = path_metrics(real_vals, capital, first, last)
    rep_vals = _values(trips, G, caps, idle, n, costfac, buyfac)
    replicated = path_metrics(rep_vals, capital, first, last)
    diff = replicated["total_return"] - actual["total_return"]
    tol = max(0.05, 0.15 * abs(actual["total_return"]))

    rng = random.Random(seed)
    samples = {k: [] for k in STAT_KEYS}
    for _ in range(sims):
        _check(cancel)
        plan = {s: _place(durs[s], n, rng) for s in syms}
        pm = path_metrics(_values(plan, G, caps, idle, n, costfac, buyfac), capital, first, last)
        for k in STAT_KEYS:
            if pm[k] is not None:
                samples[k].append(pm[k])

    stats = {}
    for k in STAT_KEYS:
        vs, a = samples[k], actual[k]
        row = {"actual": a, "n": len(vs)}
        if vs:
            s = sorted(vs)
            row.update({f"p{p}": MC.percentile(s, p) for p in MC.PCTS})
            row["mean"] = math.fsum(s) / len(s)
            if a is not None:
                row["beats_fraction"] = sum(1 for v in vs if v < a) / len(vs)
                row["p_as_good"] = (sum(1 for v in vs if v >= a) + 1) / (len(vs) + 1)
                row["p_bonferroni"] = min(1.0, row["p_as_good"] * max(1, trials))
        stats[k] = row

    used_metric = metric
    notes: list[str] = []
    if actual[metric] is None or not samples[metric]:
        used_metric = "total_return"
        notes.append(f"{METRIC_LABEL.get(metric, metric)} คำนวณไม่ได้ (ช่วงสั้นกว่า 1 ปี หรือไม่มี drawdown) จึงใช้ผลตอบแทนรวมแทน")
    head = stats[used_metric]
    reading = []
    if "p_as_good" in head:
        reading.append(f"กลยุทธ์นี้ดีกว่าการสุ่มจังหวะ (จำนวนรอบและระยะถือเท่ากัน) {head['beats_fraction'] * 100:.0f}% ของ {head['n']:,} ครั้งที่สุ่ม "
                       f"โดยวัดจาก {METRIC_LABEL[used_metric]}; โอกาสที่การสุ่มได้ผลดีเท่ากันหรือดีกว่า = {head['p_as_good']:.1%}")
        if trials > 1:
            reading.append(f"เมื่อคิดว่าลองมาแล้ว {trials} ชุด ค่า p ปรับแบบ Bonferroni (ขอบเขตบน) = {head['p_bonferroni']:.1%}")
        reading.append(verdict_text(head))

    warnings = []
    if spec["rebalance"]["mode"] != "none":
        warnings.append({"code": "rebalance_ignored", "message": "แบบจำลองไม่รวมการ rebalance ของพอร์ต"})
    if total_trips < FEW_TRIPS:
        warnings.append({"code": "few_trips", "message": f"มีเพียง {total_trips} รอบซื้อขาย พลังทางสถิติต่ำมาก ผลเทียบกับการสุ่มจึงไม่น่าเชื่อถือ"})
    if zero:
        warnings.append({"code": "zero_day_trips", "message": f"มี {zero} รอบที่ซื้อและขายในวันเดียว (ถูก stop ทันที) ไม่ถูกนำมาสุ่ม"})
    if abs(diff) > tol:
        warnings.append({"code": "model_mismatch", "message": f"แบบจำลองคลาดเคลื่อนจากผลจริง {diff * 100:+.1f} จุด (เช่น stop ระหว่างวันหรือ rebalance) ใช้ผลเทียบด้วยความระวัง"})
    if trials > 1:
        warnings.append({"code": "trials_adjusted", "message": f"ค่า p ถูกปรับตามจำนวนชุดที่ลอง ({trials}) แบบ Bonferroni"})
    return {
        "kind": "random_baseline", "metric": used_metric, "metric_label": METRIC_LABEL[used_metric], "sims": sims, "seed": seed,
        "trials": max(1, trials), "trips": total_trips, "stats": stats, "histogram": _hist(samples[used_metric], actual[used_metric]),
        "replication": {"actual": actual, "model": replicated, "total_return_diff": diff, "within_tolerance": abs(diff) <= tol},
        "time_in_market": result["stats"]["time_in_market"], "reading": reading, "notes": notes, "warnings": warnings,
        "caveats": [
            "เทียบเฉพาะจังหวะเข้า-ออก (จำนวนรอบ/ระยะถือเท่ากับของจริง) ไม่ได้ทดสอบว่าการเลือกหุ้นเองโชคดีหรือไม่",
            "สมมติฐานว่าง = ไม่มีข้อมูลในจังหวะ: การแจกแจงของพอร์ตสุ่มจึงรวมผลของ 'การอยู่ในตลาดเท่ากัน' ไว้แล้ว",
            "แบบจำลองประมาณ (close-to-close, ไม่จำลอง rebalance, stop ถูกแทนด้วยระยะถือ) ดูความคลาดเคลื่อนใน replication",
            "p ต่ำไม่ได้แปลว่าจะได้ผลเช่นนี้ในอนาคต: แยกได้แค่ว่าผลย้อนหลังนี้ไม่น่าเกิดจากจังหวะสุ่มในข้อมูลชุดเดียวกัน",
        ],
    }
