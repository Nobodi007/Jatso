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

    url = f"https://api.bitkub.com/api/market/ticker?sym={asset}_THB"

    response = requests.get(
        url,
        timeout=10,
        headers={
            "User-Agent": "XSpring-Dealer-Suite/1.0"
        },
    )

    response.raise_for_status()

    data = response.json()

    key = f"{asset}_THB"

    if key not in data:
        return {
            "error": f"ไม่พบราคา {asset}/THB",
            "asset": asset,
        }

    ticker = data[key]

    return {
        "asset": asset,
        "symbol": f"{asset}/THB",
        "price": ticker.get("last"),
        "high_24h": ticker.get("high24hr"),
        "low_24h": ticker.get("low24hr"),
        "volume_24h": ticker.get("baseVolume"),
        "quote_volume_24h": ticker.get("quoteVolume"),
        "change_24h": ticker.get("percentChange"),
    }
