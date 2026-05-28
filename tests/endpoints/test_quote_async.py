from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.quote import AsyncQuote


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        page_concurrency=2,
    )


@pytest.mark.anyio
async def test_async_day_kline_single_security(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {"list": [
                        {"securityCode": "000001.SH", "date": "2026-01-02", "close": 12.3},
                    ]},
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
                200, json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncQuote(client).day_kline_us(
                security="all", start_date="2026-01-01", end_date="2026-01-03",
            )
        # 1-day shards x 3 days
        assert route.call_count == 3


@pytest.mark.anyio
async def test_async_realtime(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": [{"securityCode": "000001.SH", "price": 12.34}],
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncQuote(client).realtime(security=["000001.SH"])
    assert df.iloc[0]["price"] == 12.34
