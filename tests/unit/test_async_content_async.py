from __future__ import annotations

import pytest

from gangtise_openapi._async_content import poll_content_async
from gangtise_openapi._errors import ApiError


@pytest.mark.anyio
async def test_async_poll_ready_on_first():
    async def fetch():
        return {"content": "ready"}

    out = await poll_content_async(fetch)
    assert out == {"content": "ready"}


@pytest.mark.anyio
async def test_async_poll_terminal_raises(monkeypatch):
    import anyio

    async def fast_sleep(_):
        await anyio.sleep(0)

    monkeypatch.setattr("gangtise_openapi._async_content.anyio.sleep", fast_sleep)

    async def fetch():
        raise ApiError("terminal", code="410111")

    with pytest.raises(ApiError) as exc:
        await poll_content_async(fetch)
    assert exc.value.code == "410111"


@pytest.mark.anyio
async def test_async_poll_unrelated_propagates():
    async def fetch():
        raise ApiError("auth bad", code="8000014")

    with pytest.raises(ApiError) as exc:
        await poll_content_async(fetch)
    assert exc.value.code == "8000014"


@pytest.mark.anyio
async def test_async_poll_exhaustion_raises(monkeypatch):
    async def fast_sleep(_):
        return None

    monkeypatch.setattr("gangtise_openapi._async_content.anyio.sleep", fast_sleep)

    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        raise ApiError("pending", code="410110")

    with pytest.raises(ApiError) as exc:
        await poll_content_async(fetch)
    assert exc.value.code == "410110"
    assert "14 attempts" in str(exc.value)
    assert calls["n"] == 14


# ── TS v0.28.0 mirrors: the renumbered async status codes ──


@pytest.mark.anyio
async def test_async_poll_treats_140001_as_pending(monkeypatch):
    import anyio

    real_sleep = anyio.sleep  # bind before patching, else fast_sleep recurses

    async def fast_sleep(_):
        await real_sleep(0)

    monkeypatch.setattr("gangtise_openapi._async_content.anyio.sleep", fast_sleep)
    state = {"i": 0}

    async def fetch():
        state["i"] += 1
        if state["i"] < 3:
            raise ApiError("生成中", code="140001", status_code=409)
        return {"content": "done"}

    out = await poll_content_async(fetch)
    assert out == {"content": "done"}
    assert state["i"] == 3


@pytest.mark.anyio
async def test_async_poll_treats_140002_as_terminal():
    async def fetch():
        raise ApiError("生成失败", code="140002", status_code=500)

    with pytest.raises(ApiError) as exc:
        await poll_content_async(fetch)
    assert exc.value.code == "140002"


@pytest.mark.anyio
async def test_async_terminal_error_keeps_server_message_and_trace():
    async def fetch():
        raise ApiError(
            "敏感内容拦截",
            code="410111",
            status_code=400,
            details={"traceId": "830965044897325056"},
        )

    with pytest.raises(ApiError) as exc:
        await poll_content_async(fetch)
    text = str(exc.value)
    assert "敏感内容拦截" in text
    assert "830965044897325056" in text
    assert exc.value.trace_id == "830965044897325056"
