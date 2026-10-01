"""Live checks for the endpoints and guards 0.5.0 added (CLI v0.39.0-v0.44.0).

Run with `pytest -m live`. Read-only and cheap by design — each test states what it
costs (the platform's published prices; the SDK cannot measure billing). Nothing here
writes account data: the stock-pool / drive writes are covered offline only.
Estimated total: about 45 credits plus `valuation_analysis` (no published price).
"""

from __future__ import annotations

import datetime as dt
import os
import warnings
from collections.abc import Iterator

import pandas as pd
import pytest

from gangtise_openapi import GangtiseClient
from gangtise_openapi._errors import ValidationError
from gangtise_openapi.domains import Bond, Fund, Fundamental, Insight, Tool, Vault

# A live answer may legitimately warn (a late first row, a missing body); each test
# asserts what it is about instead of letting pyproject's error::UserWarning fail it.
pytestmark = [pytest.mark.live, pytest.mark.filterwarnings("default::UserWarning")]


@pytest.fixture(scope="module")
def client() -> Iterator[GangtiseClient]:
    if not (os.environ.get("GANGTISE_ACCESS_KEY") or os.environ.get("GANGTISE_TOKEN")):
        pytest.skip("no live credentials configured")
    with GangtiseClient() as c:
        yield c


def _recent(days: int) -> tuple[str, str]:
    end = dt.date.today() - dt.timedelta(days=1)
    return (end - dt.timedelta(days=days)).isoformat(), end.isoformat()


def test_live_fund_nav_and_basic_info(client: GangtiseClient) -> None:
    """0.4 credits each. `expects="list"` holds on the live answer and rows come back."""
    start, end = _recent(14)
    nav = Fund(client).nav(security="510300.SH", start_date=start, end_date=end)
    assert isinstance(nav, pd.DataFrame)
    assert len(nav) > 0
    info = Fund(client).basic_info(security="005827.OF", raw=True)
    assert isinstance(info, dict) and isinstance(info.get("list"), list)
    assert len(info["list"]) == 1


def test_live_fund_unknown_code_is_empty_not_an_error(client: GangtiseClient) -> None:
    """0.4 credits (an empty result is not billed per the price list). The docstrings
    promise a lowercase suffix answers EMPTY without an error — pin it."""
    out = Fund(client).basic_info(security="005827.of", raw=True)
    assert out.get("list") == []


def test_live_bond_basic_info_is_columnar_and_flattened(client: GangtiseClient) -> None:
    """0.4 credits. Bond answers are columnar; the default frame is flattened."""
    df = Bond(client).basic_info(security="019742.SH")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1


def test_live_opinion_list_v2_brief_and_detail(client: GangtiseClient) -> None:
    """1 credit (one v2 row) + at most 30 credits (one body — an opinion without a body
    is not billed). v2 rows carry `brief`; the body endpoint answers a bare array
    (`expects="array"`), and a missing body comes back as `missingIds`, not an error."""
    listing = Insight(client).opinion_list(size=1, raw=True)
    rows = listing["list"]
    assert rows, "no opinion in the default window"
    assert "brief" in rows[0]
    opinion_id = str(rows[0]["chiefOpinionId"])
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        detail = Insight(client).opinion_detail(chief_opinion_id=opinion_id, raw=True)
    bodies = detail if isinstance(detail, list) else detail.get("list", [])
    if not bodies:
        assert isinstance(detail, dict) and detail.get("missingIds") == [opinion_id]


def test_live_highlight_list_one_row(client: GangtiseClient) -> None:
    """5 credits (one row)."""
    out = Insight(client).highlight_list(size=1, raw=True)
    assert isinstance(out.get("list"), list)


def test_live_web_search_one_result(client: GangtiseClient) -> None:
    """1 credit."""
    out = Tool(client).web_search(query="贵州茅台 三季报", size=1, raw=True)
    assert isinstance(out.get("list"), list)


def test_live_drive_folder_list_is_free_and_answers(client: GangtiseClient) -> None:
    """Free."""
    out = Vault(client).drive_folder_list(space_type=1)
    assert isinstance(out, dict)


def test_live_valuation_analysis_shape(client: GangtiseClient) -> None:
    """No published price. `expects="list"` was added on the CLI's 2026-09-24 probe of
    this endpoint; pin that the live answer is `{indicator, fieldList, list}`."""
    start, end = _recent(10)
    out = Fundamental(client).valuation_analysis(
        security_code="600519.SH", indicator="peTtm", start_date=start, end_date=end, raw=True
    )
    assert isinstance(out.get("list"), list)
    assert isinstance(out.get("fieldList"), list)


def test_live_credit_guard_refuses_a_whole_table_fetch(client: GangtiseClient) -> None:
    """About 5 credits: a 1-row look at `total` (0.1), then the first page (50 x 0.1)
    that the guard prices from. Only run when the full fetch is really past 1000
    credits — otherwise a size-less call would legitimately fetch everything."""
    total = Insight(client).research_list(size=1, raw=True)["total"]
    if total * 0.1 <= 1000:
        pytest.skip(f"only {total} research rows: too few to exercise the guard safely")
    with pytest.raises(ValidationError, match="1000-credit guard"):
        Insight(client).research_list()
