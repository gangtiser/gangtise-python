import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.ai import AI


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def _list_response(rows: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"list": rows},
        },
    )


def _dict_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": payload,
        },
    )


def test_knowledge_batch(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-data/ai/search/knowledge/batch").mock(
            return_value=_list_response([{"id": "1", "title": "x"}]),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = AI(client).knowledge_batch(query="test query")
        sent = route.calls.last.request.read()
        assert b'"queries":' in sent.replace(b" ", b"")
        assert b'"test query"' in sent
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "1"


def test_security_clue_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/security-clue/getList").mock(
            return_value=_list_response([{"gtsCode": "000001.SZ", "clue": "x"}]),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = AI(client).security_clue_list(
                start_time="2026-05-01",
                end_time="2026-05-28",
                query_mode="bySecurity",
                source="research",
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"source":' in sent
        assert b'"sourceList"' not in sent
    assert df.iloc[0]["gtsCode"] == "000001.SZ"


def test_one_pager(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-ai/agent/one-pager").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "summary": "hello"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = AI(client).one_pager(security_code="000001.SZ")
    assert result["summary"] == "hello"


def test_investment_logic(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-ai/agent/investment-logic").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "logic": "yes"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = AI(client).investment_logic(security_code="000001.SZ")
    assert result["logic"] == "yes"


def test_peer_comparison(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-ai/agent/peer-comparison").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "peers": []}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = AI(client).peer_comparison(security_code="000001.SZ")
    assert result["securityCode"] == "000001.SZ"


def test_research_outline(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-ai/agent/research-outline").mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "outline": "z"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = AI(client).research_outline(security_code="000001.SZ")
    assert result["outline"] == "z"


def test_theme_tracking(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/agent/theme-tracking").mock(
            return_value=_dict_response({"themeId": "T1", "items": []}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = AI(client).theme_tracking(theme_id="T1", date="2026-05-28", type_="news")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"type":' in sent
        assert b'"typeList"' not in sent
    assert result["themeId"] == "T1"


def test_hot_topic_default_categories(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/hot-topic/getList").mock(
            return_value=_list_response([{"id": "h1", "title": "topic"}]),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = AI(client).hot_topic()
        sent = route.calls.last.request.read()
        assert b'"morningBriefing"' in sent
        assert b'"noonBriefing"' in sent
        assert b'"afternoonFlash"' in sent
        assert b'"eveningBriefing"' in sent
    assert df.iloc[0]["id"] == "h1"


def test_hot_topic_omits_false_flags(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-ai/hot-topic/getList").mock(
            return_value=_list_response([{"id": "h2"}]),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            AI(client).hot_topic(
                with_related_securities=False,
                with_close_reading=False,
            )
        sent = route.calls.last.request.read()
        assert b'"withRelatedSecurities"' not in sent
        assert b'"withCloseReading"' not in sent


def test_management_discuss_announcement(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-ai/management-discuss/from-announcement"
        ).mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "discussion": "x"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = AI(client).management_discuss_announcement(
                report_date="2026-03-31",
                security_code="000001.SZ",
                dimension="all",
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"discussionDimension":"all"' in sent
        assert b'"dimension"' not in sent
    assert result["discussion"] == "x"


def test_management_discuss_earnings_call(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-ai/management-discuss/from-earningsCall"
        ).mock(
            return_value=_dict_response({"securityCode": "000001.SZ", "discussion": "y"}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = AI(client).management_discuss_earnings_call(
                report_date="2026-03-31",
                security_code="000001.SZ",
                dimension="businessOperation",
            )
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"discussionDimension":"businessOperation"' in sent
        assert b'"dimension"' not in sent
    assert result["discussion"] == "y"
