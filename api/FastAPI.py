from fastapi import FastAPI

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