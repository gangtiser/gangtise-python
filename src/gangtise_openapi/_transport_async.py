from __future__ import annotations

import time
from typing import Any

import anyio
import httpx

from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError
from gangtise_openapi._logging import get_logger
from gangtise_openapi._transport import (
    UploadFile,
    _apply_policy_hint,
    _build_request,
    _deadline_exceeded,
    _parse_response,
    _retry_delay,
    check_expected_shape,
    is_envelope,
    is_retryable_error,
    request_deadline_seconds,
    unwrap_envelope,
)

logger = get_logger()


def build_async_client(config: Config) -> httpx.AsyncClient:
    timeout = httpx.Timeout(config.timeout_ms / 1000.0)
    # Never fewer sockets than the fan-out width, or GANGTISE_PAGE_CONCURRENCY above
    # the pool size would only queue requests inside httpx (TS v0.42.0).
    pool = max(16, config.page_concurrency)
    limits = httpx.Limits(max_connections=pool, max_keepalive_connections=pool, keepalive_expiry=60)
    return httpx.AsyncClient(base_url=config.base_url, timeout=timeout, limits=limits)


async def _do_request(
    http: httpx.AsyncClient,
    endpoint: EndpointDef,
    body: Any,
    *,
    token: str | None,
    query: dict[str, str | int] | None,
) -> tuple[int, Any, float | None]:
    request = _build_request(http, endpoint, body, token=token, query=query)
    limit = request_deadline_seconds(http, endpoint, transfer=isinstance(body, UploadFile))
    started = time.monotonic()
    chunks: list[bytes] = []
    try:
        # The whole attempt — sending the body, waiting for the headers, reading the
        # body — sits under one deadline, like the CLI's AbortSignal: a server trickling
        # its HEADERS resets httpx's idle timeout just as a trickled body does.
        with anyio.fail_after(limit):
            response = await http.send(request, stream=True)
            try:
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                    if time.monotonic() - started > limit:
                        raise _deadline_exceeded(request, limit)
            finally:
                with anyio.CancelScope(shield=True):
                    await response.aclose()
    except TimeoutError:
        raise _deadline_exceeded(request, limit) from None
    elapsed_ms = (time.monotonic() - started) * 1000.0
    return _parse_response(
        endpoint, response.status_code, response.headers, b"".join(chunks), elapsed_ms
    )


async def request_json_async(
    http: httpx.AsyncClient,
    endpoint: EndpointDef,
    *,
    body: Any = None,
    token: str | None,
    query: dict[str, str | int] | None = None,
    max_retries: int = 2,
    attempts: list[int] | None = None,
) -> Any:
    # ``attempts`` lets a caller that replays one logical request (the client's auth
    # recovery) share ONE transient-retry budget across those sends, as the CLI's
    # withRetry does — otherwise each replay would start a fresh budget.
    budget = attempts if attempts is not None else [0]
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
            payload = unwrap_envelope(
                parsed, status_code=status_code, retry_after_ms=retry_after_ms
            )
            return check_expected_shape(endpoint, payload, status_code, parsed)
        except Exception as error:
            if budget[0] >= max_retries or not is_retryable_error(error, endpoint.retry):
                _apply_policy_hint(endpoint, error)
                raise
            await anyio.sleep(_retry_delay(error, budget[0]))
            budget[0] += 1
