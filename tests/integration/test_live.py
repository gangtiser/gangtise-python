"""Live integration tests. Run with `pytest -m live`.

Required env vars: GANGTISE_ACCESS_KEY, GANGTISE_SECRET_KEY (or a valid GANGTISE_TOKEN).
Skipped by default. CI never runs these.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterator

import pandas as pd
import pytest

from gangtise_openapi import GangtiseClient

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client() -> Iterator[GangtiseClient]:
    if not (os.environ.get("GANGTISE_ACCESS_KEY") or os.environ.get("GANGTISE_TOKEN")):
        pytest.skip("no live credentials configured")
    with GangtiseClient() as c:
        yield c


def test_live_login(client: GangtiseClient) -> None:
    result = client.login()
    assert result["authorization"].startswith("Bearer ")


def test_live_lookup_broker_orgs(client: GangtiseClient) -> None:
    from gangtise_openapi.domains.lookup import Lookup

    df = Lookup(client).broker_orgs()
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_live_reference_constant_list(client: GangtiseClient) -> None:
    # domesticCity, not citicIndustry: as of 2026-06-12 the industry categories
    # return constants=null server-side (npm CLI shows the same), while
    # domesticCity/regionCategory have data.
    from gangtise_openapi.domains.reference import Reference

    df = Reference(client).constant_list(category="domesticCity")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert "constantId" in df.columns


def test_live_quote_realtime(client: GangtiseClient) -> None:
    from gangtise_openapi.domains.quote import Quote

    df = Quote(client).realtime(security=["000001.SH"])
    assert isinstance(df, pd.DataFrame)


def test_live_quote_day_kline_single_security(client: GangtiseClient) -> None:
    # Single security + narrow window: must NOT trigger all-market sharding.
    from gangtise_openapi.domains.quote import Quote

    end = dt.date.today()
    start = end - dt.timedelta(days=14)
    df = Quote(client).day_kline(security="000001.SZ", start_date=start, end_date=end)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_live_fundamental_valuation_analysis(client: GangtiseClient) -> None:
    from gangtise_openapi.domains.fundamental import Fundamental

    df = Fundamental(client).valuation_analysis(
        security_code="000001.SZ", indicator="peTtm", limit=5
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_live_insight_research_list_small_page(client: GangtiseClient) -> None:
    # Paginated endpoint: size=5 stops after a small first page; also feeds the title cache.
    from gangtise_openapi.domains.insight import Insight

    df = Insight(client).research_list(size=5)
    assert isinstance(df, pd.DataFrame)
    assert 0 < len(df) <= 5


def test_live_alternative_concept_info(client: GangtiseClient) -> None:
    # conceptId discovery moved from the retired theme-ids local table to
    # reference.concept-search (v0.16.0).
    from gangtise_openapi.domains.alternative import Alternative
    from gangtise_openapi.domains.reference import Reference

    concepts = Reference(client).concept_search(keyword="机器人", top=1, raw=True)
    assert isinstance(concepts, dict)
    rows = concepts.get("list") or []
    assert rows, "concept-search returned no rows"
    info = Alternative(client).concept_info(concept_id=rows[0]["conceptId"])
    assert isinstance(info, dict)
    assert info
