from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.reference import AsyncReference


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


@pytest.mark.anyio
async def test_async_securities_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-reference/securities/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {"code": "000001.SZ", "name": "平安银行"},
                        ]
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).securities_search(keyword="平安")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["code"] == "000001.SZ"


@pytest.mark.anyio
async def test_async_constant_category(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-reference/constants/category").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [
                            {
                                "category": "domesticCity",
                                "categoryName": "国内城市",
                                "structureType": "flat",
                                "maxLevel": 1,
                                "usageScopes": [],
                            }
                        ],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).constant_category()
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["category"] == "domesticCity"


@pytest.mark.anyio
async def test_async_constant_list_body_and_constants_unwrap(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-reference/constants/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "category": "swIndustry",
                        "structureType": "flat",
                        "maxLevel": 1,
                        "constantCount": 1,
                        "constants": [{"constantId": "801780", "constantName": "银行", "level": 1}],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).constant_list(category="swIndustry")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"category":"swIndustry"' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["constantId"] == "801780"


@pytest.mark.anyio
async def test_async_concept_search_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-reference/concepts/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "returnedCount": 1,
                        "list": [
                            {"conceptId": "121000130", "conceptName": "机器人", "matchScore": 0.99}
                        ],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).concept_search(keyword="jqr")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"keyword":"jqr"' in body
        assert b'"top":10' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["conceptName"] == "机器人"


@pytest.mark.anyio
async def test_async_sector_search_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-reference/sectors/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "returnedCount": 1,
                        "list": [
                            {
                                "sectorId": "2000000014",
                                "sectorName": "申万一级行业指数",
                                "hierarchy": "指数数据板块-行业指数-申万指数-申万一级行业指数",
                                "matchScore": 1.0,
                            }
                        ],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).sector_search(keyword="申万一级行业指数", top=3)
        body = json.loads(route.calls.last.request.read())
        assert body == {"keyword": "申万一级行业指数", "top": 3}
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["sectorId"] == "2000000014"


@pytest.mark.anyio
async def test_async_sector_constituents_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-reference/sectors/constituents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"gtsCode": "821047.SWI", "gtsName": "申万银行"}],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).sector_constituents(sector_id="2000000014")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"sectorId":"2000000014"' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["gtsCode"] == "821047.SWI"


@pytest.mark.anyio
async def test_async_chiefs_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-reference/chiefs/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": [{"chiefId": "c1", "chiefName": "张三"}],
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).chiefs_search(keyword="张三", top=5)
        body = json.loads(route.calls.last.request.read())
        assert body == {"keyword": "张三", "top": 5}
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["chiefId"] == "c1"
