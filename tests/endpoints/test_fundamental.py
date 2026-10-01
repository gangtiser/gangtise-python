import datetime as dt
import json
import types

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ValidationError
from gangtise_openapi.domains import fundamental as fundamental_module
from gangtise_openapi.domains.fundamental import Fundamental

_BEIJING = dt.timezone(dt.timedelta(hours=8))


def _beijing_today() -> dt.date:
    """The wrapper's default end date: Beijing's day, whatever the machine's zone."""
    return dt.datetime.now(_BEIJING).date()


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def _row_response(row: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"list": [row]},
        },
    )


def test_income_statement(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(
            "/application/open-fundamental/financial-report/income-statement/accumulated"
        ).mock(
            return_value=_row_response({"securityCode": "000001.SZ", "revenue": 100.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).income_statement(security_code="000001.SZ")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["securityCode"] == "000001.SZ"
    assert df.iloc[0]["revenue"] == 100.0


def test_income_statement_quarterly(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(
            "/application/open-fundamental/financial-report/income-statement/quarterly"
        ).mock(
            return_value=_row_response({"securityCode": "000001.SZ", "revenue": 25.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).income_statement_quarterly(security_code="000001.SZ")
    assert df.iloc[0]["revenue"] == 25.0


def test_balance_sheet(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(
            "/application/open-fundamental/financial-report/balance-sheet/accumulated"
        ).mock(
            return_value=_row_response({"securityCode": "000001.SZ", "totalAssets": 5000.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).balance_sheet(security_code="000001.SZ")
    assert df.iloc[0]["totalAssets"] == 5000.0


def test_cash_flow(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(
            "/application/open-fundamental/financial-report/cash-flow-statement/accumulated"
        ).mock(
            return_value=_row_response({"securityCode": "000001.SZ", "operatingCashFlow": 200.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).cash_flow(security_code="000001.SZ")
    assert df.iloc[0]["operatingCashFlow"] == 200.0


def test_cash_flow_quarterly(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(
            "/application/open-fundamental/financial-report/cash-flow-statement/quarterly"
        ).mock(
            return_value=_row_response({"securityCode": "000001.SZ", "operatingCashFlow": 50.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).cash_flow_quarterly(security_code="000001.SZ")
    assert df.iloc[0]["operatingCashFlow"] == 50.0


def test_income_statement_hk(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/income-statement/hk").mock(
            return_value=_row_response({"securityCode": "00700.HK", "revenue": 999.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).income_statement_hk(security_code="00700.HK")
    assert df.iloc[0]["securityCode"] == "00700.HK"


def test_balance_sheet_hk(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/balance-sheet/hk").mock(
            return_value=_row_response({"securityCode": "00700.HK", "totalAssets": 8000.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).balance_sheet_hk(security_code="00700.HK")
    assert df.iloc[0]["totalAssets"] == 8000.0


def test_cash_flow_hk(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/cash-flow-statement/hk").mock(
            return_value=_row_response({"securityCode": "00700.HK", "operatingCashFlow": 333.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).cash_flow_hk(security_code="00700.HK")
    assert df.iloc[0]["operatingCashFlow"] == 333.0


def test_income_statement_us(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/income-statement/us").mock(
            return_value=_row_response({"securityCode": "TSLA.O", "revenue": 250.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).income_statement_us(security_code="TSLA.O")
    assert df.iloc[0]["securityCode"] == "TSLA.O"


def test_balance_sheet_us(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/balance-sheet/us").mock(
            return_value=_row_response({"securityCode": "TSLA.O", "totalAssets": 12345.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).balance_sheet_us(security_code="TSLA.O")
    assert df.iloc[0]["totalAssets"] == 12345.0


def test_cash_flow_us(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/cash-flow-statement/us").mock(
            return_value=_row_response({"securityCode": "TSLA.O", "operatingCashFlow": 77.0}),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).cash_flow_us(security_code="TSLA.O")
    assert df.iloc[0]["operatingCashFlow"] == 77.0


def test_main_business(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/main-business").mock(
            return_value=_row_response(
                {"securityCode": "000001.SZ", "breakdown": "product", "name": "A", "revenue": 1.0}
            ),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).main_business(security_code="000001.SZ")
        body = route.calls.last.request.read()
        # default breakdown="product" is sent on the wire
        assert b'"breakdown":"product"' in body.replace(b" ", b"")
    assert df.iloc[0]["name"] == "A"


def test_valuation_analysis(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/valuation-analysis").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {
                                "securityCode": "000001.SZ",
                                "indicator": "peTtm",
                                "date": "2026-01-02",
                                "value": 10.0,
                                "percentileRank": 0.5,
                                "average": 11.0,
                                "median": 10.5,
                                "upper1Std": 13.0,
                                "lower1Std": 9.0,
                            },
                        ]
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).valuation_analysis(
                security_code="000001.SZ", indicator="peTtm"
            )
    assert list(df.columns) == [
        "securityCode",
        "indicator",
        "date",
        "value",
        "percentileRank",
        "average",
        "median",
        "upper1Std",
        "lower1Std",
    ]
    assert df.iloc[0]["value"] == 10.0


def test_valuation_analysis_skip_null(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/valuation-analysis").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {
                                "securityCode": "000001.SZ",
                                "indicator": "peTtm",
                                "date": "2026-01-02",
                                "value": 10.0,
                                "percentileRank": 0.5,
                            },
                            {
                                "securityCode": "000001.SZ",
                                "indicator": "peTtm",
                                "date": "2026-01-03",
                                "value": None,
                                "percentileRank": 0.6,
                            },
                            {
                                "securityCode": "000001.SZ",
                                "indicator": "peTtm",
                                "date": "2026-01-04",
                                "value": 12.0,
                                "percentileRank": None,
                            },
                        ]
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).valuation_analysis(
                security_code="000001.SZ", indicator="peTtm", skip_null=True
            )
    # Only the first row survives the skip_null filter.
    assert len(df) == 1
    assert df.iloc[0]["value"] == 10.0


def test_top_holders(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/capital-structure/top-holders").mock(
            return_value=_row_response(
                {"securityCode": "000001.SZ", "holderType": "top10", "holderName": "X"}
            ),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).top_holders(security_code="000001.SZ", holder_type="top10")
        body = route.calls.last.request.read().replace(b" ", b"")
        # No fieldList on top-holders body.
        assert b"fieldList" not in body
        assert b'"holderType":"top10"' in body
    assert df.iloc[0]["holderName"] == "X"


def _earning_forecast_response() -> httpx.Response:
    # Real shape: nested {securityCode, securityName, updateList:[{date, fieldList:[{...}]}]}
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {
                "securityCode": "000001.SZ",
                "securityName": "PAB",
                "updateList": [
                    {
                        "date": "2026-01-15",
                        "fieldList": [
                            {"forecastYear": "2025E", "netIncome": 100.0, "eps": 1.0},
                            {"forecastYear": "2026E", "netIncome": 110.0, "eps": 1.1},
                        ],
                    },
                    {
                        "date": "2026-02-28",
                        "fieldList": [
                            {"forecastYear": "2025E", "netIncome": 105.0, "eps": 1.05},
                            {"forecastYear": "2026E", "netIncome": 115.0, "eps": 1.15},
                        ],
                    },
                ],
            },
        },
    )


def test_earning_forecast_flattened(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_earning_forecast_response(),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).earning_forecast(
                security_code="000001.SZ", consensus=["netIncome", "eps"], latest=False
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        assert b'"consensusList":["netIncome","eps"]' in body
    # latest=False -> 2 update dates x 2 forecast years = 4 rows.
    assert df.shape[0] == 4
    assert list(df.columns)[:4] == ["securityCode", "securityName", "date", "forecastYear"]
    assert set(df["date"]) == {"2026-01-15", "2026-02-28"}


def test_earning_forecast_default_is_latest(tmp_path):
    # Default behavior (no latest arg) keeps only the most recent update date.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_earning_forecast_response(),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).earning_forecast(security_code="000001.SZ")
    # Only the most recent update date (2026-02-28) survives -> 2 rows.
    assert df.shape[0] == 2
    assert set(df["date"]) == {"2026-02-28"}
    assert df[df["forecastYear"] == "2025E"].iloc[0]["netIncome"] == 105.0


def test_earning_forecast_injects_default_dates(tmp_path):
    # TS CLI parity: endDate defaults to BEIJING's today, startDate to 365 days back.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_earning_forecast_response(),
        )
        before = _beijing_today()
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Fundamental(client).earning_forecast(security_code="000001.SZ")
        after = _beijing_today()
        body = json.loads(route.calls.last.request.read())
    assert body["endDate"] in {before.isoformat(), after.isoformat()}
    assert body["startDate"] in {
        (before - dt.timedelta(days=365)).isoformat(),
        (after - dt.timedelta(days=365)).isoformat(),
    }


def test_earning_forecast_start_date_defaults_to_year_before_end_date(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_earning_forecast_response(),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Fundamental(client).earning_forecast(security_code="000001.SZ", end_date="2020-06-30")
        body = json.loads(route.calls.last.request.read())
    assert body["endDate"] == "2020-06-30"
    assert body["startDate"] == "2019-07-01"


def test_earning_forecast_explicit_dates_kept(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_earning_forecast_response(),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Fundamental(client).earning_forecast(
                security_code="000001.SZ", start_date="2025-01-01", end_date="2025-12-31"
            )
        body = route.calls.last.request.read().replace(b" ", b"")
    assert b'"startDate":"2025-01-01"' in body
    assert b'"endDate":"2025-12-31"' in body


def test_statement_matrix_shape_is_transposed(tmp_path):
    # Financial-report endpoints return a columnar matrix
    # {"fieldList": [...], "list": [[...]]} rather than a list of dicts;
    # normalize_rows must transpose it into named columns (otherwise the
    # DataFrame ends up with integer column names or empty).
    matrix = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "endDate", "revenue"],
            "list": [
                ["000001.SZ", "2025-12-31", 100.0],
                ["000001.SZ", "2024-12-31", 90.0],
            ],
        },
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(
            "/application/open-fundamental/financial-report/income-statement/accumulated"
        ).mock(return_value=httpx.Response(200, json=matrix))
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).income_statement(security_code="000001.SZ")
    assert list(df.columns) == ["securityCode", "endDate", "revenue"]
    assert df.shape == (2, 3)
    assert df.iloc[0]["revenue"] == 100.0
    assert df.iloc[1]["endDate"] == "2024-12-31"


def test_valuation_analysis_matrix_shape_is_transposed(tmp_path):
    # valuation-analysis serves the same columnar matrix as the statement
    # endpoints: {"fieldList": [...], "list": [[...]]}. normalize_rows transposes
    # it so columns come from fieldList and each inner array becomes one row.
    # With skip_null=True the (post-transpose) row-wise filter drops any row whose
    # value OR percentileRank is None — here the middle row (null value) is dropped.
    matrix = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "indicator", "date", "value", "percentileRank"],
            "list": [
                ["000001.SZ", "peTtm", "2026-01-02", 10.0, 0.5],
                ["000001.SZ", "peTtm", "2026-01-03", None, 0.6],
                ["000001.SZ", "peTtm", "2026-01-04", 12.0, 0.7],
            ],
        },
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/valuation-analysis").mock(
            return_value=httpx.Response(200, json=matrix)
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).valuation_analysis(
                security_code="000001.SZ", indicator="peTtm", skip_null=True
            )
    # Columns are sourced from fieldList, not integer positions.
    assert list(df.columns) == ["securityCode", "indicator", "date", "value", "percentileRank"]
    # Row with a null value is filtered out; the two complete rows survive,
    # transposed so each inner array maps positionally onto fieldList.
    assert df.shape == (2, 5)
    assert list(df["value"]) == [10.0, 12.0]
    assert df.iloc[0]["date"] == "2026-01-02"
    assert df.iloc[1]["percentileRank"] == 0.7


def test_top_holders_matrix_shape_is_transposed(tmp_path):
    # top-holders also returns the columnar matrix shape; normalize_rows must
    # transpose {fieldList, list:[[...]]} into named columns.
    matrix = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "holderType", "holderName", "holdingRatio"],
            "list": [
                ["000001.SZ", "top10", "Holder A", 5.5],
                ["000001.SZ", "top10", "Holder B", 3.2],
            ],
        },
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/capital-structure/top-holders").mock(
            return_value=httpx.Response(200, json=matrix)
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).top_holders(security_code="000001.SZ", holder_type="top10")
    assert list(df.columns) == ["securityCode", "holderType", "holderName", "holdingRatio"]
    assert df.shape == (2, 4)
    assert df.iloc[0]["holderName"] == "Holder A"
    assert df.iloc[1]["holdingRatio"] == 3.2


def test_main_business_matrix_shape_is_transposed(tmp_path):
    # main-business returns the columnar matrix shape; normalize_rows must
    # transpose {fieldList, list:[[...]]} into named columns.
    matrix = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "breakdown", "name", "revenue"],
            "list": [
                ["000001.SZ", "product", "Segment A", 1000.0],
                ["000001.SZ", "product", "Segment B", 600.0],
            ],
        },
    }
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/main-business").mock(
            return_value=httpx.Response(200, json=matrix)
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).main_business(security_code="000001.SZ")
    assert list(df.columns) == ["securityCode", "breakdown", "name", "revenue"]
    assert df.shape == (2, 4)
    assert df.iloc[0]["name"] == "Segment A"
    assert df.iloc[1]["revenue"] == 600.0


# ─────────────── valuation-analysis completeness (TS v0.39.0-v0.42.0) ───────────────

_VALUATION = "/application/open-fundamental/valuation-analysis"
_EARNING = "/application/open-fundamental/earning-forecast"
_KNOWN = ["tradeDate", "value", "percentileRank", "average", "median", "upper1Std", "lower1Std"]


def _valuation_stub(days: int = 2, *, rows_anyway: bool = False, echo_indicator: bool = True):
    """Shaped like the live endpoint (CLI probes 2026-09-24/25): the echoed field list
    is `tradeDate` then the requested names de-duplicated, unknown ones kept; each row
    is the date then one value per requested name in request order — so an explicit
    `tradeDate` or a repeated name adds a value and an unknown name adds none. A request
    with no value column answers an empty list. `limit` keeps the MOST RECENT rows."""

    def handler(request: httpx.Request) -> httpx.Response:
        req = json.loads(request.read())
        requested = req.get("fieldList")
        fields = (
            ["tradeDate", *dict.fromkeys(f for f in requested if f != "tradeDate")]
            if requested
            else _KNOWN
        )
        rows = [[f"2026-09-{i + 1:02d}", 21.5 + i, 0.42, 20, 20, 30, 10] for i in range(days)]
        has_value = not requested or any(f in _KNOWN[1:] for f in requested)
        kept = rows[-req["limit"] :] if (has_value or rows_anyway) else []
        if rows_anyway:
            out = [[row[_KNOWN.index(f)] if f in _KNOWN else None for f in fields] for row in kept]
        elif requested:
            out = [
                [row[0], *(row[_KNOWN.index(f)] for f in requested if f in _KNOWN)] for row in kept
            ]
        else:
            out = kept
        data = {"fieldList": fields, "list": out}
        if echo_indicator:
            data = {"indicator": req.get("indicator"), **data}
        return httpx.Response(200, json={"code": "000000", "status": True, "data": data})

    return handler


def _valuation(tmp_path, stub, **kwargs):
    """Call valuation_analysis against ``stub``; returns (result, sent body)."""
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_VALUATION).mock(side_effect=stub)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            out = Fundamental(client).valuation_analysis(
                security_code="600519.SH", indicator="peTtm", **kwargs
            )
        sent = json.loads(route.calls.last.request.read())
    return out, sent


def test_valuation_sends_the_default_limit_when_omitted(tmp_path):
    # Sent explicitly so the truncation check compares against the number actually sent.
    _, sent = _valuation(tmp_path, _valuation_stub())
    assert sent["limit"] == 2000


def test_valuation_rejects_a_non_positive_limit_before_any_request(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_VALUATION).mock(side_effect=_valuation_stub())
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            for bad in (0, -1, True, 1.5):
                with pytest.raises(ValidationError, match="limit"):
                    Fundamental(client).valuation_analysis(
                        security_code="600519.SH", indicator="peTtm", limit=bad
                    )
    assert not route.called


def test_valuation_full_page_is_partial_and_says_the_start_is_missing(tmp_path):
    # The server keeps the most recent rows, so a range longer than the limit silently
    # loses its beginning (TS v0.41.1 ②).
    with pytest.warns(UserWarning, match="START of the range"):
        out, _ = _valuation(tmp_path, _valuation_stub(5), limit=3, raw=True)
    assert out["partial"] is True
    assert [row[0] for row in out["list"]] == ["2026-09-03", "2026-09-04", "2026-09-05"]


def test_valuation_full_page_warns_on_the_dataframe_path_too(tmp_path):
    with pytest.warns(UserWarning, match="START of the range"):
        df, _ = _valuation(tmp_path, _valuation_stub(5), limit=3)
    assert list(df["tradeDate"]) == ["2026-09-03", "2026-09-04", "2026-09-05"]


def test_valuation_skip_null_keeps_the_truncation_signal(tmp_path):
    with pytest.warns(UserWarning, match="START of the range"):
        df, _ = _valuation(tmp_path, _valuation_stub(5), limit=3, skip_null=True)
    assert len(df) == 3


def test_valuation_range_of_exactly_limit_days_is_not_flagged(tmp_path):
    # Full page, but the ascending first row IS the requested start: nothing was cut.
    out, _ = _valuation(tmp_path, _valuation_stub(5), start_date="2026-09-03", limit=3, raw=True)
    assert "partial" not in out


def test_valuation_full_page_starting_after_start_date_is_flagged_once(tmp_path):
    # The truncation warning already says the start is missing; no second, vaguer note.
    with pytest.warns(UserWarning) as record:
        out, _ = _valuation(
            tmp_path, _valuation_stub(5), start_date="2026-09-01", limit=3, raw=True
        )
    assert out["partial"] is True
    messages = [str(w.message) for w in record]
    assert any("START of the range" in m for m in messages)
    assert not any("later than start_date" in m for m in messages)


def test_valuation_late_first_row_on_a_short_page_is_noted(tmp_path):
    # The server clips a range reaching past the account's history window without an
    # error, and a later listing looks the same (TS v0.41.1 ④).
    with pytest.warns(UserWarning, match="starts at 2026-09-01, later than start_date 2026-08-01"):
        out, _ = _valuation(tmp_path, _valuation_stub(5), start_date="2026-08-01", raw=True)
    assert "partial" not in out
    # On time: silent (the suite escalates any UserWarning to an error).
    _valuation(tmp_path, _valuation_stub(5), start_date="2026-09-01")


def test_valuation_result_under_the_limit_is_not_flagged(tmp_path):
    out, _ = _valuation(tmp_path, _valuation_stub(5), limit=10, raw=True)
    assert "partial" not in out
    assert len(out["list"]) == 5


def test_valuation_sends_each_field_once_and_never_trade_date(tmp_path):
    # An explicit tradeDate or a repeated name adds a value to every row while the
    # echoed field list names it once (TS v0.41.1 ③).
    for field in (["tradeDate", "value"], ["value", "value"], ["value", "tradeDate", "value"]):
        df, sent = _valuation(tmp_path, _valuation_stub(), field=field)
        assert sent["fieldList"] == ["value"], field
        assert df.iloc[0].to_dict() == {"tradeDate": "2026-09-01", "value": 21.5}, field


def test_valuation_trade_date_alone_is_still_sent_and_explained(tmp_path):
    # Dropping it would ask for every column; the endpoint answers it with no rows,
    # which says nothing about whether data exists (TS v0.42.0 ⑤).
    with pytest.warns(UserWarning, match="names no value column"):
        df, sent = _valuation(tmp_path, _valuation_stub(), field="tradeDate")
    assert sent["fieldList"] == ["tradeDate"]
    assert df.empty


def test_valuation_no_value_column_note_needs_an_empty_answer(tmp_path):
    # A server that answers rows anyway must not get the "nothing came back" note.
    df, _ = _valuation(tmp_path, _valuation_stub(rows_anyway=True), field="tradeDate")
    assert len(df) == 2
    # And a value column never triggers it.
    _valuation(tmp_path, _valuation_stub(), field="value")


def test_valuation_refuses_a_field_list_that_would_shift_every_value(tmp_path):
    # tradeDate (one value too many) plus an unknown name (one too few) would cancel
    # out: widths equal, every value one column to the right. tradeDate is not sent, so
    # the unknown name leaves the rows short and the width guard refuses it.
    for extra in ({}, {"skip_null": True}):
        with pytest.raises(ValidationError, match="fieldList"):
            _valuation(
                tmp_path,
                _valuation_stub(),
                field=["tradeDate", "value", "percentileRank", "foo"],
                **extra,
            )


def test_valuation_skip_null_fetches_the_columns_it_filters_on(tmp_path):
    # Narrowing field must not narrow the REQUEST past the filter's own column: without
    # percentileRank every row reads as null and the filter drops them all (TS v0.39.0 ⑥).
    df, sent = _valuation(tmp_path, _valuation_stub(), field="value", skip_null=True)
    assert sent["fieldList"] == ["value", "percentileRank"]
    assert len(df) == 2
    # Fetched for the filter only: field still decides the output columns.
    assert list(df.columns) == ["tradeDate", "value"]


def test_valuation_skip_null_with_trade_date_only(tmp_path):
    df, sent = _valuation(tmp_path, _valuation_stub(), field="tradeDate", skip_null=True)
    assert sent["fieldList"] == ["value", "percentileRank"]
    assert list(df.columns) == ["tradeDate"]
    assert list(df["tradeDate"]) == ["2026-09-01", "2026-09-02"]


def test_valuation_without_skip_null_sends_field_unchanged(tmp_path):
    df, sent = _valuation(tmp_path, _valuation_stub(), field="value")
    assert sent["fieldList"] == ["value"]
    assert list(df.columns) == ["tradeDate", "value"]


def test_valuation_raw_ignores_skip_null_and_requests_only_field(tmp_path):
    out, sent = _valuation(tmp_path, _valuation_stub(), field="value", skip_null=True, raw=True)
    assert sent["fieldList"] == ["value"]
    assert out["fieldList"] == ["tradeDate", "value"]


def test_valuation_skip_null_filters_the_bare_array_layout(tmp_path):
    # Without the `indicator` echo the normalized rows are a bare array.
    def stub(request):
        data = {
            "fieldList": ["tradeDate", "value", "percentileRank"],
            "list": [["2026-09-01", 1.0, 0.1], ["2026-09-02", None, 0.2]],
        }
        return httpx.Response(200, json={"code": "000000", "status": True, "data": data})

    df, _ = _valuation(tmp_path, stub, skip_null=True)
    assert list(df["tradeDate"]) == ["2026-09-01"]


# ─────────────── earning-forecast: Beijing default + credit guard ───────────────


def _forecast_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"securityCode": "600519.SH", "securityName": "贵州茅台", "updateList": []},
        },
    )


def test_earning_forecast_defaults_the_end_date_to_beijing_whatever_the_machine_zone(
    tmp_path, monkeypatch
):
    # 2026-07-05 23:30 UTC is already 07-06 in Beijing; the UTC day (and the local day
    # on a UTC host) still say 07-05 (TS v0.43.0 ⑪).
    class _Frozen(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            instant = dt.datetime(2026, 7, 5, 23, 30, tzinfo=dt.timezone.utc)
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    fake_dt = types.SimpleNamespace(datetime=_Frozen, date=dt.date, timedelta=dt.timedelta)
    monkeypatch.setattr(fundamental_module, "dt", fake_dt)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_EARNING).mock(return_value=_forecast_ok())
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Fundamental(client).earning_forecast(security_code="600519.SH")
        body = json.loads(route.calls.last.request.read())
    assert body["endDate"] == "2026-07-06"
    assert body["startDate"] == "2025-07-06"


def test_earning_forecast_slash_end_date_anchors_the_default_start(tmp_path):
    # The anchor is computed from the NORMALIZED end date: fromisoformat cannot read
    # "2026/09/30".
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_EARNING).mock(return_value=_forecast_ok())
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Fundamental(client).earning_forecast(security_code="600519.SH", end_date="2026/09/30")
        body = json.loads(route.calls.last.request.read())
    assert body["endDate"] == "2026-09-30"
    assert body["startDate"] == "2025-09-30"


def test_earning_forecast_costly_range_needs_confirm(tmp_path):
    # Billed 0.5 per row, ~3 rows per weekday: ten years is far above 1000 credits
    # and is refused before anything is sent (TS v0.44.0 ⑧).
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_EARNING).mock(return_value=_forecast_ok())
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ValidationError, match=r"about \d+ credits"):
                Fundamental(client).earning_forecast(
                    security_code="600519.SH", start_date="2016-01-01", end_date="2026-09-30"
                )
            assert not route.called
            # The default one-year window stays under the guard.
            Fundamental(client).earning_forecast(security_code="600519.SH", end_date="2026-09-30")
            Fundamental(client).earning_forecast(
                security_code="600519.SH",
                start_date="2016-01-01",
                end_date="2026-09-30",
                confirm=True,
            )
        bodies = [json.loads(call.request.read()) for call in route.calls]
    assert [b["startDate"] for b in bodies] == ["2025-09-30", "2016-01-01"]
    # confirm is a local switch, never a wire field.
    assert all("confirm" not in b for b in bodies)
