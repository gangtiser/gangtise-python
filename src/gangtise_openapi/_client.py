from __future__ import annotations

import asyncio
import math
import threading
import time
import warnings
from dataclasses import asdict, dataclass
from typing import Any

import anyio
import httpx
from anyio import to_thread

from gangtise_openapi._auth import (
    TokenCache,
    credential_fingerprint,
    is_cache_valid,
    normalize_token,
    read_token_cache,
    require_credentials,
    write_token_cache,
)
from gangtise_openapi._config import (
    MAX_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    Config,
    load_config,
    warn_if_plain_http,
)
from gangtise_openapi._endpoints import COSTLY_FETCH_CREDITS, EndpointDef, lookup
from gangtise_openapi._errors import ApiError, ConfigError, ValidationError
from gangtise_openapi._logging import configure_logging, get_logger
from gangtise_openapi._lookup import LOOKUP_LOADERS
from gangtise_openapi._pagination import collect_paginated, collect_paginated_async
from gangtise_openapi._title_cache import (
    TITLE_LOOKUP_SIZE,
    TitleCache,
    extract_titles,
)
from gangtise_openapi._transport import (
    AUTH_RETRY_CODES,
    UploadFile,
    build_sync_client,
    request_json,
)
from gangtise_openapi._transport_async import (
    build_async_client,
    request_json_async,
)

logger = get_logger()


@dataclass
class _AuthRecovery:
    """One logical request's token recovery so far (TS v0.44.0).

    A login is the last resort: back-to-back logins can end each other's sessions
    server-side (the 0000001008 semantics). So a token someone else already obtained
    is tried first — from memory, or from the shared cache file. Such a token is
    UNPROVEN when it did not come from a login of this client (a cache file can hold
    an old, dead one, and another request may have just put one in memory), so each
    request may replay with an unproven token once, and a failure after that logs in.
    A token this client's login minted that fails too ends the recovery: no login loop.
    """

    used_unproven_token: bool = False
    used_login_token: bool = False


def _refuse_unconfirmed(endpoint: EndpointDef, body: Any, confirm: bool) -> None:
    """The request-level guards, checked BEFORE anything is sent, on every entry point
    (a wrapper or a direct ``_call``) — a download endpoint is refused outright, and
    the two gates of TS v0.40.0 / v0.44.0:

    - a destructive endpoint needs ``confirm=True``;
    - an endpoint whose one request has no bound on what it bills is priced from the
      request body and refused past COSTLY_FETCH_CREDITS unless confirmed. A body the
      estimate cannot read is refused too: "unknown" must not pass as "free".
    """
    if not isinstance(confirm, bool):
        # It releases deletions and large billed fetches, so only a real True does:
        # a string "false" read from a config file must not count as confirmation.
        raise ValidationError(f"confirm must be True or False, got {confirm!r}")
    if endpoint.kind == "upload" and not isinstance(body, UploadFile):
        raise ValidationError(
            f"{endpoint.key} takes a file upload — use its method (tool.file_parse / "
            "vault.drive_upload), not _call with a JSON body"
        )
    if endpoint.kind == "download":
        # A download answers with file bytes: through the JSON path the (billed) request
        # would go out and only then fail to parse. The CLI routes these to its download
        # flow; the SDK's is download_to_path, which every *_download wrapper uses.
        raise ValidationError(
            f"{endpoint.key} is a download endpoint — use the matching *_download() method "
            "(or _download.download_to_path), not _call"
        )
    if confirm:
        return
    if endpoint.destructive:
        # Name the target the way the CLI does (「确认要对 X 执行」): the id fields of
        # the body, so the refusal reads as a question about THESE items.
        ids = (
            [f"{k}={v}" for k, v in body.items() if k.endswith(("Id", "IdList"))]
            if isinstance(body, dict)
            else []
        )
        target = f"对 {', '.join(ids)} " if ids else ""
        raise ValidationError(f"{endpoint.destructive} 确认要{target}执行就传 confirm=True。")
    billing = endpoint.billing
    if endpoint.estimate_billed_units is None or billing is None:
        return
    try:
        units = endpoint.estimate_billed_units(body if isinstance(body, dict) else {})
    except ValidationError as error:
        raise ValidationError(
            f"{endpoint.key} could not be priced before sending ({error}), and it is billed "
            f"per {billing.per} with no upper bound. Fix the request, or pass confirm=True "
            "to send it as it is."
        ) from error
    credits = math.ceil(units * billing.price)
    if credits <= COSTLY_FETCH_CREDITS:
        return
    raise ValidationError(
        f"{endpoint.key} would cost about {credits} credits ({billing.price} per "
        f"{billing.per}, about {units:.0f} estimated from the requested date range), above "
        f"the {COSTLY_FETCH_CREDITS}-credit guard. Narrow the date range, or pass "
        "confirm=True to send it."
    )


