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
