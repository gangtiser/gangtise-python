from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains.quote import AsyncQuote, _normalize_quote_rows


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        page_concurrency=2,
    )


@pytest.mark.anyio
async def test_async_day_kline_single_security(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {"securityCode": "000001.SH", "date": "2026-01-02", "close": 12.3},
                        ]
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).day_kline(security="000001.SH")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["close"] == 12.3


@pytest.mark.anyio
async def test_async_day_kline_us_shard_count(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline-us/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncQuote(client).day_kline_us(
                security="all",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-07",  # Wed
            )
        # 1-day shards x 3 weekdays
        assert route.call_count == 3


@pytest.mark.anyio
async def test_async_day_kline_all_weekend_range_makes_no_requests(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).day_kline(
                security="aShares",
                start_date="2026-01-03",  # Sat
                end_date="2026-01-04",  # Sun
            )
        assert route.call_count == 0
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@pytest.mark.anyio
async def test_async_day_kline_matrix_fast_path_matches_normalize_path(tmp_path):
    fields = ["securityCode", "tradeDate", "open", "close", "volume"]
    rows = [
        ["000001.SH", "2026-01-05", 10.0, 10.5, 1000],
        ["000002.SZ", "2026-01-05", 5.0, 5.2, 2000],
    ]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"fieldList": fields, "list": rows},
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).day_kline(security=["000001.SH", "000002.SZ"])
    expected = to_dataframe(_normalize_quote_rows(rows, fields), schema=None)
    pd.testing.assert_frame_equal(df, expected)
    assert list(df.columns) == fields


def _partial_failure_responder(request):
    """Mon-Wed shards: the Tuesday shard fails with a business error."""
    body = json.loads(request.read())
    if body["startDate"] == "2026-01-06":
        return httpx.Response(200, json={"code": "100001", "status": False, "msg": "boom"})
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "tradeDate", "close"],
                "list": [["000001.SH", body["startDate"], 1.0]],
            },
        },
    )


@pytest.mark.anyio
async def test_async_day_kline_partial_shard_failure_aborts_and_sets_flags(tmp_path):
    # Async sibling of the abort contract: Tuesday's hard error stops the fan-out,
    # Wednesday lands in failedShards without a request. Serial for determinism.
    cfg = replace(_cfg(tmp_path), page_concurrency=1)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            side_effect=_partial_failure_responder
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.warns(UserWarning, match="2/3 day-kline shards failed"):
                out = await AsyncQuote(client).day_kline(
                    security="aShares",
                    start_date="2026-01-05",  # Mon
                    end_date="2026-01-07",  # Wed
                    raw=True,
                )
        assert route.call_count == 2
    assert out["partial"] is True
    assert out["failedShards"] == [
        {"startDate": "2026-01-06", "endDate": "2026-01-06"},
        {"startDate": "2026-01-07", "endDate": "2026-01-07"},
    ]
    assert sorted(row[1] for row in out["list"]) == ["2026-01-05"]


def _malformed_shard_responder(request):
    """Mon-Wed shards: the Tuesday shard returns 2xx but malformed (non-list) data."""
    body = json.loads(request.read())
    if body["startDate"] == "2026-01-06":
        return httpx.Response(
            200, json={"code": "000000", "status": True, "data": {"unexpected": "shape"}}
        )
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "tradeDate", "close"],
                "list": [["000001.SH", body["startDate"], 1.0]],
            },
        },
    )


@pytest.mark.anyio
async def test_async_day_kline_malformed_shard_response_sets_partial(tmp_path):
    # Async sibling of test_day_kline_malformed_shard_response_sets_partial.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(
            side_effect=_malformed_shard_responder
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.warns(UserWarning, match="1/3 day-kline shards failed"):
                out = await AsyncQuote(client).day_kline(
                    security="aShares",
                    start_date="2026-01-05",  # Mon
                    end_date="2026-01-07",  # Wed
                    raw=True,
                )
    assert out["partial"] is True
    assert out["failedShards"] == [{"startDate": "2026-01-06", "endDate": "2026-01-06"}]
    assert sorted(row[1] for row in out["list"]) == ["2026-01-05", "2026-01-07"]


