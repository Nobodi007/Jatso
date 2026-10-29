"""วัน/สัปดาห์/เดือน/ปี ที่ดี-แย่สุด พร้อมผลของ S&P 500 ในช่วงเดียวกัน"""
from __future__ import annotations

from datetime import date
from typing import Sequence

from .core import cumulative_return, period_returns


def best_worst_days(rp: Sequence[float], rb: Sequence[float], dates_r: Sequence[date], n: int = 5) -> dict:
    idx = sorted(range(len(rp)), key=rp.__getitem__)
    def row(i):
        return {"date": dates_r[i].isoformat(), "portfolio": rp[i], "benchmark": rb[i], "active": rp[i] - rb[i]}
    return {"worst": [row(i) for i in idx[:n]], "best": [row(i) for i in reversed(idx[-n:])], "n": n}


def worst_best_periods(rp, rb, dates_r, freq: str) -> dict:
    """freq 'W' | 'M' — แต่ละงวดรวมผลทบต้นรายวัน; งวดแรก/ท้ายอาจไม่เต็ม (ดู days)"""
    p = {x["period"]: x for x in period_returns(rp, dates_r, freq)}
    b = {x["period"]: x for x in period_returns(rb, dates_r, freq)}
    rows = [{"period": k, "portfolio": v["return"], "benchmark": b[k]["return"],
             "active": v["return"] - b[k]["return"], "days": v["days"]} for k, v in p.items()]
    return {"worst": min(rows, key=lambda r: r["portfolio"]), "best": max(rows, key=lambda r: r["portfolio"])}


def calendar_year_returns(series: dict[str, Sequence[float]], dates_r: Sequence[date]) -> list[dict]:
    """series: ชื่อ -> ผลตอบแทนรายวันที่ตรงกับ dates_r ; คืนรายปีปฏิทิน (ปีแรก/ท้ายอาจไม่เต็ม)"""
    years: dict[int, dict] = {}
    for name, r in series.items():
        buckets: dict[int, list[float]] = {}
        for v, d in zip(r, dates_r):
            buckets.setdefault(d.year, []).append(v)
        for y, vals in buckets.items():
            row = years.setdefault(y, {"year": y, "days": len(vals)})
            row[name] = cumulative_return(vals)
    return [years[y] for y in sorted(years)]
