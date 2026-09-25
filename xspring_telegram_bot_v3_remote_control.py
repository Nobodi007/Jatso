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
import math
import os
import time
import atexit
import tempfile
import hashlib
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

BOT_BUILD = "2026-09-26-stable-v4-command-stable"

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
# Single-instance guard
# =========================================================
# ป้องกันเปิด Bot Token เดียวกันซ้อนกันบนเครื่องเดียวกัน
# ซึ่งเป็นสาเหตุหลักของอาการคำสั่งเดียวตอบกลับ 2 ครั้ง / ตัวเก่าตอบ
# "ไม่รู้จักคำสั่ง" พร้อมกับตัวใหม่ตอบถูกต้อง
_BOT_LOCK_PATH = os.path.join(
    tempfile.gettempdir(),
    "xspring_telegram_bot_" + hashlib.sha256(TELEGRAM_TOKEN.encode()).hexdigest()[:16] + ".lock",
)
_BOT_LOCK_HELD = False


def _pid_is_alive(pid: int) -> bool:
    try:
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False
    except Exception:
        return False


def _release_bot_lock() -> None:
    global _BOT_LOCK_HELD
    if not _BOT_LOCK_HELD:
        return
    try:
        if os.path.exists(_BOT_LOCK_PATH):
            os.remove(_BOT_LOCK_PATH)
    except Exception:
        pass
    _BOT_LOCK_HELD = False


