from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import asdict
from typing import Any

import anyio
import httpx
from anyio import to_thread

from gangtise_openapi._auth import (
    TokenCache,
    is_cache_valid,
    normalize_token,
    read_token_cache,
    require_credentials,
    write_token_cache,
)
from gangtise_openapi._config import Config, load_config
from gangtise_openapi._endpoints import EndpointDef, lookup
from gangtise_openapi._errors import ApiError
from gangtise_openapi._logging import configure_logging, get_logger
from gangtise_openapi._lookup import LOOKUP_LOADERS
from gangtise_openapi._pagination import collect_paginated, collect_paginated_async
from gangtise_openapi._title_cache import (
    TITLE_LOOKUP_SIZE,
    TitleCache,
    extract_titles,
)
from gangtise_openapi._transport import (
    build_sync_client,
    request_json,
)
from gangtise_openapi._transport_async import (
    build_async_client,
    request_json_async,
)

# Auth errors that warrant a forced re-login + one replay. 8000014/8000015 are
# AK/SK errors; 0000001008 is a server-side token invalidation (the token still
# looks valid by local expiry — e.g. logged in elsewhere — so only a forced
# refresh recovers it).
# 999002 (TOKEN_INVALID) is 0000001008's 2026-07-17 replacement, listed ahead of
# the rollout so the self-heal does not silently die when the token filter
# switches. 999011 (bad AK/SK) is deliberately absent and could not act if it
# were — it comes from auth.login, which runs unauthenticated and never reaches
# this check; its "never replay" guarantee lives in transport's
# TERMINAL_API_CODES instead.
AUTH_RETRY_CODES = frozenset({"8000014", "8000015", "0000001008", "999002"})

