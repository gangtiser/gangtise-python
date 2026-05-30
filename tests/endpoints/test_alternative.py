import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.alternative import Alternative


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_edb_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-alternative/EDB/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {"indicatorId": "I001", "indicatorName": "空调销量"},
                        ]
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Alternative(client).edb_search(keyword="空调")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"keyword":' in sent
        assert b'"limit":100' in sent
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["indicatorId"] == "I001"


def test_edb_data_transposes_matrix(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-alternative/EDB/getData").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "fieldList": ["date", "indicatorId", "value"],
                        "dataList": [
                            ["2026-01-01", "I001", 100.0],
                            ["2026-01-02", "I001", 102.5],
                            ["2026-01-03", "I001", 99.8],
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Alternative(client).edb_data(
                indicator_id="I001",
                start_date="2026-01-01",
                end_date="2026-01-03",
            )
    # Transposed: each row is a dict with the fieldList keys
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["date", "indicatorId", "value"]
    assert len(df) == 3
    assert df.iloc[1]["value"] == 102.5


_CONCEPT_SECURITIES_DATA = {
    "conceptId": "121000130",
    "conceptName": "机器人",
    "securityCount": 3,
    "securityDetail": [
        {
            "groupName": "1X机器人",
            "securityList": [
                {
                    "securityCode": "002779.SZ",
                    "securityName": "中坚科技",
                    "isKey": True,
                    "inclusionReason": "参股挪威1X机器人公司",
                },
                {
                    "securityCode": "300428.SZ",
                    "securityName": "立中集团",
                    "isKey": False,
                    "inclusionReason": "送样北欧机器人企业",
                },
            ],
        },
        {
            "groupName": "丝杠",
            "securityList": [
                {
                    "securityCode": "603009.SH",
                    "securityName": "北特科技",
                    "isKey": True,
                    "inclusionReason": "拓展滚珠丝杠业务",
                },
            ],
        },
    ],
}


def test_concept_info_returns_profile_dict(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-alternative/concept/info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "conceptId": "121000130",
                        "conceptName": "机器人",
                        "definition": "机器人是人工替代与具身智能的核心载体",
                        "investmentLogic": "需求刚性、技术临界点、产业链壁垒",
                        "industrySpace": "2030 年全球约 1200 亿美元",
                        "competitiveLandscape": "行业0-1阶段中美主导",
                        "keyEvents": [
                            {"date": "2026-12-01", "content": "小鹏预计26年Q4量产高阶人形机器人"},
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = Alternative(client).concept_info(concept_id="121000130")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"conceptId":"121000130"' in sent
    # A concept profile is a single cross-section object — returned as a dict, not a DataFrame.
    assert isinstance(result, dict)
    assert result["conceptName"] == "机器人"
    assert result["keyEvents"][0]["date"] == "2026-12-01"


def test_concept_securities_flattens_groups(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-alternative/concept/securities").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": _CONCEPT_SECURITIES_DATA},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Alternative(client).concept_securities(concept_id="121000130")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"conceptId":"121000130"' in sent
    assert isinstance(df, pd.DataFrame)
    # Grouped constituents are flattened one-row-per-security with the group name injected.
    assert list(df.columns) == [
        "groupName",
        "securityCode",
        "securityName",
        "isKey",
        "inclusionReason",
    ]
    assert len(df) == 3
    assert df.iloc[0]["groupName"] == "1X机器人"
    assert df.iloc[0]["securityCode"] == "002779.SZ"
    assert bool(df.iloc[0]["isKey"]) is True
    assert df.iloc[2]["groupName"] == "丝杠"


def test_concept_securities_raw_keeps_group_structure(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-alternative/concept/securities").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": _CONCEPT_SECURITIES_DATA},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            result = Alternative(client).concept_securities(concept_id="121000130", raw=True)
    assert isinstance(result, dict)
    assert result["securityCount"] == 3
    assert result["securityDetail"][0]["groupName"] == "1X机器人"


def test_concept_securities_empty_returns_empty_dataframe(tmp_path):
    # A concept with no constituents returns a successful payload with
    # securityDetail null (or absent). The default path must still yield a
    # DataFrame with the expected columns — not the raw dict.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-alternative/concept/securities").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "conceptId": "121000999",
                        "conceptName": "空题材",
                        "securityCount": 0,
                        "securityDetail": None,
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Alternative(client).concept_securities(concept_id="121000999")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert list(df.columns) == [
        "groupName",
        "securityCode",
        "securityName",
        "isKey",
        "inclusionReason",
    ]
