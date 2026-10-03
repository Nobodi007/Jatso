import os
from datetime import datetime

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
# CONFIG
# ============================================================

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]

configuration = Configuration(
    access_token=CHANNEL_ACCESS_TOKEN
)

handler = WebhookHandler(CHANNEL_SECRET)


# ============================================================
# SIMULATED TRADING
# ============================================================

# ราคาเหรียญ "จำลอง"
# ยังไม่ได้เชื่อม Bitkub
MOCK_PRICES = {
    "BTC": 3_500_000,
    "ETH": 120_000,
    "XRP": 75,
}

# เงินเริ่มต้นของบัญชีจำลอง
STARTING_CASH = 100_000.00

# เก็บข้อมูลผู้ใช้ไว้ใน RAM
# หมายเหตุ: Render restart แล้วข้อมูลจะหาย
users = {}


# ============================================================
# USER DATA
# ============================================================

def create_user():
    return {
        "cash": STARTING_CASH,

        "coins": {
            "BTC": 0.0,
            "ETH": 0.0,
            "XRP": 0.0,
        },

        "history": [],

        # สถานะตอนกำลังซื้อ/ขาย
        "pending_action": None,
        "pending_coin": None,
    }


def get_user(user_id):

    if user_id not in users:
        users[user_id] = create_user()

    return users[user_id]


# ============================================================
# FORMAT
# ============================================================

def money(value):
    return f"{value:,.2f} บาท"


def coin_amount(value):
    return f"{value:,.8f}"


def portfolio_value(user):

    total = user["cash"]

    for coin, amount in user["coins"].items():
        total += amount * MOCK_PRICES[coin]

    return total


# ============================================================
# QUICK REPLY
# ============================================================

def quick_menu():

    return QuickReply(
        items=[

            QuickReplyItem(
                action=PostbackAction(
                    label="📊 ราคา",
                    data="menu=price"
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="💰 ซื้อ",
                    data="menu=buy"
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="🔴 ขาย",
                    data="menu=sell"
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="💼 พอร์ต",
                    data="menu=portfolio"
                )
            ),

            QuickReplyItem(
                action=PostbackAction(
                    label="📜 ประวัติ",
                    data="menu=history"
                )
            ),
        ]
    )


# ============================================================
# MAIN MENU
# ============================================================

def main_menu():

    return (
        "🤖 JATSO Trading Bot\n\n"
        "ระบบซื้อขาย Cryptocurrency แบบจำลอง\n"
        "⚠️ ตอนนี้ยังไม่ใช้เงินจริง\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "📊 ราคาเหรียญ\n"
        "💰 ซื้อ\n"
        "🔴 ขาย\n"
        "💼 พอร์ต\n"
        "📜 ประวัติ\n\n"
        "━━━━━━━━━━━━━━\n\n"
        "กดปุ่มด้านล่าง หรือพิมพ์:\n"
        "เมนู"
    )


# ============================================================
# PRICE
# ============================================================

def price_menu():

    text = (
        "📊 ราคาคริปโตจำลอง\n\n"
        f"🟠 BTC\n"
        f"{money(MOCK_PRICES['BTC'])}\n\n"
        f"🔵 ETH\n"
        f"{money(MOCK_PRICES['ETH'])}\n\n"
        f"⚪ XRP\n"
        f"{money(MOCK_PRICES['XRP'])}\n\n"
        "━━━━━━━━━━━━━━\n"
        "⚠️ ราคานี้เป็นราคาจำลอง\n"
        "ยังไม่ได้เชื่อม Bitkub"
    )

    return text


# ============================================================
# BUY
# ============================================================

def start_buy(user):

    user["pending_action"] = "buy"
    user["pending_coin"] = None

    return (
        "💰 ซื้อ Cryptocurrency\n\n"
        "เลือกเหรียญที่ต้องการซื้อ\n\n"
        "พิมพ์:\n"
        "BTC\n"
        "ETH\n"
        "XRP\n\n"
        "หรือพิมพ์ \"ยกเลิก\""
    )


# ============================================================
# SELL
# ============================================================

def start_sell(user):

    user["pending_action"] = "sell"
    user["pending_coin"] = None

    return (
        "🔴 ขาย Cryptocurrency\n\n"
        "เลือกเหรียญที่ต้องการขาย\n\n"
        "พิมพ์:\n"
        "BTC\n"
        "ETH\n"
        "XRP\n\n"
        "หรือพิมพ์ \"ยกเลิก\""
    )


# ============================================================
# PORTFOLIO
# ============================================================

