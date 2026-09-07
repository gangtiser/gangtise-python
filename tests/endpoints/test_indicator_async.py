from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ERROR_HINTS, ApiError, ValidationError
from gangtise_openapi.domains.indicator import AsyncIndicator

_SEARCH = "/application/open-indicator/EDE/search"
_CROSS = "/application/open-indicator/EDE/cross-section"
_TIME = "/application/open-indicator/EDE/time-series"
_SCREENER = "/application/open-indicator/screener"


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


def _ind(code: str, name: str, **extra) -> dict:
    return {"code": code, "name": name, "dataType": "number", **extra}


@pytest.mark.anyio
async def test_async_search(tmp_path):
    rows = [{"indicatorCode": "qte_close"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_SEARCH).mock(return_value=_ede_response(rows))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).search(keyword="收盘价")
        body = json.loads(route.calls.last.request.read())
        assert body == {"keyword": "收盘价", "limit": 50}
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["indicatorCode"] == "qte_close"


@pytest.mark.anyio
async def test_async_search_inner_999999_keeps_generic_hint(tmp_path):
    inner = {"code": "999999", "status": False, "msg": "系统错误", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SEARCH).mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": inner})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as excinfo:
                await AsyncIndicator(client).search(keyword="收盘价")
    assert excinfo.value.hint == ERROR_HINTS["999999"]


