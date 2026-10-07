from __future__ import annotations

import datetime as dt
import json
import random
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from gangtise_openapi.__about__ import __version__
from gangtise_openapi._auth import normalize_token
from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef, RetryPolicy
from gangtise_openapi._errors import (
    EDE_NO_DATA_HINT,
    NO_REPLAY_SIDE_EFFECT_HINT,
    NO_REPLAY_UNCERTAIN_HINT,
    ApiError,
)
from gangtise_openapi._logging import get_logger

logger = get_logger()

USER_AGENT = f"gangtise-openapi-python/{__version__}"

RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
RETRYABLE_API_CODES: frozenset[str] = frozenset({"999999"})
# Never replayed on any HTTP status, outranking the 429 and 5xx rules:
# - 999011 (CREDENTIAL_INVALID): bad AK/SK, only ever from auth.login — which runs
#   unauthenticated and so never consults AUTH_RETRY_CODES, and declares no retry
#   policy. Without this a 5xx would be replayed twice for a credential that will
#   not fix itself.
# - 140002 (PROCESSING_FAILED, the new code for 410111): the async *-check
#   endpoints declare no retry policy, so a 140002@500 would be retried twice by
#   the default policy BEFORE _async_content's terminal check gets to call it
#   terminal — that guard sits above this retry loop and cannot see the retries.
#   The code means "generation failed" (terminal by definition) and only those
#   async endpoints return it, so a blanket rule is safe and skips the waste.
TERMINAL_API_CODES: frozenset[str] = frozenset({"999011", "140002"})
# Auth errors the CLIENT recovers from (a token someone else refreshed, else one login;
# see _client._recover_token). 0000001008 is the legacy code (probed 2026-09-12: still
# what the token filter emits); 999002 TOKEN_INVALID is its 2026-07-17 replacement,
# listed ahead of the rollout; 8000014/8000015 are the retired AK/SK codes. Never
# retried HERE, whatever the HTTP status: resending the rejected token cannot succeed,
# and each such resend would spend the transient-retry budget the recovered request
# still needs (the CLI recovers inside the same attempt, before classifying a retry).
# 999011 (bad AK/SK, only from the unauthenticated auth.login) is deliberately absent —
# see TERMINAL_API_CODES.
AUTH_RETRY_CODES: frozenset[str] = frozenset({"8000014", "8000015", "0000001008", "999002"})
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


@dataclass(frozen=True)
class UploadFile:
    """One multipart part for an ``upload``-kind endpoint.

    Passed as the request ``body`` so the upload shares ``request_json``'s auth,
    retry policy and envelope handling instead of forking a second request path.
    """

    filename: str
    data: bytes
    content_type: str = "application/octet-stream"
    # Plain text form fields sent next to the file (vault.drive.upload's spaceType /
    # folderId / title). Pairs rather than a dict so the dataclass stays hashable.
    fields: tuple[tuple[str, str], ...] = ()


def quote_big_int_fields(text: str, fields: tuple[str, ...]) -> str:
    """Re-quote the BARE numeric value of each named field before parsing.

    Unlike JS, Python parses arbitrarily large JSON integers exactly, so this is
    not a precision fix here — it is a TYPE-stability guard. A snowflake ID that
    arrives quoted on one call and bare on the next would otherwise reach the
    caller as ``str`` then ``int``, and an id that changes type breaks dict keys,
    equality checks and the string the SDK has to echo back. Pinning the declared
    fields to ``str`` makes the shape independent of the server's serializer.

    Values already in quotes are left alone: the pattern only matches a bare
    number immediately after the key.
    """
    if not fields:
        return text
    out = text
    for field in fields:
        out = re.sub(rf'("{re.escape(field)}"\s*:\s*)(-?\d+)', r'\1"\2"', out)
    return out


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
    if parsed.tzinfo is None:
        # An HTTP-date is GMT by definition; ``parsedate_to_datetime`` returns a naive
        # datetime for a ``-0000`` zone, which ``.timestamp()`` would read as LOCAL time.
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return max(0.0, parsed.timestamp() - now) * 1000.0


def build_sync_client(config: Config) -> httpx.Client:
    timeout = httpx.Timeout(config.timeout_ms / 1000.0)
    # Never fewer sockets than the fan-out width, or GANGTISE_PAGE_CONCURRENCY above
    # the pool size would only queue requests inside httpx (TS v0.42.0).
    pool = max(16, config.page_concurrency)
    limits = httpx.Limits(max_connections=pool, max_keepalive_connections=pool, keepalive_expiry=60)
    return httpx.Client(base_url=config.base_url, timeout=timeout, limits=limits)


