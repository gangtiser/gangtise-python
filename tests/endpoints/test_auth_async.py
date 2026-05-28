from __future__ import annotations

import json

import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.auth import AsyncAuth


def _cfg(tmp_path, *, token: str | None = "tok") -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=token,
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
        page_concurrency=3,
    )


@pytest.mark.anyio
async def test_async_auth_status_reports_cached_token(tmp_path):
    cfg = _cfg(tmp_path, token=None)
    cfg.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_cache_path.write_text(
        json.dumps(
            {
                "accessToken": "abc",
                "expiresIn": 3600,
                "time": 0,
                "expiresAt": 9999999999,
            }
        )
    )
    async with AsyncGangtiseClient(_config=cfg) as client:
        status = await AsyncAuth(client).status()
    assert status["has_cached_token"] is True
    assert status["cache"]["access_token"] == "abc"


@pytest.mark.anyio
async def test_async_auth_login_returns_authorization(tmp_path):
    cfg = _cfg(tmp_path, token=None)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "fresh",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "u",
                        "tenantId": 1,
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            result = await AsyncAuth(client).login()
    assert result["authorization"] == "Bearer fresh"
