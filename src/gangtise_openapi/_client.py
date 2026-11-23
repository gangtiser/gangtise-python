from __future__ import annotations

import asyncio
import copy
import itertools
import math
import threading
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
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
    # Logins this client had minted when the request took the token it holds now — moved
    # on with every unproven token it switches to (see _newer_login_token).
    seen_logins: int = 0


@dataclass(eq=False)
class _LoginRound:
    """One login and the requests waiting on it (TS v0.53.0 shares one refresh promise).

    A request that needs a login joins the open round, or opens one, before it waits for
    the lock; the first to get the lock runs the login, and the rest take its outcome
    instead of logging in again — one login's attempts, not one set each. The client lets
    go of a round once its login has ended, so a failure, and the frames its traceback
    holds, are kept only by the requests that waited on it. A round stays open until a
    login ends in it: one whose login was cancelled is run by its next waiter (and new
    requests join it, rather than opening a second login beside it), and one opened by a
    request that then found a token needs nothing until the next login. When the server
    refuses the very token a round minted, the requests recovering from that share one new
    login too: the round's ``successor``."""

    done: bool = False
    # Set once the login has put its token in memory, where requests can pick it up.
    minted: bool = False
    cache: TokenCache | None = None
    error: BaseException | None = None
    successor: _LoginRound | None = None


def _shared_failure(error: BaseException) -> BaseException:
    """A copy of a round's failure, for one more request that waited on it. Raising the one
    object for every request would pile each one's call stack onto its traceback, and a
    note or hint a caller adds would show on every other request's error. The copy keeps
    what the original was raised from (``__cause__``), so the hints still read it."""
    try:
        clone = copy.copy(error)
    except Exception:
        return error
    notes = getattr(error, "__notes__", None)
    if isinstance(notes, list):
        clone.__notes__ = list(notes)  # type: ignore[attr-defined]  # 3.11+
    clone.__cause__ = error.__cause__
    return clone