logger = get_logger()


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
                overrides["timeout_ms"] = int(timeout * 1000)
            if overrides:
                cfg = Config(**{**asdict(cfg), **overrides})
        self._config = cfg
        configure_logging(cfg.verbose)
        self._http: httpx.Client | None = None
        self._memo_cache: TokenCache | None = None
        self._env_token_rejected = False
        self._lock = threading.Lock()
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
        if self._http is None:
            self._http = build_sync_client(self._config)
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    # ---- Auth ----

    def _get_token(self, force_refresh: bool = False, *, stale_token: str | None = None) -> str:
        if self._config.token and not force_refresh and not self._env_token_rejected:
            return self._config.token
        if not force_refresh:
            if is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            disk = read_token_cache(self._config.token_cache_path)
            if is_cache_valid(disk):
                self._memo_cache = disk
                assert disk is not None
                return disk.access_token
        with self._lock:
            if is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                memo_token = self._memo_cache.access_token
                # A concurrent caller may have refreshed while we waited on
                # the lock; reuse its token unless it is the one that just
                # got rejected upstream (mirrors the TS refreshPromise dedup).
                if not force_refresh or (stale_token is not None and memo_token != stale_token):
                    return memo_token
            return self._refresh_token()

    def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = request_json(self._http_client(), endpoint, body=body, token=None)
        access_token: str = result["accessToken"]
        expires_in = int(result.get("expiresIn", 0))
        cache = TokenCache(
            access_token=access_token,
            expires_in=expires_in,
            time=int(result.get("time", int(time.time()))),
            expires_at=int(time.time()) + expires_in,
            uid=result.get("uid"),
            user_name=result.get("userName"),
            tenant_id=result.get("tenantId"),
        )
        self._memo_cache = cache
        try:
            write_token_cache(self._config.token_cache_path, cache)
        except OSError:
            logger.debug("Failed to persist token cache; using in-memory token", exc_info=True)
        return access_token

    # ---- Public surface used by domain wrappers ----

    def login(self) -> dict[str, Any]:
        token = self._get_token()
        cache = self._memo_cache or read_token_cache(self._config.token_cache_path)
        return {
            "authorization": normalize_token(token),
            "cache": asdict(cache) if cache else None,
        }

    def _call(
        self,
        endpoint_key: str,
        body: Any = None,
        query: dict[str, str | int] | None = None,
    ) -> Any:
        endpoint = lookup(endpoint_key)
        if endpoint.path.startswith("/guide/"):
            return list(LOOKUP_LOADERS[endpoint.key])

        def fetch_one(page_body: dict[str, Any]) -> Any:
            return self._request_once(endpoint, page_body, query)

        if endpoint.pagination is not None:
            return collect_paginated(
                endpoint,
                body=body or {},
                fetch=fetch_one,
                concurrency=self._config.page_concurrency,
            )
        return self._request_once(endpoint, body or {}, query)

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
            except OSError:
                logger.debug("Failed to persist title cache", exc_info=True)

    def _resolve_title(
        self,
        list_endpoint_key: str,
        id_field: str,
        id_value: str,
        title_field: str = "title",
    ) -> str | None:
        cached = self._title_cache.lookup(list_endpoint_key, id_value)
        if cached:
            return cached
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
            except OSError:
                logger.debug("Failed to persist title cache", exc_info=True)
        return titles.get(str(id_value))

    def _request_once(
        self,
        endpoint: EndpointDef,
        body: Any,
        query: dict[str, str | int] | None,
    ) -> Any:
        token = self._get_token()
        try:
            return request_json(self._http_client(), endpoint, body=body, token=token, query=query)
        except ApiError as error:
            if (
                error.code in AUTH_RETRY_CODES
                and self._config.access_key
                and self._config.secret_key
            ):
                if token == self._config.token:
                    # The env-provided token was rejected upstream; stop
                    # preferring it over refreshed tokens from now on.
                    self._env_token_rejected = True
                token = self._get_token(force_refresh=True, stale_token=token)
                return request_json(
                    self._http_client(), endpoint, body=body, token=token, query=query
                )
            raise


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
                overrides["timeout_ms"] = int(timeout * 1000)
            if overrides:
                cfg = Config(**{**asdict(cfg), **overrides})
        self._config = cfg
        configure_logging(cfg.verbose)
        self._http: httpx.AsyncClient | None = None
        self._http_loop: asyncio.AbstractEventLoop | None = None
        self._memo_cache: TokenCache | None = None
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

    async def _get_token(
        self, force_refresh: bool = False, *, stale_token: str | None = None
    ) -> str:
        if self._config.token and not force_refresh and not self._env_token_rejected:
            return self._config.token
        if not force_refresh:
            if is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            disk = await to_thread.run_sync(read_token_cache, self._config.token_cache_path)
            if is_cache_valid(disk):
                self._memo_cache = disk
                assert disk is not None
                return disk.access_token
        async with self._lock:
            if is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                memo_token = self._memo_cache.access_token
                # A concurrent caller may have refreshed while we waited on
                # the lock; reuse its token unless it is the one that just
                # got rejected upstream (mirrors the TS refreshPromise dedup).
                if not force_refresh or (stale_token is not None and memo_token != stale_token):
                    return memo_token
            return await self._refresh_token()

    async def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = await request_json_async(self._http_client(), endpoint, body=body, token=None)
        access_token: str = result["accessToken"]
        expires_in = int(result.get("expiresIn", 0))
        cache = TokenCache(
            access_token=access_token,
            expires_in=expires_in,
            time=int(result.get("time", int(time.time()))),
            expires_at=int(time.time()) + expires_in,
            uid=result.get("uid"),
            user_name=result.get("userName"),
            tenant_id=result.get("tenantId"),
        )
        self._memo_cache = cache
        try:
            await to_thread.run_sync(write_token_cache, self._config.token_cache_path, cache)
        except OSError:
            logger.debug("Failed to persist token cache; using in-memory token", exc_info=True)
        return access_token

    async def login(self) -> dict[str, Any]:
        token = await self._get_token()
        cache = self._memo_cache or await to_thread.run_sync(
            read_token_cache, self._config.token_cache_path
        )
        return {
            "authorization": normalize_token(token),
            "cache": asdict(cache) if cache else None,
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
            except OSError:
                logger.debug("Failed to persist title cache", exc_info=True)

    async def _resolve_title(
        self,
        list_endpoint_key: str,
        id_field: str,
        id_value: str,
        title_field: str = "title",
    ) -> str | None:
        cached = self._title_cache.lookup(list_endpoint_key, id_value)
        if cached:
            return cached
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
            except OSError:
                logger.debug("Failed to persist title cache", exc_info=True)
        return titles.get(str(id_value))

    async def _call(
        self,
        endpoint_key: str,
        body: Any = None,
        query: dict[str, str | int] | None = None,
    ) -> Any:
        endpoint = lookup(endpoint_key)
        if endpoint.path.startswith("/guide/"):
            return list(LOOKUP_LOADERS[endpoint.key])

        async def fetch_one(page_body: dict[str, Any]) -> Any:
            return await self._request_once(endpoint, page_body, query)

        if endpoint.pagination is not None:
            return await collect_paginated_async(
                endpoint,
                body=body or {},
                fetch=fetch_one,
                concurrency=self._config.page_concurrency,
            )
        return await self._request_once(endpoint, body or {}, query)

    async def _request_once(
        self,
        endpoint: EndpointDef,
        body: Any,
        query: dict[str, str | int] | None,
    ) -> Any:
        token = await self._get_token()
        try:
            return await request_json_async(
                self._http_client(), endpoint, body=body, token=token, query=query
            )
        except ApiError as error:
            if (
                error.code in AUTH_RETRY_CODES
                and self._config.access_key
                and self._config.secret_key
            ):
                if token == self._config.token:
                    # The env-provided token was rejected upstream; stop
                    # preferring it over refreshed tokens from now on.
                    self._env_token_rejected = True
                token = await self._get_token(force_refresh=True, stale_token=token)
                return await request_json_async(
                    self._http_client(), endpoint, body=body, token=token, query=query
                )
            raise
