import os
import json
import uuid
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
)

from linebot.v3.messaging.models import PostbackAction
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent,
)


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or ""
)

# สำคัญมาก:
# ต้องเป็น actor เดียวกับ account ที่เว็บ XSpring ใช้อยู่
XSPRING_ACTOR = (
    os.environ.get("XSPRING_LINE_ACTOR_EMAIL")
    or os.environ.get("XSPRING_EMAIL")
    or ""
).strip().lower()


configuration = Configuration(
    access_token=CHANNEL_ACCESS_TOKEN
)

handler = WebhookHandler(CHANNEL_SECRET)


# ============================================================
# CONFIG
# ============================================================

SUPPORTED_ASSETS = [
    "BTC",
    "ETH",
    "SOL",
    "DOGE",
    "ADA",
    "HBAR",
    "LINK",
    "XLM",
    "XRP",
    "USDT",
    "USDC",
]

# ตอนนี้ใช้ simulator fee เดียวกับที่หน้า Exchange แสดง
TRADING_FEE_PCT = float(
    os.environ.get("XSPRING_TRADING_FEE_PCT", "0.25")
) / 100.0

MIN_TRADE_THB = float(
    os.environ.get("XSPRING_MIN_TRADE_THB", "1")
)


# ============================================================
# SUPABASE REST
# ============================================================

def supabase_request(method, path, payload=None, query=None):

    if not SUPABASE_URL:
        raise RuntimeError("ยังไม่ได้ตั้ง SUPABASE_URL")

    if not SUPABASE_KEY:
        raise RuntimeError(
            "ยังไม่ได้ตั้ง SUPABASE_SERVICE_ROLE_KEY หรือ SUPABASE_KEY"
        )

    url = SUPABASE_URL + path

    if query:
        url += "?" + urllib.parse.urlencode(query)

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    data = None

    if payload is not None:
        data = json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(
        req,
        timeout=10
    ) as response:

        raw = response.read()

        if not raw:
            return None

        return json.loads(
            raw.decode("utf-8")
        )


# ============================================================
# SIM STATE
# ============================================================

def load_sim_state():

    if not XSPRING_ACTOR:
        raise RuntimeError(
            "ยังไม่ได้ตั้ง XSPRING_LINE_ACTOR_EMAIL"
        )

    rows = supabase_request(
        "GET",
        "/rest/v1/sim_state",
        query={
            "select": "data,actor,updated_at",
            "actor": f"eq.{XSPRING_ACTOR}",
            "limit": "1",
        },
    )

    if not rows:
        raise RuntimeError(
            "ไม่พบ XSpring Portfolio ของ actor นี้"
        )

    data = rows[0].get("data")

    if isinstance(data, str):

        data = json.loads(data)

    if not isinstance(data, dict):

        raise RuntimeError(
            "sim_state ใน Supabase ไม่ใช่ JSON object"
        )

    return data


def save_sim_state(sim):

    supabase_request(
        "PATCH",
        "/rest/v1/sim_state",
        payload={
            "data": sim,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        },
        query={
            "actor": f"eq.{XSPRING_ACTOR}"
        },
    )


# ============================================================
# PRICE
# ============================================================

def get_price_usd(asset):

    # ใช้ CoinGecko แทน Binance เพราะ Binance API
    # อาจตอบ HTTP 451 จาก Render region
    coin_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "DOGE": "dogecoin",
        "ADA": "cardano",
        "HBAR": "hedera-hashgraph",
        "LINK": "chainlink",
        "XLM": "stellar",
        "XRP": "ripple",
        "USDT": "tether",
        "USDC": "usd-coin",
    }

    asset = str(asset).upper().strip()

    if asset not in coin_map:
        raise ValueError(
            f"ไม่รองรับเหรียญ {asset}"
        )

    if asset in ["USDT", "USDC"]:
        return 1.0

    url = "https://api.coingecko.com/api/v3/simple/price"

    params = urllib.parse.urlencode({
        "ids": coin_map[asset],
        "vs_currencies": "usd",
    })

    req = urllib.request.Request(
        f"{url}?{params}",
        headers={
            "User-Agent": "JATSO-LINE-Bot/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=10
    ) as response:

        data = json.loads(
            response.read().decode("utf-8")
        )

    coin_id = coin_map[asset]

    if (
        coin_id not in data
        or "usd" not in data[coin_id]
    ):
        raise RuntimeError(
            f"ไม่พบราคา {asset} จาก CoinGecko"
        )

    return float(data[coin_id]["usd"])


def get_usdthb():

    # ใช้ exchangerate API แบบ public สำหรับ simulator
    url = (
        "https://open.er-api.com/v6/latest/USD"
    )

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JATSO-LINE-Bot"
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=8
    ) as response:

        data = json.loads(
            response.read().decode("utf-8")
        )

    return float(
        data["rates"]["THB"]
    )


