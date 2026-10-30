"""Indicator tests: นิยามอิสระแบบ brute-force + property test ห้ามแอบดูอนาคต"""
import math
import random

import pytest

from backtest_lab.engine import indicators as ind

NAN = float("nan")


def make_bars(n=300, seed=7):
    rnd = random.Random(seed)
    px, bars = 100.0, []
    for i in range(n):
        o = px * (1 + rnd.gauss(0, 0.004))
        c = o * (1 + rnd.gauss(0.0003, 0.015))
        h = max(o, c) * (1 + abs(rnd.gauss(0, 0.006)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, 0.006)))
        bars.append({"date": f"d{i}", "open": o, "high": h, "low": l, "close": c, "volume": rnd.randint(1000, 5000)})
        px = c
    return bars


BARS = make_bars()
C = [b["close"] for b in BARS]
H = [b["high"] for b in BARS]
L = [b["low"] for b in BARS]


def run(key, output=None, **over):
    p = ind.normalize_params(key, over)
    out = output or ind.REGISTRY[key].outputs[0]
    return ind.compute(BARS, key, p, out), p


def close_all(a, b, tol=1e-9):
    assert len(a) == len(b)
    for i, (x, y) in enumerate(zip(a, b)):
        if math.isnan(x) or math.isnan(y):
            assert math.isnan(x) and math.isnan(y), f"idx {i}: {x} vs {y}"
        else:
            assert x == pytest.approx(y, rel=tol, abs=tol), f"idx {i}: {x} vs {y}"


# ---------- independent definitions
def ref_sma(x, n):
    return [NAN if i < n - 1 else sum(x[i - n + 1:i + 1]) / n for i in range(len(x))]


def ref_ema(x, n):
    out = [NAN] * len(x)
    out[n - 1] = sum(x[:n]) / n
    for i in range(n, len(x)):
        out[i] = out[i - 1] + 2 / (n + 1) * (x[i] - out[i - 1])
    return out


def test_sma_ema_wma():
    close_all(run("sma", period=20)[0], ref_sma(C, 20))
    close_all(run("ema", period=20)[0], ref_ema(C, 20))
    n = 10
    ref = [NAN if i < n - 1 else sum((j + 1) * C[i - n + 1 + j] for j in range(n)) / (n * (n + 1) / 2) for i in range(len(C))]
    close_all(run("wma", period=n)[0], ref)


def test_roc_stddev_bbands():
    n = 20
    close_all(run("roc", period=12)[0], [NAN if i < 12 else (C[i] / C[i - 12] - 1) * 100 for i in range(len(C))])
    sd = [NAN if i < n - 1 else math.sqrt(sum((v - sum(C[i - n + 1:i + 1]) / n) ** 2 for v in C[i - n + 1:i + 1]) / n) for i in range(len(C))]
    close_all(run("stddev", period=n)[0], sd)
    sm = ref_sma(C, n)
    close_all(run("bbands", "upper", period=n, mult=2.0)[0], [a + 2 * b if a == a else NAN for a, b in zip(sm, sd)])
    close_all(run("bbands", "lower", period=n, mult=2.0)[0], [a - 2 * b if a == a else NAN for a, b in zip(sm, sd)])
    close_all(run("bbands", "middle", period=n)[0], sm)


def test_rsi_known_example():
    # ตัวอย่างมาตรฐาน Wilder (StockCharts) — ค่าอ้างอิงจำจากความจำ ถ้าไม่ตรงให้ตรวจกับนิยามอิสระด้านล่างก่อน
    px = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
          45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439,
          46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672,
          43.4205, 42.6628, 43.1314]
    bars = [{"open": v, "high": v, "low": v, "close": v, "volume": 1} for v in px]
    r = ind.compute(bars, "rsi", ind.normalize_params("rsi", {}), "value")
    assert all(math.isnan(v) for v in r[:14])
    assert r[14] == pytest.approx(70.53, abs=0.1)
    assert r[15] == pytest.approx(66.32, abs=0.1)
    assert r[16] == pytest.approx(66.55, abs=0.1)


def test_rsi_independent_and_edges():
    n = 14
    g = [max(C[i] - C[i - 1], 0) for i in range(1, len(C))]
    l = [max(C[i - 1] - C[i], 0) for i in range(1, len(C))]
    ag, al = sum(g[:n]) / n, sum(l[:n]) / n
    ref = [NAN] * len(C)
    ref[n] = 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(C)):
        ag, al = (ag * (n - 1) + g[i - 1]) / n, (al * (n - 1) + l[i - 1]) / n
        ref[i] = 100 - 100 / (1 + ag / al)
    close_all(run("rsi", period=n)[0], ref)
    flat = [{"open": 5, "high": 5, "low": 5, "close": 5, "volume": 1}] * 30
    assert all(math.isnan(v) for v in ind.compute(flat, "rsi", ind.normalize_params("rsi", {}), "value"))
    up = [{"open": i, "high": i, "low": i, "close": float(i), "volume": 1} for i in range(1, 40)]
    assert ind.compute(up, "rsi", ind.normalize_params("rsi", {}), "value")[-1] == 100.0


def test_macd():
    f, s = ref_ema(C, 12), ref_ema(C, 26)
    line = [a - b if a == a and b == b else NAN for a, b in zip(f, s)]
    close_all(run("macd", "macd")[0], line)
    valid = [v for v in line if v == v]
    sig_valid = ref_ema(valid, 9)
    sig = [NAN] * (len(line) - len(valid)) + sig_valid
    close_all(run("macd", "signal")[0], sig)
    close_all(run("macd", "hist")[0], [a - b if a == a and b == b else NAN for a, b in zip(line, sig)])


