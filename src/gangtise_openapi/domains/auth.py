# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

from typing import Any

from gangtise_openapi._auth import read_token_cache
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient


class Auth:
    """`gangtise.auth.*` — authentication helpers."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def login(self) -> dict[str, Any]:
        """报告后续请求实际会用的身份，返回 bearer 请求头与来源（auth.login）。

        设了 GANGTISE_TOKEN 时就是它（``source="env-token"``，不联网、``cache`` 为 None）；
        否则有 AK/SK 就**真的登录一次**（``source="login"``，不复用缓存——换了凭证后缓存里
        可能还是上一个账号），``cache`` 是这次登录本身的结果。
        """
        return self._client.login()

    def status(self) -> dict[str, Any]:
        """查看当前 token/缓存状态。本地方法，不发起 HTTP 请求。"""
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
            }
            if cache
            else None,
        }


class AsyncAuth:
    """Async mirror of `Auth`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def login(self) -> dict[str, Any]:
        """报告后续请求实际会用的身份，返回 bearer 请求头与来源（auth.login）。

        设了 GANGTISE_TOKEN 时就是它（``source="env-token"``，不联网、``cache`` 为 None）；
        否则有 AK/SK 就**真的登录一次**（``source="login"``，不复用缓存——换了凭证后缓存里
        可能还是上一个账号），``cache`` 是这次登录本身的结果。
        """
        return await self._client.login()

    async def status(self) -> dict[str, Any]:
        """查看当前 token/缓存状态。本地方法，不发起 HTTP 请求。"""
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
            }
            if cache
            else None,
        }
