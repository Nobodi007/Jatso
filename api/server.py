from fastapi import FastAPI
import requests

app = FastAPI(
    title="XSpring Dealer Suite API",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "service": "XSpring Dealer Suite API",
        "status": "online",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
    }


@app.get("/api/market/{asset}")
def market(asset: str):
    asset = asset.upper()
    symbol = f"{asset}_THB"

    url = "https://api.bitkub.com/api/v3/market/ticker"

    response = requests.get(
        url,
        params={"sym": symbol.lower()},
        timeout=10,
        headers={
            "Accept": "application/json",
            "User-Agent": "XSpring-Dealer-Suite/1.0",
        },
    )

    response.raise_for_status()

    data = response.json()

    # Bitkub V3 returns a list
    if not isinstance(data, list) or len(data) == 0:
        return {
            "error": f"ไม่พบราคา {asset}/THB",
            "asset": asset,
            "raw": data,
        }

    ticker = data[0]

    return {
        "asset": asset,
        "symbol": ticker.get("symbol", symbol),
        "price": float(ticker["last"]),
        "high_24h": float(ticker["high_24_hr"]),
        "low_24h": float(ticker["low_24_hr"]),
        "volume_24h": float(ticker["base_volume"]),
        "quote_volume_24h": float(ticker["quote_volume"]),
        "change_24h": float(ticker["percent_change"]),
    }
