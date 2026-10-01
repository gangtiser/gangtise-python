"""Live integration tests. Run with `pytest -m live`.

Required env vars: GANGTISE_ACCESS_KEY, GANGTISE_SECRET_KEY (or a valid GANGTISE_TOKEN).
Skipped by default. CI never runs these.
"""

from __future__ import annotations

import datetime as dt
import os
import warnings
from collections.abc import Iterator

import pandas as pd
import pytest

from gangtise_openapi import GangtiseClient

pytestmark = pytest.mark.live


def _last_weekday() -> dt.date:
    """Most recent Mon-Fri STRICTLY BEFORE today. Not a trading calendar — holidays
    still land empty — but it keeps a weekend run from probing a guaranteed-empty day
    and reading it as a regression.

    🔴 Excludes today on purpose. Daily bars for the current session are not published
    until after the close, so a weekday run before then got zero rows from a perfectly
    healthy endpoint — `hkStocks` returned 0 rows for the current day and 2811 for the
    previous one. Yesterday is always settled; today is only sometimes."""
    day = dt.date.today() - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


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

    # A result that fills `limit` is flagged partial (0.5.0) — the
    # series is one row per calendar day and the API keeps the most recent rows, so
    # five rows with no start date are the tail of a longer series.
    with pytest.warns(UserWarning, match="5-row limit"):
        df = Fundamental(client).valuation_analysis(
            security_code="000001.SZ", indicator="peTtm", limit=5
        )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5


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


def test_live_indicator_cross_section_key_by_code(client: GangtiseClient) -> None:
    """key_by='code' must key columns by the code the caller passed in.

    Load-bearing and only checkable live: the flattener reads `indicatorList` as
    the column axis of a [security][indicator] matrix. The server does NOT
    preserve the requested order (probed 2026-07-24: asking for [cf_finc_exp,
    cf_finc_exp_qtr] returns [cf_finc_exp_qtr, cf_finc_exp]), so a positional read
    would silently mismatch. This also pins the 2026-08-01 contract: `universe`
    instead of `securityCodeList`, a structured `indicatorList` instead of the two
    parallel arrays, and a TRANSPOSED values matrix.
    EDE bills per cell, 100-cell minimum — keep the matrix tiny.
    """
    from gangtise_openapi.domains.indicator import Indicator

    codes = ["cf_finc_exp", "cf_finc_exp_qtr"]
    ind = Indicator(client)
    # These are report-period indicators: they reject tradeDate since 2026-08-14,
    # so the query date has to travel as each indicator's own reportDate.
    params = {code: {"reportDate": "2025-12-31"} for code in codes}
    raw = ind.cross_section(
        date="2025-12-31",
        indicator=codes,
        security="600519.SH",
        indicator_param=params,
        raw=True,
    )
    inner = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
    assert isinstance(inner, dict)
    assert "indicatorCodeList" not in inner, "server reverted to the pre-08-01 shape"
    returned = [meta["code"] for meta in inner["indicatorList"]]
    values = inner["values"]
    assert sorted(returned) == sorted(codes)

    df = ind.cross_section(
        date="2025-12-31",
        indicator=codes,
        security="600519.SH",
        indicator_param=params,
        key_by="code",
    )
    assert isinstance(df, pd.DataFrame)
    assert set(codes) <= set(df.columns), f"expected code columns, got {list(df.columns)}"
    # Cross-section is [security][indicator]: row 0 is 600519.SH across the columns.
    for j, code in enumerate(returned):
        assert df.iloc[0][code] == values[0][j] or (
            pd.isna(df.iloc[0][code]) and values[0][j] is None
        )


def test_live_indicator_time_series_key_by_code_multi_security(client: GangtiseClient) -> None:
    # Single-indicator x multi-security branch: columns become securityCode.
    from gangtise_openapi.domains.indicator import Indicator

    end = dt.date.today()
    start = end - dt.timedelta(days=7)
    securities = ["600519.SH", "000001.SZ"]
    df = Indicator(client).time_series(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        indicator="qte_close",
        security=securities,
        key_by="code",
    )
    assert isinstance(df, pd.DataFrame)
    assert set(securities) <= set(df.columns), f"expected code columns, got {list(df.columns)}"


