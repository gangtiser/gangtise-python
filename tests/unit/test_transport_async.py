from __future__ import annotations

import httpx
import pytest

from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import EDE_NO_DATA_HINT, ERROR_HINTS, ApiError
from gangtise_openapi._transport_async import build_async_client, request_json_async


def _endpoint() -> EndpointDef:
    return EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=None,
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


@pytest.mark.anyio
async def test_request_json_async_success(respx_mock, cfg):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 1}})
    )
    async with build_async_client(cfg) as http:
        out = await request_json_async(http, _endpoint(), body={}, token="tok")
    assert out == {"v": 1}


@pytest.mark.anyio
async def test_request_json_async_500_then_success(respx_mock, cfg):
    respx_mock.post("/p").mock(
        side_effect=[
            httpx.Response(500, text="boom"),
            httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 2}}),
        ]
    )
    async with build_async_client(cfg) as http:
        out = await request_json_async(http, _endpoint(), body={}, token="tok")
    assert out == {"v": 2}


@pytest.mark.anyio
async def test_request_json_async_envelope_error_raises(respx_mock, cfg):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "999997", "status": False, "msg": "no perm"})
    )
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError) as exc:
            await request_json_async(http, _endpoint(), body={}, token="tok")
    assert exc.value.code == "999997"


@pytest.mark.anyio
async def test_request_json_async_4xx_envelope_code_and_hint(respx_mock, cfg):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(403, json={"code": "999997", "status": False, "msg": "no perm"})
    )
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError) as exc:
            await request_json_async(http, _endpoint(), body={}, token="tok")
    assert exc.value.code == "999997"
    assert exc.value.status_code == 403
    assert exc.value.hint == ERROR_HINTS["999997"]
    assert "权限" in exc.value.hint
    assert route.call_count == 1


@pytest.mark.anyio
async def test_request_json_async_503_exhausts_retries(respx_mock, cfg, monkeypatch):
    async def fast_sleep(_):
        return None

    monkeypatch.setattr("gangtise_openapi._transport_async.anyio.sleep", fast_sleep)
    route = respx_mock.post("/p").mock(return_value=httpx.Response(503, text="unavailable"))
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError) as exc:
            await request_json_async(http, _endpoint(), body={}, token="tok")
    assert exc.value.status_code == 503
    # initial attempt + max_retries (2) = 3 requests total
    assert route.call_count == 3


@pytest.mark.anyio
async def test_request_json_async_non_retryable_raises_immediately(respx_mock, cfg):
    route = respx_mock.post("/p").mock(return_value=httpx.Response(400, text="bad request"))
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError) as exc:
            await request_json_async(http, _endpoint(), body={}, token="tok")
    assert exc.value.status_code == 400
    assert route.call_count == 1


@pytest.mark.anyio
async def test_request_json_async_attaches_authorization_header(respx_mock, cfg):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {}})
    )
    async with build_async_client(cfg) as http:
        await request_json_async(http, _endpoint(), body={}, token="tok")
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert route.calls.last.request.headers["user-agent"].startswith("gangtise-openapi-python/")


def _no_replay_endpoint() -> EndpointDef:
    return EndpointDef(
        key="x", method="POST", path="/p", kind="json", description="d", retry="no-replay"
    )


@pytest.mark.anyio
async def test_request_json_async_no_replay_does_not_retry_500(respx_mock, cfg):
    route = respx_mock.post("/p").mock(return_value=httpx.Response(500, text="boom"))
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError):
            await request_json_async(http, _no_replay_endpoint(), body={}, token="tok")
    assert route.call_count == 1


@pytest.mark.anyio
async def test_request_json_async_no_999999_fails_fast_with_ede_hint(respx_mock, cfg):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(500, json={"code": "999999", "status": False, "msg": "err"})
    )
    endpoint = EndpointDef(
        key="x", method="POST", path="/p", kind="json", description="d", retry="no-999999"
    )
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError) as exc:
            await request_json_async(http, endpoint, body={}, token="tok")
    assert route.call_count == 1
    assert exc.value.hint == EDE_NO_DATA_HINT