def _success_code(code: Any) -> bool:
    return str(code) in {"000000", "0"}


class TracedDict(dict):  # type: ignore[type-arg]
    """A payload that remembers the ``traceId`` of the envelope it came out of.

    ``unwrap_envelope`` discards the envelope, and with it the ONE correlation id
    Gangtise support can trace a failure by. That matters most for the failures
    raised downstream of the transport — an EDE matrix whose shape no longer
    matches is exactly the kind of thing worth reporting, and it would otherwise
    reach the user trace-less.

    A ``dict`` subclass rather than a wrapper object so nothing downstream has to
    know about it: it serializes, compares, and tabulates exactly like the plain
    dict it replaces, and the id rides on an attribute that no iteration sees.
    Mirrors the CLI's non-enumerable ``ENVELOPE_TRACE_ID`` symbol (TS v0.31.0).
    """

    __slots__ = ("envelope_trace_id",)

    def __init__(self, data: dict[str, Any], trace_id: str) -> None:
        super().__init__(data)
        self.envelope_trace_id = trace_id


class TracedList(list):  # type: ignore[type-arg]
    """``TracedDict``'s twin for a bare-array payload (the ``expects="array"`` opinion
    detail endpoints): a batch whose elements turn out malformed downstream is worth
    reporting, and without this it would reach the user trace-less. Only those
    endpoints are wrapped — every other list payload stays a plain ``list``."""

    __slots__ = ("envelope_trace_id",)

    def __init__(self, data: list[Any], trace_id: str) -> None:
        super().__init__(data)
        self.envelope_trace_id = trace_id


def _attach_envelope_trace_id(data: Any, trace_id: Any) -> Any:
    """Carry an envelope's traceId onto the payload it wrapped. Only plain dicts
    are wrapped — a list or scalar has nowhere to put it, and re-wrapping an
    already-traced payload would drop the OUTER id, which is the one the server
    logged (the EDE inner envelope carries none of its own)."""
    if not isinstance(data, dict) or isinstance(data, TracedDict):
        return data
    if not isinstance(trace_id, (str, int)) or isinstance(trace_id, bool):
        return data
    return TracedDict(data, str(trace_id))