def _flag_failed_items(endpoint: EndpointDef, data: Any) -> Any:
    """The stock-pool and drive batch writes report per-item failures INSIDE a
    ``000000`` success: an unknown security code lands in ``failList`` while the
    envelope still says 操作成功 (probed 2026-09-14). Without this a script that added
    50 codes and got 48 in cannot tell. Mark the result ``partial`` and name the
    failures in a warning (TS v0.40.0 ``flagFailedItems``).

    Only a NON-EMPTY failList flags: the same endpoints answer a fully successful call
    with ``failList: []``."""
    if not endpoint.item_failures or not isinstance(data, dict):
        return data
    fails = data.get("failList")
    if not isinstance(fails, list) or not fails:
        return data
    data["partial"] = True
    details = []
    for item in fails:
        if not isinstance(item, dict):
            details.append(str(item))
            continue
        # Each write family keys the failure on its own field.
        ident = item.get("securityCode", item.get("poolId", item.get("fileId", item)))
        reason = item.get("failReason")
        details.append(f"{ident}（{reason}）" if reason else str(ident))  # noqa: RUF001
    warnings.warn(
        f"{endpoint.key} — {len(fails)} item(s) failed while the request itself succeeded: "
        f"{'、'.join(details)}. Result marked partial (see failList).",
        stacklevel=4,
    )
    return data


def _int_or(value: Any, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _login_fields(result: Any) -> tuple[str, int]:
    """``(accessToken, expiresIn)`` from a login answer. A missing or non-string token is
    an ``ApiError`` naming the problem rather than a bare ``KeyError``; a missing or
    non-numeric ``expiresIn`` reads as 0 — expired at once, so the next call logs in
    again (as the CLI does)."""
    token = result.get("accessToken") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token:
        raise ApiError("auth.login answered without an accessToken", details=result)
    expires = result.get("expiresIn")
    expires_in = (
        int(expires)
        if isinstance(expires, (int, float))
        and not isinstance(expires, bool)
        and expires == expires
        and abs(expires) != float("inf")
        else 0
    )
    return token, expires_in


def _timeout_ms(timeout: float) -> int:
    """``timeout=`` (seconds) passed in code: held to the bounds GANGTISE_TIMEOUT_MS has
    (1 s to 1 h), but refused rather than silently replaced — a value in code is a
    decision, not a typo in an environment file."""
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not (MIN_TIMEOUT_MS <= timeout * 1000 <= MAX_TIMEOUT_MS)
    ):
        raise ConfigError(
            f"timeout must be a number of seconds from {MIN_TIMEOUT_MS // 1000} to "
            f"{MAX_TIMEOUT_MS // 1000}, got {timeout!r}"
        )
    return int(timeout * 1000)


def _same_token(a: str | None, b: str | None) -> bool:
    """One token whatever its ``Bearer`` prefix: an env token may carry it, a cached one
    does not."""
    return a is not None and b is not None and normalize_token(a) == normalize_token(b)