def get_price_thb(asset):

    usd = get_price_usd(asset)
    fx = get_usdthb()

    return usd * fx


# ============================================================
# USER SESSION
# ============================================================

line_sessions = {}


def get_session(user_id):

    if user_id not in line_sessions:

        line_sessions[user_id] = {
            "action": None,
            "asset": None,
            "amount": None,
            "quote": None,
            "order_id": None,
        }

    return line_sessions[user_id]


def clear_session(user_id):

    line_sessions[user_id] = {
        "action": None,
        "asset": None,
        "amount": None,
        "quote": None,
        "order_id": None,
    }


# ============================================================
# FORMAT
# ============================================================

def money(v):

    return f"฿{float(v):,.2f}"


def coin(v):

    return f"{float(v):,.8f}"


# ============================================================
# MENU
# ============================================================

def menu_text():

    return (
        "🤖 JATSO Trading Bot\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📊 ราคา\n"
        "💰 ซื้อ\n"
        "🔴 ขาย\n"
        "💼 พอร์ต\n"
        "📜 ประวัติ\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "ระบบนี้เชื่อมกับ XSpring Dealer Suite\n"
        "⚠️ ยังเป็น Exchange Simulator\n\n"
        "พิมพ์ \"เมนู\" เพื่อกลับหน้าหลัก"
    )


def quick_menu():

    return QuickReply(
        items=[

            QuickReplyItem(
                action=PostbackAction(
                    label="📊 ราคา",
                    data="price",
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="💰 ซื้อ",
                    data="buy",
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="🔴 ขาย",
                    data="sell",
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="💼 พอร์ต",
                    data="portfolio",
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="📜 ประวัติ",
                    data="history",
                )
            ),

        ]
    )


# ============================================================
# PRICE
# ============================================================

def show_price(asset="BTC"):

    asset = asset.upper()

    if asset not in SUPPORTED_ASSETS:

        return "❌ ไม่รองรับเหรียญนี้"

    try:

        px = get_price_thb(asset)

        return (
            f"📊 {asset}/THB\n\n"
            f"ราคาปัจจุบันประมาณ\n"
            f"{money(px)}\n\n"
            "⚠️ ราคาสำหรับ Simulator"
        )

    except Exception as exc:

        return (
            "❌ ดึงราคาไม่ได้\n\n"
            f"{str(exc)[:120]}"
        )


# ============================================================
# PORTFOLIO
# ============================================================

def show_portfolio():

    sim = load_sim_state()

    cash = float(
        sim.get(
            "customer_thb",
            0
        ) or 0
    )

    coins = sim.get(
        "customer_coins",
        {}
    )

    if not isinstance(coins, dict):

        coins = {}

    text = (
        "💼 XSpring Portfolio\n\n"
        f"💵 THB\n"
        f"{money(cash)}\n\n"
        "━━━━━━━━━━━━━━━━\n"
    )

    for asset, qty in coins.items():

        try:

            qty = float(qty)

        except Exception:

            continue

        if qty <= 0:
            continue

        try:

            px = get_price_thb(asset)
            value = qty * px

            text += (
                f"\n🪙 {asset}\n"
                f"จำนวน {coin(qty)}\n"
                f"มูลค่า {money(value)}\n"
            )

        except Exception:

            text += (
                f"\n🪙 {asset}\n"
                f"จำนวน {coin(qty)}\n"
            )

    return text


# ============================================================
# HISTORY
# ============================================================

def show_history():

    sim = load_sim_state()

    orders = sim.get(
        "orders",
        []
    )

    if not orders:

        return (
            "📜 ประวัติ\n\n"
            "ยังไม่มีรายการ"
        )

    rows = [
        x
        for x in orders
        if isinstance(x, dict)
        and str(
            x.get("Source", "")
        ).lower() == "line"
    ]

    if not rows:

        return (
            "📜 ประวัติ LINE\n\n"
            "ยังไม่มีรายการซื้อขายผ่าน LINE"
        )

    text = "📜 ประวัติ LINE\n\n"

    for rec in rows[-10:][::-1]:

        text += (
            f"{'🟢' if rec.get('ฝั่ง') == 'ซื้อ' else '🔴'} "
            f"{rec.get('ฝั่ง', '—')} "
            f"{rec.get('เหรียญ', '—')}\n"
            f"มูลค่า: {money(rec.get('มูลค่า (บาท)', 0))}\n"
            f"ราคา: {money(rec.get('ราคาที่ลูกค้าได้', 0))}\n"
            f"Order: {rec.get('Order ID', '—')}\n"
            "━━━━━━━━━━━━\n"
        )

    return text


