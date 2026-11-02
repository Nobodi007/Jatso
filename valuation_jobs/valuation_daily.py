# valuation_daily.py
import os
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import psycopg
import requests
from psycopg.rows import dict_row

DB_URL = os.environ["DATABASE_URL"]
POLYGON_KEY = os.environ.get("POLYGON_API_KEY")
FULL_REBUILD = os.environ.get("FULL_REBUILD") == "1"
SYNC_SPLITS = os.environ.get("SYNC_SPLITS") == "1"

STALE_DAYS = 200   # งบเก่ากว่านี้ไม่ใช้ (ปกติงบออกทุก ~90 วัน)
MIN_HIST = 36      # ต้องมีประวัติอย่างน้อย 36 เดือนถึงจะคิด percentile
MIN_PEERS = 5      # กลุ่มอุตสาหกรรมต้องมีอย่างน้อย 5 ตัว ไม่งั้นใช้ sector แทน
DISCOUNT, TERMINAL_G = 0.10, 0.025

FUND_COLS = ["period_end", "available_date", "revenue_ttm", "net_income_ttm", "ebitda_ttm",
             "fcf_ttm", "shares_diluted", "cash", "total_debt", "split_factor"]


def query(conn, sql, params=None):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall())


def upsert(conn, table, df, keys):
    if df.empty:
        return
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.astype(object).where(pd.notna(df), None)
    cols = list(df.columns)
    sql = (
        f"insert into {table} ({','.join(cols)}) values ({','.join(['%s'] * len(cols))}) "
        f"on conflict ({','.join(keys)}) do update set "
        + ",".join(f"{c}=excluded.{c}" for c in cols if c not in keys)
    )
    with conn.cursor() as cur:
        cur.executemany(sql, list(df.itertuples(index=False, name=None)))
    conn.commit()


# ---------- splits จาก Polygon ----------

def sync_splits(conn, tickers):
    """ดึง split ทั้งตลาดตั้งแต่ 2009 ใช้ไม่กี่ request (แพ็กเกจฟรีได้ 5 ครั้งต่อนาที)"""
    url = "https://api.polygon.io/v3/reference/splits"
    params = {"execution_date.gte": "2009-01-01", "limit": 1000, "apiKey": POLYGON_KEY}
    rows = []
    while url:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(60)
            continue
        r.raise_for_status()
        js = r.json()
        rows += [(s["ticker"], s["execution_date"], s["split_from"], s["split_to"])
                 for s in js.get("results", []) if s["ticker"] in tickers]
        url = js.get("next_url")
        params = {"apiKey": POLYGON_KEY}
        if url:
            time.sleep(12.5)
    with conn.cursor() as cur:
        cur.executemany("insert into splits values (%s,%s,%s,%s) on conflict do nothing", rows)
    conn.commit()
    print(f"splits: {len(rows)}")


def add_split_factor(fund, splits):
    """ตัวคูณจำนวนหุ้น = ผลคูณของ split ทั้งหมดที่เกิดหลังวันยื่นงบ"""
    if splits.empty:
        fund["split_factor"] = 1.0
        return fund
    splits = splits.assign(ratio=splits.split_to / splits.split_from)
    m = fund[["ticker", "period_end", "available_date"]].merge(splits, on="ticker")
    m = m[m.execution_date > m.available_date]
    fac = m.groupby(["ticker", "period_end"]).ratio.prod().rename("split_factor").reset_index()
    fund = fund.merge(fac, on=["ticker", "period_end"], how="left")
    fund["split_factor"] = fund.split_factor.fillna(1.0)
    return fund


# ---------- Reverse DCF ----------