def _running_asyncio_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class GangtiseClient:
    """Synchronous client for the Gangtise OpenAPI."""

    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        _config: Config | None = None,
    ) -> None:
        if _config is not None:
            cfg = _config
        else:
            cfg = load_config()
            overrides: dict[str, Any] = {}
            if access_key is not None:
                overrides["access_key"] = access_key
            if secret_key is not None:
                overrides["secret_key"] = secret_key
            if base_url is not None:
                overrides["base_url"] = base_url
            if token is not None:
                overrides["token"] = token
            if timeout is not None:
                overrides["timeout_ms"] = _timeout_ms(timeout)
            if overrides:
                cfg = Config(**{**asdict(cfg), **overrides})
        warn_if_plain_http(cfg.base_url)
        self._config = cfg
        configure_logging(cfg.verbose)
        self._http: httpx.Client | None = None
        self._memo_cache: TokenCache | None = None
        # The token this client's last login returned: proven, unlike one read from the
        # cache file (see _recover_token).
        self._login_token: str | None = None
        self._env_token_rejected = False
        self._lock = threading.Lock()
        self._http_lock = threading.Lock()
        self._title_cache = TitleCache(cfg.title_cache_path)

    @property
    def config(self) -> Config:
        return self._config

    def __enter__(self) -> GangtiseClient:
        self._http_client()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        self.close()

    def _http_client(self) -> httpx.Client:
        # Locked: the first calls can arrive concurrently (the EDE calendar probe fans
        # out on threads), and each unguarded check-then-set built its own client —
        # only the last is ever closed, the rest leak their pools. A lock of its own:
        # ``_lock`` is held across a login, which itself needs the HTTP client.
        if self._http is None:
            with self._http_lock:
                if self._http is None:
                    self._http = build_sync_client(self._config)
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    # ---- Auth ----

    def _fingerprint(self) -> str | None:
        """Identity a cached token must carry, or None without an access key (then there
        is no second account the cache could belong to)."""
        ak = self._config.access_key
        return credential_fingerprint(ak, self._config.base_url) if ak else None

    def _get_token(self) -> str:
        if self._config.token and not self._env_token_rejected:
            return self._config.token
        fingerprint = self._fingerprint()
        if is_cache_valid(self._memo_cache, expected_fingerprint=fingerprint):
            assert self._memo_cache is not None
            return self._memo_cache.access_token
        disk = read_token_cache(self._config.token_cache_path)
        if is_cache_valid(disk, expected_fingerprint=fingerprint):
            self._memo_cache = disk
            assert disk is not None
            return disk.access_token
        with self._lock:
            # A concurrent caller may have logged in while we waited on the lock.
            if is_cache_valid(self._memo_cache, expected_fingerprint=fingerprint):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            return self._refresh_token()

    def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = request_json(self._http_client(), endpoint, body=body, token=None)
        access_token, expires_in = _login_fields(result)
        cache = TokenCache(
            access_token=access_token,
            expires_in=expires_in,
            time=_int_or(result.get("time"), int(time.time())),
            expires_at=int(time.time()) + expires_in,
            uid=result.get("uid"),
            user_name=result.get("userName"),
            tenant_id=result.get("tenantId"),
            issued_for=credential_fingerprint(access_key, self._config.base_url),
        )
        self._memo_cache = cache
        self._login_token = access_token
        try:
            write_token_cache(self._config.token_cache_path, cache)
        except OSError:
            logger.debug("Failed to persist token cache; using in-memory token", exc_info=True)
        return access_token

    def _auth_recoverable(self, error: BaseException) -> bool:
        return (
            isinstance(error, ApiError)
            and error.code in AUTH_RETRY_CODES
            and bool(self._config.access_key)
            and bool(self._config.secret_key)
        )

    def _other_memo_token(self, failed: str) -> str | None:
        memo = self._memo_cache
        if not is_cache_valid(memo) or memo is None or _same_token(memo.access_token, failed):
            return None
        return memo.access_token

    def _recover_token(self, failed: str, state: _AuthRecovery) -> str | None:
        """A token to replay a request with after ``failed`` was rejected by an auth
        code, or None when this request's recovery is spent (see ``_AuthRecovery``)."""
        if state.used_login_token:
            return None
        if _same_token(failed, self._config.token):
            # The env-provided token was rejected upstream; stop preferring it.
            self._env_token_rejected = True

        def from_memory() -> str | None:
            memo = self._other_memo_token(failed)
            if memo is None:
                return None
            if memo == self._login_token:
                state.used_login_token = True
                return memo
            if not state.used_unproven_token:
                state.used_unproven_token = True
                return memo
            return None

        token = from_memory()
        if token is not None:
            return token
        if not state.used_unproven_token:
            disk = read_token_cache(self._config.token_cache_path)
            # Checked again after the read: a request of this client may have logged
            # in while it ran, and the snapshot just read can predate that login.
            token = from_memory()
            if token is not None:
                return token
            if (
                disk is not None
                and is_cache_valid(disk, expected_fingerprint=self._fingerprint())
                and not _same_token(disk.access_token, failed)
            ):
                self._memo_cache = disk
                state.used_unproven_token = True
                return disk.access_token
        with self._lock:
            memo = self._other_memo_token(failed)
            if memo is not None and memo == self._login_token:
                # Another request logged in while this one waited on the lock.
                token = memo
            else:
                self._memo_cache = None
                token = self._refresh_token()
        state.used_login_token = True
        return token

    # ---- Public surface used by domain wrappers ----

    def login(self) -> dict[str, Any]:
        """Report the identity requests will actually use (TS v0.40.0).

        ``GANGTISE_TOKEN`` set → that token wins for every other call, so minting a
        fresh one would name an account no request uses: report it and contact
        nothing. Otherwise force a real login — falling back to the cache would report
        the PREVIOUS account after a credential swap. ``cache`` is this login's own
        in-memory result, never a re-read of disk: when persisting failed, the file
        still holds the previous account."""
        if self._config.token and not self._env_token_rejected:
            return {
                "authorization": normalize_token(self._config.token),
                "cache": None,
                "source": "env-token",
            }
        with self._lock:
            token = self._refresh_token()
        cache = self._memo_cache
        return {
            "authorization": normalize_token(token),
            "cache": asdict(cache) if cache else None,
            "source": "login",
        }

    def _call(
        self,
        endpoint_key: str,
        body: Any = None,
        query: dict[str, str | int] | None = None,
        *,
        confirm: bool = False,
    ) -> Any:
        """The one path every wrapper goes through. ``confirm=True`` is the SDK's
        ``--yes``: it lets a destructive endpoint through, and a request the credit
        guards would refuse (a size-less per-row billed list past
        COSTLY_FETCH_CREDITS, an open-ended earning-forecast range)."""
        endpoint = lookup(endpoint_key)
        if endpoint.path.startswith("/guide/"):
            return list(LOOKUP_LOADERS[endpoint.key])
        _refuse_unconfirmed(endpoint, body, confirm)

        def fetch_one(page_body: dict[str, Any]) -> Any:
            return self._request_once(endpoint, page_body, query)

        if endpoint.pagination is not None:
            return collect_paginated(
                endpoint,
                body=body or {},
                fetch=fetch_one,
                concurrency=self._config.page_concurrency,
                allow_costly=confirm,
            )
        return _flag_failed_items(endpoint, self._request_once(endpoint, body or {}, query))

    def _record_list_titles(
        self,
        *,
        list_endpoint_key: str,
        id_field: str,
        title_field: str,
        rows: list[Any],
    ) -> None:
        titles = extract_titles(rows, id_field=id_field, title_field=title_field)
        if titles:
            self._title_cache.set_titles(list_endpoint_key, titles)
            try:
                self._title_cache.flush()
            except Exception:
                # Best-effort side effect of a list call whose rows are already paid
                # for: a corrupt file on disk (flush re-reads it to merge) or a title
                # that cannot be encoded must never keep those rows from the caller.
                logger.debug("Failed to persist title cache", exc_info=True)

    def _resolve_title(
        self,
        list_endpoint_key: str,
        id_field: str,
        id_value: str,
        title_field: str = "title",
        *,
        allow_lookup: bool = False,
    ) -> str | None:
        """Friendly filename for a download: title cache first, list endpoint only on request.

        The cache (populated by any prior list call on the same endpoint) is free.
        The LIST FALLBACK is not: ``TITLE_LOOKUP_SIZE`` rows across 4 requests, and 9
        of the 12 endpoints wired up for title lookup are metered at 0.1 credits/row —
        roughly 20 credits spent on nothing but a nicer filename, on a download that
        itself costs 10-50. Batch N downloads on a cold cache and that was 4N requests.
        So the fallback is opt-in (``resolve_title=True``) and off by default; without
        it the caller keeps the server's own Content-Disposition name, or
        ``<prefix>-<id>``. The normal `list()` → `download()` workflow is unaffected —
        the cache hits and nothing extra is sent (TS v0.37.0).

        Rows fetched by the fallback are written back to the cache whole, not just the
        row asked for: they are already paid for, so the rest of a batch gets its names
        free.
        """
        cached = self._title_cache.lookup(list_endpoint_key, id_value)
        if cached:
            return cached
        if not allow_lookup:
            return None
        try:
            result = self._call(
                list_endpoint_key,
                body={"from": 0, "size": TITLE_LOOKUP_SIZE},
            )
        except Exception:
            # List-fetch failure must not break the download flow.
            return None
        rows = result.get("list") if isinstance(result, dict) else result
        if not isinstance(rows, list):
            return None
        titles = extract_titles(rows, id_field=id_field, title_field=title_field)
        if titles:
            self._title_cache.set_titles(list_endpoint_key, titles)
            try:
                self._title_cache.flush()
            except Exception:
                # Best-effort side effect of a list call whose rows are already paid
                # for: a corrupt file on disk (flush re-reads it to merge) or a title
                # that cannot be encoded must never keep those rows from the caller.
                logger.debug("Failed to persist title cache", exc_info=True)
        return titles.get(str(id_value))

    def _request_once(
        self,
        endpoint: EndpointDef,
        body: Any,
        query: dict[str, str | int] | None,
    ) -> Any:
        token = self._get_token()
        state = _AuthRecovery()
        attempts = [0]  # one transient-retry budget across auth replays (CLI withRetry)
        while True:
            try:
                return request_json(
                    self._http_client(),
                    endpoint,
                    body=body,
                    token=token,
                    query=query,
                    attempts=attempts,
                )
            except ApiError as error:
                if not self._auth_recoverable(error):
                    raise
                recovered = self._recover_token(token, state)
                if recovered is None:
                    raise
                token = recovered


