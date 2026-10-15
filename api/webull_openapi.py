"""Read-only Webull Thailand OpenAPI adapter for UAT.

This module intentionally exposes no order placement, replacement, or cancellation
methods. Credentials are read only from the backend environment.
"""
from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter(prefix="/api/webull", tags=["Webull UAT (read-only)"])

# Deliberately pinned to UAT. Do not make this configurable from the browser.
WEBULL_HOST = "th-api.uat.webullbroker.com"
WEBULL_BASE_URL = f"https://{WEBULL_HOST}"
REQUEST_TIMEOUT_SECONDS = 15


_token_cache: dict[str, Any] = {"token": "", "expires_at": 0, "status": ""}
_token_lock = Lock()


def _app_credentials() -> tuple[str, str]:
    app_key = os.getenv("WEBULL_APP_KEY", "").strip()
    app_secret = os.getenv("WEBULL_APP_SECRET", "").strip()
    if not (app_key and app_secret):
        raise HTTPException(
            status_code=503,
            detail="Webull UAT is not configured. Set WEBULL_APP_KEY and WEBULL_APP_SECRET in the backend environment.",
        )
    return app_key, app_secret


def _new_client(app_key: str, app_secret: str):
    # Lazy import: keep status routes available even if SDK installation fails.
    try:
        from webull.core.client import ApiClient
    except Exception as exc:
        raise RuntimeError("Webull SDK unavailable: " + type(exc).__name__) from None
    client = ApiClient(
        app_key, app_secret, "th", connect_timeout=5,
        timeout=REQUEST_TIMEOUT_SECONDS, auto_retry=False,
    )
    client.add_endpoint("th", WEBULL_HOST)
    return client


def _get_access_token() -> str:
    """Create/cache a UAT token on the server; never expose its value to the browser."""
    app_key, app_secret = _app_credentials()
    env_token = os.getenv("WEBULL_ACCESS_TOKEN", "").strip()
    if env_token:
        return env_token
    now_ms = int(time.time() * 1000)
    with _token_lock:
        token = str(_token_cache.get("token") or "")
        expires_at = int(_token_cache.get("expires_at") or 0)
        if token and expires_at > now_ms + 60_000:
            return token
        try:
            client = _new_client(app_key, app_secret)
            from webull.core.request import ApiRequest
            request = ApiRequest("/auth/tokens/create", version="v3", method="POST")
            response = client.get_response(request)
            payload = response.json()
        except Exception as exc:
            logging.getLogger("uvicorn.error").error(
                "webull token create failed: %s: %s", type(exc).__name__, str(exc)[:300]
            )
            raise HTTPException(
                status_code=502,
                detail=f"Webull UAT token creation failed ({type(exc).__name__}). Check UAT permissions and SDK signing support.",
            ) from None
        token = str(payload.get("token") or "")
        status = str(payload.get("status") or "").upper()
        expires_at = int(payload.get("expires_at") or 0)
        if not token:
            raise HTTPException(status_code=502, detail="Webull UAT token response did not contain a token.")
        _token_cache.update({"token": token, "expires_at": expires_at, "status": status})
        if status not in {"NORMAL", "PENDING"}:
            raise HTTPException(status_code=502, detail=f"Webull UAT token status is {status or 'UNKNOWN'}.")
        return token


