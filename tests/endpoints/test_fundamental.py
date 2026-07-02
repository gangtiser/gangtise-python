import datetime as dt
import json

import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.fundamental import Fundamental


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
    # TS CLI parity: endDate defaults to today, startDate to 365 days back.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_earning_forecast_response(),
        )
        before = dt.date.today()
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Fundamental(client).earning_forecast(security_code="000001.SZ")
        after = dt.date.today()
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