def test_donchian_excludes_current_bar():
    n = 20
    up, _ = run("donchian", "upper", period=n)
    for i in range(n, len(H)):
        assert up[i] == max(H[i - n:i])
    assert math.isnan(up[n - 1])
    lo, _ = run("donchian", "lower", period=n)
    for i in range(n, len(L)):
        assert lo[i] == min(L[i - n:i])


def test_stoch_willr_cci():
    k, d, sm = 14, 3, 3
    raw = [NAN if i < k - 1 else 100 * (C[i] - min(L[i - k + 1:i + 1])) / (max(H[i - k + 1:i + 1]) - min(L[i - k + 1:i + 1])) for i in range(len(C))]
    sk = [NAN] * len(C)
    for i in range(k - 1 + sm - 1, len(C)):
        sk[i] = sum(raw[i - sm + 1:i + 1]) / sm
    close_all(run("stoch", "k", k=k, d=d, smooth=sm)[0], sk)
    sd = [NAN] * len(C)
    for i in range(k - 1 + sm - 1 + d - 1, len(C)):
        sd[i] = sum(sk[i - d + 1:i + 1]) / d
    close_all(run("stoch", "d", k=k, d=d, smooth=sm)[0], sd)
    n = 14
    wr = [NAN if i < n - 1 else -100 * (max(H[i - n + 1:i + 1]) - C[i]) / (max(H[i - n + 1:i + 1]) - min(L[i - n + 1:i + 1])) for i in range(len(C))]
    close_all(run("willr", period=n)[0], wr)
    n = 20
    tp = [(a + b + c) / 3 for a, b, c in zip(H, L, C)]
    cci = []
    for i in range(len(C)):
        if i < n - 1:
            cci.append(NAN)
            continue
        w = tp[i - n + 1:i + 1]
        m = sum(w) / n
        md = sum(abs(v - m) for v in w) / n
        cci.append((tp[i] - m) / (0.015 * md))
    close_all(run("cci", period=n)[0], cci)


def test_atr_and_adx():
    n = 14
    tr = [NAN] + [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(1, len(C))]
    atr = [NAN] * len(C)
    atr[n] = sum(tr[1:n + 1]) / n
    for i in range(n + 1, len(C)):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    close_all(run("atr", period=n)[0], atr)
    adx, _ = run("adx", "adx", period=n)
    pdi, _ = run("adx", "plus_di", period=n)
    mdi, _ = run("adx", "minus_di", period=n)
    assert math.isnan(adx[2 * n - 2]) and not math.isnan(adx[2 * n - 1])
    for i in range(n, len(C)):
        assert 0 <= pdi[i] <= 100 and 0 <= mdi[i] <= 100
    assert all(0 <= v <= 100 for v in adx if v == v)
    # ทิศทางชัด: ขาขึ้นต่อเนื่อง -> +DI >> -DI, ADX สูง
    up = [{"open": i, "high": i + 1.0, "low": i - 1.0, "close": float(i), "volume": 1} for i in range(1, 120)]
    p = ind.normalize_params("adx", {})
    assert ind.compute(up, "adx", p, "plus_di")[-1] > 40
    assert ind.compute(up, "adx", p, "minus_di")[-1] < 1
    assert ind.compute(up, "adx", p, "adx")[-1] > 90


@pytest.mark.parametrize("key,over", [
    ("sma", {"period": 20}), ("ema", {"period": 20}), ("wma", {"period": 9}), ("rsi", {}), ("macd", {}),
    ("bbands", {}), ("atr", {}), ("stoch", {}), ("adx", {}), ("donchian", {}), ("roc", {}), ("cci", {}),
    ("willr", {}), ("stddev", {}), ("ema", {"period": 5, "source": "open"}),
])
def test_no_lookahead_every_output(key, over):
    """ค่า ณ แท่ง i ต้องเท่ากันไม่ว่าจะส่งข้อมูลถึง i หรือถึงปลายสุด"""
    p = ind.normalize_params(key, over)
    for out in ind.REGISTRY[key].outputs:
        full = ind.compute(BARS, key, p, out)
        for i in range(0, len(BARS), 7):
            part = ind.compute(BARS[:i + 1], key, p, out)
            a, b = part[i], full[i]
            assert (math.isnan(a) and math.isnan(b)) or a == pytest.approx(b, rel=1e-12, abs=1e-12), (key, out, i)


def test_warmup_nan_then_values():
    for key, d in ind.REGISTRY.items():
        p = ind.normalize_params(key, {})
        for out in d.outputs:
            v = ind.compute(BARS, key, p, out)
            assert len(v) == len(BARS)
            assert math.isnan(v[0])
            assert not math.isnan(v[-1]), (key, out)


def test_normalize_params_validation():
    with pytest.raises(ValueError):
        ind.normalize_params("ema", {"period": 1})
    with pytest.raises(ValueError):
        ind.normalize_params("ema", {"period": 20.5})
    with pytest.raises(ValueError):
        ind.normalize_params("ema", {"period": True})
    with pytest.raises(ValueError):
        ind.normalize_params("ema", {"source": "vwap"})
    with pytest.raises(ValueError):
        ind.normalize_params("macd", {"fast": 30, "slow": 20})
    with pytest.raises(ValueError):
        ind.normalize_params("ema", {"foo": 1})
    assert ind.normalize_params("rsi", {}) == {"period": 14, "source": "close"}


def test_catalogue_matches_registry():
    cat = ind.catalogue()
    assert {c["key"] for c in cat} == set(ind.REGISTRY)
