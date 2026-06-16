from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError
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
                security="all",
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
async def test_async_day_kline_partial_shard_failure_sets_flags(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(
            side_effect=_partial_failure_responder
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            with pytest.warns(UserWarning, match="1/3 kline shards failed"):
                out = await AsyncQuote(client).day_kline(
                    security="all",
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
                    security="all",
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
async def test_async_index_day_kline_30_day_shards_and_body(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/index/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncQuote(client).index_day_kline(
                security="all",
                start_date="2026-01-01",
                end_date="2026-03-31",
            )
        # 90 days / 30 per shard = 3 shards
        assert route.call_count == 3
        # index-day-kline body uses `securityList` (camelCase, list form)
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"securityList":["all"]' in sent
        assert b'"securityCode"' not in sent


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
                    "data": [{"securityCode": "000001.SH", "price": 12.34}],
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).realtime(security=["000001.SH"])
    assert df.iloc[0]["price"] == 12.34
