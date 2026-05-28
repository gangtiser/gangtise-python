from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any

import anyio
import httpx

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

AUTH_RETRY_CODES = frozenset({"8000014", "8000015"})


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
        self._http: httpx.Client | None = None
        self._memo_cache: TokenCache | None = None
        self._lock = threading.Lock()
        self._title_cache = TitleCache(cfg.title_cache_path)

    @property
    def config(self) -> Config:
        return self._config

    def __enter__(self) -> GangtiseClient:
        self._http = build_sync_client(self._config)
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

    def _get_token(self, force_refresh: bool = False) -> str:
        if self._config.token and not force_refresh:
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
            if not force_refresh and is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            return self._refresh_token()

    def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = request_json(
            self._http_client(), self._config, endpoint, body=body, token=None
        )
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
        write_token_cache(self._config.token_cache_path, cache)
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
            self._title_cache.flush()

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
            self._title_cache.flush()
        return titles.get(str(id_value))

    def _request_once(
        self,
        endpoint: EndpointDef,
        body: Any,
        query: dict[str, str | int] | None,
    ) -> Any:
        try:
            token = self._get_token()
            return request_json(
                self._http_client(),
                self._config,
                endpoint,
                body=body,
                token=token,
                query=query,
            )
        except ApiError as error:
            if (
                error.code in AUTH_RETRY_CODES
                and self._config.access_key
                and self._config.secret_key
            ):
                self._memo_cache = None
                token = self._get_token(force_refresh=True)
                return request_json(
                    self._http_client(),
                    self._config,
                    endpoint,
                    body=body,
                    token=token,
                    query=query,
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
        self._http: httpx.AsyncClient | None = None
        self._memo_cache: TokenCache | None = None
        self._lock = anyio.Lock()
        self._title_cache = TitleCache(cfg.title_cache_path)

    @property
    def config(self) -> Config:
        return self._config

    async def __aenter__(self) -> AsyncGangtiseClient:
        self._http = build_async_client(self._config)
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
            await self._http.aclose()
            self._http = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = build_async_client(self._config)
        return self._http

    async def _get_token(self, force_refresh: bool = False) -> str:
        if self._config.token and not force_refresh:
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
        async with self._lock:
            if not force_refresh and is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            return await self._refresh_token()

    async def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = await request_json_async(
            self._http_client(), self._config, endpoint, body=body, token=None
        )
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
        write_token_cache(self._config.token_cache_path, cache)
        return access_token

    async def login(self) -> dict[str, Any]:
        token = await self._get_token()
        cache = self._memo_cache or read_token_cache(self._config.token_cache_path)
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
            self._title_cache.flush()

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
            self._title_cache.flush()
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
        try:
            token = await self._get_token()
            return await request_json_async(
                self._http_client(),
                self._config,
                endpoint,
                body=body,
                token=token,
                query=query,
            )
        except ApiError as error:
            if (
                error.code in AUTH_RETRY_CODES
                and self._config.access_key
                and self._config.secret_key
            ):
                self._memo_cache = None
                token = await self._get_token(force_refresh=True)
                return await request_json_async(
                    self._http_client(),
                    self._config,
                    endpoint,
                    body=body,
                    token=token,
                    query=query,
                )
            raise
