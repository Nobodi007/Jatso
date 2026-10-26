import asyncio

import pytest

from stocks import risk_ratelimit as RL


def _run(c):
    return asyncio.run(c)


def test_blocks_after_limit_and_isolates_users():
    dep = RL.make_limiter(lambda: None, 3, 60, "t")
    for _ in range(3):
        assert _run(dep(email="u1")) == "u1"
    with pytest.raises(Exception) as ei:
        _run(dep(email="u1"))
    assert ei.value.status_code == 429 and "Retry-After" in ei.value.headers
    assert _run(dep(email="u2")) == "u2"


def test_separate_limiters_do_not_share_counters():
    a = RL.make_limiter(lambda: None, 1, 60, "a")
    b = RL.make_limiter(lambda: None, 1, 60, "b")
    _run(a(email="u"))
    assert _run(b(email="u")) == "u"


def test_table_full_fails_closed_for_new_users(monkeypatch):
    monkeypatch.setattr(RL, "MAX_KEYS", 2)
    dep = RL.make_limiter(lambda: None, 1, 60, "x")
    _run(dep(email="a"))
    _run(dep(email="b"))
    with pytest.raises(Exception) as ei:
        _run(dep(email="c"))
    assert ei.value.status_code == 429
