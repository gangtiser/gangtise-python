"""tool.web_search (TS v0.41.0 ⑥, default size with page bodies v0.44.0 ⑧)."""

from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.tool import AsyncTool, Tool

_PATH = "/application/open-tool/web-search/search"
_ANSWER = {
    "query": "减持新规",
    "total": 1,
    "hints": [],
    "list": [
        {
            "title": "关于减持的规定",
            "url": "https://www.csrc.gov.cn/x.html",
            "site": "csrc.gov.cn",
            "tier": "T0",
            "publishTime": None,
            "flags": [],
        }
    ],
}


def _ok(data) -> httpx.Response:
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


def _sent(route) -> dict:
    return json.loads(route.calls.last.request.content)


def test_web_search_minimal_call_sends_query_and_default_size(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PATH).mock(return_value=_ok(_ANSWER))
        with GangtiseClient(_config=seeded_config) as client:
            df = Tool(client).web_search(query="减持新规")
    assert _sent(route) == {"query": "减持新规", "size": 10}
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["tier"] == "T0"


def test_web_search_full_body_dedupes_sites(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PATH).mock(return_value=_ok(_ANSWER))
        with GangtiseClient(_config=seeded_config) as client:
            raw = Tool(client).web_search(
                query="减持新规",
                size=2,
                freshness="week",
                min_tier="T1",
                site=["csrc.gov.cn", "sse.com.cn", "csrc.gov.cn"],
                include_content=True,
                max_content_chars=6000,
                raw=True,
            )
    assert _sent(route) == {
        "query": "减持新规",
        "size": 2,
        "freshness": "week",
        "minTier": "T1",
        "siteList": ["csrc.gov.cn", "sse.com.cn"],
        "includeContent": True,
        "maxContentChars": 6000,
    }
    assert raw["hints"] == []


def test_web_search_include_content_defaults_size_to_its_lower_cap(seeded_config):
    # With bodies on the cap drops to 5, and the default follows it: include_content
    # alone must not fail on a size nobody passed.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PATH).mock(return_value=_ok(_ANSWER))
        with GangtiseClient(_config=seeded_config) as client:
            Tool(client).web_search(query="x", include_content=True, raw=True)
    assert _sent(route)["size"] == 5


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"size": 6, "include_content": True}, "caps size at 5"),
        ({"size": 21}, "between 1 and 20"),
        ({"size": 0}, "between 1 and 20"),
        ({"freshness": "year"}, "invalid freshness"),
        ({"min_tier": "T4"}, "invalid min_tier"),
        ({"site": [f"s{i}.com" for i in range(11)]}, "at most 10 distinct domains"),
        ({"max_content_chars": 999, "include_content": True}, "between 1000 and 20000"),
        ({"max_content_chars": 20001}, "between 1000 and 20000"),
    ],
)
def test_web_search_refuses_bad_arguments_before_the_credit(seeded_config, kwargs, match):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_PATH)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match=match):
                Tool(client).web_search(query="x", **kwargs)
    assert not route.called


def test_web_search_eleven_sites_with_a_duplicate_count_as_ten(seeded_config):
    sites = [f"s{i}.com" for i in range(10)] + ["s0.com"]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PATH).mock(return_value=_ok(_ANSWER))
        with GangtiseClient(_config=seeded_config) as client:
            Tool(client).web_search(query="x", site=sites, raw=True)
    assert len(_sent(route)["siteList"]) == 10


def test_web_search_refuses_a_payload_without_a_list(seeded_config):
    # expects="list": a null data is a broken answer, not "no results".
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_PATH).mock(return_value=_ok(None))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="returned no list payload"):
                Tool(client).web_search(query="x")


@pytest.mark.anyio
async def test_async_web_search_round_trip(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_PATH).mock(return_value=_ok(_ANSWER))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            tool = AsyncTool(client)
            df = await tool.web_search(query="减持新规", site="csrc.gov.cn", include_content=True)
            with pytest.raises(ValidationError, match="caps size at 5"):
                await tool.web_search(query="x", size=10, include_content=True)
    assert _sent(route) == {
        "query": "减持新规",
        "size": 5,
        "siteList": ["csrc.gov.cn"],
        "includeContent": True,
    }
    assert df.iloc[0]["site"] == "csrc.gov.cn"
