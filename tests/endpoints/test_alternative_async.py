from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.alternative import AsyncAlternative


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
async def test_async_edb_data_transposes_matrix(tmp_path):
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
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncAlternative(client).edb_data(
                indicator_id="I001",
                start_date="2026-01-01",
                end_date="2026-01-03",
            )
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["date", "indicatorId", "value"]
    assert len(df) == 3
    assert df.iloc[1]["value"] == 102.5


@pytest.mark.anyio
async def test_async_concept_info_returns_profile_dict(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-alternative/concept/info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "conceptId": "121000130",
                        "conceptName": "机器人",
                        "definition": "机器人是人工替代与具身智能的核心载体",
                        "keyEvents": [{"date": "2026-12-01", "content": "量产"}],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            result = await AsyncAlternative(client).concept_info(concept_id="121000130")
    assert isinstance(result, dict)
    assert result["conceptName"] == "机器人"


@pytest.mark.anyio
async def test_async_concept_securities_flattens_groups(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-alternative/concept/securities").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "conceptId": "121000130",
                        "conceptName": "机器人",
                        "securityCount": 1,
                        "securityDetail": [
                            {
                                "groupName": "丝杠",
                                "securityList": [
                                    {
                                        "securityCode": "603009.SH",
                                        "securityName": "北特科技",
                                        "isKey": True,
                                        "inclusionReason": "拓展滚珠丝杠业务",
                                    }
                                ],
                            }
                        ],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncAlternative(client).concept_securities(concept_id="121000130")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "groupName",
        "securityCode",
        "securityName",
        "isKey",
        "inclusionReason",
    ]
    assert df.iloc[0]["groupName"] == "丝杠"
    assert df.iloc[0]["securityName"] == "北特科技"


@pytest.mark.anyio
async def test_async_concept_securities_empty_returns_empty_dataframe(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-alternative/concept/securities").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "conceptId": "121000999",
                        "securityCount": 0,
                        "securityDetail": None,
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncAlternative(client).concept_securities(concept_id="121000999")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
    assert list(df.columns) == [
        "groupName",
        "securityCode",
        "securityName",
        "isKey",
        "inclusionReason",
    ]
