"""Live integration tests. Run with `pytest -m live`.

Required env vars: GANGTISE_ACCESS_KEY, GANGTISE_SECRET_KEY (or a valid GANGTISE_TOKEN).
Skipped by default. CI never runs these.
"""

from __future__ import annotations

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


def test_live_lookup_research_areas(client: GangtiseClient) -> None:
    from gangtise_openapi.domains.lookup import Lookup

    df = Lookup(client).research_areas()
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_live_quote_realtime(client: GangtiseClient) -> None:
    from gangtise_openapi.domains.quote import Quote

    df = Quote(client).realtime(security=["000001.SH"])
    assert isinstance(df, pd.DataFrame)
