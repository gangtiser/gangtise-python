from __future__ import annotations

import threading
from typing import Any, ClassVar

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config, load_config
from gangtise_openapi._errors import ConfigError

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


class _Facade:
    """Module-level singleton exposing namespace-style access to the SDK."""

    _DOMAIN_FACTORIES: ClassVar[dict[str, str]] = {
        "auth": "gangtise_openapi.domains.auth:Auth",
        "fundamental": "gangtise_openapi.domains.fundamental:Fundamental",
        "insight": "gangtise_openapi.domains.insight:Insight",
        "lookup": "gangtise_openapi.domains.lookup:Lookup",
        "quote": "gangtise_openapi.domains.quote:Quote",
        "reference": "gangtise_openapi.domains.reference:Reference",
    }
    # mapping populated in Phase 5: additional domains added as wrappers land.

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


gangtise = _Facade()
