from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.reference import AsyncReference


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


@pytest.mark.anyio
async def test_async_securities_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-reference/securities/search").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {"list": [
                        {"code": "000001.SZ", "name": "平安银行"},
                    ]},
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncReference(client).securities_search(keyword="平安")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["code"] == "000001.SZ"