@pytest.mark.anyio
async def test_async_day_kline_all_shards_failed_raises_bare_api_error(tmp_path):
    # `except ApiError` must work on the async fan-out path too (no ExceptionGroup).
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "100001", "status": False, "msg": "boom"}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError) as excinfo:
                await AsyncQuote(client).day_kline(
                    security="aShares",
                    start_date="2026-01-05",  # Mon
                    end_date="2026-01-06",  # Tue
                )
    assert excinfo.value.code == "100001"


@pytest.mark.anyio
async def test_async_day_kline_hk_shard_count_and_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline-hk/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncQuote(client).day_kline_hk(
                security="all",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-09",  # Fri
            )
        # 2-day shards x 5 weekdays -> 3 shards
        assert route.call_count == 3
        # day-kline-hk body uses `securityList` (camelCase, list form)
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityList":["all"]' in sent
        assert b'"securityCode"' not in sent


@pytest.mark.anyio
@pytest.mark.parametrize("keyword", ["all", "ALL"])
async def test_async_index_day_kline_refuses_a_keyword_before_any_request(tmp_path, keyword):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/index/kline/daily")
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ValidationError, match="total 0 and no error"):
                await AsyncQuote(client).index_day_kline(
                    security=keyword, start_date="2026-06-03", end_date="2026-06-03"
                )
        assert route.call_count == 0


@pytest.mark.anyio
async def test_async_minute_kline(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/minute").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {
                                "securityCode": "000001.SH",
                                "datetime": "2026-01-02 10:00:00",
                                "close": 12.3,
                            },
                        ]
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).minute_kline(security="000001.SH")
        # minute-kline body uses `securityCode` (singular), NOT `securityList`
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityCode":"000001.SH"' in sent
        assert b'"securityList"' not in sent
    assert df.iloc[0]["close"] == 12.3


@pytest.mark.anyio
async def test_async_realtime(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"securityCode": "000001.SH", "price": 12.34}],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).realtime(security=["000001.SH"])
    assert df.iloc[0]["price"] == 12.34


@pytest.mark.anyio
async def test_async_fund_flow_single_security_body_and_default_limit(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/fund-flow/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "fieldList": ["securityCode", "tradeDate", "mainNetInflow"],
                        "list": [["600519.SH", "2026-06-03", 1234.5]],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).fund_flow(
                security="600519.SH",
                start_date="2026-06-01",
                end_date="2026-06-05",
            )
        body = json.loads(route.calls.last.request.read())
        assert body == {
            "securityList": ["600519.SH"],
            "startDate": "2026-06-01",
            "endDate": "2026-06-05",
            "limit": 6000,
        }
    assert df.iloc[0]["mainNetInflow"] == 1234.5


