"""การจับคู่คำสั่ง: ราคาเปิด ± slippage, ค่าคอมมิชชัน, หุ้นเศษ

ซื้อ: ราคา = open×(1+s)  ค่าคอม = shares×ราคา×c      ขาย: ราคา = open×(1−s)  ค่าคอม = shares×ราคา×c
slippage_cost = shares×open×s (ต้นทุนแฝงเทียบราคาเปิด) แยกรายงานจากค่าคอม
"""
from __future__ import annotations

from .. import config as C


class Account:
    """สถานะบัญชี (เงินสด + จำนวนหุ้น) — ไม่มีดอกเบี้ยเงินสด"""

    def __init__(self, cash: float, commission_bps: float, slippage_bps: float):
        self.cash = cash
        self.shares: dict[str, float] = {}
        self.c = commission_bps / 1e4
        self.s = slippage_bps / 1e4
        self.trades: list[dict] = []
        self.commission_paid = 0.0
        self.slippage_cost = 0.0
        self.traded_notional = 0.0          # ไม่นับการซื้อเริ่มต้น (ใช้คำนวณ turnover)

    def value(self, prices: dict[str, float]) -> float:
        return self.cash + sum(q * prices[s] for s, q in self.shares.items())

    def buy_outlay(self, symbol: str, open_px: float, outlay: float, day: str, reason: str) -> None:
        """ซื้อให้ใช้เงินรวมค่าคอม = outlay พอดี"""
        px = open_px * (1 + self.s)
        qty = outlay / (px * (1 + self.c))
        if qty <= 0 or outlay < C.MIN_TRADE_NOTIONAL:
            return
        notional = qty * px
        comm = notional * self.c
        self.cash -= notional + comm
        self.shares[symbol] = self.shares.get(symbol, 0.0) + qty
        self._log(day, symbol, "buy", qty, px, notional, comm, qty * open_px * self.s, reason)

    def sell_qty(self, symbol: str, open_px: float, qty: float, day: str, reason: str) -> None:
        qty = min(qty, self.shares.get(symbol, 0.0))
        px = open_px * (1 - self.s)
        notional = qty * px
        if qty <= 0 or notional < C.MIN_TRADE_NOTIONAL:
            return
        comm = notional * self.c
        self.cash += notional - comm
        self.shares[symbol] -= qty
        if self.shares[symbol] < 1e-12:
            del self.shares[symbol]
        self._log(day, symbol, "sell", qty, px, notional, comm, qty * open_px * self.s, reason)

    def _log(self, day, symbol, side, qty, px, notional, comm, slip, reason):
        self.commission_paid += comm
        self.slippage_cost += slip
        if reason != "initial":
            self.traded_notional += notional
        self.trades.append({"date": day, "symbol": symbol, "side": side, "shares": qty, "price": px,
                            "notional": notional, "commission": comm, "slippage_cost": slip, "reason": reason})
