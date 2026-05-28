import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.alternative import Alternative


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_edb_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-alternative/EDB/search").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {"list": [
                        {"indicatorId": "I001", "indicatorName": "空调销量"},
                    ]},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Alternative(client).edb_search(keyword="空调")
        sent = route.calls.last.request.read().replace(b" ", b"")
        assert b'"keyword":' in sent
        assert b'"limit":100' in sent
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["indicatorId"] == "I001"


def test_edb_data_transposes_matrix(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-alternative/EDB/getData").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {
                        "fieldList": ["date", "indicatorId", "value"],
                        "dataList": [
                            ["2026-01-01", "I001", 100.0],
                            ["2026-01-02", "I001", 102.5],
                            ["2026-01-03", "I001", 99.8],
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Alternative(client).edb_data(
                indicator_id="I001",
                start_date="2026-01-01",
                end_date="2026-01-03",
            )
    # Transposed: each row is a dict with the fieldList keys
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["date", "indicatorId", "value"]
    assert len(df) == 3
    assert df.iloc[1]["value"] == 102.5
