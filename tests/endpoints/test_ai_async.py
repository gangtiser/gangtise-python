from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ValidationError
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


def _list_response(rows: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": "000000", "status": True, "data": {"total": len(rows), "list": rows}},
    )


_EARNINGS_GET_ID = "/application/open-ai/agent/earnings-review-getid"
_EARNINGS_GET_CONTENT = "/application/open-ai/agent/earnings-review-getcontent"
_VIEWPOINT_GET_ID = "/application/open-ai/agent/viewpoint-debate-getid"
_VIEWPOINT_GET_CONTENT = "/application/open-ai/agent/viewpoint-debate-getcontent"


@pytest.mark.anyio
async def test_async_knowledge_batch_body_shape(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-data/ai/search/knowledge/batch").mock(
            return_value=_list_response([{"id": "1", "title": "x"}]),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncAI(client).knowledge_batch(
                query="q1",
                resource_type=1,
                knowledge_name="kb",
                start_time=1767225600000,
                end_time=1769904000000,
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"queries":["q1"]' in sent
        assert b'"top":10' in sent
        assert b'"resourceTypes":[1]' in sent
        assert b'"knowledgeNames":["kb"]' in sent
        assert b'"startTime":1767225600000' in sent
        assert b'"endTime":1769904000000' in sent
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "1"


@pytest.mark.anyio
async def test_async_knowledge_batch_empty_resource_type_omitted(tmp_path):
    # TS omits resourceTypes when empty (`.length` guard); Python must match.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-data/ai/search/knowledge/batch").mock(
            return_value=_list_response([{"id": "1"}]),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncAI(client).knowledge_batch(query="q1", resource_type=[])
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"resourceTypes"' not in sent


@pytest.mark.anyio
async def test_async_security_clue_list_sends_bare_source(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/security-clue/getList").mock(
            return_value=_list_response([{"gtsCode": "000001.SZ", "clue": "x"}]),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncAI(client).security_clue_list(
                start_time="2026-05-01",
                end_time="2026-05-28",
                query_mode="bySecurity",
                gts_code="000001.SZ",
                source="research",
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"startTime":"2026-05-01"' in sent
        assert b'"endTime":"2026-05-28"' in sent
        assert b'"queryMode":"bySecurity"' in sent
        assert b'"gtsCodeList":["000001.SZ"]' in sent
        # TS sends bare `source`, NOT `sourceList`.
        assert b'"source":["research"]' in sent
        assert b'"sourceList"' not in sent
    assert df.iloc[0]["gtsCode"] == "000001.SZ"


@pytest.mark.anyio
async def test_async_investment_logic(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/agent/investment-logic").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "logic": "yes"}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).investment_logic(security_code="000001.SZ")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityCode":"000001.SZ"' in sent
    assert result["logic"] == "yes"


@pytest.mark.anyio
async def test_async_peer_comparison(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/agent/peer-comparison").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "peers": []}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).peer_comparison(security_code="000001.SZ")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityCode":"000001.SZ"' in sent
    assert result["securityCode"] == "000001.SZ"


@pytest.mark.anyio
async def test_async_research_outline(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/agent/research-outline").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "outline": "z"}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).research_outline(security_code="000001.SZ")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityCode":"000001.SZ"' in sent
    assert result["outline"] == "z"


@pytest.mark.anyio
async def test_async_theme_tracking_sends_bare_type(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/agent/theme-tracking").mock(
            return_value=_dict_response({"themeId": "T1", "items": []}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).theme_tracking(
                theme_id="T1", date="2026-05-28", type_="news"
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"themeId":"T1"' in sent
        assert b'"date":"2026-05-28"' in sent
        assert b'"type":["news"]' in sent
        assert b'"typeList"' not in sent
    assert result["themeId"] == "T1"


@pytest.mark.anyio
async def test_async_hot_topic_default_categories(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/hot-topic/getList").mock(
            return_value=_list_response([{"id": "h1", "title": "topic"}]),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncAI(client).hot_topic()
        sent = route.calls.last.request.read()
        assert b'"morningBriefing"' in sent
        assert b'"noonBriefing"' in sent
        assert b'"afternoonFlash"' in sent
        assert b'"eveningBriefing"' in sent
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "h1"


@pytest.mark.anyio
async def test_async_hot_topic_sends_false_flags(tmp_path):
    # TS v0.19.0 parity: flags go out as explicit booleans, so False sends false.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/hot-topic/getList").mock(
            return_value=_list_response([{"id": "h2"}]),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncAI(client).hot_topic(
                with_related_securities=False,
                with_close_reading=False,
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"withRelatedSecurities":false' in sent
        assert b'"withCloseReading":false' in sent


@pytest.mark.anyio
async def test_async_raw_passthrough(tmp_path):
    payload = {"total": 1, "list": [{"id": "1"}]}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        for path in (
            "/application/open-data/ai/search/knowledge/batch",
            "/application/open-ai/security-clue/getList",
            "/application/open-ai/hot-topic/getList",
        ):
            router.post(path).mock(return_value=_list_response([{"id": "1"}]))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            ai = AsyncAI(client)
            assert await ai.knowledge_batch(query="q", raw=True) == payload
            assert (
                await ai.security_clue_list(
                    start_time="2026-05-01",
                    end_time="2026-05-28",
                    query_mode="bySecurity",
                    raw=True,
                )
                == payload
            )
            assert await ai.hot_topic(raw=True) == payload


@pytest.mark.anyio
async def test_async_management_discuss_announcement(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/management-discuss/from-announcement").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "discussion": "x"}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).management_discuss_announcement(
                report_date="2026-03-31",
                security_code="000001.SZ",
                dimension="all",
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"reportDate":"2026-03-31"' in sent
        assert b'"discussionDimension":"all"' in sent
        assert b'"dimension"' not in sent
    assert result["discussion"] == "x"


@pytest.mark.anyio
async def test_async_management_discuss_earnings_call(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/management-discuss/from-earningsCall").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "discussion": "y"}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).management_discuss_earnings_call(
                report_date="2026-03-31",
                security_code="000001.SZ",
                dimension="businessOperation",
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"reportDate":"2026-03-31"' in sent
        assert b'"discussionDimension":"businessOperation"' in sent
        assert b'"dimension"' not in sent
    assert result["discussion"] == "y"


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

    monkeypatch.setattr("gangtise_openapi._async_content.anyio.sleep", _no_sleep)
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
                security_code="600519.SH",
                period="2026q1",
            )
    assert result["content"] == "result"


@pytest.mark.anyio
async def test_async_earnings_review_polls_on_410110_then_succeeds(tmp_path, monkeypatch):
    # poll_content_async sleeps via anyio.sleep — monkeypatch to no-op so the
    # 410110-pending -> retry -> success path runs instantly (<1s).
    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("gangtise_openapi._async_content.anyio.sleep", _no_sleep)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post(_EARNINGS_GET_ID).mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"dataId": "abc"}},
            )
        )
        content_route = router.post(_EARNINGS_GET_CONTENT).mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"code": "410110", "status": False, "msg": "pending"},
                ),
                httpx.Response(
                    200,
                    json={"code": "000000", "status": True, "data": {"content": "done"}},
                ),
            ]
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).earnings_review(
                security_code="600519.SH",
                period="2026q1",
            )
    assert result["content"] == "done"
    assert content_route.call_count == 2


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
                security_code="600519.SH",
                period="2026q1",
                wait=False,
            )
        assert content_route.call_count == 0
    assert result == {"data_id": "abc", "status": "pending"}


@pytest.mark.anyio
async def test_async_earnings_review_check_returns_server_response(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_EARNINGS_GET_CONTENT).mock(
            return_value=_dict_response({"content": None}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).earnings_review_check(data_id="abc")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"dataId":"abc"' in sent
    assert result == {"content": None}


@pytest.mark.anyio
async def test_async_viewpoint_debate_wait_true_returns_content(tmp_path, monkeypatch):
    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("gangtise_openapi._async_content.anyio.sleep", _no_sleep)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        id_route = router.post(_VIEWPOINT_GET_ID).mock(
            return_value=_dict_response({"dataId": "xyz"}),
        )
        router.post(_VIEWPOINT_GET_CONTENT).mock(
            return_value=_dict_response({"content": "debate"}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).viewpoint_debate(viewpoint="AI is bullish")
        sent = id_route.calls.last.request.read().replace(b" ", b"")
        assert b'"viewpoint":"AIisbullish"' in sent
    assert result["content"] == "debate"


@pytest.mark.anyio
async def test_async_viewpoint_debate_wait_false_returns_pending(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post(_VIEWPOINT_GET_ID).mock(
            return_value=_dict_response({"dataId": "xyz"}),
        )
        content_route = router.post(_VIEWPOINT_GET_CONTENT)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).viewpoint_debate(
                viewpoint="AI is bullish",
                wait=False,
            )
        assert content_route.call_count == 0
    assert result == {"data_id": "xyz", "status": "pending"}


@pytest.mark.anyio
async def test_async_viewpoint_debate_check_returns_server_response(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_VIEWPOINT_GET_CONTENT).mock(
            return_value=_dict_response({"content": None}),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAI(client).viewpoint_debate_check(data_id="xyz")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"dataId":"xyz"' in sent
    assert result == {"content": None}


@pytest.mark.anyio
async def test_async_knowledge_resource_download_writes_file(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-data/ai/resource/download").mock(
            return_value=httpx.Response(
                200,
                content=b"resource",
                headers={"content-disposition": 'attachment; filename="kb.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            path = await AsyncAI(client).knowledge_resource_download(
                resource_type=1,
                source_id="s1",
                output=tmp_path / "out.pdf",
            )
        sent_url = str(route.calls.last.request.url)
        assert "resourceType=1" in sent_url
        assert "sourceId=s1" in sent_url
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"resource"


@pytest.mark.anyio
async def test_async_stock_summary_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/stock-summary/getList").mock(
            return_value=_list_response([{"securityCode": "600519.SH", "summary": "x"}]),
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncAI(client).stock_summary_list(security="600519.SH")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityList":["600519.SH"]' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["securityCode"] == "600519.SH"


@pytest.mark.anyio
async def test_async_stock_summary_list_requires_security(tmp_path):
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        with pytest.raises(ValidationError):
            await AsyncAI(client).stock_summary_list(security=[])