class _CacheWriter:
    """Writes one client's logins to the cache file in the order they were issued. An
    async login cancelled while its write runs on a worker thread lets go of the lock with
    the write still going, so the next login can mint and write before it lands — and the
    older token would end up on disk. A write whose login is older than the one already
    written is skipped."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._tickets = itertools.count(1)
        self._written = 0

    def ticket(self) -> int:
        return next(self._tickets)

    def write(self, cache: TokenCache, ticket: int) -> None:
        with self._lock:
            if ticket < self._written:
                return
            write_token_cache(self._path, cache)
            self._written = ticket


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
        ident = next(
            (item[k] for k in ("securityCode", "poolId", "fileId", "stockNoteId") if k in item),
            item,
        )
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
        # Logins this client has minted a token in; a request records it (_AuthRecovery).
        self._logins_minted = 0
        # The login requests are waiting on, if any (see _LoginRound).
        self._login_round: _LoginRound | None = None
        # Guards the login round, and the token in memory against one read from the cache
        # file replacing what a login has put there since the read began.
        self._state_lock = threading.Lock()
        self._env_token_rejected = False
        self._lock = threading.Lock()
        self._http_lock = threading.Lock()
        self._title_cache = TitleCache(cfg.title_cache_path)
        self._cache_writer = _CacheWriter(cfg.token_cache_path)

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
        # Locked: the first calls can arrive concurrently (the ETF component-code lookups
        # fan out on threads), and each unguarded check-then-set built its own client —
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
        # Each check reads memory once into a local: another thread may replace or clear it
        # between a check and a second read.
        memo = self._memo_cache
        if is_cache_valid(memo, expected_fingerprint=fingerprint):
            assert memo is not None
            return memo.access_token
        disk = read_token_cache(self._config.token_cache_path)
        if is_cache_valid(disk, expected_fingerprint=fingerprint):
            assert disk is not None
            with self._state_lock:
                # A login may have put a newer token in memory while the file was read.
                memo = self._memo_cache
                if is_cache_valid(memo, expected_fingerprint=fingerprint):
                    assert memo is not None
                    return memo.access_token
                self._memo_cache = disk
            return disk.access_token
        round_ = self._join_login()
        with self._lock:
            # A concurrent caller may have logged in while we waited on the lock.
            memo = self._memo_cache
            if is_cache_valid(memo, expected_fingerprint=fingerprint):
                assert memo is not None
                return memo.access_token
            try:
                return self._login(round_)
            except Exception:
                # The cache held nothing usable when this login began. If it does now,
                # another process logged in meanwhile, and its token serves this request
                # as well. Read with the lock held, so no login of this client lands
                # between the read and the write.
                disk = read_token_cache(self._config.token_cache_path)
                if not is_cache_valid(disk, expected_fingerprint=fingerprint):
                    raise
                assert disk is not None
                with self._state_lock:
                    self._memo_cache = disk
                return disk.access_token

    def _join_login(self) -> _LoginRound:
        with self._state_lock:
            return self._open_round()

    def _open_round(self) -> _LoginRound:
        if self._login_round is None:
            self._login_round = _LoginRound()
        return self._login_round

    def _login(self, round_: _LoginRound, rejected: str | None = None) -> str:
        """Run ``round_``'s login, with ``_lock`` held — or, when it has ended while this
        caller waited, take its outcome (see ``_LoginRound``). ``rejected``: a token the
        server has just refused, passed only when the round had already minted when the
        request joined it — the request may have picked up that very token while the login
        was still writing the cache. If the round's token is the refused one, its outcome is
        no answer, and the round's successor runs a new login. A successor is always a login
        after the refusal, so its outcome is taken whatever token it returns."""
        if round_.done:
            if round_.error is not None:
                raise _shared_failure(round_.error)
            assert round_.cache is not None
            if not _same_token(round_.cache.access_token, rejected):
                with self._state_lock:
                    if self._memo_cache is None:
                        self._memo_cache = round_.cache
                return round_.cache.access_token
            if round_.successor is None:
                round_.successor = self._join_login()
            return self._login(round_.successor)
        try:
            cache = self._refresh_token(round_)
        except Exception as error:
            round_.error = error
            raise
        else:
            round_.cache = cache
            return cache.access_token
        finally:
            with self._state_lock:
                round_.done = round_.cache is not None or round_.error is not None
                if round_.done and self._login_round is round_:
                    self._login_round = None

    def _refresh_token(self, round_: _LoginRound) -> TokenCache:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = request_json(
            self._http_client(),
            endpoint,
            body=body,
            token=None,
            proxied=self._config.proxy is not None,
        )
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
        with self._state_lock:
            self._memo_cache = cache
            self._login_token = access_token
            self._logins_minted += 1
            round_.minted = True
        ticket = self._cache_writer.ticket()
        try:
            self._cache_writer.write(cache, ticket)
        except OSError:
            logger.debug("Failed to persist token cache; using in-memory token", exc_info=True)
        return cache

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
        with self._state_lock:
            token = self._newer_login_token(state)
        if token is not None:
            return token

        def from_memory() -> str | None:
            memo = self._other_memo_token(failed)
            if memo is None:
                return None
            if memo == self._login_token:
                state.used_login_token = True
                return memo
            if not state.used_unproven_token:
                state.used_unproven_token = True
                state.seen_logins = self._logins_minted
                return memo
            return None

        token = from_memory()
        if token is not None:
            return token
        if not state.used_unproven_token:
            disk = read_token_cache(self._config.token_cache_path)
            with self._state_lock:
                # Checked again after the read: a request of this client may have logged
                # in while it ran, and the snapshot just read can predate that login.
                token = self._newer_login_token(state) or from_memory()
                if (
                    token is None
                    and disk is not None
                    and is_cache_valid(disk, expected_fingerprint=self._fingerprint())
                    and not _same_token(disk.access_token, failed)
                ):
                    self._memo_cache = disk
                    state.used_unproven_token = True
                    state.seen_logins = self._logins_minted
                    token = disk.access_token
            if token is not None:
                return token
        with self._state_lock:
            round_ = self._open_round()
            # Minted already: the refused token may be this round's own (see _login).
            rejected = failed if round_.minted else None
        with self._lock:
            with self._state_lock:
                newer = self._newer_login_token(state)
            if newer is not None:
                return newer
            memo = self._other_memo_token(failed)
            if memo is not None and memo == self._login_token:
                # Another request logged in while this one waited on the lock.
                token = memo
            else:
                with self._state_lock:
                    self._memo_cache = None
                try:
                    token = self._login(round_, rejected=rejected)
                except Exception:
                    # A token another process logged in for while this login was being
                    # tried gets this request's one replay with an unproven token, if
                    # that has not been used (TS v0.53.0).
                    cached = None if state.used_unproven_token else self._fresh_disk_token(failed)
                    if cached is None:
                        raise
                    state.used_unproven_token = True
                    state.seen_logins = self._logins_minted
                    return cached
        state.used_login_token = True
        return token

    def _newer_login_token(self, state: _AuthRecovery) -> str | None:
        """The token of a login of this client that succeeded after the request took its
        own — taken even when it equals the refused token, as a server may issue the same
        one again — but only while it is still the token in memory. Cleared, another
        request has seen it refused and is logging in anew; replaced, a token from the
        cache file (another process's login) has superseded it. Sync: ``_state_lock`` held."""
        memo = self._memo_cache
        if (
            self._logins_minted <= state.seen_logins
            or memo is None
            or memo.access_token != self._login_token
            or not is_cache_valid(memo, expected_fingerprint=self._fingerprint())
        ):
            return None
        state.used_login_token = True
        return memo.access_token

    def _fresh_disk_token(self, failed: str) -> str | None:
        """A valid token for these credentials in the shared cache file, other than
        ``failed``; it becomes the in-memory one."""
        disk = read_token_cache(self._config.token_cache_path)
        if (
            disk is None
            or not is_cache_valid(disk, expected_fingerprint=self._fingerprint())
            or _same_token(disk.access_token, failed)
        ):
            return None
        with self._state_lock:
            self._memo_cache = disk
        return disk.access_token

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
        # A login already under way is this one too: its requests and this call share it.
        round_ = self._join_login()
        with self._lock:
            token = self._login(round_)
        cache = round_.cache
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
        state = _AuthRecovery(seen_logins=self._logins_minted)
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
                    proxied=self._config.proxy is not None,
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
        # Logins this client has minted a token in; a request records it (_AuthRecovery).
        self._logins_minted = 0
        self._login_round: _LoginRound | None = None
        self._env_token_rejected = False
        self._lock = anyio.Lock()
        self._title_cache = TitleCache(cfg.title_cache_path)
        self._cache_writer = _CacheWriter(cfg.token_cache_path)

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
        memo = self._memo_cache
        if is_cache_valid(memo, expected_fingerprint=fingerprint):
            assert memo is not None
            return memo.access_token
        disk = await to_thread.run_sync(read_token_cache, self._config.token_cache_path)
        if is_cache_valid(disk, expected_fingerprint=fingerprint):
            assert disk is not None
            # A login may have put a newer token in memory while the file was read (no
            # await between this check and the write).
            memo = self._memo_cache
            if is_cache_valid(memo, expected_fingerprint=fingerprint):
                assert memo is not None
                return memo.access_token
            self._memo_cache = disk
            return disk.access_token
        round_ = self._join_login()
        async with self._lock:
            memo = self._memo_cache
            if is_cache_valid(memo, expected_fingerprint=fingerprint):
                assert memo is not None
                return memo.access_token
            try:
                return await self._login(round_)
            except Exception:
                # Another process may have logged in meanwhile (see the sync twin).
                disk = await to_thread.run_sync(read_token_cache, self._config.token_cache_path)
                if not is_cache_valid(disk, expected_fingerprint=fingerprint):
                    raise
                assert disk is not None
                self._memo_cache = disk
                return disk.access_token

    def _join_login(self) -> _LoginRound:
        # No await in between: atomic on the event loop.
        if self._login_round is None:
            self._login_round = _LoginRound()
        return self._login_round

    async def _login(self, round_: _LoginRound, rejected: str | None = None) -> str:
        """Async mirror of ``GangtiseClient._login``; a cancelled login (a timeout around
        the call, a cancelled task) leaves its round open."""
        if round_.done:
            if round_.error is not None:
                raise _shared_failure(round_.error)
            assert round_.cache is not None
            if not _same_token(round_.cache.access_token, rejected):
                if self._memo_cache is None:
                    self._memo_cache = round_.cache
                return round_.cache.access_token
            if round_.successor is None:
                round_.successor = self._join_login()
            return await self._login(round_.successor)
        try:
            cache = await self._refresh_token(round_)
        except Exception as error:
            round_.error = error
            raise
        else:
            round_.cache = cache
            return cache.access_token
        finally:
            round_.done = round_.cache is not None or round_.error is not None
            if round_.done and self._login_round is round_:
                self._login_round = None

    async def _refresh_token(self, round_: _LoginRound) -> TokenCache:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = await request_json_async(
            self._http_client(),
            endpoint,
            body=body,
            token=None,
            proxied=self._config.proxy is not None,
        )
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
        self._logins_minted += 1
        round_.minted = True
        ticket = self._cache_writer.ticket()
        try:
            await to_thread.run_sync(self._cache_writer.write, cache, ticket)
        except OSError:
            logger.debug("Failed to persist token cache; using in-memory token", exc_info=True)
        return cache

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
        token = self._newer_login_token(state)
        if token is not None:
            return token

        def from_memory() -> str | None:
            memo = self._other_memo_token(failed)
            if memo is None:
                return None
            if memo == self._login_token:
                state.used_login_token = True
                return memo
            if not state.used_unproven_token:
                state.used_unproven_token = True
                state.seen_logins = self._logins_minted
                return memo
            return None

        token = from_memory()
        if token is not None:
            return token
        if not state.used_unproven_token:
            disk = await to_thread.run_sync(read_token_cache, self._config.token_cache_path)
            token = self._newer_login_token(state) or from_memory()
            if token is not None:
                return token
            if (
                disk is not None
                and is_cache_valid(disk, expected_fingerprint=self._fingerprint())
                and not _same_token(disk.access_token, failed)
            ):
                self._memo_cache = disk
                state.used_unproven_token = True
                state.seen_logins = self._logins_minted
                return disk.access_token
        round_ = self._join_login()
        rejected = failed if round_.minted else None  # see GangtiseClient._login
        async with self._lock:
            newer = self._newer_login_token(state)
            if newer is not None:
                return newer
            memo = self._other_memo_token(failed)
            if memo is not None and memo == self._login_token:
                token = memo
            else:
                self._memo_cache = None
                try:
                    token = await self._login(round_, rejected=rejected)
                except Exception:
                    cached = (
                        None if state.used_unproven_token else await self._fresh_disk_token(failed)
                    )
                    if cached is None:
                        raise
                    state.used_unproven_token = True
                    state.seen_logins = self._logins_minted
                    return cached
        state.used_login_token = True
        return token

    def _newer_login_token(self, state: _AuthRecovery) -> str | None:
        """Mirror of ``GangtiseClient._newer_login_token`` (no await, so no lock)."""
        memo = self._memo_cache
        if (
            self._logins_minted <= state.seen_logins
            or memo is None
            or memo.access_token != self._login_token
            or not is_cache_valid(memo, expected_fingerprint=self._fingerprint())
        ):
            return None
        state.used_login_token = True
        return memo.access_token

    async def _fresh_disk_token(self, failed: str) -> str | None:
        """Async mirror of ``GangtiseClient._fresh_disk_token``."""
        disk = await to_thread.run_sync(read_token_cache, self._config.token_cache_path)
        if (
            disk is None
            or not is_cache_valid(disk, expected_fingerprint=self._fingerprint())
            or _same_token(disk.access_token, failed)
        ):
            return None
        self._memo_cache = disk
        return disk.access_token

    async def login(self) -> dict[str, Any]:
        """Async mirror of ``GangtiseClient.login``."""
        if self._config.token and not self._env_token_rejected:
            return {
                "authorization": normalize_token(self._config.token),
                "cache": None,
                "source": "env-token",
            }
        round_ = self._join_login()
        async with self._lock:
            token = await self._login(round_)
        cache = round_.cache
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
        state = _AuthRecovery(seen_logins=self._logins_minted)
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
                    proxied=self._config.proxy is not None,
                )
            except ApiError as error:
                if not self._auth_recoverable(error):
                    raise
                recovered = await self._recover_token(token, state)
                if recovered is None:
                    raise
                token = recovered
