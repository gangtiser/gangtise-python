from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import httpx

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError

logger = logging.getLogger("gangtise_openapi")

RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
RETRYABLE_API_CODES: frozenset[str] = frozenset({"999999"})
_RETRYABLE_HTTPX_EXC: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
)


def build_sync_client(config: Config) -> httpx.Client:
    timeout = httpx.Timeout(config.timeout_ms / 1000.0)
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=16, keepalive_expiry=60)
    return httpx.Client(base_url=config.base_url, timeout=timeout, limits=limits)


def _success_code(code: Any) -> bool:
    return str(code) in {"000000", "0"}


def is_envelope(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if "code" not in payload:
        return False
    return any(k in payload for k in ("msg", "data", "success", "status"))


def unwrap_envelope(payload: Any, status_code: int | None = None) -> Any:
    if not is_envelope(payload):
        return payload
    code = payload.get("code")
    code_str = str(code) if code is not None else None
    ok = (
        payload.get("status") is True
        or payload.get("success") is True
        or _success_code(code)
    )
    if not ok:
        raise ApiError(
            payload.get("msg") or "API request failed",
            code=code_str,
            status_code=status_code,
            details=payload,
        )
    return payload.get("data") if "data" in payload else payload


def is_retryable_error(error: BaseException) -> bool:
    if isinstance(error, ApiError):
        if error.status_code in RETRYABLE_HTTP_STATUS:
            return True
        return error.code in RETRYABLE_API_CODES
    return isinstance(error, _RETRYABLE_HTTPX_EXC)


def _backoff_delay(attempt: int, base_ms: float = 400.0, max_ms: float = 4000.0) -> float:
    jitter = random.random() * base_ms
    raw_ms: float = base_ms * float(2 ** attempt) + jitter
    return min(max_ms, raw_ms) / 1000.0


def _do_request(
    http: httpx.Client,
    config: Config,
    endpoint: EndpointDef,
    body: Any,
    *,
    token: str | None,
    query: dict[str, str | int] | None,
) -> tuple[int, Any]:
    headers: dict[str, str] = {"content-type": "application/json"}
    if token is not None:
        headers["Authorization"] = normalize_token(token)
    started = time.monotonic()
    response = http.request(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
        content=None if endpoint.method == "GET" else json.dumps(body or {}).encode("utf8"),
    )
    elapsed_ms = (time.monotonic() - started) * 1000.0
    logger.debug(
        "[gangtise] %5.0fms %s %s (status=%s, bytes=%s)",
        elapsed_ms,
        endpoint.method,
        endpoint.path,
        response.status_code,
        len(response.content),
    )
    try:
        parsed = response.json()
    except ValueError as err:
        if response.status_code >= 400:
            raise ApiError(
                f"API request failed (HTTP {response.status_code})",
                status_code=response.status_code,
                details=response.text[:500],
            ) from err
        raise ApiError(
            "Failed to parse API response",
            status_code=response.status_code,
            details=response.text[:500],
        ) from err
    return response.status_code, parsed


def request_json(
    http: httpx.Client,
    config: Config,
    endpoint: EndpointDef,
    *,
    body: Any = None,
    token: str | None,
    query: dict[str, str | int] | None = None,
    max_retries: int = 2,
) -> Any:
    attempt = 0
    while True:
        try:
            status_code, parsed = _do_request(
                http, config, endpoint, body, token=token, query=query
            )
            if status_code >= 400:
                if is_envelope(parsed):
                    code = parsed.get("code")
                    raise ApiError(
                        parsed.get("msg") or f"API request failed (HTTP {status_code})",
                        code=str(code) if code is not None else None,
                        status_code=status_code,
                        details=parsed,
                    )
                raise ApiError(
                    f"API request failed (HTTP {status_code})",
                    status_code=status_code,
                    details=parsed,
                )
            return unwrap_envelope(parsed, status_code=status_code)
        except Exception as error:
            if attempt >= max_retries or not is_retryable_error(error):
                raise
            time.sleep(_backoff_delay(attempt))
            attempt += 1
