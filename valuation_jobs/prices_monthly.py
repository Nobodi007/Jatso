# prices_monthly.py  -- ดึงราคาปิดรายเดือน (ปรับ split แล้ว ไม่ปรับปันผล) จาก Yahoo ลงตาราง prices_monthly
import os
import time

import pandas as pd
import psycopg
import yfinance as yf

DB_URL = os.environ["DATABASE_URL"]
CHUNK = 60          # ดึงทีละกี่ตัว กัน Yahoo จำกัดความถี่
YEARS = "7y"        # เผื่อไว้ให้พอคิด percentile 5 ปี

DDL = """
create table if not exists prices_monthly (
  ticker text not null,
  month_end date not null,
  close double precision,
  primary key (ticker, month_end)
);
alter table prices_monthly enable row level security;
"""


def to_yahoo(t):
    return t.replace(".", "-")  # BRK.B -> BRK-B


def fetch_chunk(tickers):
    ymap = {to_yahoo(t): t for t in tickers}
    df = yf.download(list(ymap), period=YEARS, interval="1mo", auto_adjust=False,
                     group_by="ticker", progress=False, threads=True)
    rows = []
    for y, t in ymap.items():
        try:
            s = df[y]["Close"] if len(ymap) > 1 else df["Close"]
        except KeyError:
            continue
        s = s.dropna()
        for ts, v in s.items():
            me = (pd.Timestamp(ts) + pd.offsets.MonthEnd(0)).date()  # Yahoo ระบุวันแรกของเดือน -> แปลงเป็นสิ้นเดือน
            rows.append((t, me, float(v)))
    return rows


def run():
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute("select ticker from companies order by ticker")
            tickers = [r[0] for r in cur.fetchall()]
        only = os.environ.get("TICKERS")  # เช่น TICKERS=PANW,PHM สำหรับดึงซ้ำเฉพาะบางตัว
        if only:
            tickers = [t.strip().upper() for t in only.split(",") if t.strip()]
        conn.commit()

        total, missing = 0, []
        for i in range(0, len(tickers), CHUNK):
            part = tickers[i:i + CHUNK]
            rows = fetch_chunk(part)
            got = {r[0] for r in rows}
            missing += [t for t in part if t not in got]
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into prices_monthly (ticker, month_end, close) values (%s,%s,%s) "
                    "on conflict (ticker, month_end) do update set close = excluded.close", rows)
            conn.commit()
            total += len(rows)
            print(f"{min(i + CHUNK, len(tickers))}/{len(tickers)}  rows={total}")
            time.sleep(2)

        print("no price:", missing)


if __name__ == "__main__":
    run()
