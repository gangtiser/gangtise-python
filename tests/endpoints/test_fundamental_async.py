from __future__ import annotations

import datetime as dt
import json
import types

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ValidationError
from gangtise_openapi.domains import fundamental as fundamental_module
from gangtise_openapi.domains.fundamental import AsyncFundamental

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
                indicator="peTtm",
                skip_null=True,
            )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 10.0


@pytest.mark.anyio
async def test_async_earning_forecast_injects_default_dates(tmp_path):
    # TS CLI parity: endDate defaults to BEIJING's today, startDate to 365 days back.
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
        before = _beijing_today()
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncFundamental(client).earning_forecast(security_code="000001.SZ")
        after = _beijing_today()
        body = json.loads(route.calls.last.request.read())
    assert body["endDate"] in {before.isoformat(), after.isoformat()}
    assert body["startDate"] in {
        (before - dt.timedelta(days=365)).isoformat(),
        (after - dt.timedelta(days=365)).isoformat(),
    }


@pytest.mark.anyio
async def test_async_earning_forecast_start_date_defaults_to_year_before_end_date(tmp_path):
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
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncFundamental(client).earning_forecast(
                security_code="000001.SZ", end_date="2020-06-30"
            )
        body = json.loads(route.calls.last.request.read())
    assert body["endDate"] == "2020-06-30"
    assert body["startDate"] == "2019-07-01"


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


@pytest.mark.anyio
async def test_async_income_statement_us(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/income-statement/us").mock(
            return_value=_matrix_response(["securityCode", "revenue"], [["TSLA.O", 250.0]])
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).income_statement_us(security_code="TSLA.O")
    assert df.iloc[0]["securityCode"] == "TSLA.O"


@pytest.mark.anyio
async def test_async_balance_sheet_us(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/balance-sheet/us").mock(
            return_value=_matrix_response(["securityCode", "totalAssets"], [["TSLA.O", 12345.0]])
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).balance_sheet_us(security_code="TSLA.O")
    assert df.iloc[0]["totalAssets"] == 12345.0


@pytest.mark.anyio
async def test_async_cash_flow_us(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-fundamental/financial-report/cash-flow-statement/us").mock(
            return_value=_matrix_response(["securityCode", "operatingCashFlow"], [["TSLA.O", 77.0]])
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncFundamental(client).cash_flow_us(security_code="TSLA.O")
    assert df.iloc[0]["operatingCashFlow"] == 77.0


# ─────────────── valuation-analysis completeness (TS v0.39.0-v0.42.0) ───────────────

_VALUATION = "/application/open-fundamental/valuation-analysis"
_EARNING = "/application/open-fundamental/earning-forecast"
_KNOWN = ["tradeDate", "value", "percentileRank", "average", "median", "upper1Std", "lower1Std"]


def _valuation_stub(days: int = 2, *, rows_anyway: bool = False):
    """Same live-shaped stub as the sync suite: echoed fields de-duplicated with unknown
    names kept, one value per requested known name (an explicit tradeDate adds one), no
    rows without a value column, `limit` keeps the most recent rows."""

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
        data = {"indicator": req.get("indicator"), "fieldList": fields, "list": out}
        return httpx.Response(200, json={"code": "000000", "status": True, "data": data})

    return handler


async def _valuation(tmp_path, stub, **kwargs):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_VALUATION).mock(side_effect=stub)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            out = await AsyncFundamental(client).valuation_analysis(
                security_code="600519.SH", indicator="peTtm", **kwargs
            )
        sent = json.loads(route.calls.last.request.read())
    return out, sent


@pytest.mark.anyio
async def test_async_valuation_sends_the_default_limit_when_omitted(tmp_path):
    _, sent = await _valuation(tmp_path, _valuation_stub())
    assert sent["limit"] == 2000


@pytest.mark.anyio
async def test_async_valuation_rejects_a_non_positive_limit_before_any_request(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_VALUATION).mock(side_effect=_valuation_stub())
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ValidationError, match="limit"):
                await AsyncFundamental(client).valuation_analysis(
                    security_code="600519.SH", indicator="peTtm", limit=0
                )
    assert not route.called


@pytest.mark.anyio
async def test_async_valuation_full_page_is_partial_and_says_the_start_is_missing(tmp_path):
    with pytest.warns(UserWarning, match="START of the range"):
        out, _ = await _valuation(tmp_path, _valuation_stub(5), limit=3, raw=True)
    assert out["partial"] is True
    with pytest.warns(UserWarning, match="START of the range"):
        df, _ = await _valuation(tmp_path, _valuation_stub(5), limit=3, skip_null=True)
    assert len(df) == 3


