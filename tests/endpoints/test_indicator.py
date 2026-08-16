from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ERROR_HINTS, ApiError, ValidationError
from gangtise_openapi.domains.indicator import Indicator

_SEARCH = "/application/open-indicator/EDE/search"
_CROSS = "/application/open-indicator/EDE/cross-section"
_TIME = "/application/open-indicator/EDE/time-series"
# The screener sits directly under open-indicator, NOT under the EDE/ prefix.
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
    # EDE endpoints have historically double-wrapped: the shared client strips the
    # outer envelope and leaves an inner {code, status, data} to peel.
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"code": "000000", "status": True, "data": inner_data},
        },
    )


def _ind(code: str, name: str, **extra) -> dict:
    """One `indicatorList` entry — the structured form that replaced the parallel
    indicatorCodeList / indicatorNameList arrays in the 2026-08-01 revision."""
    return {"code": code, "name": name, "dataType": "number", **extra}


# ─────────────────────────────── search ───────────────────────────────


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


def test_search_inner_999999_keeps_generic_hint(tmp_path):
    # search's inner-envelope 999999 keeps the generic hint: unlike the data-fetch
    # endpoints it takes only a keyword, so date/scope/param guidance would be
    # nonsense (TS v0.28.2).
    inner = {"code": "999999", "status": False, "msg": "系统错误", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SEARCH).mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": inner})
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as excinfo:
                Indicator(client).search(keyword="收盘价")
    assert excinfo.value.code == "999999"
    assert excinfo.value.hint == ERROR_HINTS["999999"]


# ──────────────────────────── cross-section ────────────────────────────


def test_cross_section(tmp_path):
    # 2026-08-01 contract: `universe` (not securityCodeList), a structured
    # `indicatorList`, and a TRANSPOSED values matrix — values[i] is security i's
    # row across the indicators.
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_open", "开盘价")],
        "securityCodeList": ["600519.SH", "000001.SZ"],
        "securityNameList": ["贵州茅台", "平安银行"],
        "values": [[1700, 1690], [11, 10]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).cross_section(
                date="2025-01-02",
                indicator=["qte_close", "qte_open"],
                security=["600519.SH", "000001.SZ"],
                scale="8",
                indicator_param={"qte_close": {"adjustType": "2"}},
            )
        body = json.loads(route.calls.last.request.read())
        assert body["indicatorCodeList"] == ["qte_close", "qte_open"]
        assert body["universe"] == ["600519.SH", "000001.SZ"]
        assert "securityCodeList" not in body  # renamed by the 2026-08-01 revision
        assert "date" not in body  # root-level date is gone; it rides per indicator
        assert body["scale"] == "8"
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
        assert "currency" not in body  # unset optionals stripped
    assert isinstance(df, pd.DataFrame)
    # one row per security, indicator names as columns, and NO row-level date
    assert "date" not in df.columns
    assert list(df["security"]) == ["600519.SH", "000001.SZ"]
    assert df.iloc[0]["收盘价"] == 1700
    assert df.iloc[0]["开盘价"] == 1690
    assert df.iloc[1]["收盘价"] == 11