def portfolio_menu(user):

    total = portfolio_value(user)

    btc_value = user["coins"]["BTC"] * MOCK_PRICES["BTC"]
    eth_value = user["coins"]["ETH"] * MOCK_PRICES["ETH"]
    xrp_value = user["coins"]["XRP"] * MOCK_PRICES["XRP"]

    return (
        "💼 JATSO Portfolio\n\n"

        f"💵 เงินสด\n"
        f"{money(user['cash'])}\n\n"

        "━━━━━━━━━━━━━━\n\n"

        f"🟠 BTC\n"
        f"จำนวน: {coin_amount(user['coins']['BTC'])}\n"
        f"มูลค่า: {money(btc_value)}\n\n"

        f"🔵 ETH\n"
        f"จำนวน: {coin_amount(user['coins']['ETH'])}\n"
        f"มูลค่า: {money(eth_value)}\n\n"

        f"⚪ XRP\n"
        f"จำนวน: {coin_amount(user['coins']['XRP'])}\n"
        f"มูลค่า: {money(xrp_value)}\n\n"

        "━━━━━━━━━━━━━━\n\n"

        f"💼 มูลค่าพอร์ตรวม\n"
        f"{money(total)}"
    )


# ============================================================
# HISTORY
# ============================================================

def history_menu(user):

    history = user["history"]

    if not history:

        return (
            "📜 ประวัติการซื้อขาย\n\n"
            "ยังไม่มีรายการซื้อขาย"
        )

    text = "📜 ประวัติการซื้อขาย\n\n"

    # แสดงสูงสุด 10 รายการล่าสุด
    for trade in history[-10:][::-1]:

        if trade["action"] == "BUY":
            emoji = "💰"
            action_text = "ซื้อ"
        else:
            emoji = "🔴"
            action_text = "ขาย"

        text += (
            f"{emoji} {action_text} {trade['coin']}\n"
            f"จำนวน: {coin_amount(trade['amount'])}\n"
            f"ราคา: {money(trade['price'])}\n"
            f"มูลค่า: {money(trade['total'])}\n"
            f"เวลา: {trade['time']}\n"
            "━━━━━━━━━━━━━━\n"
        )

    return text


# ============================================================
# PROCESS COIN
# ============================================================

def process_coin(user, text):

    coin = text.upper().strip()

    if coin not in MOCK_PRICES:

        return (
            "❌ ไม่พบเหรียญนี้\n\n"
            "รองรับ:\n"
            "BTC\n"
            "ETH\n"
            "XRP\n\n"
            "หรือพิมพ์ \"ยกเลิก\""
        )

    user["pending_coin"] = coin

    price = MOCK_PRICES[coin]

    if user["pending_action"] == "buy":

        return (
            f"💰 ซื้อ {coin}\n\n"
            f"ราคาปัจจุบัน:\n"
            f"{money(price)}\n\n"
            "ต้องการใช้เงินกี่บาท?\n\n"
            "ตัวอย่าง:\n"
            "1000\n\n"
            "หรือพิมพ์ \"ยกเลิก\""
        )

    if user["pending_action"] == "sell":

        owned = user["coins"][coin]

        return (
            f"🔴 ขาย {coin}\n\n"
            f"ราคาปัจจุบัน:\n"
            f"{money(price)}\n\n"
            f"คุณมี:\n"
            f"{coin_amount(owned)} {coin}\n\n"
            "ต้องการขายกี่เหรียญ?\n\n"
            "ตัวอย่าง:\n"
            "0.001\n\n"
            "หรือพิมพ์ \"ยกเลิก\""
        )

    return main_menu()


# ============================================================
# PROCESS TRADE
# ============================================================

