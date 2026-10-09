import os, sys, json
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import requests
import yfinance as yf

BKK = timezone(timedelta(hours=7))
TH_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]


def env(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        sys.exit(f"ยังไม่ได้ตั้งค่า secret: {name}")
    return v


def num(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def money(n, sign=False):
    body = f"฿{abs(n):,.2f}"
    if n < 0:
        return "-" + body
    if sign and n > 0:
        return "+" + body
    return body


def pct(n):
    return f"{'+' if n > 0 else ''}{n:.2f}%"


# ---------- ดึงข้อมูลพอร์ตจาก Supabase (ตาราง sim_state เดียวกับแอป) ----------
def load_sim():
    url = env("SUPABASE_URL").rstrip("/")
    key = env("SUPABASE_KEY")
    actor = env("SUPABASE_ACTOR", required=False)
    q = "select=data,actor,updated_at&order=updated_at.desc&limit=1"
    if actor:
        q += f"&actor=eq.{quote(actor)}"
    r = requests.get(
        f"{url}/rest/v1/sim_state?{q}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        sys.exit("ไม่พบข้อมูลพอร์ตใน Supabase")
    data = rows[0]["data"]
    return json.loads(data) if isinstance(data, str) else data


# ---------- คำนวณต้นทุนเฉลี่ยแบบเดียวกับ portfolio_snapshot ในแอป ----------
def build_positions(sim):
    txs = sim.get("portfolio_ledger") or []
    cash, realized = 0.0, 0.0
    qty, avg = {}, {}
    for tx in txs:
        if not isinstance(tx, dict):
            continue
        typ = str(tx.get("type", "")).upper()
        asset = str(tx.get("asset", "THB")).upper()
        q = num(tx.get("qty"))
        gross = num(tx.get("gross_thb"))
        cash += num(tx.get("cash_delta_thb"))
        if asset == "THB" or typ in {"DEPOSIT", "WITHDRAWAL", "FEE"}:
            realized += num(tx.get("realized_pnl_thb"))
            continue
        old_q, old_c = qty.get(asset, 0.0), avg.get(asset, 0.0)
        if typ == "BUY" and q > 0:
            new_q = old_q + q
            avg[asset] = (old_q * old_c + gross) / new_q if new_q > 0 else 0.0
            qty[asset] = new_q
        elif typ == "SELL" and q < 0:
            realized += num(tx.get("realized_pnl_thb"))
            qty[asset] = max(0.0, old_q - abs(q))
            if qty[asset] <= 1e-12:
                qty[asset], avg[asset] = 0.0, 0.0
    if "customer_thb" in sim:
        cash = num(sim.get("customer_thb"))
    holdings = {a: (q, avg.get(a, 0.0)) for a, q in qty.items() if q > 1e-12}
    return cash, holdings, realized, txs


# ---------- ราคาปัจจุบัน (yfinance แบบเดียวกับแอป) ----------
def get_prices(symbols):
    if not symbols:
        return {}
    tickers = [f"{s}-USD" for s in symbols] + ["THB=X"]
    close = yf.download(tickers, period="5d", interval="1d", progress=False)["Close"].ffill()
    last = close.iloc[-1]
    usdthb = float(last["THB=X"])
    out = {}
    for s in symbols:
        v = last.get(f"{s}-USD")
        if v is not None and v == v:
            out[s] = float(v) * usdthb
    return out


def trades_today(txs, today):
    n = 0
    for tx in txs:
        if not isinstance(tx, dict) or str(tx.get("type", "")).upper() not in {"BUY", "SELL"}:
            continue
        ts = str(tx.get("timestamp", ""))
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            d = d.replace(tzinfo=BKK) if d.tzinfo is None else d.astimezone(BKK)
            if d.date() == today:
                n += 1
        except ValueError:
            if ts[:10] == today.isoformat():
                n += 1
    return n


def build_message(sim):
    now = datetime.now(BKK)
    cash, holdings, realized, txs = build_positions(sim)
    prices = get_prices(list(holdings.keys()))

    rows = []
    for asset, (q, avg) in holdings.items():
        px = prices.get(asset, 0.0)
        value, cost = q * px, q * avg
        upnl = value - cost if avg > 0 and px > 0 else 0.0
        rows.append({
            "asset": asset, "value": value, "cost": cost, "upnl": upnl,
            "pct": (upnl / cost * 100) if cost > 0 else 0.0,
        })

    market = sum(r["value"] for r in rows)
    invested = sum(r["cost"] for r in rows)
    unrealized = sum(r["upnl"] for r in rows)
    total_pnl = unrealized + realized
    total_pct = (total_pnl / invested * 100) if invested > 0 else 0.0
    n_trades = trades_today(txs, now.date())

    lines = [
        "📊 รายงานพอร์ตประจำวัน",
        f"{TH_DAYS[now.weekday()]} {now:%d/%m/%Y} เวลา {now:%H:%M}",
        "",
        "💼 สถานะพอร์ต",
        f"มูลค่ารวม: {money(cash + market)}",
        f"เงินสด: {money(cash)}",
        f"มูลค่าเหรียญ: {money(market)} ({len(rows)} เหรียญ)",
        "",
        f"{'📈' if total_pnl >= 0 else '📉'} กำไร/ขาดทุน",
        f"รวม: {money(total_pnl, sign=True)} ({pct(total_pct)})",
        f"ยังไม่ขายออก: {money(unrealized, sign=True)}",
        f"ขายแล้ว: {money(realized, sign=True)}",
        "",
    ]

    winners = [r for r in rows if r["upnl"] > 0]
    losers = [r for r in rows if r["upnl"] < 0]
    if winners:
        b = max(winners, key=lambda r: r["upnl"])
        lines.append(f"🏆 กำไรสูงสุด: {b['asset']} {money(b['upnl'], True)} ({pct(b['pct'])})")
    else:
        lines.append("🏆 กำไรสูงสุด: ไม่มีเหรียญที่กำไร")
    if losers:
        w = min(losers, key=lambda r: r["upnl"])
        lines.append(f"🔻 ขาดทุนสูงสุด: {w['asset']} {money(w['upnl'], True)} ({pct(w['pct'])})")
    else:
        lines.append("🔻 ขาดทุนสูงสุด: ไม่มีเหรียญที่ขาดทุน")

    lines += ["", f"🔄 วันนี้เทรด {n_trades} รายการ" if n_trades else "🔄 วันนี้ไม่มีการเทรด"]
    return "\n".join(lines)


def send_telegram(text):
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    if not r.ok:
        sys.exit(f"ส่ง Telegram ไม่สำเร็จ: {r.text}")


if __name__ == "__main__":
    msg = build_message(load_sim())
    print(msg)
    send_telegram(msg)
