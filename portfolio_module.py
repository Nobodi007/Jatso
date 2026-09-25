# =========================================================================
# portfolio_module.py
# PORTFOLIO / WATCHLIST ENGINE — Holdings, Avg Cost, Realized/Unrealized P&L,
# Allocation %, Transaction History, Deposit/Withdrawal
# =========================================================================
#
# This file is fully SELF-CONTAINED — it does not import anything from your
# main xspring_dealer_suite.py, so there is no circular-import risk.
# It duplicates a few small formatting helpers (fmt_baht, fmt_coin, section,
# metric_card, WIDE, comma_number_input) so it can run standalone. These
# reuse the SAME CSS class names your main file already injects via
# THEME_CSS (e.g. ".xs-sec"), so visual styling matches automatically —
# nothing extra to configure there.
#
# HOW TO INSTALL
# ---------------
# 1) Put this file next to your main script, e.g.:
#       xspring_dealer_suite.py
#       portfolio_module.py
#
# 2) In xspring_dealer_suite.py, near your other imports at the top, add:
#
#       from portfolio_module import (
#           render_portfolio_panel,
#           render_portfolio_mini_card,
#           compute_portfolio_ledger,
#           portfolio_summary,
#           unified_transaction_history,
#           do_withdraw,
#           log_cash_flow,
#       )
#
# 3) Apply these 4 small patches to your EXISTING functions in the main file:
#
#    a) sim_defaults() — add two keys to the returned dict:
#           "initial_capital": 1_000_000.0,
#           "cash_ledger": [],
#
#    b) sim_normalize_state() — add near the other sim.setdefault(...) calls:
#           sim.setdefault("initial_capital", 1_000_000.0)
#           sim.setdefault("cash_ledger", [])
#
#    c) _do_deposit() — right after the line
#           sim["customer_thb"] = float(sim.get("customer_thb", 1_000_000.0)) + amt
#       add:
#           log_cash_flow(sim, "deposit", amt)
#
#    d) render_tab4() (Wallet) — call, anywhere in the function:
#           render_portfolio_panel(sim, price_thb_map, can_trade_fn=can_trade)
#
# 4) Optional cross-tab hooks — in render_tab1() (Backtest) and
#    render_tab2() (Planner), call:
#           render_portfolio_mini_card(sim, {asset: price}, asset)
#    (see usage examples at the bottom of this file for exact placement)
#
# That's it — no other changes needed. can_trade_fn is the ONLY thing wired
# in from your app, because role logic (can_trade()) is app-specific; every
# other helper below is fully independent.
# =========================================================================

from __future__ import annotations

import re
from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# Default trading fee used when the caller doesn't pass fee_pct explicitly.
# Pass fee_pct=LOCAL_TRADING_FEE_PCT (your host constant) into the functions
# below if you ever change your app's fee and want this module to follow it
# automatically instead of relying on this local default.
DEFAULT_FEE_PCT = 0.0025


# -------------------------------------------------------------------------
# 0. SELF-CONTAINED UI / FORMAT HELPERS (duplicated from host, decoupled)
# -------------------------------------------------------------------------

def _sv_tuple() -> tuple[int, int]:
    try:
        nums = re.findall(r"\d+", st.__version__)
        return (int(nums[0]), int(nums[1]))
    except Exception:
        return (1, 40)


WIDE = {"width": "stretch"} if _sv_tuple() >= (1, 49) else {"use_container_width": True}


def fmt_num(value: Any, force_sign: bool = False) -> str:
    value = 0.0 if pd.isna(value) else float(value)
    sign = "- " if value < 0 else ("+ " if force_sign else "")
    v = abs(value)
    if v >= 1_000_000_000:
        num = f"{v / 1_000_000_000:,.2f}B"
    elif v >= 1_000_000:
        num = f"{v / 1_000_000:,.2f}M"
    elif v >= 1_000:
        num = f"{v / 1_000:,.1f}K"
    else:
        num = f"{v:,.2f}"
    return f"{sign}{num}"


def fmt_baht(value: Any, force_sign: bool = False) -> str:
    return f"฿ {fmt_num(value, force_sign)}"


