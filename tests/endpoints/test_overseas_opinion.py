"""Overseas opinions: the list, the detail and the account-ID search (TS v0.52.0), and the
``expects="object"`` shape check the same release added."""

from __future__ import annotations

import json
import warnings

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.insight import AsyncInsight, Insight
from gangtise_openapi.domains.reference import AsyncReference, Reference
from gangtise_openapi.domains.vault import Vault

_LIST = "/application/open-insight/overseasOpinion/getList"
_DETAIL = "/application/open-insight/overseasOpinion/getDetail"
_ACCOUNTS = "/application/open-reference/overseasAccount/search"


def _ok(data) -> httpx.Response:
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


def _sent(route) -> dict:
    return json.loads(route.calls.last.request.content)


def _detail_route(router, answer=None) -> list[list[str]]:
    calls: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ids = json.loads(request.content)["overseasOpinionIdList"]
        calls.append(ids)
        if answer is not None:
            return answer(ids)
        return _ok([{"overseasOpinionId": i, "content": f"body {i}"} for i in ids])

    router.post(_DETAIL).mock(side_effect=handler)
    return calls


def test_list_sends_its_filters_and_returns_a_frame(seeded_config):
    row = {"overseasOpinionId": "o1", "accountName": "Bloomberg", "brief": "b"}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_LIST).mock(return_value=_ok({"total": 1, "list": [row]}))
        with GangtiseClient(_config=seeded_config) as client:
            df = Insight(client).overseas_opinion_list(
                size=5,
                start_time="2026-11-01",
                keyword="AI",
                rank_type=2,
                account="34713362",
                security=["NVDA.O"],
                category=["opinion", "dataAnalysis"],
                industry=107700008,
                region="us",
                original_flag=0,
            )
    assert _sent(route) == {
        "from": 0,
        "size": 5,
        "startTime": "2026-11-01",
        "keyword": "AI",
        "rankType": 2,
        "accountIdList": ["34713362"],
        "securityList": ["NVDA.O"],
        "categoryList": ["opinion", "dataAnalysis"],
        "industryList": [107700008],
        "regionList": ["us"],
        "originalFlag": 0,
    }
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["overseasOpinionId"] == "o1"


def test_list_serves_rows_only_inside_the_offset_window(seeded_config):
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="10000"):
            Insight(client).overseas_opinion_list(from_=10000, size=5)


def test_list_refuses_an_explicit_empty_account_list_naming_it(seeded_config):
    with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="account"):
            Insight(client).overseas_opinion_list(account=[], size=5)


def test_detail_batches_20_ids_under_its_own_field_and_names_the_missing(seeded_config):
    ids = [f"O{i + 1}" for i in range(25)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        calls = _detail_route(router, answer=lambda got: _ok([{"overseasOpinionId": got[0]}]))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="no body returned for 23 ID"):
                result = Insight(client).overseas_opinion_detail(
                    overseas_opinion_id=[*ids, "O1"], raw=True
                )
    assert [len(c) for c in calls] == [20, 5]
    assert [r["overseasOpinionId"] for r in result["list"]] == ["O1", "O21"]
    assert result["partial"] is True
    assert len(result["missingIds"]) == 23


def test_detail_keeps_earlier_bodies_when_a_later_batch_is_out_of_the_accounts_range(
    seeded_config,
):
    def answer(got: list[str]) -> httpx.Response:
        if got[0] == "O21":
            return httpx.Response(200, json={"code": "110003", "msg": "超出数据权限范围"})
        return _ok([{"overseasOpinionId": i} for i in got])

    ids = [f"O{i + 1}" for i in range(25)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router, answer=answer)
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="5 ID"):
                result = Insight(client).overseas_opinion_detail(overseas_opinion_id=ids, raw=True)
    assert result["total"] == 20
    assert result["unfetchedIds"] == ids[20:]
    assert result["unfetchedError"]["code"] == "110003"


def test_detail_default_is_a_frame_of_the_bodies(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        _detail_route(router)
        with GangtiseClient(_config=seeded_config) as client:
            df = Insight(client).overseas_opinion_detail(overseas_opinion_id="O1")
    assert list(df["content"]) == ["body O1"]


@pytest.mark.anyio
async def test_async_list_and_detail(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_LIST).mock(
            return_value=_ok({"total": 1, "list": [{"overseasOpinionId": "o1"}]})
        )
        calls = _detail_route(router)
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            insight = AsyncInsight(client)
            listed = await insight.overseas_opinion_list(region="us", size=1, raw=True)
            bodies = await insight.overseas_opinion_detail(
                overseas_opinion_id=[r["overseasOpinionId"] for r in listed["list"]], raw=True
            )
    assert _sent(route)["regionList"] == ["us"]
    assert calls == [["o1"]]
    assert bodies["list"] == [{"overseasOpinionId": "o1", "content": "body o1"}]


def test_account_search_pages_by_from_and_size(seeded_config):
    row = {"accountId": "34713362", "accountName": "Bloomberg", "matchScore": 1}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_ACCOUNTS).mock(return_value=_ok({"total": 1, "list": [row]}))
        with GangtiseClient(_config=seeded_config) as client:
            df = Reference(client).overseas_account_search(keyword="bloomberg", size=5)
    assert _sent(route) == {"accountName": "bloomberg", "from": 0, "size": 5}
    assert df.iloc[0]["accountId"] == "34713362"


@pytest.mark.anyio
async def test_async_account_search_refuses_a_null_answer(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_ACCOUNTS).mock(return_value=_ok(None))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ApiError, match="returned no list payload"):
                await AsyncReference(client).overseas_account_search(keyword="elo", size=5)


# ---------------------------------------------------------------- expects="object"


@pytest.mark.parametrize("data", [None, [{"constantId": "1"}]])
def test_constant_list_refuses_an_answer_that_is_not_an_object(seeded_config, data):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-reference/constants/getList").mock(return_value=_ok(data))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="returned no object payload") as excinfo:
                Reference(client).constant_list(category="gicsIndustry")
    assert excinfo.value.structural


def test_drive_folder_list_passes_an_object_through(seeded_config):
    data = {"folderList": [], "fileList": []}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/drive/getFolderList").mock(return_value=_ok(data))
        with GangtiseClient(_config=seeded_config) as client, warnings.catch_warnings():
            warnings.simplefilter("error")
            assert Vault(client).drive_folder_list() == data