def implied_growth(market_cap, fcf0, r=DISCOUNT, tg=TERMINAL_G, years=10):
    if not fcf0 or fcf0 <= 0 or not market_cap:
        return None

    def value(g):
        pv, f = 0.0, fcf0
        for t in range(1, years + 1):
            f *= 1 + g
            pv += f / (1 + r) ** t
        return pv + f * (1 + tg) / (r - tg) / (1 + r) ** years

    lo, hi = -0.5, 1.0
    if value(hi) < market_cap:
        return float("inf")
    if value(lo) > market_cap:
        return float("-inf")
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if value(mid) < market_cap else (lo, mid)
    return (lo + hi) / 2


# ---------- ตัวช่วยคำนวณ ----------

def pos(s):
    return s.where(s > 0)


def pct_5y(s):
    """ค่าล่าสุดสูงกว่าประวัติ 60 เดือนก่อนหน้ากี่ %"""
    cur, hist = s.iloc[-1], s.iloc[-61:-1].dropna()
    if pd.isna(cur) or len(hist) < MIN_HIST:
        return np.nan
    return (hist < cur).mean()


def rev_cagr_5y(g):
    g = g.dropna(subset=["revenue_ttm"]).sort_values("period_end")
    if g.empty:
        return np.nan
    last = g.iloc[-1]
    target = last.period_end - pd.DateOffset(years=5)
    old = g[(g.period_end - target).abs() <= pd.Timedelta(days=45)]
    if old.empty:
        return np.nan
    r0, r1 = old.iloc[0].revenue_ttm, last.revenue_ttm
    if r0 <= 0 or r1 <= 0:
        return np.nan
    return (r1 / r0) ** (1 / 5) - 1


def peer_median(df, key):
    if df[key].isna().all():
        return pd.Series(np.nan, index=df.index)
    g = df.groupby(key).pe
    return g.transform("median").where(g.transform("count") >= MIN_PEERS)


# ---------- main ----------