# ============================================================
# BUY
# ============================================================

def start_buy(user_id):

    s = get_session(user_id)

    s["action"] = "buy"
    s["asset"] = None
    s["amount"] = None
    s["quote"] = None
    s["order_id"] = None

    return (
        "💰 BUY\n\n"
        "พิมพ์เหรียญที่ต้องการซื้อ\n\n"
        "ตัวอย่าง:\n"
        "BTC\n\n"
        "หรือพิมพ์ /cancel"
    )


# ============================================================
# SELL
# ============================================================

def start_sell(user_id):

    s = get_session(user_id)

    s["action"] = "sell"
    s["asset"] = None
    s["amount"] = None
    s["quote"] = None
    s["order_id"] = None

    return (
        "🔴 SELL\n\n"
        "พิมพ์เหรียญที่ต้องการขาย\n\n"
        "ตัวอย่าง:\n"
        "BTC\n\n"
        "หรือพิมพ์ /cancel"
    )


# ============================================================
# COIN SELECTION
# ============================================================

def select_coin(user_id, text):

    asset = text.upper().strip()

    if asset not in SUPPORTED_ASSETS:

        return (
            "❌ ไม่พบเหรียญ\n\n"
            "รองรับ:\n"
            + ", ".join(SUPPORTED_ASSETS)
        )

    s = get_session(user_id)

    s["asset"] = asset

    if s["action"] == "buy":

        return (
            f"💰 BUY {asset}\n\n"
            "ต้องการซื้อเป็นเงินกี่บาท?\n\n"
            "ตัวอย่าง:\n"
            "500000"
        )

    return (
        f"🔴 SELL {asset}\n\n"
        "ต้องการขายกี่เหรียญ?\n\n"
        "ตัวอย่าง:\n"
        "0.1"
    )


# ============================================================
# CREATE ORDER
# ============================================================

def create_order_preview(user_id, amount):

    s = get_session(user_id)

    asset = s["asset"]
    action = s["action"]

    sim = load_sim_state()

    cash = float(
        sim.get(
            "customer_thb",
            0
        ) or 0
    )

    coins = sim.setdefault(
        "customer_coins",
        {}
    )

    owned = float(
        coins.get(
            asset,
            0
        ) or 0
    )

    try:

        market_price = get_price_thb(asset)

    except Exception as exc:

        return (
            f"❌ ดึงราคา {asset} ไม่ได้\n"
            f"{str(exc)[:100]}"
        )

    if action == "buy":

        amount_thb = amount

        if amount_thb < MIN_TRADE_THB:

            return "❌ มูลค่าซื้อต่ำเกินไป"

        if amount_thb > cash:

            return (
                "❌ เงินไม่พอ\n\n"
                f"เงินคงเหลือ: {money(cash)}\n"
                f"ต้องการ: {money(amount_thb)}"
            )

        quote = market_price

        fee = amount_thb * TRADING_FEE_PCT

        qty = amount_thb / quote

        order_id = (
            "LINE-"
            + uuid.uuid4().hex[:10].upper()
        )

        s["amount"] = amount_thb
        s["quote"] = quote
        s["order_id"] = order_id

        return (
            "🟢 ยืนยันคำสั่ง BUY\n\n"
            f"Order ID: {order_id}\n"
            f"Source: LINE\n"
            f"Pair: {asset}/THB\n"
            f"Type: MARKET\n\n"
            f"จำนวนเงิน: {money(amount_thb)}\n"
            f"ราคา: {money(quote)}\n"
            f"ประมาณได้รับ: {coin(qty)} {asset}\n"
            f"Fee: {fee:,.2f} บาท\n\n"
            "⚠️ Exchange Simulator\n\n"
            "พิมพ์ /confirm เพื่อยืนยัน\n"
            "หรือ /cancel เพื่อยกเลิก"
        )

    # SELL

    qty = amount

    if qty <= 0:

        return "❌ จำนวนต้องมากกว่า 0"

    if qty > owned:

        return (
            "❌ เหรียญไม่พอ\n\n"
            f"ถืออยู่: {coin(owned)} {asset}\n"
            f"ต้องการขาย: {coin(qty)} {asset}"
        )

    quote = market_price

    gross = qty * quote

    fee = gross * TRADING_FEE_PCT

    receive = gross - fee

    order_id = (
        "LINE-"
        + uuid.uuid4().hex[:10].upper()
    )

    s["amount"] = qty
    s["quote"] = quote
    s["order_id"] = order_id

    return (
        "🔴 ยืนยันคำสั่ง SELL\n\n"
        f"Order ID: {order_id}\n"
        f"Source: LINE\n"
        f"Pair: {asset}/THB\n"
        f"Type: MARKET\n\n"
        f"จำนวน: {coin(qty)} {asset}\n"
        f"ราคา: {money(quote)}\n"
        f"มูลค่าขาย: {money(gross)}\n"
        f"Fee: {money(fee)}\n"
        f"ได้รับสุทธิ: {money(receive)}\n\n"
        "⚠️ Exchange Simulator\n\n"
        "พิมพ์ /confirm เพื่อยืนยัน\n"
        "หรือ /cancel เพื่อยกเลิก"
    )


