"""ถอดรหัส JWT (HS256) ของผู้ใช้ — เขียนใหม่ ไม่ import จาก api/stocks/auth.py
ใช้ค่า env AUTH_JWT_SECRET ตัวเดียวกับระบบหลัก (อ่าน env ไม่ใช่การผูกโค้ด) email มาจาก claim `sub` เท่านั้น"""
from __future__ import annotations

import os


class AuthError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


def decode_email(authorization: str, secret: str | None = None) -> str:
    import jwt
    if not (authorization or "").lower().startswith("bearer "):
        raise AuthError(401, "login_required")
    secret = (secret if secret is not None else os.environ.get("AUTH_JWT_SECRET", "")).strip()
    if len(secret) < 32:
        raise AuthError(503, "auth_not_configured")
    try:
        payload = jwt.decode(authorization[7:].strip(), secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise AuthError(401, "session_expired")
    email = str(payload.get("sub") or "").strip().lower()
    if not email:
        raise AuthError(401, "invalid_session")
    return email