@pytest.mark.anyio
async def test_async_valuation_first_row_decides_truncation_and_late_start(tmp_path):
    # Range of exactly `limit` days: the first row IS the start, nothing was cut.
    out, _ = await _valuation(
        tmp_path, _valuation_stub(5), start_date="2026-09-03", limit=3, raw=True
    )
    assert "partial" not in out
    # A full page starting after start_date: flagged, and no second note.
    with pytest.warns(UserWarning) as record:
        out, _ = await _valuation(
            tmp_path, _valuation_stub(5), start_date="2026-09-01", limit=3, raw=True
        )
    assert out["partial"] is True
    assert not any("later than start_date" in str(w.message) for w in record)
    # A short page starting late: noted, not partial.
    with pytest.warns(UserWarning, match="later than start_date 2026-08-01"):
        out, _ = await _valuation(tmp_path, _valuation_stub(5), start_date="2026-08-01", raw=True)
    assert "partial" not in out


@pytest.mark.anyio
async def test_async_valuation_field_is_deduped_without_trade_date(tmp_path):
    df, sent = await _valuation(tmp_path, _valuation_stub(), field=["tradeDate", "value", "value"])
    assert sent["fieldList"] == ["value"]
    assert df.iloc[0].to_dict() == {"tradeDate": "2026-09-01", "value": 21.5}
    with pytest.warns(UserWarning, match="names no value column"):
        df, sent = await _valuation(tmp_path, _valuation_stub(), field="tradeDate")
    assert sent["fieldList"] == ["tradeDate"]
    assert df.empty
    # Rows anyway: no note.
    await _valuation(tmp_path, _valuation_stub(rows_anyway=True), field="tradeDate")


@pytest.mark.anyio
async def test_async_valuation_refuses_a_field_list_that_would_shift_every_value(tmp_path):
    with pytest.raises(ValidationError, match="fieldList"):
        await _valuation(
            tmp_path, _valuation_stub(), field=["tradeDate", "value", "percentileRank", "foo"]
        )


@pytest.mark.anyio
async def test_async_valuation_skip_null_fetches_the_columns_it_filters_on(tmp_path):
    df, sent = await _valuation(tmp_path, _valuation_stub(), field="value", skip_null=True)
    assert sent["fieldList"] == ["value", "percentileRank"]
    assert list(df.columns) == ["tradeDate", "value"]
    assert len(df) == 2
    _, sent = await _valuation(tmp_path, _valuation_stub(), field="value", skip_null=True, raw=True)
    assert sent["fieldList"] == ["value"]


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


@pytest.mark.anyio
async def test_async_earning_forecast_defaults_the_end_date_to_beijing(tmp_path, monkeypatch):
    class _Frozen(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            instant = dt.datetime(2026, 7, 5, 23, 30, tzinfo=dt.timezone.utc)
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    fake_dt = types.SimpleNamespace(datetime=_Frozen, date=dt.date, timedelta=dt.timedelta)
    monkeypatch.setattr(fundamental_module, "dt", fake_dt)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_EARNING).mock(return_value=_forecast_ok())
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncFundamental(client).earning_forecast(security_code="600519.SH")
        body = json.loads(route.calls.last.request.read())
    assert (body["startDate"], body["endDate"]) == ("2025-07-06", "2026-07-06")


@pytest.mark.anyio
async def test_async_earning_forecast_slash_end_date_anchors_the_default_start(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_EARNING).mock(return_value=_forecast_ok())
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncFundamental(client).earning_forecast(
                security_code="600519.SH", end_date="2026/09/30"
            )
        body = json.loads(route.calls.last.request.read())
    assert (body["startDate"], body["endDate"]) == ("2025-09-30", "2026-09-30")


@pytest.mark.anyio
async def test_async_earning_forecast_costly_range_needs_confirm(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post(_EARNING).mock(return_value=_forecast_ok())
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ValidationError, match=r"about \d+ credits"):
                await AsyncFundamental(client).earning_forecast(
                    security_code="600519.SH", start_date="2016-01-01", end_date="2026-09-30"
                )
            assert not route.called
            await AsyncFundamental(client).earning_forecast(
                security_code="600519.SH",
                start_date="2016-01-01",
                end_date="2026-09-30",
                confirm=True,
            )
        body = json.loads(route.calls.last.request.read())
    assert body["startDate"] == "2016-01-01"
    assert "confirm" not in body
