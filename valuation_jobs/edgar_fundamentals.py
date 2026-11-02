# edgar_fundamentals.py
import os
import time
from collections import defaultdict
from datetime import date

import requests
from supabase import create_client

UA = {"User-Agent": "Nobodi Valuation your-email@example.com"}  # ต้องมีอีเมลจริง
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A"}

FLOW_TAGS = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
    ],
    "net_income": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
    "op_income": ["OperatingIncomeLoss"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
           "DepreciationAndAmortization", "Depreciation"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}
INSTANT_TAGS = {
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "debt": ["LongTermDebt", "LongTermDebtNoncurrent", "DebtInstrumentCarryingAmount"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}
SHARES_TAGS = ["WeightedAverageNumberOfDilutedSharesOutstanding"]


def _d(s):
    return date.fromisoformat(s)


def _days(a, b):
    return (_d(b) - _d(a)).days


def collect(gaap, tags, unit="USD", instant=False):
    """รวมค่าจากหลาย tag ตามลำดับความสำคัญ โดยเลือกแยกทีละงวด ไม่ใช่เลือกครั้งเดียวทั้งบริษัท
    เพราะบริษัทเปลี่ยน tag กลางทางได้ เช่น SalesRevenueNet -> RevenueFromContract... ช่วงปี 2018"""
    out = {}
    for tag in tags:
        for it in gaap.get(tag, {}).get("units", {}).get(unit, []):
            if it.get("form") not in FORMS:
                continue
            if instant == ("start" in it):  # instant ต้องไม่มี start, duration ต้องมี
                continue
            key = it["end"] if instant else (it["start"], it["end"])
            cur = out.get(key)
            if cur and cur["tag"] != tag:
                continue  # tag ที่สำคัญกว่ามีค่าของงวดนี้แล้ว
            if cur is None:
                out[key] = {"val": it["val"], "first": it["filed"], "last": it["filed"], "tag": tag}
            else:
                cur["first"] = min(cur["first"], it["filed"])  # วันที่ตลาดเห็นครั้งแรก
                if it["filed"] >= cur["last"]:                 # ใช้ค่าจากฉบับแก้ไขล่าสุด
                    cur["val"], cur["last"] = it["val"], it["filed"]
    return out


def to_quarterly(dur):
    """แปลงข้อมูลแบบช่วงเวลาให้เป็นรายไตรมาส: ใช้ค่า 3 เดือนตรง ๆ ถ้ามี
    ถ้าไม่มี ใช้ YTD หรือยอดทั้งปี ลบ YTD ที่เริ่มวันเดียวกันแต่สั้นกว่าหนึ่งไตรมาส"""
    by_start = defaultdict(list)
    for (s, e), v in dur.items():
        by_start[s].append((e, v))

    q = {}
    for (s, e), v in dur.items():
        if 80 <= _days(s, e) <= 100:
            q[e] = {"val": v["val"], "avail": v["first"]}

    for (s, e), v in dur.items():
        if e in q or not (170 <= _days(s, e) <= 380):
            continue
        for e2, v2 in by_start[s]:
            if 80 <= _days(e2, e) <= 100:
                q[e] = {"val": v["val"] - v2["val"], "avail": max(v["first"], v2["first"])}
                break
    return dict(sorted(q.items()))


def ttm(q):
    ends = list(q)
    out = {}
    for i in range(3, len(ends)):
        w = ends[i - 3 : i + 1]
        if _days(w[0], w[-1]) > 300:  # มีไตรมาสหายกลางทาง ข้ามไป
            continue
        out[w[-1]] = {
            "val": sum(q[e]["val"] for e in w),
            "avail": max(q[e]["avail"] for e in w),
        }
    return out


def shares_at(dur, end):
    """จำนวนหุ้นถัวเฉลี่ยแบบ diluted ใช้งวดที่สั้นที่สุดที่จบวันนั้น (ไตรมาสก่อน ถ้าไม่มีใช้ทั้งปี)"""
    cands = [(_days(s, e), v["val"]) for (s, e), v in dur.items() if e == end]
    return min(cands)[1] if cands else None


def build_rows(ticker, facts):
    gaap = facts.get("us-gaap")
    if not gaap:
        return []  # ยื่นแบบ IFRS (20-F) ให้ไปใช้ข้อมูลจาก FMP

    q = {k: to_quarterly(collect(gaap, tags)) for k, tags in FLOW_TAGS.items()}
    t = {k: ttm(v) for k, v in q.items()}
    inst = {k: collect(gaap, tags, instant=True) for k, tags in INSTANT_TAGS.items()}
    shares = collect(gaap, SHARES_TAGS, unit="shares")

    def val(d, e):
        return d[e]["val"] if e in d else None

    rows = []
    for end in t["net_income"]:
        ni = val(t["net_income"], end)
        cfo, capex = val(t["cfo"], end), val(t["capex"], end)
        op, da = val(t["op_income"], end), val(t["da"], end)
        sh = shares_at(shares, end)
        avail = max(d[end]["avail"] for d in (t["net_income"], t["revenue"], t["cfo"]) if end in d)

        rows.append({
            "ticker": ticker,
            "period_end": end,
            "available_date": avail,
            "revenue_q": val(q["revenue"], end),
            "net_income_q": val(q["net_income"], end),
            "revenue_ttm": val(t["revenue"], end),
            "net_income_ttm": ni,
            "op_income_ttm": op,
            "ebitda_ttm": op + da if op is not None and da is not None else None,
            "cfo_ttm": cfo,
            "capex_ttm": capex,
            "fcf_ttm": cfo - capex if cfo is not None and capex is not None else None,
            "shares_diluted": sh,
            "eps_ttm": ni / sh if ni is not None and sh else None,
            "cash": val(inst["cash"], end),
            "total_debt": val(inst["debt"], end),
            "equity": val(inst["equity"], end),
            "source": "sec",
        })
    return rows


# ---------- ดึงข้อมูลและบันทึก ----------

def load_cik_map():
    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=UA, timeout=30)
    r.raise_for_status()
    return {v["ticker"]: str(v["cik_str"]).zfill(10) for v in r.json().values()}


def fetch_facts(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    for attempt in range(3):
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code == 404:
            return None
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(5 * 2 ** attempt)
            continue
        r.raise_for_status()
        return r.json().get("facts", {})
    return None


def run():
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    tickers = [r["ticker"] for r in sb.table("companies").select("ticker")
               .eq("filer_type", "us-gaap").execute().data]
    ciks = load_cik_map()
    failed = []

    for tk in tickers:
        cik = ciks.get(tk.replace(".", "-"))  # BRK.B -> BRK-B ตามรูปแบบของ SEC
        if not cik:
            failed.append((tk, "no_cik"))
            continue
        try:
            facts = fetch_facts(cik)
            rows = build_rows(tk, facts) if facts else []
        except Exception as e:
            failed.append((tk, repr(e)))
            continue
        finally:
            time.sleep(0.15)  # ต่ำกว่าเพดาน 10 request ต่อวินาที

        if not rows:
            failed.append((tk, "no_data"))
            continue
        for i in range(0, len(rows), 500):
            sb.table("fundamentals_quarterly").upsert(
                rows[i : i + 500], on_conflict="ticker,period_end"
            ).execute()

    print(f"done: {len(tickers) - len(failed)}/{len(tickers)}")
    for f in failed:
        print("FAILED", *f)


if __name__ == "__main__":
    run()
