from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError
from gangtise_openapi.domains.indicator import Indicator

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
    # EDE endpoints double-wrap: the shared client strips the outer envelope and
    # leaves an inner {code, status, data} that _unwrap_indicator_data peels.
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"code": "000000", "status": True, "data": inner_data},
        },
    )


def test_search(tmp_path):
    rows = [{"indicatorCode": "qte_close", "indicatorName": "收盘价"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_SEARCH).mock(return_value=_ede_response(rows))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).search(keyword="收盘价", limit=20)
        body = json.loads(route.calls.last.request.read())
        assert body == {"keyword": "收盘价", "limit": 20}
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["indicatorCode"] == "qte_close"


def test_search_raw_returns_inner_envelope(tmp_path):
    rows = [{"indicatorCode": "qte_close"}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SEARCH).mock(return_value=_ede_response(rows))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            out = Indicator(client).search(keyword="x", raw=True)
    # raw returns the (still-wrapped) inner envelope the client surfaced
    assert out == {"code": "000000", "status": True, "data": rows}


def test_cross_section(tmp_path):
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).cross_section(
                date="2025-01-02",
                indicator=["qte_close", "qte_open"],
                security=["600519.SH", "000001.SZ"],
                scale="8",
                indicator_param={"qte_close": {"adjustmentType": "2"}},
            )
        body = json.loads(route.calls.last.request.read())
        assert body["indicatorCodeList"] == ["qte_close", "qte_open"]
        assert body["securityCodeList"] == ["600519.SH", "000001.SZ"]
        assert body["date"] == "2025-01-02"
        assert body["scale"] == "8"
        assert body["indicatorParamList"] == [
            {
                "indicatorCode": "qte_close",
                "parameters": [{"paramKey": "adjustmentType", "paramValue": "2"}],
            }
        ]
        assert "currency" not in body  # unset optionals stripped
    assert isinstance(df, pd.DataFrame)
    # one row per security, indicator names as columns
    assert list(df["security"]) == ["600519.SH", "000001.SZ"]
    assert df.iloc[0]["收盘价"] == 1700
    assert df.iloc[0]["开盘价"] == 1690
    assert df.iloc[1]["收盘价"] == 11


def test_time_series(tmp_path):
    matrix = {
        "dates": ["2025-01-02", "2025-01-03"],
        "securityCodeList": ["600519.SH"],
        "indicatorCodeList": ["qte_close", "qte_open"],
        "indicatorNameList": ["收盘价", "开盘价"],
        "values": [[1700, 1710], [1690, 1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).time_series(
                start_date="2025-01-02",
                end_date="2025-01-03",
                indicator=["qte_close", "qte_open"],
                security="600519.SH",
                calendar_type="TD",
            )
        body = json.loads(route.calls.last.request.read())
        assert body["startDate"] == "2025-01-02"
        assert body["endDate"] == "2025-01-03"
        assert body["calendarType"] == "TD"
        assert body["securityCodeList"] == ["600519.SH"]
    assert isinstance(df, pd.DataFrame)
    # one row per date, indicator names as columns (single-security case)
    assert list(df["date"]) == ["2025-01-02", "2025-01-03"]
    assert df.iloc[0]["收盘价"] == 1700
    assert df.iloc[1]["开盘价"] == 1700


def test_time_series_single_indicator_multi_security(tmp_path):
    # The other time-series branch: one indicator, many securities -> columns are
    # the securities and `values` is [security][date] (values[i] = security i's
    # series over the dates). Locks in the TS-faithful orientation, which the
    # docstring/README advertise but the single-security test above doesn't cover.
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).time_series(
                start_date="2025-01-02",
                end_date="2025-01-03",
                indicator="qte_close",
                security=["600519.SH", "000001.SZ"],
            )
    assert list(df["date"]) == ["2025-01-02", "2025-01-03"]
    assert df.iloc[0]["贵州茅台"] == 1700
    assert df.iloc[0]["平安银行"] == 11
    assert df.iloc[1]["贵州茅台"] == 1710
    assert df.iloc[1]["平安银行"] == 12


def test_inner_envelope_failure_raises(tmp_path):
    # Outer envelope OK, but the inner EDE envelope carries a failure code that
    # must surface as ApiError instead of rendering its null payload as success.
    inner_failure = {"code": "500", "status": False, "msg": "indicator boom", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": inner_failure},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as excinfo:
                Indicator(client).cross_section(date="2025-01-02", security="600519.SH")
    assert excinfo.value.code == "500"
