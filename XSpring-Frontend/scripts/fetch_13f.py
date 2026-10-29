#!/usr/bin/env python3
"""ดึงพอร์ตนักลงทุนชื่อดังจาก SEC 13F-HR (EDGAR) แล้วเขียนเป็น public/data/superinvestors.json

ใช้ได้แค่ standard library ต้องมี Python 3.10+
ตั้ง SEC_USER_AGENT เป็น "ชื่อแอป อีเมลติดต่อ" (SEC บังคับให้ระบุ)
  python scripts/fetch_13f.py            # ดึงทุกคน
  python scripts/fetch_13f.py --check    # เช็กว่า CIK แต่ละอันตรงชื่อกองทุนไหม (ไม่ดึงพอร์ต)
"""
import json, os, sys, time, urllib.request, urllib.error, xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "public" / "data" / "superinvestors.json"
CACHE = HERE / "cusip_cache.json"
UA = os.environ.get("SEC_USER_AGENT") or "XSpring-Research contact@example.com"
TOP_FOR_TICKER = 40      # แปลง CUSIP -> ticker เฉพาะ 40 ตัวใหญ่สุดของแต่ละกอง
MAX_SOLD = 10

# (id, ชื่อคน, ชื่อกองทุน, CIK) -- CIK บางตัวจำจากความรู้ ต้องรัน --check ยืนยันก่อน
INVESTORS = [
    ("buffett",      "Warren Buffett",     "Berkshire Hathaway",           1067983),
    ("dalio",        "Ray Dalio",          "Bridgewater Associates",       1350694),
    ("burry",        "Michael Burry",      "Scion Asset Management",       1649339),
    ("ackman",       "Bill Ackman",        "Pershing Square Capital",      1336528),
    ("soros",        "George Soros",       "Soros Fund Management",        1029160),
    ("druckenmiller","Stan Druckenmiller", "Duquesne Family Office",       1536411),
    ("tepper",       "David Tepper",       "Appaloosa",                    1656456),
    ("loeb",         "Dan Loeb",           "Third Point",                  1040273),
    ("icahn",        "Carl Icahn",         "Icahn Carl C",                 921669),
    ("einhorn",      "David Einhorn",      "Greenlight Capital",           1079114),
    ("klarman",      "Seth Klarman",       "Baupost Group",                1061768),
    ("pabrai",       "Mohnish Pabrai",     "Dalal Street LLC",             1549575),
    ("lili",         "Li Lu",              "Himalaya Capital Management",  1709323),
    ("marks",        "Howard Marks",       "Oaktree Capital Management",   1403528),
    ("wood",         "Cathie Wood",        "ARK Investment Management",    1697748),
    ("munger",       "Charlie Munger",     "Daily Journal Corp",           783412),
    ("berkowitz",    "Bruce Berkowitz",    "Fairholme Capital",            1056831),
    ("akre",         "Chuck Akre",         "Akre Capital Management",      1112520),
    ("peltz",        "Nelson Peltz",       "Trian Fund Management",        1345471),
    ("coleman",      "Chase Coleman",      "Tiger Global Management",      1167483),
    ("laffont",      "Philippe Laffont",   "Coatue Management",            1135730),
    ("simons",       "Jim Simons (RenTech)","Renaissance Technologies",    1037389),
    ("griffin",      "Ken Griffin",        "Citadel Advisors",             1423053),
    ("singer",       "Paul Singer",        "Elliott Investment Management",1791786),
]

_last = 0.0
def http(url: str, data: bytes | None = None, headers: dict | None = None):
    global _last
    for attempt in range(4):
        wait = 0.2 - (time.time() - _last)
        if wait > 0: time.sleep(wait)          # SEC จำกัด ~10 req/s
        _last = time.time()
        req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Encoding": "identity", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1)); continue
            raise
    raise RuntimeError("unreachable")

def get_json(url): return json.loads(http(url))

def latest_13f(cik: int, n: int = 2):
    sub = get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    rec = sub["filings"]["recent"]
    out = []
    for i, form in enumerate(rec["form"]):
        if form == "13F-HR":
            out.append({"acc": rec["accessionNumber"][i], "filed": rec["filingDate"][i], "period": rec["reportDate"][i]})
            if len(out) == n: break
    return sub.get("name", ""), out

def _tag(el): return el.tag.rsplit("}", 1)[-1]