@pytest.mark.anyio
async def test_async_fund_flow_ashares_shards_by_day(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/fund-flow/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncQuote(client).fund_flow(
                security="aShares",
                start_date="2026-06-29",  # Mon
                end_date="2026-07-01",  # Wed
            )
    assert route.call_count == 3
    body = json.loads(route.calls[0].request.read())
    assert body["limit"] == 10000


@pytest.mark.anyio
async def test_async_fund_flow_ashares_without_dates_rejected(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/fund-flow/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ValidationError, match="requires both start_date and end_date"):
                await AsyncQuote(client).fund_flow(security="aShares")
    assert route.call_count == 0


@pytest.mark.anyio
async def test_async_day_kline_rejects_out_of_range_limit(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            for bad in (0, 10001):
                with pytest.raises(ValidationError, match="between 1 and 10000"):
                    await AsyncQuote(client).day_kline(security="000001.SZ", limit=bad)
    assert route.call_count == 0


@pytest.mark.anyio
async def test_async_minute_kline_rejects_out_of_range_limit(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/minute").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ValidationError, match="between 1 and 10000"):
                await AsyncQuote(client).minute_kline(security="000001.SZ", limit=-5)
    assert route.call_count == 0


@pytest.mark.anyio
async def test_async_day_kline_rejects_non_int_limit(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            for bad in (1.5, True, "10"):
                with pytest.raises(ValidationError, match="integer between 1 and 10000"):
                    await AsyncQuote(client).day_kline(security="000001.SZ", limit=bad)
    assert route.call_count == 0


# ─── v0.4.0 async mirrors (TS v0.37/v0.38) ───


@pytest.mark.anyio
async def test_async_quote_without_a_list_payload_is_refused_with_its_trace(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "traceId": "830965044897325056",
                    "data": None,
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ApiError, match="returned no list payload") as excinfo:
                await AsyncQuote(client).day_kline(security="000001.SH")
    assert excinfo.value.structural is True
    assert excinfo.value.trace_id == "830965044897325056"


@pytest.mark.anyio
async def test_async_realtime_flags_a_field_the_server_never_returned(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "fieldList": ["securityCode", "latestPrice"],
                        "list": [["600519.SH", 1297.41]],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.warns(UserWarning, match="returned no column for turnoverRate"):
                out = await AsyncQuote(client).realtime(
                    security="600519.SH",
                    field=["securityCode", "latestPrice", "turnoverRate"],
                    raw=True,
                )
    assert out["partial"] is True
    assert out["missingFields"] == ["turnoverRate"]


@pytest.mark.anyio
async def test_async_minute_kline_fans_out_over_several_securities(tmp_path):
    def responder(request):
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": "000000",
                "status": True,
                "data": {
                    "total": 1,
                    "fieldList": ["securityCode", "close"],
                    "list": [[body["securityCode"], 1.0]],
                },
            },
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/minute").mock(side_effect=responder)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).minute_kline(security=["600519.SH", "000001.SZ"])
    assert df["securityCode"].tolist() == ["600519.SH", "000001.SZ"]


@pytest.mark.anyio
async def test_async_day_kline_batches_per_security_when_the_range_would_not_fit(tmp_path):
    sent = []

    def responder(request):
        body = json.loads(request.content)
        sent.append(body["securityList"])
        return httpx.Response(
            200,
            json={
                "code": "000000",
                "status": True,
                "data": {
                    "total": 1,
                    "fieldList": ["securityCode", "close"],
                    "list": [[body["securityList"][0], 1.0]],
                },
            },
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).day_kline(
                security=["600519.SH", "000001.SZ", "00700.HK"], limit=100
            )
    assert sorted(sent) == [["000001.SZ"], ["00700.HK"], ["600519.SH"]]
    assert df["securityCode"].tolist() == ["600519.SH", "000001.SZ", "00700.HK"]


@pytest.mark.anyio
async def test_async_minute_kline_requires_a_security(tmp_path):
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        with pytest.raises(ValidationError, match="security is required"):
            await AsyncQuote(client).minute_kline(security=[])


@pytest.mark.anyio
@pytest.mark.parametrize("layout", ["2016-01-01", "2016/01/01", "20160101"])
async def test_async_day_kline_split_decision_does_not_depend_on_date_layout(tmp_path, layout):
    end = layout.replace("2016", "2026")

    def responder(request):
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": "000000",
                "status": True,
                "data": {
                    "total": 1,
                    "fieldList": ["securityCode", "close"],
                    "list": [[body["securityList"][0], 1.0]],
                },
            },
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncQuote(client).day_kline(
                security=["600519.SH", "000001.SZ", "00700.HK"],
                start_date=layout,
                end_date=end,
                limit=5000,
            )
    assert route.call_count == 3
    for call in route.calls:
        body = json.loads(call.request.content)
        assert body["startDate"] == "2016-01-01"
        assert body["endDate"] == "2026-01-01"


@pytest.mark.anyio
async def test_async_minute_kline_warns_when_a_part_reports_itself_partial(tmp_path):
    def responder(request):
        body = json.loads(request.content)
        payload = {
            "total": 1,
            "fieldList": ["securityCode", "close"],
            "list": [[body["securityCode"], 1.0]],
        }
        if body["securityCode"] == "600519.SH":
            payload["partial"] = True
        return httpx.Response(200, json={"code": "000000", "status": True, "data": payload})

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/minute").mock(side_effect=responder)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.warns(UserWarning, match="600519.SH reported itself partial"):
                await AsyncQuote(client).minute_kline(security=["600519.SH", "000001.SZ"])


# ── CLI v0.39.0 - v0.44.0 port (async mirrors; stubs shared with the sync module) ──

from tests.endpoints.test_quote import (  # noqa: E402
    _empty_ok,
    _kline_responder,
    _minute_responder,
    _sent,
    _weekday_strings,
    _window_responder,
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "keyword", "dates"),
    [
        ("day_kline", "aShares", {"start_date": "2026-09-15"}),
        ("day_kline_hk", "all", {"end_date": "2026-09-24"}),
        ("fund_flow", "aShares", {}),
    ],
)
async def test_async_full_market_keyword_requires_both_dates(tmp_path, method, keyword, dates):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.route(method="POST")
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.raises(ValidationError, match="requires both start_date and end_date"):
                await getattr(AsyncQuote(client), method)(security=keyword, **dates)
        assert route.call_count == 0


@pytest.mark.anyio
async def test_async_hk_full_market_shards_two_weekdays_across_the_weekend(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(side_effect=_empty_ok)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncQuote(client).day_kline(
                security="hkStocks", start_date="2026-07-03", end_date="2026-07-08"
            )
    windows = sorted((b["startDate"], b["endDate"]) for b in _sent(route))
    assert windows == [("2026-07-03", "2026-07-06"), ("2026-07-07", "2026-07-08")]


@pytest.mark.anyio
async def test_async_day_kline_skips_shards_before_the_history_window(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            side_effect=_window_responder
        )
        async with AsyncGangtiseClient(
            _config=replace(_cfg(tmp_path), page_concurrency=1)
        ) as client:
            with pytest.warns(
                UserWarning, match=r"lie outside your account's history window \(110003\)"
            ):
                out = await AsyncQuote(client).day_kline(
                    security="aShares", start_date="2015-12-28", end_date="2016-01-08", raw=True
                )
        assert route.call_count == 10
    assert "partial" not in out
    assert len(out["outOfWindowShards"]) == 4
    assert sorted({row[1] for row in out["list"]}) == _weekday_strings("2016-01-01", "2016-01-08")


@pytest.mark.anyio
async def test_async_day_kline_failure_warning_names_the_first_error_and_the_unsent_shards(
    tmp_path,
):
    def responder(request):
        if json.loads(request.content)["startDate"] == "2026-01-06":
            return httpx.Response(
                200, json={"code": "120001", "status": False, "msg": "证券代码无效"}
            )
        return _kline_responder(request)

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        async with AsyncGangtiseClient(
            _config=replace(_cfg(tmp_path), page_concurrency=1)
        ) as client:
            with pytest.warns(UserWarning) as record:
                out = await AsyncQuote(client).day_kline(
                    security="aShares", start_date="2026-01-05", end_date="2026-01-16", raw=True
                )
    messages = [str(w.message) for w in record]
    assert any(
        "not sent: the first error stopped the rest" in m and "(120001)" in m for m in messages
    )
    assert not any("after the requested start" in m for m in messages)
    assert out["partial"] is True


@pytest.mark.anyio
async def test_async_day_kline_names_a_column_only_a_later_shard_returned(tmp_path):
    def responder(request):
        start = json.loads(request.content)["startDate"]
        fields, row = (
            (["close", "volume", "amount"], [20, 200, 2000])
            if start == "2026-04-03"
            else (["close", "volume"], [10, 100])
        )
        return httpx.Response(
            200,
            json={"code": "000000", "status": True, "data": {"fieldList": fields, "list": [row]}},
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.warns(UserWarning, match="came back only in later shards"):
                out = await AsyncQuote(client).day_kline(
                    security="aShares", start_date="2026-04-01", end_date="2026-04-03", raw=True
                )
    assert out["fieldList"] == ["close", "volume"]
    assert out["droppedColumns"] == ["amount"]
    assert out["partial"] is True
    assert len(out["list"]) == 3


@pytest.mark.anyio
async def test_async_identity_columns_for_several_securities(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        daily = router.post("/application/open-quote/kline/daily").mock(
            side_effect=_kline_responder
        )
        minute = router.post("/application/open-quote/kline/minute").mock(side_effect=_empty_ok)
        realtime = router.post("/application/open-quote/quote/realtime").mock(side_effect=_empty_ok)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            quote = AsyncQuote(client)
            with pytest.warns(UserWarning, match="adds securityCode, tradeDate to field"):
                await quote.day_kline(
                    security=["600519.SH", "000858.SZ"],
                    start_date="2026-06-01",
                    end_date="2026-06-05",
                    field="close",
                )
            with pytest.warns(UserWarning, match="adds securityCode, tradeTime to field"):
                await quote.minute_kline(security=["600519.SH", "000858.SZ"], field="close")
            with pytest.warns(UserWarning, match="adds securityCode to field"):
                await quote.realtime(security="aShares", field="latestPrice")
            await quote.realtime(security="600519.SH", field="latestPrice")
    assert _sent(daily)[0]["fieldList"] == ["securityCode", "tradeDate", "close"]
    assert [b["fieldList"] for b in _sent(minute)] == [["securityCode", "tradeTime", "close"]] * 2
    assert [b["fieldList"] for b in _sent(realtime)] == [
        ["securityCode", "latestPrice"],
        ["latestPrice"],
    ]


@pytest.mark.anyio
async def test_async_day_kline_packs_securities_and_keeps_input_order(tmp_path):
    codes = [f"GRP{(i * 7) % 30:02d}.SZ" for i in range(30)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            side_effect=_kline_responder
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            out = await AsyncQuote(client).day_kline(
                security=codes, start_date="2024-01-01", end_date="2026-12-31", raw=True
            )
    assert sorted(len(b["securityList"]) for b in _sent(route)) == [6, 12, 12]
    order = [row[0] for row in out["list"]]
    assert [c for i, c in enumerate(order) if i == 0 or c != order[i - 1]] == codes


@pytest.mark.anyio
async def test_async_day_kline_never_plans_a_request_onto_its_cap(tmp_path):
    codes = [f"GRP{i:02d}.SZ" for i in range(1, 6)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            side_effect=_kline_responder
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            out = await AsyncQuote(client).day_kline(
                security=codes, start_date="2026-06-01", end_date="2026-06-02", limit=10, raw=True
            )
    assert sorted(len(b["securityList"]) for b in _sent(route)) == [1, 4]
    assert len(out["list"]) == 10
    assert "partial" not in out


@pytest.mark.anyio
async def test_async_late_start_and_empty_minute_range_are_noted(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            side_effect=lambda r: _kline_responder(r, first_day="2026-06-03")
        )
        router.post("/application/open-quote/kline/minute").mock(side_effect=_minute_responder)
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            quote = AsyncQuote(client)
            with pytest.warns(
                UserWarning,
                match="starts at 2026-06-03, 33 days after the requested start 2026-05-01",
            ):
                await quote.day_kline(
                    security="600519.SH", start_date="2026-05-01", end_date="2026-06-05"
                )
            with pytest.warns(UserWarning, match="31 days after the requested start 2026-05-01"):
                await quote.minute_kline(
                    security=["600519.SH", "000858.SZ"],
                    start_time="2026-05-01 09:30:00",
                    end_time="2026-06-01 15:00:00",
                    field=["securityCode", "tradeTime", "close"],
                )
            with pytest.warns(UserWarning, match="no minute bars came back"):
                await quote.minute_kline(
                    security="EMPTY.SH",
                    start_time="2026-06-01 09:30:00",
                    end_time="2026-06-01 15:00:00",
                )


@pytest.mark.anyio
async def test_async_repeated_codes_are_sent_once(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        daily = router.post("/application/open-quote/kline/daily").mock(
            side_effect=_kline_responder
        )
        minute = router.post("/application/open-quote/kline/minute").mock(
            side_effect=_minute_responder
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            quote = AsyncQuote(client)
            df = await quote.day_kline(
                security=["600519.SH", "600519.SH"], start_date="2026-06-01", end_date="2026-06-05"
            )
            await quote.minute_kline(security=["600519.SH", "600519.SH"])
    assert _sent(daily)[0]["securityList"] == ["600519.SH"]
    assert len(df) == 5
    assert minute.call_count == 1
