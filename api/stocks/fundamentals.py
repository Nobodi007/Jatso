import asyncio
import os
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Query

from . import providers as p
from .cache import ProviderError, RateLimited, cached, take_quota
from .router import get_quote, guard, norm, profile

router = APIRouter(prefix="/api/stocks", tags=["stocks-fundamentals"])

SEC_UA = os.getenv("SEC_USER_AGENT", "")
FMP_KEY = os.getenv("FMP_KEY", "")
FMP = "https://financialmodelingprep.com/stable"


# =====================================================
# Helpers
# =====================================================
def _date_range(frm: date | None, to: date | None, max_days: int = 31):
    frm = frm or date.today()
    to = to or frm + timedelta(days=7)
    if to < frm or (to - frm).days > max_days:
        raise HTTPException(400, "invalid_range")
    return frm, to


async def _fmp(path: str, **params):
    if not FMP_KEY:
        raise ProviderError("FMP_KEY not set")
    if not take_quota("fmp", 240, 86400):
        raise RateLimited("fmp")
    data = await p._get_json(f"{FMP}{path}", {**params, "apikey": FMP_KEY})
    if isinstance(data, dict) and ("Error Message" in data or "error" in data):
        raise ProviderError(str(data))
    return data


async def _sec_get(url: str):
    if not SEC_UA:
        raise ProviderError("SEC_USER_AGENT not set")
    if not take_quota("sec", 8, 1):  # SEC อนุญาตไม่เกิน 10 ครั้ง/วินาที
        raise RateLimited("sec")
    try:
        resp = await p._client.get(url, headers={"User-Agent": SEC_UA}, timeout=30)
    except httpx.HTTPError as e:
        raise ProviderError(str(e)) from e
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RateLimited("sec")
    if resp.status_code >= 400:
        raise ProviderError(f"sec -> {resp.status_code}")
    return resp.json()


# =====================================================
# อัตราส่วนการเงิน (Finnhub)
# =====================================================
def _pick(m: dict, *keys):
    for k in keys:
        if m.get(k) is not None:
            return m[k]
    return None


async def get_metrics(s: str) -> dict:
    d = await guard(cached(
        f"metric:{s}", 86400,
        lambda: p.finnhub("/stock/metric", symbol=s, metric="all"),
    ))
    m = (d or {}).get("metric") or {}
    if not m:
        raise HTTPException(404, "symbol_not_found")
    # ค่าที่เป็น % ส่งมาเป็นตัวเลขเปอร์เซ็นต์แล้ว เช่น roe = 150.2 คือ 150.2%
    return {
        "symbol": s,
        "pe": _pick(m, "peTTM", "peBasicExclExtraTTM", "peExclExtraTTM"),
        "pb": _pick(m, "pbQuarterly", "pbAnnual"),
        "ps": _pick(m, "psTTM", "psAnnual"),
        "roe": _pick(m, "roeTTM", "roeRfy"),
        "roa": _pick(m, "roaTTM", "roaRfy"),
        "grossMargin": _pick(m, "grossMarginTTM", "grossMarginAnnual"),
        "netMargin": _pick(m, "netProfitMarginTTM", "netProfitMarginAnnual"),
        "debtToEquity": _pick(m, "totalDebt/totalEquityQuarterly", "totalDebt/totalEquityAnnual"),
        "currentRatio": _pick(m, "currentRatioQuarterly", "currentRatioAnnual"),
        "dividendYield": _pick(m, "currentDividendYieldTTM", "dividendYieldIndicatedAnnual"),
        "eps": _pick(m, "epsTTM", "epsExclExtraItemsTTM"),
        "revenueGrowth": _pick(m, "revenueGrowthTTMYoy", "revenueGrowthQuarterlyYoy"),
        "beta": m.get("beta"),
        "high52w": m.get("52WeekHigh"),
        "low52w": m.get("52WeekLow"),
    }


# =====================================================
# งบการเงิน (SEC EDGAR)
# =====================================================
CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "grossProfit": ["GrossProfit"],
    "operatingIncome": ["OperatingIncomeLoss"],
    "netIncome": ["NetIncomeLoss"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "totalAssets": ["Assets"],
    "totalLiabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "longTermDebt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "operatingCashFlow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "dividendsPaid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
}
INSTANT = {"totalAssets", "totalLiabilities", "equity", "cash", "longTermDebt"}  # ตัวเลขงบดุล


async def _cik_map() -> dict:
    async def fetch():
        d = await _sec_get("https://www.sec.gov/files/company_tickers.json")
        return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in d.values()}
    return await cached("sec:tickers", 86400, fetch)


def _annual_values(facts: dict, names: list[str], instant: bool) -> dict:
    merged: dict[str, float] = {}
    for name in names:
        units = (facts.get(name) or {}).get("units", {})
        rows = units.get("USD") or units.get("USD/shares") or []
        per: dict[str, tuple] = {}
        for x in rows:
            if x.get("form") not in ("10-K", "10-K/A"):
                continue
            end = x.get("end")
            if not instant:
                start = x.get("start")
                if not start:
                    continue
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                if not 350 <= days <= 380:  # เอาเฉพาะตัวเลขทั้งปี ไม่เอารายไตรมาส
                    continue
            filed = x.get("filed", "")
            if end not in per or filed > per[end][1]:  # ถ้ามีงบแก้ไข ใช้ฉบับล่าสุด
                per[end] = (x["val"], filed)
        for end, (val, _) in per.items():
            merged.setdefault(end, val)  # concept แรกในรายการได้สิทธิ์ก่อน
    return merged


