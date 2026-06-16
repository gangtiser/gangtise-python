from __future__ import annotations

import datetime as dt
import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.fundamental import AsyncFundamental


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
async def test_async_income_statement(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(
            "/application/open-fundamental/financial-report/income-statement/accumulated"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {"securityCode": "000001.SZ", "revenue": 100.0},
                        ]
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).income_statement(
                security_code="000001.SZ",
            )
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["revenue"] == 100.0


@pytest.mark.anyio
async def test_async_valuation_analysis_skip_null(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/valuation-analysis").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {"securityCode": "000001.SZ", "value": 10.0, "percentileRank": 50.0},
                            {"securityCode": "000001.SZ", "value": None, "percentileRank": None},
                        ]
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).valuation_analysis(
                security_code="000001.SZ",
                indicator="PE",
                skip_null=True,
            )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 10.0


@pytest.mark.anyio
async def test_async_earning_forecast_injects_default_dates(tmp_path):
    # TS CLI parity: endDate defaults to today, startDate to 365 days back.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "securityCode": "000001.SZ",
                        "securityName": "PAB",
                        "updateList": [],
                    },
                },
            )
        )
        before = dt.date.today()
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncFundamental(client).earning_forecast(security_code="000001.SZ")
        after = dt.date.today()
        body = json.loads(route.calls.last.request.read())
    assert body["endDate"] in {before.isoformat(), after.isoformat()}
    assert body["startDate"] in {
        (before - dt.timedelta(days=365)).isoformat(),
        (after - dt.timedelta(days=365)).isoformat(),
    }


# ---------------------------------------------------------------------------
# Body-mapping coverage for the 9 async methods that lacked an async test.
#
# These tests assert the OUTGOING request body (snake_case kwarg -> camelCase
# wire field). The sync tests cannot catch a typo in the *async* wrapper, so the
# whole point here is to read ``router.calls.last.request`` and verify the exact
# camelCase keys/values the async wrapper put on the wire. A realistic columnar
# matrix response (``{data:{fieldList:[...], list:[[...]]}}``, _normalize case 1)
# is used so the DataFrame transpose is exercised too.
# ---------------------------------------------------------------------------


def _matrix_response(field_list: list[str], rows: list[list]) -> httpx.Response:
    """Columnar-matrix envelope: {data:{fieldList, list:[[...]]}} (normalize case 1)."""
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"fieldList": field_list, "list": rows},
        },
    )


def _last_body(route) -> dict:
    return json.loads(route.calls.last.request.content)


