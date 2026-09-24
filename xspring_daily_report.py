from __future__ import annotations

import os
import json
import argparse
import smtplib
from pathlib import Path
from datetime import datetime, timezone, date
from email.message import EmailMessage
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np


BASE = Path(__file__).resolve().parent
BANGKOK = ZoneInfo("Asia/Bangkok")


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def report_today_bangkok() -> date:
    return datetime.now(BANGKOK).date()


def load_sim() -> dict:
    """โหลด sim_state จากไฟล์ก่อน; ถ้าไม่มีให้โหลดจาก Supabase."""
    path = Path(env("XSPRING_SIM_STATE", str(BASE / "sim_state.json")))
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            raise RuntimeError(f"อ่าน sim state ไม่สำเร็จ: {exc}") from exc

    url = env("SUPABASE_URL")
    key = env("SUPABASE_KEY")
    actor = env("XSPRING_REPORT_ACTOR")
    if url and key and actor:
        import requests

        res = requests.get(
            f"{url.rstrip('/')}/rest/v1/sim_state",
            params={
                "select": "data",
                "actor": f"eq.{actor}",
                "limit": "1",
            },
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
            timeout=30,
        )
        res.raise_for_status()
        rows = res.json()
        if rows and isinstance(rows[0].get("data"), dict):
            return rows[0]["data"]

    raise FileNotFoundError(
        "ไม่พบ sim_state.json และไม่มี Supabase config "
        "(SUPABASE_URL / SUPABASE_KEY / XSPRING_REPORT_ACTOR) ครบ"
    )


def load_prices(assets: list[str]) -> dict[str, float]:
    """ดึงราคาปัจจุบันจาก Bitkub โดยตรงเป็น THB เพื่อไม่ใช้ yfinance."""
    if not assets:
        return {}

    try:
        import requests
    except Exception as exc:
        print(f"[price] requests import failed: {exc}")
        return {}

    prices: dict[str, float] = {}
    for raw_asset in sorted(set(str(a).upper().strip() for a in assets if a)):
        asset = raw_asset
        try:
            url = "https://api.bitkub.com/api/market/ticker"
            res = requests.get(
                url,
                params={"sym": f"THB_{asset}"},
                headers={"User-Agent": "XSpring-Dealer-Daily-Report/1.0"},
                timeout=15,
            )
            res.raise_for_status()
            data = res.json()

            row = data.get(f"THB_{asset}") or data.get(f"{asset}_THB")
            if not isinstance(row, dict):
                print(f"[price] {asset}: ticker row not found")
                continue

            value = row.get("last")
            if value in (None, ""):
                print(f"[price] {asset}: last price missing")
                continue

            price = float(value)
            if price >= 0:
                prices[asset] = price
        except Exception as exc:
            print(f"[price] {asset}: {exc}")

    print(f"[price] loaded {len(prices)}/{len(set(assets))} assets from Bitkub")
    return prices


def _normalize_order_date(value) -> date | None:
    """รองรับทั้ง YYYY-MM-DD และ ISO timestamp พร้อม timezone."""
    if value in (None, ""):
        return None

    try:
        text = str(value).strip()
        if not text:
            return None

        # วันที่ใน ledger ปัจจุบันเป็น YYYY-MM-DD
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            # ถ้ามีเวลา/offset ต่อท้าย ให้ parse เป็น timestamp ก่อน
            if len(text) == 10:
                return pd.Timestamp(text).date()

        ts = pd.Timestamp(text)
        if pd.isna(ts):
            return None

        # ถ้ามี timezone ให้แปลงเป็นเวลาไทยก่อนตัดวันที่
        if ts.tzinfo is not None:
            ts = ts.tz_convert(BANGKOK)
        return ts.date()
    except Exception:
        return None


def _extract_order_date(record: dict) -> date | None:
    for key in (
        "วันที่",
        "date",
        "created_at",
        "timestamp",
        "datetime",
        "เวลา",
    ):
        if key in record:
            parsed = _normalize_order_date(record.get(key))
            if parsed is not None:
                return parsed
    return None


