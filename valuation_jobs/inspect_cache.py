import os, base64, gzip, json, psycopg

with psycopg.connect(os.environ["DATABASE_URL"]) as c, c.cursor() as cur:
    cur.execute("select symbol, payload from bt_price_cache where symbol = 'AAPL'")
    sym, p = cur.fetchone()

if isinstance(p, (bytes, memoryview)):
    p = bytes(p).decode()
data = json.loads(gzip.decompress(base64.b64decode(p)))

print("type:", type(data).__name__)
if isinstance(data, dict):
    for k, v in data.items():
        print(k, "->", type(v).__name__, (v[:3] if isinstance(v, list) else str(v)[:200]))
else:
    print("len:", len(data))
    print(data[:3])
