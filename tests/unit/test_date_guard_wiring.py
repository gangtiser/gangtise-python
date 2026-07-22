"""Every wrapper's date / datetime kwargs reach the guard.

The guard lives in one place (``_request_body``), so the risk is not the guard
itself but a wrapper that never calls it. These assert the wiring per domain, and
that the rejection happens BEFORE any HTTP request — no transport is mocked here,
so a wrapper that let the value through would fail with a connection error rather
than ``ValidationError``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gangtise_openapi._errors import ValidationError
from gangtise_openapi.domains.ai import AI, AsyncAI
from gangtise_openapi.domains.alternative import Alternative, AsyncAlternative
from gangtise_openapi.domains.fundamental import AsyncFundamental, Fundamental
from gangtise_openapi.domains.indicator import AsyncIndicator, Indicator
from gangtise_openapi.domains.insight import AsyncInsight, Insight
from gangtise_openapi.domains.quote import AsyncQuote, Quote
from gangtise_openapi.domains.vault import AsyncVault, Vault

# "07/01/2026" is the dangerous one: the server accepts it and reads it as
# 2026-01-07 with a slash but 2026-07-01 with a hyphen, both HTTP 200.
_AMBIGUOUS = "07/01/2026"

_CASES = [
    (
        "fundamental.balance_sheet",
        lambda c: Fundamental(c).balance_sheet(security_code="600519.SH", start_date=_AMBIGUOUS),
    ),
    (
        "fundamental.valuation_analysis",
        lambda c: Fundamental(c).valuation_analysis(
            security_code="600519.SH", indicator="peTtm", end_date=_AMBIGUOUS
        ),
    ),
    ("quote.day_kline", lambda c: Quote(c).day_kline(security="600519.SH", start_date=_AMBIGUOUS)),
    (
        "quote.minute_kline",
        lambda c: Quote(c).minute_kline(security="600519.SH", start_time=_AMBIGUOUS),
    ),
    ("ai.hot_topic", lambda c: AI(c).hot_topic(start_date=_AMBIGUOUS)),
    ("ai.theme_tracking", lambda c: AI(c).theme_tracking(theme_id="1", date=_AMBIGUOUS)),
    (
        "ai.management_discuss_announcement",
        lambda c: AI(c).management_discuss_announcement(
            report_date=_AMBIGUOUS, security_code="000001.SZ", dimension="all"
        ),
    ),
    (
        "ai.security_clue_list",
        lambda c: AI(c).security_clue_list(
            start_time=_AMBIGUOUS, end_time="2026-07-02", query_mode="bySecurity"
        ),
    ),
    ("insight.research_list", lambda c: Insight(c).research_list(start_time=_AMBIGUOUS)),
    ("insight.announcement_list", lambda c: Insight(c).announcement_list(start_time=_AMBIGUOUS)),
    (
        "alternative.edb_data",
        lambda c: Alternative(c).edb_data(
            indicator_id="1", start_date=_AMBIGUOUS, end_date="2026-07-02"
        ),
    ),
    (
        "indicator.cross_section",
        lambda c: Indicator(c).cross_section(
            date=_AMBIGUOUS, indicator="qte_close", security="600519.SH"
        ),
    ),
    (
        "indicator.time_series",
        lambda c: Indicator(c).time_series(
            start_date=_AMBIGUOUS,
            end_date="2026-07-02",
            indicator="qte_close",
            security="600519.SH",
        ),
    ),
    ("vault.drive_list", lambda c: Vault(c).drive_list(start_time=_AMBIGUOUS)),
]


@pytest.mark.parametrize(("name", "call"), _CASES, ids=[c[0] for c in _CASES])
def test_wrapper_rejects_ambiguous_date(name, call):
    client = MagicMock()
    client._call.side_effect = AssertionError(f"{name} issued a request with {_AMBIGUOUS!r}")
    with pytest.raises(ValidationError):
        call(client)
    client._call.assert_not_called()


# ── async mirrors: the guard must not be sync-only ──

_ASYNC_CASES = [
    (
        "fundamental.balance_sheet",
        lambda c: AsyncFundamental(c).balance_sheet(
            security_code="600519.SH", start_date=_AMBIGUOUS
        ),
    ),
    (
        "quote.day_kline",
        lambda c: AsyncQuote(c).day_kline(security="600519.SH", start_date=_AMBIGUOUS),
    ),
    (
        "quote.minute_kline",
        lambda c: AsyncQuote(c).minute_kline(security="600519.SH", start_time=_AMBIGUOUS),
    ),
    ("ai.theme_tracking", lambda c: AsyncAI(c).theme_tracking(theme_id="1", date=_AMBIGUOUS)),
    (
        "ai.management_discuss_announcement",
        lambda c: AsyncAI(c).management_discuss_announcement(
            report_date=_AMBIGUOUS, security_code="000001.SZ", dimension="all"
        ),
    ),
    ("insight.research_list", lambda c: AsyncInsight(c).research_list(start_time=_AMBIGUOUS)),
    (
        "insight.announcement_list",
        lambda c: AsyncInsight(c).announcement_list(start_time=_AMBIGUOUS),
    ),
    (
        "indicator.cross_section",
        lambda c: AsyncIndicator(c).cross_section(
            date=_AMBIGUOUS, indicator="qte_close", security="600519.SH"
        ),
    ),
    (
        "alternative.edb_data",
        lambda c: AsyncAlternative(c).edb_data(
            indicator_id="1", start_date=_AMBIGUOUS, end_date="2026-07-02"
        ),
    ),
    ("vault.drive_list", lambda c: AsyncVault(c).drive_list(start_time=_AMBIGUOUS)),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("name", "call"), _ASYNC_CASES, ids=[c[0] for c in _ASYNC_CASES])
async def test_async_wrapper_rejects_ambiguous_date(name, call):
    client = MagicMock()
    client._call = AsyncMock(
        side_effect=AssertionError(f"{name} issued a request with {_AMBIGUOUS!r}")
    )
    with pytest.raises(ValidationError):
        await call(client)
    client._call.assert_not_awaited()


# ── Paths that parse the date locally BEFORE building the body ──
# These reach ``datetime.fromisoformat`` first, so without their own guard the user
# gets a bare ValueError instead of the ValidationError explaining WHY the layout
# is refused.


def test_earning_forecast_bad_end_date_raises_validation_error():
    # end_date is consumed locally (it anchors the default start_date) before the
    # body is built.
    client = MagicMock()
    with pytest.raises(ValidationError):
        Fundamental(client).earning_forecast(security_code="600519.SH", end_date=_AMBIGUOUS)
    client._call.assert_not_called()


def test_all_market_kline_bad_date_raises_validation_error():
    # The all-market sharding planner parses both dates to build day windows.
    client = MagicMock()
    with pytest.raises(ValidationError):
        Quote(client).day_kline(security="all", start_date=_AMBIGUOUS, end_date="2026-07-02")
    client._call.assert_not_called()
