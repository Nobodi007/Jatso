"""Nobodi Webull Thailand OpenAPI adapter — consolidated coverage.

This module is pinned to the Webull Thailand UAT host. It exposes fixed endpoint
wrappers only (never a user-supplied upstream URL). Read-only endpoints are enabled;
order placement/replace/cancel and watchlist mutations are disabled unless explicitly
enabled by backend-only environment flags. No credentials are returned to clients.

Tested previously by the project owner on UAT: token/create, accounts, stock snapshots,
stock bars, open orders, order history, and order detail. New endpoints need individual
UAT/permission verification. This is not a claim that every endpoint is entitled or live.
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from threading import Lock, RLock, Thread
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request
try:
    from webull.core.client import ApiClient
    from webull.core.request import ApiRequest
except Exception:  # SDK ติดตั้งไม่ได้ ให้เฉพาะ route Webull ใช้ไม่ได้ ไม่ให้ทั้ง API ล้ม
    ApiClient = None  # type: ignore
    ApiRequest = None  # type: ignore
router = APIRouter(prefix="/api/webull", tags=["Webull UAT"])

# Never allow a browser parameter to alter the upstream host.
WEBULL_HOST = "th-api.uat.webullbroker.com"
WEBULL_EVENTS_HOST_DEFAULT = "th-events-api.uat.webullbroker.com"
WEBULL_REGION = "th"
REQUEST_TIMEOUT_SECONDS = 15
TOKEN_FALLBACK_LIFETIME_MS = 10 * 60_000
TOKEN_REFRESH_MARGIN_MS = 60_000

# Silence SDK internals once at import time (they may log signed headers/params).
logging.getLogger("webull").setLevel(logging.CRITICAL)
logging.getLogger("webull.core").setLevel(logging.CRITICAL)
_log = logging.getLogger(__name__)

_token_cache: dict[str, Any] = {"token": "", "expires_at": 0, "status": ""}
_token_lock = Lock()

# gRPC event stream state is deliberately in-memory. It can be drained by polling
# /events/recent; a production deployment should persist events if they must survive restarts.
_EVENT_LOCK = RLock()
_EVENT_ROWS: deque[dict[str, Any]] = deque(maxlen=1000)
_EVENT_WORKERS: dict[str, dict[str, Any]] = {}


class _UpstreamFailure(Exception):
    def __init__(self, status: int | None, detail: dict[str, Any], request_id: str | None = None):
        super().__init__(str(detail.get("message") or "Webull upstream request failed"))
        self.status = status
        self.detail = detail
        self.request_id = request_id


# ============================== CONFIG / FLAGS ==============================
def _app_credentials() -> tuple[str, str]:
    app_key = os.getenv("WEBULL_APP_KEY", "").strip()
    app_secret = os.getenv("WEBULL_APP_SECRET", "").strip()
    if not (app_key and app_secret):
        raise HTTPException(
            status_code=503,
            detail="Webull UAT is not configured. Set WEBULL_APP_KEY and WEBULL_APP_SECRET in the backend environment.",
        )
    return app_key, app_secret


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _require_mutation_flag(name: str, purpose: str) -> None:
    if not _flag_enabled(name):
        raise HTTPException(
            status_code=423,
            detail={"message": f"{purpose} is disabled by default", "required_environment_flag": name,
                    "environment": "UAT only"},
        )


def _allowed_account_ids() -> set[str]:
    return {x.strip() for x in os.getenv("WEBULL_ALLOWED_ACCOUNT_IDS", "").split(",") if x.strip()}


def _check_account_allowed(account_id: str, purpose: str) -> None:
    """If WEBULL_ALLOWED_ACCOUNT_IDS is set, only those accounts may be used for mutations/events."""
    allowed = _allowed_account_ids()
    if not allowed or account_id not in allowed:
        raise HTTPException(status_code=403, detail=f"บัญชีนี้ไม่ได้อยู่ใน WEBULL_ALLOWED_ACCOUNT_IDS สำหรับ {purpose}")


def _body_account_id(body: dict[str, Any]) -> str:
    account_id = str(body.get("account_id") or "").strip()
    if not account_id or len(account_id) > 100:
        raise HTTPException(status_code=422, detail="account_id is required in body (max 100 chars).")
    return account_id

if ApiClient is None:
        raise HTTPException(status_code=503, detail="Webull SDK ยังไม่พร้อมใช้งานบนเซิร์ฟเวอร์")

# ============================== SDK CLIENT / TOKEN ==============================
def _new_client(app_key: str, app_secret: str) -> ApiClient:
    client = ApiClient(
        app_key, app_secret, WEBULL_REGION,
        connect_timeout=5, timeout=REQUEST_TIMEOUT_SECONDS, auto_retry=False,
    )
    client.add_endpoint(WEBULL_REGION, WEBULL_HOST)
    return client


def _call_getter(obj: Any, name: str) -> Any:
    fn = getattr(obj, name, None)
    if callable(fn):
        try:
            return fn()
        except Exception:
            return None
    return None


def _extract_error(exc: Exception) -> tuple[int | None, dict[str, Any], str | None]:
    """Supports both SDK-style exceptions (get_http_status, ...) and requests-style .response."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    detail: dict[str, Any] = {"message": "Webull upstream request failed", "error_type": type(exc).__name__}
    request_id: str | None = None

    # SDK-style exceptions (ServerException / ClientException)
    sdk_status = _call_getter(exc, "get_http_status")
    if status is None and sdk_status is not None:
        try:
            status = int(sdk_status)
        except (TypeError, ValueError):
            pass
    for getter, key in (("get_error_code", "error_code"), ("get_error_msg", "message")):
        value = _call_getter(exc, getter)
        if value:
            detail[key] = str(value)[:300]
    sdk_request_id = _call_getter(exc, "get_request_id")
    if sdk_request_id:
        request_id = str(sdk_request_id)[:200]

    # requests-style response
    if response is not None:
        headers = getattr(response, "headers", {}) or {}
        for name in ("x-request-id", "request-id", "x-correlation-id", "trace-id"):
            if not request_id and headers.get(name):
                request_id = str(headers.get(name))[:200]
        try:
            body = response.json()
            if isinstance(body, dict):
                for key in ("error_code", "code", "message"):
                    if body.get(key) is not None:
                        detail[key] = str(body[key])[:300]
                for key in ("request_id", "requestId", "trace_id"):
                    if not request_id and body.get(key):
                        request_id = str(body[key])[:200]
        except Exception:
            pass
    return status, detail, request_id