# ============================================================
# CONFIRM
# ============================================================

def confirm_order(user_id):

    s = get_session(user_id)

    if not s.get("action"):
        return "❌ ไม่มีคำสั่งที่รอยืนยัน"

    if not s.get("asset"):
        return "❌ ยังไม่ได้เลือกเหรียญ"

    if not s.get("amount"):
        return "❌ ยังไม่ได้ระบุจำนวน"

    sim = load_sim_state()

    cash = float(
        sim.get(
            "customer_thb",
            0
        ) or 0
    )

    coins = sim.setdefault(
        "customer_coins",
        {}
    )

    asset = s["asset"]
    action = s["action"]
    amount = float(s["amount"])
    quote = float(s["quote"])
    order_id = s["order_id"]

    owned = float(
        coins.get(
            asset,
            0
        ) or 0
    )

    now = datetime.now(
        timezone.utc
    )

    # ========================================================
    # BUY
    # ========================================================

    if action == "buy":

        if amount > cash:

            return (
                "❌ ORDER REJECTED\n\n"
                "เงินคงเหลือไม่พอ"
            )

        qty = amount / quote

        fee = amount * TRADING_FEE_PCT

        coins[asset] = (
            owned + qty
        )

        sim["customer_thb"] = (
            cash - amount
        )

        side_th = "ซื้อ"

        delivered = qty

    # ========================================================
    # SELL
    # ========================================================

    else:

        qty = amount

        if qty > owned:

            return (
                "❌ ORDER REJECTED\n\n"
                "เหรียญคงเหลือไม่พอ"
            )

        gross = qty * quote

        fee = gross * TRADING_FEE_PCT

        receive = gross - fee

        coins[asset] = max(
            0.0,
            owned - qty
        )

        sim["customer_thb"] = (
            cash + receive
        )

        side_th = "ขาย"

        delivered = qty

        amount = gross

    # ========================================================
    # ORDER RECORD
    # ========================================================

    order = {

        "วันที่": now.strftime(
            "%Y-%m-%d"
        ),

        "เวลา": now.strftime(
            "%H:%M:%S"
        ),

        "ฝั่ง": side_th,

        "เหรียญ": asset,

        "มูลค่า (บาท)": amount,

        "ราคาที่ลูกค้าได้": quote,

        "เหรียญที่ส่งมอบ": delivered,

        "ค่าธรรมเนียม": fee,

        "สถานะ": "Filled",

        "ประเภท": "MARKET",

        "Exchange": "XSpring Simulator",

        "Source": "LINE",

        "Order ID": order_id,

        "Customer": XSPRING_ACTOR,

        "Line User ID": user_id,

    }

    sim.setdefault(
        "orders",
        []
    ).append(order)

    # ========================================================
    # SAVE
    # ========================================================

    save_sim_state(sim)

    # clear pending
    clear_session(user_id)

    return (
        "✅ ORDER FILLED\n\n"
        f"Order ID: {order_id}\n"
        f"Source: LINE\n"
        f"Exchange: XSpring Simulator\n\n"
        f"{'ซื้อ' if action == 'buy' else 'ขาย'} "
        f"{coin(delivered)} {asset}\n"
        f"ราคา: {money(quote)}\n"
        f"Fee: {money(fee)}\n\n"
        f"💵 THB คงเหลือ\n"
        f"{money(sim['customer_thb'])}\n\n"
        f"🪙 {asset}\n"
        f"{coin(coins[asset])}\n\n"
        "Portfolio ใน XSpring Dealer Suite "
        "จะใช้รายการนี้เป็น Source: LINE"
    )


# ============================================================
# REPLY
# ============================================================

