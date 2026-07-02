from __future__ import annotations

import asyncio
import contextlib
import threading
from typing import TYPE_CHECKING, Any, ClassVar

import anyio

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._config import Config, load_config
from gangtise_openapi._errors import ConfigError

if TYPE_CHECKING:
    from gangtise_openapi.domains import (
        AI,
        Alternative,
        AsyncAI,
        AsyncAlternative,
        AsyncAuth,
        AsyncFundamental,
        AsyncIndicator,
        AsyncInsight,
        AsyncLookup,
        AsyncQuote,
        AsyncReference,
        AsyncVault,
        Auth,
        Fundamental,
        Indicator,
        Insight,
        Lookup,
        Quote,
        Reference,
        Vault,
    )

_CONFIG_FIELDS_FOR_EQUALITY = (
    "base_url",
    "access_key",
    "secret_key",
    "token",
    "token_cache_path",
    "title_cache_path",
    "timeout_ms",
    "page_concurrency",
)


def _signature(cfg: Config) -> tuple[Any, ...]:
    return tuple(getattr(cfg, field) for field in _CONFIG_FIELDS_FOR_EQUALITY)


def _running_asyncio_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class _Facade:
    """Module-level singleton exposing namespace-style access to the SDK."""

    _DOMAIN_FACTORIES: ClassVar[dict[str, str]] = {
        "ai": "gangtise_openapi.domains.ai:AI",
        "alternative": "gangtise_openapi.domains.alternative:Alternative",
        "auth": "gangtise_openapi.domains.auth:Auth",
        "fundamental": "gangtise_openapi.domains.fundamental:Fundamental",
        "indicator": "gangtise_openapi.domains.indicator:Indicator",
        "insight": "gangtise_openapi.domains.insight:Insight",
        "lookup": "gangtise_openapi.domains.lookup:Lookup",
        "quote": "gangtise_openapi.domains.quote:Quote",
        "reference": "gangtise_openapi.domains.reference:Reference",
        "vault": "gangtise_openapi.domains.vault:Vault",
    }
    # mapping populated in Phase 5: additional domains added as wrappers land.

    if TYPE_CHECKING:
        ai: AI
        alternative: Alternative
        auth: Auth
        fundamental: Fundamental
        indicator: Indicator
        insight: Insight
        lookup: Lookup
        quote: Quote
        reference: Reference
        vault: Vault

    def __init__(self) -> None:
        self._client: GangtiseClient | None = None
        self._signature: tuple[Any, ...] | None = None
        self._domains: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ---- Lifecycle ----

    def configure(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        replace: bool = False,
    ) -> GangtiseClient:
        with self._lock:
            new_client = GangtiseClient(
                access_key=access_key,
                secret_key=secret_key,
                base_url=base_url,
                token=token,
                timeout=timeout,
            )
            new_signature = _signature(new_client.config)
            if self._client is not None and not replace:
                if new_signature == self._signature:
                    new_client.close()
                    return self._client
                new_client.close()
                raise ConfigError(
                    "default client already configured with different settings; "
                    "call gangtise.reset() or pass replace=True"
                )
            self._close_client()
            self._client = new_client
            self._signature = new_signature
            return new_client

    def reset(self) -> None:
        with self._lock:
            self._close_client()

    def _close_client(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._signature = None
        self._domains.clear()
        # also reset async facade
        if hasattr(self, "_async_facade"):
            self._async_facade.close()
            del self._async_facade

    def _ensure_client(self) -> GangtiseClient:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    cfg = load_config()
                    self._client = GangtiseClient(_config=cfg)
                    self._signature = _signature(cfg)
        assert self._client is not None
        return self._client

    # ---- Domain attribute dispatch (filled in by Phase 5 tasks) ----

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._DOMAIN_FACTORIES:
            raise AttributeError(f"unknown domain or attribute: {name!r}")
        if name not in self._domains:
            module_path, class_name = self._DOMAIN_FACTORIES[name].split(":")
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            self._domains[name] = cls(self._ensure_client())
        return self._domains[name]

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(self._DOMAIN_FACTORIES))

    # ---- Async mirror ----

    @property
    def async_(self) -> _AsyncFacade:
        if not hasattr(self, "_async_facade"):
            self._async_facade = _AsyncFacade(parent=self)
        return self._async_facade


class _AsyncFacade:
    """Async mirror of `_Facade`. Lazy attribute dispatch to async domain wrappers."""

    _DOMAIN_FACTORIES: ClassVar[dict[str, str]] = {
        "auth": "gangtise_openapi.domains.auth:AsyncAuth",
        "lookup": "gangtise_openapi.domains.lookup:AsyncLookup",
        "reference": "gangtise_openapi.domains.reference:AsyncReference",
        "insight": "gangtise_openapi.domains.insight:AsyncInsight",
        "quote": "gangtise_openapi.domains.quote:AsyncQuote",
        "fundamental": "gangtise_openapi.domains.fundamental:AsyncFundamental",
        "ai": "gangtise_openapi.domains.ai:AsyncAI",
        "vault": "gangtise_openapi.domains.vault:AsyncVault",
        "alternative": "gangtise_openapi.domains.alternative:AsyncAlternative",
        "indicator": "gangtise_openapi.domains.indicator:AsyncIndicator",
    }

    if TYPE_CHECKING:
        ai: AsyncAI
        alternative: AsyncAlternative
        auth: AsyncAuth
        fundamental: AsyncFundamental
        indicator: AsyncIndicator
        insight: AsyncInsight
        lookup: AsyncLookup
        quote: AsyncQuote
        reference: AsyncReference
        vault: AsyncVault

    def __init__(self, parent: _Facade) -> None:
        self._parent = parent
        self._client: AsyncGangtiseClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._domains: dict[str, Any] = {}

    def _ensure_client(self) -> AsyncGangtiseClient:
        loop = _running_asyncio_loop()
        if (
            self._client is not None
            and loop is not None
            and self._loop is not None
            and self._loop is not loop
        ):
            # A previous asyncio.run() closed the old loop. Do not hand out domain
            # wrappers bound to that loop's AsyncClient.
            self._client = None
            self._domains.clear()
        if self._client is None:
            parent_client = self._parent._client
            cfg = parent_client.config if parent_client is not None else load_config()
            self._client = AsyncGangtiseClient(_config=cfg)
            self._loop = loop
        elif self._loop is None:
            self._loop = loop
        return self._client

    async def aclose(self) -> None:
        client = self._client
        self._client = None
        self._loop = None
        self._domains.clear()
        if client is not None:
            await client.aclose()

    def close(self) -> None:
        client = self._client
        self._client = None
        self._loop = None
        self._domains.clear()
        if client is None:
            return

        async def close_client() -> None:
            # Closing a client created on an already-closed event loop can raise
            # from the transport. The facade must still drop the stale reference.
            with contextlib.suppress(RuntimeError):
                await client.aclose()

        loop = _running_asyncio_loop()
        if loop is None:
            anyio.run(close_client)
        else:
            loop.create_task(close_client())

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._DOMAIN_FACTORIES:
            raise AttributeError(f"unknown async domain: {name!r}")
        if name not in self._domains:
            module_path, class_name = self._DOMAIN_FACTORIES[name].split(":")
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            self._domains[name] = cls(self._ensure_client())
        return self._domains[name]

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(self._DOMAIN_FACTORIES))


gangtise = _Facade()