def parse_info_table(xml_bytes: bytes, filed: str):
    """คืน dict cusip -> {name, value(USD), shares}. ข้าม option และ principal amount"""
    root = ET.fromstring(xml_bytes)
    mult = 1 if filed >= "2023-01-03" else 1000   # ก่อนปี 2023 ยื่นหน่วยพันดอลลาร์
    agg: dict[str, dict] = {}
    for it in root.iter():
        if _tag(it) != "infoTable": continue
        f = {}
        for c in it.iter():
            f[_tag(c)] = (c.text or "").strip()
        if f.get("putCall"): continue
        if f.get("sshPrnamtType", "SH") != "SH": continue
        cusip = f.get("cusip", "").upper()
        if not cusip: continue
        try:
            val = float(f.get("value", "0")) * mult
            sh = float(f.get("sshPrnamt", "0"))
        except ValueError:
            continue
        a = agg.setdefault(cusip, {"name": f.get("nameOfIssuer", ""), "value": 0.0, "shares": 0.0})
        a["value"] += val; a["shares"] += sh
    return agg

def load_holdings(cik: int, filing: dict):
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{filing['acc'].replace('-', '')}"
    items = get_json(base + "/index.json")["directory"]["item"]
    xmls = [i["name"] for i in items if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower()]
    xmls.sort(key=lambda n: 0 if "table" in n.lower() else 1)
    for name in xmls:
        agg = parse_info_table(http(f"{base}/{name}"), filing["filed"])
        if agg: return agg
    return {}

def load_cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}

def map_tickers(cusips: list[str], cache: dict):
    """OpenFIGI (ฟรี ไม่ต้องมี key: 10 รายการ/ครั้ง, 25 ครั้ง/6 วิ). ใส่ OPENFIGI_KEY ถ้ามีเพื่อเร็วขึ้น"""
    todo = [c for c in cusips if c not in cache]
    hdr = {"Content-Type": "application/json"}
    if os.environ.get("OPENFIGI_KEY"): hdr["X-OPENFIGI-APIKEY"] = os.environ["OPENFIGI_KEY"]
    for i in range(0, len(todo), 10):
        chunk = todo[i:i + 10]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]).encode()
        try:
            res = json.loads(http("https://api.openfigi.com/v3/mapping", body, hdr))
        except Exception as e:
            print("  openfigi error:", e, file=sys.stderr); break
        for c, r in zip(chunk, res):
            d = (r.get("data") or [None])[0]
            cache[c] = d["ticker"] if d else ""
        time.sleep(0.5)

def build(inv, cache):
    iid, person, fund, cik = inv
    ename, filings = latest_13f(cik)
    if not filings: raise RuntimeError("ไม่พบ 13F-HR")
    cur_f = filings[0]
    cur = load_holdings(cik, cur_f)
    prev = load_holdings(cik, filings[1]) if len(filings) > 1 else {}
    total = sum(h["value"] for h in cur.values()) or 1.0
    ranked = sorted(cur.items(), key=lambda kv: -kv[1]["value"])
    sold = sorted(((c, h) for c, h in prev.items() if c not in cur), key=lambda kv: -kv[1]["value"])[:MAX_SOLD]
    map_tickers([c for c, _ in ranked[:TOP_FOR_TICKER]] + [c for c, _ in sold], cache)
    rows = []
    for c, h in ranked:
        p = prev.get(c)
        if not prev: change, pct = "", None
        elif not p: change, pct = "new", None
        else:
            pct = (h["shares"] - p["shares"]) / p["shares"] if p["shares"] else None
            change = "added" if pct and pct > 0.01 else "reduced" if pct and pct < -0.01 else "same"
        rows.append({"cusip": c, "ticker": cache.get(c, ""), "name": h["name"], "value": round(h["value"]),
                     "shares": round(h["shares"]), "weight": round(h["value"] / total, 5),
                     "change": change, "change_pct": None if pct is None else round(pct, 4)})
    return {"id": iid, "person": person, "fund": fund, "cik": cik, "edgar_name": ename,
            "period": cur_f["period"], "filed": cur_f["filed"], "total_value": round(total),
            "holdings_count": len(rows), "holdings": rows[:60],
            "sold": [{"cusip": c, "ticker": cache.get(c, ""), "name": h["name"], "value": round(h["value"])} for c, h in sold]}

def main():
    if "--check" in sys.argv:
        for iid, person, fund, cik in INVESTORS:
            try:
                name, f = latest_13f(cik, 1)
                print(f"{iid:14} CIK {cik:<8} EDGAR={name!r:45} คาดว่า={fund!r}  13F ล่าสุด={f[0]['period'] if f else 'ไม่มี'}")
            except Exception as e:
                print(f"{iid:14} CIK {cik:<8} ERROR {e}")
        return
    cache = load_cache(); out = []
    for inv in INVESTORS:
        try:
            print("ดึง", inv[1], "...", flush=True)
            out.append(build(inv, cache))
        except Exception as e:
            print("  ข้าม", inv[1], "->", e, file=sys.stderr)
    CACHE.write_text(json.dumps(cache, indent=0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "investors": out}, ensure_ascii=False))
    print(f"เขียน {OUT} ({len(out)}/{len(INVESTORS)} กอง)")

if __name__ == "__main__":
    main()