def reply_message(
    reply_token,
    text
):

    with ApiClient(
        configuration
    ) as api_client:

        api = MessagingApi(
            api_client
        )

        api.reply_message(

            ReplyMessageRequest(

                reply_token=reply_token,

                messages=[
                    TextMessage(
                        text=text,
                        quick_reply=quick_menu()
                    )
                ]
            )
        )


# ============================================================
# WEBHOOK
# ============================================================

@app.route(
    "/webhook",
    methods=["POST"]
)
def webhook():

    signature = request.headers.get(
        "X-Line-Signature"
    )

    if not signature:
        abort(400)

    body = request.get_data(
        as_text=True
    )

    try:

        handler.handle(
            body,
            signature
        )

    except InvalidSignatureError:

        abort(400)

    return "OK"


# ============================================================
# MESSAGE
# ============================================================

@handler.add(
    MessageEvent,
    message=TextMessageContent
)
def handle_message(event):

    user_id = event.source.user_id

    text = (
        event.message.text
        .strip()
    )

    lower = text.lower()

    try:

        # ----------------------------------------------------
        # CANCEL
        # ----------------------------------------------------

        if lower in [
            "/cancel",
            "cancel",
            "ยกเลิก",
        ]:

            clear_session(
                user_id
            )

            response = (
                "❌ ยกเลิกคำสั่งแล้ว\n\n"
                + menu_text()
            )

        # ----------------------------------------------------
        # CONFIRM
        # ----------------------------------------------------

        elif lower in [
            "/confirm",
            "confirm",
        ]:

            response = confirm_order(
                user_id
            )

        # ----------------------------------------------------
        # MENU
        # ----------------------------------------------------

        elif lower in [
            "เมนู",
            "menu",
            "/start",
            "start",
        ]:

            response = menu_text()

        # ----------------------------------------------------
        # PRICE
        # ----------------------------------------------------

        elif lower in [
            "ราคา",
            "price",
            "ราคา btc",
        ]:

            response = show_price("BTC")

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        elif lower in [
            "ซื้อ",
            "buy",
        ]:

            response = start_buy(
                user_id
            )

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        elif lower in [
            "ขาย",
            "sell",
        ]:

            response = start_sell(
                user_id
            )

        # ----------------------------------------------------
        # PORTFOLIO
        # ----------------------------------------------------

        elif lower in [
            "พอร์ต",
            "portfolio",
            "wallet",
        ]:

            response = show_portfolio()

        # ----------------------------------------------------
        # HISTORY
        # ----------------------------------------------------

        elif lower in [
            "ประวัติ",
            "history",
        ]:

            response = show_history()

        # ----------------------------------------------------
        # BUY / SELL FLOW
        # ----------------------------------------------------

        else:

            session = get_session(
                user_id
            )

            if session["action"]:

                # ขั้นเลือกเหรียญ
                if session["asset"] is None:

                    response = select_coin(
                        user_id,
                        text
                    )

                # ขั้นกรอกจำนวน
                else:

                    try:

                        value = float(
                            text.replace(
                                ",",
                                ""
                            )
                        )

                    except ValueError:

                        response = (
                            "❌ กรุณาใส่ตัวเลข\n\n"
                            "ตัวอย่าง:\n"
                            "500000"
                        )

                    else:

                        response = create_order_preview(
                            user_id,
                            value
                        )

            else:

                response = (
                    "🤖 ไม่พบคำสั่ง\n\n"
                    "พิมพ์ \"เมนู\" เพื่อเปิด JATSO Trading Bot"
                )

    except Exception as exc:

        print(
            f"[LINE ERROR] {type(exc).__name__}: {exc}"
        )

        response = (
            "❌ ระบบเกิดข้อผิดพลาด\n\n"
            "ลองใหม่อีกครั้งครับ"
        )

    reply_message(
        event.reply_token,
        response
    )


# ============================================================
# POSTBACK
# ============================================================

@handler.add(PostbackEvent)
def handle_postback(event):

    user_id = event.source.user_id

    data = event.postback.data

    try:

        if data == "price":

            response = show_price("BTC")

        elif data == "buy":

            response = start_buy(
                user_id
            )

        elif data == "sell":

            response = start_sell(
                user_id
            )

        elif data == "portfolio":

            response = show_portfolio()

        elif data == "history":

            response = show_history()

        else:

            response = menu_text()

    except Exception as exc:

        print(
            f"[LINE POSTBACK ERROR] {exc}"
        )

        response = (
            "❌ ระบบเกิดข้อผิดพลาด"
        )

    reply_message(
        event.reply_token,
        response
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return (
        "JATSO LINE Trading Bot is running."
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        )
    )