def test_live_indicator_screener_bindings(client: GangtiseClient) -> None:
    """The screener answers with the variable each column was bound to.

    That `field` is the ONLY thing tying a column back to the filter it came from,
    and nothing in the payload can catch it going wrong — a swapped binding prints
    a perfectly ordinary table. `check_screener_bindings` is therefore load-bearing
    and only verifiable live. Same billing shape as the cross-section test (EDE
    bills per cell, 100-cell minimum), so keep the universe to one security.
    """
    from gangtise_openapi.domains.indicator import Indicator

    raw = Indicator(client).screener(
        date=_last_weekday().isoformat(),
        expression="F1 > 0",
        indicator={"F1": "qte_close"},
        security="600519.SH",
        raw=True,
    )
    inner = raw.get("data") if isinstance(raw, dict) and "data" in raw else raw
    assert isinstance(inner, dict)
    # Every returned column names the variable it was requested under.
    assert [meta.get("field") for meta in inner["indicatorList"]] == ["F1"]
    assert [meta.get("code") for meta in inner["indicatorList"]] == ["qte_close"]


def test_live_quote_day_kline_market_keyword_replaced_all(client: GangtiseClient) -> None:
    """`all` is gone on the unified day-kline; the market keywords replaced it.

    The server answers `120001 invalid security code` for BOTH the retired keyword
    and a keyword mixed with codes, which points at codes that are perfectly fine —
    so the SDK refuses locally. This pins that the LOCAL rule still matches the
    server: one trading day of hkStocks is the cheapest whole-market probe (~2810
    rows, free endpoint).
    """
    from gangtise_openapi._errors import ValidationError
    from gangtise_openapi.domains.quote import Quote

    quote = Quote(client)
    with pytest.raises(ValidationError, match="aShares"):
        quote.day_kline(security="all", start_date="2026-01-05", end_date="2026-01-05")
    with pytest.raises(ValidationError, match="alone"):
        quote.day_kline(security=["hkStocks", "00700.HK"])

    day = _last_weekday()
    df = quote.day_kline(security="hkStocks", start_date=day.isoformat(), end_date=day.isoformat())
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0, "hkStocks whole-market day returned nothing"


def test_live_indicator_search_no_ede_fetch_hint(client: GangtiseClient) -> None:
    # search is free and takes only a keyword; it must not carry the fetch hint's
    # date/scope/param guidance. Also confirms the fields the hint points at exist.
    from gangtise_openapi.domains.indicator import Indicator

    df = Indicator(client).search(keyword="财务费用", limit=5)
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    assert {"indicatorCode", "scopeList", "parameterList"} <= set(df.columns)


@pytest.mark.filterwarnings("default::UserWarning")
def test_live_quote_full_market_shards_merge_cleanly(client: GangtiseClient) -> None:
    """Free endpoint. A whole-market range across several trading days goes out as one
    shard per weekday (A-shares) and comes back merged: every trading day present, each
    security once per day, no shard failed or truncated, nothing flagged partial.

    The window is the last five trading days of the Shanghai Composite (000001.SH): an
    index is never suspended, a holiday is simply not in it, and a day whose shard came
    back silently empty shows up as missing. Thirty calendar days always hold more than
    five sessions, so an empty answer there is a fault, not a holiday."""
    from gangtise_openapi.domains.quote import Quote

    quote = Quote(client)
    end = _last_weekday()
    reference = quote.day_kline(
        security="000001.SH",
        start_date=(end - dt.timedelta(days=30)).isoformat(),
        end_date=end.isoformat(),
        raw=True,
    )
    sessions = sorted(
        set(pd.DataFrame(reference["list"], columns=reference["fieldList"])["tradeDate"])
    )
    assert len(sessions) >= 5, f"index calendar returned {sessions}"
    trading_days = set(sessions[-5:])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raw = quote.day_kline(
            security="aShares", start_date=sessions[-5], end_date=sessions[-1], raw=True
        )
    notes = [str(w.message)[:200] for w in caught]
    assert isinstance(raw, dict)
    markers = ("partial", "failedShards", "truncatedShards", "droppedColumns")
    flagged = {marker: raw[marker] for marker in markers if marker in raw}
    assert not flagged, f"{flagged}; warnings: {notes}"
    df = pd.DataFrame(raw["list"], columns=raw["fieldList"])
    assert not df.duplicated(["securityCode", "tradeDate"]).any()
    per_day = df.groupby("tradeDate").size()
    assert set(per_day.index) == trading_days, f"got {sorted(per_day.index)}"
    assert (per_day > 4000).all(), per_day.to_dict()
    assert raw["total"] == len(df)
