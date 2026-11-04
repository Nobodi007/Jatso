"""ผลตอบแทนและความเสี่ยงแยกรายหุ้น — เขียนใหม่ทั้งหมดจากบันทึกการซื้อขายของ engine (ไม่ใช่โค้ดคัดลอกจาก Risk Center
เพราะ Risk Center ใช้พอร์ตจริง/ledger ซึ่ง Lab ไม่มี)

หลักที่ล็อกไว้ (มี test ตรวจว่าบวกกลับได้พอดี)
1) P&L รายหุ้น (USD)  net_i = Σขาย(เงินสุทธิ) − Σซื้อ(เงินสุทธิ) + หุ้นคงเหลือ × ราคาปิดวันสุดท้าย
   และ Σ_i net_i = มูลค่าพอร์ตสิ้นสุด − เงินที่ใส่ทั้งหมด (เงินต้น + เงินเติม)  (เงินสดไม่มีดอกเบี้ย จึงไม่มี P&L ฝั่งเงินสด)
   แยกต้นทุน: gross = net + ค่าคอม + slippage  (slippage คิดเทียบราคาเปิด ตามที่ engine ล็อก)
2) การมีส่วนร่วมต่อผลตอบแทนรวม = net_i / เงินต้น  (บวกกันได้เท่ากับผลตอบแทนรวมของพอร์ต — เป็นการบวกแบบเงินต้นคงที่
   ไม่ใช่ผลตอบแทนถ่วงเวลา)
3) ผลตอบแทนรายวันของพอร์ต = Σ_i c_{i,t} โดย c_{i,t} = (มูลค่าหุ้น i ปลายวัน − ต้นวัน − เงินที่ใส่สุทธิวันนั้น) / มูลค่าพอร์ตวันก่อน
   ความเสี่ยงที่เกิดจริง: %risk_i = Cov(c_i, r_p) / Var(r_p)  (บวกกันได้ 100% พอดี เพราะ Σ c_i = r_p)
   ใช้ได้กับกลยุทธ์ที่สลับถือ/ไม่ถือ (ต่างจากการแยกความเสี่ยงด้วยน้ำหนักคงที่)
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

from . import core as E

MIN_OBS = 60


def _shares_by_day(sym: str, trades: Sequence[dict], cal: Sequence[str]) -> tuple[list[float], list[float]]:
    """(จำนวนหุ้น ณ ปิดวัน k, เงินสุทธิที่ลงในหุ้นนี้วัน k [ซื้อ + , ขาย −])"""
    idx = {d: i for i, d in enumerate(cal)}
    dsh, dcf = [0.0] * len(cal), [0.0] * len(cal)
    for t in trades:
        if t["symbol"] != sym:
            continue
        k = idx[t["date"]]
        if t["side"] == "buy":
            dsh[k] += t["shares"]
            dcf[k] += t["notional"] + t["commission"]
        else:
            dsh[k] -= t["shares"]
            dcf[k] -= t["notional"] - t["commission"]
    sh, run = [], 0.0
    for v in dsh:
        run += v
        sh.append(run if abs(run) > 1e-9 else 0.0)
    return sh, dcf


def build(syms: Sequence[str], trades: Sequence[dict], cal: Sequence[str], closes: Mapping[str, Sequence[float]],
          capital: float, eq: Sequence[float], rp: Sequence[float], flows: Sequence[float] | None = None) -> dict:
    """flows[k] = เงินใหม่ที่เข้าพอร์ตที่เปิดวัน k (DCA แท้) — ไม่ระบุ = ไม่มีเงินเข้า/ออก (พฤติกรรมเดิมทุกประการ)
    ฐานของผลตอบแทนรายวัน = มูลค่าวันก่อน + เงินที่เข้าวันนั้น (ตรงกับผลตอบแทนถ่วงเวลาของ engine)"""
    N = len(cal)
    fl = list(flows) if flows is not None else [0.0] * N
    money_in = capital + math.fsum(fl)
    rows, contrib, avg_w = [], {}, {}
    vals = {}
    total_net = 0.0
    for s in syms:
        sh, cf = _shares_by_day(s, trades, cal)
        v = [sh[k] * closes[s][k] for k in range(N)]
        vals[s] = v
        buys = sum(t["notional"] for t in trades if t["symbol"] == s and t["side"] == "buy")
        sells = sum(t["notional"] for t in trades if t["symbol"] == s and t["side"] == "sell")
        comm = sum(t["commission"] for t in trades if t["symbol"] == s)
        slip = sum(t["slippage_cost"] for t in trades if t["symbol"] == s)
        net = sells - buys - comm + v[-1]
        total_net += net
        prev = [0.0] + v[:-1]
        base = [capital + fl[0]] + [eq[k - 1] + fl[k] for k in range(1, N)]
        contrib[s] = [(v[k] - prev[k] - cf[k]) / base[k] for k in range(N)]
        avg_w[s] = math.fsum(v[k] / eq[k] for k in range(N)) / N
        n_trades = sum(1 for t in trades if t["symbol"] == s)
        rows.append({"symbol": s, "net_pnl": net, "contribution": net / money_in, "gross_pnl": net + comm + slip,
                     "commission": comm, "slippage_cost": slip, "final_value": v[-1], "final_weight": v[-1] / eq[-1],
                     "avg_weight": avg_w[s], "trade_count": n_trades})
    # ความเสี่ยงที่เกิดจริง
    var_p = E._var(list(rp)) if N >= 2 else 0.0
    risk_ok = N >= MIN_OBS and var_p > E.EPS
    for r in rows:
        c = contrib[r["symbol"]]
        r["pct_of_risk"] = (E._cov(c, list(rp)) / var_p) if risk_ok else None
        r["risk_volatility_contribution"] = (E._cov(c, list(rp)) / var_p * math.sqrt(var_p) * E.SQRT_T) if risk_ok else None
    rows.sort(key=lambda r: -r["net_pnl"])
    final_pnl = eq[-1] - money_in
    return {
        "method": "per-stock P&L from trade log; Σ net = final value − initial capital; %risk = Cov(c_i, r_p)/Var(r_p) from daily contributions",
        "positions": rows,
        "totals": {"net_pnl": total_net, "portfolio_pnl": final_pnl, "reconciliation_error": total_net - final_pnl,
                   "total_return": final_pnl / money_in, "sum_contribution": total_net / money_in, "money_in": money_in,
                   "commission": sum(r["commission"] for r in rows), "slippage_cost": sum(r["slippage_cost"] for r in rows),
                   "pct_risk_sum": (sum(r["pct_of_risk"] for r in rows) if risk_ok else None)},
        "risk_status": "ok" if risk_ok else "insufficient_data",
        "n_obs": N,
        "_daily_contrib": contrib,
    }