def _empty_orders_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "วันที่",
            "ฝั่ง",
            "เหรียญ",
            "มูลค่า (บาท)",
            "ราคาที่ลูกค้าได้",
            "เหรียญที่ส่งมอบ",
            "Hedge (เหรียญ)",
            "Hedge (USD)",
            "CEX Liquidity ใช้ (บาท)",
            "Unhedged (บาท)",
            "Market Edge",
            "รายได้",
            "ต้นทุน",
            "กำไรออเดอร์",
            "สต็อกคงเหลือ",
            "FX ใช้สะสม (USD)",
            "CEX Liquidity ใช้สะสม (บาท)",
            "NC Buffer",
            "ผลด่าน",
        ]
    )


def build_report(sim: dict, report_date: date):
    orders = [x for x in sim.get("orders", []) if isinstance(x, dict)]

    # ใช้การ parse ทีละ record เพื่อรองรับทั้งวันที่แบบเดิมและ timestamp แบบใหม่
    today_orders = [
        rec for rec in orders
        if _extract_order_date(rec) == report_date
    ]

    today_df = pd.DataFrame(today_orders) if today_orders else _empty_orders_frame()
    all_df = pd.DataFrame(orders) if orders else _empty_orders_frame()

    if not today_df.empty:
        result_col = today_df.get(
            "ผลด่าน", pd.Series(index=today_df.index, dtype=str)
        ).fillna("").astype(str)
        rejected = today_df[result_col.str.startswith("Reject")].copy()
        successful = today_df[~result_col.str.startswith("Reject")].copy()
    else:
        rejected = today_df.copy()
        successful = today_df.copy()

    def num(frame: pd.DataFrame, col: str) -> float:
        if frame.empty or col not in frame.columns:
            return 0.0
        return float(
            pd.to_numeric(frame[col], errors="coerce")
            .fillna(0)
            .sum()
        )

    pnl_today = num(successful, "กำไรออเดอร์")
    volume_today = num(today_df, "มูลค่า (บาท)")
    pnl_total = float(sim.get("pnl_thb", 0.0) or 0.0)

    latest_nc = np.nan
    if not all_df.empty and "NC Buffer" in all_df.columns:
        nc_series = pd.to_numeric(
            all_df["NC Buffer"], errors="coerce"
        ).dropna()
        if not nc_series.empty:
            latest_nc = float(nc_series.iloc[-1])

    assets = list((sim.get("inv_coins") or {}).keys())
    prices = load_prices(assets)
    target = float(sim.get("target_thb", 0.0) or 0.0)

    exposure_rows = []
    for asset, quantity in (sim.get("inv_coins") or {}).items():
        qty = float(quantity or 0.0)
        price = float(prices.get(str(asset).upper(), 0.0))
        stock_value = qty * price
        exposure_rows.append(
            {
                "เหรียญ": asset,
                "จำนวน": qty,
                "ราคาล่าสุด (THB)": price,
                "มูลค่าสต็อก (THB)": stock_value,
                "Target (THB)": target,
                "Exposure (THB)": (
                    stock_value - target if price > 0 else np.nan
                ),
            }
        )

    exposure = pd.DataFrame(exposure_rows)
    if exposure.empty:
        exposure = pd.DataFrame(
            columns=[
                "เหรียญ",
                "จำนวน",
                "ราคาล่าสุด (THB)",
                "มูลค่าสต็อก (THB)",
                "Target (THB)",
                "Exposure (THB)",
            ]
        )

    month_key = report_date.strftime("%Y-%m")
    monthly_fx = float(
        (sim.get("fx_used_usd_by_month") or {}).get(month_key, 0.0) or 0.0
    )

    summary = pd.DataFrame(
        [
            {
                "วันที่": report_date.isoformat(),
                "ออเดอร์วันนี้": int(len(today_df)),
                "ออเดอร์สำเร็จ": int(len(successful)),
                "Reject": int(len(rejected)),
                "Volume วันนี้ (THB)": volume_today,
                "P&L วันนี้ (THB)": pnl_today,
                "P&L สะสม (THB)": pnl_total,
                "NC Buffer ล่าสุด (THB)": latest_nc,
                "Unhedged สะสม (THB)": float(
                    sim.get("unhedged_thb", 0.0) or 0.0
                ),
                "FX ใช้สะสมเดือน (USD)": monthly_fx,
                "CEX Liquidity ใช้สะสม (THB)": float(
                    sim.get("cex_used_thb", 0.0) or 0.0
                ),
            }
        ]
    )

    print(
        f"[report] date={report_date} total_orders={len(orders)} "
        f"today_orders={len(today_df)} successful={len(successful)} "
        f"reject={len(rejected)}"
    )

    return summary, today_df, rejected, exposure


