from __future__ import annotations

import os
import json
import argparse
import smtplib
from pathlib import Path
from datetime import datetime, timezone
from email.message import EmailMessage
from io import BytesIO

import pandas as pd
import numpy as np


BASE = Path(__file__).resolve().parent


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def load_sim() -> dict:
    path = Path(env("XSPRING_SIM_STATE", str(BASE / "sim_state.json")))
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            raise RuntimeError(f"อ่าน sim state ไม่สำเร็จ: {exc}") from exc

    # Optional cloud mode: read the user's sim_state from Supabase.
    url = env("SUPABASE_URL")
    key = env("SUPABASE_KEY")
    actor = env("XSPRING_REPORT_ACTOR")
    if url and key and actor:
        import requests

        res = requests.get(
            f"{url.rstrip('/')}/rest/v1/sim_state",
            params={"select": "data", "actor": f"eq.{actor}", "limit": "1"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
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
    """
    ดึงราคาตลาดโดยตรงจาก Yahoo Finance และแปลง USD -> THB
    โดยไม่เรียก fetch_price_data() ของ Dealer Suite เพื่อหลีกเลี่ยง
    ปัญหา pandas/yfinance MultiIndex ที่ทำให้เกิด Length mismatch.

    คืนค่าเป็นราคาต่อ 1 เหรียญใน THB เช่น BTC -> BTC/USD * USD/THB.
    ถ้าดึงราคาเหรียญใดไม่ได้ จะข้ามเฉพาะเหรียญนั้นและยังสร้างรายงานต่อได้.
    """
    if not assets:
        return {}

    try:
        import yfinance as yf
    except Exception as exc:
        print(f"[price] yfinance import failed: {exc}")
        return {}

    def last_close(ticker: str) -> float | None:
        try:
            # history() ให้ DataFrame ตรง ๆ และไม่ต้องพึ่งโครงสร้างคอลัมน์
            # ของ fetch_price_data() ใน Dealer Suite
            frame = yf.Ticker(ticker).history(
                period="5d",
                interval="1d",
                auto_adjust=False,
                actions=False,
            )
            if frame is None or frame.empty or "Close" not in frame.columns:
                return None

            close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
            if close.empty:
                return None
            return float(close.iloc[-1])
        except Exception as exc:
            print(f"[price] {ticker}: {exc}")
            return None

    # USD/THB สำหรับแปลงราคาสินทรัพย์จาก USD เป็นบาท
    usdthb = last_close("USDTHB=X")
    if usdthb is None or usdthb <= 0:
        print("[price] USDTHB=X unavailable; cannot convert market prices to THB")
        return {}

    prices: dict[str, float] = {}
    for asset in sorted(set(str(a).upper() for a in assets if a)):
        try:
            # Stablecoins ใช้ 1 USD เป็นฐานเพื่อให้รายงานไม่แกว่งจาก ticker เล็ก ๆ
            if asset in {"USDT", "USDC"}:
                prices[asset] = float(usdthb)
                continue

            usd_price = last_close(f"{asset}-USD")
            if usd_price is not None and usd_price >= 0:
                prices[asset] = float(usd_price) * float(usdthb)
            else:
                print(f"[price] {asset}: no valid USD price")
        except Exception as exc:
            print(f"[price] {asset}: {exc}")

    print(f"[price] loaded {len(prices)}/{len(set(assets))} assets; USDTHB={usdthb:.4f}")
    return prices


def build_report(sim: dict, report_date):
    orders = [x for x in sim.get("orders", []) if isinstance(x, dict)]
    all_df = pd.DataFrame(orders)

    if all_df.empty:
        today_df = pd.DataFrame()
    else:
        dates = pd.to_datetime(all_df.get("วันที่"), errors="coerce")
        today_df = all_df[dates.dt.date == report_date].copy()

    result_col = (
        today_df.get("ผลด่าน", pd.Series(dtype=str)).astype(str)
        if not today_df.empty
        else pd.Series(dtype=str)
    )
    rejected = (
        today_df[result_col.str.startswith("Reject")].copy()
        if not today_df.empty
        else today_df.copy()
    )
    successful = (
        today_df[~result_col.str.startswith("Reject")].copy()
        if not today_df.empty
        else today_df.copy()
    )

    def num(frame, col):
        if frame.empty or col not in frame.columns:
            return 0.0
        return float(pd.to_numeric(frame[col], errors="coerce").fillna(0).sum())

    pnl_today = num(successful, "กำไรออเดอร์")
    volume_today = num(today_df, "มูลค่า (บาท)")
    pnl_total = float(sim.get("pnl_thb", 0.0) or 0.0)

    latest_nc = np.nan
    if not all_df.empty and "NC Buffer" in all_df.columns:
        nc_series = pd.to_numeric(all_df["NC Buffer"], errors="coerce").dropna()
        if not nc_series.empty:
            latest_nc = float(nc_series.iloc[-1])

    assets = list((sim.get("inv_coins") or {}).keys())
    prices = load_prices(assets)
    target = float(sim.get("target_thb", 0.0) or 0.0)

    exposure_rows = []
    for asset, quantity in (sim.get("inv_coins") or {}).items():
        qty = float(quantity or 0.0)
        price = float(prices.get(asset, 0.0))
        stock_value = qty * price
        exposure_rows.append(
            {
                "เหรียญ": asset,
                "จำนวน": qty,
                "ราคาล่าสุด (THB)": price,
                "มูลค่าสต็อก (THB)": stock_value,
                "Target (THB)": target,
                "Exposure (THB)": stock_value - target if price > 0 else np.nan,
            }
        )

    exposure = pd.DataFrame(exposure_rows)

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
                "FX ใช้สะสมเดือน (USD)": float(
                    (sim.get("fx_used_usd_by_month") or {}).get(
                        report_date.strftime("%Y-%m"), 0.0
                    )
                ),
                "CEX Liquidity ใช้สะสม (THB)": float(
                    sim.get("cex_used_thb", 0.0) or 0.0
                ),
            }
        ]
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
                max(len(str(cell.value or "")) for cell in column) + 2, 40
            )
            ws2.column_dimensions[column[0].column_letter].width = width

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def pdf_bytes(summary, today, rejects, exposure) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font = "Helvetica"
    font_candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "C:/Windows/Fonts/leelawui.ttf",
        "C:/Windows/Fonts/THSarabunNew.ttf",
    ]

    for font_path in font_candidates:
        if Path(font_path).is_file():
            try:
                pdfmetrics.registerFont(TTFont("DailyThai", font_path))
                font = "DailyThai"
                break
            except Exception:
                pass

    out = BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=landscape(A4),
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24,
    )

    styles = getSampleStyleSheet()
    styles["Title"].fontName = font
    styles["Normal"].fontName = font
    styles["Heading3"].fontName = font

    story = [
        Paragraph("XSpring Dealer Suite — Daily Report", styles["Title"]),
        Spacer(1, 8),
        Paragraph(
            datetime.now(timezone.utc)
            .astimezone()
            .strftime("Generated %Y-%m-%d %H:%M:%S %Z"),
            styles["Normal"],
        ),
    ]

    def add_dataframe(frame, title):
        story.append(Spacer(1, 8))
        story.append(Paragraph(title, styles["Heading3"]))

        if frame.empty:
            story.append(Paragraph("ไม่มีข้อมูล", styles["Normal"]))
            return

        view = frame.head(30).copy()
        view = view.astype(object).where(pd.notna(view), "—").astype(str)
        table_data = [list(view.columns)] + view.values.tolist()

        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20242b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("FONTNAME", (0, 0), (-1, -1), font),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)

    add_dataframe(summary, "สรุปประจำวัน")
    add_dataframe(exposure, "Exposure")
    add_dataframe(rejects, "Reject วันนี้")

    doc.build(story)
    return out.getvalue()


def send_telegram(files: list[Path]) -> bool:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
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
            ok = ok and response.ok
            if not response.ok:
                print("[telegram]", response.text[:500])
        except Exception as exc:
            print("[telegram]", exc)
            ok = False

    return ok


def send_email(files: list[Path], report_date) -> bool:
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
        help="YYYY-MM-DD; default = today",
    )
    parser.add_argument(
        "--out-dir",
        default=str(BASE / "daily_reports"),
    )
    args = parser.parse_args()

    report_date = (
        pd.Timestamp(args.date).date()
        if args.date
        else datetime.now().date()
    )

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
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not (email_ok or telegram_ok):
        raise SystemExit(
            "สร้างไฟล์แล้ว แต่ยังไม่ได้ส่ง: "
            "ตั้งค่า SMTP_* หรือ TELEGRAM_* อย่างน้อยหนึ่งช่องทาง"
        )


if __name__ == "__main__":
    main()
