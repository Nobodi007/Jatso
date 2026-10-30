import asyncio

from backtest_lab.api import handlers as H
from backtest_lab.tests.test_handlers import SPEC, finish, services


def test_meta_exposes_indicator_catalogue_and_rule_language():
    st, m = H.meta()
    keys = {i["key"] for i in m["indicators"]}
    assert {"ema", "rsi", "macd", "bbands", "adx", "donchian"} <= keys
    assert "cross_above" in m["rule_language"]["operators"]


def test_strategy_run_through_service_with_warnings():
    spec = {**SPEC, "strategy": {
        "entry": {"op": ">", "left": {"price": "close"}, "right": {"ind": "sma", "period": 20}},
        "stops": {"stop_loss_pct": 10}}}

    async def go():
        s = services()
        st, out = await H.create_run(s, "a@x.com", {"spec": spec})
        assert st == 202
        await finish(s)
        st, run = await H.get_run(s, "a@x.com", out["id"])
        assert run["status"] == "done", run.get("error")
        res = run["result"]
        assert res["mode"] == "strategy" and res["strategy_result"]["trip_stats"]["open_at_end"] == 1
        codes = {w["code"] for w in res["warnings"]}
        assert {"hindsight_risk", "few_trades", "survivorship_bias"} <= codes
        assert res["comparison"]["buy_hold"] and res["comparison"]["benchmark"]
    asyncio.run(go())


def test_invalid_strategy_rejected_400():
    async def go():
        s = services()
        bad = {**SPEC, "strategy": {"entry": {"op": ">", "left": {"ind": "nope"}, "right": {"value": 1}}}}
        st, out = await H.create_run(s, "a@x.com", {"spec": bad})
        assert st == 400 and "strategy" in out["message"]
    asyncio.run(go())
