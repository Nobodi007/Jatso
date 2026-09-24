"""
XSpring Dealer Suite - 3D Order Book
Bitkub v3 depth snapshot, cached for 10 minutes.
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
    response = requests.get(
        BITKUB_DEPTH_URL,
        params={"sym": symbol.lower(), "lmt": int(limit)},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, dict):
        raise RuntimeError("Bitkub API ส่งข้อมูลไม่ถูกต้อง")

    if payload.get("error", 0) not in (0, None):
        raise RuntimeError(f"Bitkub API error: {payload}")

    # Bitkub v3 returns: {"error": 0, "result": {"bids": [...], "asks": [...]}}
    result = payload.get("result", payload)
    if not isinstance(result, dict):
        raise RuntimeError("ไม่พบ result ของ Order Book จาก Bitkub")

    def clean(rows):
        out = []
        for row in rows or []:
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
        "asks": clean(result.get("asks")),
        "bids": clean(result.get("bids")),
        "fetched_at": datetime.now(BANGKOK_TZ),
    }


def _cube_mesh(x_center, y_center, width, depth, height, color, hover_text):
    x0, x1 = x_center - width / 2, x_center + width / 2
    y0, y1 = y_center - depth / 2, y_center + depth / 2
    z0, z1 = 0.0, height

    x = [x0, x1, x1, x0, x0, x1, x1, x0]
    y = [y0, y0, y1, y1, y0, y0, y1, y1]
    z = [z0, z0, z0, z0, z1, z1, z1, z1]

    i = [0, 0, 0, 1, 1, 2, 4, 4, 5, 6, 3, 3]
    j = [1, 2, 3, 2, 5, 3, 5, 6, 6, 7, 7, 4]
    k = [2, 3, 1, 5, 6, 7, 6, 7, 4, 4, 4, 0]

    return go.Mesh3d(
        x=x, y=y, z=z, i=i, j=j, k=k,
        color=color,
        opacity=0.82,
        flatshading=True,
        hovertext=hover_text,
        hoverinfo="text",
        showlegend=False,
    )


def _make_3d_orderbook(asks, bids, symbol="BTC/THB"):
    bids = sorted(bids, key=lambda r: r[0])
    asks = sorted(asks, key=lambda r: r[0])

    all_rows = bids + asks
    if not all_rows:
        return go.Figure()

    prices = [p for p, _ in all_rows]
    amounts = [q for _, q in all_rows]
    price_span = max(max(prices) - min(prices), 1.0)
    bar_width = price_span / max(len(prices), 10) * 0.72
    z_cap = max(amounts) or 1.0

    traces = []

    for idx, (price, amount) in enumerate(bids):
        traces.append(_cube_mesh(
            price, -(idx + 1), bar_width, 0.72, min(amount, z_cap),
            "#00d68f",
            f"<b>🟢 BID — ซื้อ</b><br>ราคา: {price:,.2f} THB<br>"
            f"ปริมาณ: {amount:,.8f} BTC<br>Depth: {idx + 1}",
        ))

    for idx, (price, amount) in enumerate(asks):
        traces.append(_cube_mesh(
            price, idx + 1, bar_width, 0.72, min(amount, z_cap),
            "#ff3b5c",
            f"<b>🔴 ASK — ขาย</b><br>ราคา: {price:,.2f} THB<br>"
            f"ปริมาณ: {amount:,.8f} BTC<br>Depth: {idx + 1}",
        ))

    best_bid = max((p for p, _ in bids), default=None)
    best_ask = min((p for p, _ in asks), default=None)

    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2
        traces.append(go.Scatter3d(
            x=[mid, mid], y=[-1.5, 1.5], z=[0, 0],
            mode="lines+text",
            line=dict(width=8, color="#ffffff"),
            text=["", f"Mid {mid:,.2f} THB"],
            textposition="top center",
            hovertemplate=f"Mid Price: {mid:,.2f} THB<extra></extra>",
            showlegend=False,
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        height=560,
        margin=dict(l=0, r=0, t=45, b=0),
        template="plotly_dark",
        paper_bgcolor="#07111f",
        plot_bgcolor="#07111f",
        scene=dict(
            xaxis=dict(title="ราคา (THB)", tickformat=",", backgroundcolor="#07111f"),
            yaxis=dict(title="Depth", backgroundcolor="#07111f"),
            zaxis=dict(title="ปริมาณ (BTC)", backgroundcolor="#07111f"),
            aspectmode="manual",
            aspectratio=dict(x=2.2, y=1.15, z=1.0),
            camera=dict(eye=dict(x=1.65, y=1.55, z=1.15)),
        ),
        showlegend=False,
    )
    return fig


def render_orderbook_3d(symbol="btc_thb", title="3D Order Book", limit=25):
    symbol = symbol.lower()
    st.subheader(title)
    st.caption("3D Market Depth • Bitkub • snapshot • cache 10 นาที")

    try:
        data = fetch_orderbook(symbol, limit)
    except Exception as exc:
        st.error(f"โหลด Order Book ไม่สำเร็จ: {exc}")
        return

    asks, bids = data["asks"], data["bids"]
    fetched_at = data["fetched_at"]

    if not asks and not bids:
        st.warning("Bitkub ส่ง Order Book ว่างกลับมา")
        return

    best_bid = max((p for p, _ in bids), default=0.0)
    best_ask = min((p for p, _ in asks), default=0.0)

    c1, c2, c3 = st.columns(3)
    c1.metric("🟢 Best Bid", f"{best_bid:,.2f} THB" if best_bid else "-")
    c2.metric("🔴 Best Ask", f"{best_ask:,.2f} THB" if best_ask else "-")
    c3.metric("Spread", f"{best_ask - best_bid:,.2f} THB"
              if best_bid and best_ask else "-")

    fig = _make_3d_orderbook(
        asks, bids, symbol.upper().replace("_", "/")
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displaylogo": False, "scrollZoom": True, "responsive": True},
    )

    st.caption(
        "ข้อมูล snapshot ล่าสุด: "
        + fetched_at.strftime("%d/%m/%Y %H:%M:%S น.")
        + " (เวลาไทย) • cache 10 นาที"
    )

    left, right = st.columns(2)
    with left:
        st.markdown("### 🟢 Bid — ซื้อ")
        st.dataframe(
            [{"ราคา (THB)": p, "ปริมาณ (BTC)": q}
             for p, q in sorted(bids, reverse=True)],
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.markdown("### 🔴 Ask — ขาย")
        st.dataframe(
            [{"ราคา (THB)": p, "ปริมาณ (BTC)": q}
             for p, q in sorted(asks)],
            use_container_width=True,
            hide_index=True,
        )
