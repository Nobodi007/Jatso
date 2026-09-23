"""
xspring_telegram_bot.py
========================
XSpring Dealer Suite - Telegram status bot

รันแยกจาก Streamlit:
    python xspring_telegram_bot.py

Environment variables:
    TELEGRAM_BOT_TOKEN     - token จาก @BotFather
    SUPABASE_URL           - URL ของ Supabase project
    SUPABASE_KEY           - Supabase key ที่ bot ใช้อ่าน/เขียนข้อมูล
    XSPRING_ALLOWED_EMAIL  - optional, comma-separated emails
                             เช่น user1@gmail.com,user2@gmail.com
                             ใช้ "*" เพื่ออนุญาตทุก email

คำสั่ง:
    /start
    /help
    /link your@email.com
    /unlink
    /whoami
    /status
    /nc
    /snapshot
    /history
    /wallet
    /portfolio
    /risk
    /price BTC
    /prices
"""

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import uuid
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

ALLOWED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("XSPRING_ALLOWED_EMAIL", "").split(",")
    if e.strip()
}

# Supabase Python client
try:
    from supabase import create_client
except ImportError:
    create_client = None

sb = None
if create_client and SUPABASE_URL and SUPABASE_KEY:
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as exc:
        print(f"[Supabase] client init error: {exc}")


# =========================================================
# Telegram low-level API
# =========================================================

def tg_call(method: str, payload: dict) -> dict:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("ยังไม่ได้ตั้ง TELEGRAM_BOT_TOKEN")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=40) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram API error"))

    return result


def send_message(chat_id: int, text: str) -> None:
    # ใช้ plain text เพื่อไม่ให้ email / เครื่องหมายพิเศษ
    # ทำให้ Telegram Markdown parse พัง
    tg_call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
        },
    )


def get_updates(offset: Optional[int] = None) -> list[dict]:
    payload = {"timeout": 30}
    if offset is not None:
        payload["offset"] = offset

    return tg_call("getUpdates", payload).get("result", [])


def set_bot_commands() -> None:
    """ตั้งเมนูคำสั่งที่ Telegram แสดงเมื่อผู้ใช้พิมพ์ /"""
    commands = [
        {"command": "status", "description": "ภาพรวมระบบ / NC / Wallet"},
        {"command": "nc", "description": "เช็ค NC Buffer ล่าสุด"},
        {"command": "snapshot", "description": "ดู Snapshot ล่าสุดแบบละเอียด"},
        {"command": "history", "description": "ดู NC Snapshot ย้อนหลัง"},
        {"command": "wallet", "description": "ดูเงินและเหรียญในกระเป๋าจำลอง"},
        {"command": "portfolio", "description": "ดู Portfolio แบบสรุป"},
        {"command": "risk", "description": "ตรวจสถานะความเสี่ยง NC"},
        {"command": "config", "description": "ดูค่าพารามิเตอร์เว็บล่าสุด"},
        {"command": "set", "description": "แก้พารามิเตอร์เว็บ เช่น /set capital 100000000"},
        {"command": "price", "description": "เช็คราคา เช่น /price BTC"},
        {"command": "prices", "description": "ดูราคาหลายเหรียญ"},
        {"command": "news", "description": "ข่าวคริปโทล่าสุด 1 ข่าว"},
        {"command": "buy", "description": "ซื้อใน Exchange Simulator"},
        {"command": "sell", "description": "ขายใน Exchange Simulator"},
        {"command": "confirm", "description": "ยืนยันคำสั่งซื้อขาย"},
        {"command": "cancel", "description": "ยกเลิกคำสั่งที่รอยืนยัน"},
        {"command": "orders", "description": "ดูรายการซื้อขายล่าสุด"},
        {"command": "whoami", "description": "ดูบัญชีที่ Telegram เชื่อมอยู่"},
        {"command": "link", "description": "เชื่อมบัญชี Telegram กับเว็บ"},
        {"command": "unlink", "description": "ยกเลิกการเชื่อมบัญชี"},
        {"command": "help", "description": "แสดงคำสั่งทั้งหมด"},
    ]
    try:
        tg_call("setMyCommands", {"commands": commands})
        print("[Telegram] command menu updated")
    except Exception as exc:
        print(f"[Telegram] setMyCommands error: {exc}")


# =========================================================
# Validation / configuration
# =========================================================

def validate_config() -> None:
    missing = []

    if not TELEGRAM_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")

    if missing:
        raise SystemExit(
            "ยังไม่ได้ตั้ง environment variable: "
            + ", ".join(missing)
        )

    if sb is None:
        raise SystemExit(
            "โหลด Supabase client ไม่สำเร็จ — "
            "ติดตั้งด้วย: pip install supabase"
        )


# =========================================================
# Telegram <-> email linking
# =========================================================