def process_trade(user, text):

    try:

        amount = float(
            text.replace(",", "").strip()
        )

    except ValueError:

        return (
            "❌ กรุณาใส่ตัวเลขเท่านั้น\n\n"
            "ตัวอย่าง:\n"
            "1000"
        )

    if amount <= 0:

        return "❌ จำนวนต้องมากกว่า 0"

    action = user["pending_action"]
    coin = user["pending_coin"]
    price = MOCK_PRICES[coin]


    # ========================================================
    # BUY
    # ========================================================

    if action == "buy":

        cash_to_use = amount

        if cash_to_use > user["cash"]:

            return (
                "❌ เงินไม่พอ\n\n"
                f"เงินที่มี:\n"
                f"{money(user['cash'])}\n\n"
                f"ต้องการใช้:\n"
                f"{money(cash_to_use)}"
            )

        bought_amount = cash_to_use / price

        user["cash"] -= cash_to_use

        user["coins"][coin] += bought_amount

        user["history"].append({

            "action": "BUY",

            "coin": coin,

            "amount": bought_amount,

            "price": price,

            "total": cash_to_use,

            "time": datetime.now().strftime(
                "%d/%m/%Y %H:%M:%S"
            ),
        })

        # reset state
        user["pending_action"] = None
        user["pending_coin"] = None

        return (
            "✅ ซื้อสำเร็จ\n\n"

            f"🪙 เหรียญ: {coin}\n"

            f"📦 จำนวน:\n"
            f"{coin_amount(bought_amount)} {coin}\n\n"

            f"💰 ราคา:\n"
            f"{money(price)}\n\n"

            f"💵 ใช้เงิน:\n"
            f"{money(cash_to_use)}\n\n"

            "━━━━━━━━━━━━━━\n\n"

            f"💵 เงินคงเหลือ:\n"
            f"{money(user['cash'])}"
        )


    # ========================================================
    # SELL
    # ========================================================

    if action == "sell":

        sell_amount = amount

        owned = user["coins"][coin]

        if sell_amount > owned:

            return (
                "❌ เหรียญไม่พอ\n\n"

                f"คุณมี:\n"
                f"{coin_amount(owned)} {coin}\n\n"

                f"ต้องการขาย:\n"
                f"{coin_amount(sell_amount)} {coin}"
            )

        cash_received = sell_amount * price

        user["coins"][coin] -= sell_amount

        user["cash"] += cash_received

        user["history"].append({

            "action": "SELL",

            "coin": coin,

            "amount": sell_amount,

            "price": price,

            "total": cash_received,

            "time": datetime.now().strftime(
                "%d/%m/%Y %H:%M:%S"
            ),
        })

        # reset state
        user["pending_action"] = None
        user["pending_coin"] = None

        return (
            "✅ ขายสำเร็จ\n\n"

            f"🪙 เหรียญ: {coin}\n"

            f"📦 จำนวน:\n"
            f"{coin_amount(sell_amount)} {coin}\n\n"

            f"💰 ราคา:\n"
            f"{money(price)}\n\n"

            f"💵 ได้รับเงิน:\n"
            f"{money(cash_received)}\n\n"

            "━━━━━━━━━━━━━━\n\n"

            f"💵 เงินคงเหลือ:\n"
            f"{money(user['cash'])}"
        )


    return main_menu()


# ============================================================
# REPLY
# ============================================================

def reply_message(reply_token, text):

    with ApiClient(configuration) as api_client:

        messaging_api = MessagingApi(api_client)

        messaging_api.reply_message(

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

@app.route("/webhook", methods=["POST"])
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
# MESSAGE HANDLER
# ============================================================

@handler.add(
    MessageEvent,
    message=TextMessageContent
)
def handle_message(event):

    user_id = event.source.user_id

    user = get_user(user_id)

    user_text = event.message.text.strip()

    text_lower = user_text.lower()


    # ========================================================
    # CANCEL
    # ========================================================

    if text_lower in [
        "ยกเลิก",
        "cancel",
        "ยกเลิกคำสั่ง"
    ]:

        user["pending_action"] = None
        user["pending_coin"] = None

        reply_message(
            event.reply_token,
            "❌ ยกเลิกคำสั่งแล้ว\n\n" + main_menu()
        )

        return


    # ========================================================
    # BUY / SELL FLOW
    # ========================================================

    if user["pending_action"] in [
        "buy",
        "sell"
    ]:

        # ยังไม่ได้เลือกเหรียญ
        if user["pending_coin"] is None:

            response = process_coin(
                user,
                user_text
            )

        # เลือกเหรียญแล้ว กำลังรอจำนวน
        else:

            response = process_trade(
                user,
                user_text
            )

        reply_message(
            event.reply_token,
            response
        )

        return


    # ========================================================
    # MAIN COMMANDS
    # ========================================================

    if text_lower in [
        "เมนู",
        "menu",
        "start",
        "เริ่ม"
    ]:

        response = main_menu()


    elif text_lower in [
        "1",
        "ราคา",
        "ราคาเหรียญ",
        "price"
    ]:

        response = price_menu()


    elif text_lower in [
        "2",
        "ซื้อ",
        "buy"
    ]:

        response = start_buy(user)


    elif text_lower in [
        "3",
        "ขาย",
        "sell"
    ]:

        response = start_sell(user)


    elif text_lower in [
        "4",
        "พอร์ต",
        "portfolio"
    ]:

        response = portfolio_menu(user)


    elif text_lower in [
        "5",
        "ประวัติ",
        "history"
    ]:

        response = history_menu(user)


    else:

        response = (
            "🤖 JATSO Trading Bot\n\n"
            "ไม่พบคำสั่งนี้ครับ\n\n"
            "พิมพ์ \"เมนู\" เพื่อเปิด Trading Bot"
        )


    reply_message(
        event.reply_token,
        response
    )


# ============================================================
# POSTBACK HANDLER
# ============================================================

@handler.add(PostbackEvent)
def handle_postback(event):

    user_id = event.source.user_id

    user = get_user(user_id)

    data = event.postback.data


    if data == "menu=price":

        response = price_menu()


    elif data == "menu=buy":

        response = start_buy(user)


    elif data == "menu=sell":

        response = start_sell(user)


    elif data == "menu=portfolio":

        response = portfolio_menu(user)


    elif data == "menu=history":

        response = history_menu(user)


    else:

        response = main_menu()


    reply_message(
        event.reply_token,
        response
    )


# ============================================================
# HOME
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return "JATSO LINE Trading Bot is running."


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
