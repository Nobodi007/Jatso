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


def _side_scatter(rows, y_sign, unit, label):
    """สร้างจุด (x=ราคา, y=Depth ตามฝั่ง, z=ปริมาณ) สำหรับฝั่งเดียว"""
    xs, ys, zs, hover = [], [], [], []
    for idx, (price, amount) in enumerate(rows):
        xs.append(price)
        ys.append(y_sign * (idx + 1))
        zs.append(amount)
        hover.append(
            f"<b>{label}</b><br>ราคา: {price:,.2f} THB<br>"
            f"ปริมาณ: {amount:,.8f} {unit}<br>Depth: {idx + 1}"
        )
    return xs, ys, zs, hover


def _make_3d_orderbook(asks, bids, symbol="BTC/THB"):
    bids = sorted(bids, key=lambda r: r[0], reverse=True)  # best bid ใกล้ mid ก่อน
    asks = sorted(asks, key=lambda r: r[0])                # best ask ใกล้ mid ก่อน

    all_rows = bids + asks
    if not all_rows:
        return go.Figure()

    unit = symbol.split("/")[0]

    bx, by, bz, bhover = _side_scatter(bids, -1, unit, "🟢 BID — ซื้อ")
    ax, ay, az, ahover = _side_scatter(asks, 1, unit, "🔴 ASK — ขาย")

    fig = go.Figure()

    if bx:
        fig.add_trace(go.Scatter3d(
            x=bx, y=by, z=bz,
            mode="markers",
            name="BID",
            marker=dict(
                size=6,
                color=bz,
                colorscale="Greens",
                opacity=0.9,
                colorbar=dict(
                    title=f"BID<br>({unit})",
                    thickness=14,
                    len=0.42,
                    x=1.02,
                    y=0.78,
                ),
                line=dict(width=0),
            ),
            hovertext=bhover,
            hoverinfo="text",
            showlegend=False,
        ))

    if ax:
        fig.add_trace(go.Scatter3d(
            x=ax, y=ay, z=az,
            mode="markers",
            name="ASK",
            marker=dict(
                size=6,
                color=az,
                colorscale="Reds",
                opacity=0.9,
                colorbar=dict(
                    title=f"ASK<br>({unit})",
                    thickness=14,
                    len=0.42,
                    x=1.02,
                    y=0.22,
                ),
                line=dict(width=0),
            ),
            hovertext=ahover,
            hoverinfo="text",
            showlegend=False,
        ))

    zs = bz + az

    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2
        max_z = max(zs) if zs else 1.0
        fig.add_trace(go.Scatter3d(
            x=[mid, mid], y=[-1.5, 1.5], z=[0, 0],
            mode="lines",
            line=dict(width=5, color="#ffffff"),
            hovertemplate=f"Mid Price: {mid:,.2f} THB<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        height=560,
        margin=dict(l=0, r=0, t=30, b=0),
        template="plotly_dark",
        paper_bgcolor="#07111f",
        scene=dict(
            xaxis=dict(title="ราคา (THB)", tickformat=",", backgroundcolor="#07111f",
                       gridcolor="#1d2b3a", zerolinecolor="#1d2b3a"),
            yaxis=dict(title="Depth (ซ้าย=Bid / ขวา=Ask)", backgroundcolor="#07111f",
                       gridcolor="#1d2b3a", zerolinecolor="#1d2b3a"),
            zaxis=dict(title=f"ปริมาณ ({unit})", backgroundcolor="#07111f",
                       gridcolor="#1d2b3a", zerolinecolor="#1d2b3a"),
            aspectmode="manual",
            aspectratio=dict(x=2.0, y=1.2, z=0.9),
            camera=dict(eye=dict(x=1.6, y=1.6, z=1.0)),
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
