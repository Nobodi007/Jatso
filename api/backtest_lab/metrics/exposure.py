"""ความกระจุกตัวและการแยกความเสี่ยงตามน้ำหนัก — คัดลอกสูตรจาก Risk Center api/stocks/risk_exposure.py
(risk_decomposition: Σ = ความแปรปรวนร่วมตัวอย่าง ×252, MCR/CCR/%risk, correlation, diversification ratio)
เป็นโค้ดของแพ็กเกจนี้เอง ไม่ import; ตัด exposure/stress ที่ผูกกับพอร์ตจริงออก  การแก้ที่นี่ไม่กระทบ Risk Center
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

from . import core as E

MIN_OBS_COV = 60


def _m(x):
    return x.to_dict() if hasattr(x, "to_dict") else x


def concentration(weights: Mapping[str, float]) -> dict:
    """HHI / N_eff / top-k บนน้ำหนักของหุ้น (ปรับให้รวม 1 ในกลุ่มหุ้น)"""
    tot = math.fsum(weights.values())
    if tot <= 0:
        na = E._na(E.UNDEFINED, "", "", 0, "no equity positions")
        return {"hhi": _m(na), "effective_n": _m(na), "top1": _m(na), "top3": _m(na), "top5": _m(na)}
    we = sorted((w / tot for w in weights.values()), reverse=True)
    n = len(we)
    hhi = math.fsum(w * w for w in we)
    top = lambda k: E._ok(math.fsum(we[:k]), "share of equity", f"Σ top-{k} equity weights", n)
    return {"hhi": _m(E._ok(hhi, "index 0..1", "HHI = Σ w_i² (equity weights)", n)),
            "effective_n": _m(E._ok(1.0 / hhi, "positions", "N_eff = 1 / HHI", n)),
            "top1": _m(top(1)), "top3": _m(top(3)), "top5": _m(top(5))}


def _complete(r):
    return bool(r) and all(v is not None and math.isfinite(v) for v in r)


def risk_decomposition(w_nav: Mapping[str, float], returns: Mapping[str, Sequence[float | None]]) -> dict:
    """Historical-covariance decomposition ของน้ำหนักที่ให้มา (ถือคงที่ตลอดช่วง)"""
    f_vol = "σ_p = √(wᵀΣw), Σ = sample covariance ×252, w = target NAV weights (cash has zero variance)"
    syms, excluded = [], []
    n = max((len(v) for v in returns.values() if v), default=0)
    for s in w_nav:
        r = returns.get(s)
        if not r or len(r) != n:
            excluded.append({"symbol": s, "reason": "no return history"})
        elif not _complete(r):
            excluded.append({"symbol": s, "reason": "incomplete price history in window"})
        else:
            syms.append(s)
    if not syms or n < MIN_OBS_COV:
        na = E._na(E.INSUFFICIENT, "", f_vol, n, f"need ≥{MIN_OBS_COV} aligned observations and priced holdings")
        return {"portfolio_volatility": _m(na), "contributions": [], "correlation": None, "excluded": excluded}
    k = len(syms)
    cov = [[E._cov(returns[a], returns[b]) * E.TRADING_DAYS for b in syms] for a in syms]
    w = [w_nav[s] for s in syms]
    sw = [math.fsum(cov[i][j] * w[j] for j in range(k)) for i in range(k)]
    var = math.fsum(w[i] * sw[i] for i in range(k))
    if var <= E.EPS:
        na = E._na(E.UNDEFINED, "", f_vol, n, "portfolio variance is zero")
        return {"portfolio_volatility": _m(na), "contributions": [], "correlation": None, "excluded": excluded}
    sig = math.sqrt(var)
    limited = n < E.MIN_OBS_FULL or bool(excluded)
    vol = E.Metric(sig, E.LIMITED if limited else E.OK, "annualized volatility", f_vol, n,
                   "short window or excluded holdings" if limited else None)
    vols = [math.sqrt(max(cov[i][i], 0.0)) for i in range(k)]
    contrib = []
    for i, s in enumerate(syms):
        mcr = sw[i] / sig
        ccr = w[i] * mcr
        contrib.append({"symbol": s, "weight_nav": w[i], "volatility": vols[i], "mcr": mcr, "ccr": ccr,
                        "pct_of_risk": ccr / sig})
    contrib.sort(key=lambda r: -r["pct_of_risk"])
    corr = [[(cov[i][j] / (vols[i] * vols[j])) if vols[i] > E.EPS and vols[j] > E.EPS else None
             for j in range(k)] for i in range(k)]
    pairs = sorted(({"a": syms[i], "b": syms[j], "correlation": corr[i][j]}
                    for i in range(k) for j in range(i + 1, k) if corr[i][j] is not None),
                   key=lambda p: -p["correlation"])
    if pairs:
        avgc = E._ok(math.fsum(p["correlation"] for p in pairs) / len(pairs), "correlation",
                     "mean of pairwise correlations", n)
    else:
        avgc = E._na(E.UNDEFINED, "correlation", "mean of pairwise correlations", n, "need ≥2 priced holdings")
    sum_wv = math.fsum(w[i] * vols[i] for i in range(k))
    return {"portfolio_volatility": _m(vol),
            "diversification_ratio": _m(E._ok(sum_wv / sig, "ratio", "Σ w_i σ_i / σ_p", n)),
            "avg_pairwise_correlation": _m(avgc),
            "contributions": contrib, "correlation": {"symbols": syms, "matrix": corr},
            "top_pairs": pairs[:5], "excluded": excluded}


def build(targets: Mapping[str, float], closes: Mapping[str, Sequence[float]], avg_weights: Mapping[str, float],
          final_weights: Mapping[str, float]) -> dict:
    """targets = น้ำหนักเป้าหมายของ spec; closes = ราคาปิดรายวัน (เติมช่องว่างแล้ว)"""
    rets = {s: [c[i] / c[i - 1] - 1.0 for i in range(1, len(c))] for s, c in closes.items()}
    return {"note": "ตามน้ำหนักเป้าหมายของ spec ถือคงที่ ไม่สะท้อนจังหวะเข้า/ออกของกลยุทธ์ (ดู attribution.pct_of_risk สำหรับความเสี่ยงที่เกิดจริง)",
            "target": concentration(targets), "average_held": concentration(avg_weights),
            "final": concentration(final_weights),
            "static_decomposition": risk_decomposition(dict(targets), rets)}
