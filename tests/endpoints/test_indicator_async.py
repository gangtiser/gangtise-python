from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError
from gangtise_openapi.domains.indicator import AsyncIndicator

_SEARCH = "/application/open-indicator/EDE/search"
_CROSS = "/application/open-indicator/EDE/cross-section"
_TIME = "/application/open-indicator/EDE/time-series"


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def _ede_response(inner_data) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"code": "000000", "status": True, "data": inner_data},
        },
    )


@pytest.mark.anyio
async def test_async_search(tmp_path):
    rows = [{"indicatorCode": "qte_close", "indicatorName": "收盘价"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_SEARCH).mock(return_value=_ede_response(rows))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).search(keyword="收盘价", limit=20)
        body = json.loads(route.calls.last.request.read())
        assert body == {"keyword": "收盘价", "limit": 20}
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["indicatorCode"] == "qte_close"


@pytest.mark.anyio
async def test_async_cross_section(tmp_path):
    matrix = {
        "date": "2025-01-02",
        "indicatorCodeList": ["qte_close", "qte_open"],
        "indicatorNameList": ["收盘价", "开盘价"],
        "securityCodeList": ["600519.SH", "000001.SZ"],
        "securityNameList": ["贵州茅台", "平安银行"],
        "values": [[1700, 11], [1690, 10]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).cross_section(
                date="2025-01-02",
                indicator=["qte_close", "qte_open"],
                security=["600519.SH", "000001.SZ"],
                indicator_param={"qte_close": {"adjustmentType": "2"}},
            )
        body = json.loads(route.calls.last.request.read())
        assert body["indicatorCodeList"] == ["qte_close", "qte_open"]
        assert body["date"] == "2025-01-02"
        assert body["indicatorParamList"] == [
            {
                "indicatorCode": "qte_close",
                "parameters": [{"paramKey": "adjustmentType", "paramValue": "2"}],
            }
        ]
    assert isinstance(df, pd.DataFrame)
    assert list(df["security"]) == ["600519.SH", "000001.SZ"]
    assert df.iloc[0]["收盘价"] == 1700
    assert df.iloc[1]["开盘价"] == 10


@pytest.mark.anyio
async def test_async_time_series(tmp_path):
    matrix = {
        "dates": ["2025-01-02", "2025-01-03"],
        "securityCodeList": ["600519.SH"],
        "indicatorCodeList": ["qte_close", "qte_open"],
        "indicatorNameList": ["收盘价", "开盘价"],
        "values": [[1700, 1710], [1690, 1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_TIME).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).time_series(
                start_date="2025-01-02",
                end_date="2025-01-03",
                indicator=["qte_close", "qte_open"],
                security="600519.SH",
            )
        body = json.loads(route.calls.last.request.read())
        assert body["startDate"] == "2025-01-02"
        assert body["endDate"] == "2025-01-03"
    assert isinstance(df, pd.DataFrame)
    assert list(df["date"]) == ["2025-01-02", "2025-01-03"]
    assert df.iloc[0]["收盘价"] == 1700


@pytest.mark.anyio
async def test_async_time_series_single_indicator_multi_security(tmp_path):
    # Single-indicator x multi-security branch: columns are securities,
    # values is [security][date]. (Sibling branch covered by test_async_time_series.)
    matrix = {
        "dates": ["2025-01-02", "2025-01-03"],
        "securityCodeList": ["600519.SH", "000001.SZ"],
        "securityNameList": ["贵州茅台", "平安银行"],
        "indicatorCodeList": ["qte_close"],
        "indicatorNameList": ["收盘价"],
        "values": [[1700, 1710], [11, 12]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).time_series(
                start_date="2025-01-02",
                end_date="2025-01-03",
                indicator="qte_close",
                security=["600519.SH", "000001.SZ"],
            )
    assert list(df["date"]) == ["2025-01-02", "2025-01-03"]
    assert df.iloc[0]["贵州茅台"] == 1700
    assert df.iloc[1]["平安银行"] == 12


@pytest.mark.anyio
async def test_async_inner_envelope_failure_raises(tmp_path):
    inner_failure = {"code": "500", "status": False, "msg": "indicator boom", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": inner_failure},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as excinfo:
                await AsyncIndicator(client).cross_section(date="2025-01-02", security="600519.SH")
    assert excinfo.value.code == "500"
