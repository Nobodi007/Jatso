import os

import jwt
from fastapi import Header, HTTPException


def current_email(authorization: str = Header(default="")) -> str:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "login_required", headers={"WWW-Authenticate": "Bearer"})

    secret = os.environ.get("AUTH_JWT_SECRET", "").strip()
    if len(secret) < 32:
        raise HTTPException(503, "auth_not_configured")

    try:
        payload = jwt.decode(authorization[7:].strip(), secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "session_expired", headers={"WWW-Authenticate": "Bearer"})

    email = str(payload.get("sub") or "").strip().lower()
    if not email:
        raise HTTPException(401, "invalid_session")
    return email
