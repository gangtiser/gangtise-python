import json

import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.reference import Reference


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_securities_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-reference/securities/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": [
                        {"code": "000001.SH", "name": "上证指数", "market": "SH"},
                    ],
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).securities_search(keyword="上证")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["code"] == "000001.SH"


def test_constant_category(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.get("/application/open-reference/constants/category").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [
                            {
                                "category": "citicIndustry",
                                "categoryName": "中信一级行业",
                                "structureType": "flat",
                                "maxLevel": 1,
                                "usageScopes": [],
                            }
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).constant_category()
        assert route.calls.last.request.method == "GET"
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["category"] == "citicIndustry"


def test_constant_list_body_and_constants_unwrap(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-reference/constants/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "category": "citicIndustry",
                        "structureType": "flat",
                        "maxLevel": 1,
                        "constantCount": 2,
                        "constants": [
                            {"constantId": "100800121", "constantName": "银行", "level": 1},
                            {"constantId": "100800122", "constantName": "房地产", "level": 1},
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).constant_list(category="citicIndustry")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"category":"citicIndustry"' in body
    assert isinstance(df, pd.DataFrame)
    assert list(df["constantId"]) == ["100800121", "100800122"]


def test_concept_search_body(tmp_path):
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).concept_search(keyword="机器人", top=3)
        body = json.loads(route.calls.last.request.read())
        assert body == {"keyword": "机器人", "top": 3}
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["conceptId"] == "121000130"


def test_sector_search_keyword_optional(tmp_path):
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
                                "sectorId": "1000001005",
                                "sectorName": "半导体设备",
                                "hierarchy": "中国内地股票-概念类-科技-半导体设备",
                                "matchScore": 0.9,
                            }
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).sector_search()
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"keyword"' not in body
        assert b'"top":10' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["sectorId"] == "1000001005"


def test_sector_constituents_body(tmp_path):
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).sector_constituents(sector_id="2000000014")
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"sectorId":"2000000014"' in body
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["gtsCode"] == "821047.SWI"


def test_constant_list_raw_returns_envelope_data(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-reference/constants/getList").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"category": "regionCategory", "constants": [{"constantId": "1"}]},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            out = Reference(client).constant_list(category="regionCategory", raw=True)
    assert out == {"category": "regionCategory", "constants": [{"constantId": "1"}]}
