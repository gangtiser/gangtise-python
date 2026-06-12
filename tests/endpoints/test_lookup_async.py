from __future__ import annotations

import pandas as pd
import pytest

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.lookup import AsyncLookup


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
async def test_async_broker_orgs_returns_dataframe(tmp_path):
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        df = await AsyncLookup(client).broker_orgs()
    assert isinstance(df, pd.DataFrame)
    assert {"id", "name"}.issubset(df.columns)
    assert len(df) > 0


@pytest.mark.anyio
async def test_async_broker_orgs_raw_returns_list(tmp_path):
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        rows = await AsyncLookup(client).broker_orgs(raw=True)
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)


@pytest.mark.anyio
async def test_async_meeting_orgs_returns_dataframe(tmp_path):
    async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
        df = await AsyncLookup(client).meeting_orgs()
    assert isinstance(df, pd.DataFrame)
    assert {"id", "name"}.issubset(df.columns)
    assert len(df) > 0
