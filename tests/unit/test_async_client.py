from __future__ import annotations

import json

import anyio
import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError


def _login_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"accessToken": "refreshed", "expiresIn": 3600, "time": 0},
        },
    )


def _seed_stale_token(cfg: Config) -> None:
    cfg.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_cache_path.write_text(
        json.dumps({"accessToken": "stale", "expiresIn": 1, "time": 0, "expiresAt": 9999999999})
    )


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


def _cfg(tmp_path, *, token: str | None = None) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=token,
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


@pytest.mark.anyio
async def test_async_call_auth_code_8000014_triggers_one_refresh(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_stale_token(cfg)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login_route = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=_login_ok()
        )
        ep_route = router.post("/application/open-quote/quote/realtime").mock(
            side_effect=[
                httpx.Response(200, json={"code": "8000014", "status": False, "msg": "expired"}),
                httpx.Response(200, json={"code": "000000", "status": True, "data": []}),
            ]
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            out = await client._call("quote.realtime", body={"securityList": ["x"]})
    assert out == []
    assert ep_route.call_count == 2
    assert login_route.call_count == 1
    assert ep_route.calls.last.request.headers["Authorization"] == "Bearer refreshed"


@pytest.mark.anyio
async def test_async_auth_refresh_failure_propagates(tmp_path):
    # 8000014 forces a refresh; when the login itself fails, that ApiError
    # surfaces to the caller (no infinite retry).
    cfg = _cfg(tmp_path)
    _seed_stale_token(cfg)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login_route = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200, json={"code": "100001", "status": False, "msg": "login denied"}
            )
        )
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200, json={"code": "8000014", "status": False, "msg": "expired"}
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.raises(ApiError) as exc_info:
                await client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc_info.value.code == "100001"
    assert login_route.call_count == 1


@pytest.mark.anyio
async def test_async_second_auth_error_after_refresh_propagates(tmp_path):
    # The auth retry happens exactly once: a second 8000014 after a
    # successful refresh propagates as-is.
    cfg = _cfg(tmp_path)
    _seed_stale_token(cfg)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login_route = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=_login_ok()
        )
        ep_route = router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200, json={"code": "8000014", "status": False, "msg": "expired"}
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.raises(ApiError) as exc_info:
                await client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc_info.value.code == "8000014"
    assert ep_route.call_count == 2
    assert login_route.call_count == 1


@pytest.mark.anyio
async def test_async_rejected_env_token_not_reused_after_refresh(tmp_path):
    cfg = _cfg(tmp_path, token="expired-env-token")

    def data_side_effect(request):
        if request.headers["Authorization"] == "Bearer expired-env-token":
            return httpx.Response(200, json={"code": "8000014", "status": False, "msg": "expired"})
        return httpx.Response(200, json={"code": "000000", "status": True, "data": []})

    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login_route = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=_login_ok()
        )
        data_route = router.post("/application/open-quote/quote/realtime").mock(
            side_effect=data_side_effect
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            for _ in range(3):
                assert await client._call("quote.realtime", body={"securityList": ["x"]}) == []
        assert login_route.call_count == 1
        auths = [call.request.headers["Authorization"] for call in data_route.calls]
        assert auths == [
            "Bearer expired-env-token",
            "Bearer refreshed",
            "Bearer refreshed",
            "Bearer refreshed",
        ]


@pytest.mark.anyio
async def test_async_concurrent_stale_token_refresh_logs_in_once(tmp_path):
    # Five concurrent tasks sharing one stale token must trigger exactly one
    # login (mirror of the sync barrier test).
    cfg = _cfg(tmp_path)
    _seed_stale_token(cfg)
    stale_seen = 0
    gate = anyio.Event()

    async def data_side_effect(request):
        nonlocal stale_seen
        if request.headers["Authorization"] == "Bearer stale":
            stale_seen += 1
            if stale_seen == 5:
                gate.set()
            await gate.wait()
            return httpx.Response(200, json={"code": "8000014", "status": False, "msg": "expired"})
        return httpx.Response(200, json={"code": "000000", "status": True, "data": []})

    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login_route = router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=_login_ok()
        )
        router.post("/application/open-quote/quote/realtime").mock(side_effect=data_side_effect)
        results: list = []
        async with AsyncGangtiseClient(_config=cfg) as client:

            async def call() -> None:
                results.append(await client._call("quote.realtime", body={"securityList": ["x"]}))

            with anyio.fail_after(10):
                async with anyio.create_task_group() as tg:
                    for _ in range(5):
                        tg.start_soon(call)
        assert results == [[], [], [], [], []]
        assert login_route.call_count == 1


@pytest.mark.anyio
async def test_aenter_reuses_lazily_created_http_client(tmp_path):
    client = AsyncGangtiseClient(_config=_cfg(tmp_path))
    first = client._http_client()
    async with client:
        assert client._http is first
    assert first.is_closed