@pytest.mark.anyio
async def test_async_cross_section(tmp_path):
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_open", "开盘价")],
        "securityCodeList": ["600519.SH", "000001.SZ"],
        "securityNameList": ["贵州茅台", "平安银行"],
        "values": [[1700, 1690], [11, 10]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).cross_section(
                date="2025-01-02",
                indicator=["qte_close", "qte_open"],
                security=["600519.SH", "000001.SZ"],
                indicator_param={"qte_close": {"adjustType": "2"}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["universe"] == ["600519.SH", "000001.SZ"]
    assert "securityCodeList" not in body
    assert "date" not in body
    assert body["indicatorParamList"] == [
        {
            "indicatorCode": "qte_close",
            "parameters": [
                {"paramKey": "adjustType", "paramValue": "2"},
                {"paramKey": "tradeDate", "paramValue": "2025-01-02"},
            ],
        },
        {
            "indicatorCode": "qte_open",
            "parameters": [{"paramKey": "tradeDate", "paramValue": "2025-01-02"}],
        },
    ]
    assert "date" not in df.columns
    assert df.iloc[0]["收盘价"] == 1700
    assert df.iloc[1]["收盘价"] == 11


@pytest.mark.anyio
async def test_async_cross_section_key_by_code(tmp_path):
    matrix = {
        "indicatorList": [
            _ind("cf_finc_exp_qtr", "财务费用(单季度)"),
            _ind("cf_finc_exp", "财务费用(现金流量表)"),
        ],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[40, 100]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).cross_section(
                date="2026-03-31",
                indicator=["cf_finc_exp", "cf_finc_exp_qtr"],
                security="600519.SH",
                key_by="code",
            )
    assert df.iloc[0]["cf_finc_exp"] == 100
    assert df.iloc[0]["cf_finc_exp_qtr"] == 40


@pytest.mark.anyio
async def test_async_cross_section_dropped_indicator_marks_partial(tmp_path):
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.warns(UserWarning, match="not_a_real_code"):
                df = await AsyncIndicator(client).cross_section(
                    date="2026-03-31",
                    indicator=["qte_close", "not_a_real_code"],
                    security="600519.SH",
                )
    assert df.iloc[0]["收盘价"] == 1700


@pytest.mark.anyio
async def test_async_time_series(tmp_path):
    matrix = {
        "dates": ["2025-01-02", "2025-01-03"],
        "securityCodeList": ["600519.SH"],
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_open", "开盘价")],
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
    assert body["universe"] == ["600519.SH"]
    assert body["indicatorParamList"] == []
    assert list(df["date"]) == ["2025-01-02", "2025-01-03"]
    assert df.iloc[0]["收盘价"] == 1700


@pytest.mark.anyio
async def test_async_time_series_single_indicator_multi_security(tmp_path):
    matrix = {
        "dates": ["2025-01-02"],
        "securityCodeList": ["600519.SH", "000001.SZ"],
        "securityNameList": ["贵州茅台", "平安银行"],
        "indicatorList": [_ind("qte_close", "收盘价")],
        "values": [[1700], [11]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).time_series(
                start_date="2025-01-02",
                end_date="2025-01-02",
                indicator="qte_close",
                security=["600519.SH", "000001.SZ"],
            )
    assert df.iloc[0]["贵州茅台"] == 1700
    assert df.iloc[0]["平安银行"] == 11


@pytest.mark.anyio
async def test_async_time_series_key_by_code_single_security(tmp_path):
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_vol", "成交量")],
        "values": [[1323.0], [4966097]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).time_series(
                start_date="2026-05-18",
                end_date="2026-05-18",
                indicator=["qte_close", "qte_vol"],
                security="600519.SH",
                key_by="code",
            )
    assert df.iloc[0]["qte_close"] == 1323.0
    assert df.iloc[0]["qte_vol"] == 4966097


@pytest.mark.anyio
async def test_async_time_series_key_by_code_multi_security(tmp_path):
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH", "09992.HK"],
        "securityNameList": ["贵州茅台", "泡泡玛特"],
        "indicatorList": [_ind("qte_close", "收盘价")],
        "values": [[1323.0], [150.7]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).time_series(
                start_date="2026-05-18",
                end_date="2026-05-18",
                indicator="qte_close",
                security=["600519.SH", "09992.HK"],
                key_by="code",
            )
    assert df.iloc[0]["600519.SH"] == 1323.0
    assert df.iloc[0]["09992.HK"] == 150.7


@pytest.mark.anyio
async def test_async_time_series_single_sector_id_takes_the_security_axis(tmp_path):
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "indicatorList": [_ind("qte_close", "收盘价")],
        "values": [[1323.0]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).time_series(
                start_date="2026-05-18",
                end_date="2026-05-18",
                indicator="qte_close",
                security="1234567890",
            )
    assert "贵州茅台" in df.columns
    assert "收盘价" not in df.columns


@pytest.mark.anyio
async def test_async_time_series_multi_by_multi_response_is_fatal(tmp_path):
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH", "000858.SZ"],
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_vol", "成交量")],
        "values": [[1], [2], [3], [4]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError, match="does not support"):
                await AsyncIndicator(client).time_series(
                    start_date="2026-05-18",
                    end_date="2026-05-18",
                    indicator=["qte_close", "qte_vol"],
                    security=["600519.SH", "000858.SZ"],
                )


@pytest.mark.anyio
async def test_async_cross_section_shape_mismatch_is_fatal(tmp_path):
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_open", "开盘价")],
        "securityCodeList": ["600519.SH"],
        "values": [[1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError, match="cells for 2 indicators"):
                await AsyncIndicator(client).cross_section(
                    date="2026-03-31",
                    indicator=["qte_close", "qte_open"],
                    security="600519.SH",
                )


@pytest.mark.anyio
async def test_async_inner_envelope_failure_raises(tmp_path):
    inner_failure = {"code": "500", "status": False, "msg": "indicator boom", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": inner_failure}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as excinfo:
                await AsyncIndicator(client).cross_section(
                    date="2025-01-02", indicator="qte_close", security="600519.SH"
                )
    assert excinfo.value.code == "500"


@pytest.mark.anyio
async def test_async_inner_envelope_999999_gets_ede_no_data_hint(tmp_path):
    from gangtise_openapi._errors import EDE_NO_DATA_HINT

    inner = {"code": "999999", "status": False, "msg": "系统错误", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": inner})
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as excinfo:
                await AsyncIndicator(client).cross_section(
                    date="2025-01-02", indicator="qte_close", security="600519.SH"
                )
    assert excinfo.value.hint == EDE_NO_DATA_HINT


@pytest.mark.anyio
async def test_async_screener(tmp_path):
    matrix = {
        "indicatorList": [
            _ind("qte_mkt_cptl", "总市值", field="F1"),
            _ind("finc_pe_ttm", "PE(TTM)", field="F2"),
        ],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[21000, 23.4]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncIndicator(client).screener(
                date="2026-08-07",
                expression="F1 >= 500 && F2 <= 30",
                indicator={"F1": "qte_mkt_cptl", "F2": "finc_pe_ttm"},
                security="1234567890",
            )
        body = json.loads(route.calls.last.request.read())
    assert body["universe"] == ["1234567890"]
    assert [b["field"] for b in body["indicatorList"]] == ["F1", "F2"]
    assert all(
        {"paramKey": "tradeDate", "paramValue": "2026-08-07"} in b["parameters"]
        for b in body["indicatorList"]
    )
    assert df.iloc[0]["总市值"] == 21000


@pytest.mark.anyio
async def test_async_screener_unknown_binding_is_fatal(tmp_path):
    matrix = {
        "indicatorList": [_ind("qte_mkt_cptl", "总市值", field="F9")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[21000]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError, match="never requested"):
                await AsyncIndicator(client).screener(
                    date="2026-08-07",
                    expression="F1 >= 500",
                    indicator={"F1": "qte_mkt_cptl"},
                    security="600519.SH",
                )


@pytest.mark.anyio
async def test_async_key_by_invalid_raises_before_request(tmp_path):
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        with pytest.raises(ValidationError):
            await AsyncIndicator(client).cross_section(
                date="2025-01-02", indicator="qte_close", security="600519.SH", key_by="codes"
            )


@pytest.mark.anyio
async def test_async_cross_section_requires_both_axes(tmp_path):
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        with pytest.raises(ValidationError, match="indicator is required"):
            await AsyncIndicator(client).cross_section(
                date="2025-01-02", indicator=[], security="600519.SH"
            )


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["cross_section", "time_series"])
async def test_async_indicator_param_referencing_an_unbound_code_is_refused(tmp_path, method):
    kwargs = (
        {"start_date": "2026-01-01", "end_date": "2026-01-31"}
        if method == "time_series"
        else {"date": "2026-01-05"}
    )
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        with pytest.raises(ValidationError, match="is not in indicator="):
            await getattr(AsyncIndicator(client), method)(
                indicator="is_op_rev",
                security="600519.SH",
                indicator_param={"is_op_rve": {"reportDate": "2025-06-30"}},
                **kwargs,
            )
