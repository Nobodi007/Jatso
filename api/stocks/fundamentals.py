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
# รองรับ 10-K (บริษัทอเมริกา) และ 20-F/40-F (บริษัทต่างชาติ)
# รองรับ us-gaap และ ifrs-full และใช้สกุลเงินที่บริษัทรายงานจริง
# =====================================================
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}

# ลำดับใน list = ลำดับ fallback (tag แรกได้สิทธิ์ก่อน tag หลังเติมปีที่ขาด)
CONCEPTS = {
    # ---- งบกำไรขาดทุน ----
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "costOfRevenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "grossProfit": ["GrossProfit"],
    "researchAndDevelopment": ["ResearchAndDevelopmentExpense"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "operatingExpenses": ["OperatingExpenses", "CostsAndExpenses"],
    "operatingIncome": ["OperatingIncomeLoss"],
    "interestExpense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "incomeBeforeTax": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "incomeTax": ["IncomeTaxExpenseBenefit"],
    "netIncome": ["NetIncomeLoss", "ProfitLoss"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "dilutedShares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    # ---- งบดุล ----
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "shortTermInvestments": [
        "ShortTermInvestments", "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    ],
    "receivables": ["AccountsReceivableNetCurrent"],
    "inventory": ["InventoryNet"],
    "currentAssets": ["AssetsCurrent"],
    "ppe": ["PropertyPlantAndEquipmentNet"],
    "goodwill": ["Goodwill"],
    "totalAssets": ["Assets"],
    "currentLiabilities": ["LiabilitiesCurrent"],
    "shortTermDebt": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"],
    "longTermDebt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "totalLiabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    # ---- งบกระแสเงินสด ----
    "depreciation": [
        "DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation",
    ],
    "sbc": ["ShareBasedCompensation"],
    "operatingCashFlow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "investingCashFlow": ["NetCashProvidedByUsedInInvestingActivities"],
    "financingCashFlow": ["NetCashProvidedByUsedInFinancingActivities"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "dividendsPaid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
}

# ชื่อ tag ชุด IFRS (บริษัทที่ยื่น 20-F ด้วย IFRS เช่น ASML, NVO)
# หมายเหตุ: บริษัทบางแห่งใช้ tag ของตัวเอง (extension) สำหรับบางรายการ ซึ่งจะขึ้น "–"
# ใช้ /{symbol}/financials/debug ดูว่าบริษัทนั้นใช้ tag ชื่ออะไร แล้วเพิ่มในลิสต์ด้านล่าง
IFRS_CONCEPTS = {k: [] for k in CONCEPTS}
IFRS_CONCEPTS.update({
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "costOfRevenue": ["CostOfSales"],
    "grossProfit": ["GrossProfit"],
    "researchAndDevelopment": ["ResearchAndDevelopmentExpense"],
    "sga": ["SellingGeneralAndAdministrativeExpense", "AdministrativeExpense"],
    "operatingIncome": ["ProfitLossFromOperatingActivities"],
    "interestExpense": ["InterestExpense", "FinanceCosts"],
    "incomeBeforeTax": ["ProfitLossBeforeTax"],
    "incomeTax": ["IncomeTaxExpenseContinuingOperations"],
    "netIncome": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "eps": ["DilutedEarningsLossPerShare", "BasicEarningsLossPerShare"],
    "dilutedShares": ["AdjustedWeightedAverageShares", "WeightedAverageShares"],
    "cash": ["CashAndCashEquivalents"],
    "receivables": ["CurrentTradeReceivables", "TradeAndOtherCurrentReceivables"],
    "inventory": ["Inventories"],
    "currentAssets": ["CurrentAssets"],
    "ppe": ["PropertyPlantAndEquipment"],
    "goodwill": ["Goodwill"],
    "totalAssets": ["Assets"],
    "currentLiabilities": ["CurrentLiabilities"],
    "shortTermDebt": ["CurrentBorrowings", "CurrentPortionOfLongtermBorrowings", "ShorttermBorrowings"],
    "longTermDebt": ["LongtermBorrowings", "NoncurrentBorrowings"],
    "totalLiabilities": ["Liabilities"],
    "equity": ["EquityAttributableToOwnersOfParent", "Equity"],
    "depreciation": ["DepreciationAndAmortisationExpense", "AdjustmentsForDepreciationAndAmortisationExpense"],
    "sbc": ["AdjustmentsForSharebasedPayments"],
    "operatingCashFlow": ["CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "investingCashFlow": ["CashFlowsFromUsedInInvestingActivities"],
    "financingCashFlow": ["CashFlowsFromUsedInFinancingActivities"],
    "buybacks": ["PaymentsToAcquireOrRedeemEntitysShares"],
    "dividendsPaid": ["DividendsPaidClassifiedAsFinancingActivities"],
})

# บริษัทบางแห่งรายงานรายจ่ายเป็นค่าลบ ให้เป็นบวกเสมอเพื่อให้สูตร FCF ถูก
ABS_KEYS = {"capex", "buybacks", "dividendsPaid"}

# ตัวเลขงบดุล (ณ วันที่ ไม่มี start date)
INSTANT = {
    "cash", "shortTermInvestments", "receivables", "inventory", "currentAssets", "ppe",
    "goodwill", "totalAssets", "currentLiabilities", "shortTermDebt", "longTermDebt",
    "totalLiabilities", "equity",
}

# จัดกลุ่มให้ฝั่งหน้าเว็บใช้เรนเดอร์ตาราง (key = แท็บย่อยใน Statements)
STATEMENTS = {
    "income": [
        "revenue", "costOfRevenue", "grossProfit", "researchAndDevelopment", "sga",
        "operatingExpenses", "operatingIncome", "interestExpense", "incomeBeforeTax",
        "incomeTax", "netIncome", "eps", "dilutedShares",
    ],
    "balance": [
        "cash", "shortTermInvestments", "receivables", "inventory", "currentAssets", "ppe",
        "goodwill", "totalAssets", "currentLiabilities", "shortTermDebt", "longTermDebt",
        "totalDebt", "totalLiabilities", "equity", "netDebt",
    ],
    "cashflow": [
        "netIncome", "depreciation", "sbc", "operatingCashFlow", "capex", "freeCashFlow",
        "investingCashFlow", "financingCashFlow", "buybacks", "dividendsPaid",
    ],
}


async def _cik_map() -> dict:
    async def fetch():
        d = await _sec_get("https://www.sec.gov/files/company_tickers.json")
        return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in d.values()}
    return await cached("sec:tickers", 86400, fetch)


def _kind(key: str) -> str:
    return "pershare" if key == "eps" else "shares" if key == "dilutedShares" else "money"


def _units_for(units: dict, kind: str, cur: str) -> list:
    """เลือกชุดตัวเลขตามชนิด: เงิน (ตามสกุลที่บริษัทรายงาน) / ต่อหุ้น / จำนวนหุ้น"""
    if kind == "shares":
        return units.get("shares") or []
    if kind == "pershare":
        return units.get(f"{cur}/shares") or next((v for k, v in units.items() if k.endswith("/shares")), [])
    return units.get(cur) or []


def _detect_currency(facts: dict, concepts: dict) -> str | None:
    """สกุลเงินที่บริษัทใช้รายงานงบ: เลือกสกุลที่มีข้อมูลรายปีมากสุดจาก concept หลัก"""
    score: dict[str, int] = {}
    for key in ("revenue", "netIncome", "totalAssets"):
        for name in concepts.get(key, []):
            for unit, rows in ((facts.get(name) or {}).get("units") or {}).items():
                if "/" in unit or unit in ("shares", "pure"):
                    continue
                score[unit] = score.get(unit, 0) + sum(1 for x in rows if x.get("form") in ANNUAL_FORMS)
    return max(score, key=score.get) if score else None


def _annual_values(facts: dict, names: list[str], instant: bool, kind: str, cur: str) -> dict:
    merged: dict[str, float] = {}
    for name in names:
        rows = _units_for((facts.get(name) or {}).get("units", {}), kind, cur)
        per: dict[str, tuple] = {}
        for x in rows:
            if x.get("form") not in ANNUAL_FORMS:
                continue
            end = x.get("end")
            if not end:
                continue
            if not instant:
                start = x.get("start")
                if not start:
                    continue
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days
                if not 350 <= days <= 380:  # เอาเฉพาะตัวเลขทั้งปี
                    continue
            filed = x.get("filed", "")
            if end not in per or filed > per[end][1]:  # ถ้ามีงบแก้ไข ใช้ฉบับล่าสุด
                per[end] = (x["val"], filed)
        for end, (val, _) in per.items():
            merged.setdefault(end, val)  # concept แรกในรายการได้สิทธิ์ก่อน
    return merged


def _yoy(cur, prev):
    if cur is None or prev in (None, 0):
        return None
    return (cur - prev) / abs(prev) * 100


def _pct(a, b):
    return a / b * 100 if a is not None and b else None


def _derive(row: dict) -> None:
    """คำนวณบรรทัดที่ SEC ไม่ได้ให้ตรง ๆ"""
    g = row.get
    if g("grossProfit") is None and g("revenue") is not None and g("costOfRevenue") is not None:
        row["grossProfit"] = g("revenue") - g("costOfRevenue")
    if g("operatingCashFlow") is not None and g("capex") is not None:
        row["freeCashFlow"] = g("operatingCashFlow") - g("capex")
    else:
        row["freeCashFlow"] = None
    if g("shortTermDebt") is not None or g("longTermDebt") is not None:
        row["totalDebt"] = (g("shortTermDebt") or 0) + (g("longTermDebt") or 0)
    else:
        row["totalDebt"] = None
    if g("totalLiabilities") is None and g("totalAssets") is not None and g("equity") is not None:
        row["totalLiabilities"] = g("totalAssets") - g("equity")
    liquid = (g("cash") or 0) + (g("shortTermInvestments") or 0) if g("cash") is not None else None
    row["netDebt"] = row["totalDebt"] - liquid if row["totalDebt"] is not None and liquid is not None else None
    # margin (%)
    row["grossMargin"] = _pct(g("grossProfit"), g("revenue"))
    row["operatingMargin"] = _pct(g("operatingIncome"), g("revenue"))
    row["netMargin"] = _pct(g("netIncome"), g("revenue"))
    row["fcfMargin"] = _pct(g("freeCashFlow"), g("revenue"))


GROWTH_KEYS = sorted({k for ks in STATEMENTS.values() for k in ks})


def _add_growth(rows: list[dict]) -> None:
    """% เปลี่ยนจากปีก่อน ใส่ใน row['yoy'][key] (ข้ามถ้าปีไม่ติดกัน เช่น ขาดข้อมูลบางปี)"""
    for i, row in enumerate(rows):
        yoy = {}
        prev = rows[i - 1] if i else None
        if prev:
            gap = (date.fromisoformat(row["fiscalYearEnd"]) - date.fromisoformat(prev["fiscalYearEnd"])).days
            if 300 <= gap <= 430:
                for k in GROWTH_KEYS:
                    yoy[k] = _yoy(row.get(k), prev.get(k))
        row["yoy"] = yoy


def _build_rows(facts: dict, concepts: dict, cur: str) -> list[dict]:
    cols = {k: _annual_values(facts, names, k in INSTANT, _kind(k), cur) for k, names in concepts.items()}
    ends = sorted(set(cols["revenue"]) | set(cols["netIncome"]))  # ย้อนหลังเท่าที่ SEC มี
    rows = []
    for end in ends:
        row = {"fiscalYearEnd": end, "year": int(end[:4])}
        for k in concepts:
            v = cols[k].get(end)
            row[k] = abs(v) if v is not None and k in ABS_KEYS else v
        _derive(row)
        rows.append(row)
    return rows


async def get_financials(s: str, years: int) -> dict:
    cik = (await guard(_cik_map())).get(s.replace(".", "-"))
    if not cik:
        raise HTTPException(404, "not_in_sec")  # ไม่มีใน SEC เลย (เช่น หุ้นที่ไม่ได้ยื่นกับ SEC)

    async def fetch():
        d = await _sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        if not d:
            return {"symbol": s, "name": None, "currency": None, "annual": [], "taxonomy": "unsupported",
                    "statements": STATEMENTS}
        all_facts = d.get("facts") or {}
        # ลอง us-gaap ก่อน (รวมบริษัทต่างชาติที่ใช้ US GAAP เช่น ARM) แล้วค่อย IFRS
        for tax, concepts in (("us-gaap", CONCEPTS), ("ifrs-full", IFRS_CONCEPTS)):
            facts = all_facts.get(tax) or {}
            cur = _detect_currency(facts, concepts) if facts else None
            if not cur:
                continue
            rows = _build_rows(facts, concepts, cur)
            if rows:
                _add_growth(rows)
                return {"symbol": s, "name": d.get("entityName"), "currency": cur, "taxonomy": tax,
                        "annual": rows, "statements": STATEMENTS}
        return {"symbol": s, "name": d.get("entityName"), "currency": None, "annual": [],
                "taxonomy": "unsupported", "statements": STATEMENTS}

    # คีย์ fin2 เพื่อไม่ใช้ผลว่างที่เคยแคชไว้จากโค้ดเวอร์ชันเก่า
    data = await guard(cached(f"fin2:{s}", 86400, fetch))
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


@router.get("/{symbol}/overview")
async def overview(symbol: str):
    s = norm(symbol)
    pr, m = await asyncio.gather(profile(s), get_metrics(s))
    cur = "USD"
    try:
        fin = await get_financials(s, 1)
        last = fin["annual"][-1] if fin["annual"] else {}
        cur = fin.get("currency") or "USD"
    except HTTPException:  # หุ้นที่ไม่อยู่ใน SEC: ยังแสดง key facts ได้ แต่ไม่มี capital structure
        last = {}
    mcap = pr.get("marketCap")  # ตรวจหน่วยให้ตรงกับที่ profile() ส่งมา (Finnhub ปกติเป็นล้านดอลลาร์)
    debt = last.get("totalDebt")
    liquid = (last.get("cash") or 0) + (last.get("shortTermInvestments") or 0) if last.get("cash") is not None else None
    # มูลค่าตลาดเป็น USD ถ้างบเป็นสกุลอื่นห้ามเอามารวมกัน
    ev = mcap + debt - liquid if cur == "USD" and None not in (mcap, debt, liquid) else None
    return {
        "symbol": s,
        "keyFacts": {
            "name": pr.get("name"), "logo": pr.get("logo"), "industry": pr.get("industry"),
            "marketCap": mcap, "pe": m["pe"], "eps": m["eps"], "dividendYield": m["dividendYield"],
            "website": pr.get("weburl") or pr.get("website"),
            "employees": pr.get("employeeTotal") or pr.get("employees"),
            "description": pr.get("description"),
        },
        "capitalStructure": {"marketCap": mcap, "debt": debt, "cash": liquid, "enterpriseValue": ev,
                             "currency": cur, "asOf": last.get("fiscalYearEnd")},
        "latest": last,
    }


@router.get("/{symbol}/financials")
async def financials(symbol: str, years: int = Query(5, ge=1, le=20)):
    return await get_financials(norm(symbol), years)


@router.get("/{symbol}/financials/debug")
async def financials_debug(symbol: str, q: str = ""):
    """ดู tag ที่บริษัทนั้นรายงานจริงใน SEC (เฉพาะที่มีข้อมูลรายปี) ใช้ตอนต้องเพิ่ม tag ให้หุ้นที่ยังขึ้น "–"
    ตัวอย่าง: /api/stocks/ASML/financials/debug?q=borrow"""
    s = norm(symbol)
    cik = (await guard(_cik_map())).get(s.replace(".", "-"))
    if not cik:
        raise HTTPException(404, "not_in_sec")
    d = await guard(_sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"))
    out: dict = {}
    for tax, facts in ((d or {}).get("facts") or {}).items():
        tags = {}
        for name, f in facts.items():
            if q and q.lower() not in name.lower():
                continue
            for unit, rows in (f.get("units") or {}).items():
                n = sum(1 for x in rows if x.get("form") in ANNUAL_FORMS)
                if n:
                    tags[f"{name} [{unit}]"] = n
        out[tax] = dict(sorted(tags.items()))
    return {"symbol": s, "entity": (d or {}).get("entityName"), "annualFactCount": out}


@router.get("/{symbol}/dividends")
async def dividends(symbol: str):
    s = norm(symbol)
    rows = await guard(cached(f"divhist:{s}", 86400, lambda: _fmp("/dividends", symbol=s)))
    return [{k: x.get(k) for k in DIV_KEYS} for x in (rows or [])[:40]]