def is_envelope(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if "code" not in payload:
        return False
    return any(k in payload for k in ("msg", "data", "success", "status"))


def unwrap_envelope(
    payload: Any, status_code: int | None = None, retry_after_ms: float | None = None
) -> Any:
    if not is_envelope(payload):
        return payload
    code = payload.get("code")
    code_str = str(code) if code is not None else None
    ok = payload.get("status") is True or payload.get("success") is True or _success_code(code)
    if not ok:
        # Gangtise also wraps errors in HTTP 200 bodies; without retry_after_ms a
        # rate-limited 200 envelope would lose the server's backoff window and
        # degrade into the blind exponential schedule.
        raise ApiError(
            payload.get("msg") or "API request failed",
            code=code_str,
            status_code=status_code,
            details=payload,
            retry_after_ms=retry_after_ms,
        )
    if "data" not in payload:
        return payload
    # An EDE response double-wraps and only the OUTER envelope carries a traceId,
    # so peeling the inner one has to hand the carried id down rather than lose it.
    trace_id = payload.get("traceId")
    if trace_id is None:
        trace_id = getattr(payload, "envelope_trace_id", None)
    return _attach_envelope_trace_id(payload["data"], trace_id)


def check_expected_shape(endpoint: EndpointDef, payload: Any, status_code: int, parsed: Any) -> Any:
    """Refuse a 2xx payload that is not the shape the endpoint always returns.

    ``expects="list"`` (the seven quote endpoints, bond, fund, …): every legitimate
    answer — including an empty date range or an unknown security code — is
    ``{"total": 0, "list": []}``, so a ``data: null`` or a bare object is a broken
    response, not an empty one. ``expects="array"`` (the two opinion detail
    endpoints): the answer is a bare array, ``[]`` when no ID had a body — anything
    else would otherwise read as "every paid-for body is missing" (TS v0.41.0).
    Without this the normalizers hand ``None`` back as a success and the caller sees
    "no data".

    Checked HERE, not in a wrapper: ``None`` cannot carry the envelope's traceId
    (``_attach_envelope_trace_id`` only wraps dicts), so a check further down would
    report the failure trace-less — the envelope is passed as ``details`` so the id
    survives on the error. Marked ``structural`` because it is a verdict about THIS
    one response: a fan-out records the shard as failed and keeps sending the rest
    (TS v0.38.0). ``ApiError`` with a 2xx status and no code is not retryable, so
    the transport's own loop will not resend it.
    """
    if endpoint.expects is None:
        return payload
    if endpoint.expects == "array":
        if isinstance(payload, list):
            trace_id = parsed.get("traceId") if isinstance(parsed, dict) else None
            if isinstance(trace_id, (str, int)) and not isinstance(trace_id, bool):
                return TracedList(payload, str(trace_id))
            return payload
    elif isinstance(payload, dict) and isinstance(payload.get("list"), list):
        return payload
    if payload is None:
        got = "null"
    elif isinstance(payload, list):
        got = "an array"
    elif isinstance(payload, dict):
        # Not ``type(payload).__name__``: a traced payload is a ``TracedDict``, and
        # naming an internal subclass tells the reader nothing about the response.
        got = "an object with no list" if endpoint.expects == "list" else "an object"
    else:
        got = type(payload).__name__
    error = ApiError(
        f"{endpoint.key} returned no {endpoint.expects} payload (got {got}) — "
        "the response layout may have changed",
        status_code=status_code,
        details=parsed,
    )
    error.structural = True
    raise error


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
        if error.code in TERMINAL_API_CODES or error.code in AUTH_RETRY_CODES:
            return False
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


# Total deadline of one request, as a multiple of its (idle) timeout. httpx's read
# timeout is an IDLE timeout: a server that sends a few bytes per interval resets it
# forever and holds the request open indefinitely. JSON answers are small, so twice the
# timeout leaves room for a slow link. A file transfer (upload, download) can
# legitimately run long, and the idle timeout already catches a stalled one, so its
# bound only ends a trickle: sixty times the timeout (30 min at the default) still lets
# 50 MB through at about 28 KB/s (TS v0.44.0).
JSON_TOTAL_FACTOR = 2
TRANSFER_TOTAL_FACTOR = 60


def request_deadline_seconds(
    http: httpx.Client | httpx.AsyncClient, endpoint: EndpointDef, *, transfer: bool
) -> float:
    """Seconds one attempt may take in total: the effective idle timeout (the endpoint's
    floor, or the client's if higher) times the JSON or transfer factor."""
    read = http.timeout.read
    base = read if read is not None else 30.0
    if endpoint.timeout_ms is not None:
        base = max(base, endpoint.timeout_ms / 1000.0)
    return base * (TRANSFER_TOTAL_FACTOR if transfer else JSON_TOTAL_FACTOR)


def _deadline_exceeded(request: httpx.Request, seconds: float) -> httpx.ReadTimeout:
    # A ReadTimeout, so the retry policy treats it like any other response timeout:
    # replayed on the default policy, never on "no-replay" (the server may have run it).
    return httpx.ReadTimeout(
        f"request exceeded its overall deadline ({seconds:.0f}s) while the response was "
        "still arriving",
        request=request,
    )


def _build_request(
    http: httpx.Client | httpx.AsyncClient,
    endpoint: EndpointDef,
    body: Any,
    *,
    token: str | None,
    query: dict[str, str | int] | None,
) -> httpx.Request:
    headers: dict[str, str] = {"content-type": "application/json", "user-agent": USER_AGENT}
    if token is not None:
        headers["Authorization"] = normalize_token(token)
    timeout = _effective_timeout(http, endpoint)
    extensions = {"timeout": timeout.as_dict()} if timeout is not None else None
    if isinstance(body, UploadFile):
        # httpx writes its own multipart content-type (with the boundary); leaving
        # the JSON one in place would make the server reject the parts.
        headers.pop("content-type", None)
        return http.build_request(
            endpoint.method,
            endpoint.path,
            params=query,
            headers=headers,
            files={"file": (body.filename, body.data, body.content_type)},
            data=dict(body.fields) or None,
            extensions=extensions,
        )
    return http.build_request(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
        content=None if endpoint.method == "GET" else json.dumps(body or {}).encode("utf8"),
        extensions=extensions,
    )


def _parse_body(raw: bytes, endpoint: EndpointDef) -> Any:
    """Decode the JSON body, applying the endpoint's big-int field guard first.

    ``json.loads`` on bytes detects UTF-8/16/32 itself; only endpoints that declare
    ``big_int_fields`` pay for the text rewrite.
    """
    if not endpoint.big_int_fields:
        return json.loads(raw)
    return json.loads(quote_big_int_fields(raw.decode("utf-8"), endpoint.big_int_fields))


def _parse_response(
    endpoint: EndpointDef, status_code: int, headers: httpx.Headers, raw: bytes, elapsed_ms: float
) -> tuple[int, Any, float | None]:
    logger.debug(
        "[gangtise] %5.0fms %s %s (status=%s, bytes=%s)",
        elapsed_ms,
        endpoint.method,
        endpoint.path,
        status_code,
        len(raw),
    )
    # Parse Retry-After once so every error path (JSON parse failure AND the
    # envelope/HTTP-error raise in request_json) carries it — a non-JSON 429/503
    # must still honor the server's rate window instead of default backoff.
    retry_after_ms = parse_retry_after_ms(headers.get("retry-after"), time.time())
    try:
        parsed = _parse_body(raw, endpoint)
    except ValueError as err:
        text = raw[:2000].decode("utf-8", errors="replace")[:500]
        if status_code >= 400:
            raise ApiError(
                f"API request failed (HTTP {status_code})",
                status_code=status_code,
                details=text,
                retry_after_ms=retry_after_ms,
            ) from err
        raise ApiError(
            "Failed to parse API response",
            status_code=status_code,
            details=text,
            retry_after_ms=retry_after_ms,
        ) from err
    return status_code, parsed, retry_after_ms


def _do_request(
    http: httpx.Client,
    endpoint: EndpointDef,
    body: Any,
    *,
    token: str | None,
    query: dict[str, str | int] | None,
) -> tuple[int, Any, float | None]:
    request = _build_request(http, endpoint, body, token=token, query=query)
    limit = request_deadline_seconds(http, endpoint, transfer=isinstance(body, UploadFile))
    started = time.monotonic()
    # Sync httpx has no whole-request deadline: sending the body and waiting for the
    # headers stay bounded by the idle timeouts only, and the total is enforced from
    # the first body chunk on (the async transport covers all three phases).
    response = http.send(request, stream=True)
    try:
        chunks: list[bytes] = []
        for chunk in response.iter_bytes():
            chunks.append(chunk)
            if time.monotonic() - started > limit:
                raise _deadline_exceeded(request, limit)
    finally:
        response.close()
    elapsed_ms = (time.monotonic() - started) * 1000.0
    return _parse_response(
        endpoint, response.status_code, response.headers, b"".join(chunks), elapsed_ms
    )


def request_json(
    http: httpx.Client,
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
            payload = unwrap_envelope(
                parsed, status_code=status_code, retry_after_ms=retry_after_ms
            )
            return check_expected_shape(endpoint, payload, status_code, parsed)
        except Exception as error:
            if budget[0] >= max_retries or not is_retryable_error(error, endpoint.retry):
                _apply_policy_hint(endpoint, error)
                raise
            time.sleep(_retry_delay(error, budget[0]))
            budget[0] += 1


def _apply_policy_hint(endpoint: EndpointDef, error: BaseException) -> None:
    """Replace the generic 999999 "retry later" hint where it would mislead.

    EDE fetch (cross-section/time-series/screener): a parameter checklist — a wrong
    code or param name comes back as its own error (100003), but a date on the wrong
    axis silently yields null cells; indicator.search (also no-999999) keeps the
    generic hint. "no-replay" endpoints: the SDK deliberately did not retry because
    the request may already have executed — "retry later" would invite a manual
    double-bill on a billed endpoint, or a second copy / a false "not found" on a
    free write."""
    if not (isinstance(error, ApiError) and error.code == "999999"):
        return
    # Only the EDE data-fetch endpoints (cross-section/time-series/screener) take
    # a date/scope/params query, so only they get the fetch hint. indicator.search
    # shares the no-999999 policy but has just a keyword, so the date/scopeList/
    # param guidance would be nonsense — it keeps the generic hint (TS v0.28.2).
    if endpoint.key in (
        "indicator.cross-section",
        "indicator.time-series",
        "indicator.screener",
    ):
        error.hint = EDE_NO_DATA_HINT
    elif endpoint.retry == "no-replay":
        error.hint = (
            NO_REPLAY_UNCERTAIN_HINT if endpoint.billing is not None else NO_REPLAY_SIDE_EFFECT_HINT
        )