async def get_financials(s: str, years: int) -> dict:
    cik = (await guard(_cik_map())).get(s.replace(".", "-"))
    if not cik:
        raise HTTPException(404, "not_in_sec")  # เช่น หุ้นต่างชาติที่ยื่น 20-F

    async def fetch():
        d = await _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        if not d:
            return {"symbol": s, "name": None, "annual": []}
        facts = d.get("facts", {}).get("us-gaap", {})
        cols = {k: _annual_values(facts, v, k in INSTANT) for k, v in CONCEPTS.items()}
        ends = sorted(set(cols["revenue"]) | set(cols["netIncome"]))[-10:]
        rows = []
        for end in ends:
            row = {"fiscalYearEnd": end, "year": int(end[:4])}
            for k in CONCEPTS:
                row[k] = cols[k].get(end)
            ocf, capex = row["operatingCashFlow"], row["capex"]
            row["freeCashFlow"] = ocf - capex if ocf is not None and capex is not None else None
            rows.append(row)
        return {"symbol": s, "name": d.get("entityName"), "currency": "USD", "annual": rows}

    data = await guard(cached(f"fin:{s}", 86400, fetch))
    return {**data, "annual": data["annual"][-years:]}


# =====================================================
# Routes: path ที่เป็นคำตายตัวต้องประกาศก่อน /{symbol}/...
# =====================================================
@router.get("/compare")
async def compare(symbols: str = Query(..., description="เช่น AAPL,MSFT,NVDA")):
    syms = list(dict.fromkeys(norm(x) for x in symbols.split(",") if x.strip()))
    if not 2 <= len(syms) <= 4:
        raise HTTPException(400, "compare_2_to_4")

    async def one(s: str):
        q, pr, m = await asyncio.gather(get_quote(s), profile(s), get_metrics(s))
        return {
            **m,
            "name": pr["name"], "logo": pr["logo"], "industry": pr["industry"],
            "marketCap": pr["marketCap"],
            "price": q["price"], "changePercent": q["changePercent"],
        }

    return await asyncio.gather(*(one(s) for s in syms))


@router.get("/calendar/earnings")
async def earnings_calendar(
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
    symbol: str | None = None,
):
    frm, to = _date_range(frm, to)
    params = {"from": frm.isoformat(), "to": to.isoformat()}
    key = f"earn:{frm}:{to}"
    if symbol:
        params["symbol"] = norm(symbol)
        key += f":{params['symbol']}"
    d = await guard(cached(key, 6 * 3600, lambda: p.finnhub("/calendar/earnings", **params)))
    rows = (d or {}).get("earningsCalendar") or []
    rows.sort(key=lambda x: (x.get("date") or "", -(x.get("revenueEstimate") or 0)))
    return [
        {
            "symbol": x.get("symbol"),
            "date": x.get("date"),
            "hour": x.get("hour"),  # bmo = ก่อนตลาดเปิด, amc = หลังตลาดปิด
            "quarter": x.get("quarter"),
            "year": x.get("year"),
            "epsEstimate": x.get("epsEstimate"),
            "epsActual": x.get("epsActual"),
            "revenueEstimate": x.get("revenueEstimate"),
            "revenueActual": x.get("revenueActual"),
        }
        for x in rows
    ]


DIV_KEYS = ("symbol", "date", "recordDate", "paymentDate", "declarationDate",
            "dividend", "adjDividend", "yield", "frequency")


@router.get("/calendar/dividends")
async def dividend_calendar(
    frm: date | None = Query(None, alias="from"),
    to: date | None = None,
):
    frm, to = _date_range(frm, to)
    rows = await guard(cached(
        f"div:{frm}:{to}", 6 * 3600,
        lambda: _fmp("/dividends-calendar", **{"from": frm.isoformat(), "to": to.isoformat()}),
    ))
    # date = วันขึ้นเครื่องหมาย XD
    return [
        {k: x.get(k) for k in DIV_KEYS}
        for x in rows or []
        if "." not in (x.get("symbol") or "")  # เอาเฉพาะหุ้นอเมริกา
    ]


@router.get("/{symbol}/metrics")
async def metrics(symbol: str):
    return await get_metrics(norm(symbol))


@router.get("/{symbol}/financials")
async def financials(symbol: str, years: int = Query(5, ge=1, le=10)):
    return await get_financials(norm(symbol), years)


@router.get("/{symbol}/dividends")
async def dividends(symbol: str):
    s = norm(symbol)
    rows = await guard(cached(f"divhist:{s}", 86400, lambda: _fmp("/dividends", symbol=s)))
    return [{k: x.get(k) for k in DIV_KEYS} for x in (rows or [])[:40]]
