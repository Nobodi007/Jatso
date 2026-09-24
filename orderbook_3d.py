"""
XSpring Dealer Suite - 3D Order Book
-------------------------------------
3D Market Depth แบบ "กำแพง/แท่ง" สำหรับ Streamlit + Plotly

แหล่งข้อมูล:
    Bitkub Public API v3 /market/depth

พฤติกรรม:
    - BTC/THB เป็นค่าเริ่มต้น
    - cache 10 นาที
    - Bid = ฝั่งซื้อ
    - Ask = ฝั่งขาย
    - แต่ละระดับราคาถูกวาดเป็นแท่ง 3D
    - หมุน / ซูม / เลื่อนกราฟได้ด้วยเมาส์
    - แสดง Best Bid / Best Ask / Spread
    - แสดงตาราง Order Book ด้านล่าง
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
def fetch_orderbook(symbol: str = "btc_thb", limit: int = 25) -> dict:
    """ดึง snapshot Order Book และ cache ไว้ 10 นาที"""
    response = requests.get(
        BITKUB_DEPTH_URL,
        params={
            "sym": symbol.lower(),
            "lmt": int(limit),
        },
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("Bitkub API ส่งข้อมูลที่ไม่ใช่ JSON object")

    if data.get("error", 0) not in (0, None):
        raise RuntimeError(f"Bitkub API error: {data}")

    def clean(rows):
        result = []
        for row in rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                price = float(row[0])
                amount = float(row[1])
            except (TypeError, ValueError):
                continue

            if price > 0 and amount > 0:
                result.append((price, amount))

        return result

    return {
        "asks": clean(data.get("asks")),
        "bids": clean(data.get("bids")),
        "fetched_at": datetime.now(BANGKOK_TZ),
    }


def _cube_mesh(
    x_center: float,
    y_center: float,
    width: float,
    depth: float,
    height: float,
    color: str,
    name: str,
    hover_text: str,
):
    """
    สร้างแท่งสี่เหลี่ยม 3D หนึ่งแท่งด้วย Mesh3d

    Plotly ไม่มี primitive "3D bar" โดยตรง จึงใช้ Mesh3d
    สร้างทรงลูกบาศก์/ปริซึม ซึ่งเหมาะกับ depth visualization
    """
    x0 = x_center - width / 2
    x1 = x_center + width / 2
    y0 = y_center - depth / 2
    y1 = y_center + depth / 2
    z0 = 0.0
    z1 = height

    # 8 vertices
    x = [x0, x1, x1, x0, x0, x1, x1, x0]
    y = [y0, y0, y1, y1, y0, y0, y1, y1]
    z = [z0, z0, z0, z0, z1, z1, z1, z1]

    # 12 triangles = 6 faces
    i = [0, 0, 0, 1, 1, 2, 4, 4, 5, 6, 3, 3]
    j = [1, 2, 3, 2, 5, 3, 5, 6, 6, 7, 7, 4]
    k = [2, 3, 1, 5, 6, 7, 6, 7, 4, 4, 4, 0]

    return go.Mesh3d(
        x=x,
        y=y,
        z=z,
        i=i,
        j=j,
        k=k,
        color=color,
        opacity=0.82,
        flatshading=True,
        hovertext=hover_text,
        hoverinfo="text",
        name=name,
        showlegend=False,
    )


def _make_3d_orderbook(asks, bids, symbol="BTC/THB"):
    """
    สร้าง 3D Order Book แบบแท่ง

    X = ราคา
    Y = ลำดับ depth
    Z = ปริมาณ
    """

    # ให้ราคาต่ำ -> สูง
    bids = sorted(bids, key=lambda row: row[0])
    asks = sorted(asks, key=lambda row: row[0])

    if not bids and not asks:
        return go.Figure()

    all_amounts = [amount for _, amount in bids + asks]
    max_amount = max(all_amounts, default=1.0)

    # จำกัดความสูงเพื่อให้กราฟไม่เสียรูปจาก order เดียวที่ใหญ่มาก
    z_cap = max_amount
    if z_cap <= 0:
        z_cap = 1.0

    all_prices = [price for price, _ in bids + asks]
    min_price = min(all_prices)
    max_price = max(all_prices)

    price_span = max(max_price - min_price, 1.0)
    bar_width = price_span / max(len(all_prices), 10) * 0.72

    # แยกฝั่งให้เห็นเป็นกำแพงคนละด้าน
    traces = []

    # Bid: สีเขียว
    for idx, (price, amount) in enumerate(bids):
        height = min(amount, z_cap)

        hover = (
            "<b>🟢 BID — ซื้อ</b><br>"
            f"ราคา: {price:,.2f} THB<br>"
            f"ปริมาณ: {amount:,.8f} BTC<br>"
            f"Depth: {idx + 1}"
        )

        traces.append(
            _cube_mesh(
                x_center=price,
                y_center=-(idx + 1),
                width=bar_width,
                depth=0.72,
                height=height,
                color="#00d68f",
                name="Bid (ซื้อ)",
                hover_text=hover,
            )
        )

    # Ask: สีแดง
    for idx, (price, amount) in enumerate(asks):
        height = min(amount, z_cap)

        hover = (
            "<b>🔴 ASK — ขาย</b><br>"
            f"ราคา: {price:,.2f} THB<br>"
            f"ปริมาณ: {amount:,.8f} BTC<br>"
            f"Depth: {idx + 1}"
        )

        traces.append(
            _cube_mesh(
                x_center=price,
                y_center=idx + 1,
                width=bar_width,
                depth=0.72,
                height=height,
                color="#ff3b5c",
                name="Ask (ขาย)",
                hover_text=hover,
            )
        )

    # Best Bid / Best Ask / Mid Price
    best_bid = max((p for p, _ in bids), default=None)
    best_ask = min((p for p, _ in asks), default=None)

    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2

        traces.append(
            go.Scatter3d(
                x=[mid, mid],
                y=[-1.5, 1.5],
                z=[0, 0],
                mode="lines+text",
                line=dict(width=8, color="#ffffff"),
                text=["", f"Mid {mid:,.2f} THB"],
                textposition="top center",
                name="Mid Price",
                hovertemplate=f"Mid Price: {mid:,.2f} THB<extra></extra>",
            )
        )

    fig = go.Figure(data=traces)

    fig.update_layout(
        title=dict(
            text=f"3D Order Book — {symbol}",
            x=0.02,
        ),
        height=680,
        margin=dict(l=0, r=0, t=55, b=0),
        template="plotly_dark",
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        scene=dict(
            xaxis=dict(
                title="ราคา (THB)",
                tickformat=",",
                showbackground=True,
                backgroundcolor="#07111f",
                gridcolor="#253247",
                zerolinecolor="#53657d",
            ),
            yaxis=dict(
                title="Depth",
                showbackground=True,
                backgroundcolor="#07111f",
                gridcolor="#253247",
                zerolinecolor="#53657d",
            ),
            zaxis=dict(
                title="ปริมาณ (BTC)",
                showbackground=True,
                backgroundcolor="#07111f",
                gridcolor="#253247",
                zerolinecolor="#53657d",
            ),
            aspectmode="manual",
            aspectratio=dict(x=2.2, y=1.15, z=1.0),
            camera=dict(
                eye=dict(x=1.65, y=1.55, z=1.15),
            ),
        ),
        showlegend=False,
    )

    return fig


def render_orderbook_3d(
    symbol: str = "btc_thb",
    title: str = "3D Order Book",
    limit: int = 25,
):
    """เรียกใช้ในหน้า Streamlit"""
    symbol = symbol.lower()

    st.subheader(title)
    st.caption(
        "3D Market Depth • Bitkub • snapshot ล่าสุด • "
        "ระบบ cache ข้อมูล 10 นาที"
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

    best_bid = max((p for p, _ in bids), default=0.0)
    best_ask = min((p for p, _ in asks), default=0.0)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "🟢 Best Bid",
            f"{best_bid:,.2f} THB" if best_bid else "-",
        )

    with c2:
        st.metric(
            "🔴 Best Ask",
            f"{best_ask:,.2f} THB" if best_ask else "-",
        )

    with c3:
        if best_bid and best_ask:
            spread = best_ask - best_bid
            st.metric("Spread", f"{spread:,.2f} THB")
        else:
            st.metric("Spread", "-")

    fig = _make_3d_orderbook(
        asks,
        bids,
        symbol.upper().replace("_", "/"),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "responsive": True,
        },
    )

    st.caption(
        "ข้อมูล snapshot ล่าสุด: "
        + fetched_at.strftime("%d/%m/%Y %H:%M:%S น.")
        + " (เวลาไทย) • cache 10 นาที"
    )

    left, right = st.columns(2)

    with left:
        st.markdown("### 🟢 Bid — ซื้อ")
        bid_rows = [
            {
                "ราคา (THB)": price,
                "ปริมาณ (BTC)": amount,
            }
            for price, amount in sorted(
                bids,
                key=lambda row: row[0],
                reverse=True,
            )
        ]
        st.dataframe(
            bid_rows,
            use_container_width=True,
            hide_index=True,
        )

    with right:
        st.markdown("### 🔴 Ask — ขาย")
        ask_rows = [
            {
                "ราคา (THB)": price,
                "ปริมาณ (BTC)": amount,
            }
            for price, amount in sorted(
                asks,
                key=lambda row: row[0],
            )
        ]
        st.dataframe(
            ask_rows,
            use_container_width=True,
            hide_index=True,
        )
