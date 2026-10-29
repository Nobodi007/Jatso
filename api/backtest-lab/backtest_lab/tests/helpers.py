from datetime import date, timedelta


def mk_bars(start: str, n: int, fn):
    """fn(i) -> (open, close) หรือ close เดี่ยว ๆ ; ข้ามเสาร์-อาทิตย์"""
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            v = fn(len(out))
            o, c = (v, v) if not isinstance(v, tuple) else v
            out.append({"date": d.isoformat(), "open": float(o), "high": float(max(o, c)),
                        "low": float(min(o, c)), "close": float(c), "volume": 1000})
        d += timedelta(days=1)
    return out


def spec(positions, start, end, **kw):
    from backtest_lab.engine.spec import validate_spec
    base = {"start": start, "end": end, "initial_capital": 100000, "positions": positions,
            "costs": {"commission_bps": 0, "slippage_bps": 0}}
    base.update(kw)
    return validate_spec(base)