def _stringify_params(params: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            result[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            result[key] = ",".join(str(item) for item in value)
        else:
            result[key] = str(value)
    return result


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    app_key, app_secret = _app_credentials()
    access_token = _get_access_token()
    query = _stringify_params(params)

    # Use Webull's official SDK for request signing and transport. This avoids
    # duplicating the signing algorithm in the app and keeps the App Secret
    # out of HTTP headers. Keep SDK logs quiet so signed request details are
    # not unnecessarily written to Render logs.
    logging.getLogger("webull").setLevel(logging.CRITICAL)
    logging.getLogger("webull.core").setLevel(logging.CRITICAL)
    try:
        client = _new_client(app_key, app_secret)
        client.set_token(access_token)
        from webull.core.request import ApiRequest
        request = ApiRequest(
            path,
            version="v3",
            method=method.upper(),
            query_params=query,
            body_params=body,
        )
        response = client.get_response(request)
        return response.json()
    except HTTPException:
        raise
    except Exception as exc:
        # Do not return raw SDK exception text: some SDK errors include request
        # metadata. It is safer to report only the exception class to clients.
        raise HTTPException(
            status_code=502,
            detail=f"Webull UAT SDK request failed ({type(exc).__name__}). Check Render logs and UAT permissions.",
        ) from None


def _sdk_available() -> bool:
    try:
        from webull.core.client import ApiClient  # noqa: F401
        from webull.core.request import ApiRequest  # noqa: F401
        return True
    except Exception:
        return False


@router.get("/status")
def webull_status() -> dict[str, Any]:
    """Safe configuration diagnostic; never returns credentials or token values."""
    return {
        "provider": "Webull Thailand OpenAPI",
        "environment": "UAT",
        "read_only": True,
        "trading_actions_enabled": False,
        "endpoint_host": WEBULL_HOST,
        "configured": all(os.getenv(name, "").strip() for name in (
            "WEBULL_APP_KEY", "WEBULL_APP_SECRET"
        )),
        "sdk_importable": _sdk_available(),
        "credentials_present": {
            "app_key": bool(os.getenv("WEBULL_APP_KEY", "").strip()),
            "app_secret": bool(os.getenv("WEBULL_APP_SECRET", "").strip()),
            "access_token": bool(os.getenv("WEBULL_ACCESS_TOKEN", "").strip() or _token_cache.get("token")),
            "allowed_user": bool(os.getenv("WEBULL_ALLOWED_USER_EMAIL", "").strip()),
        },
    }


@router.post("/token/create")
def create_access_token() -> dict[str, Any]:
    """Create or reuse a server-side UAT token; token value is never returned."""
    token = _get_access_token()
    return {
        "provider": "Webull Thailand OpenAPI",
        "environment": "UAT",
        "token_created": bool(token),
        "token_cached": bool(_token_cache.get("token")),
        "status": _token_cache.get("status") or "EXTERNAL_TOKEN",
        "expires_at": _token_cache.get("expires_at") or None,
        "token_value_returned": False,
    }


@router.get("/accounts")
def list_accounts() -> Any:
    """List accounts; does not expose balances or submit orders."""
    return _request("GET", "/trading/accounts/list")

@router.get("/positions")
def account_positions(
    account_id: str = Query(..., min_length=1, max_length=100),
) -> Any:
    """Read account positions only. No orders are submitted."""
    return _request(
        "GET",
        "/trading/assets/positions/list",
        params={"account_id": account_id},
    )

@router.get("/stocks/snapshots")
def stock_snapshots(
    symbols: str = Query(..., min_length=1, max_length=2000, description="Comma-separated symbols, max 100"),
    category: str = Query("US_STOCK", pattern="^(US_STOCK|US_ETF)$"),
    extend_hour_required: bool = False,
    overnight_required: bool = False,
) -> Any:
    symbol_list = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    if not symbol_list or len(symbol_list) > 100 or len(set(symbol_list)) != len(symbol_list):
        raise HTTPException(status_code=422, detail="Provide 1–100 unique symbols, comma-separated.")
    return _request(
        "GET",
        "/market-data/stocks/snapshots/list",
        params={
            "symbols": ",".join(symbol_list),
            "category": category,
            "extend_hour_required": extend_hour_required,
            "overnight_required": overnight_required,
        },
    )


@router.post("/stocks/bars")
def stock_bars(body: dict[str, Any]) -> Any:
    """Read historical stock bars only. Validate the supported fields before forwarding."""
    allowed = {"symbols", "category", "timespan", "count", "real_time_required", "trading_sessions"}
    unknown = set(body) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported fields: {', '.join(sorted(unknown))}")
    symbols = body.get("symbols")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 100:
        raise HTTPException(status_code=422, detail="symbols must be an array containing 1–100 symbols.")
    if body.get("category", "US_STOCK") not in {"US_STOCK", "US_ETF"}:
        raise HTTPException(status_code=422, detail="category must be US_STOCK or US_ETF.")
    if body.get("timespan") not in {"S5", "S15", "M1", "M5", "M15", "M30", "M60", "M120", "M240", "D", "W", "M", "Y"}:
        raise HTTPException(status_code=422, detail="Unsupported timespan.")
    count = body.get("count", 200)
    if not isinstance(count, int) or not 1 <= count <= (1650 if body.get("timespan") == "M1" else 1200):
        raise HTTPException(status_code=422, detail="count is outside the documented limit.")
    forwarded = {
        "symbols": [str(s).strip().upper() for s in symbols],
        "category": body.get("category", "US_STOCK"),
        "timespan": body["timespan"],
        "count": count,
        "real_time_required": body.get("real_time_required", True),
    }
    if body.get("trading_sessions") is not None:
        forwarded["trading_sessions"] = body["trading_sessions"]
    return _request("POST", "/market-data/stocks/bars/list", body=forwarded)


@router.get("/orders/open")
def open_orders(account_id: str = Query(..., min_length=1, max_length=100), pagination_key: str | None = None) -> Any:
    params = {"account_id": account_id}
    if pagination_key:
        params["pagination_key"] = pagination_key
    return _request("GET", "/trading/orders/open-orders/list", params=params)


@router.get("/orders/history")
def order_history(
    account_id: str = Query(..., min_length=1, max_length=100),
    start_time: str | None = None,
    end_time: str | None = None,
    pagination_key: str | None = None,
) -> Any:
    params: dict[str, Any] = {"account_id": account_id}
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
    if pagination_key:
        params["pagination_key"] = pagination_key
    return _request("GET", "/trading/orders/historical-orders/list", params=params)


@router.get("/orders/detail")
def order_detail(
    account_id: str = Query(..., min_length=1, max_length=100),
    client_order_id: str = Query(..., min_length=1, max_length=32),
) -> Any:
    return _request(
        "GET",
        "/trading/orders/get",
        params={"account_id": account_id, "client_order_id": client_order_id},
    )
