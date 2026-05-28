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


def test_earning_forecast(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_row_response(
                {"securityCode": "000001.SZ", "netIncome": 500.0, "eps": 1.23}
            ),
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Fundamental(client).earning_forecast(
                security_code="000001.SZ", consensus=["netIncome", "eps"]
            )
        body = route.calls.last.request.read().replace(b" ", b"")
        # No fieldList; consensus is sent as consensusList.
        assert b"fieldList" not in body
        assert b'"consensusList":["netIncome","eps"]' in body
    assert df.iloc[0]["eps"] == 1.23