@pytest.mark.anyio
async def test_async_income_statement_quarterly_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-fundamental/financial-report/income-statement/quarterly"
        ).mock(
            return_value=_matrix_response(
                ["securityCode", "endDate", "revenue"],
                [["000001.SZ", "2025-03-31", 25.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).income_statement_quarterly(
                security_code="000001.SZ",
                period="q1",
                report_type="latest",
                fiscal_year=2025,
                field="revenue",
            )
        body = _last_body(route)
    # snake_case -> camelCase, scalars wrapped into lists via _as_list.
    assert body == {
        "securityCode": "000001.SZ",
        "period": ["q1"],
        "reportType": ["latest"],
        "fiscalYear": [2025],
        "fieldList": ["revenue"],
    }
    # Columnar matrix transposed into named columns.
    assert list(df.columns) == ["securityCode", "endDate", "revenue"]
    assert df.iloc[0]["revenue"] == 25.0
    assert df.iloc[0]["endDate"] == "2025-03-31"


@pytest.mark.anyio
async def test_async_balance_sheet_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-fundamental/financial-report/balance-sheet/accumulated"
        ).mock(
            return_value=_matrix_response(
                ["securityCode", "endDate", "totalAssets"],
                [["000001.SZ", "2025-12-31", 5000.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).balance_sheet(
                security_code="000001.SZ",
                period="2025annual",
                report_type="adjusted",
            )
        body = _last_body(route)
    assert body == {
        "securityCode": "000001.SZ",
        "period": ["2025annual"],
        "reportType": ["adjusted"],
    }
    assert list(df.columns) == ["securityCode", "endDate", "totalAssets"]
    assert df.iloc[0]["totalAssets"] == 5000.0


@pytest.mark.anyio
async def test_async_cash_flow_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-fundamental/financial-report/cash-flow-statement/accumulated"
        ).mock(
            return_value=_matrix_response(
                ["securityCode", "endDate", "operatingCashFlow"],
                [["000001.SZ", "2025-12-31", 200.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).cash_flow(
                security_code="000001.SZ",
                start_date="2024-01-01",
                end_date="2025-12-31",
            )
        body = _last_body(route)
    assert body == {
        "securityCode": "000001.SZ",
        "startDate": "2024-01-01",
        "endDate": "2025-12-31",
    }
    assert list(df.columns) == ["securityCode", "endDate", "operatingCashFlow"]
    assert df.iloc[0]["operatingCashFlow"] == 200.0


@pytest.mark.anyio
async def test_async_cash_flow_quarterly_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-fundamental/financial-report/cash-flow-statement/quarterly"
        ).mock(
            return_value=_matrix_response(
                ["securityCode", "endDate", "operatingCashFlow"],
                [["000001.SZ", "2025-03-31", 50.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).cash_flow_quarterly(
                security_code="000001.SZ",
                period=["q1", "q2"],
            )
        body = _last_body(route)
    # List input passes through _as_list unchanged.
    assert body == {"securityCode": "000001.SZ", "period": ["q1", "q2"]}
    assert list(df.columns) == ["securityCode", "endDate", "operatingCashFlow"]
    assert df.iloc[0]["operatingCashFlow"] == 50.0


@pytest.mark.anyio
async def test_async_income_statement_hk_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-fundamental/financial-report/income-statement/hk"
        ).mock(
            return_value=_matrix_response(
                ["securityCode", "endDate", "revenue"],
                [["00700.HK", "2025-12-31", 999.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).income_statement_hk(
                security_code="00700.HK",
                period="annual",
            )
        body = _last_body(route)
    assert body == {"securityCode": "00700.HK", "period": ["annual"]}
    assert list(df.columns) == ["securityCode", "endDate", "revenue"]
    assert df.iloc[0]["securityCode"] == "00700.HK"
    assert df.iloc[0]["revenue"] == 999.0


@pytest.mark.anyio
async def test_async_balance_sheet_hk_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/financial-report/balance-sheet/hk").mock(
            return_value=_matrix_response(
                ["securityCode", "endDate", "totalAssets"],
                [["00700.HK", "2025-12-31", 8000.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).balance_sheet_hk(
                security_code="00700.HK",
                period="annual",
            )
        body = _last_body(route)
    assert body == {"securityCode": "00700.HK", "period": ["annual"]}
    assert list(df.columns) == ["securityCode", "endDate", "totalAssets"]
    assert df.iloc[0]["totalAssets"] == 8000.0


@pytest.mark.anyio
async def test_async_cash_flow_hk_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(
            "/application/open-fundamental/financial-report/cash-flow-statement/hk"
        ).mock(
            return_value=_matrix_response(
                ["securityCode", "endDate", "operatingCashFlow"],
                [["00700.HK", "2025-12-31", 333.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).cash_flow_hk(
                security_code="00700.HK",
                period="annual",
            )
        body = _last_body(route)
    assert body == {"securityCode": "00700.HK", "period": ["annual"]}
    assert list(df.columns) == ["securityCode", "endDate", "operatingCashFlow"]
    assert df.iloc[0]["operatingCashFlow"] == 333.0


@pytest.mark.anyio
async def test_async_main_business_body(tmp_path):
    # main_business maps `period` -> `periodList` (NOT bare `period`); the default
    # breakdown="product" must appear on the wire.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/main-business").mock(
            return_value=_matrix_response(
                ["securityCode", "breakdown", "name", "revenue"],
                [["000001.SZ", "product", "A", 1.0]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).main_business(
                security_code="000001.SZ",
                period="annual",
                field="revenue",
            )
        body = _last_body(route)
    assert body == {
        "securityCode": "000001.SZ",
        "breakdown": "product",
        "periodList": ["annual"],
        "fieldList": ["revenue"],
    }
    # Guard the divergence: this endpoint must NOT send a bare `period`.
    assert "period" not in body
    assert list(df.columns) == ["securityCode", "breakdown", "name", "revenue"]
    assert df.iloc[0]["name"] == "A"
    assert df.iloc[0]["revenue"] == 1.0


@pytest.mark.anyio
async def test_async_top_holders_body(tmp_path):
    # top_holders maps `period` -> bare `period` (NOT `periodList`) and sends
    # `holderType`; it must NOT include a `fieldList` key.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-fundamental/capital-structure/top-holders").mock(
            return_value=_matrix_response(
                ["securityCode", "holderType", "holderName"],
                [["000001.SZ", "top10", "X"]],
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).top_holders(
                security_code="000001.SZ",
                holder_type="top10",
                period="annual",
                fiscal_year=2025,
            )
        body = _last_body(route)
    assert body == {
        "securityCode": "000001.SZ",
        "holderType": "top10",
        "period": ["annual"],
        "fiscalYear": [2025],
    }
    # Guard the divergence from main_business: bare `period`, never `periodList`,
    # and no `fieldList` on this endpoint.
    assert "periodList" not in body
    assert "fieldList" not in body
    assert list(df.columns) == ["securityCode", "holderType", "holderName"]
    assert df.iloc[0]["holderName"] == "X"