class AsyncGangtiseClient:
    """Async counterpart to GangtiseClient."""

    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        _config: Config | None = None,
    ) -> None:
        if _config is not None:
            cfg = _config
        else:
            cfg = load_config()
            overrides: dict[str, Any] = {}
            if access_key is not None:
                overrides["access_key"] = access_key
            if secret_key is not None:
                overrides["secret_key"] = secret_key
            if base_url is not None:
                overrides["base_url"] = base_url
            if token is not None:
                overrides["token"] = token
            if timeout is not None:
                overrides["timeout_ms"] = _timeout_ms(timeout)
            if overrides:
                cfg = Config(**{**asdict(cfg), **overrides})
        warn_if_plain_http(cfg.base_url)
        self._config = cfg
        configure_logging(cfg.verbose)
        self._http: httpx.AsyncClient | None = None
        self._http_loop: asyncio.AbstractEventLoop | None = None
        self._memo_cache: TokenCache | None = None
        self._login_token: str | None = None
        self._env_token_rejected = False
        self._lock = anyio.Lock()
        self._title_cache = TitleCache(cfg.title_cache_path)

    @property
    def config(self) -> Config:
        return self._config

    async def __aenter__(self) -> AsyncGangtiseClient:
        self._http_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None:
            http = self._http
            self._http = None
            self._http_loop = None
            await http.aclose()

    def _http_client(self) -> httpx.AsyncClient:
        loop = _running_asyncio_loop()
        if (
            self._http is not None
            and loop is not None
            and self._http_loop is not None
            and self._http_loop is not loop
        ):
            # httpx/anyio keepalive streams are bound to the loop that created them.
            # Drop the closed-loop client; a fresh one avoids "Event loop is closed"
            # when the module-level async facade is reused across asyncio.run().
            self._http = None
            self._http_loop = None
        if self._http is None:
            self._http = build_async_client(self._config)
            self._http_loop = loop
        return self._http

    def _fingerprint(self) -> str | None:
        ak = self._config.access_key
        return credential_fingerprint(ak, self._config.base_url) if ak else None

    async def _get_token(self) -> str:
        if self._config.token and not self._env_token_rejected:
            return self._config.token
        fingerprint = self._fingerprint()
        if is_cache_valid(self._memo_cache, expected_fingerprint=fingerprint):
            assert self._memo_cache is not None
            return self._memo_cache.access_token
        disk = await to_thread.run_sync(read_token_cache, self._config.token_cache_path)
        if is_cache_valid(disk, expected_fingerprint=fingerprint):
            self._memo_cache = disk
            assert disk is not None
            return disk.access_token
        async with self._lock:
            if is_cache_valid(self._memo_cache, expected_fingerprint=fingerprint):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            return await self._refresh_token()

    async def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = await request_json_async(self._http_client(), endpoint, body=body, token=None)
        access_token, expires_in = _login_fields(result)
        cache = TokenCache(
            access_token=access_token,
            expires_in=expires_in,
            time=_int_or(result.get("time"), int(time.time())),
            expires_at=int(time.time()) + expires_in,
            uid=result.get("uid"),
            user_name=result.get("userName"),
            tenant_id=result.get("tenantId"),
            issued_for=credential_fingerprint(access_key, self._config.base_url),
        )
        self._memo_cache = cache
        self._login_token = access_token
        try:
            await to_thread.run_sync(write_token_cache, self._config.token_cache_path, cache)
        except OSError:
            logger.debug("Failed to persist token cache; using in-memory token", exc_info=True)
        return access_token

    def _auth_recoverable(self, error: BaseException) -> bool:
        return (
            isinstance(error, ApiError)
            and error.code in AUTH_RETRY_CODES
            and bool(self._config.access_key)
            and bool(self._config.secret_key)
        )

    def _other_memo_token(self, failed: str) -> str | None:
        memo = self._memo_cache
        if not is_cache_valid(memo) or memo is None or _same_token(memo.access_token, failed):
            return None
        return memo.access_token

    async def _recover_token(self, failed: str, state: _AuthRecovery) -> str | None:
        """Async mirror of ``GangtiseClient._recover_token``."""
        if state.used_login_token:
            return None
        if _same_token(failed, self._config.token):
            self._env_token_rejected = True

        def from_memory() -> str | None:
            memo = self._other_memo_token(failed)
            if memo is None:
                return None
            if memo == self._login_token:
                state.used_login_token = True
                return memo
            if not state.used_unproven_token:
                state.used_unproven_token = True
                return memo
            return None

        token = from_memory()
        if token is not None:
            return token
        if not state.used_unproven_token:
            disk = await to_thread.run_sync(read_token_cache, self._config.token_cache_path)
            token = from_memory()
            if token is not None:
                return token
            if (
                disk is not None
                and is_cache_valid(disk, expected_fingerprint=self._fingerprint())
                and not _same_token(disk.access_token, failed)
            ):
                self._memo_cache = disk
                state.used_unproven_token = True
                return disk.access_token
        async with self._lock:
            memo = self._other_memo_token(failed)
            if memo is not None and memo == self._login_token:
                token = memo
            else:
                self._memo_cache = None
                token = await self._refresh_token()
        state.used_login_token = True
        return token

    async def login(self) -> dict[str, Any]:
        """Async mirror of ``GangtiseClient.login``."""
        if self._config.token and not self._env_token_rejected:
            return {
                "authorization": normalize_token(self._config.token),
                "cache": None,
                "source": "env-token",
            }
        async with self._lock:
            token = await self._refresh_token()
        cache = self._memo_cache
        return {
            "authorization": normalize_token(token),
            "cache": asdict(cache) if cache else None,
            "source": "login",
        }

    async def _record_list_titles(
        self,
        *,
        list_endpoint_key: str,
        id_field: str,
        title_field: str,
        rows: list[Any],
    ) -> None:
        titles = extract_titles(rows, id_field=id_field, title_field=title_field)
        if titles:
            self._title_cache.set_titles(list_endpoint_key, titles)
            try:
                await to_thread.run_sync(self._title_cache.flush)
            except Exception:
                # Best-effort (see the sync twin): never lose paid rows to the cache.
                logger.debug("Failed to persist title cache", exc_info=True)

    async def _resolve_title(
        self,
        list_endpoint_key: str,
        id_field: str,
        id_value: str,
        title_field: str = "title",
        *,
        allow_lookup: bool = False,
    ) -> str | None:
        """Async mirror of :meth:`GangtiseClient._resolve_title` — same opt-in rule."""
        cached = self._title_cache.lookup(list_endpoint_key, id_value)
        if cached:
            return cached
        if not allow_lookup:
            return None
        try:
            result = await self._call(
                list_endpoint_key, body={"from": 0, "size": TITLE_LOOKUP_SIZE}
            )
        except Exception:
            return None
        rows = result.get("list") if isinstance(result, dict) else result
        if not isinstance(rows, list):
            return None
        titles = extract_titles(rows, id_field=id_field, title_field=title_field)
        if titles:
            self._title_cache.set_titles(list_endpoint_key, titles)
            try:
                await to_thread.run_sync(self._title_cache.flush)
            except Exception:
                # Best-effort (see the sync twin): never lose paid rows to the cache.
                logger.debug("Failed to persist title cache", exc_info=True)
        return titles.get(str(id_value))

    async def _call(
        self,
        endpoint_key: str,
        body: Any = None,
        query: dict[str, str | int] | None = None,
        *,
        confirm: bool = False,
    ) -> Any:
        """Async mirror of ``GangtiseClient._call`` (same ``confirm`` semantics)."""
        endpoint = lookup(endpoint_key)
        if endpoint.path.startswith("/guide/"):
            return list(LOOKUP_LOADERS[endpoint.key])
        _refuse_unconfirmed(endpoint, body, confirm)

        async def fetch_one(page_body: dict[str, Any]) -> Any:
            return await self._request_once(endpoint, page_body, query)

        if endpoint.pagination is not None:
            return await collect_paginated_async(
                endpoint,
                body=body or {},
                fetch=fetch_one,
                concurrency=self._config.page_concurrency,
                allow_costly=confirm,
            )
        return _flag_failed_items(endpoint, await self._request_once(endpoint, body or {}, query))

    async def _request_once(
        self,
        endpoint: EndpointDef,
        body: Any,
        query: dict[str, str | int] | None,
    ) -> Any:
        token = await self._get_token()
        state = _AuthRecovery()
        attempts = [0]  # one transient-retry budget across auth replays (CLI withRetry)
        while True:
            try:
                return await request_json_async(
                    self._http_client(),
                    endpoint,
                    body=body,
                    token=token,
                    query=query,
                    attempts=attempts,
                )
            except ApiError as error:
                if not self._auth_recoverable(error):
                    raise
                recovered = await self._recover_token(token, state)
                if recovered is None:
                    raise
                token = recovered
