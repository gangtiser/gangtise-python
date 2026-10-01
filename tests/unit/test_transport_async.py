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
    assert "联系客户经理" in exc.value.hint
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
        key="indicator.cross-section",
        method="POST",
        path="/p",
        kind="json",
        description="d",
        retry="no-999999",
    )
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError) as exc:
            await request_json_async(http, endpoint, body={}, token="tok")
    assert route.call_count == 1
    assert exc.value.hint == EDE_NO_DATA_HINT


@pytest.mark.anyio
async def test_request_json_async_no_999999_search_keeps_generic_hint(respx_mock, cfg):
    # search (also no-999999) keeps the generic hint — only the data-fetch
    # endpoints get the date/scope/param guidance (TS v0.28.2).
    respx_mock.post("/p").mock(
        return_value=httpx.Response(500, json={"code": "999999", "status": False, "msg": "err"})
    )
    endpoint = EndpointDef(
        key="indicator.search",
        method="POST",
        path="/p",
        kind="json",
        description="d",
        retry="no-999999",
    )
    async with build_async_client(cfg) as http:
        with pytest.raises(ApiError) as exc:
            await request_json_async(http, endpoint, body={}, token="tok")
    # Exact: the generic 999999 hint, NOT the EDE data-fetch hint (and not None).
    assert exc.value.hint == ERROR_HINTS["999999"]


class _AsyncTrickle(httpx.AsyncByteStream):
    def __init__(self, clock: list[float]) -> None:
        self._clock = clock

    async def __aiter__(self):
        yield b'{"code": "000000", "status": true, "data": '
        for _ in range(10):
            self._clock[0] += 5.0
            yield b" "
        yield b"null}"


@pytest.mark.anyio
async def test_async_trickling_response_is_cut_at_the_total_deadline(respx_mock, monkeypatch):
    """Async mirror of the TS v0.44.0 total deadline (2x the idle timeout for JSON)."""
    clock = [1000.0]
    monkeypatch.setattr("gangtise_openapi._transport_async.time.monotonic", lambda: clock[0])
    ep = EndpointDef(
        key="x", method="POST", path="/p", kind="json", description="d", retry="no-replay"
    )
    route = respx_mock.post("/p").mock(
        side_effect=lambda request: httpx.Response(200, stream=_AsyncTrickle(clock))
    )
    async with httpx.AsyncClient(base_url="https://api.test", timeout=10.0) as http:
        with pytest.raises(httpx.ReadTimeout, match="overall deadline"):
            await request_json_async(http, ep, body={}, token="tok")
    assert route.call_count == 1


@pytest.mark.anyio
async def test_async_deadline_also_covers_waiting_for_the_headers(monkeypatch):
    """The deadline must cover send + headers, not just the body — a
    server trickling its headers resets the idle timeout too."""
    import anyio

    from gangtise_openapi import _transport_async as mod

    monkeypatch.setattr(mod, "request_deadline_seconds", lambda *a, **k: 0.2)
    ep = EndpointDef(
        key="x", method="POST", path="/p", kind="json", description="d", retry="no-replay"
    )

    async def stall(request):
        await anyio.sleep(5)  # headers never arrive within the deadline
        return httpx.Response(200, json={"code": "000000", "status": True, "data": None})

    transport = httpx.MockTransport(stall)
    started = anyio.current_time()
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as http:
        with pytest.raises(httpx.ReadTimeout, match="overall deadline"):
            await request_json_async(http, ep, body={}, token="tok")
    assert anyio.current_time() - started < 2