def excel_bytes(summary, today, rejects, exposure) -> bytes:
    from openpyxl import Workbook
    from openpyxl.utils.dataframe import dataframe_to_rows

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"

    for row in dataframe_to_rows(summary, index=False, header=True):
        ws.append(row)

    for name, frame in [
        ("Orders", today),
        ("Rejects", rejects),
        ("Exposure", exposure),
    ]:
        ws2 = wb.create_sheet(name)
        if frame.empty:
            ws2.append(["ไม่มีข้อมูล"])
        else:
            for row in dataframe_to_rows(frame, index=False, header=True):
                ws2.append(row)

        ws2.freeze_panes = "A2"
        for column in ws2.columns:
            width = min(
                max(len(str(cell.value or "")) for cell in column) + 2,
                40,
            )
            ws2.column_dimensions[column[0].column_letter].width = width

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def _register_thai_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansThai-Regular.ttf",
        "C:/Windows/Fonts/leelawui.ttf",
        "C:/Windows/Fonts/THSarabunNew.ttf",
    ]

    for font_path in candidates:
        if Path(font_path).is_file():
            try:
                pdfmetrics.registerFont(TTFont("DailyThai", font_path))
                return "DailyThai"
            except Exception as exc:
                print(f"[pdf] font load failed {font_path}: {exc}")

    print("[pdf] Thai font not found; fallback to Helvetica")
    return "Helvetica"


def pdf_bytes(summary, today, rejects, exposure) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    font = _register_thai_font()

    out = BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=landscape(A4),
        rightMargin=22,
        leftMargin=22,
        topMargin=22,
        bottomMargin=22,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DailyTitle",
            parent=styles["Title"],
            fontName=font,
            fontSize=18,
            leading=22,
            alignment=TA_LEFT,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DailyHeading",
            parent=styles["Heading3"],
            fontName=font,
            fontSize=12,
            leading=15,
            spaceBefore=8,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DailyNormal",
            parent=styles["Normal"],
            fontName=font,
            fontSize=9,
            leading=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DailyCell",
            parent=styles["Normal"],
            fontName=font,
            fontSize=6.5,
            leading=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DailyHeader",
            parent=styles["Normal"],
            fontName=font,
            fontSize=6.5,
            leading=8,
            textColor=colors.white,
        )
    )

    story = [
        Paragraph("XSpring Dealer Suite — Daily Report", styles["DailyTitle"]),
        Paragraph(
            datetime.now(BANGKOK).strftime("สร้างเมื่อ %Y-%m-%d %H:%M:%S (เวลาไทย)"),
            styles["DailyNormal"],
        ),
    ]

    def fmt_value(value):
        if value is None:
            return "—"
        if isinstance(value, float) and np.isnan(value):
            return "—"
        if isinstance(value, (float, np.floating)):
            return f"{float(value):,.4f}"
        if isinstance(value, (int, np.integer)):
            return f"{int(value):,}"
        return str(value)

    def add_dataframe(frame: pd.DataFrame, title: str, max_rows: int = 30):
        story.append(Spacer(1, 6))
        story.append(Paragraph(title, styles["DailyHeading"]))

        if frame.empty:
            story.append(Paragraph("ไม่มีข้อมูล", styles["DailyNormal"]))
            return

        view = frame.head(max_rows).copy()
        headers = [Paragraph(str(c), styles["DailyHeader"]) for c in view.columns]
        rows = [headers]
        for values in view.itertuples(index=False, name=None):
            rows.append(
                [Paragraph(fmt_value(v), styles["DailyCell"]) for v in values]
            )

        # ป้องกันหัวตารางยาวจนล้นหน้า
        table = Table(rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20242b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(table)

    add_dataframe(summary, "สรุปประจำวัน", 5)
    add_dataframe(exposure, "Exposure", 30)
    add_dataframe(rejects, "Reject วันนี้", 30)

    doc.build(story)
    return out.getvalue()


def send_telegram(files: list[Path]) -> bool:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return False

    import requests

    ok = True
    for path in files:
        try:
            with path.open("rb") as fh:
                response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={
                        "chat_id": chat_id,
                        "caption": path.name,
                    },
                    files={
                        "document": (
                            path.name,
                            fh,
                            "application/octet-stream",
                        )
                    },
                    timeout=60,
                )
            if not response.ok:
                ok = False
                print("[telegram]", response.text[:500])
        except Exception as exc:
            ok = False
            print("[telegram]", exc)

    return ok


