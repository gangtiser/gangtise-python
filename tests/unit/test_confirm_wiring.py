"""Every per-row billed paginated list exposes ``confirm`` and hands it to ``_call``.

The credit guard (TS v0.43.0 / v0.44.0) refuses a fetch estimated above 1000 credits
unless the caller confirms; a wrapper without ``confirm`` would leave the caller no way
through. The pagination layer is stubbed here — what is under test is the wiring from
the wrapper kwarg to ``allow_costly``, for the sync and the async client alike.
"""

from __future__ import annotations

from typing import Any

import pytest

from gangtise_openapi import _client
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._endpoints import ENDPOINTS
from gangtise_openapi.domains.ai import AI, AsyncAI
from gangtise_openapi.domains.insight import AsyncInsight, Insight
from gangtise_openapi.domains.vault import AsyncVault, Vault

_SYNC = {"insight": Insight, "ai": AI, "vault": Vault}
_ASYNC = {"insight": AsyncInsight, "ai": AsyncAI, "vault": AsyncVault}

# (endpoint key, domain, method, the kwargs the method cannot do without)
_CASES: list[tuple[str, str, str, dict[str, Any]]] = [
    ("insight.opinion.list", "insight", "opinion_list", {}),
    ("insight.opinion.list-with-content", "insight", "opinion_list", {"with_content": True}),
    ("insight.foreign-opinion.list", "insight", "foreign_opinion_list", {}),
    (
        "insight.foreign-opinion.list-with-content",
        "insight",
        "foreign_opinion_list",
        {"with_content": True},
    ),
    ("insight.summary.list", "insight", "summary_list", {}),
    ("insight.roadshow.list", "insight", "roadshow_list", {}),
    ("insight.site-visit.list", "insight", "site_visit_list", {}),
    ("insight.strategy.list", "insight", "strategy_list", {}),
    ("insight.forum.list", "insight", "forum_list", {}),
    ("insight.performance-calendar.list", "insight", "performance_calendar_list", {"size": 5}),
    ("insight.research.list", "insight", "research_list", {}),
    ("insight.foreign-report.list", "insight", "foreign_report_list", {}),
    ("insight.announcement.list", "insight", "announcement_list", {}),
    ("insight.announcement-hk.list", "insight", "announcement_hk_list", {}),
    ("insight.announcement-us.list", "insight", "announcement_us_list", {}),
    ("insight.independent-opinion.list", "insight", "independent_opinion_list", {}),
    ("insight.official-account.list", "insight", "official_account_list", {}),
    ("insight.qa.list", "insight", "qa_list", {"security_code": "600519.SH"}),
    ("insight.highlight.list", "insight", "highlight_list", {}),
    (
        "ai.security-clue.list",
        "ai",
        "security_clue_list",
        {
            "start_time": "2026-09-01",
            "end_time": "2026-09-02",
            "query_mode": "bySecurity",
            "gts_code": "600519.SH",
        },
    ),
    ("ai.hot-topic", "ai", "hot_topic", {}),
    ("ai.management-sentiment-indicator", "ai", "management_sentiment_indicator", {}),
    ("ai.management-sentiment-conclusion", "ai", "management_sentiment_conclusion", {}),
    ("vault.my-conference.list", "vault", "my_conference_list", {}),
]


def test_every_per_row_paginated_list_is_covered():
    """Registry-wide: a per-row billed list added to ANY domain must join the cases."""
    billed = {
        key
        for key, ep in ENDPOINTS.items()
        if ep.pagination is not None and ep.billing is not None and ep.billing.per == "row"
    }
    assert billed == {case[0] for case in _CASES}


@pytest.fixture
def captured(monkeypatch) -> list[tuple[str, bool]]:
    seen: list[tuple[str, bool]] = []

    def fake(endpoint, *, allow_costly=False, **_):
        seen.append((endpoint.key, allow_costly))
        return {"total": 0, "list": []}

    async def fake_async(endpoint, *, allow_costly=False, **_):
        seen.append((endpoint.key, allow_costly))
        return {"total": 0, "list": []}

    monkeypatch.setattr(_client, "collect_paginated", fake)
    monkeypatch.setattr(_client, "collect_paginated_async", fake_async)
    return seen


@pytest.mark.parametrize(("key", "domain", "method", "kwargs"), _CASES, ids=[c[0] for c in _CASES])
def test_confirm_reaches_the_credit_guard(seeded_config, captured, key, domain, method, kwargs):
    with GangtiseClient(_config=seeded_config) as client:
        wrapper = getattr(_SYNC[domain](client), method)
        wrapper(**kwargs, raw=True)
        wrapper(**kwargs, confirm=True, raw=True)
    assert captured == [(key, False), (key, True)]


@pytest.mark.anyio
@pytest.mark.parametrize(("key", "domain", "method", "kwargs"), _CASES, ids=[c[0] for c in _CASES])
async def test_async_confirm_reaches_the_credit_guard(
    seeded_config, captured, key, domain, method, kwargs
):
    async with AsyncGangtiseClient(_config=seeded_config) as client:
        wrapper = getattr(_ASYNC[domain](client), method)
        await wrapper(**kwargs, raw=True)
        await wrapper(**kwargs, confirm=True, raw=True)
    assert captured == [(key, False), (key, True)]
