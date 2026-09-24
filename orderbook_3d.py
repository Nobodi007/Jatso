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


# ลำดับ vertex ของลูกบาศก์ (8 จุด) + สามเหลี่ยม 12 หน้า
_CUBE_I = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
_CUBE_J = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
_CUBE_K = [0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6]


def _bars_trace(rows, y_sign, color, label, unit, width, depth, z_cap):
    """รวมทุกแท่งของฝั่งเดียวกันเป็น Mesh3d เดียว"""
    xs, ys, zs, ii, jj, kk, hover = [], [], [], [], [], [], []

    for idx, (price, amount) in enumerate(rows):
        yc = y_sign * (idx + 1)
        h = min(amount, z_cap)
        x0, x1 = price - width / 2, price + width / 2
        y0, y1 = yc - depth / 2, yc + depth / 2

        xs += [x0, x0, x1, x1, x0, x0, x1, x1]
        ys += [y0, y1, y1, y0, y0, y1, y1, y0]
        zs += [0, 0, 0, 0, h, h, h, h]

        base = idx * 8
        ii += [base + v for v in _CUBE_I]
        jj += [base + v for v in _CUBE_J]
        kk += [base + v for v in _CUBE_K]

        text = (
            f"<b>{label}</b><br>ราคา: {price:,.2f} THB<br>"
            f"ปริมาณ: {amount:,.8f} {unit}<br>Depth: {idx + 1}"
        )
        hover += [text] * 8

    return go.Mesh3d(
        x=xs, y=ys, z=zs, i=ii, j=jj, k=kk,
        color=color,
        opacity=0.85,
        flatshading=True,
        hovertext=hover,
        hoverinfo="text",
        showlegend=False,
    )


def _make_3d_orderbook(asks, bids, symbol="BTC/THB"):
    bids = sorted(bids, key=lambda r: r[0])
    asks = sorted(asks, key=lambda r: r[0])

    all_rows = bids + asks
    if not all_rows:
        return go.Figure()

    unit = symbol.split("/")[0]
    prices = [p for p, _ in all_rows]
    amounts = sorted(q for _, q in all_rows)

    price_span = max(max(prices) - min(prices), 1.0)
    bar_width = price_span / max(len(prices), 10) * 0.72

    # ตัดยอดที่สูงผิดปกติ (whale order) ไม่ให้แท่งอื่นแบนหมด
    # ค่าจริงยังดูได้จาก hover
    z_cap = amounts[int(len(amounts) * 0.95) - 1] if len(amounts) >= 10 else amounts[-1]
    z_cap = z_cap or 1.0

    traces = []
    if bids:
        traces.append(_bars_trace(
            list(reversed(bids)), -1, "#00d68f", "🟢 BID — ซื้อ",
            unit, bar_width, 0.72, z_cap,
        ))
    if asks:
        traces.append(_bars_trace(
            asks, 1, "#ff3b5c", "🔴 ASK — ขาย",
            unit, bar_width, 0.72, z_cap,
        ))

    best_bid = max((p for p, _ in bids), default=None)
    best_ask = min((p for p, _ in asks), default=None)
    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2
        traces.append(go.Scatter3d(
            x=[mid, mid], y=[-1.5, 1.5], z=[0, 0],
            mode="lines",
            line=dict(width=6, color="#ffffff"),
            hovertemplate=f"Mid Price: {mid:,.2f} THB<extra></extra>",
            showlegend=False,
        ))

    fig = go.Figure(data=traces)
    fig.update_layout(
        height=520,
        margin=dict(l=0, r=0, t=30, b=0),
        template="plotly_dark",
        paper_bgcolor="#07111f",
        scene=dict(
            xaxis=dict(title="ราคา (THB)", tickformat=",", backgroundcolor="#07111f"),
            yaxis=dict(title="Depth", backgroundcolor="#07111f"),
            zaxis=dict(title=f"ปริมาณ ({unit})", backgroundcolor="#07111f"),
            aspectmode="manual",
            aspectratio=dict(x=2.2, y=1.15, z=1.0),
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