def run():
    with psycopg.connect(DB_URL) as conn:
        companies = query(conn, "select ticker, sector, industry, valuation_model from companies")
        tickers = set(companies.ticker)

        if SYNC_SPLITS and POLYGON_KEY:
            sync_splits(conn, tickers)

        # ราคาปิดรายเดือน (Yahoo, ปรับ split แล้ว) จากตาราง prices_monthly
        prices = query(conn, """
            select ticker, month_end as date, close from prices_monthly
            where month_end >= %s
        """, (date.today() - timedelta(days=7 * 366),))
        prices["date"] = pd.to_datetime(prices["date"])
        # แถวของเดือนปัจจุบันจาก Yahoo ลงวันสิ้นเดือน (อนาคต) ตัดทิ้ง แล้วใช้ราคาล่าสุดจาก stock_heat แทน
        prices = prices[prices["date"] <= pd.Timestamp.today().normalize()]

        heat = query(conn, """
            select symbol as ticker, price as close, quote_at from stock_heat
            where price is not null and symbol in (select ticker from companies)
        """)
        if not heat.empty:
            heat["date"] = pd.to_datetime(heat["quote_at"], utc=True).dt.tz_localize(None).dt.normalize()
            heat = heat[["ticker", "date", "close"]].drop_duplicates("ticker", keep="last")
            ym = lambda d: d["ticker"] + d["date"].dt.strftime("%Y-%m")
            prices = prices[~ym(prices).isin(set(ym(heat)))]   # เดือนเดียวกันให้ใช้ค่าล่าสุดจาก stock_heat
            prices = pd.concat([prices, heat], ignore_index=True)

        fund = query(conn, """
            select ticker, period_end, available_date, revenue_ttm, net_income_ttm,
                   ebitda_ttm, fcf_ttm, shares_diluted, cash, total_debt
            from fundamentals_quarterly where period_end >= '2012-01-01'
        """)
        splits = query(conn, "select * from splits")

        for df, cols in ((prices, ["date"]), (fund, ["period_end", "available_date"]),
                         (splits, ["execution_date"] if not splits.empty else [])):
            for c in cols:
                df[c] = pd.to_datetime(df[c])

        fund = add_split_factor(fund, splits)

        # จับคู่ราคากับงบที่ตลาดเห็นแล้ว ณ วันนั้น (กัน look-ahead)
        prices = prices.sort_values("date")
        fund = fund.sort_values(["available_date", "period_end"])
        df = pd.merge_asof(prices, fund, left_on="date", right_on="available_date",
                           by="ticker", direction="backward")
        stale = (df.date - df.available_date).dt.days > STALE_DAYS
        df.loc[stale | df.available_date.isna(), FUND_COLS] = np.nan

        df["market_cap"] = df.close * df.shares_diluted * df.split_factor
        df["pe"] = df.market_cap / pos(df.net_income_ttm)
        df["ps"] = df.market_cap / pos(df.revenue_ttm)
        df["pfcf"] = df.market_cap / pos(df.fcf_ttm)
        ev = df.market_cap + df.total_debt.fillna(0) - df.cash.fillna(0)
        df["ev_ebitda"] = ev / pos(df.ebitda_ttm)
        df["month_end"] = df.date + pd.offsets.MonthEnd(0)  # เดือนนี้จะถูกเขียนทับทุกวัน
        df = df.sort_values(["ticker", "month_end"])

        # ----- valuation_monthly -----
        monthly = df[["ticker", "month_end", "close", "market_cap", "pe", "ps", "pfcf", "ev_ebitda"]] \
            .rename(columns={"close": "price"})
        if not FULL_REBUILD:
            monthly = monthly[monthly.month_end >= pd.Timestamp.today() - pd.Timedelta(days=95)]
        monthly = monthly.assign(month_end=monthly.month_end.dt.date)
        upsert(conn, "valuation_monthly", monthly, ["ticker", "month_end"])

        # ----- valuation_latest -----
        pcts = df.groupby("ticker").agg(
            pe_pct_5y=("pe", pct_5y), ps_pct_5y=("ps", pct_5y), pfcf_pct_5y=("pfcf", pct_5y))
        latest = df.groupby("ticker").tail(1).merge(companies, on="ticker", how="left") \
                   .merge(pcts, on="ticker", how="left")

        latest_day = latest.date.max()
        latest = latest[(latest_day - latest.date).dt.days <= 7]  # ตัดหุ้นที่ราคาไม่อัปเดต

        peer = peer_median(latest, "industry").fillna(peer_median(latest, "sector"))
        latest["pe_vs_industry"] = latest.pe / peer - 1

        cagr = fund.groupby("ticker").apply(rev_cagr_5y, include_groups=False).rename("hist_rev_cagr_5y")
        latest = latest.merge(cagr, on="ticker", how="left")

        statuses, growths = [], []
        for row in latest.itertuples():
            if row.valuation_model != "standard":
                statuses.append("unsupported_type"); growths.append(None)
            elif pd.isna(row.market_cap):
                statuses.append("insufficient_data"); growths.append(None)
            elif pd.isna(row.fcf_ttm) or row.fcf_ttm <= 0:
                statuses.append("negative_fcf"); growths.append(None)
            else:
                g = implied_growth(row.market_cap, row.fcf_ttm)
                if g in (float("inf"), float("-inf")):
                    statuses.append("extreme"); growths.append(None)
                else:
                    statuses.append("ok"); growths.append(g)
        latest["model_status"] = statuses
        latest["implied_growth"] = growths

        out = latest[["ticker", "date", "close", "market_cap", "pe", "ps", "pfcf", "ev_ebitda",
                      "pe_pct_5y", "ps_pct_5y", "pfcf_pct_5y", "pe_vs_industry",
                      "implied_growth", "hist_rev_cagr_5y", "model_status"]] \
            .rename(columns={"date": "as_of", "close": "price"})
        out = out.assign(as_of=out.as_of.dt.date, updated_at=pd.Timestamp.now(tz="UTC"))
        upsert(conn, "valuation_latest", out, ["ticker"])

        print(f"latest: {len(out)} rows | status:", out.model_status.value_counts().to_dict())


if __name__ == "__main__":
    run()
