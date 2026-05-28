import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.reference import Reference


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_securities_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-reference/securities/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": [
                        {"code": "000001.SH", "name": "上证指数", "market": "SH"},
                    ],
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).securities_search(keyword="上证")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["code"] == "000001.SH"
