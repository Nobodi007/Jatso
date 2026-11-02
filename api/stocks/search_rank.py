"""จัดอันดับผลค้นหาหุ้นสหรัฐ (pure: ไม่เรียกเครือข่าย ทดสอบได้)

ปัญหาของเดิม: ส่งผลของ Finnhub /search ออกไปตรง ๆ ตามลำดับของ Finnhub ซึ่งเป็น fuzzy match
(พิมพ์ "a" แล้วได้ NVDA, MSFT เพราะชื่อบริษัทมีตัว a) และกรองทิ้งทุกตัวที่มีจุด จึงหา BRK.B ไม่เจอ

วิธีนี้: รวมผล Finnhub กับรายการหุ้นยอดนิยมในเครื่อง แล้วให้คะแนนใหม่ตามลำดับความตรง
  1) ตรงกับ ticker เป๊ะ  2) ticker ขึ้นต้นด้วยคำค้น  3) ชื่อบริษัทขึ้นต้นด้วยคำค้น
  4) ทุกคำที่พิมพ์เป็นคำขึ้นต้นของคำในชื่อ  5) ticker/ชื่อมีคำค้นอยู่ข้างใน
แล้วบวกคะแนนความนิยม และลดคะแนน warrant/right/unit/preferred
ถ้าไม่มีตัวไหนตรงเลย (เช่นพิมพ์ผิด "microsft") จะใช้ลำดับ fuzzy เดิมของ Finnhub เป็น fallback
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

MAX_QUERY = 20
EXACT = 5000  # ticker ตรงเป๊ะ ต้องอยู่บนสุดเสมอ ไม่ว่าตัวอื่นจะนิยมแค่ไหน

# ticker ที่รับ: ตัวอักษรล้วน (ต่อด้วย - ได้) หรือหุ้นคลาส A/B เช่น BRK.B BF.B ส่วนตัวที่มีจุดอื่น (VOD.L, 7203.T) คือตลาดอื่น ตัดทิ้ง
_SYMBOL_OK = re.compile(r"^(?:[A-Z][A-Z\-]{0,9}|[A-Z]{1,5}\.[AB])$")
_NON_WORD = re.compile(r"[^0-9a-z\u0e00-\u0e7f]+")
_THAI_MARKS = re.compile(r"[\u0e47-\u0e4c]")  # ็ ่ ้ ๊ ๋ ์  ตัดทิ้งเพื่อให้สะกดต่างกันเล็กน้อยยังตรงกัน

# หุ้นยอดนิยม (ลำดับ = ความนิยม ตัวต้น ๆ ได้คะแนนบวกมากกว่า) และใช้เป็น fallback เมื่อ Finnhub ล่ม/โดน rate limit
POPULAR: dict[str, str] = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation", "NVDA": "NVIDIA Corporation", "AMZN": "Amazon.com Inc",
    "GOOGL": "Alphabet Inc. Class A", "GOOG": "Alphabet Inc. Class C", "META": "Meta Platforms, Inc.", "TSLA": "Tesla Inc",
    "AVGO": "Broadcom Inc", "BRK.B": "Berkshire Hathaway Inc. Class B", "LLY": "Eli Lilly and Company", "JPM": "JPMorgan Chase & Co.",
    "V": "Visa Inc.", "MA": "Mastercard Incorporated", "UNH": "UnitedHealth Group Incorporated", "XOM": "Exxon Mobil Corporation",
    "WMT": "Walmart Inc.", "COST": "Costco Wholesale Corporation", "HD": "The Home Depot, Inc.", "PG": "The Procter & Gamble Company",
    "JNJ": "Johnson & Johnson", "ORCL": "Oracle Corporation", "NFLX": "Netflix, Inc.", "BAC": "Bank of America Corporation",
    "CRM": "Salesforce, Inc.", "AMD": "Advanced Micro Devices, Inc.", "KO": "The Coca-Cola Company", "PEP": "PepsiCo, Inc.",
    "MU": "Micron Technology, Inc.", "INTC": "Intel Corporation", "QCOM": "QUALCOMM Incorporated", "CSCO": "Cisco Systems, Inc.",
    "ADBE": "Adobe Inc.", "DIS": "The Walt Disney Company", "PLTR": "Palantir Technologies Inc.", "UBER": "Uber Technologies, Inc.",
    "TSM": "Taiwan Semiconductor Manufacturing Company Limited", "ASML": "ASML Holding N.V.", "BABA": "Alibaba Group Holding Limited",
    "ARM": "Arm Holdings plc", "SMCI": "Super Micro Computer, Inc.", "COIN": "Coinbase Global, Inc.", "MSTR": "MicroStrategy Incorporated",
    "HOOD": "Robinhood Markets, Inc.", "SOFI": "SoFi Technologies, Inc.", "SHOP": "Shopify Inc.", "SNOW": "Snowflake Inc.",
    "PANW": "Palo Alto Networks, Inc.", "CRWD": "CrowdStrike Holdings, Inc.", "NOW": "ServiceNow, Inc.", "INTU": "Intuit Inc.",
    "AMAT": "Applied Materials, Inc.", "LRCX": "Lam Research Corporation", "KLAC": "KLA Corporation", "TXN": "Texas Instruments Incorporated",
    "IBM": "International Business Machines Corporation", "ACN": "Accenture plc", "DELL": "Dell Technologies Inc.",
    "PYPL": "PayPal Holdings, Inc.", "ABNB": "Airbnb, Inc.", "DASH": "DoorDash, Inc.", "SPOT": "Spotify Technology S.A.",
    "RBLX": "Roblox Corporation", "NKE": "NIKE, Inc.", "SBUX": "Starbucks Corporation", "MCD": "McDonald's Corporation",
    "TGT": "Target Corporation", "LOW": "Lowe's Companies, Inc.", "BA": "The Boeing Company", "CAT": "Caterpillar Inc.",
    "GE": "GE Aerospace", "GS": "The Goldman Sachs Group, Inc.", "MS": "Morgan Stanley", "C": "Citigroup Inc.",
    "WFC": "Wells Fargo & Company", "SCHW": "The Charles Schwab Corporation", "BX": "Blackstone Inc.", "AXP": "American Express Company",
    "T": "AT&T Inc.", "VZ": "Verizon Communications Inc.", "PFE": "Pfizer Inc.", "MRK": "Merck & Co., Inc.",
    "ABBV": "AbbVie Inc.", "TMO": "Thermo Fisher Scientific Inc.", "ABT": "Abbott Laboratories", "NVO": "Novo Nordisk A/S",
    "CVX": "Chevron Corporation", "F": "Ford Motor Company", "GM": "General Motors Company", "RIVN": "Rivian Automotive, Inc.",
    "NIO": "NIO Inc.", "LCID": "Lucid Group, Inc.", "DAL": "Delta Air Lines, Inc.", "UAL": "United Airlines Holdings, Inc.",
    "GME": "GameStop Corp.", "AMC": "AMC Entertainment Holdings, Inc.", "MARA": "MARA Holdings, Inc.", "RIOT": "Riot Platforms, Inc.",
    "SPY": "SPDR S&P 500 ETF Trust", "QQQ": "Invesco QQQ Trust", "DIA": "SPDR Dow Jones Industrial Average ETF Trust",
    "IWM": "iShares Russell 2000 ETF", "VOO": "Vanguard S&P 500 ETF", "VTI": "Vanguard Total Stock Market ETF",
    "VT": "Vanguard Total World Stock ETF", "SCHD": "Schwab U.S. Dividend Equity ETF", "ARKK": "ARK Innovation ETF",
    "XLK": "Technology Select Sector SPDR Fund", "XLF": "Financial Select Sector SPDR Fund", "SMH": "VanEck Semiconductor ETF",
    "SOXX": "iShares Semiconductor ETF", "TLT": "iShares 20+ Year Treasury Bond ETF", "GLD": "SPDR Gold Shares",
    "SLV": "iShares Silver Trust", "TQQQ": "ProShares UltraPro QQQ", "SQQQ": "ProShares UltraPro Short QQQ",
    "SOXL": "Direxion Daily Semiconductor Bull 3X Shares", "JEPI": "JPMorgan Equity Premium Income ETF",
}
_POP_RANK = {s: i for i, s in enumerate(POPULAR)}

# ชื่อเรียกภาษาไทย/ชื่อไทยที่คนพิมพ์ -> ticker (สะกดหลายแบบใส่เป็นหลายคีย์ ระบบตัดวรรณยุกต์ให้เองอยู่แล้ว)
ALIASES: dict[str, str] = {
    "แอปเปิล": "AAPL", "แอปเปิ้ล": "AAPL", "ไอโฟน": "AAPL", "ไมโครซอฟท์": "MSFT", "ไมโครซอฟต์": "MSFT",
    "เอ็นวิเดีย": "NVDA", "เอนวิเดีย": "NVDA", "อเมซอน": "AMZN", "กูเกิล": "GOOGL", "กูเกิ้ล": "GOOGL", "อัลฟาเบท": "GOOGL",
    "เมตา": "META", "เฟซบุ๊ก": "META", "เฟซบุ๊ค": "META", "เฟสบุ๊ก": "META", "เทสลา": "TSLA", "เทสล่า": "TSLA",
    "เน็ตฟลิกซ์": "NFLX", "เน็ตฟลิก": "NFLX", "ไมครอน": "MU", "อินเทล": "INTC", "เอเอ็มดี": "AMD", "ควอลคอมม์": "QCOM",
    "ซิสโก้": "CSCO", "ออราเคิล": "ORCL", "ดิสนีย์": "DIS", "พาลันเทียร์": "PLTR", "อูเบอร์": "UBER", "เพย์พาล": "PYPL",
    "โคคาโคล่า": "KO", "เป๊บซี่": "PEP", "แมคโดนัลด์": "MCD", "สตาร์บัคส์": "SBUX", "ไนกี้": "NKE", "โบอิ้ง": "BA",
    "วอลมาร์ท": "WMT", "คอสต์โก": "COST", "วีซ่า": "V", "มาสเตอร์การ์ด": "MA", "โคอินเบส": "COIN", "อาลีบาบา": "BABA",
    "ทีเอสเอ็มซี": "TSM", "บรอดคอม": "AVGO", "เบิร์กเชียร์": "BRK.B", "ฟอร์ด": "F", "ท็อปทรี": "TQQQ",
}


def _strip_marks(s: str) -> str:
    return _THAI_MARKS.sub("", s)


def norm_text(s: str) -> str:
    return _NON_WORD.sub(" ", _strip_marks(unicodedata.normalize("NFKC", s)).casefold()).strip()


_ALIAS_N = {norm_text(k): v for k, v in ALIASES.items()}


def is_thai(s: str) -> bool:
    return any("\u0e00" <= c <= "\u0e7f" for c in s)


def clean_query(q: str) -> str:
    """ตัด $ นำหน้า ช่องว่างซ้ำ และจำกัดความยาว"""
    q = unicodedata.normalize("NFKC", q or "").strip().lstrip("$").strip()
    return re.sub(r"\s+", " ", q)[:MAX_QUERY]


def provider_query(q: str) -> str | None:
    """คำค้นที่ส่งให้ Finnhub ได้ (ASCII ล้วน) คำค้นภาษาไทยไม่ส่งไป เพื่อไม่เปลือกโควตา 60 ครั้ง/นาที"""
    return q if q and q.isascii() else None


def valid_symbol(sym: str) -> bool:
    return bool(_SYMBOL_OK.match(sym))


def _alias_hits(q_norm: str) -> list[str]:
    if len(q_norm) < 2:
        return []
    out: list[str] = []
    for key, sym in _ALIAS_N.items():
        if key.startswith(q_norm) and sym not in out:
            out.append(sym)
    return out


def _type_penalty(typ: str, exact: bool) -> int:
    t = (typ or "").casefold()
    if any(k in t for k in ("warrant", "right", "unit")):
        return 0 if exact else -600
    if "preferred" in t:
        return 0 if exact else -300
    if "fund" in t and "etp" not in t:
        return -60
    return 0


def _pop_bonus(sym: str) -> int:
    r = _POP_RANK.get(sym)
    if r is None:
        return 0
    return int(120 * (1 - r / len(_POP_RANK))) + 10  # สูงสุด ~130 ไม่ให้ข้ามลำดับความตรง


def _base_score(q_sym: str, q_text: str, q_tokens: list[str], sym: str, name: str) -> tuple[int, str]:
    """(คะแนนฐาน, ชนิดการจับคู่) คะแนน 0 = ไม่ตรงเลย (Finnhub fuzzy)"""
    sym_c = sym.replace("-", "").replace(".", "")
    q_c = q_sym.replace("-", "").replace(".", "")
    n = norm_text(name)
    words = n.split()
    if sym == q_sym or sym_c == q_c:
        return EXACT, "symbol"
    if sym.startswith(q_sym) or sym_c.startswith(q_c):
        return 800 - 15 * min(len(sym_c) - len(q_c), 10), "symbol"
    if n.startswith(q_text):
        return 700, "name"
    if q_tokens and all(any(w.startswith(t) for w in words) for t in q_tokens):
        return 550, "name"
    if len(q_c) >= 2 and q_c in sym_c:
        return 200, "symbol"
    if len(q_text) >= 3 and q_text in n:
        return 150, "name"
    return 0, "fuzzy"


def rank_search(query: str, finnhub_results: Iterable[dict] | None, limit: int = 10) -> list[dict]:
    """คืนรายการ {symbol, name, type, match} เรียงตามความตรง

    finnhub_results: ค่าของ data["result"] จาก Finnhub /search (None ถ้าเรียกไม่ได้ จะใช้รายการในเครื่องอย่างเดียว)
    match: "symbol" | "name" | "alias" | "fuzzy" (UI ใช้ไฮไลต์ได้)
    """
    q = clean_query(query)
    if not q:
        return []
    q_sym = q.upper().replace(" ", "")
    q_text = norm_text(q)
    q_tokens = q_text.split()
    q_norm = q_text

    cands: dict[str, dict] = {}
    order = 0

    def add(sym: str, name: str, typ: str, fuzzy_pos: int | None) -> None:
        nonlocal order
        if sym in cands:
            # เก็บชื่อ/ชนิดจาก Finnhub ถ้ามี
            if typ and not cands[sym]["type"]:
                cands[sym]["type"] = typ
            if fuzzy_pos is not None and cands[sym]["fz"] is None:
                cands[sym]["fz"] = fuzzy_pos
            return
        cands[sym] = {"symbol": sym, "name": name, "type": typ, "fz": fuzzy_pos, "ord": order}
        order += 1

    for i, x in enumerate(finnhub_results or []):
        sym = str(x.get("symbol") or "").upper().strip()
        if not sym or not valid_symbol(sym):
            continue
        add(sym, str(x.get("description") or ""), str(x.get("type") or ""), i)
    for sym, name in POPULAR.items():
        add(sym, name, "", None)

    alias_syms = _alias_hits(q_norm) if is_thai(q) else []

    scored = []
    for c in cands.values():
        sym, name, typ = c["symbol"], c["name"], c["type"]
        base, why = _base_score(q_sym, q_text, q_tokens, sym, name)
        if sym in alias_syms:
            base, why = max(base, 900), "alias"
        if base <= 0:
            continue
        exact = base >= EXACT
        s = base + _pop_bonus(sym) + _type_penalty(typ, exact)
        scored.append((s, c, why))

    if scored:
        scored.sort(key=lambda t: (-t[0], len(t[1]["symbol"]), t[1]["symbol"]))
        return [
            {"symbol": c["symbol"], "name": c["name"], "type": c["type"], "match": why}
            for _, c, why in scored[:limit]
        ]

    # ไม่ตรงอะไรเลย (พิมพ์ผิด/สะกดแปลก): ใช้ลำดับ fuzzy ของ Finnhub ตามเดิม
    fuzzy = sorted((c for c in cands.values() if c["fz"] is not None), key=lambda c: c["fz"])
    return [
        {"symbol": c["symbol"], "name": c["name"], "type": c["type"], "match": "fuzzy"}
        for c in fuzzy
        if _type_penalty(c["type"], False) == 0
    ][:limit]
