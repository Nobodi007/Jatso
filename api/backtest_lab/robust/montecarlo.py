"""Monte Carlo (block bootstrap) — จำลองความไม่แน่นอนของผลตอบแทน "จากรูปแบบที่เคยเกิดขึ้น" ไม่ใช่การพยากรณ์

วิธี: สุ่มบล็อกของผลตอบแทนรายวันที่เคยเกิดจริง (circular moving-block, เริ่มสุ่มทุกบล็อก) มาต่อกันเป็นเส้นทางใหม่
- ใช้ดัชนีวันเดียวกันกับผลตอบแทนของพอร์ตและ S&P 500 (resample คู่กัน) เพื่อคงความสัมพันธ์ในวันเดียวกัน
- บล็อกคงความสัมพันธ์ระยะสั้น (ความผันผวนเป็นกลุ่ม/โมเมนตัมช่วงสั้น) ไว้ ส่วนลำดับยาวถูกสลับ
- สมมติว่าอนาคตมีการแจกแจงผลตอบแทนคล้ายอดีตที่ใช้ทดสอบ (ถ้าช่วงนั้นเป็นตลาดขาขึ้นยาว ผลจะดูดีเกินจริง)
- resample "ผลตอบแทนรายวันของพอร์ตที่รันแล้ว" ไม่ได้รันกฎกลยุทธ์ซ้ำบนราคาใหม่
- ทำซ้ำได้: seed เดียวกัน = ผลเดิม
"""
from __future__ import annotations

import math
import random

MAX_SIMS = 5000
MAX_WORK = 12_000_000            # sims × horizon (กันกินเวลา CPU)
TRADING_DAYS = 252
PCTS = (5, 25, 50, 75, 95)


class MCError(ValueError):
    pass


def returns_from_series(series: list[dict], key: str) -> list[float]:
    v = [1.0 + s[key] for s in series]
    return [v[0] - 1.0] + [v[i] / v[i - 1] - 1.0 for i in range(1, len(v))]


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _dist(vals: list[float]) -> dict:
    s = sorted(vals)
    out = {f"p{p}": percentile(s, p) for p in PCTS}
    out["mean"] = math.fsum(s) / len(s)
    return out


def simulate(rp: list[float], rb: list[float], *, sims: int = 2000, horizon: int | None = None,
             block: int = 21, seed: int = 1, bands: int = 60, actual_final: float | None = None) -> dict:
    n = len(rp)
    if n < 60 or len(rb) != n:
        raise MCError("ข้อมูลผลตอบแทนสั้นเกินไปสำหรับ Monte Carlo (ต้องมีอย่างน้อย 60 วัน)")
    horizon = horizon or n
    if not (21 <= horizon <= 30 * TRADING_DAYS):
        raise MCError("ช่วงจำลองต้องอยู่ระหว่าง 21 วัน ถึง 30 ปี")
    if not (100 <= sims <= MAX_SIMS):
        raise MCError(f"จำนวนรอบจำลองต้องอยู่ระหว่าง 100 ถึง {MAX_SIMS}")
    if not (1 <= block <= TRADING_DAYS):
        raise MCError("ความยาวบล็อกต้องอยู่ระหว่าง 1 ถึง 252 วัน")
    if sims * horizon > MAX_WORK:
        raise MCError("งานใหญ่เกินกำหนด (ลดจำนวนรอบหรือช่วงจำลอง)")
    block = min(block, n)
    rng = random.Random(seed)
    nb = max(2, min(bands, horizon))
    cps = sorted({round(i * (horizon - 1) / (nb - 1)) for i in range(nb)})
    is_cp = [False] * horizon
    for c in cps:
        is_cp[c] = True

    finals, bfinals, mdds = [], [], []
    fan = [[] for _ in cps]
    for _ in range(sims):
        v = vb = peak = 1.0
        mdd = 0.0
        pos = ci = 0
        while pos < horizon:
            start = rng.randrange(n)
            for j in range(min(block, horizon - pos)):
                idx = (start + j) % n
                v *= 1.0 + rp[idx]
                vb *= 1.0 + rb[idx]
                if v > peak:
                    peak = v
                else:
                    d = v / peak - 1.0
                    if d < mdd:
                        mdd = d
                if is_cp[pos + j]:
                    fan[ci].append(v - 1.0)
                    ci += 1
            pos += block
        finals.append(v - 1.0)
        bfinals.append(vb - 1.0)
        mdds.append(mdd)

    yrs = horizon / TRADING_DAYS
    cagr = [(1.0 + f) ** (1.0 / yrs) - 1.0 if f > -1 else -1.0 for f in finals]
    N = float(sims)
    out = {
        "params": {"sims": sims, "horizon_days": horizon, "horizon_years": round(yrs, 2), "block_days": block, "seed": seed,
                   "method": "circular moving-block bootstrap (resample พอร์ตและ S&P 500 คู่กัน)", "source_days": n},
        "final_return": _dist(finals), "cagr": _dist(cagr), "max_drawdown": _dist(mdds),
        "benchmark_final_return": _dist(bfinals),
        "prob": {
            "loss": sum(1 for f in finals if f < 0) / N,
            "beat_benchmark": sum(1 for a, b in zip(finals, bfinals) if a > b) / N,
            "drawdown_worse_20": sum(1 for m in mdds if m <= -0.20) / N,
            "drawdown_worse_30": sum(1 for m in mdds if m <= -0.30) / N,
            "drawdown_worse_50": sum(1 for m in mdds if m <= -0.50) / N,
        },
        "fan": {"x": cps, **{f"p{p}": [percentile(sorted(col), p) for col in fan] for p in PCTS}},
        "labels": ["monte_carlo_simulation", "not_a_forecast"],
        "caveats": [
            "เป็นการจำลองจากรูปแบบผลตอบแทนที่เคยเกิดขึ้นในช่วงที่ทดสอบ ไม่ใช่การพยากรณ์อนาคต",
            "ถ้าช่วงที่ทดสอบเป็นขาขึ้นยาว ผลจำลองจะดูดีเกินจริงตามไปด้วย (สมมติอนาคตคล้ายอดีต)",
            "สุ่มจากผลตอบแทนรายวันของพอร์ตที่รันแล้ว ไม่ได้รันกฎกลยุทธ์ซ้ำบนราคาใหม่ และไม่รวมเหตุการณ์ที่ไม่เคยอยู่ในข้อมูล",
            "ไม่รวมหุ้นที่ถูกถอนจากตลาด (survivorship bias) ซึ่งทำให้ผลจริงอาจแย่กว่า",
        ],
    }
    if actual_final is not None and horizon == n:
        out["actual"] = {"final_return": actual_final, "percentile_rank": sum(1 for f in finals if f <= actual_final) / N}
    return out
