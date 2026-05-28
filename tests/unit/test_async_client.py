from __future__ import annotations

import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config


@pytest.fixture
def async_cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="env-tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


@pytest.mark.anyio
async def test_async_call_uses_env_token(async_cfg):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": []},
            )
        )
        async with AsyncGangtiseClient(_config=async_cfg) as client:
            out = await client._call("quote.realtime", body={"securityList": ["x"]})
    assert out == []
    assert route.calls.last.request.headers["Authorization"] == "Bearer env-tok"


@pytest.mark.anyio
async def test_async_lookup_returns_local_data(async_cfg):
    async with AsyncGangtiseClient(_config=async_cfg) as client:
        rows = await client._call("lookup.research-areas.list")
    assert isinstance(rows, list)
    assert len(rows) > 0


@pytest.mark.anyio
async def test_async_login_returns_authorization(tmp_path):
    cfg = Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=None,
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "tok",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "x",
                        "tenantId": 1,
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            result = await client.login()
    assert result["authorization"] == "Bearer tok"