def test_cross_section_caller_report_date_suppresses_trade_date(tmp_path):
    # Report-period indicators REJECT tradeDate since 2026-08-14 (100003 "不支持参数
    # tradeDate; 缺少必填参数 reportDate"), so a caller-supplied date parameter must
    # not be joined by an injected one.
    matrix = {
        "indicatorList": [_ind("is_tot_op_rev", "营业总收入")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[63789220000]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Indicator(client).cross_section(
                date="2025-01-02",
                indicator="is_tot_op_rev",
                security="600519.SH",
                indicator_param={"is_tot_op_rev": {"reportDate": "2024-12-31"}},
            )
        body = json.loads(route.calls.last.request.read())
    params = body["indicatorParamList"][0]["parameters"]
    assert params == [{"paramKey": "reportDate", "paramValue": "2024-12-31"}]


def test_cross_section_s_date_still_gets_a_trade_date(tmp_path):
    # `sDate` is the interval START while the required `tradeDate` is its END, so
    # it must NOT count as "already dated" — treating it as one silently moved the
    # interval end (茅台 sDate=2024-01-02: 2,265,873,849 without vs 65,687,435 with).
    matrix = {
        "indicatorList": [_ind("qte_vol_intvl", "区间成交量")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[65687435]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Indicator(client).cross_section(
                date="2024-01-31",
                indicator="qte_vol_intvl",
                security="600519.SH",
                indicator_param={"qte_vol_intvl": {"sDate": "2024-01-02"}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["indicatorParamList"][0]["parameters"] == [
        {"paramKey": "sDate", "paramValue": "2024-01-02"},
        {"paramKey": "tradeDate", "paramValue": "2024-01-31"},
    ]


def test_cross_section_key_by_code(tmp_path):
    # Batch code→value use-case: the request order is [cf_finc_exp, cf_finc_exp_qtr]
    # but the server answers in its own order, and the display names are
    # server-chosen suffixed variants. key_by="code" lets the caller read the column
    # back under the code it asked for (TS v0.28.2).
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).cross_section(
                date="2026-03-31",
                indicator=["cf_finc_exp", "cf_finc_exp_qtr"],
                security="600519.SH",
                key_by="code",
            )
    row = df.iloc[0]
    assert row["security"] == "600519.SH"
    assert row["cf_finc_exp"] == 100
    assert row["cf_finc_exp_qtr"] == 40


def test_cross_section_null_display_name_falls_back_to_code(tmp_path):
    # The server sends null display names for real (probed 2026-07-24). Stringifying
    # would put the column under the literal header "None".
    matrix = {
        "indicatorList": [{"code": "qte_open", "name": None}, _ind("qte_close", "日收盘价")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": [None],
        "values": [[1400.0, 1409.52]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).cross_section(
                date="2026-03-31", indicator=["qte_open", "qte_close"], security="600519.SH"
            )
    assert "None" not in df.columns
    assert df.iloc[0]["qte_open"] == 1400.0
    assert df.iloc[0]["日收盘价"] == 1409.52
    # A null security name degrades to the code — never the text "None".
    assert df.iloc[0]["name"] == "600519.SH"


def test_cross_section_omits_name_column_when_no_names_came_back(tmp_path):
    # An always-present `name: None` is invisible in JSON but a real empty column
    # in a DataFrame.
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价")],
        "securityCodeList": ["600519.SH"],
        "values": [[1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).cross_section(
                date="2026-03-31", indicator="qte_close", security="600519.SH"
            )
    assert list(df.columns) == ["security", "收盘价"]


def test_cross_section_dropped_indicator_marks_partial(tmp_path):
    # A coverage gap is padded with null these days, so a vanished column means the
    # server did not RESOLVE that code — invisible otherwise (key_by=code finds no
    # key at all rather than a null).
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="not_a_real_code"):
                df = Indicator(client).cross_section(
                    date="2026-03-31",
                    indicator=["qte_close", "not_a_real_code"],
                    security="600519.SH",
                )
    assert df.iloc[0]["收盘价"] == 1700


def test_cross_section_sector_id_is_not_reported_as_dropped(tmp_path):
    # A universe entry without a "." is a sector ID; the server expands it into
    # constituents, so its absence from securityCodeList is expected.
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价")],
        "securityCodeList": ["600519.SH", "000858.SZ"],
        "securityNameList": ["贵州茅台", "五粮液"],
        "values": [[1700], [130]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).cross_section(
                date="2026-03-31", indicator="qte_close", security="1234567890"
            )
    assert len(df) == 2


def test_cross_section_empty_matrix_notes_ambiguity_without_partial(tmp_path):
    # An all-empty matrix is no longer "no data": since 2026-08-07 a real coverage
    # gap keeps its row and column, so nothing in the request resolved. Calling
    # every requested code "omitted" would be false metadata.
    matrix = {
        "indicatorList": [],
        "securityCodeList": [],
        "securityNameList": [],
        "values": [],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="NOTHING in the request resolved"):
                df = Indicator(client).cross_section(
                    date="2026-03-31", indicator="qte_close", security="999999.SH"
                )
    assert df.empty


def test_cross_section_raw_returns_the_untouched_payload(tmp_path):
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价")],
        "securityCodeList": ["600519.SH"],
        "values": [[1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            out = Indicator(client).cross_section(
                date="2026-03-31", indicator="qte_close", security="600519.SH", raw=True
            )
    assert out == {"code": "000000", "status": True, "data": matrix}


# ───────────────────────────── time-series ─────────────────────────────


def test_time_series(tmp_path):
    matrix = {
        "dates": ["2025-01-02", "2025-01-03"],
        "securityCodeList": ["600519.SH"],
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_open", "开盘价")],
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
        assert body["universe"] == ["600519.SH"]
        assert "securityCodeList" not in body
        # The endpoint requires the key even with nothing to configure.
        assert body["indicatorParamList"] == []
    assert list(df["date"]) == ["2025-01-02", "2025-01-03"]
    assert df.iloc[0]["收盘价"] == 1700
    assert df.iloc[1]["开盘价"] == 1700


def test_time_series_single_indicator_multi_security(tmp_path):
    matrix = {
        "dates": ["2025-01-02", "2025-01-03"],
        "securityCodeList": ["600519.SH", "000001.SZ"],
        "securityNameList": ["贵州茅台", "平安银行"],
        "indicatorList": [_ind("qte_close", "收盘价")],
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


def test_time_series_key_by_code_single_security(tmp_path):
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_vol", "成交量")],
        "values": [[1323.0], [4966097]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).time_series(
                start_date="2026-05-18",
                end_date="2026-05-18",
                indicator=["qte_close", "qte_vol"],
                security="600519.SH",
                key_by="code",
            )
    row = df.iloc[0]
    assert row["date"] == "2026-05-18"
    assert row["qte_close"] == 1323.0
    assert row["qte_vol"] == 4966097


def test_time_series_key_by_code_multi_security(tmp_path):
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH", "09992.HK"],
        "securityNameList": ["贵州茅台", "泡泡玛特"],
        "indicatorList": [_ind("qte_close", "收盘价")],
        "values": [[1323.0], [150.7]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).time_series(
                start_date="2026-05-18",
                end_date="2026-05-18",
                indicator="qte_close",
                security=["600519.SH", "09992.HK"],
                key_by="code",
            )
    row = df.iloc[0]
    assert row["600519.SH"] == 1323.0
    assert row["09992.HK"] == 150.7


def test_time_series_two_securities_one_returned_still_labels_by_security(tmp_path):
    # The server drops securities with no data at all, so a two-security request
    # coming back with one must NOT flip to the indicator axis — a bare 收盘价
    # column loses whose series it is (probed 2026-08-02 on 600519.SH + 09992.HK).
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "indicatorList": [_ind("finc_pe_ttm", "PE(TTM)")],
        "values": [[23.4]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="09992.HK"):
                df = Indicator(client).time_series(
                    start_date="2026-05-18",
                    end_date="2026-05-18",
                    indicator="finc_pe_ttm",
                    security=["600519.SH", "09992.HK"],
                )
    assert "贵州茅台" in df.columns
    assert "PE(TTM)" not in df.columns


def test_time_series_single_sector_id_takes_the_security_axis(tmp_path):
    # v0.31.0 regression guard: a sector ID is expanded SERVER-side, so the request
    # count (1) says nothing about the axis. When the expansion yields exactly one
    # constituent the response is 1x1 and only the universe can break the tie —
    # this is the one legal use of a sector ID on the time-series endpoint.
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "indicatorList": [_ind("qte_close", "收盘价")],
        "values": [[1323.0]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).time_series(
                start_date="2026-05-18",
                end_date="2026-05-18",
                indicator="qte_close",
                security="1234567890",
            )
    assert "贵州茅台" in df.columns
    assert "收盘价" not in df.columns


def test_time_series_duplicate_security_is_not_two_securities(tmp_path):
    # The same code passed twice used to read as a two-security request, which
    # degraded the column from the indicator name to the security code.
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "indicatorList": [_ind("qte_close", "收盘价")],
        "values": [[1323.0]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).time_series(
                start_date="2026-05-18",
                end_date="2026-05-18",
                indicator="qte_close",
                security=["600519.SH", "600519.SH"],
            )
    assert "收盘价" in df.columns


def test_time_series_multi_by_multi_response_is_fatal(tmp_path):
    # The endpoint does not support it as a REQUEST (100003); as a RESPONSE it is
    # unattributable — whichever axis becomes the columns, the other identity is
    # silently discarded, and the request/response diff is empty so nothing else
    # would flag it.
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": ["600519.SH", "000858.SZ"],
        "securityNameList": ["贵州茅台", "五粮液"],
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_vol", "成交量")],
        "values": [[1], [2], [3], [4]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="does not support"):
                Indicator(client).time_series(
                    start_date="2026-05-18",
                    end_date="2026-05-18",
                    indicator=["qte_close", "qte_vol"],
                    security=["600519.SH", "000858.SZ"],
                )


def test_time_series_dates_without_an_identity_axis_is_fatal(tmp_path):
    # `securityCodeList: []` with a populated matrix leaves every row belonging to
    # no security at all, and the row/column counts still line up.
    matrix = {
        "dates": ["2026-05-18"],
        "securityCodeList": [],
        "indicatorList": [_ind("qte_close", "收盘价")],
        "values": [[1323.0]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_TIME).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="could not be attributed"):
                Indicator(client).time_series(
                    start_date="2026-05-18",
                    end_date="2026-05-18",
                    indicator="qte_close",
                    security="600519.SH",
                )


# ──────────────────────── matrix shape guards ────────────────────────


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (None, "no matrix object"),
        ([], "no matrix object"),
        ({"total": 0, "list": []}, "none of the matrix fields"),
        (
            {"securityCodeList": ["600519.SH"], "indicatorList": [_ind("q", "Q")]},
            "no `values` array",
        ),
        (
            {"securityCodeList": ["600519.SH"], "indicatorList": None, "values": [[1]]},
            "missing `indicatorList`",
        ),
        (
            {"securityCodeList": [None], "indicatorList": [_ind("q", "Q")], "values": [[1]]},
            "not a usable identifier",
        ),
        (
            {"securityCodeList": ["600519.SH"], "indicatorList": [{"name": "Q"}], "values": [[1]]},
            "no usable `code`",
        ),
        (
            {
                "securityCodeList": ["600519.SH", "000858.SZ"],
                "indicatorList": [_ind("q", "Q")],
                "values": [[1]],
            },
            "1 value rows for 2 securities",
        ),
        (
            {
                "securityCodeList": ["600519.SH"],
                "indicatorList": [_ind("q", "Q"), _ind("r", "R")],
                "values": [[1]],
            },
            "value row 0 has 1 cells for 2 indicators",
        ),
    ],
)
def test_cross_section_shape_guards(tmp_path, payload, match):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(payload))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match=match):
                Indicator(client).cross_section(
                    date="2026-03-31", indicator="q", security="600519.SH"
                )


def test_security_name_length_mismatch_drops_names_but_keeps_values(tmp_path):
    # Names are consumed POSITIONALLY: ["泡泡玛特"] against two codes would label
    # 茅台's row 泡泡玛特. But a name is a caption, not structure — drop the caption
    # and keep the (correct) numbers, unlike the fatal guards above.
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价")],
        "securityCodeList": ["600519.SH", "09992.HK"],
        "securityNameList": ["泡泡玛特"],
        "values": [[1700], [150]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="names are positional"):
                df = Indicator(client).cross_section(
                    date="2026-03-31",
                    indicator="qte_close",
                    security=["600519.SH", "09992.HK"],
                )
    assert "name" not in df.columns
    assert list(df["security"]) == ["600519.SH", "09992.HK"]
    assert list(df["收盘价"]) == [1700, 150]


def test_inner_envelope_failure_raises(tmp_path):
    inner_failure = {"code": "500", "status": False, "msg": "indicator boom", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": inner_failure}
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as excinfo:
                Indicator(client).cross_section(
                    date="2025-01-02", indicator="qte_close", security="600519.SH"
                )
    assert excinfo.value.code == "500"


def test_inner_envelope_999999_gets_ede_no_data_hint(tmp_path):
    from gangtise_openapi._errors import EDE_NO_DATA_HINT

    inner = {"code": "999999", "status": False, "msg": "系统错误", "data": None}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": inner})
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as excinfo:
                Indicator(client).cross_section(
                    date="2025-01-02", indicator="qte_close", security="600519.SH"
                )
    assert excinfo.value.code == "999999"
    assert excinfo.value.hint == EDE_NO_DATA_HINT


# ─────────────────────────────── screener ───────────────────────────────


def test_screener(tmp_path):
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
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).screener(
                date="2026-08-07",
                expression="F1 >= 500 && F2 <= 30",
                indicator={"F1": "qte_mkt_cptl", "F2": "finc_pe_ttm"},
                security="1234567890",
                indicator_param={"F1": {"scale": "8"}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["universe"] == ["1234567890"]
    assert body["expression"] == "F1 >= 500 && F2 <= 30"
    assert body["indicatorList"] == [
        {
            "field": "F1",
            "indicatorCode": "qte_mkt_cptl",
            "parameters": [
                {"paramKey": "scale", "paramValue": "8"},
                {"paramKey": "tradeDate", "paramValue": "2026-08-07"},
            ],
        },
        {
            "field": "F2",
            "indicatorCode": "finc_pe_ttm",
            "parameters": [{"paramKey": "tradeDate", "paramValue": "2026-08-07"}],
        },
    ]
    assert df.iloc[0]["security"] == "600519.SH"
    assert df.iloc[0]["总市值"] == 21000


def test_screener_same_code_on_two_variables_suffixes_both_columns(tmp_path):
    # A bare 收盘价 next to 收盘价 (F2) reads as "the" close price when it is really
    # just whichever variable the server happened to list first.
    matrix = {
        "indicatorList": [
            _ind("qte_close", "收盘价", field="F1"),
            _ind("qte_close", "收盘价", field="F2"),
        ],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[1350.6, 1361.7]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).screener(
                date="2026-08-07",
                expression="F1 > F2",
                indicator={"F1": "qte_close", "F2": "qte_close"},
                security="600519.SH",
                indicator_param={"F2": {"tradeDate": "2026-08-06"}},
            )
    assert "收盘价 (F1)" in df.columns
    assert "收盘价 (F2)" in df.columns
    assert "收盘价" not in df.columns


def test_screener_unknown_binding_is_fatal(tmp_path):
    # The `field` is the ONLY thing tying a column back to the filter it came from;
    # a swapped one renders as a perfectly ordinary table.
    matrix = {
        "indicatorList": [_ind("qte_mkt_cptl", "总市值", field="F9")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[21000]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="never requested"):
                Indicator(client).screener(
                    date="2026-08-07",
                    expression="F1 >= 500",
                    indicator={"F1": "qte_mkt_cptl"},
                    security="600519.SH",
                )


def test_screener_binding_code_mismatch_is_fatal(tmp_path):
    matrix = {
        "indicatorList": [_ind("finc_pe_ttm", "PE(TTM)", field="F1")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[23.4]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="the filter and the column disagree"):
                Indicator(client).screener(
                    date="2026-08-07",
                    expression="F1 >= 500",
                    indicator={"F1": "qte_mkt_cptl"},
                    security="600519.SH",
                )


def test_screener_missing_mandatory_column_is_fatal(tmp_path):
    # `F1 && F2` with F1 absent: the rows are presented as having passed a filter
    # that cannot be shown to have run at all.
    matrix = {
        "indicatorList": [_ind("finc_pe_ttm", "PE(TTM)", field="F2")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[23.4]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="cannot be evaluated"):
                Indicator(client).screener(
                    date="2026-08-07",
                    expression="F1 >= 500 && F2 <= 30",
                    indicator={"F1": "qte_mkt_cptl", "F2": "finc_pe_ttm"},
                    security="600519.SH",
                )


def test_screener_missing_disjunct_degrades_to_partial(tmp_path):
    # `F1 || F2` with F1 absent: a row can legitimately have matched through F2, so
    # the result stands — losing the column costs information, not correctness
    # (probed 2026-08-03 over 09992.HK, where finc_pe_ttm has no HK coverage).
    matrix = {
        "indicatorList": [_ind("finc_pb_mrq", "PB(MRQ)", field="F2")],
        "securityCodeList": ["09992.HK"],
        "securityNameList": ["泡泡玛特"],
        "values": [[14.9]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="produced no column"):
                df = Indicator(client).screener(
                    date="2026-08-07",
                    expression="F1 > 0 || F2 > 0",
                    indicator={"F1": "finc_pe_ttm", "F2": "finc_pb_mrq"},
                    security="09992.HK",
                )
    assert df.iloc[0]["security"] == "09992.HK"


def test_screener_empty_result_notes_the_ambiguity(tmp_path):
    matrix = {
        "indicatorList": [],
        "securityCodeList": [],
        "securityNameList": [],
        "values": [],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="nothing matched the expression"):
                df = Indicator(client).screener(
                    date="2026-08-07",
                    expression="F1 >= 500",
                    indicator={"F1": "qte_mkt_cptl"},
                    security="600519.SH",
                )
    assert df.empty


def test_screener_rejects_unbound_expression_variable(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="expression references 'F2'"):
            Indicator(client).screener(
                date="2026-08-07",
                expression="F1 >= 500 && F2 <= 30",
                indicator={"F1": "qte_mkt_cptl"},
                security="600519.SH",
            )


def test_screener_rejects_param_for_an_unbound_variable(tmp_path):
    # The server silently drops it, so the query would run with a filter the caller
    # believes is applied but is not.
    with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="indicator_param references 'F3'"):
            Indicator(client).screener(
                date="2026-08-07",
                expression="F1 >= 500",
                indicator={"F1": "qte_mkt_cptl"},
                security="600519.SH",
                indicator_param={"F3": {"scale": "8"}},
            )


def test_screener_rejects_a_malformed_variable_name(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="expected F followed by a positive integer"):
            Indicator(client).screener(
                date="2026-08-07",
                expression="X1 >= 500",
                indicator={"X1": "qte_mkt_cptl"},
                security="600519.SH",
            )


# ─────────────────────────── local validation ───────────────────────────


def test_key_by_invalid_raises_before_request(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
        with pytest.raises(ValidationError):
            Indicator(client).cross_section(
                date="2025-01-02", indicator="qte_close", security="600519.SH", key_by="codes"
            )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"indicator": [], "security": "600519.SH"}, "indicator is required"),
        ({"indicator": "qte_close", "security": []}, "security is required"),
        ({"indicator": [], "security": []}, "indicator and security are required"),
    ],
)
def test_cross_section_requires_both_axes(tmp_path, kwargs, match):
    # Every matrix endpoint needs at least one of each; omitting one costs a round
    # trip to be told 100001 in the API's own parameter names.
    with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match=match):
            Indicator(client).cross_section(date="2025-01-02", **kwargs)


def test_matrix_shape_error_keeps_the_envelope_trace_id(tmp_path):
    # A shape mismatch is exactly the failure worth reporting to support, and the
    # traceId is the only handle they can trace it by — but it lives on the
    # envelope the transport already discarded (TS v0.31.0).
    matrix = {
        "indicatorList": [_ind("qte_close", "收盘价"), _ind("qte_open", "开盘价")],
        "securityCodeList": ["600519.SH"],
        "values": [[1700]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_CROSS).mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "traceId": "830965044897325056",
                    "data": {"code": "000000", "status": True, "data": matrix},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as excinfo:
                Indicator(client).cross_section(
                    date="2026-03-31",
                    indicator=["qte_close", "qte_open"],
                    security="600519.SH",
                )
    assert excinfo.value.trace_id == "830965044897325056"
    assert "trace 830965044897325056" in str(excinfo.value)


def test_cross_section_empty_param_mapping_suppresses_the_date_injection(tmp_path):
    # A handful of indicators take NO date at all (an empty parameterList), and the
    # server rejects a stray tradeDate with 100003 — so injecting unconditionally
    # makes them unreachable here, which is where the CLI and gangtise-mcp stand.
    # Opt-in: only an explicitly empty mapping suppresses it.
    matrix = {
        "indicatorList": [_ind("scr_exchg_mkt", "上市市场")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [["上海证券交易所"]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Indicator(client).cross_section(
                date="2026-08-13",
                indicator="scr_exchg_mkt",
                security="600519.SH",
                indicator_param={"scr_exchg_mkt": {}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["indicatorParamList"] == [{"indicatorCode": "scr_exchg_mkt", "parameters": []}]
    assert df.iloc[0]["上市市场"] == "上海证券交易所"


def test_cross_section_fiscal_year_alone_does_not_suppress_the_injection(tmp_path):
    # 🔴 The regression guard for a design that was reverted. `fiscalYear` LOOKS
    # like a period selector, and treating it as one would fix the two indicators
    # that take only fiscalYear — but a live `indicator.search` sweep of 323
    # indicators (2026-08-15) found 5 that require fiscalYear AND tradeDate:
    # frcst_op_rev, frcst_op_rev_yoy, frcst_shnp, frcst_shnp_yoy, frcst_pe. On
    # those, suppressing the injection breaks a call that works today.
    matrix = {
        "indicatorList": [_ind("frcst_pe", "预测PE")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[23.4]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Indicator(client).cross_section(
                date="2026-08-13",
                indicator="frcst_pe",
                security="600519.SH",
                indicator_param={"frcst_pe": {"fiscalYear": "2026"}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["indicatorParamList"][0]["parameters"] == [
        {"paramKey": "fiscalYear", "paramValue": "2026"},
        {"paramKey": "tradeDate", "paramValue": "2026-08-13"},
    ]


def test_cross_section_none_marker_suppresses_only_the_marked_key(tmp_path):
    # The fiscalYear-only pair (div_cash_paid_ratio, div_cash_yr) needs the other
    # parameters to travel while tradeDate stays away. A `None` marks the key as
    # unwanted — and must never reach the wire as the string "None".
    matrix = {
        "indicatorList": [_ind("div_cash_yr", "年度现金分红总额")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[30000000000]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_CROSS).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Indicator(client).cross_section(
                date="2026-08-13",
                indicator="div_cash_yr",
                security="600519.SH",
                indicator_param={"div_cash_yr": {"fiscalYear": "2025", "tradeDate": None}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["indicatorParamList"][0]["parameters"] == [
        {"paramKey": "fiscalYear", "paramValue": "2025"}
    ]
    assert "None" not in json.dumps(body, ensure_ascii=False)


def test_screener_none_marker_suppresses_only_the_marked_key(tmp_path):
    matrix = {
        "indicatorList": [_ind("div_cash_yr", "年度现金分红总额", field="F1")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [[30000000000]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Indicator(client).screener(
                date="2026-08-13",
                expression="F1 > 0",
                indicator={"F1": "div_cash_yr"},
                security="600519.SH",
                indicator_param={"F1": {"fiscalYear": "2025", "tradeDate": None}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["indicatorList"][0]["parameters"] == [
        {"paramKey": "fiscalYear", "paramValue": "2025"}
    ]
    assert "None" not in json.dumps(body, ensure_ascii=False)


def test_screener_empty_param_mapping_suppresses_the_date_injection(tmp_path):
    matrix = {
        "indicatorList": [_ind("scr_exchg_sctr", "交易板块", field="F1")],
        "securityCodeList": ["600519.SH"],
        "securityNameList": ["贵州茅台"],
        "values": [["主板"]],
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_SCREENER).mock(return_value=_ede_response(matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Indicator(client).screener(
                date="2026-08-13",
                expression="F1 contains '主板'",
                indicator={"F1": "scr_exchg_sctr"},
                security="600519.SH",
                indicator_param={"F1": {}},
            )
        body = json.loads(route.calls.last.request.read())
    assert body["indicatorList"][0]["parameters"] == []