def link_email(chat_id: int, email: str) -> str:
    email = email.strip().lower()

    if not email or "@" not in email:
        return "ใช้แบบนี้: /link your@email.com"

    if ALLOWED_EMAILS and "*" not in ALLOWED_EMAILS:
        if email not in ALLOWED_EMAILS:
            return "❌ อีเมลนี้ไม่ได้รับอนุญาตให้ใช้งานระบบ"

    if sb is None:
        return "⚠️ ยังไม่ได้ตั้งค่า Supabase — เชื่อมบัญชีไม่ได้"

    try:
        # ป้องกัน 1 Telegram chat ผูกกับ email อื่นโดยไม่ตั้งใจ
        existing = (
            sb.table("telegram_links")
            .select("email")
            .eq("chat_id", chat_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            old_email = str(existing.data[0].get("email", "")).lower()
            if old_email and old_email != email:
                return (
                    f"⚠️ Telegram นี้เชื่อมกับ {old_email} อยู่แล้ว\n"
                    "ถ้าต้องการเปลี่ยนบัญชี ต้อง unlink ก่อน"
                )

        sb.table("telegram_links").upsert(
            {
                "email": email,
                "chat_id": chat_id,
                "linked_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        return (
            f"✅ เชื่อมบัญชี {email} กับ Telegram นี้เรียบร้อย\n"
            "ใช้ /nc หรือ /wallet ได้เลย"
        )

    except Exception as exc:
        print(f"[link] error: {exc}")
        return "❌ เชื่อมบัญชีไม่สำเร็จ กรุณาตรวจสอบ Supabase และลองใหม่"


def email_for_chat(chat_id: int) -> Optional[str]:
    if sb is None:
        return None

    try:
        res = (
            sb.table("telegram_links")
            .select("email")
            .eq("chat_id", chat_id)
            .limit(1)
            .execute()
        )

        if res.data:
            return str(res.data[0]["email"]).strip().lower()

    except Exception as exc:
        print(f"[email_for_chat] error: {exc}")

    return None


def unlink_chat(chat_id: int) -> str:
    if sb is None:
        return "⚠️ ไม่มี Supabase"

    try:
        existing = (
            sb.table("telegram_links")
            .select("email")
            .eq("chat_id", chat_id)
            .limit(1)
            .execute()
        )

        if not existing.data:
            return "ตอนนี้ Telegram นี้ยังไม่ได้เชื่อมบัญชี"

        email = existing.data[0]["email"]

        sb.table("telegram_links").delete().eq(
            "chat_id", chat_id
        ).execute()

        return f"✅ ยกเลิกการเชื่อมบัญชี {email} แล้ว"

    except Exception as exc:
        print(f"[unlink] error: {exc}")
        return "❌ ยกเลิกการเชื่อมบัญชีไม่สำเร็จ"


# =========================================================
# XSpring status commands
# =========================================================

def cmd_nc(chat_id: int) -> str:
    email = email_for_chat(chat_id)

    if not email:
        return (
            "ยังไม่ได้เชื่อมบัญชี\n"
            "พิมพ์ /link your@email.com ก่อน"
        )

    try:
        res = (
            sb.table("nc_snapshots")
            .select("*")
            .eq("actor", email)
            .order("snapshot_at", desc=True)
            .limit(1)
            .execute()
        )

        if not res.data:
            return (
                "ยังไม่มี NC Snapshot ที่บันทึกไว้\n"
                "เข้าเว็บแล้วบันทึก Snapshot ในหน้า Liquidity Planner ก่อน"
            )

        s = res.data[0]

        buf = float(s.get("nc_buffer") or 0)
        req_nc = float(s.get("nc_required") or 0)
        actual = float(s.get("nc_actual") or 0)

        if buf < 0:
            icon = "🚨"
        elif req_nc > 0 and buf < 0.5 * req_nc:
            icon = "⚠️"
        else:
            icon = "✅"

        asset = s.get("asset") or "-"
        snapshot_at = str(s.get("snapshot_at") or "-")
        snapshot_at = snapshot_at[:16].replace("T", " ")

        return (
            f"{icon} NC Snapshot ({asset})\n"
            f"เวลา: {snapshot_at}\n"
            f"NC จริง: ฿{actual:,.0f}\n"
            f"NC ขั้นต่ำ: ฿{req_nc:,.0f}\n"
            f"Buffer: ฿{buf:+,.0f}"
        )

    except Exception as exc:
        print(f"[nc] error: {exc}")
        return "❌ อ่าน NC Snapshot ไม่สำเร็จ"


def cmd_wallet(chat_id: int) -> str:
    email = email_for_chat(chat_id)

    if not email:
        return (
            "ยังไม่ได้เชื่อมบัญชี\n"
            "พิมพ์ /link your@email.com ก่อน"
        )

    try:
        res = (
            sb.table("sim_state")
            .select("data")
            .eq("actor", email)
            .limit(1)
            .execute()
        )

        if not res.data:
            return (
                "ยังไม่มีข้อมูลกระเป๋าจำลอง\n"
                "เข้าเว็บแล้วลองซื้อขายใน Exchange UI Simulator ก่อน"
            )

        sim = res.data[0].get("data") or {}

        try:
            cash = float(sim.get("customer_thb", 0.0) or 0.0)
        except (TypeError, ValueError):
            cash = 0.0

        coins = sim.get("customer_coins") or {}

        lines = [
            "💰 กระเป๋าจำลองของคุณ",
            f"เงินบาท: ฿{cash:,.2f}",
        ]

        if isinstance(coins, dict):
            for sym, qty in coins.items():
                try:
                    qty = float(qty)
                except (TypeError, ValueError):
                    continue

                if qty > 0:
                    lines.append(f"🪙 {sym}: {qty:,.6f}")

        return "\n".join(lines)

    except Exception as exc:
        print(f"[wallet] error: {exc}")
        return "❌ อ่านกระเป๋าจำลองไม่สำเร็จ"


def _binance_spot_ticker_24h(symbol: str):
    """Return (ticker_json, source_label, close_time_ms).

    Try Binance public Spot endpoints in order so the bot can still work
    when one hostname is blocked/unreachable from the Railway region.
    """
    symbol = symbol.upper().strip()
    encoded = urllib.parse.quote(f"{symbol}USDT", safe="")

    endpoints = [
        (
            f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={encoded}",
            "Binance Spot API · data-api.binance.vision",
        ),
        (
            f"https://api.binance.com/api/v3/ticker/24hr?symbol={encoded}",
            "Binance Spot API · api.binance.com",
        ),
        (
            f"https://api1.binance.com/api/v3/ticker/24hr?symbol={encoded}",
            "Binance Spot API · api1.binance.com",
        ),
    ]

    last_exc = None
    for url, source in endpoints:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "XSpring-Dealer-Bot/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                d = json.loads(response.read().decode("utf-8"))

            # Validate the minimum fields before accepting the endpoint.
            float(d["lastPrice"])
            float(d["priceChangePercent"])
            close_time_ms = int(d.get("closeTime") or 0)
            return d, source, close_time_ms
        except Exception as exc:
            last_exc = exc
            print(f"[price] endpoint failed: {url} -> {exc}")

    raise RuntimeError(f"Binance price endpoints unavailable: {last_exc}")


def _format_price_time(close_time_ms: int) -> str:
    """Format Binance ticker time as Thailand local time."""
    if not close_time_ms:
        return "ไม่ทราบเวลา"

    dt = datetime.fromtimestamp(close_time_ms / 1000.0, tz=timezone.utc)
    try:
        dt = dt.astimezone(ZoneInfo("Asia/Bangkok"))
    except Exception:
        # Fallback: keep UTC if zoneinfo data is unavailable.
        pass
    return dt.strftime("%d/%m/%Y %H:%M:%S") + " น."


def cmd_price(symbol: str) -> str:
    symbol = symbol.strip().upper()

    if not symbol:
        return "ใช้แบบนี้: /price BTC"

    if not symbol.isalnum():
        return "❌ Symbol ไม่ถูกต้อง เช่น BTC, ETH, SOL"

    try:
        d, source, close_time_ms = _binance_spot_ticker_24h(symbol)
        price = float(d["lastPrice"])
        change = float(d["priceChangePercent"])

        return (
            f"💹 {symbol}/USDT (Binance)\n"
            f"ราคา: ${price:,.2f}\n"
            f"เปลี่ยน 24H: {change:+.2f}%\n"
            f"Source: {source}\n"
            f"Time: {_format_price_time(close_time_ms)}"
        )

    except Exception as exc:
        print(f"[price] error for {symbol}: {exc}")
        return (
            f"ดึงราคา {symbol} ไม่สำเร็จ\n"
            "เช็คว่าสะกดถูกไหม เช่น BTC, ETH, SOL"
        )


def get_latest_snapshot(email: str):
    res = (
        sb.table("nc_snapshots")
        .select("*")
        .eq("actor", email)
        .order("snapshot_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def cmd_whoami(chat_id: int) -> str:
    email = email_for_chat(chat_id)
    if not email:
        return "👤 Telegram นี้ยังไม่ได้เชื่อมบัญชี\nใช้ /link your@email.com"

    try:
        res = (
            sb.table("telegram_links")
            .select("email,chat_id,linked_at")
            .eq("chat_id", chat_id)
            .limit(1)
            .execute()
        )
        linked_at = "-"
        if res.data:
            linked_at = str(res.data[0].get("linked_at") or "-")[:16].replace("T", " ")
        return (
            "👤 Account\n"
            f"Email: {email}\n"
            "Telegram: ✅ Linked\n"
            f"Linked at: {linked_at}"
        )
    except Exception as exc:
        print(f"[whoami] error: {exc}")
        return f"👤 Account\nEmail: {email}\nTelegram: ✅ Linked"


def cmd_snapshot(chat_id: int) -> str:
    email = email_for_chat(chat_id)
    if not email:
        return "ยังไม่ได้เชื่อมบัญชี\nพิมพ์ /link your@email.com ก่อน"

    try:
        s = get_latest_snapshot(email)
        if not s:
            return "ยังไม่มี NC Snapshot ที่บันทึกไว้\nเข้าเว็บแล้วบันทึก Snapshot ก่อน"

        def money(key):
            try:
                return f"฿{float(s.get(key) or 0):,.0f}"
            except (TypeError, ValueError):
                return "-"

        def number(key, digits=4):
            try:
                return f"{float(s.get(key) or 0):,.{digits}f}"
            except (TypeError, ValueError):
                return "-"

        snapshot_at = str(s.get("snapshot_at") or "-")[:16].replace("T", " ")
        price = number("price_usd", 2)
        fx = number("usdthb", 4)

        return (
            "📸 Latest NC Snapshot\n"
            f"เวลา: {snapshot_at}\n"
            f"Asset: {s.get('asset') or '-'}\n"
            f"Price USD: ${price}\n"
            f"USD/THB: {fx}\n"
            f"Required Stock: {money('required_stock_thb')}\n"
            f"Total Capital: {money('total_capital_thb')}\n"
            f"CEX Margin: {money('cex_margin_thb')}\n"
            f"Liabilities: {money('liab_thb')}\n"
            f"NC Actual: {money('nc_actual')}\n"
            f"NC Required: {money('nc_required')}\n"
            f"NC Buffer: {money('nc_buffer')}"
        )
    except Exception as exc:
        print(f"[snapshot] error: {exc}")
        return "❌ อ่าน Snapshot ไม่สำเร็จ"


def cmd_history(chat_id: int) -> str:
    email = email_for_chat(chat_id)
    if not email:
        return "ยังไม่ได้เชื่อมบัญชี\nพิมพ์ /link your@email.com ก่อน"

    try:
        res = (
            sb.table("nc_snapshots")
            .select("snapshot_at,asset,nc_actual,nc_required,nc_buffer")
            .eq("actor", email)
            .order("snapshot_at", desc=True)
            .limit(5)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return "ยังไม่มี NC Snapshot ในประวัติ"

        lines = ["📚 NC History (ล่าสุด 5 รายการ)"]
        for i, s in enumerate(rows, 1):
            ts = str(s.get("snapshot_at") or "-")[:16].replace("T", " ")
            try:
                actual = float(s.get("nc_actual") or 0)
                required = float(s.get("nc_required") or 0)
                buf = float(s.get("nc_buffer") or 0)
                lines.append(
                    f"{i}. {ts} | {s.get('asset') or '-'}\n"
                    f"   Actual ฿{actual:,.0f} | Required ฿{required:,.0f} | Buffer ฿{buf:+,.0f}"
                )
            except (TypeError, ValueError):
                lines.append(f"{i}. {ts} | อ่านตัวเลขไม่ได้")

        return "\n".join(lines)
    except Exception as exc:
        print(f"[history] error: {exc}")
        return "❌ อ่านประวัติ NC ไม่สำเร็จ"


def cmd_status(chat_id: int) -> str:
    email = email_for_chat(chat_id)
    if not email:
        return (
            "🤖 XSpring Dealer Suite\n\n"
            "Telegram: 🟡 ยังไม่ได้เชื่อมบัญชี\n"
            "ใช้ /link your@email.com"
        )

    try:
        s = get_latest_snapshot(email)
        wallet_text = cmd_wallet(chat_id)

        lines = [
            "🤖 XSpring Dealer Suite",
            "",
            f"👤 {email}",
            "🔗 Telegram: ✅ Linked",
            "",
            "📊 NC",
        ]

        if s:
            actual = float(s.get("nc_actual") or 0)
            required = float(s.get("nc_required") or 0)
            buf = float(s.get("nc_buffer") or 0)

            if buf < 0:
                status = "🚨 BELOW REQUIRED"
            elif required > 0 and buf < 0.5 * required:
                status = "⚠️ LOW BUFFER"
            else:
                status = "🟢 NORMAL"

            lines.extend([
                f"Actual:   ฿{actual:,.0f}",
                f"Required: ฿{required:,.0f}",
                f"Buffer:   ฿{buf:+,.0f}",
                f"Status:   {status}",
            ])
        else:
            lines.append("ยังไม่มี Snapshot")

        lines.extend(["", "💰 Wallet", wallet_text, "", "🟢 Bot: Online"])
        return "\n".join(lines)
    except Exception as exc:
        print(f"[status] error: {exc}")
        return "❌ อ่าน Status ไม่สำเร็จ"


def cmd_risk(chat_id: int) -> str:
    email = email_for_chat(chat_id)
    if not email:
        return "ยังไม่ได้เชื่อมบัญชี\nพิมพ์ /link your@email.com ก่อน"

    try:
        s = get_latest_snapshot(email)
        if not s:
            return "ยังไม่มี NC Snapshot สำหรับประเมิน Risk"

        actual = float(s.get("nc_actual") or 0)
        required = float(s.get("nc_required") or 0)
        buf = float(s.get("nc_buffer") or 0)

        if buf < 0:
            status = "🚨 BELOW REQUIRED"
        elif required > 0 and buf < 0.5 * required:
            status = "⚠️ LOW BUFFER"
        else:
            status = "🟢 NORMAL"

        ratio = (buf / required * 100) if required else 0

        return (
            "🛡 Risk Status\n\n"
            f"NC Actual:   ฿{actual:,.0f}\n"
            f"NC Required: ฿{required:,.0f}\n"
            f"NC Buffer:   ฿{buf:+,.0f}\n"
            f"Buffer vs Required: {ratio:+.1f}%\n\n"
            f"Status: {status}"
        )
    except Exception as exc:
        print(f"[risk] error: {exc}")
        return "❌ ประเมิน Risk ไม่สำเร็จ"


def cmd_portfolio(chat_id: int) -> str:
    email = email_for_chat(chat_id)
    if not email:
        return "ยังไม่ได้เชื่อมบัญชี\nพิมพ์ /link your@email.com ก่อน"

    try:
        res = (
            sb.table("sim_state")
            .select("data")
            .eq("actor", email)
            .limit(1)
            .execute()
        )
        if not res.data:
            return "ยังไม่มีข้อมูล Portfolio จำลอง"

        sim = res.data[0].get("data") or {}
        try:
            cash = float(sim.get("customer_thb", 0) or 0)
        except (TypeError, ValueError):
            cash = 0

        coins = sim.get("customer_coins") or {}
        lines = ["📦 Portfolio", f"THB: ฿{cash:,.2f}"]

        found = False
        if isinstance(coins, dict):
            for sym, qty in coins.items():
                try:
                    q = float(qty)
                except (TypeError, ValueError):
                    continue
                if q > 0:
                    found = True
                    lines.append(f"{str(sym).upper()}: {q:,.8f}")

        if not found:
            lines.append("เหรียญ: ไม่มี")

        return "\n".join(lines)
    except Exception as exc:
        print(f"[portfolio] error: {exc}")
        return "❌ อ่าน Portfolio ไม่สำเร็จ"



# =========================================================
# Remote Web Control — Telegram <-> Supabase <-> Streamlit
# =========================================================

REMOTE_CONFIG_TABLE = "dealer_remote_config"

# key ที่ผู้ใช้เห็นใน Telegram -> รูปแบบข้อมูล/ช่วงที่อนุญาต
REMOTE_PARAMS = {
    "asset": {"label": "Asset", "kind": "choice", "choices": ["BTC", "ETH", "SOL", "DOGE", "ADA", "HBAR", "LINK", "XLM", "XRP", "USDT", "USDC"]},
    "exchange": {"label": "Global Exchange", "kind": "choice", "choices": ["Binance", "Coinbase", "Kraken", "OKX", "กำหนดเอง (Custom)"]},
    "trade_vol": {"label": "Daily Trade Volume USD eq.", "kind": "float", "lo": 0, "hi": 1_000_000_000_000},
    "spread": {"label": "Dealer Spread %", "kind": "float", "lo": 0, "hi": 100},
    "hedge_taker": {"label": "Hedge Taker Fee %", "kind": "float", "lo": 0, "hi": 100},
    "hedge_maker": {"label": "Hedge Maker Fee %", "kind": "float", "lo": 0, "hi": 100},
    "maker_ratio": {"label": "Maker Ratio %", "kind": "float", "lo": 0, "hi": 100},
    "fx_limit": {"label": "FX Limit USD/month", "kind": "float", "lo": 1, "hi": 1_000_000_000_000},
    "premium": {"label": "Local Premium/Discount %", "kind": "float", "lo": -100, "hi": 100},
    "slippage": {"label": "Slippage Sensitivity %", "kind": "float", "lo": 0, "hi": 100},
    "depth": {"label": "Market Depth USD", "kind": "float", "lo": 0, "hi": 1_000_000_000_000},
    "impact_penalty": {"label": "Impact Penalty %", "kind": "float", "lo": 0, "hi": 100},
    "monthly_volume": {"label": "Monthly Volume THB", "kind": "float", "lo": 0, "hi": 10_000_000_000_000},
    "net_bias": {"label": "Net Flow Bias %", "kind": "float", "lo": -100, "hi": 100},
    "flow_cv": {"label": "Flow CV %", "kind": "float", "lo": 10, "hi": 150},
    "lag": {"label": "Settlement Lag days", "kind": "int", "lo": 1, "hi": 10},
    "confidence": {"label": "Safety Stock Confidence", "kind": "choice_num", "choices": [90, 95, 99, 99.9]},
    "capital": {"label": "Total Capital THB", "kind": "float", "lo": 0, "hi": 10_000_000_000_000},
    "margin": {"label": "CEX Margin THB", "kind": "float", "lo": 0, "hi": 10_000_000_000_000},
    "liab": {"label": "Customer Liabilities THB", "kind": "float", "lo": 1, "hi": 10_000_000_000_000},
    "margin_asset": {"label": "CEX Margin Asset", "kind": "choice", "choices": ["Stablecoin", "เหรียญเดียวกับที่เทรด"]},
    "cp_haircut": {"label": "CEX Counterparty Haircut %", "kind": "float", "lo": 0, "hi": 100},
    "custodian": {"label": "Custodian", "kind": "bool"},
    "trading_risk": {"label": "NC Trading Risk Rate %", "kind": "float", "lo": 0, "hi": 100},
    "cold_foreign": {"label": "Cold Wallet Foreign NC %", "kind": "float", "lo": 1, "hi": 100},
    "hot_wallet": {"label": "Hot Wallet %", "kind": "float", "lo": 0, "hi": 100},
    "cold_domestic": {"label": "Cold Wallet Domestic %", "kind": "float", "lo": 0, "hi": 100},
}

REMOTE_ALIASES = {
    "setcapital": "capital", "setmargin": "margin", "setliab": "liab",
    "setspread": "spread", "setpremium": "premium", "setfxlimit": "fx_limit",
    "sethedgetaker": "hedge_taker", "sethedgemaker": "hedge_maker",
    "setmakerratio": "maker_ratio", "setmonthlyvolume": "monthly_volume",
    "setnetbias": "net_bias", "setflowcv": "flow_cv", "setlag": "lag",
    "setconfidence": "confidence", "setcphaircut": "cp_haircut",
    "settradingrisk": "trading_risk", "setcoldforeign": "cold_foreign",
    "sethotwallet": "hot_wallet", "setcolddomestic": "cold_domestic",
    "setslippage": "slippage", "setdepth": "depth", "setimpact": "impact_penalty",
    "setasset": "asset", "setexchange": "exchange", "setmarginasset": "margin_asset",
    "setcustodian": "custodian",
}

# ค่าตั้งต้นตรงกับ Sidebar ของ XSpring v26 เมื่อยังไม่เคยมี remote config
REMOTE_DEFAULTS = {
    "asset": "BTC", "exchange": "Binance", "trade_vol": 100000.0,
    "spread": 0.5, "hedge_taker": 0.10, "hedge_maker": 0.10, "maker_ratio": 0.0,
    "fx_limit": 5_000_000.0, "premium": 0.1, "slippage": 10.0, "depth": 0.0,
    "impact_penalty": 0.5, "monthly_volume": 80_000_000.0, "net_bias": 15.0,
    "flow_cv": 50.0, "lag": 1, "confidence": 99, "capital": 150_000_000.0,
    "margin": 30_000_000.0, "liab": 100_000_000.0, "margin_asset": "Stablecoin",
    "cp_haircut": 2.0, "custodian": True, "trading_risk": 2.0,
    "cold_foreign": 1.5, "hot_wallet": 30.0, "cold_domestic": 80.0,
}


def _linked_email_or_message(chat_id: int) -> tuple[Optional[str], Optional[str]]:
    email = email_for_chat(chat_id)
    if not email:
        return None, "ยังไม่ได้เชื่อมบัญชี\nพิมพ์ /link your@email.com ก่อน"
    if ALLOWED_EMAILS and "*" not in ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return None, "❌ บัญชีนี้ไม่ได้รับอนุญาตให้ควบคุมระบบ"
    return email, None


def _remote_config_row(email: str) -> Optional[dict]:
    if sb is None:
        return None
    res = (sb.table(REMOTE_CONFIG_TABLE)
             .select("actor,config,updated_at,updated_by,source")
             .eq("actor", email)
             .limit(1)
             .execute())
    return res.data[0] if res.data else None


def _remote_config(email: str) -> dict:
    row = _remote_config_row(email)
    cfg = dict(REMOTE_DEFAULTS)
    if row and isinstance(row.get("config"), dict):
        cfg.update(row["config"])
    return cfg


def _parse_remote_value(param: str, raw: str):
    spec = REMOTE_PARAMS[param]
    kind = spec["kind"]
    raw = raw.strip()
    if kind == "choice":
        for choice in spec["choices"]:
            if raw.lower() == str(choice).lower():
                return choice
        raise ValueError("ค่าต้องเป็นหนึ่งใน: " + ", ".join(map(str, spec["choices"])))
    if kind == "choice_num":
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            raise ValueError("ต้องเป็นตัวเลข")
        if not any(abs(value - float(x)) < 1e-9 for x in spec["choices"]):
            raise ValueError("ค่าที่ใช้ได้: 90, 95, 99, 99.9")
        return 99.9 if abs(value - 99.9) < 1e-9 else int(value)
    if kind == "bool":
        v = raw.lower()
        if v in {"on", "true", "1", "yes", "y"}: return True
        if v in {"off", "false", "0", "no", "n"}: return False
        raise ValueError("ใช้ on/off")
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        raise ValueError("ต้องเป็นตัวเลข")
    if kind == "int":
        if value != int(value):
            raise ValueError("ต้องเป็นจำนวนเต็ม")
        value = int(value)
    if value < spec["lo"] or value > spec["hi"]:
        raise ValueError(f"ต้องอยู่ในช่วง {spec['lo']} ถึง {spec['hi']}")
    return value


def _fmt_remote_value(param: str, value) -> str:
    if param in {"capital", "margin", "liab", "monthly_volume", "trade_vol"}:
        return f"{float(value):,.0f}"
    if param in {"fx_limit", "depth"}:
        return f"{float(value):,.0f}"
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return str(value)


def _audit_remote_change(email: str, chat_id: int, param: str, old, new) -> None:
    if sb is None:
        return
    try:
        sb.table("audit_log").insert({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session_id": f"tg-{chat_id}",
            "actor": email,
            "model_version": "telegram",
            "config_sha256": None,
            "event": "telegram_remote_config_change",
            "param": param,
            "old_value": old,
            "new_value": new,
            "params": {"source": "telegram", "chat_id": chat_id},
        }).execute()
    except Exception as exc:
        print(f"[remote_config audit] error: {exc}")


def cmd_remote_config(chat_id: int) -> str:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return err
    try:
        row = _remote_config_row(email)
        cfg = _remote_config(email)
        updated = str(row.get("updated_at") or "ยังไม่เคยบันทึก")[:19].replace("T", " ") if row else "ยังไม่เคยบันทึก"
        lines = ["⚙️ XSpring Remote Config", f"👤 {email}", f"Updated: {updated} UTC", ""]
        groups = [
            ("Dealer", ["asset", "exchange", "trade_vol", "spread", "hedge_taker", "hedge_maker", "maker_ratio", "fx_limit", "premium"]),
            ("Execution", ["slippage", "depth", "impact_penalty"]),
            ("Flow", ["monthly_volume", "net_bias", "flow_cv", "lag", "confidence"]),
            ("Capital / NC", ["capital", "margin", "liab", "margin_asset", "cp_haircut", "custodian", "trading_risk", "cold_foreign", "hot_wallet", "cold_domestic"]),
        ]
        for title, names in groups:
            lines.append(f"{title}:")
            for name in names:
                lines.append(f"  {name}: {_fmt_remote_value(name, cfg.get(name))}")
            lines.append("")
        lines.append("ใช้ /set <param> <value> เพื่อแก้ค่า")
        return "\n".join(lines).rstrip()
    except Exception as exc:
        print(f"[config] error: {exc}")
        return "❌ อ่าน Remote Config ไม่สำเร็จ"


def cmd_set_remote(chat_id: int, arg: str) -> str:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return err
    parts = arg.strip().split(maxsplit=1)
    if len(parts) != 2:
        return "ใช้แบบนี้: /set capital 100000000\nพิมพ์ /help เพื่อดู parameter"
    param = parts[0].lower().lstrip("/")
    param = REMOTE_ALIASES.get(param, param)
    if param not in REMOTE_PARAMS:
        return "❌ ไม่รู้จัก parameter: " + parts[0] + "\nใช้ /config เพื่อดูรายการ"
    try:
        new_value = _parse_remote_value(param, parts[1])
        current = _remote_config(email)
        old_value = current.get(param)
        current[param] = new_value

        sb.table(REMOTE_CONFIG_TABLE).upsert({
            "actor": email,
            "config": current,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": f"telegram:{chat_id}",
            "source": "telegram",
        }).execute()
        _audit_remote_change(email, chat_id, param, old_value, new_value)

        return (
            "✅ Remote Config อัปเดตแล้ว\n"
            f"👤 {email}\n"
            f"{param}: {_fmt_remote_value(param, old_value)} → {_fmt_remote_value(param, new_value)}\n\n"
            "รีเฟรชเว็บ XSpring Dealer Suite แล้วค่าจะถูกใช้กับการคำนวณ"
        )
    except Exception as exc:
        print(f"[set] error: {exc}")
        return f"❌ แก้ค่าไม่สำเร็จ: {exc}"

def cmd_prices(arg: str = "") -> str:
    symbols = [x.upper() for x in arg.split() if x.strip()]
    if not symbols:
        symbols = ["BTC", "ETH", "SOL"]

    if len(symbols) > 8:
        return "ใส่ได้สูงสุด 8 เหรียญ เช่น /prices BTC ETH SOL"

    lines = ["📈 Market Prices (Binance Spot)"]
    for symbol in symbols:
        if not symbol.isalnum():
            lines.append(f"{symbol}: ❌ symbol ไม่ถูกต้อง")
            continue

        try:
            d, source, close_time_ms = _binance_spot_ticker_24h(symbol)
            price = float(d["lastPrice"])
            change = float(d["priceChangePercent"])

            lines.append(
                f"{symbol}: ${price:,.2f} ({change:+.2f}%)\n"
                f"   Source: {source}\n"
                f"   Time: {_format_price_time(close_time_ms)}"
            )
        except Exception as exc:
            print(f"[prices] error for {symbol}: {exc}")
            lines.append(f"{symbol}: ❌ ดึงราคาไม่ได้")

    return "\n".join(lines)


# =========================================================
# News + Exchange Simulator via Telegram
# =========================================================

PENDING_ORDERS: dict[int, dict] = {}
NEWS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]
SUPPORTED_TRADE_ASSETS = {"BTC", "ETH", "SOL", "DOGE", "ADA", "HBAR", "LINK", "XLM", "XRP", "USDT", "USDC"}
LOCAL_TRADE_FEE = 0.0025
MIN_TRADE_THB = 50.0


def _http_text(url: str, timeout: float = 12.0) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "XSpring-Dealer-Bot/1.0", "Accept": "application/rss+xml, application/xml, text/xml"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _news_keywords(asset: str) -> list[str]:
    asset = (asset or "").strip().upper()
    return {
        "BTC": ["BTC", "BITCOIN"],
        "ETH": ["ETH", "ETHEREUM"],
        "SOL": ["SOL", "SOLANA"],
        "XRP": ["XRP", "RIPPLE"],
        "DOGE": ["DOGE", "DOGECOIN"],
        "ADA": ["ADA", "CARDANO"],
        "LINK": ["LINK", "CHAINLINK"],
        "XLM": ["XLM", "STELLAR"],
        "HBAR": ["HBAR", "HEDERA"],
        "USDT": ["USDT", "TETHER"],
        "USDC": ["USDC", "CIRCLE"],
    }.get(asset, [asset] if asset else [])


def _latest_news_item(asset: str = "") -> tuple[str, dict]:
    last_exc = None
    keywords = _news_keywords(asset)
    for source, url in NEWS_FEEDS:
        try:
            raw = _http_text(url)
            root = ET.fromstring(raw)
            candidates = root.findall(".//item")
            is_atom = False
            if not candidates:
                candidates = root.findall(".//{http://www.w3.org/2005/Atom}entry")
                is_atom = True
            if not candidates:
                raise RuntimeError("ไม่พบรายการข่าว")

            selected = candidates[0]
            # หาเรื่องล่าสุดที่เกี่ยวกับเหรียญที่ระบุ โดยค้นจาก title + description/summary
            if keywords:
                for candidate in candidates:
                    if is_atom:
                        title0 = candidate.findtext("{http://www.w3.org/2005/Atom}title") or ""
                        desc0 = candidate.findtext("{http://www.w3.org/2005/Atom}summary") or ""
                    else:
                        title0 = candidate.findtext("title") or ""
                        desc0 = candidate.findtext("description") or ""
                    hay = f"{title0} {desc0}".upper()
                    if any(k in hay for k in keywords):
                        selected = candidate
                        break

            item = selected
            if is_atom:
                title = item.findtext("{http://www.w3.org/2005/Atom}title") or ""
                link_node = item.find("{http://www.w3.org/2005/Atom}link")
                link = link_node.attrib.get("href", "") if link_node is not None else ""
                published = (item.findtext("{http://www.w3.org/2005/Atom}published")
                             or item.findtext("{http://www.w3.org/2005/Atom}updated") or "")
                desc = item.findtext("{http://www.w3.org/2005/Atom}summary") or ""
            else:
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                published = item.findtext("pubDate") or item.findtext("dc:date") or ""
                desc = item.findtext("description") or ""
            if not title.strip() or not link.strip():
                raise RuntimeError("ข่าวไม่มีหัวข้อหรือลิงก์")
            return source, {
                "title": _clean_html(title),
                "link": link.strip(),
                "published": published.strip(),
                "description": _clean_html(desc),
            }
        except Exception as exc:
            last_exc = exc
            print(f"[news] feed failed: {source} -> {exc}")
    raise RuntimeError(f"news feeds unavailable: {last_exc}")


def _format_news_time(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "ไม่ทราบเวลา"
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(ZoneInfo("Asia/Bangkok"))
        return dt.strftime("%d/%m/%Y %H:%M:%S") + " น. ICT"
    except Exception:
        return value[:80]


def cmd_news(asset: str = "") -> str:
    try:
        source, item = _latest_news_item(asset)
        desc = item.get("description", "")
        if len(desc) > 260:
            desc = desc[:257].rstrip() + "..."
        headline = f"📰 ข่าว {asset.upper()} ล่าสุด" if asset.strip() else "📰 ข่าวคริปโทล่าสุด"
        lines = [
            headline,
            "",
            item["title"],
        ]
        if desc:
            lines.extend(["", desc])
        lines.extend([
            "",
            f"Source: {source}",
            f"เวลา: {_format_news_time(item.get('published'))}",
            f"🔗 {item['link']}",
        ])
        return "\n".join(lines)
    except Exception as exc:
        print(f"[news] error: {exc}")
        return "❌ ดึงข่าวล่าสุดไม่ได้ในตอนนี้"


def _bitkub_ticker(symbol: str) -> dict:
    """Fetch a Bitkub public ticker with v3-first + legacy fallback.

    Bitkub's current public market docs expose v3 ticker data, while the
    legacy /api/market/ticker endpoint is deprecated. Responses may be
    wrapped as {"error": 0, "result": {...}} or returned as a direct
    {"THB_BTC": {...}} mapping, so accept both shapes.
    """
    symbol = symbol.upper().strip()
    if symbol not in SUPPORTED_TRADE_ASSETS:
        raise ValueError("รองรับเฉพาะเหรียญใน XSpring Exchange Simulator")

    pair = f"{symbol}_THB"
    endpoints = [
        # Current Bitkub v3 market ticker.
        f"https://api.bitkub.com/api/v3/market/ticker?sym={urllib.parse.quote(pair.lower())}",
        # Legacy public ticker kept as a compatibility fallback.
        f"https://api.bitkub.com/api/market/ticker?sym=THB_{urllib.parse.quote(symbol)}",
        f"https://api.bitkub.com/api/market/ticker",
    ]
    last_error = None

    for url in endpoints:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "XSpring-Dealer-Bot/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)

            # Current v3 shape: {error: 0, result: {...}}.
            if isinstance(data, dict) and isinstance(data.get("result"), dict):
                result = data["result"]
                # Some versions may return a pair map inside result.
                row = result.get(pair) or result.get(f"THB_{symbol}") or result.get(symbol)
                if isinstance(row, dict):
                    data = row
                elif "last" in result:
                    data = result

            # Legacy shape: {"THB_BTC": {...}} or {"BTC_THB": {...}}.
            if isinstance(data, dict) and "last" not in data:
                row = data.get(f"THB_{symbol}") or data.get(pair)
                if isinstance(row, dict):
                    data = row

            if not isinstance(data, dict) or "last" not in data:
                raise RuntimeError(f"Bitkub ticker response ไม่ถูกต้อง: {str(data)[:300]}")

            # Normalize numeric fields so downstream trade code is stable.
            out = dict(data)
            for key in ("last", "lowestAsk", "highestBid", "percentChange", "high24hr", "low24hr"):
                if key in out and out[key] not in (None, ""):
                    try:
                        out[key] = float(out[key])
                    except (TypeError, ValueError):
                        pass
            return out
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Bitkub ticker ใช้งานไม่ได้: {last_error}")


def _remote_trade_config(email: str) -> dict:
    cfg = _remote_config(email)
    # Remote config stores human UI percentages; convert to decimal where needed.
    return {
        "spread": float(cfg.get("spread", 0.5)) / 100.0,
        "premium": float(cfg.get("premium", 0.1)) / 100.0,
    }


def _sim_state(email: str) -> dict:
    res = (sb.table("sim_state").select("data").eq("actor", email).limit(1).execute())
    if res.data and isinstance(res.data[0].get("data"), dict):
        sim = dict(res.data[0]["data"])
    else:
        sim = {
            "asset": "BTC", "inv_coins": {}, "target_thb": 0.0,
            "fx_used_usd": 0.0, "cex_used_thb": 0.0, "pnl_thb": 0.0,
            "unhedged_thb": 0.0, "orders": [], "current_date": None,
            "customer_coins": {}, "customer_thb": 1_000_000.0, "open_orders": [],
        }
    sim.setdefault("customer_thb", 1_000_000.0)
    sim.setdefault("customer_coins", {})
    sim.setdefault("orders", [])
    sim.setdefault("open_orders", [])
    return sim


def _save_sim_state(email: str, sim: dict) -> None:
    sb.table("sim_state").upsert({
        "actor": email,
        "data": sim,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def _quote_for_trade(email: str, asset: str, side: str) -> tuple[float, dict]:
    ticker = _bitkub_ticker(asset)
    last = float(ticker["last"])
    ask = float(ticker.get("lowestAsk") or last)
    bid = float(ticker.get("highestBid") or last)
    rcfg = _remote_trade_config(email)
    base = ask if side == "buy" else bid
    # Keep the same dealer-spread concept as the Exchange tab, while using live Bitkub market data.
    quote = base * (1.0 + rcfg["premium"])
    quote = quote * (1.0 + rcfg["spread"] if side == "buy" else 1.0 - rcfg["spread"])
    return quote, ticker


def _parse_trade_arg(arg: str, side: str) -> tuple[str, float, str, Optional[float]]:
    parts = arg.strip().split()
    if len(parts) < 2:
        raise ValueError(
            "ใช้ /buy BTC 500000 [market] หรือ /buy BTC 500000 limit 2800000\n"
            "ขายใช้ /sell BTC 0.1 [market] หรือ /sell BTC 0.1 limit 2800000"
        )
    asset = parts[0].upper()
    amount = float(parts[1].replace(",", ""))
    if asset not in SUPPORTED_TRADE_ASSETS:
        raise ValueError(f"ไม่รองรับ {asset} ใน Exchange Simulator")
    if amount <= 0:
        raise ValueError("จำนวนต้องมากกว่า 0")
    typ = "market"
    limit_price = None
    if len(parts) >= 3:
        typ = parts[2].lower()
        if typ not in {"market", "limit"}:
            raise ValueError("ประเภทคำสั่งต้องเป็น market หรือ limit")
    if typ == "limit":
        if len(parts) < 4:
            raise ValueError("Limit ต้องระบุราคา เช่น /buy BTC 500000 limit 2800000")
        limit_price = float(parts[3].replace(",", ""))
        if limit_price <= 0:
            raise ValueError("Limit price ต้องมากกว่า 0")
    return asset, amount, typ, limit_price


def _audit_trade(email: str, chat_id: int, event: str, param: str, old, new, extra: Optional[dict] = None) -> None:
    try:
        sb.table("audit_log").insert({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session_id": f"tg-{chat_id}", "actor": email,
            "model_version": "telegram-exchange-v1", "config_sha256": None,
            "event": event, "param": param, "old_value": old, "new_value": new,
            "params": extra or {},
        }).execute()
    except Exception as exc:
        print(f"[trade audit] error: {exc}")


def cmd_trade_preview(chat_id: int, arg: str, side: str) -> str:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return err
    try:
        asset, amount, typ, limit_price = _parse_trade_arg(arg, side)
        quote, ticker = _quote_for_trade(email, asset, side)
        if side == "buy":
            amount_thb = amount
            coins = amount_thb * (1.0 - LOCAL_TRADE_FEE) / (limit_price if typ == "limit" else quote)
            available = float(_sim_state(email).get("customer_thb", 0.0))
            if amount_thb < MIN_TRADE_THB:
                raise ValueError(f"ขั้นต่ำ ฿{MIN_TRADE_THB:,.0f}")
            if amount_thb > available:
                raise ValueError(f"THB ในกระเป๋าไม่พอ (มี ฿{available:,.2f})")
            amount_label = f"฿{amount_thb:,.2f}"
            qty_label = f"{coins:,.8f} {asset}"
        else:
            coins = amount
            available = float((_sim_state(email).get("customer_coins") or {}).get(asset, 0.0))
            if coins > available:
                raise ValueError(f"{asset} ในกระเป๋าไม่พอ (มี {available:,.8f})")
            exec_price = limit_price if typ == "limit" else quote
            settlement = coins * exec_price * (1.0 - LOCAL_TRADE_FEE)
            amount_label = f"{coins:,.8f} {asset}"
            qty_label = f"฿{settlement:,.2f}"

        if typ == "limit":
            will_fill = (side == "buy" and limit_price >= float(ticker.get("lowestAsk") or quote)) or (side == "sell" and limit_price <= float(ticker.get("highestBid") or quote))
            fill_note = "มีโอกาสจับคู่ทันทีตามราคาในตลาด" if will_fill else "จะเก็บเป็น Open Order ใน Simulator"
        else:
            fill_note = "จะ execute ทันทีด้วยราคาตลาดล่าสุด"

        order_id = uuid.uuid4().hex[:10].upper()
        pending = {
            "id": order_id, "email": email, "chat_id": chat_id, "side": side,
            "asset": asset, "amount": amount, "type": typ, "limit_price": limit_price,
            "quote": quote, "ticker": ticker, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        PENDING_ORDERS[chat_id] = pending
        side_text = "BUY 🟢" if side == "buy" else "SELL 🔴"
        return (
            f"{'🟢' if side == 'buy' else '🔴'} ยืนยันคำสั่ง {side_text}\n\n"
            f"Order ID: {order_id}\nExchange: Bitkub\nPair: {asset}/THB\n"
            f"Type: {typ.upper()}\n"
            f"จำนวน: {amount_label}\n"
            f"ราคา: ฿{(limit_price if typ == 'limit' else quote):,.2f}\n"
            f"ประมาณได้รับ: {qty_label}\n"
            f"Fee: {LOCAL_TRADE_FEE * 100:.2f}%\n\n"
            f"{fill_note}\n\n"
            "⚠️ เป็น Exchange Simulator ของ XSpring Dealer Suite\n"
            "พิมพ์ /confirm เพื่อยืนยัน หรือ /cancel เพื่อยกเลิก"
        )
    except Exception as exc:
        print(f"[trade preview] error: {exc}")
        return f"❌ สร้างคำสั่งไม่ได้: {exc}"


def _execute_pending(chat_id: int) -> str:
    pending = PENDING_ORDERS.get(chat_id)
    if not pending:
        return "ไม่มีคำสั่งที่รอยืนยัน\nใช้ /buy หรือ /sell ก่อน"
    email = email_for_chat(chat_id)
    if email != pending.get("email"):
        PENDING_ORDERS.pop(chat_id, None)
        return "❌ บัญชี Telegram ไม่ตรงกับคำสั่งที่รอยืนยัน"
    try:
        sim = _sim_state(email)
        side = pending["side"]
        asset = pending["asset"]
        amount = float(pending["amount"])
        typ = pending["type"]
        limit_price = pending.get("limit_price")
        quote = float(pending["quote"])
        ticker = pending["ticker"] or {}
        market_ask = float(ticker.get("lowestAsk") or quote)
        market_bid = float(ticker.get("highestBid") or quote)

        if typ == "limit":
            crossed = (side == "buy" and limit_price >= market_ask) or (side == "sell" and limit_price <= market_bid)
            if not crossed:
                # Keep it as an open simulated order; reserve the customer balance.
                open_orders = sim.setdefault("open_orders", [])
                order = {
                    "id": pending["id"], "side": side, "asset": asset, "type": "limit",
                    "amount": amount, "limit_price": limit_price,
                    "created_at": pending["created_at"], "status": "open", "source": "telegram",
                }
                if side == "buy":
                    cash = float(sim.get("customer_thb", 0.0))
                    if amount > cash:
                        raise ValueError(f"THB ในกระเป๋าไม่พอ (มี ฿{cash:,.2f})")
                    sim["customer_thb"] = cash - amount
                    order["reserved_thb"] = amount
                else:
                    coins = float((sim.get("customer_coins") or {}).get(asset, 0.0))
                    if amount > coins:
                        raise ValueError(f"{asset} ในกระเป๋าไม่พอ")
                    sim["customer_coins"][asset] = coins - amount
                    order["reserved_coins"] = amount
                open_orders.append(order)
                _save_sim_state(email, sim)
                _audit_trade(email, chat_id, "telegram_sim_order_open", asset, None, order, {"order_id": pending["id"]})
                PENDING_ORDERS.pop(chat_id, None)
                return f"🟡 LIMIT ORDER เปิดแล้ว\nOrder ID: {pending['id']}\n{side.upper()} {amount:,.8f} {asset} @ ฿{limit_price:,.2f}\nStatus: OPEN\nใช้ /orders ดูรายการ"

        # Market order, or crossed limit: execute immediately.
        exec_price = (limit_price if typ == "limit" else quote)
        fee = 0.0
        customer_coins = sim.setdefault("customer_coins", {})
        cash_before = float(sim.get("customer_thb", 0.0))
        coins_before = float(customer_coins.get(asset, 0.0))
        if side == "buy":
            amount_thb = amount
            fee = amount_thb * LOCAL_TRADE_FEE
            settlement = amount_thb - fee
            received = settlement / exec_price
            if amount_thb < MIN_TRADE_THB:
                raise ValueError(f"ขั้นต่ำ ฿{MIN_TRADE_THB:,.0f}")
            if amount_thb > cash_before + 1e-9:
                raise ValueError(f"THB ในกระเป๋าไม่พอ (มี ฿{cash_before:,.2f})")
            sim["customer_thb"] = cash_before - amount_thb
            customer_coins[asset] = coins_before + received
            settlement_value = amount_thb
            qty = received
        else:
            qty = amount
            if qty <= 0 or qty > coins_before + 1e-12:
                raise ValueError(f"{asset} ในกระเป๋าไม่พอ (มี {coins_before:,.8f})")
            gross = qty * exec_price
            fee = gross * LOCAL_TRADE_FEE
            received_thb = gross - fee
            customer_coins[asset] = max(0.0, coins_before - qty)
            sim["customer_thb"] = cash_before + received_thb
            settlement_value = received_thb

        record = {
            "วันที่": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "เวลา": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ฝั่ง": "ซื้อ" if side == "buy" else "ขาย", "เหรียญ": asset,
            "มูลค่า (บาท)": amount if side == "buy" else settlement_value,
            "ราคาที่ลูกค้าได้": exec_price,
            "เหรียญที่ส่งมอบ": qty, "ค่าธรรมเนียม": fee,
            "ประเภท": typ.upper(), "Exchange": "Bitkub", "Source": "Telegram",
            "Order ID": pending["id"], "สถานะ": "Filled",
        }
        sim.setdefault("orders", []).append(record)
        sim["orders"] = sim["orders"][-500:]
        _save_sim_state(email, sim)
        _audit_trade(email, chat_id, "telegram_sim_order_filled", asset, None, record, {"order_id": pending["id"]})
        PENDING_ORDERS.pop(chat_id, None)
        return (
            f"✅ ORDER FILLED\nOrder ID: {pending['id']}\nExchange: Bitkub\n"
            f"{record['ฝั่ง']} {qty:,.8f} {asset}\nราคา: ฿{exec_price:,.2f}\n"
            f"Fee: ฿{fee:,.2f}\n\n"
            f"💰 THB คงเหลือ: ฿{sim['customer_thb']:,.2f}\n"
            f"🪙 {asset}: {customer_coins.get(asset, 0.0):,.8f}"
        )
    except Exception as exc:
        print(f"[trade execute] error: {exc}")
        return f"❌ Execute ไม่สำเร็จ: {exc}"


def cmd_cancel_trade(chat_id: int) -> str:
    if PENDING_ORDERS.pop(chat_id, None):
        return "✅ ยกเลิกคำสั่งที่รอยืนยันแล้ว"
    return "ไม่มีคำสั่งที่รอยืนยัน"


def cmd_orders(chat_id: int) -> str:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return err
    try:
        sim = _sim_state(email)
        orders = list(sim.get("orders") or [])[-5:][::-1]
        open_orders = list(sim.get("open_orders") or [])[-5:][::-1]
        lines = ["📋 Exchange Orders", "", "Filled ล่าสุด:"]
        if not orders:
            lines.append("- ไม่มี")
        for o in orders:
            lines.append(
                f"• {o.get('Order ID','-')} | {o.get('ฝั่ง','-')} {o.get('เหรียญ','-')} | "
                f"฿{float(o.get('มูลค่า (บาท)',0) or 0):,.2f} | {o.get('สถานะ','Filled')}"
            )
        lines.append("")
        lines.append("Open Limit:")
        if not open_orders:
            lines.append("- ไม่มี")
        for o in open_orders:
            lines.append(f"• {o.get('id','-')} | {o.get('side','-').upper()} {o.get('asset','-')} @ ฿{float(o.get('limit_price',0) or 0):,.2f}")
        return "\n".join(lines)
    except Exception as exc:
        print(f"[orders] error: {exc}")
        return "❌ อ่าน Orders ไม่สำเร็จ"


# =========================================================
# Help / command router
# =========================================================

HELP_TEXT = (
    "🤖 XSpring Dealer Suite Bot\n\n"
    "📊 NC / Liquidity\n"
    "/status — ภาพรวมระบบ / NC / Wallet\n"
    "/nc — เช็ค NC Buffer ล่าสุด\n"
    "/snapshot — ดู Snapshot ล่าสุดแบบละเอียด\n"
    "/history — ดู NC Snapshot ย้อนหลัง 5 รายการ\n"
    "/risk — ตรวจสถานะความเสี่ยง NC\n"
    "/config — ดูค่าพารามิเตอร์เว็บล่าสุด\n"
    "/set <param> <value> — แก้ค่าพารามิเตอร์เว็บ\n"
    "ตัวอย่าง: /set capital 100000000\n"
    "          /set spread 0.50\n\n"
    "💰 Portfolio\n"
    "/wallet — เช็คยอดเงิน/เหรียญในกระเป๋าจำลอง\n"
    "/portfolio — ดู Portfolio แบบสรุป\n\n"
    "📈 Market\n"
    "/price BTC — เช็คราคาเหรียญ\n"
    "/prices — ดู BTC/ETH/SOL หรือระบุเหรียญเอง\n"
    "/news — ข่าวคริปโทล่าสุด 1 ข่าว (เช่น /news BTC)\n\n"
    "🛒 Exchange Simulator\n"
    "/buy BTC 500000 — ซื้อ BTC ด้วย THB\n"
    "/sell BTC 0.1 — ขาย BTC\n"
    "/buy BTC 500000 limit 2800000 — Limit Buy\n"
    "/confirm — ยืนยันคำสั่ง\n"
    "/cancel — ยกเลิกคำสั่งรอยืนยัน\n"
    "/orders — ดู Orders ล่าสุด\n\n"
    "⚙️ Account\n"
    "/whoami — ดูบัญชีที่ Telegram เชื่อมอยู่\n"
    "/link อีเมล — เชื่อมบัญชี Telegram กับเว็บ\n"
    "/unlink — ยกเลิกการเชื่อมบัญชี Telegram\n"
    "/help — แสดงคำสั่งทั้งหมด"
)


def handle_command(chat_id: int, text: str) -> str:
    parts = text.strip().split(maxsplit=1)

    if not parts:
        return HELP_TEXT

    cmd = parts[0].split("@", 1)[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        return HELP_TEXT

    if cmd == "/link":
        return link_email(chat_id, arg) if arg else "ใช้แบบนี้: /link your@email.com"

    if cmd == "/unlink":
        return unlink_chat(chat_id)

    if cmd == "/whoami":
        return cmd_whoami(chat_id)

    if cmd == "/status":
        return cmd_status(chat_id)

    if cmd == "/nc":
        return cmd_nc(chat_id)

    if cmd == "/snapshot":
        return cmd_snapshot(chat_id)

    if cmd == "/history":
        return cmd_history(chat_id)

    if cmd == "/wallet":
        return cmd_wallet(chat_id)

    if cmd == "/portfolio":
        return cmd_portfolio(chat_id)

    if cmd == "/risk":
        return cmd_risk(chat_id)

    if cmd == "/config":
        return cmd_remote_config(chat_id)

    if cmd == "/set":
        return cmd_set_remote(chat_id, arg)

    # shortcut commands เช่น /setcapital 100000000
    shortcut = cmd.lstrip("/")
    if shortcut in REMOTE_ALIASES:
        return cmd_set_remote(chat_id, shortcut + (f" {arg}" if arg else ""))

    if cmd == "/price":
        return cmd_price(arg) if arg else "ใช้แบบนี้: /price BTC"

    if cmd == "/prices":
        return cmd_prices(arg)

    if cmd == "/news":
        return cmd_news(arg)

    if cmd == "/buy":
        return cmd_trade_preview(chat_id, arg, "buy")

    if cmd == "/sell":
        return cmd_trade_preview(chat_id, arg, "sell")

    if cmd == "/confirm":
        return _execute_pending(chat_id)

    if cmd == "/cancel":
        return cmd_cancel_trade(chat_id)

    if cmd == "/orders":
        return cmd_orders(chat_id)

    return "ไม่รู้จักคำสั่งนี้\nพิมพ์ /help เพื่อดูคำสั่งทั้งหมด"


# =========================================================
# Main polling loop
# =========================================================

def main_loop() -> None:
    validate_config()

    print("==========================================")
    print("XSpring Telegram Bot")
    print("Polling mode")
    print("==========================================")
    print("Bot เริ่มทำงานแล้ว...")
    set_bot_commands()

    offset = None

    while True:
        try:
            updates = get_updates(offset)

            for upd in updates:
                offset = upd["update_id"] + 1

                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = msg.get("text", "")

                if not chat_id or not text:
                    continue

                try:
                    reply = handle_command(int(chat_id), text)
                except Exception as exc:
                    print(f"[command] error: {exc}")
                    reply = "❌ เกิดข้อผิดพลาดภายใน Bot"

                try:
                    send_message(int(chat_id), reply)
                except Exception as exc:
                    print(f"[sendMessage] error: {exc}")

        except KeyboardInterrupt:
            print("\nหยุด XSpring Telegram Bot")
            break

        except Exception as exc:
            print(f"[polling] error: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main_loop()