def _invalidate_token_cache() -> None:
    with _token_lock:
        _token_cache.update({"token": "", "expires_at": 0, "status": ""})


def _get_access_token() -> str:
    """Reuse a configured token or create/cache one server-side with the official SDK."""
    app_key, app_secret = _app_credentials()
    configured = os.getenv("WEBULL_ACCESS_TOKEN", "").strip()
    if configured:
        return configured
    with _token_lock:
        now_ms = int(time.time() * 1000)
        cached = str(_token_cache.get("token") or "")
        expires_at = int(_token_cache.get("expires_at") or 0)
        if cached and expires_at > now_ms + TOKEN_REFRESH_MARGIN_MS:
            return cached
        try:
            client = _new_client(app_key, app_secret)
            response = client.get_response(ApiRequest("/auth/tokens/create", version="v3", method="POST"))
            payload = response.json()
        except Exception as exc:
            status, detail, request_id = _extract_error(exc)
            raise HTTPException(
                status_code=502,
                detail={"message": "Webull UAT token creation failed", "upstream_status": status,
                        "error_type": detail.get("error_type"), "error_code": detail.get("error_code"),
                        "request_id": request_id},
            ) from None
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail={"message": "Unexpected Webull token response shape"})

        token = str(payload.get("token") or "")
        status = str(payload.get("status") or "UNKNOWN").upper()
        try:
            expires_at = int(payload.get("expires_at") or 0)
        except (TypeError, ValueError):
            expires_at = 0
        if 0 < expires_at < 10**12:  # seconds -> milliseconds
            expires_at *= 1000
        if expires_at <= 0:  # unknown lifetime: be conservative
            expires_at = now_ms + TOKEN_FALLBACK_LIFETIME_MS

        if not token:
            raise HTTPException(status_code=502, detail={"message": "Webull token response omitted token", "status": status})
        # UAT returns PENDING for test tokens in some accounts. Token access is confirmed
        # by actual endpoint calls, not inferred here. Never cache an unusable token.
        if status not in {"NORMAL", "PENDING"}:
            raise HTTPException(status_code=502, detail={"message": "Webull token is not usable", "status": status})
        _token_cache.update({"token": token, "expires_at": expires_at, "status": status})
        return token


