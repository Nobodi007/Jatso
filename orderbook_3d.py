"""
XSpring Dealer Suite - 3D Order Book (lightweight)
Bitkub v3 depth snapshot, cached for 10 minutes.

ทำไมเบากว่าเดิม:
- รวมแท่งทั้งหมดเป็น Mesh3d แค่ 2 trace (bid / ask) แทนที่จะสร้างทีละแท่ง
- cache 10 นาที ไม่ยิง API ทุกครั้งที่หน้าจอ rerun
- จำกัดจำนวนระดับราคา (default 20 ต่อฝั่ง)
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import requests
import streamlit as st

BITKUB_DEPTH_URL = "https://api.bitkub.com/api/v3/market/depth"
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
CACHE_TTL_SECONDS = 600  # 10 นาที


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="กำลังโหลด Order Book...")
def fetch_orderbook(symbol: str = "btc_thb", limit: int = 20) -> dict:
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

    result = payload.get("result", payload)
    if not isinstance(result, dict):
        raise RuntimeError("ไม่พบ result ของ Order Book จาก Bitkub")

    def clean(rows):
        out = []
        for row in rows or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                price, amount = float(row[0]), float(row[1])
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


def _make_3d_orderbook(asks, bids, symbol="BTC/THB"):
    """สร้าง Order Book แบบ 3D Scatter ให้หน้าตาใกล้เคียงกราฟตัวอย่าง"""
    bids = sorted(bids, key=lambda r: r[0])
    asks = sorted(asks, key=lambda r: r[0])

    rows = []
    # BID อยู่ฝั่ง Depth ติดลบ / ASK อยู่ฝั่ง Depth บวก
    for idx, (price, amount) in enumerate(reversed(bids), start=1):
        rows.append((price, -idx, amount, "🟢 BID — ซื้อ"))
    for idx, (price, amount) in enumerate(asks, start=1):
        rows.append((price, idx, amount, "🔴 ASK — ขาย"))

    if not rows:
        return go.Figure()

    unit = symbol.split("/")[0]
    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    zs = [r[2] for r in rows]
    labels = [r[3] for r in rows]

    hover = [
        f"<b>{label}</b><br>"
        f"ราคา: {price:,.2f} THB<br>"
        f"ปริมาณ: {amount:,.8f} {unit}<br>"
        f"Depth: {abs(depth)}"
        for (price, depth, amount, label) in rows
    ]

    # ใช้ปริมาณเป็นทั้งแกน Z และสี เพื่อให้ได้ gradient แบบกราฟตัวอย่าง
    fig = go.Figure(data=[go.Scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="markers",
        marker=dict(
            size=5,
            color=zs,
            colorscale="Rainbow",
            opacity=0.9,
            line=dict(width=0),
            colorbar=dict(title=f"ปริมาณ ({unit})", thickness=12),
        ),
        text=hover,
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
    )])

    best_bid = max((p for p, _ in bids), default=None)
    best_ask = min((p for p, _ in asks), default=None)
    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2
        fig.add_trace(go.Scatter3d(
            x=[mid],
            y=[0],
            z=[0],
            mode="markers",
            marker=dict(size=7, color="white", symbol="diamond"),
            hovertemplate=f"Mid Price: {mid:,.2f} THB<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        title=dict(text="3D Order Book — Scatter", font=dict(size=14)),
        height=600,
        margin=dict(l=0, r=0, t=40, b=0),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        scene=dict(
            xaxis=dict(
                title="ราคา (THB)",
                tickformat=",",
                backgroundcolor="#181a20",
                gridcolor="#49647f",
                zerolinecolor="#8aa0b5",
            ),
            yaxis=dict(
                title="Depth",
                backgroundcolor="#181a20",
                gridcolor="#49647f",
                zerolinecolor="#8aa0b5",
            ),
            zaxis=dict(
                title=f"ปริมาณ ({unit})",
                backgroundcolor="#181a20",
                gridcolor="#49647f",
                zerolinecolor="#8aa0b5",
            ),
            aspectmode="manual",
            aspectratio=dict(x=2.0, y=1.15, z=1.0),
            camera=dict(eye=dict(x=1.65, y=1.55, z=1.15)),
        ),
        showlegend=False,
    )
    return fig


def render_orderbook_3d(symbol="btc_thb", title="3D Order Book", limit=20):
    symbol = symbol.lower()
    unit = symbol.split("_")[0].upper()

    head_l, head_r = st.columns([5, 1])
    head_l.subheader(title)
    head_l.caption("3D Market Depth • Bitkub • snapshot • cache 10 นาที")
    if head_r.button("🔄 รีเฟรช", key=f"refresh_ob_{symbol}"):
        fetch_orderbook.clear()

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
    c3.metric(
        "Spread",
        f"{best_ask - best_bid:,.2f} THB" if best_bid and best_ask else "-",
    )

    fig = _make_3d_orderbook(asks, bids, symbol.upper().replace("_", "/"))
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"orderbook_3d_{symbol}",
        config={"displaylogo": False, "scrollZoom": True, "responsive": True},
    )

    st.caption(
        "ข้อมูล snapshot ล่าสุด: "
        + fetched_at.strftime("%d/%m/%Y %H:%M:%S น.")
        + " (เวลาไทย) • cache 10 นาที"
    )

    # ตารางอยู่ใน expander — ไม่ต้อง render ถ้าไม่เปิดดู
    with st.expander("📋 ตารางราคา Bid / Ask"):
        left, right = st.columns(2)
        with left:
            st.markdown("### 🟢 Bid — ซื้อ")
            st.dataframe(
                [{"ราคา (THB)": p, f"ปริมาณ ({unit})": q}
                 for p, q in sorted(bids, reverse=True)],
                use_container_width=True,
                hide_index=True,
                height=300,
            )
        with right:
            st.markdown("### 🔴 Ask — ขาย")
            st.dataframe(
                [{"ราคา (THB)": p, f"ปริมาณ ({unit})": q}
                 for p, q in sorted(asks)],
                use_container_width=True,
                hide_index=True,
                height=300,
            )
