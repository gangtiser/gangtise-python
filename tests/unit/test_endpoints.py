import pytest

from gangtise_openapi._endpoints import ENDPOINTS, EndpointDef, lookup


def test_endpoint_count():
    assert len(ENDPOINTS) == 92


def test_lookup_known_endpoint():
    ep = lookup("quote.day-kline")
    assert ep.key == "quote.day-kline"
    assert ep.method == "POST"
    assert ep.path == "/application/open-quote/kline/daily"
    assert ep.kind == "json"


def test_lookup_unknown_raises():
    with pytest.raises(KeyError):
        lookup("does.not.exist")


def test_pagination_registry_matches_ts_source():
    # Translated 1:1 from gangtise-openapi-cli/src/core/endpoints.ts.
    # max_page_size differs per endpoint — do NOT assume "all 50".
    expected: dict[str, int] = {
        "insight.opinion.list": 50,
        "insight.summary.list": 50,
        "insight.roadshow.list": 50,
        "insight.site-visit.list": 50,
        "insight.strategy.list": 50,
        "insight.forum.list": 50,
        "insight.research.list": 50,
        "insight.foreign-report.list": 50,
        "insight.announcement.list": 50,
        "insight.announcement-hk.list": 50,
        "insight.announcement-us.list": 50,
        "insight.foreign-opinion.list": 50,
        "insight.independent-opinion.list": 50,
        "insight.official-account.list": 50,
        "insight.qa.list": 500,
        "ai.security-clue.list": 500,
        "ai.hot-topic": 20,
        "vault.drive.list": 50,
        "vault.record.list": 50,
        "vault.my-conference.list": 50,
        "vault.wechat-message.list": 50,
        "vault.wechat-chatroom.list": 50,
    }
    actual = {
        k: ep.pagination.max_page_size for k, ep in ENDPOINTS.items() if ep.pagination is not None
    }
    assert actual == expected
    # v0.23.0: wechat-chatroom now returns {total, list} and paginates like any other
    # total-driven endpoint (the sequential/list_key mechanism was removed).
    chatroom = ENDPOINTS["vault.wechat-chatroom.list"].pagination
    assert chatroom is not None
    assert chatroom.max_page_size == 50


def test_download_endpoints_have_kind_download():
    download_keys = [k for k, ep in ENDPOINTS.items() if ep.kind == "download"]
    assert "insight.summary.download" in download_keys
    assert "insight.research.download" in download_keys
    for key in download_keys:
        assert ENDPOINTS[key].method in {"GET", "POST"}


def test_local_lookup_endpoints_marked():
    # v0.16.0: only the two API-uncovered local tables remain.
    lookup_keys = sorted(k for k in ENDPOINTS if k.startswith("lookup."))
    assert lookup_keys == [
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
    ]
    for key in lookup_keys:
        assert ENDPOINTS[key].path.startswith("/guide/")


def test_reference_constant_concept_sector_endpoints():
    # Translated 1:1 from gangtise-openapi-cli v0.16.0 endpoints.ts.
    category = ENDPOINTS["reference.constant-category"]
    assert category.method == "GET"
    assert category.path == "/application/open-reference/constants/category"
    assert category.kind == "json"

    constants = ENDPOINTS["reference.constant-list"]
    assert constants.method == "POST"
    assert constants.path == "/application/open-reference/constants/getList"

    concepts = ENDPOINTS["reference.concept-search"]
    assert concepts.method == "POST"
    assert concepts.path == "/application/open-reference/concepts/search"

    sectors = ENDPOINTS["reference.sector-search"]
    assert sectors.method == "POST"
    assert sectors.path == "/application/open-reference/sectors/search"

    constituents = ENDPOINTS["reference.sector-constituents"]
    assert constituents.method == "POST"
    assert constituents.path == "/application/open-reference/sectors/constituents"


def test_dataclass_equality():
    a = EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")
    b = EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")
    assert a == b