# ============================== REQUEST CORE ==============================
def _clean_query(params: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in (params or {}).items():
        if value is None or str(value).strip() == "":
            continue
        if isinstance(value, bool):
            result[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            result[key] = ",".join(str(item) for item in value)
        else:
            result[key] = str(value)
    return result


def _request(
    path: str | tuple[str, ...],
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | list[Any] | None = None,
) -> Any:
    """Signed request via official SDK. Candidate paths fall back only on 404/405."""
    app_key, app_secret = _app_credentials()
    token = _get_access_token()
    query = _clean_query(params)
    candidates = (path,) if isinstance(path, str) else tuple(path)
    if not candidates:
        raise HTTPException(status_code=500, detail="No upstream path configured.")
    last_failure: _UpstreamFailure | None = None

    for index, upstream_path in enumerate(candidates):
        is_last = index == len(candidates) - 1
        try:
            client = _new_client(app_key, app_secret)
            client.set_token(token)
            response = client.get_response(ApiRequest(
                upstream_path, version="v3", method=method.upper(),
                query_params=query, body_params=body,
            ))
            status = int(getattr(response, "status_code", 200) or 200)
            if status >= 400:
                try:
                    response.raise_for_status()
                except Exception as exc:
                    upstream_status, detail, request_id = _extract_error(exc)
                    upstream_status = upstream_status or status
                    if upstream_status in {404, 405} and not is_last:
                        continue
                    last_failure = _UpstreamFailure(upstream_status, detail, request_id)
                    break
                else:
                    last_failure = _UpstreamFailure(status, {"message": "Webull upstream request failed"})
                    break
            return response.json()
        except HTTPException:
            raise
        except Exception as exc:
            status, detail, request_id = _extract_error(exc)
            if status in {404, 405} and not is_last:
                continue
            last_failure = _UpstreamFailure(status, detail, request_id)
            break

    failure = last_failure or _UpstreamFailure(None, {"message": "Webull request failed"})
    if failure.status == 401 and not os.getenv("WEBULL_ACCESS_TOKEN", "").strip():
        _invalidate_token_cache()  # expired/revoked token: recreate on next call

    # Preserve 4xx business errors like 417 so the client can distinguish permission,
    # parameter, and server-side failures. Normalize upstream 5xx/unknown to gateway 502.
    code = failure.status if failure.status and 400 <= failure.status < 500 else 502
    payload = {"provider": "Webull UAT", "upstream_status": failure.status, **failure.detail}
    if failure.request_id:
        payload["request_id"] = failure.request_id
    _log.warning("Webull API failure: path=%s method=%s status=%s request_id=%s error=%s",
                 candidates[-1], method.upper(), failure.status, failure.request_id,
                 failure.detail.get("error_code") or failure.detail.get("message"))
    raise HTTPException(status_code=code, detail=payload) from None


def _query(request: Request, *, default_category: str | None = None, require_symbol: bool = False) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        params[key] = value
    if default_category:
        params.setdefault("category", default_category)
    if require_symbol and not any(str(params.get(k) or "").strip() for k in ("symbol", "symbols", "ticker", "underlying_symbol")):
        raise HTTPException(status_code=422, detail="A symbol query parameter is required.")
    return params


# ============================== STATUS / TOKEN ==============================
@router.get("/status")
def webull_status() -> dict[str, Any]:
    token_exists = bool(os.getenv("WEBULL_ACCESS_TOKEN", "").strip() or _token_cache.get("token"))
    return {
        "provider": "Webull Thailand OpenAPI", "environment": "UAT", "read_only_default": True,
        "upstream_host": WEBULL_HOST,
        "credentials_present": {
            "app_key": bool(os.getenv("WEBULL_APP_KEY", "").strip()),
            "app_secret": bool(os.getenv("WEBULL_APP_SECRET", "").strip()),
            "access_token_configured_or_cached": token_exists,
        },
        "order_actions_enabled": _flag_enabled("WEBULL_UAT_ORDER_ACTIONS_ENABLED"),
        "watchlist_writes_enabled": _flag_enabled("WEBULL_UAT_WATCHLIST_WRITES_ENABLED"),
        "account_allowlist_active": bool(_allowed_account_ids()),
        "market_data_stream_control_enabled": True,
        "gRPC_events_enabled": _flag_enabled("WEBULL_UAT_EVENTS_ENABLED"),
        "credentials_returned": False,
    }


@router.post("/token/create")
def create_access_token() -> dict[str, Any]:
    token = _get_access_token()
    external = bool(os.getenv("WEBULL_ACCESS_TOKEN", "").strip())
    return {"provider": "Webull Thailand OpenAPI", "environment": "UAT", "token_created_or_reused": bool(token),
            "status": "EXTERNAL_TOKEN" if external else (_token_cache.get("status") or "UNKNOWN"),
            "expires_at": None if external else (_token_cache.get("expires_at") or None),
            "token_value_returned": False}


@router.post("/token/check")
def check_access_token() -> Any:
    token = _get_access_token()
    result = _request("/auth/tokens/check", method="POST", body={"token": token})
    if isinstance(result, dict):
        result = {k: v for k, v in result.items() if k.lower() not in {"token", "access_token"}}
    return result


# ============================== TRADING ACCOUNT READS ==============================
@router.get("/accounts")
def list_accounts() -> Any:
    return _request("/trading/accounts/list")


@router.get("/account/balance")
def account_balance(account_id: str = Query(..., min_length=1, max_length=100)) -> Any:
    return _request("/trading/assets/balances/get", params={"account_id": account_id})


@router.get("/positions")
def account_positions(
    account_id: str = Query(..., min_length=1, max_length=100),
    pagination_key: str | None = None,
) -> Any:
    return _request("/trading/assets/positions/list",
                    params={"account_id": account_id, "pagination_key": pagination_key})


@router.get("/stocks/instruments")
def stock_instruments(request: Request) -> Any:
    params = _query(request, default_category="US_STOCK")
    return _request("/trading/instruments/stocks/profiles/list", params=params)


# ============================== STOCK MARKET DATA ==============================
_STOCK_TIMESPANS = {"S5", "S15", "M1", "M5", "M15", "M30", "M60", "M120", "M240", "D", "W", "M", "Y"}
_STOCK_BARS_PATHS = ("/market-data/stocks/bars/list", "/openapi/market-data/stock/batch-bars")


def _validate_stock_bars(body: dict[str, Any]) -> dict[str, Any]:
    allowed = {"symbols", "category", "timespan", "count", "real_time_required", "trading_sessions"}
    unknown = set(body) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported fields: {', '.join(sorted(unknown))}")

    symbols = body.get("symbols")
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 100:
        raise HTTPException(status_code=422, detail="symbols must be an array containing 1–100 symbols.")
    cleaned = [str(s).strip().upper() for s in symbols if str(s).strip()]
    if len(cleaned) != len(symbols) or len(set(cleaned)) != len(cleaned):
        raise HTTPException(status_code=422, detail="symbols must be non-empty and unique.")

    category = body.get("category", "US_STOCK")
    if category not in {"US_STOCK", "US_ETF"}:
        raise HTTPException(status_code=422, detail="category must be US_STOCK or US_ETF.")

    timespan = body.get("timespan")
    if timespan not in _STOCK_TIMESPANS:
        raise HTTPException(status_code=422, detail="Unsupported timespan.")

    count = body.get("count", 200)
    max_count = 1650 if timespan == "M1" else 1200
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= max_count:
        raise HTTPException(status_code=422, detail=f"count must be an integer between 1 and {max_count}.")

    real_time_required = body.get("real_time_required", True)
    if not isinstance(real_time_required, bool):
        raise HTTPException(status_code=422, detail="real_time_required must be a boolean.")

    forwarded: dict[str, Any] = {"symbols": cleaned, "category": category, "timespan": timespan,
                                 "count": count, "real_time_required": real_time_required}
    if body.get("trading_sessions") is not None:
        forwarded["trading_sessions"] = body["trading_sessions"]
    return forwarded


# These two routes are already verified by the project owner on UAT; keep the paths intact.
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
    return _request(("/market-data/stocks/snapshots/list", "/openapi/market-data/stock/snapshot"), params={
        "symbols": ",".join(symbol_list), "category": category,
        "extend_hour_required": extend_hour_required, "overnight_required": overnight_required,
    })


@router.post("/stocks/bars")
def stock_bars(body: dict[str, Any]) -> Any:
    return _request(_STOCK_BARS_PATHS, method="POST", body=_validate_stock_bars(body))


@router.post("/stocks/bars/batch")
def stock_bars_batch(body: dict[str, Any]) -> Any:
    """Alias of /stocks/bars with identical validation (kept for client compatibility)."""
    return _request(_STOCK_BARS_PATHS, method="POST", body=_validate_stock_bars(body))


@router.get("/stocks/bars/single")
def stock_bars_single(request: Request) -> Any:
    params = _query(request, default_category="US_STOCK", require_symbol=True)
    return _request(("/openapi/market-data/stock/bars", "/market-data/stocks/bars/get"), params=params)


@router.get("/stocks/ticks")
def stock_ticks(request: Request) -> Any:
    params = _query(request, default_category="US_STOCK", require_symbol=True)
    return _request(("/market-data/stocks/ticks/list", "/openapi/market-data/stock/tick"), params=params)


@router.get("/stocks/quotes")
def stock_quotes(request: Request) -> Any:
    params = _query(request, default_category="US_STOCK", require_symbol=True)
    return _request(("/market-data/stocks/depths/list", "/openapi/market-data/stock/quotes"), params=params)


@router.get("/stocks/footprints")
def stock_footprints(request: Request) -> Any:
    params = _query(request, default_category="US_STOCK", require_symbol=True)
    return _request(("/market-data/stocks/footprints/list", "/openapi/market-data/stock/footprint"), params=params)


# ============================== OPTIONS MARKET DATA ==============================
def _option_symbols(symbols: str) -> str:
    values = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    if not values or len(values) > 20 or len(set(values)) != len(values):
        raise HTTPException(status_code=422, detail="Provide 1–20 unique option symbols, comma-separated.")
    return ",".join(values)


@router.get("/options/contracts")
def option_contracts(request: Request) -> Any:
    params = _query(request)
    if not any(params.get(k) for k in ("symbol", "underlying_symbol", "underlying", "symbols")):
        raise HTTPException(status_code=422, detail="Provide the underlying symbol to search option contracts.")
    return _request(("/trading/instruments/options/contracts/list", "/trading/instruments/options/contracts/get",
                     "/market-data/options/contracts/list", "/openapi/market-data/option/contracts"), params=params)


@router.get("/options/snapshots")
def option_snapshots(symbols: str = Query(..., min_length=1, max_length=2000)) -> Any:
    return _request(("/market-data/options/snapshots/list", "/openapi/market-data/option/snapshot"),
                    params={"symbols": _option_symbols(symbols), "category": "US_OPTION"})


@router.get("/options/bars")
def option_bars(
    symbols: str = Query(..., min_length=1, max_length=2000),
    timespan: str = Query("D", pattern="^(M1|M5|M15|M30|M60|M120|M240|D|W|M|Y)$"),
    count: int = Query(200, ge=1, le=1200),
    real_time_required: bool = False,
) -> Any:
    params = {"symbols": _option_symbols(symbols), "category": "US_OPTION", "timespan": timespan,
              "count": count, "real_time_required": real_time_required}
    return _request(("/market-data/options/bars/list", "/openapi/market-data/option/bars"), params=params)


@router.get("/options/ticks")
def option_ticks(request: Request) -> Any:
    params = _query(request, default_category="US_OPTION", require_symbol=True)
    return _request(("/market-data/options/ticks/list", "/openapi/market-data/option/tick"), params=params)


# ============================== SCREENER ==============================
def _screener_paths(slug: str) -> tuple[str, ...]:
    return (f"/market-data/stocks/screener/{slug}", f"/market-data/screener/{slug}",
            f"/openapi/market-data/screener/{slug}")


def _screener_get(slug: str, request: Request) -> Any:
    return _request(_screener_paths(slug), params=_query(request, default_category="US_STOCK"))


@router.get("/screener/gainers-losers")
def screener_gainers_losers(request: Request) -> Any:
    return _screener_get("gainers-losers", request)


@router.get("/screener/top-active")
def screener_top_active(request: Request) -> Any:
    return _screener_get("top-active", request)


@router.get("/screener/market-sectors")
def screener_market_sectors(request: Request) -> Any:
    return _screener_get("market-sectors", request)


@router.get("/screener/market-sectors/detail")
def screener_market_sectors_detail(request: Request) -> Any:
    return _screener_get("market-sectors/detail", request)


@router.get("/screener/high-dividend")
def screener_high_dividend(request: Request) -> Any:
    return _screener_get("high-dividend", request)


@router.get("/screener/52-week-high-low")
def screener_52_week_high_low(request: Request) -> Any:
    return _screener_get("52-week-high-low", request)


# ============================== WATCHLISTS ==============================
@router.get("/watchlists")
def watchlists_list(request: Request) -> Any:
    return _request(("/market-data/watchlists/list", "/openapi/market-data/watchlist/list"), params=_query(request))


@router.get("/watchlists/instruments")
def watchlist_instruments(request: Request) -> Any:
    params = _query(request)
    if not params.get("watchlist_id") and not params.get("id"):
        raise HTTPException(status_code=422, detail="watchlist_id is required.")
    return _request(("/market-data/watchlists/instruments/list", "/openapi/market-data/watchlist/instruments/list"),
                    params=params)


def _watchlist_write(paths: tuple[str, ...], body: dict[str, Any]) -> Any:
    _require_mutation_flag("WEBULL_UAT_WATCHLIST_WRITES_ENABLED", "Webull watchlist writes")
    return _request(paths, method="POST", body=body)


@router.post("/watchlists/create")
def watchlists_create(body: dict[str, Any]) -> Any:
    return _watchlist_write(("/market-data/watchlists/create", "/openapi/market-data/watchlist/create"), body)


@router.post("/watchlists/update")
def watchlists_update(body: dict[str, Any]) -> Any:
    return _watchlist_write(("/market-data/watchlists/update", "/openapi/market-data/watchlist/update"), body)


@router.post("/watchlists/delete")
def watchlists_delete(body: dict[str, Any]) -> Any:
    return _watchlist_write(("/market-data/watchlists/delete", "/openapi/market-data/watchlist/delete"), body)


@router.post("/watchlists/instruments/add")
def watchlist_add_instruments(body: dict[str, Any]) -> Any:
    return _watchlist_write(("/market-data/watchlists/instruments/add",
                             "/openapi/market-data/watchlist/instruments/add"), body)


@router.post("/watchlists/instruments/remove")
def watchlist_remove_instruments(body: dict[str, Any]) -> Any:
    return _watchlist_write(("/market-data/watchlists/instruments/remove",
                             "/openapi/market-data/watchlist/instruments/remove"), body)


@router.post("/watchlists/instruments/sort-order")
def watchlist_sort_instruments(body: dict[str, Any]) -> Any:
    return _watchlist_write(("/market-data/watchlists/instruments/update-sort-order",
                             "/openapi/market-data/watchlist/instruments/sort-order"), body)


# ============================== STOCK / ETF FUNDAMENTALS (23 interfaces) ==============================
# The first path candidate follows the Thailand UAT reference URLs supplied by the user.
# Alternative candidates are tried only when Webull returns 404/405, to tolerate API-version differences.
_FUNDAMENTAL_PATHS: dict[str, tuple[tuple[str, ...], str]] = {
    "company-profile": (("/market-data/fundamentals/company-profiles/get", "/openapi/instrument/company/profile"), "US_STOCK"),
    "analyst-target-price": (("/market-data/fundamentals/analysis/target-prices/get", "/openapi/instrument/analyst/target-price"), "US_STOCK"),
    "analyst-rating": (("/market-data/fundamentals/analysis/ratings/get", "/openapi/instrument/analyst/rating"), "US_STOCK"),
    "forecast-eps": (("/market-data/fundamentals/forecast-eps/get", "/openapi/instrument/forecast/eps"), "US_STOCK"),
    "filings": (("/market-data/fundamentals/filings/list", "/openapi/instrument/filings/list", "/openapi/instrument/filings"), "US_STOCK"),
    "earnings-calendar": (("/market-data/fundamentals/earnings-calendars/list", "/openapi/instrument/earnings-calendar", "/openapi/instrument/earnings/calendar"), "US_STOCK"),
    "dividend-calendar": (("/market-data/fundamentals/dividend-calendars/list", "/openapi/instrument/dividend-calendar", "/openapi/instrument/dividend/calendar"), "US_STOCK"),
    "capital-flow": (("/market-data/fundamentals/capital-flows/get", "/openapi/instrument/capital-flow"), "US_STOCK"),
    "industry-comparison": (("/market-data/fundamentals/industry-comparisons/get", "/openapi/instrument/industry-comparison", "/openapi/instrument/industry/comparison"), "US_STOCK"),
    "financial-indicators": (("/market-data/fundamentals/indicators/get", "/openapi/instrument/financial-indicators", "/openapi/instrument/financial/indicators"), "US_STOCK"),
    "income-statement": (("/market-data/fundamentals/income-statements/get", "/openapi/instrument/financial-income", "/openapi/instrument/financial/income"), "US_STOCK"),
    "cash-flow": (("/market-data/fundamentals/cash-flows/get", "/openapi/instrument/financial-cashflow", "/openapi/instrument/financial/cash-flow"), "US_STOCK"),
    "balance-sheet": (("/market-data/fundamentals/balance-sheets/get", "/openapi/instrument/financial-balancesheet", "/openapi/instrument/financial/balance-sheet"), "US_STOCK"),
    "financial-alert": (("/market-data/fundamentals/financial-alerts/get", "/openapi/instrument/financial-alert", "/openapi/instrument/financial/alert"), "US_STOCK"),
    "fund-brief": (("/market-data/fundamentals/fund-brief/get", "/openapi/instrument/fund/brief"), "US_ETF"),
    "fund-performance": (("/market-data/fundamentals/fund-performances/get", "/openapi/instrument/fund/performance"), "US_ETF"),
    "fund-net-value": (("/market-data/fundamentals/fund-net-values/get", "/openapi/instrument/fund/net-value"), "US_ETF"),
    "fund-holdings": (("/market-data/fundamentals/fund-holdings/get", "/openapi/instrument/fund/holdings"), "US_ETF"),
    "fund-dividends": (("/market-data/fundamentals/fund-dividends/get", "/openapi/instrument/fund/dividends"), "US_ETF"),
    "fund-rating": (("/market-data/fundamentals/fund-ratings/get", "/openapi/instrument/fund/rating"), "US_ETF"),
    "fund-splits": (("/market-data/fundamentals/fund-splits/get", "/openapi/instrument/fund/splits"), "US_ETF"),
    "fund-files": (("/market-data/fundamentals/fund-files/get", "/openapi/instrument/fund/files"), "US_ETF"),
    "fund-allocation": (("/market-data/fundamentals/fund-allocations/get", "/openapi/instrument/fund/allocation"), "US_ETF"),
}


def _fundamental_handler(slug: str, path_candidates: tuple[str, ...], category: str) -> Callable[[Request], Any]:
    def endpoint(request: Request) -> Any:
        params = _query(request, default_category=category, require_symbol=True)
        return _request(path_candidates, params=params)
    endpoint.__name__ = "fundamentals_" + slug.replace("-", "_")
    endpoint.__doc__ = f"Read-only Webull Fundamentals: {slug}."
    return endpoint


for _slug, (_paths, _category) in _FUNDAMENTAL_PATHS.items():
    router.add_api_route(
        f"/fundamentals/{_slug}", _fundamental_handler(_slug, _paths, _category),
        methods=["GET"], name=f"fundamentals_{_slug.replace('-', '_')}",
    )


# ============================== ORDER QUERIES ==============================
@router.get("/orders/open")
def open_orders(
    account_id: str = Query(..., min_length=1, max_length=100),
    pagination_key: str | None = None,
) -> Any:
    return _request("/trading/orders/open-orders/list",
                    params={"account_id": account_id, "pagination_key": pagination_key})


@router.get("/orders/history")
def order_history(
    account_id: str = Query(..., min_length=1, max_length=100),
    start_time: str | None = None,
    end_time: str | None = None,
    pagination_key: str | None = None,
) -> Any:
    return _request("/trading/orders/historical-orders/list", params={
        "account_id": account_id, "start_time": start_time,
        "end_time": end_time, "pagination_key": pagination_key,
    })


@router.get("/orders/detail")
def order_detail(
    account_id: str = Query(..., min_length=1, max_length=100),
    client_order_id: str = Query(..., min_length=1, max_length=32),
) -> Any:
    return _request("/trading/orders/get", params={"account_id": account_id, "client_order_id": client_order_id})


# ============================== ORDER ACTIONS (UAT, flag-gated) ==============================
@router.post("/orders/preview")
def order_preview(body: dict[str, Any]) -> Any:
    """Preview is non-submitting, but still validates/estimates against UAT only."""
    account_id = _body_account_id(body)
    return _request("/trading/orders/preview", method="POST", params={"account_id": account_id}, body=body)


def _order_mutation(path: str, purpose: str, body: dict[str, Any]) -> Any:
    _require_mutation_flag("WEBULL_UAT_ORDER_ACTIONS_ENABLED", purpose)
    account_id = _body_account_id(body)
    _check_account_allowed(account_id, "order actions")
    return _request(path, method="POST", params={"account_id": account_id}, body=body)


@router.post("/orders/place")
def order_place(body: dict[str, Any]) -> Any:
    return _order_mutation("/trading/orders/place", "UAT order placement", body)


@router.post("/orders/replace")
def order_replace(body: dict[str, Any]) -> Any:
    return _order_mutation("/trading/orders/replace", "UAT order replacement", body)


@router.post("/orders/cancel")
def order_cancel(body: dict[str, Any]) -> Any:
    return _order_mutation("/trading/orders/cancel", "UAT order cancellation", body)


# ============================== MARKET-DATA STREAMING CONTROL ==============================
@router.post("/streaming/subscribe")
def streaming_subscribe(body: dict[str, Any]) -> Any:
    return _request(("/market-data/streaming/subscribe", "/openapi/market-data/streaming/subscribe"),
                    method="POST", body=body)


@router.post("/streaming/unsubscribe")
def streaming_unsubscribe(body: dict[str, Any]) -> Any:
    return _request(("/market-data/streaming/unsubscribe", "/openapi/market-data/streaming/unsubscribe"),
                    method="POST", body=body)


# ============================== gRPC TRADE / POSITION EVENTS ==============================
def _events_host() -> str:
    return os.getenv("WEBULL_EVENTS_HOST", WEBULL_EVENTS_HOST_DEFAULT).strip() or WEBULL_EVENTS_HOST_DEFAULT


def _jsonable(value: Any) -> Any:
    """Convert protobuf/arbitrary SDK objects into JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")[:5000]
        except UnicodeDecodeError:
            return f"<{len(value)} bytes>"
    try:
        from google.protobuf.json_format import MessageToDict
        from google.protobuf.message import Message
        if isinstance(value, Message):
            return MessageToDict(value, preserving_proto_field_name=True)
    except ImportError:
        pass
    return str(value)[:5000]


def _set_worker(account_id: str, **fields: Any) -> None:
    with _EVENT_LOCK:
        _EVENT_WORKERS.setdefault(account_id, {}).update(fields)


def _event_worker(account_id: str) -> None:
    host = _events_host()
    try:
        app_key, app_secret = _app_credentials()
        from webull.trade.trade_events_client import TradeEventsClient

        # NOTE: verify the constructor signature in SDK 3.0.3 (site-packages) accepts host=.
        client = TradeEventsClient(app_key, app_secret, WEBULL_REGION, host=host)

        def on_events_message(event_type: Any, subscribe_type: Any, payload: Any, raw_message: Any) -> None:
            row = {
                "account_id_suffix": account_id[-4:],
                "_account_id": account_id,  # internal only; stripped before responding
                "event_type": str(event_type),
                "subscribe_type": str(subscribe_type),
                "payload": _jsonable(payload),
                "received_at": int(time.time() * 1000),
            }
            with _EVENT_LOCK:
                _EVENT_ROWS.append(row)
                worker = _EVENT_WORKERS.setdefault(account_id, {})
                worker["status"] = "RUNNING"
                worker["last_event_at"] = row["received_at"]

        client.on_events_message = on_events_message
        _set_worker(account_id, status="CONNECTING", started_at=int(time.time()), host=host)
        client.do_subscribe([account_id])  # blocks until the stream ends
        _set_worker(account_id, status="STOPPED", stopped_at=int(time.time()))
    except Exception as exc:
        error_type = "NotConfigured" if isinstance(exc, HTTPException) else type(exc).__name__
        _set_worker(account_id, status="ERROR", error_type=error_type,
                    stopped_at=int(time.time()), host=host)
        _log.warning("Webull gRPC event worker failed for account suffix=%s type=%s", account_id[-4:], error_type)


@router.post("/events/start")
def start_event_stream(body: dict[str, Any]) -> dict[str, Any]:
    _require_mutation_flag("WEBULL_UAT_EVENTS_ENABLED", "Webull UAT event subscription")
    account_id = _body_account_id(body)
    _check_account_allowed(account_id, "event subscriptions")
    with _EVENT_LOCK:
        worker = _EVENT_WORKERS.get(account_id)
        if worker and worker.get("status") in {"STARTING", "CONNECTING", "RUNNING"}:
            return {"status": worker.get("status"), "account_id_suffix": account_id[-4:], "already_started": True}
        _EVENT_WORKERS[account_id] = {"status": "STARTING", "started_at": int(time.time()), "host": _events_host()}
    thread = Thread(target=_event_worker, args=(account_id,), daemon=True, name=f"webull-events-{account_id[-4:]}")
    thread.start()
    return {"status": "STARTING", "account_id_suffix": account_id[-4:], "host": _events_host()}


@router.get("/events/status")
def event_stream_status() -> dict[str, Any]:
    with _EVENT_LOCK:
        return {"enabled": _flag_enabled("WEBULL_UAT_EVENTS_ENABLED"),
                "workers": [{"account_id_suffix": key[-4:], **value} for key, value in _EVENT_WORKERS.items()],
                "buffered_events": len(_EVENT_ROWS), "storage": "in-memory; cleared on process restart"}


@router.get("/events/recent")
def recent_events(limit: int = Query(50, ge=1, le=200), account_id: str | None = None) -> dict[str, Any]:
    with _EVENT_LOCK:
        rows = list(_EVENT_ROWS)
    if account_id:
        rows = [row for row in rows if row.get("_account_id") == account_id]
    rows = [{k: v for k, v in row.items() if k != "_account_id"} for row in rows[-limit:]]
    return {"count": len(rows), "events": rows}


# ============================== MANIFEST ==============================
# Endpoint manifest visible for local diagnostics; does not make upstream calls.
@router.get("/manifest")
def endpoint_manifest() -> dict[str, Any]:
    return {
        "environment": "UAT", "upstream_host": WEBULL_HOST,
        "covered_groups": {
            "authentication": ["token/create", "token/check", "status"],
            "account_read": ["accounts", "account/balance", "positions", "stocks/instruments"],
            "stocks_market_data": ["stocks/snapshots", "stocks/bars", "stocks/ticks", "stocks/quotes",
                                   "stocks/footprints", "stocks/bars/batch", "stocks/bars/single"],
            "options_market_data": ["options/contracts", "options/snapshots", "options/bars", "options/ticks"],
            "screeners": ["screener/gainers-losers", "screener/top-active", "screener/market-sectors",
                          "screener/market-sectors/detail", "screener/high-dividend", "screener/52-week-high-low"],
            "watchlists": ["watchlists", "watchlists/instruments", "watchlists/create", "watchlists/update",
                           "watchlists/delete", "watchlists/instruments/add", "watchlists/instruments/remove",
                           "watchlists/instruments/sort-order"],
            "fundamentals": sorted(_FUNDAMENTAL_PATHS.keys()),
            "orders": ["orders/open", "orders/history", "orders/detail", "orders/preview",
                       "orders/place", "orders/replace", "orders/cancel"],
            "streaming": ["streaming/subscribe", "streaming/unsubscribe"],
            "events": ["events/start", "events/status", "events/recent"],
        },
        "safety": {"host_pinned_to_uat": True, "order_mutations_default_disabled": True,
                   "watchlist_mutations_default_disabled": True,
                   "account_allowlist_applies_to": ["orders/place", "orders/replace", "orders/cancel", "events/start"],
                   "credentials_or_token_returned": False},
        "unverified_upstream_paths": "new routes must be verified against the user's UAT access; "
                                     "compatible path candidates fall back only on 404/405",
    }