def _acquire_bot_lock() -> None:
    global _BOT_LOCK_HELD
    payload = f"pid={os.getpid()}\ntime={time.time():.0f}\n"
    try:
        fd = os.open(_BOT_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        _BOT_LOCK_HELD = True
        atexit.register(_release_bot_lock)
        return
    except FileExistsError:
        pass
    except Exception as exc:
        print(f"[lock] cannot create lock: {exc}")
        return

    # ล็อกค้างจาก process ที่ตายแล้ว ให้เก็บกวาดได้อัตโนมัติ
    try:
        raw = open(_BOT_LOCK_PATH, "r", encoding="utf-8").read()
        old_pid = 0
        for line in raw.splitlines():
            if line.startswith("pid="):
                old_pid = int(line.split("=", 1)[1])
                break
        if old_pid and _pid_is_alive(old_pid):
            raise SystemExit(
                f"Bot Token นี้กำลังถูกรันอยู่แล้ว (PID {old_pid})\n"
                "กรุณาปิด Bot ตัวเก่าก่อน แล้วค่อยรันไฟล์นี้"
            )
        os.remove(_BOT_LOCK_PATH)
        _acquire_bot_lock()
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(f"ไม่สามารถตรวจ/สร้าง Bot lock ได้: {exc}")


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
    payload = {"timeout": 30, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset

    return tg_call("getUpdates", payload).get("result", [])


def set_bot_commands() -> None:
    """ตั้งเมนูคำสั่งที่ Telegram แสดงเมื่อผู้ใช้พิมพ์ /"""
    commands = [
        {"command": "version", "description": "ตรวจว่า Bot ตัวไหนกำลังรันอยู่"},
        {"command": "status", "description": "ภาพรวมระบบ / NC / Wallet"},
        {"command": "nc", "description": "เช็ค NC Buffer ล่าสุด"},
        {"command": "snapshot", "description": "ดู Snapshot ล่าสุดแบบละเอียด"},
        {"command": "history", "description": "ดู NC Snapshot ย้อนหลัง"},
        {"command": "wallet", "description": "ดูเงินและเหรียญในกระเป๋าจำลอง"},
        {"command": "portfolio", "description": "ดู Portfolio แบบสรุป"},
        {"command": "summary", "description": "สรุป Portfolio ทั้งพอร์ต"},
        {"command": "today", "description": "สรุปกิจกรรมวันนี้"},
        {"command": "risk", "description": "ตรวจความเสี่ยง Portfolio"},
        {"command": "config", "description": "ดูค่าพารามิเตอร์เว็บล่าสุด"},
        {"command": "set", "description": "แก้พารามิเตอร์เว็บ เช่น /set capital 100000000"},
        {"command": "price", "description": "เช็คราคา เช่น /price BTC"},
        {"command": "prices", "description": "ดูราคาหลายเหรียญ"},
        {"command": "alert", "description": "ตั้งแจ้งเตือนราคา เช่น /alert BTC above 3000000"},
        {"command": "alerts", "description": "ดูรายการแจ้งเตือนราคา"},
        {"command": "delalert", "description": "ลบแจ้งเตือน เช่น /delalert A1B2C3"},
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


def clear_webhook_keep_updates() -> None:
    """Ensure polling mode is active without deleting pending user messages."""
    try:
        tg_call("deleteWebhook", {"drop_pending_updates": False})
        print("[Telegram] webhook disabled; pending updates kept")
    except Exception as exc:
        print(f"[Telegram] deleteWebhook warning: {exc}")


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



# =========================================================
# Telegram Personal Assistant — Portfolio Summary / Today / Risk
# =========================================================

def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return default


def _th_now() -> datetime:
    try:
        return datetime.now(ZoneInfo("Asia/Bangkok"))
    except Exception:
        return datetime.now(timezone.utc)


def _parse_tx_time(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        # Legacy order dates may be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(text[:19], fmt)
                dt = dt.replace(tzinfo=timezone.utc)
                break
            except Exception:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        return dt.astimezone(ZoneInfo("Asia/Bangkok"))
    except Exception:
        return dt


def _portfolio_ledger_for_sim(sim: dict) -> list[dict]:
    ledger = sim.get("portfolio_ledger")
    if isinstance(ledger, list) and ledger:
        return [x for x in ledger if isinstance(x, dict)]

    # Fallback for accounts whose ledger has not yet been initialized.
    rows = []
    orders = sim.get("orders") if isinstance(sim.get("orders"), list) else []
    for i, rec in enumerate(orders):
        if not isinstance(rec, dict):
            continue
        side_raw = str(rec.get("ฝั่ง", rec.get("side", ""))).strip().upper()
        side = "BUY" if side_raw in {"BUY", "ซื้อ"} else "SELL"
        asset = str(rec.get("เหรียญ", rec.get("asset", sim.get("asset", ""))) or "").upper()
        qty = _to_float(rec.get("เหรียญที่ส่งมอบ", rec.get("qty", 0)))
        gross = _to_float(rec.get("มูลค่า (บาท)", rec.get("gross_thb", 0)))
        price = _to_float(rec.get("ราคาที่ลูกค้าได้", rec.get("price_thb", 0)))
        fee = _to_float(rec.get("ค่าธรรมเนียม", rec.get("fee_thb", 0)))
        if fee <= 0 and gross > 0:
            fee = gross * LOCAL_TRADE_FEE
        rows.append({
            "id": rec.get("Order ID", rec.get("id", f"LEGACY-{i+1}")),
            "timestamp": rec.get("timestamp", rec.get("วันที่")),
            "type": side,
            "asset": asset,
            "qty": qty if side == "BUY" else -qty,
            "price_thb": price,
            "gross_thb": gross,
            "fee_thb": fee,
            "cash_delta_thb": -gross if side == "BUY" else gross - fee,
            "realized_pnl_thb": _to_float(rec.get("realized_pnl_thb", 0)),
            "note": rec.get("note", ""),
        })
    return rows


def _portfolio_market_data(sim: dict, ledger: list[dict]) -> dict:
    """Build a read-only portfolio view from the same sim/ledger data used by web."""
    cash = _to_float(sim.get("customer_thb", 0))
    holdings = {}
    realized = 0.0
    fees = 0.0

    for tx in ledger:
        typ = str(tx.get("type", "")).upper()
        asset = str(tx.get("asset", "")).upper().strip()
        qty = _to_float(tx.get("qty", 0))
        gross = _to_float(tx.get("gross_thb", 0))
        fee = _to_float(tx.get("fee_thb", 0))
        fees += fee
        realized += _to_float(tx.get("realized_pnl_thb", 0))

        if typ in {"BUY", "SELL"} and asset:
            h = holdings.setdefault(asset, {"qty": 0.0, "cost": 0.0})
            if typ == "BUY":
                # Ledger gross is the cash amount; fee is tracked separately.
                h["qty"] += abs(qty)
                h["cost"] += gross + fee
            elif typ == "SELL":
                sell_qty = abs(qty)
                before_qty = h["qty"]
                avg_cost = h["cost"] / before_qty if before_qty > 0 else 0.0
                h["qty"] = max(0.0, before_qty - sell_qty)
                h["cost"] = max(0.0, h["cost"] - avg_cost * min(sell_qty, before_qty))

    # Prefer actual wallet coin balances when present; this protects against
    # legacy ledgers that predate the portfolio ledger.
    coins = sim.get("customer_coins")
    if isinstance(coins, dict):
        for asset, qty in coins.items():
            asset = str(asset).upper().strip()
            q = _to_float(qty)
            if asset and q > 0:
                holdings.setdefault(asset, {"qty": q, "cost": 0.0})["qty"] = q

    rows = []
    for asset, h in holdings.items():
        qty = max(0.0, _to_float(h.get("qty")))
        if qty <= 0:
            continue
        try:
            ticker = _bitkub_ticker(asset)
            price = _to_float(ticker.get("last"))
        except Exception as exc:
            print(f"[assistant price] {asset} unavailable: {exc}")
            price = 0.0
        cost = max(0.0, _to_float(h.get("cost")))
        value = qty * price
        unrealized = value - cost if cost > 0 else 0.0
        rows.append({
            "asset": asset,
            "qty": qty,
            "price": price,
            "value": value,
            "cost": cost,
            "unrealized": unrealized,
        })

    market_value = sum(r["value"] for r in rows)
    total_value = cash + market_value
    invested = sum(r["cost"] for r in rows)
    unrealized = sum(r["unrealized"] for r in rows)
    return {
        "cash": cash,
        "rows": rows,
        "market_value": market_value,
        "total_value": total_value,
        "invested": invested,
        "realized": realized,
        "unrealized": unrealized,
        "fees": fees,
    }


def _load_portfolio_for_chat(chat_id: int) -> tuple[Optional[str], Optional[dict], Optional[str]]:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return None, None, err
    try:
        sim = _sim_state(email)
        ledger = _portfolio_ledger_for_sim(sim)
        return email, {"sim": sim, "ledger": ledger, "portfolio": _portfolio_market_data(sim, ledger)}, None
    except Exception as exc:
        print(f"[assistant portfolio] error: {exc}")
        return email, None, "❌ อ่านข้อมูล Portfolio ไม่สำเร็จ"


def cmd_summary(chat_id: int) -> str:
    email, ctx, err = _load_portfolio_for_chat(chat_id)
    if err:
        return err
    p = ctx["portfolio"]
    rows = sorted(ctx["portfolio"]["rows"], key=lambda x: x["value"], reverse=True)

    lines = [
        "📊 Portfolio Summary",
        "",
        f"Portfolio Value\n฿{p['total_value']:,.2f}",
        f"\nCash\n฿{p['cash']:,.2f}",
        f"\nInvested\n฿{p['invested']:,.2f}",
        f"\nUnrealized P&L\n{p['unrealized']:+,.2f} บาท",
        f"\nRealized P&L\n{p['realized']:+,.2f} บาท",
    ]

    # Today is based on today's realized activity. If snapshots exist, use
    # today's first snapshot as an additional reference when available.
    today = _th_now().date()
    today_realized = 0.0
    today_fees = 0.0
    for tx in ctx["ledger"]:
        dt = _parse_tx_time(tx.get("timestamp"))
        if dt and dt.date() == today:
            today_realized += _to_float(tx.get("realized_pnl_thb", 0))
            today_fees += _to_float(tx.get("fee_thb", 0))
    lines.append(f"\nToday (realized)\n{today_realized:+,.2f} บาท")

    if rows:
        lines.extend(["", "Holdings"])
        for r in rows[:8]:
            lines.append(f"• {r['asset']} {r['qty']:,.8f} · ฿{r['value']:,.2f}")
    else:
        lines.extend(["", "Holdings\n• ไม่มีสินทรัพย์"])

    lines.extend(["", f"Fees (ledger)\n฿{p['fees']:,.2f}"])
    return "\n".join(lines)


def cmd_today(chat_id: int) -> str:
    email, ctx, err = _load_portfolio_for_chat(chat_id)
    if err:
        return err
    today = _th_now().date()
    txs = []
    for tx in ctx["ledger"]:
        dt = _parse_tx_time(tx.get("timestamp"))
        if dt and dt.date() == today:
            txs.append(tx)

    txs.sort(key=lambda x: _parse_tx_time(x.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    fees = sum(_to_float(x.get("fee_thb", 0)) for x in txs)
    net_flow = sum(_to_float(x.get("cash_delta_thb", 0)) for x in txs)

    lines = ["📅 Today's Activity", ""]
    if not txs:
        lines.append("วันนี้ยังไม่มีธุรกรรม")
    else:
        for tx in txs[:20]:
            typ = str(tx.get("type", "")).upper()
            asset = str(tx.get("asset", "")).upper()
            gross = _to_float(tx.get("gross_thb", 0))
            qty = abs(_to_float(tx.get("qty", 0)))
            if typ == "BUY":
                lines.append(f"BUY {asset}   ฿{gross:,.2f}")
            elif typ == "SELL":
                lines.append(f"SELL {asset}   ฿{gross:,.2f}")
            elif typ in {"DEPOSIT", "WITHDRAWAL", "WITHDRAW"}:
                sign = "+" if _to_float(tx.get("cash_delta_thb", 0)) >= 0 else "-"
                lines.append(f"{typ}   {sign}฿{abs(_to_float(tx.get('cash_delta_thb', 0))):,.2f}")
            elif typ == "FEE":
                lines.append(f"FEE   ฿{_to_float(tx.get('fee_thb', gross)):,.2f}")
            else:
                lines.append(f"{typ or 'TX'} {asset}   ฿{gross:,.2f}")

    lines.extend([
        "",
        f"Fees          ฿{fees:,.2f}",
        f"Net Flow      {net_flow:+,.2f} บาท",
    ])
    return "\n".join(lines)


def _portfolio_risk_metrics(ctx: dict) -> dict:
    p = ctx["portfolio"]
    total = p["total_value"]
    rows = p["rows"]
    cash_pct = (p["cash"] / total * 100.0) if total > 0 else 0.0
    largest = max(rows, key=lambda x: x["value"], default=None)
    largest_pct = (largest["value"] / total * 100.0) if largest and total > 0 else 0.0

    # Use stored portfolio snapshots when available. No synthetic risk series.
    snapshots = ctx["sim"].get("portfolio_snapshots", [])
    values = []
    if isinstance(snapshots, list):
        for s in snapshots:
            if isinstance(s, dict):
                v = _to_float(s.get("total_value_thb", s.get("portfolio_value_thb", 0)))
                if v > 0:
                    values.append(v)
    peak = max(values) if values else total
    drawdown = ((total / peak) - 1.0) * 100.0 if peak > 0 else 0.0

    # Volatility is reported only when enough stored snapshot values exist.
    volatility = None
    if len(values) >= 3:
        rets = []
        for a, b in zip(values, values[1:]):
            if a > 0:
                rets.append(b / a - 1.0)
        if len(rets) >= 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            volatility = math.sqrt(max(0.0, var)) * math.sqrt(365.0) * 100.0

    return {
        "assets": len(rows),
        "cash_pct": cash_pct,
        "largest": largest,
        "largest_pct": largest_pct,
        "drawdown": min(0.0, drawdown),
        "volatility": volatility,
    }


def cmd_portfolio_risk(chat_id: int) -> str:
    email, ctx, err = _load_portfolio_for_chat(chat_id)
    if err:
        return err
    r = _portfolio_risk_metrics(ctx)
    largest = r["largest"]
    largest_text = f"{largest['asset']} {r['largest_pct']:.1f}%" if largest else "-"
    vol_text = f"{r['volatility']:.1f}%" if r["volatility"] is not None else "N/A"

    if r["drawdown"] <= -10 or r["cash_pct"] < 10:
        status = "⚠️ ต้องติดตาม"
    else:
        status = "🟢 ข้อมูลปกติ"

    return (
        "🛡 Portfolio Risk\n\n"
        f"Assets       {r['assets']}\n"
        f"Cash         {r['cash_pct']:.1f}%\n"
        f"Largest      {largest_text}\n"
        f"Drawdown     {r['drawdown']:.1f}%\n"
        f"Volatility   {vol_text}\n\n"
        f"สถานะ: {status}"
    )


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
# Telegram Price Alerts
# =========================================================

def _price_alerts_for_email(email: str, sim: Optional[dict] = None) -> tuple[dict, list[dict]]:
    if sim is None:
        sim = _sim_state(email)
    alerts = sim.setdefault("price_alerts", [])
    if not isinstance(alerts, list):
        alerts = []
        sim["price_alerts"] = alerts
    return sim, alerts


def _format_thb_price(price: float) -> str:
    return f"฿{float(price):,.2f}"


def cmd_price_alert(chat_id: int, arg: str) -> str:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return err

    parts = arg.strip().split()
    if len(parts) < 3:
        return (
            "ใช้แบบนี้:\n"
            "/alert BTC above 3000000\n"
            "/alert XRP below 50\n\n"
            "เงื่อนไข: above / below\n"
            "ราคาอ้างอิงเป็น Bitkub THB"
        )

    asset = parts[0].upper()
    condition = parts[1].lower()
    if condition in {">", ">=", "สูงกว่า", "เหนือ"}:
        condition = "above"
    elif condition in {"<", "<=", "ต่ำกว่า", "ใต้"}:
        condition = "below"
    if condition not in {"above", "below"}:
        return "❌ เงื่อนไขต้องเป็น above หรือ below เช่น /alert BTC above 3000000"

    try:
        target = float(parts[2].replace(",", ""))
    except (TypeError, ValueError):
        return "❌ ราคาไม่ถูกต้อง เช่น /alert BTC above 3000000"
    if target <= 0:
        return "❌ ราคาเป้าหมายต้องมากกว่า 0"
    if asset not in SUPPORTED_TRADE_ASSETS:
        return f"❌ ไม่รองรับ {asset} ใน Exchange Simulator"

    # Verify the market is reachable and capture the current price.
    try:
        ticker = _bitkub_ticker(asset)
        current = float(ticker["last"])
    except Exception as exc:
        print(f"[alert] ticker error: {exc}")
        return f"❌ ดึงราคา {asset}/THB ไม่ได้ตอนนี้"

    sim, alerts = _price_alerts_for_email(email)
    active = [a for a in alerts if a.get("active", True)]
    if len(active) >= 20:
        return "❌ ตั้งแจ้งเตือนได้สูงสุด 20 รายการที่ยังทำงานอยู่"

    alert_id = uuid.uuid4().hex[:6].upper()
    alert = {
        "id": alert_id,
        "chat_id": int(chat_id),
        "asset": asset,
        "condition": condition,
        "target": float(target),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_price": current,
        "active": True,
        "triggered_at": None,
    }
    alerts.append(alert)
    sim["price_alerts"] = alerts[-100:]
    _save_sim_state(email, sim)

    cond_text = "แตะ/สูงกว่า" if condition == "above" else "แตะ/ต่ำกว่า"
    return (
        f"🔔 ตั้งแจ้งเตือนราคาแล้ว\n"
        f"ID: {alert_id}\n"
        f"{asset}/THB: {cond_text} {_format_thb_price(target)}\n"
        f"ราคาปัจจุบัน: {_format_thb_price(current)}\n"
        "ระบบจะตรวจราคาอัตโนมัติและส่ง Telegram เมื่อถึงเงื่อนไข"
    )


def cmd_price_alerts(chat_id: int) -> str:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return err
    try:
        sim, alerts = _price_alerts_for_email(email)
        mine = [a for a in alerts if int(a.get("chat_id") or 0) == int(chat_id)]
        if not mine:
            return "🔔 ยังไม่มี Price Alert\nใช้ /alert BTC above 3000000 เพื่อสร้างรายการแรก"
        lines = ["🔔 Price Alerts", ""]
        for a in reversed(mine[-20:]):
            status = "🟢 ACTIVE" if a.get("active", True) else "⚪ TRIGGERED"
            op = ">=" if a.get("condition") == "above" else "<="
            lines.append(
                f"{a.get('id','-')} | {status}\n"
                f"{a.get('asset','-')}/THB {op} {_format_thb_price(float(a.get('target') or 0))}"
            )
        return "\n".join(lines)
    except Exception as exc:
        print(f"[alerts] list error: {exc}")
        return "❌ อ่านรายการ Price Alert ไม่สำเร็จ"


def cmd_delete_price_alert(chat_id: int, arg: str) -> str:
    email, err = _linked_email_or_message(chat_id)
    if err:
        return err
    alert_id = arg.strip().upper()
    if not alert_id:
        return "ใช้แบบนี้: /delalert A1B2C3"
    try:
        sim, alerts = _price_alerts_for_email(email)
        found = False
        for a in alerts:
            if str(a.get("id", "")).upper() == alert_id and int(a.get("chat_id") or 0) == int(chat_id):
                a["active"] = False
                a["deleted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                found = True
                break
        if not found:
            return f"❌ ไม่พบ Alert ID {alert_id}"
        sim["price_alerts"] = alerts
        _save_sim_state(email, sim)
        return f"✅ ลบ Price Alert {alert_id} แล้ว"
    except Exception as exc:
        print(f"[delalert] error: {exc}")
        return "❌ ลบ Price Alert ไม่สำเร็จ"


def check_price_alerts() -> None:
    """ตรวจ Price Alerts แบบประหยัด API และไม่เขียน sim_state ทุกครั้งที่ราคาเปลี่ยน.

    - cache ticker ต่อ asset ภายในรอบเดียว
    - บันทึกลง Supabase เฉพาะตอน trigger/invalid
    - ถ้า Telegram ส่งไม่สำเร็จ จะยังคง ACTIVE เพื่อไม่ทำ Alert หาย
    """
    if sb is None:
        return
    try:
        res = sb.table("sim_state").select("actor,data").limit(500).execute()
        rows = res.data or []
    except Exception as exc:
        print(f"[alert] load sim_state error: {exc}")
        return

    ticker_cache: dict[str, float] = {}
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for row in rows:
        email = str(row.get("actor") or "").strip()
        sim = row.get("data")
        if not email or not isinstance(sim, dict):
            continue
        alerts = sim.get("price_alerts")
        if not isinstance(alerts, list):
            continue

        changed = False
        for alert in alerts:
            if not alert.get("active", True):
                continue
            chat_id = alert.get("chat_id")
            asset = str(alert.get("asset") or "").upper().strip()
            condition = str(alert.get("condition") or "").lower().strip()
            try:
                target = float(alert.get("target"))
                previous = float(alert.get("last_price")) if alert.get("last_price") is not None else None
                chat_id = int(chat_id)
                if not asset or condition not in {"above", "below"} or target <= 0 or chat_id <= 0:
                    alert["active"] = False
                    changed = True
                    continue
            except (TypeError, ValueError):
                alert["active"] = False
                changed = True
                continue

            try:
                if asset not in ticker_cache:
                    ticker_cache[asset] = float(_bitkub_ticker(asset)["last"])
                current = ticker_cache[asset]
            except Exception as exc:
                print(f"[alert] {asset} ticker error: {exc}")
                continue

            crossed = (
                current >= target and (previous is None or previous < target)
                if condition == "above"
                else current <= target and (previous is None or previous > target)
            )

            # อัปเดต last_price ใน memory เพื่อใช้ตรวจ crossing รอบถัดไป
            # แต่ไม่ save ลง DB ทุก polling cycle
            alert["last_price"] = current

            if crossed:
                direction = "ขึ้นถึง" if condition == "above" else "ลงถึง"
                msg = (
                    "🚨 PRICE ALERT\n"
                    f"{asset}/THB {direction} {_format_thb_price(target)}\n"
                    f"ราคาปัจจุบัน: {_format_thb_price(current)}\n"
                    f"Alert ID: {alert.get('id','-')}\n"
                    "สถานะ: Triggered (หยุดแจ้งซ้ำแล้ว)"
                )
                try:
                    send_message(chat_id, msg)
                    alert["active"] = False
                    alert["triggered_at"] = now_iso
                    changed = True
                except Exception as exc:
                    # อย่าปิด Alert หาก Telegram ล้มเหลว
                    print(f"[alert] send error for {chat_id}: {exc}")

        if changed:
            try:
                sim["price_alerts"] = alerts[-100:]
                _save_sim_state(email, sim)
            except Exception as exc:
                print(f"[alert] save error for {email}: {exc}")


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



def _trade_model_config(email: str, sim: dict) -> dict:
    """โหลด model context ให้ Telegram ledger ใช้ schema/logic เดียวกับ Exchange UI."""
    cfg = {}
    try:
        row = (
            sb.table("nc_snapshots")
            .select("config,required_stock_thb")
            .eq("actor", email)
            .order("snapshot_at", desc=True)
            .limit(1)
            .execute()
        )
        if row.data:
            raw_cfg = row.data[0].get("config")
            if isinstance(raw_cfg, dict):
                cfg.update(raw_cfg)
            if not sim.get("target_thb"):
                try:
                    sim["target_thb"] = float(row.data[0].get("required_stock_thb") or 0.0)
                except (TypeError, ValueError):
                    pass
    except Exception as exc:
        print(f"[trade model] snapshot config unavailable: {exc}")

    remote = _remote_config(email)
    # dealer_remote_config stores human UI units; convert them to web-model units.
    cfg.update({
        "dealer_spread": float(remote.get("spread", 0.5)) / 100.0,
        "local_premium": float(remote.get("premium", 0.1)) / 100.0,
        "hedge_fee_taker": float(remote.get("hedge_taker", 0.10)) / 100.0,
        "hedge_fee_maker": float(remote.get("hedge_maker", 0.10)) / 100.0,
        "maker_ratio": float(remote.get("maker_ratio", 0.0)) / 100.0,
        "fx_limit_max": float(remote.get("fx_limit", 5_000_000.0)),
        "slippage_sensitivity": float(remote.get("slippage", 10.0)) / 100.0,
        "market_depth_usd": float(remote.get("depth", 0.0)),
        "impact_penalty": float(remote.get("impact_penalty", 0.5)) / 100.0,
        "monthly_volume_thb": float(remote.get("monthly_volume", 80_000_000.0)),
        "net_bias_pct": float(remote.get("net_bias", 15.0)) / 100.0,
        "flow_cv_pct": float(remote.get("flow_cv", 50.0)) / 100.0,
        "settlement_days": int(remote.get("lag", 1)),
        "confidence": float(remote.get("confidence", 99)),
        "total_capital_thb": float(remote.get("capital", 150_000_000.0)),
        "cex_margin_thb": float(remote.get("margin", 30_000_000.0)),
        "liab_thb": float(remote.get("liab", 100_000_000.0)),
        "cex_counterparty_haircut": float(remote.get("cp_haircut", 2.0)) / 100.0,
        "trading_risk_rate": float(remote.get("trading_risk", 2.0)) / 100.0,
        "hot_wallet_pct": float(remote.get("hot_wallet", 30.0)) / 100.0,
        "cold_domestic_split_pct": float(remote.get("cold_domestic", 80.0)) / 100.0,
        "cold_foreign_rate": float(remote.get("cold_foreign", 1.5)) / 100.0,
        "include_trading_fee_revenue": bool(cfg.get("include_trading_fee_revenue", True)),
        "withdrawal_fee_markup_pct": float(cfg.get("withdrawal_fee_markup_pct", 0.0) or 0.0),
        "ktb_fx_spread_bps": float(cfg.get("ktb_fx_spread_bps", 0.0) or 0.0),
        "fixed_min_nc": float(cfg.get("fixed_min_nc", 0.0) or 0.0),
        "h_crypto": float(cfg.get("h_crypto", 0.0) or 0.0),
        "h_cex": float(cfg.get("h_cex", float(remote.get("cp_haircut", 2.0)) / 100.0)),
        "custody_rate_blended": float(cfg.get("custody_rate_blended", 0.0) or 0.0),
        "hot_wallet_cap_breach": bool(cfg.get("hot_wallet_cap_breach", False)),
    })

    # Keep the blended hedge fee exactly aligned with the web model.
    maker_ratio = min(max(float(cfg["maker_ratio"]), 0.0), 1.0)
    cfg["hedge_fee"] = (
        cfg["hedge_fee_taker"] * (1.0 - maker_ratio)
        + cfg["hedge_fee_maker"] * maker_ratio
    )
    cfg["daily_volume_thb"] = cfg["monthly_volume_thb"] / 30.0

    # Fallback target stock only when sim_state has never been initialized by web.
    if float(sim.get("target_thb", 0.0) or 0.0) <= 0:
        z_map = {90.0: 1.2816, 95.0: 1.6449, 99.0: 2.3263, 99.9: 3.0902}
        z = z_map.get(float(cfg["confidence"]), 2.3263)
        factor = (
            max(0.0, cfg["net_bias_pct"]) * cfg["settlement_days"]
            + z * cfg["flow_cv_pct"] * math.sqrt(max(cfg["settlement_days"], 1))
        ) / 30.0
        sim["target_thb"] = factor * cfg["monthly_volume_thb"]

    return cfg


def _global_trade_reference(asset: str, local_ticker: dict) -> tuple[float, float, str]:
    """คืน global USD, USD/THB proxy และ source โดยใช้ Binance + Bitkub USDT/THB."""
    try:
        d, source, _close = _binance_spot_ticker_24h(asset)
        spot_usd = float(d["lastPrice"])
    except Exception:
        # ถ้า Binance ใช้งานไม่ได้ ให้ย้อนคำนวณจาก local quote ได้
        spot_usd = 0.0

    try:
        usdt_ticker = _bitkub_ticker("USDT")
        usdthb = float(usdt_ticker.get("last") or 0.0)
    except Exception:
        usdthb = 0.0

    if usdthb <= 0:
        usdthb = 35.0

    if spot_usd <= 0:
        # local_ticker.last is THB/coin; use it as a last-resort global proxy.
        spot_usd = float(local_ticker.get("last") or 0.0) / usdthb

    return spot_usd, usdthb, "Binance Spot + Bitkub USDT/THB"


def _enrich_trade_ledger_record(
    email: str,
    sim: dict,
    side: str,
    asset: str,
    amount_thb: float,
    exec_price: float,
    qty: float,
    fee: float,
    ticker: dict,
    order_id: str,
    order_type: str,
) -> dict:
    """ทำ ledger record ให้ตรงกับ execute_order() ของ Exchange UI มากที่สุด."""
    cfg = _trade_model_config(email, sim)
    spot_usd, usdthb, global_source = _global_trade_reference(asset, ticker)
    coin_price_global = spot_usd * usdthb

    if coin_price_global <= 0:
        coin_price_global = exec_price / max(
            1e-12,
            (1.0 + cfg["local_premium"])
            * (1.0 + cfg["dealer_spread"] if side == "buy" else 1.0 - cfg["dealer_spread"])
        )

    inv = sim.setdefault("inv_coins", {})
    target_thb = float(sim.get("target_thb", 0.0) or 0.0)
    target_coins = target_thb / coin_price_global if coin_price_global > 0 else 0.0
    inv_before = float(inv.get(asset, target_coins) or 0.0)
    inv.setdefault(asset, inv_before)

    month_str = datetime.now(timezone.utc).strftime("%Y-%m")
    fx_by_month = sim.setdefault("fx_used_usd_by_month", {})
    month_used = float(fx_by_month.get(month_str, 0.0) or 0.0)

    # Same inventory/hedge flow as the web Exchange Simulator.
    if side == "buy":
        inv_after_customer = inv_before - qty
        hedge_required = max(0.0, target_coins - inv_after_customer)
        fx_left = max(0.0, cfg["fx_limit_max"] - month_used)
        max_hedge = (
            fx_left / (spot_usd * (1.0 + cfg["hedge_fee"]))
            if spot_usd > 0 else 0.0
        )
        hedged_coins = min(hedge_required, max_hedge)
        residual_unhedged = max(0.0, hedge_required - hedged_coins)
        hedge_thb = hedged_coins * coin_price_global
        hedge_usd = hedged_coins * spot_usd * (1.0 + cfg["hedge_fee"])
        cex_used_this = 0.0
        inv_after = inv_after_customer + hedged_coins

        fx_by_month[month_str] = month_used + hedge_usd
        sim["fx_used_usd"] = float(sim.get("fx_used_usd", 0.0) or 0.0) + hedge_usd
    else:
        inv_after_customer = inv_before + qty
        hedge_required = max(0.0, inv_after_customer - target_coins)
        cex_before = float(sim.get("cex_used_thb", 0.0) or 0.0)
        cex_limit = float(cfg["cex_margin_thb"])
        cex_left = max(0.0, cex_limit - cex_before)
        max_hedge = cex_left / coin_price_global if coin_price_global > 0 else 0.0
        hedged_coins = min(hedge_required, max_hedge)
        residual_unhedged = max(0.0, hedge_required - hedged_coins)
        hedge_thb = hedged_coins * coin_price_global
        hedge_usd = hedged_coins * spot_usd * (1.0 + cfg["hedge_fee"])
        cex_used_this = hedge_thb
        inv_after = max(0.0, inv_after_customer - hedged_coins)
        sim["cex_used_thb"] = cex_before + cex_used_this

    inv[asset] = inv_after
    unhedged_thb_this = residual_unhedged * coin_price_global
    sim["unhedged_thb"] = float(sim.get("unhedged_thb", 0.0) or 0.0) + unhedged_thb_this

    # Dealer P&L — same structure as the web order model.
    if side == "buy":
        market_edge = qty * (exec_price - coin_price_global)
    else:
        market_edge = qty * (coin_price_global - exec_price)

    fee_rev = fee if cfg["include_trading_fee_revenue"] else 0.0
    ktb_fx_benefit = hedge_thb * (cfg["ktb_fx_spread_bps"] / 10000.0)

    daily_vol = abs(float(ticker.get("percentChange") or 0.0)) / 100.0
    depth_usd = float(cfg["market_depth_usd"])
    impact_pen = float(cfg["impact_penalty"])
    hedge_order_usd = hedged_coins * spot_usd
    hedge_part = (
        hedge_order_usd / depth_usd
        if depth_usd > 0 and hedge_order_usd > 0 else 0.0
    )
    impact_cost = (
        hedge_thb * hedge_part * impact_pen
        if hedge_thb > 0 and depth_usd > 0 and impact_pen > 0 else 0.0
    )
    slippage_cost = (
        hedge_thb * daily_vol * cfg["slippage_sensitivity"] + impact_cost
        if hedged_coins > 0 else 0.0
    )
    hedge_fee_cost = hedge_thb * cfg["hedge_fee"]

    revenue = market_edge + fee_rev + ktb_fx_benefit
    cost = hedge_fee_cost + slippage_cost
    net = revenue - cost
    sim["pnl_thb"] = float(sim.get("pnl_thb", 0.0) or 0.0) + net

    # NC after the hedge, using the same nc_snapshot formula/inputs saved by web.
    stock_thb = max(0.0, inv_after) * coin_price_global
    h_crypto = float(cfg["h_crypto"])
    h_cex = float(cfg["h_cex"])
    custody_rate = float(cfg["custody_rate_blended"])
    capital = float(cfg["total_capital_thb"])
    cex_margin = float(cfg["cex_margin_thb"])
    liab = float(cfg["liab_thb"])
    trading_nc = float(cfg["trading_risk_rate"]) * float(cfg["daily_volume_thb"])
    custody_nc = stock_thb * custody_rate
    nc_actual = (
        capital - stock_thb
        + stock_thb * (1.0 - h_crypto)
        + cex_margin * (1.0 - h_cex)
        - liab
    )
    nc_required = float(cfg["fixed_min_nc"]) + trading_nc + custody_nc
    nc_buffer = nc_actual - nc_required

    if nc_buffer < 0:
        nc_status = "NC ไม่พอ"
    elif nc_buffer < 0.5 * nc_required or cfg["hot_wallet_cap_breach"]:
        nc_status = "เฝ้าระวัง"
    else:
        nc_status = "ผ่าน"

    record = {
        "วันที่": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "เวลา": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ฝั่ง": "ซื้อ" if side == "buy" else "ขาย",
        "เหรียญ": asset,
        "มูลค่า (บาท)": amount_thb,
        "ราคาที่ลูกค้าได้": exec_price,
        "เหรียญที่ส่งมอบ": qty,
        "Hedge (เหรียญ)": hedged_coins,
        "Hedge (USD)": hedge_usd,
        "CEX Liquidity ใช้ (บาท)": cex_used_this,
        "Unhedged (บาท)": unhedged_thb_this,
        "Market Edge": market_edge,
        "รายได้": revenue,
        "ต้นทุน": cost,
        "กำไรออเดอร์": net,
        "สต็อกคงเหลือ": inv_after,
        "FX ใช้สะสม (USD)": month_used + hedge_usd if side == "buy" else month_used,
        "CEX Liquidity ใช้สะสม (บาท)": float(sim.get("cex_used_thb", 0.0) or 0.0),
        "NC Buffer": nc_buffer,
        "ผลด่าน": nc_status if residual_unhedged <= 1e-12 and nc_buffer >= 0 else (
            "NC ไม่พอ" if nc_buffer < 0 else "เฝ้าระวัง"
        ),
        "ค่าธรรมเนียม": fee,
        "ประเภท": order_type.upper(),
        "Exchange": "Bitkub",
        "Source": "Telegram",
        "Order ID": order_id,
        "สถานะ": "Filled",
        "Global Reference (THB)": coin_price_global,
        "Global Source": global_source,
        "NC Actual": nc_actual,
        "NC Required": nc_required,
    }
    return record

def _parse_trade_arg(arg: str, side: str) -> tuple[str, float, str, Optional[float]]:
    parts = arg.strip().split()
    if len(parts) < 2:
        raise ValueError(
            "ใช้ /buy BTC 500000 market หรือ /buy BTC 500000 limit 2800000\n"
            "ขายใช้ /sell BTC 0.1 market หรือ /sell BTC 0.1 limit 2800000"
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
            crossed = (
                (side == "buy" and limit_price >= market_ask)
                or (side == "sell" and limit_price <= market_bid)
            )
            if not crossed:
                # ใช้ schema เดียวกับ Exchange UI Simulator
                # และไม่ reserve เงิน/เหรียญ เพราะ web simulator ก็ตรวจยอดตอน match
                open_orders = sim.setdefault("open_orders", [])
                order = {
                    "id": pending["id"],
                    "side": side,
                    "asset": asset,
                    "amount_thb": amount if side == "buy" else 0.0,
                    "qty": amount if side == "sell" else 0.0,
                    "px": limit_price,
                    "type": "limit",
                    "source": "telegram",
                    "created_at": pending["created_at"],
                    "status": "open",
                }
                open_orders.append(order)
                _save_sim_state(email, sim)
                _audit_trade(
                    email, chat_id, "telegram_sim_order_open",
                    asset, None, order, {"order_id": pending["id"]},
                )
                PENDING_ORDERS.pop(chat_id, None)
                return (
                    f"🟡 LIMIT ORDER เปิดแล้ว\n"
                    f"Order ID: {pending['id']}\n"
                    f"{side.upper()} {amount:,.8f} {asset} @ ฿{limit_price:,.2f}\n"
                    "Status: OPEN\n"
                    "ใช้ /orders ดูรายการ"
                )

        # Market order หรือ crossed limit
        exec_price = limit_price if typ == "limit" else quote
        customer_coins = sim.setdefault("customer_coins", {})
        cash_before = float(sim.get("customer_thb", 0.0) or 0.0)
        coins_before = float(customer_coins.get(asset, 0.0) or 0.0)

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
            amount_thb = gross

        record = _enrich_trade_ledger_record(
            email=email,
            sim=sim,
            side=side,
            asset=asset,
            amount_thb=amount_thb,
            exec_price=exec_price,
            qty=qty,
            fee=fee,
            ticker=ticker,
            order_id=pending["id"],
            order_type=typ,
        )

        sim.setdefault("orders", []).append(record)
        sim["orders"] = sim["orders"][-500:]
        _save_sim_state(email, sim)
        _audit_trade(
            email, chat_id, "telegram_sim_order_filled",
            asset, None, record, {"order_id": pending["id"]},
        )
        PENDING_ORDERS.pop(chat_id, None)

        return (
            f"✅ ORDER FILLED\n"
            f"Order ID: {pending['id']}\n"
            "Exchange: Bitkub\n"
            f"{record['ฝั่ง']} {qty:,.8f} {asset}\n"
            f"ราคา: ฿{exec_price:,.2f}\n"
            f"Fee: ฿{fee:,.2f}\n"
            f"Dealer P&L: ฿{float(record['กำไรออเดอร์']):+,.2f}\n"
            f"NC Buffer: ฿{float(record['NC Buffer']):+,.2f}\n\n"
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
    "🧩 Version: " + BOT_BUILD + "\n\n"
    "🤖 XSpring Dealer Suite Bot\n\n"
    "📊 NC / Liquidity\n"
    "/status — ภาพรวมระบบ / NC / Wallet\n"
    "/nc — เช็ค NC Buffer ล่าสุด\n"
    "/snapshot — ดู Snapshot ล่าสุดแบบละเอียด\n"
    "/history — ดู NC Snapshot ย้อนหลัง 5 รายการ\n"
    "/risk — ตรวจความเสี่ยง Portfolio\n"
    "/config — ดูค่าพารามิเตอร์เว็บล่าสุด\n"
    "/set <param> <value> — แก้ค่าพารามิเตอร์เว็บ\n"
    "ตัวอย่าง: /set capital 100000000\n"
    "          /set spread 0.50\n\n"
    "💰 Portfolio\n"
    "/wallet — เช็คยอดเงิน/เหรียญในกระเป๋าจำลอง\n"
    "/portfolio — ดู Portfolio แบบสรุป\n"
    "/summary — สรุป Portfolio ทั้งพอร์ต\n"
    "/today — สรุปกิจกรรมวันนี้\n\n"
    "📈 Market\n"
    "/price BTC — เช็คราคาเหรียญ\n"
    "/prices — ดู BTC/ETH/SOL หรือระบุเหรียญเอง\n"
    "/alert BTC above 3000000 — แจ้งเมื่อราคาถึงเป้าหมาย\n"
    "/alert XRP below 50 — แจ้งเมื่อราคาลงถึงเป้าหมาย\n"
    "/alerts — ดู Price Alert ที่ตั้งไว้\n"
    "/delalert A1B2C3 — ลบ Price Alert\n"
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

    # Telegram may deliver /command@BotName in groups.
    # Normalize harmless punctuation/case so the same command is always routed
    # to one handler instead of falling through to the old "unknown command" reply.
    cmd = parts[0].split("@", 1)[0].strip().lower()
    cmd = cmd.rstrip(".,!?;:，。！？")
    arg = parts[1].strip() if len(parts) > 1 else ""

    # Backward-compatible aliases for commands users may already have typed.
    aliases = {
        "/alerts": "/alerts",
        "/pricealerts": "/alerts",
        "/price-alerts": "/alerts",
        "/pricealert": "/alert",
        "/del-alert": "/delalert",
        "/deletealert": "/delalert",
    }
    cmd = aliases.get(cmd, cmd)

    if cmd in ("/start", "/help"):
        return HELP_TEXT

    if cmd == "/version":
        return f"🧩 Bot Build: {BOT_BUILD}\nPrice Alert: /alert /alerts /delalert\nPersonal: /summary /today /risk"

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

    if cmd == "/summary":
        return cmd_summary(chat_id)

    if cmd == "/today":
        return cmd_today(chat_id)

    if cmd == "/risk":
        return cmd_portfolio_risk(chat_id)

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

    if cmd == "/alert":
        return cmd_price_alert(chat_id, arg)

    if cmd == "/alerts":
        return cmd_price_alerts(chat_id)

    if cmd == "/delalert":
        return cmd_delete_price_alert(chat_id, arg)

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

    return (
        "❌ ไม่รู้จักคำสั่งนี้\n\n"
        "คำสั่งที่ใช้ได้ เช่น\n"
        "• /alert BTC above 3000000\n"
        "• /alerts\n"
        "• /price BTC\n"
        "• /prices\n"
        "• /summary\n"
        "• /today\n"
        "• /risk\n\n"
        "พิมพ์ /help เพื่อดูทั้งหมด"
    )


# =========================================================
# Main polling loop
# =========================================================

# กันการส่งคำตอบซ้ำจาก update เดิมภายใน process เดียว
# และช่วยกรองกรณี Telegram/network retry ที่ทำให้คำสั่งเดียวถูกประมวลผลซ้ำ
_LAST_HANDLED_UPDATES: dict[int, float] = {}
_LAST_SENT_RESPONSES: dict[tuple[int, str], float] = {}

def _should_send_response(chat_id: int, text: str, now: float, window: float = 3.0) -> bool:
    key = (int(chat_id), str(text).strip())
    previous = _LAST_SENT_RESPONSES.get(key)
    if previous is not None and (now - previous) < window:
        print(f"[dedup] skip duplicate response for chat={chat_id}")
        return False
    _LAST_SENT_RESPONSES[key] = now
    # cleanup
    if len(_LAST_SENT_RESPONSES) > 500:
        cutoff = now - 60.0
        for k, ts in list(_LAST_SENT_RESPONSES.items()):
            if ts < cutoff:
                _LAST_SENT_RESPONSES.pop(k, None)
    return True

def main_loop() -> None:
    validate_config()
    _acquire_bot_lock()

    print("==========================================")
    print("XSpring Telegram Bot")
    print("Stable polling mode")
    print(f"Build: {BOT_BUILD}")
    print("==========================================")
    print("Bot เริ่มทำงานแล้ว...")
    clear_webhook_keep_updates()
    set_bot_commands()

    offset = None
    next_alert_check = 0.0
    seen_updates: set[int] = set()
    ALERT_INTERVAL = 30.0

    while True:
        try:
            now = time.monotonic()
            if now >= next_alert_check:
                check_price_alerts()
                next_alert_check = time.monotonic() + ALERT_INTERVAL

            updates = get_updates(offset)

            for upd in updates:
                update_id = upd.get("update_id")
                if update_id is not None:
                    uid = int(update_id)
                    if uid in seen_updates:
                        print(f"[dedup] skip duplicate update_id={uid}")
                        continue
                    seen_updates.add(uid)
                    # กัน memory โตไม่จบ
                    if len(seen_updates) > 2000:
                        seen_updates = set(sorted(seen_updates)[-1000:])
                    offset = uid + 1

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
                    reply = "❌ เกิดข้อผิดพลาดภายใน Bot กรุณาลองใหม่อีกครั้ง"

                try:
                    send_now = time.monotonic()
                    if _should_send_response(int(chat_id), reply, send_now):
                        send_message(int(chat_id), reply)
                except Exception as exc:
                    print(f"[sendMessage] error: {exc}")

        except KeyboardInterrupt:
            print("\nหยุด XSpring Telegram Bot")
            break

        except Exception as exc:
            msg = str(exc)
            print(f"[polling] error: {msg}")
            if "409" in msg or "Conflict" in msg or "terminated by other getUpdates" in msg:
                print("[polling] พบ Bot Token เดียวกันถูกใช้งานจาก process อื่น — รอ 15 วินาที")
                time.sleep(15)
            else:
                time.sleep(5)


if __name__ == "__main__":
    main_loop()
