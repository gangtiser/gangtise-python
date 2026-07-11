from __future__ import annotations

import json
import time
from typing import Any

import anyio
import httpx

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError
from gangtise_openapi._logging import get_logger
from gangtise_openapi._transport import (
    USER_AGENT,
    _apply_ede_hint,
    _effective_timeout,
    _retry_delay,
    is_envelope,
    is_retryable_error,
    parse_retry_after_ms,
    unwrap_envelope,
)

logger = get_logger()


def build_async_client(config: Config) -> httpx.AsyncClient:
    timeout = httpx.Timeout(config.timeout_ms / 1000.0)
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=16, keepalive_expiry=60)
    return httpx.AsyncClient(base_url=config.base_url, timeout=timeout, limits=limits)


async def _do_request(
    http: httpx.AsyncClient,
    endpoint: EndpointDef,
    body: Any,
    *,
    token: str | None,
    query: dict[str, str | int] | None,
) -> tuple[int, Any, float | None]:
    headers: dict[str, str] = {"content-type": "application/json", "user-agent": USER_AGENT}
    if token is not None:
        headers["Authorization"] = normalize_token(token)
    timeout = _effective_timeout(http, endpoint)
    started = time.monotonic()
    response = await http.request(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
        content=None if endpoint.method == "GET" else json.dumps(body or {}).encode("utf8"),
        timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
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
    # Parse Retry-After once so every error path (JSON parse failure AND the
    # envelope/HTTP-error raise in request_json_async) carries it — a non-JSON
    # 429/503 must still honor the server's rate window instead of default backoff.
    retry_after_ms = parse_retry_after_ms(response.headers.get("retry-after"), time.time())
    try:
        parsed = response.json()
    except ValueError as err:
        if response.status_code >= 400:
            raise ApiError(
                f"API request failed (HTTP {response.status_code})",
                status_code=response.status_code,
                details=response.text[:500],
                retry_after_ms=retry_after_ms,
            ) from err
        raise ApiError(
            "Failed to parse API response",
            status_code=response.status_code,
            details=response.text[:500],
            retry_after_ms=retry_after_ms,
        ) from err
    return response.status_code, parsed, retry_after_ms


async def request_json_async(
    http: httpx.AsyncClient,
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
            status_code, parsed, retry_after_ms = await _do_request(
                http, endpoint, body, token=token, query=query
            )
            if status_code >= 400:
                if is_envelope(parsed):
                    code = parsed.get("code")
                    raise ApiError(
                        parsed.get("msg") or f"API request failed (HTTP {status_code})",
                        code=str(code) if code is not None else None,
                        status_code=status_code,
                        details=parsed,
                        retry_after_ms=retry_after_ms,
                    )
                raise ApiError(
                    f"API request failed (HTTP {status_code})",
                    status_code=status_code,
                    details=parsed,
                    retry_after_ms=retry_after_ms,
                )
            return unwrap_envelope(parsed, status_code=status_code)
        except Exception as error:
            if attempt >= max_retries or not is_retryable_error(error, endpoint.retry):
                _apply_ede_hint(endpoint, error)
                raise
            await anyio.sleep(_retry_delay(error, attempt))
            attempt += 1
