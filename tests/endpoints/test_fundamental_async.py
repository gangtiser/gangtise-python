from __future__ import annotations

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
