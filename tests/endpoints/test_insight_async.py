from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.insight import AsyncInsight


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        page_concurrency=3,
    )


def _row_response(row: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"total": 1, "list": [row]},
        },
    )


@pytest.mark.anyio
async def test_async_opinion_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/chief-opinion/getList").mock(
            return_value=_row_response(
                {"id": "1", "title": "x", "broker": "A", "chief": "B"},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncInsight(client).opinion_list(industry=1)
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "1"


@pytest.mark.anyio
async def test_async_announcement_list_scales_seconds_int_to_ms(tmp_path):
    # TS toTimestamp13 parity: a seconds-level int is scaled to milliseconds.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-insight/announcement/getList").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"total": 0, "list": []}},
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            await AsyncInsight(client).announcement_list(start_time=1767225600)
    sent = route.calls.last.request.read()
    assert b'"startTime":1767225600000' in sent.replace(b" ", b"")


@pytest.mark.anyio
async def test_async_research_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200,
                content=b"data",
                headers={"content-disposition": 'attachment; filename="file.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            path = await AsyncInsight(client).research_download(
                report_id="r1",
                output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"data"
