from __future__ import annotations

import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.ai import AsyncAI


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def _dict_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": "000000", "status": True, "data": payload},
    )


_EARNINGS_GET_ID = "/application/open-ai/agent/earnings-review-getid"
_EARNINGS_GET_CONTENT = "/application/open-ai/agent/earnings-review-getcontent"


@pytest.mark.anyio
async def test_async_one_pager(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-ai/agent/one-pager").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "summary": "hello"}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).one_pager(security_code="000001.SZ")
    assert result["summary"] == "hello"


@pytest.mark.anyio
async def test_async_earnings_review_wait_true_returns_content(tmp_path, monkeypatch):
    # poll_content_async sleeps via anyio.sleep — monkeypatch to no-op
    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr(
        "gangtise_openapi._async_content.anyio.sleep", _no_sleep
    )
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_EARNINGS_GET_ID).mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"dataId": "abc"}},
            )
        )
        router.post(_EARNINGS_GET_CONTENT).mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"content": "result"}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).earnings_review(
                security_code="600519.SH", period="2026q1",
            )
    assert result["content"] == "result"


@pytest.mark.anyio
async def test_async_earnings_review_wait_false_returns_pending(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post(_EARNINGS_GET_ID).mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"dataId": "abc"}},
            )
        )
        content_route = router.post(_EARNINGS_GET_CONTENT)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).earnings_review(
                security_code="600519.SH", period="2026q1", wait=False,
            )
        assert content_route.call_count == 0
    assert result == {"data_id": "abc", "status": "pending"}