def test_retry_policy_registry_matches_ts_source():
    # Translated 1:1 from gangtise-openapi-cli v0.26.0/v0.27.0 endpoints.ts.
    # These annotations are billing-safety-critical — a drifted entry either
    # double-bills (missing no-replay) or degrades reliability (spurious one).
    expected_no_replay = {
        "insight.summary.download",
        "insight.foreign-report.download",
        "ai.knowledge-batch",
        "ai.one-pager",
        "ai.investment-logic",
        "ai.peer-comparison",
        "ai.earnings-review.get-id",
        "ai.theme-tracking",
        "ai.research-outline",
        "ai.hot-topic",
        "ai.management-discuss-announcement",
        "ai.management-discuss-earnings-call",
        "ai.viewpoint-debate.get-id",
        "vault.my-conference.download",
        "alternative.concept-info",
        "alternative.concept-securities",
    }
    expected_no_999999 = {
        "indicator.search",
        "indicator.cross-section",
        "indicator.time-series",
    }
    assert {k for k, ep in ENDPOINTS.items() if ep.retry == "no-replay"} == expected_no_replay
    assert {k for k, ep in ENDPOINTS.items() if ep.retry == "no-999999"} == expected_no_999999


def test_timeout_floor_registry_matches_ts_source():
    # The 7 synchronous AI generation endpoints get a 120s floor (TS v0.24.0).
    expected = {
        "ai.one-pager",
        "ai.investment-logic",
        "ai.peer-comparison",
        "ai.theme-tracking",
        "ai.research-outline",
        "ai.management-discuss-announcement",
        "ai.management-discuss-earnings-call",
    }
    floors = {k: ep.timeout_ms for k, ep in ENDPOINTS.items() if ep.timeout_ms is not None}
    assert set(floors) == expected
    assert all(v == 120_000 for v in floors.values())


def test_all_endpoint_keys_match_ts_source():
    expected = {
        "auth.login",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "insight.opinion.list",
        "insight.summary.list",
        "insight.summary.download",
        "insight.roadshow.list",
        "insight.site-visit.list",
        "insight.strategy.list",
        "insight.forum.list",
        "insight.research.list",
        "insight.research.download",
        "insight.foreign-report.list",
        "insight.foreign-report.download",
        "insight.announcement.list",
        "insight.announcement.download",
        "insight.announcement-hk.list",
        "insight.announcement-hk.download",
        "insight.announcement-us.list",
        "insight.announcement-us.download",
        "insight.foreign-opinion.list",
        "insight.independent-opinion.list",
        "insight.independent-opinion.download",
        "insight.official-account.list",
        "insight.official-account.download",
        "insight.qa.list",
        "insight.report-image.list",
        "insight.report-image.download",
        "reference.securities-search",
        "reference.chiefs-search",
        "reference.institution-search",
        "reference.official-account-search",
        "reference.constant-category",
        "reference.constant-list",
        "reference.concept-search",
        "reference.sector-search",
        "reference.sector-constituents",
        "quote.day-kline",
        "quote.day-kline-hk",
        "quote.day-kline-us",
        "quote.index-day-kline",
        "quote.minute-kline",
        "quote.realtime",
        "quote.fund-flow",
        "fundamental.income-statement",
        "fundamental.income-statement-quarterly",
        "fundamental.balance-sheet",
        "fundamental.cash-flow",
        "fundamental.cash-flow-quarterly",
        "fundamental.income-statement-hk",
        "fundamental.balance-sheet-hk",
        "fundamental.cash-flow-hk",
        "fundamental.income-statement-us",
        "fundamental.balance-sheet-us",
        "fundamental.cash-flow-us",
        "fundamental.main-business",
        "fundamental.valuation-analysis",
        "fundamental.top-holders",
        "fundamental.earning-forecast",
        "ai.stock-summary.list",
        "ai.knowledge-batch",
        "ai.knowledge-resource.download",
        "ai.security-clue.list",
        "ai.one-pager",
        "ai.investment-logic",
        "ai.peer-comparison",
        "ai.earnings-review.get-id",
        "ai.earnings-review.get-content",
        "ai.theme-tracking",
        "ai.research-outline",
        "ai.hot-topic",
        "ai.management-discuss-announcement",
        "ai.management-discuss-earnings-call",
        "ai.viewpoint-debate.get-id",
        "ai.viewpoint-debate.get-content",
        "vault.drive.list",
        "vault.drive.download",
        "vault.record.list",
        "vault.record.download",
        "vault.my-conference.list",
        "vault.my-conference.download",
        "vault.wechat-message.list",
        "vault.wechat-chatroom.list",
        "vault.stock-pool.list",
        "vault.stock-pool.stocks",
        "alternative.edb-search",
        "alternative.edb-data",
        "alternative.concept-info",
        "alternative.concept-securities",
        "indicator.search",
        "indicator.cross-section",
        "indicator.time-series",
    }
    assert set(ENDPOINTS.keys()) == expected