def fmt_coin(value: float, symbol: str = "") -> str:
    v = abs(float(value))
    d = 6 if v < 1 else (4 if v < 1000 else 2)
    return f"{value:,.{d}f}" + (f" {symbol}" if symbol else "")


def section(title: str) -> None:
    """Reuses the '.xs-sec' CSS class already injected by your main file's
    THEME_CSS — styling matches automatically, no extra CSS needed here."""
    st.markdown(f'<div class="xs-sec">{title}</div>', unsafe_allow_html=True)


def _colored_metric(label: str, display_value: str, raw_value: Optional[float] = None,
                    sub_text: Optional[str] = None, font_size: str = "1.5rem") -> None:
    color = "#EAECEF" if raw_value is None else ("#0ecb81" if raw_value >= 0 else "#f6465d")
    sub = (f'<div style="font-size:.75rem;color:{color};opacity:.85;margin-top:3px;">{sub_text}</div>'
           if sub_text else "")
    st.markdown(
        f'<div style="padding:.35rem 0 .6rem 0;">'
        f'<div style="font-size:.8rem;color:#848e9c;margin-bottom:4px;">{label}</div>'
        f'<div style="font-size:{font_size};font-weight:700;color:{color};'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
        f'line-height:1.25;">{display_value}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


def metric_card(col, label: str, value: str, raw_value: Optional[float] = None,
                sub_text: Optional[str] = None, font_size: str = "1.5rem") -> None:
    with col:
        with st.container(border=True):
            _colored_metric(label, value, raw_value, sub_text, font_size)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv().encode("utf-8-sig")


def _reformat_comma_key(key: str) -> None:
    raw = st.session_state.get(key, "")
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
        st.session_state[key] = f"{num:,.0f}" if num == int(num) else f"{num:,.2f}"
    except ValueError:
        pass


def comma_number_input(label: str, value: float, min_value: Optional[float] = None,
                       key: Optional[str] = None, help: Optional[str] = None,
                       disabled: bool = False) -> float:
    if key not in st.session_state:
        st.session_state[key] = f"{value:,.0f}"
    st.text_input(label, key=key, help=help, disabled=disabled,
                  on_change=_reformat_comma_key, args=(key,))
    cleaned = st.session_state[key].replace(",", "").replace(" ", "").strip()
    try:
        num = float(cleaned)
    except ValueError:
        num = float(value)
    if min_value is not None and num < min_value:
        num = float(min_value)
    return num


def _open_deposit_flag() -> None:
    """Sets the same session_state keys your existing deposit_dialog()
    mechanism already checks for (open_deposit / dep_error), so your host
    file's dialog opens without needing to import anything from it."""
    st.session_state["open_deposit"] = True
    st.session_state["dep_error"] = None


# -------------------------------------------------------------------------
# 1. RAW TRADE FILTERING
# -------------------------------------------------------------------------

def portfolio_own_trades(sim: dict) -> list[dict]:
    """คำสั่งซื้อ/ขายที่เป็นของ 'ลูกค้าเจ้าของกระเป๋าจำลอง' เท่านั้น
    (ไม่รวมออเดอร์ของลูกค้าจำลองรายอื่นจาก Batch Random ซึ่งจะมี field 'Customer' ติดมา
    เพราะ run_random_batch เรียก execute_order ด้วย affect_wallet=False)"""
    out = []
    for o in sim.get("orders", []):
        if not isinstance(o, dict):
            continue
        if "Customer" in o:            # = ลูกค้าจำลองรายอื่นในตลาด ไม่ใช่เจ้าของกระเป๋า
            continue
        if not o.get("เหรียญ") or not o.get("ฝั่ง"):
            continue
        out.append(o)
    return out


# -------------------------------------------------------------------------
# 2. WEIGHTED-AVERAGE COST BASIS ENGINE
# -------------------------------------------------------------------------

def compute_portfolio_ledger(sim: dict, fee_pct: float = DEFAULT_FEE_PCT) -> dict[str, dict[str, float]]:
    """เดินบัญชีต้นทุนแบบ Weighted-Average Cost ทีละออเดอร์ตามลำดับเวลา

    คืนค่า {เหรียญ: {qty, cost_thb, realized_pnl, fees_thb, n_buy, n_sell,
                     invested_thb, withdrawn_thb}}
    - qty / cost_thb  = สิ่งที่ 'ยังถืออยู่' ตอนนี้ (หลังหักส่วนที่ขายไปแล้วตามต้นทุนเฉลี่ย)
    - realized_pnl    = กำไร/ขาดทุนที่รับรู้แล้วจากการขาย (สุทธิค่าธรรมเนียมทั้งสองขา)
    - fees_thb        = ค่าธรรมเนียมซื้อขายสะสมของเหรียญนี้ (ข้อมูลอ้างอิง ไม่ใช่ตัวหักต้นทุนซ้ำ)
    """
    trades = sorted(portfolio_own_trades(sim), key=lambda r: str(r.get("วันที่", "")))
    book: dict[str, dict[str, float]] = {}
    for r in trades:
        asset = str(r.get("เหรียญ"))
        side = r.get("ฝั่ง")
        amt = float(r.get("มูลค่า (บาท)") or 0.0)
        coins = float(r.get("เหรียญที่ส่งมอบ") or 0.0)
        if amt <= 0 or coins <= 0:
            continue
        fee = amt * fee_pct
        b = book.setdefault(asset, dict(
            qty=0.0, cost_thb=0.0, realized_pnl=0.0, fees_thb=0.0,
            n_buy=0, n_sell=0, invested_thb=0.0, withdrawn_thb=0.0,
        ))
        b["fees_thb"] += fee
        if side == "ซื้อ":
            b["qty"] += coins
            b["cost_thb"] += amt          # cash outlay ทั้งหมด (รวมค่าธรรมเนียมแล้ว) = ต้นทุน
            b["invested_thb"] += amt
            b["n_buy"] += 1
        else:  # ขาย
            avg_cost = (b["cost_thb"] / b["qty"]) if b["qty"] > 1e-12 else 0.0
            sell_coins = min(coins, b["qty"])
            cost_removed = avg_cost * sell_coins
            proceeds = amt * (1 - fee_pct)   # เงินสดที่ได้จริงหลังหักค่าธรรมเนียม
            b["realized_pnl"] += proceeds - cost_removed
            b["withdrawn_thb"] += proceeds
            b["qty"] = max(0.0, b["qty"] - sell_coins)
            b["cost_thb"] = max(0.0, b["cost_thb"] - cost_removed)
            b["n_sell"] += 1
    return book


# -------------------------------------------------------------------------
# 3. CASH LEDGER (deposit / withdrawal)
# -------------------------------------------------------------------------

def log_cash_flow(sim: dict, kind: str, amount: float, note: str = "") -> None:
    sim.setdefault("cash_ledger", []).append({
        "date": pd.Timestamp.now(tz="Asia/Bangkok").strftime("%Y-%m-%d %H:%M:%S"),
        "type": kind, "amount": float(amount), "note": note,
    })


def do_withdraw(sim: dict, amount: float) -> tuple[bool, str]:
    amount = float(amount or 0.0)
    cash = float(sim.get("customer_thb", 0.0))
    if amount <= 0:
        return False, "กรอกจำนวนเงินที่มากกว่า 0"
    if amount > cash + 1e-9:
        return False, f"ยอดเงินบาทไม่พอ (มี {fmt_baht(cash)})"
    sim["customer_thb"] = cash - amount
    log_cash_flow(sim, "withdrawal", amount)
    return True, f"ถอนเงิน {fmt_baht(amount)} สำเร็จ"


# -------------------------------------------------------------------------
# 4. PORTFOLIO SUMMARY (holdings + allocation + total P&L incl. deposits)
# -------------------------------------------------------------------------

def portfolio_summary(sim: dict, price_thb: dict[str, float],
                      fee_pct: float = DEFAULT_FEE_PCT) -> dict[str, Any]:
    book = compute_portfolio_ledger(sim, fee_pct=fee_pct)
    cash = float(sim.get("customer_thb", 0.0))

    rows = []
    total_holdings_val = 0.0
    total_unreal = 0.0
    total_realized = 0.0
    total_fees = 0.0
    total_invested = 0.0

    for asset, b in book.items():
        px = float(price_thb.get(asset, 0.0))
        val = b["qty"] * px
        avg_cost = (b["cost_thb"] / b["qty"]) if b["qty"] > 1e-9 else 0.0
        unreal = val - b["cost_thb"]
        unreal_pct = (unreal / b["cost_thb"] * 100) if b["cost_thb"] > 1e-9 else 0.0

        total_holdings_val += val
        total_unreal += unreal
        total_realized += b["realized_pnl"]
        total_fees += b["fees_thb"]
        total_invested += b["invested_thb"]

        if b["qty"] > 1e-9 or b["n_sell"] > 0:
            rows.append(dict(
                asset=asset, qty=b["qty"], avg_cost=avg_cost, price=px, value=val,
                cost_thb=b["cost_thb"], unrealized_pnl=unreal, unrealized_pct=unreal_pct,
                realized_pnl=b["realized_pnl"], fees_thb=b["fees_thb"],
                n_buy=b["n_buy"], n_sell=b["n_sell"],
            ))

    total_value = cash + total_holdings_val
    for r in rows:
        r["allocation_pct"] = (r["value"] / total_value * 100) if total_value > 0 else 0.0

    initial_capital = float(sim.get("initial_capital", 1_000_000.0))
    ledger = sim.get("cash_ledger", [])
    deposits = sum(c["amount"] for c in ledger if c.get("type") == "deposit")
    withdrawals = sum(c["amount"] for c in ledger if c.get("type") == "withdrawal")
    net_contributed = initial_capital + deposits - withdrawals
    total_pnl = total_value - net_contributed
    total_pnl_pct = (total_pnl / net_contributed * 100) if net_contributed > 0 else 0.0

    return dict(
        rows=pd.DataFrame(rows), cash=cash, total_holdings_val=total_holdings_val,
        total_value=total_value, total_unrealized=total_unreal,
        total_realized=total_realized, total_fees=total_fees,
        total_invested=total_invested, net_contributed=net_contributed,
        total_pnl=total_pnl, total_pnl_pct=total_pnl_pct,
        deposits=deposits, withdrawals=withdrawals, initial_capital=initial_capital,
    )


# -------------------------------------------------------------------------
# 5. UNIFIED TRANSACTION HISTORY (trades + cash flow)
# -------------------------------------------------------------------------

def unified_transaction_history(sim: dict, fee_pct: float = DEFAULT_FEE_PCT) -> pd.DataFrame:
    rows = []
    for r in portfolio_own_trades(sim):
        rows.append(dict(
            วันที่=r.get("วันที่"), ประเภท=r.get("ฝั่ง"), เหรียญ=r.get("เหรียญ"),
            จำนวนเหรียญ=r.get("เหรียญที่ส่งมอบ"), ราคา=r.get("ราคาที่ลูกค้าได้"),
            มูลค่า_บาท=r.get("มูลค่า (บาท)"),
            ค่าธรรมเนียม=(float(r.get("มูลค่า (บาท)") or 0) * fee_pct),
            แหล่งที่มา=r.get("Source", "Web"),
        ))
    for c in sim.get("cash_ledger", []):
        label = "ฝากเงิน" if c.get("type") == "deposit" else "ถอนเงิน"
        rows.append(dict(
            วันที่=c.get("date"), ประเภท=label, เหรียญ="THB",
            จำนวนเหรียญ=None, ราคา=None, มูลค่า_บาท=c.get("amount"),
            ค่าธรรมเนียม=0.0, แหล่งที่มา="Wallet",
        ))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["_sort"] = pd.to_datetime(df["วันที่"], errors="coerce")
    return df.sort_values("_sort", ascending=False).drop(columns=["_sort"])


# -------------------------------------------------------------------------
# 6. RENDER — full Portfolio panel (put in Wallet / Tab 4)
# -------------------------------------------------------------------------

def render_portfolio_panel(
    sim: dict,
    price_thb: dict[str, float],
    *,
    fee_pct: float = DEFAULT_FEE_PCT,
    can_trade_fn: Optional[Callable[[], bool]] = None,
) -> None:
    """can_trade_fn: pass your host's `can_trade` function so deposit/withdraw
    buttons respect your role system. If omitted, buttons are always enabled."""
    can_trade_fn = can_trade_fn or (lambda: True)
    summ = portfolio_summary(sim, price_thb, fee_pct=fee_pct)

    section("📊 Portfolio Overview")
    k = st.columns(4)
    metric_card(k[0], "มูลค่าพอร์ตรวม", fmt_baht(summ["total_value"]),
                summ["total_pnl"], f"เงินสด {fmt_baht(summ['cash'])}")
    metric_card(k[1], "กำไร/ขาดทุนรวม (เทียบเงินต้น)",
                fmt_baht(summ["total_pnl"], True), summ["total_pnl"],
                f"{summ['total_pnl_pct']:+.2f}% · เงินต้นสุทธิ {fmt_baht(summ['net_contributed'])}")
    metric_card(k[2], "Unrealized P&L", fmt_baht(summ["total_unrealized"], True),
                summ["total_unrealized"])
    metric_card(k[3], "Realized P&L", fmt_baht(summ["total_realized"], True),
                summ["total_realized"], f"ค่าธรรมเนียมสะสม {fmt_baht(summ['total_fees'])}")

    rows = summ["rows"]
    if rows.empty:
        st.info("ยังไม่มีสินทรัพย์ในพอร์ต — เริ่มซื้อขายที่แท็บ Exchange UI Simulator")
    else:
        disp = rows.copy()
        disp["เหรียญ"] = disp["asset"]
        disp["จำนวนถือครอง"] = disp["qty"].map(lambda v: f"{v:,.6f}")
        disp["ต้นทุนเฉลี่ย"] = disp["avg_cost"].map(fmt_baht)
        disp["ราคาปัจจุบัน"] = disp["price"].map(fmt_baht)
        disp["มูลค่าปัจจุบัน"] = disp["value"].map(fmt_baht)
        disp["Unrealized P&L"] = disp.apply(
            lambda r: f"{fmt_baht(r['unrealized_pnl'], True)} ({r['unrealized_pct']:+.2f}%)", axis=1)
        disp["Realized P&L"] = disp["realized_pnl"].map(lambda v: fmt_baht(v, True))
        disp["สัดส่วนพอร์ต"] = disp["allocation_pct"].map(lambda v: f"{v:.1f}%")
        show_cols = ["เหรียญ", "จำนวนถือครอง", "ต้นทุนเฉลี่ย", "ราคาปัจจุบัน",
                    "มูลค่าปัจจุบัน", "Unrealized P&L", "Realized P&L", "สัดส่วนพอร์ต"]
        st.dataframe(disp[show_cols].sort_values("มูลค่าปัจจุบัน", ascending=False),
                     height=min(360, 45 + 35 * len(disp)), **WIDE)

        pie_rows = rows[rows["value"] > 0]
        if not pie_rows.empty or summ["cash"] > 0:
            labels = list(pie_rows["asset"]) + (["Cash"] if summ["cash"] > 0 else [])
            values = list(pie_rows["value"]) + ([summ["cash"]] if summ["cash"] > 0 else [])
            fig = go.Figure(go.Pie(
                labels=labels, values=values, hole=0.55,
                marker=dict(colors=["#0ecb81", "#3B82F6", "#fcd535", "#9945FF",
                                    "#f6465d", "#14B6E7", "#848e9c"])))
            fig.update_layout(
                template="plotly_dark", height=320, margin=dict(t=20, b=20),
                title=dict(text="Allocation ของพอร์ต", font=dict(size=13)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, **WIDE)

    section("💵 ฝาก / ถอนเงิน")
    dc1, dc2 = st.columns(2)
    with dc1:
        st.caption("ฝากเงินเข้ากระเป๋าจำลอง")
        st.button("➕ ฝากเงิน", key="port_open_deposit",
                  on_click=_open_deposit_flag, disabled=not can_trade_fn(), **WIDE)
    with dc2:
        st.caption("ถอนเงินออกจากกระเป๋าจำลอง")
        wd_amt = comma_number_input("จำนวนที่ต้องการถอน (THB)", value=0,
                                    min_value=0, key="port_wd_amt", disabled=not can_trade_fn())
        if st.button("➖ ถอนเงิน", key="port_wd_btn", disabled=not can_trade_fn(), **WIDE):
            ok, msg = do_withdraw(sim, wd_amt)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    section("🧾 ประวัติธุรกรรมทั้งหมด")
    hist = unified_transaction_history(sim, fee_pct=fee_pct)
    if hist.empty:
        st.caption("ยังไม่มีประวัติธุรกรรม")
    else:
        st.dataframe(hist, height=min(420, 45 + 35 * len(hist)), **WIDE)
        st.download_button("⬇️ ดาวน์โหลดประวัติธุรกรรม (CSV)", to_csv_bytes(hist),
                           "xspring_transaction_history.csv", "text/csv", **WIDE)


# -------------------------------------------------------------------------
# 7. RENDER — compact card for Backtest / Planner tabs
# -------------------------------------------------------------------------

def render_portfolio_mini_card(sim: dict, price_thb: dict[str, float], asset: str,
                               fee_pct: float = DEFAULT_FEE_PCT) -> None:
    """การ์ดย่อ: แสดงสถานะการถือครองเหรียญนี้ของพอร์ตลูกค้าจำลอง
    ใช้ฝังในหน้า Backtest (Tab 1) หรือ Planner (Tab 2) เพื่อให้ข้อมูลพอร์ตจริง
    ไหลเข้ามาเป็นบริบทประกอบการตัดสินใจ"""
    book = compute_portfolio_ledger(sim, fee_pct=fee_pct)
    b = book.get(asset)
    if not b or b["qty"] <= 1e-9:
        st.caption(f"💼 พอร์ตจำลองยังไม่ถือ {asset} อยู่ตอนนี้ — "
                   "ไปที่แท็บ Exchange UI Simulator เพื่อเริ่มซื้อขาย")
        return
    px = float(price_thb.get(asset, 0.0))
    val = b["qty"] * px
    avg_cost = b["cost_thb"] / b["qty"] if b["qty"] > 0 else 0.0
    unreal = val - b["cost_thb"]
    unreal_pct = (unreal / b["cost_thb"] * 100) if b["cost_thb"] > 0 else 0.0
    c = st.columns(4)
    metric_card(c[0], f"พอร์ตถือครอง {asset}", fmt_coin(b["qty"], asset))
    metric_card(c[1], "ต้นทุนเฉลี่ย", fmt_baht(avg_cost))
    metric_card(c[2], "มูลค่าปัจจุบัน", fmt_baht(val), unreal)
    metric_card(c[3], "Unrealized P&L", fmt_baht(unreal, True), unreal, f"{unreal_pct:+.2f}%")


# =========================================================================
# USAGE SNIPPETS — copy the relevant line(s) into the existing functions
# in your main xspring_dealer_suite.py file
# =========================================================================
#
# --- In render_tab4() (Wallet), anywhere after price_thb_map is built:
#         render_portfolio_panel(sim, price_thb_map, can_trade_fn=can_trade)
#
# --- In render_tab1() (Backtest), right after:
#         st.success(f"✅ โหลดข้อมูล **{asset}** สำเร็จ ...")
#     add:
#         _sim = st.session_state.get("sim")
#         if isinstance(_sim, dict):
#             render_portfolio_mini_card(_sim, {asset: float(bt["Local_THB"].iloc[-1])}, asset)
#
# --- In render_tab2() (Planner), right after the "🧾 สรุปผลสำหรับผู้บริหาร" verdict_box:
#         _sim = st.session_state.get("sim")
#         if isinstance(_sim, dict) and not data.empty:
#             render_portfolio_mini_card(_sim, {asset: usdthb_now * data["Global_USD"].iloc[-1]}, asset)
# =========================================================================
