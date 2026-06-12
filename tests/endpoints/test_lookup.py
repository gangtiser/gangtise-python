import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.lookup import Lookup


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_broker_orgs_returns_dataframe(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:
        df = Lookup(client).broker_orgs()
    assert isinstance(df, pd.DataFrame)
    assert {"id", "name"}.issubset(df.columns)
    assert len(df) > 0


def test_broker_orgs_raw_returns_list(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:
        rows = Lookup(client).broker_orgs(raw=True)
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)


def test_meeting_orgs_returns_dataframe(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:
        df = Lookup(client).meeting_orgs()
    assert isinstance(df, pd.DataFrame)
    assert {"id", "name"}.issubset(df.columns)
    assert len(df) > 0


def test_retired_lookups_removed(tmp_path):
    # v0.16.0: API-covered tables moved to reference.* — wrappers must be gone.
    with GangtiseClient(_config=_cfg(tmp_path)) as client:
        lookup = Lookup(client)
    for retired in (
        "research_areas",
        "industries",
        "regions",
        "announcement_categories",
        "industry_codes",
        "theme_ids",
    ):
        assert not hasattr(lookup, retired), retired