def send_email(files: list[Path], report_date: date) -> bool:
    host = env("SMTP_HOST")
    user = env("SMTP_USER")
    password = env("SMTP_PASSWORD")
    recipient = env("REPORT_TO_EMAIL")

    if not (host and user and password and recipient):
        return False

    port = int(env("SMTP_PORT", "587"))

    msg = EmailMessage()
    msg["Subject"] = (
        f"XSpring Dealer Suite — Daily Report {report_date.isoformat()}"
    )
    msg["From"] = user
    msg["To"] = recipient
    msg.set_content(
        "แนบ Daily Report ของ XSpring Dealer Suite (PDF + Excel)"
    )

    for path in files:
        data = path.read_bytes()
        subtype = (
            "pdf"
            if path.suffix.lower() == ".pdf"
            else "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        msg.add_attachment(
            data,
            maintype="application",
            subtype=subtype,
            filename=path.name,
        )

    with smtplib.SMTP(host, port, timeout=60) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate and send XSpring Dealer Suite Daily Report."
    )
    parser.add_argument(
        "--date",
        help="YYYY-MM-DD; default = วันนี้ตามเวลา Asia/Bangkok",
    )
    parser.add_argument(
        "--out-dir",
        default=str(BASE / "daily_reports"),
    )
    args = parser.parse_args()

    report_date = (
        pd.Timestamp(args.date).date()
        if args.date
        else report_today_bangkok()
    )

    print(f"[report] using report date: {report_date}")

    sim = load_sim()
    summary, today, rejects, exposure = build_report(sim, report_date)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = f"xspring_daily_report_{report_date.isoformat()}"
    xlsx_path = out_dir / f"{stem}.xlsx"
    pdf_path = out_dir / f"{stem}.pdf"

    xlsx_path.write_bytes(
        excel_bytes(summary, today, rejects, exposure)
    )
    pdf_path.write_bytes(
        pdf_bytes(summary, today, rejects, exposure)
    )

    email_ok = send_email([pdf_path, xlsx_path], report_date)
    telegram_ok = send_telegram([pdf_path, xlsx_path])

    result = {
        "date": str(report_date),
        "pdf": str(pdf_path),
        "xlsx": str(xlsx_path),
        "email": email_ok,
        "telegram": telegram_ok,
        "orders_today": int(len(today)),
        "rejects_today": int(len(rejects)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not (email_ok or telegram_ok):
        raise SystemExit(
            "สร้างไฟล์แล้ว แต่ยังไม่ได้ส่ง: "
            "ตั้งค่า TELEGRAM_* หรือ SMTP_* อย่างน้อยหนึ่งช่องทาง"
        )


if __name__ == "__main__":
    main()
