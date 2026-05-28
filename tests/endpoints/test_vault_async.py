from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.vault import AsyncVault


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


@pytest.mark.anyio
async def test_async_drive_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-vault/drive/getList").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"id": "f1", "name": "doc.pdf"}],
                    },
                },
            )
        )
        async with AsyncGangtiseClient(_config=_cfg(tmp_path)) as client:
            df = await AsyncVault(client).drive_list(keyword="doc")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "f1"


@pytest.mark.anyio
async def test_async_drive_download_writes_file(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-vault/drive/download/file").mock(
            return_value=httpx.Response(
                200, content=b"file",
                headers={"content-disposition": 'attachment; filename="f.pdf"'},
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            path = await AsyncVault(client).drive_download(
                file_id="f1", output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"file"
