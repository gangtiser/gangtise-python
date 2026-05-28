from __future__ import annotations

from typing import Any

from gangtise_openapi._auth import read_token_cache
from gangtise_openapi._client import GangtiseClient


class Auth:
    """`gangtise.auth.*` — authentication helpers."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def login(self) -> dict[str, Any]:
        """Force a login (or reuse cached token) and return the bearer header."""
        return self._client.login()

    def status(self) -> dict[str, Any]:
        """Inspect the current token state without forcing a network call."""
        cfg = self._client.config
        cache = read_token_cache(cfg.token_cache_path)
        return {
            "has_env_token": bool(cfg.token),
            "has_cached_token": bool(cache and cache.access_token),
            "cache": {
                "access_token": cache.access_token if cache else None,
                "expires_at": cache.expires_at if cache else None,
                "uid": cache.uid if cache else None,
                "user_name": cache.user_name if cache else None,
                "tenant_id": cache.tenant_id if cache else None,
            } if cache else None,
        }
