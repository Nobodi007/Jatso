import json
import time

import jwt
import pytest

from backtest_lab.api.auth import AuthError, decode_email
from backtest_lab.db.client import DbError, SbClient
from backtest_lab.db.run_store import MemoryRunStore, SupabaseRunStore

SECRET = "x" * 40


def tok(sub="User@Example.com", secret=SECRET, **kw):
    return "Bearer " + jwt.encode({"sub": sub, **kw}, secret, algorithm="HS256")


def test_auth_ok_lowercases_email():
    assert decode_email(tok(), SECRET) == "user@example.com"


@pytest.mark.parametrize("hdr,secret,status,code", [
    ("", SECRET, 401, "login_required"),
    ("Basic abc", SECRET, 401, "login_required"),
    (tok(secret="y" * 40), SECRET, 401, "session_expired"),
    (tok(exp=int(time.time()) - 10), SECRET, 401, "session_expired"),
    (tok(sub=""), SECRET, 401, "invalid_session"),
    (tok(), "short", 503, "auth_not_configured"),
])
def test_auth_rejections(hdr, secret, status, code):
    with pytest.raises(AuthError) as e:
        decode_email(hdr, secret)
    assert (e.value.status, e.value.code) == (status, code)


class Rec:
    """transport ปลอม: บันทึกทุกคำขอ"""
    def __init__(self, payload=b"[]", status=200):
        self.calls, self.payload, self.status = [], payload, status

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        return self.status, self.payload


def test_every_supabase_query_is_scoped_by_email():
    rec = Rec(payload=json.dumps([{"id": "r1", "email": "a@x.com", "status": "queued"}]).encode())
    st = SupabaseRunStore(SbClient("https://db.example", "KEY123", rec))
    st.create("a@x.com", {"k": 1}, "h", "v")
    st.get("a@x.com", "r1"); st.list("a@x.com"); st.count("a@x.com")
    st.update("a@x.com", "r1", {"status": "done"}); st.delete("a@x.com", "r1"); st.find_active("a@x.com", "h")
    assert len(rec.calls) == 7
    for method, url, _, body in rec.calls:
        if method == "POST":
            assert json.loads(body)["email"] == "a@x.com"
        else:
            assert "email=eq.a%40x.com" in url, (method, url)             # ทุก GET/PATCH/DELETE มีตัวกรอง email
    for method, url, *_ in rec.calls:
        if method in ("GET", "PATCH", "DELETE") and "bt_runs" in url and "id=eq" in url:
            assert "email=eq." in url


def test_db_error_does_not_leak_key_or_url():
    st = SupabaseRunStore(SbClient("https://secret-host.example", "SUPERSECRETKEY", Rec(payload=b"boom", status=500)))
    with pytest.raises(DbError) as e:
        st.get("a@x.com", "r1")
    assert "SUPERSECRETKEY" not in str(e.value) and "secret-host" not in str(e.value)


def test_memory_store_isolation():
    st = MemoryRunStore()
    a = st.create("a@x.com", {}, "h", "v"); st.create("b@x.com", {}, "h", "v")
    assert st.get("b@x.com", a["id"]) is None
    assert st.delete("b@x.com", a["id"]) is False and st.get("a@x.com", a["id"]) is not None
    st.update("b@x.com", a["id"], {"status": "hacked"})
    assert st.get("a@x.com", a["id"])["status"] == "queued"
    assert len(st.list("a@x.com")) == 1 and st.count("b@x.com") == 1
