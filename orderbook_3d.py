"""
XSpring Dealer Suite - 3D Order Book
-------------------------------------
ดึง Order Book จาก Bitkub Public REST API v3
และแสดงเป็น 3D Market Depth ใน Streamlit

อัปเดตข้อมูลทุก 10 นาที (600 วินาที)
ไม่มี API Key เพราะใช้ public market endpoint
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st
import plotly.graph_objects as go


BITKUB_DEPTH_URL = "https://api.bitkub.com/api/v3/market/depth"
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


@st.cache_data(ttl=600, show_spinner=False)
def fetch_orderbook(symbol: str = "btc_thb", limit: int = 30) -> dict:
    """
    ดึง order book จาก Bitkub และ cache 10 นาที

    response:
      {
        "asks": [[price, amount], ...],
        "bids": [[price, amount], ...]
      }
    """
    response = requests.get(
        BITKUB_DEPTH_URL,
        params={"sym": symbol.lower(), "lmt": int(limit)},
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()

    # Bitkub API v3 อาจตอบ error object
    if isinstance(data, dict) and data.get("error", 0) not in (0, None):
        raise RuntimeError(f"Bitkub API error: {data}")

    if not isinstance(data, dict):
        raise RuntimeError("รูปแบบข้อมูล Order Book จาก Bitkub ไม่ถูกต้อง")

    asks = data.get("asks") or []
    bids = data.get("bids") or []

    def clean(rows):
        out = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                price = float(row[0])
                amount = float(row[1])
            except (TypeError, ValueError):
                continue

            if price > 0 and amount > 0:
                out.append((price, amount))
        return out

    return {
        "asks": clean(asks),
        "bids": clean(bids),
        "fetched_at": datetime.now(BANGKOK_TZ),
    }


def _make_3d_orderbook(asks, bids, symbol="BTC/THB"):
    """
    สร้าง 3D Market Depth:
      X = ราคา
      Y = ระดับ Order
      Z = ปริมาณเหรียญ

    ไม่ทำข้อมูลเวลาเทียม เพราะ endpoint นี้ให้ snapshot ปัจจุบัน
    """
    # เรียงราคา: bid จากต่ำ -> สูง, ask จากต่ำ -> สูง
    bids = sorted(bids, key=lambda x: x[0])
    asks = sorted(asks, key=lambda x: x[0])

    # ใช้ระดับ order เป็นแกน Y
    max_levels = max(len(bids), len(asks), 1)

    bid_x = [p for p, _ in bids]
    bid_z = [q for _, q in bids]
    ask_x = [p for p, _ in asks]
    ask_z = [q for _, q in asks]

    # ทำให้เป็นเส้น 3D ที่อ่านง่าย:
    # Y = ระดับราคา/ลำดับ depth
    bid_y = list(range(len(bids)))
    ask_y = list(range(len(asks)))

    fig = go.Figure()

    if bids:
        fig.add_trace(
            go.Scatter3d(
                x=bid_x,
                y=bid_y,
                z=bid_z,
                mode="lines+markers",
                name="Bid (ซื้อ)",
                line=dict(width=7),
                marker=dict(size=5),
                hovertemplate=(
                    "<b>Bid</b><br>"
                    "ราคา: %{x:,.2f} THB<br>"
                    "Depth: %{y}<br>"
                    "จำนวน: %{z:,.8f}<extra></extra>"
                ),
            )
        )

        # เส้นฐานเพื่อให้เห็นรูปทรงของ depth
        fig.add_trace(
            go.Scatter3d(
                x=bid_x,
                y=bid_y,
                z=[0] * len(bids),
                mode="lines",
                name="Bid base",
                showlegend=False,
                line=dict(width=2),
                hoverinfo="skip",
            )
        )

    if asks:
        fig.add_trace(
            go.Scatter3d(
                x=ask_x,
                y=ask_y,
                z=ask_z,
                mode="lines+markers",
                name="Ask (ขาย)",
                line=dict(width=7),
                marker=dict(size=5),
                hovertemplate=(
                    "<b>Ask</b><br>"
                    "ราคา: %{x:,.2f} THB<br>"
                    "Depth: %{y}<br>"
                    "จำนวน: %{z:,.8f}<extra></extra>"
                ),
            )
        )

        fig.add_trace(
            go.Scatter3d(
                x=ask_x,
                y=ask_y,
                z=[0] * len(asks),
                mode="lines",
                name="Ask base",
                showlegend=False,
                line=dict(width=2),
                hoverinfo="skip",
            )
        )

    # จุดกลางตลาด
    if bids and asks:
        best_bid = max(p for p, _ in bids)
        best_ask = min(p for p, _ in asks)
        mid = (best_bid + best_ask) / 2

        fig.add_trace(
            go.Scatter3d(
                x=[mid],
                y=[0],
                z=[0],
                mode="markers+text",
                name="Mid Price",
                marker=dict(size=9, symbol="diamond"),
                text=[f"{mid:,.2f} THB"],
                textposition="top center",
                hovertemplate="Mid: %{x:,.2f} THB<extra></extra>",
            )
        )

    fig.update_layout(
        title=f"3D Order Book — {symbol}",
        height=650,
        margin=dict(l=0, r=0, t=55, b=0),
        template="plotly_dark",
        scene=dict(
            xaxis=dict(
                title="ราคา (THB)",
                tickformat=",",
            ),
            yaxis=dict(
                title="Depth Level",
            ),
            zaxis=dict(
                title="ปริมาณ",
            ),
            camera=dict(
                eye=dict(x=1.65, y=1.55, z=1.25),
            ),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
        ),
    )

    return fig


def render_orderbook_3d(
    symbol: str = "btc_thb",
    title: str = "Order Book",
    limit: int = 30,
):
    """
    เรียกใช้จากหน้า Streamlit ได้โดยตรง

    ตัวอย่าง:
        from orderbook_3d import render_orderbook_3d
        render_orderbook_3d("btc_thb")
    """
    symbol = symbol.lower()

    st.subheader(title)
    st.caption(
        "3D Market Depth จาก Bitkub • อัปเดตข้อมูลสูงสุดทุก 10 นาที"
    )

    try:
        data = fetch_orderbook(symbol, limit)
    except Exception as exc:
        st.error(f"โหลด Order Book ไม่สำเร็จ: {exc}")
        return

    asks = data["asks"]
    bids = data["bids"]
    fetched_at = data["fetched_at"]

    if not asks and not bids:
        st.warning("ยังไม่มีข้อมูล Order Book")
        return

    # Metrics
    best_bid = max((p for p, _ in bids), default=0.0)
    best_ask = min((p for p, _ in asks), default=0.0)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "Best Bid",
            f"{best_bid:,.2f} THB" if best_bid else "-",
        )

    with c2:
        st.metric(
            "Best Ask",
            f"{best_ask:,.2f} THB" if best_ask else "-",
        )

    with c3:
        if best_bid and best_ask:
            spread = best_ask - best_bid
            st.metric("Spread", f"{spread:,.2f} THB")
        else:
            st.metric("Spread", "-")

    fig = _make_3d_orderbook(asks, bids, symbol.upper().replace("_", "/"))
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "ข้อมูล snapshot ล่าสุด: "
        + fetched_at.strftime("%d/%m/%Y %H:%M:%S น.")
        + " (เวลาไทย) • cache 10 นาที"
    )

    # ตารางรายละเอียด
    left, right = st.columns(2)

    with left:
        st.markdown("### Bid (ซื้อ)")
        bid_rows = [
            {"ราคา (THB)": p, "ปริมาณ": q}
            for p, q in sorted(bids, key=lambda x: x[0], reverse=True)
        ]
        st.dataframe(
            bid_rows,
            use_container_width=True,
            hide_index=True,
        )

    with right:
        st.markdown("### Ask (ขาย)")
        ask_rows = [
            {"ราคา (THB)": p, "ปริมาณ": q}
            for p, q in sorted(asks, key=lambda x: x[0])
        ]
        st.dataframe(
            ask_rows,
            use_container_width=True,
            hide_index=True,
        )
