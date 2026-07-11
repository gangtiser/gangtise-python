from __future__ import annotations

import json
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from gangtise_openapi.__about__ import __version__
from gangtise_openapi._auth import normalize_token
from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef, RetryPolicy
from gangtise_openapi._errors import EDE_NO_DATA_HINT, ApiError
from gangtise_openapi._logging import get_logger

logger = get_logger()

USER_AGENT = f"gangtise-openapi-python/{__version__}"

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
# Connect-phase / pool failures: the request provably never reached the server, so
# a replay cannot double-execute (or double-bill) anything even under "no-replay".
_CONNECT_PHASE_EXC: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

# A Retry-After delay is honored even beyond the backoff cap — but never past this
# ceiling, so a hostile/misconfigured header can't stall the caller for minutes.
RETRY_AFTER_CEILING_MS = 60_000.0


def parse_retry_after_ms(value: str | None, now: float) -> float | None:
    """Parse a Retry-After header (delta-seconds or an HTTP-date) into a delay in
    ms. Returns None when absent or unparseable. ``now`` is epoch seconds."""
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.isascii() and raw.isdigit():
        return float(raw) * 1000.0
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, parsed.timestamp() - now) * 1000.0


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
    ok = payload.get("status") is True or payload.get("success") is True or _success_code(code)
    if not ok:
        raise ApiError(
            payload.get("msg") or "API request failed",
            code=code_str,
            status_code=status_code,
            details=payload,
        )
    return payload.get("data") if "data" in payload else payload


def is_retryable_error(error: BaseException, policy: RetryPolicy = "default") -> bool:
    """Whether the retry loop may resend after ``error`` under ``policy``.

    "no-replay" (per-call billed endpoints): only 429 (rejected before
    processing) and connect-phase failures (request never sent) retry —
    5xx / response timeouts / 999999 fail fast so a request the server may have
    executed is never re-billed. The client-level token self-heal sits outside
    this loop and is unaffected. "no-999999" (EDE): the no-data code 999999 is
    not retried; everything else follows the default policy.
    """
    if isinstance(error, ApiError):
        if error.status_code == 429:
            return True
        if policy == "no-replay":
            return False
        if error.code in RETRYABLE_API_CODES:
            return policy != "no-999999"
        return error.status_code in RETRYABLE_HTTP_STATUS
    if policy == "no-replay":
        return isinstance(error, _CONNECT_PHASE_EXC)
    return isinstance(error, _RETRYABLE_HTTPX_EXC)


def is_transient_error(error: BaseException) -> bool:
    """Errors worth waiting out (anything the default policy would retry):
    transient 5xx / network / timeout / 429 / 999999. Used by async polling to
    survive a blip without abandoning a multi-minute wait."""
    return is_retryable_error(error, "default")


def _backoff_delay(attempt: int, base_ms: float = 400.0, max_ms: float = 4000.0) -> float:
    jitter = random.random() * base_ms
    raw_ms: float = base_ms * float(2**attempt) + jitter
    return min(max_ms, raw_ms) / 1000.0


def _retry_delay(error: BaseException, attempt: int) -> float:
    """Seconds to sleep before the next attempt: a server-sent Retry-After wins
    over exponential backoff (capped by RETRY_AFTER_CEILING_MS)."""
    retry_after = getattr(error, "retry_after_ms", None)
    if isinstance(retry_after, (int, float)) and retry_after >= 0:
        return min(float(retry_after), RETRY_AFTER_CEILING_MS) / 1000.0
    return _backoff_delay(attempt)


def _effective_timeout(
    http: httpx.Client | httpx.AsyncClient, endpoint: EndpointDef
) -> httpx.Timeout | None:
    """Per-endpoint timeout floor (TS ``resolveTimeoutMs``): lift the request
    timeout to ``endpoint.timeout_ms``, never lowering a higher client-level
    timeout. None means "use the client default"."""
    if endpoint.timeout_ms is None:
        return None
    floor_s = endpoint.timeout_ms / 1000.0
    read = http.timeout.read
    if read is None or read >= floor_s:
        return None
    return httpx.Timeout(floor_s)


def _do_request(
    http: httpx.Client,
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
    response = http.request(
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
    # envelope/HTTP-error raise in request_json) carries it — a non-JSON 429/503
    # must still honor the server's rate window instead of default backoff.
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


def request_json(
    http: httpx.Client,
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
            status_code, parsed, retry_after_ms = _do_request(
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
            time.sleep(_retry_delay(error, attempt))
            attempt += 1


def _apply_ede_hint(endpoint: EndpointDef, error: BaseException) -> None:
    """EDE uses 999999 for "no data for this query" (probed 2026-07-11) — the
    generic "system error, retry later" hint would send the user retrying a
    query that will never have data. Swap in a context-specific hint."""
    if endpoint.retry == "no-999999" and isinstance(error, ApiError) and error.code == "999999":
        error.hint = EDE_NO_DATA_HINT
