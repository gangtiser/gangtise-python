import pytest

from gangtise_openapi._endpoints import ENDPOINTS, EndpointDef, lookup


def test_endpoint_count():
    assert len(ENDPOINTS) == 75


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
        "insight.foreign-opinion.list": 50,
        "insight.independent-opinion.list": 50,
        "ai.security-clue.list": 500,
        "ai.hot-topic": 20,
        "vault.drive.list": 50,
        "vault.record.list": 50,
        "vault.my-conference.list": 50,
        "vault.wechat-message.list": 50,
    }
    actual = {
        k: ep.pagination.max_page_size for k, ep in ENDPOINTS.items() if ep.pagination is not None
    }
    assert actual == expected
    assert ENDPOINTS["vault.wechat-chatroom.list"].pagination is None


def test_download_endpoints_have_kind_download():
    download_keys = [k for k, ep in ENDPOINTS.items() if ep.kind == "download"]
    assert "insight.summary.download" in download_keys
    assert "insight.research.download" in download_keys
    for key in download_keys:
        assert ENDPOINTS[key].method in {"GET", "POST"}


def test_local_lookup_endpoints_marked():
    for key in [
        "lookup.research-areas.list",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "lookup.industries.list",
        "lookup.regions.list",
        "lookup.announcement-categories.list",
        "lookup.industry-codes.list",
        "lookup.theme-ids.list",
    ]:
        assert ENDPOINTS[key].path.startswith("/guide/")


def test_dataclass_equality():
    a = EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")
    b = EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")
    assert a == b


def test_all_endpoint_keys_match_ts_source():
    expected = {
        "auth.login",
        "lookup.research-areas.list",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "lookup.industries.list",
        "lookup.regions.list",
        "lookup.announcement-categories.list",
        "lookup.industry-codes.list",
        "lookup.theme-ids.list",
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
        "insight.foreign-opinion.list",
        "insight.independent-opinion.list",
        "insight.independent-opinion.download",
        "reference.securities-search",
        "quote.day-kline",
        "quote.day-kline-hk",
        "quote.day-kline-us",
        "quote.index-day-kline",
        "quote.minute-kline",
        "quote.realtime",
        "fundamental.income-statement",
        "fundamental.income-statement-quarterly",
        "fundamental.balance-sheet",
        "fundamental.cash-flow",
        "fundamental.cash-flow-quarterly",
        "fundamental.income-statement-hk",
        "fundamental.balance-sheet-hk",
        "fundamental.cash-flow-hk",
        "fundamental.main-business",
        "fundamental.valuation-analysis",
        "fundamental.top-holders",
        "fundamental.earning-forecast",
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
    }
    assert set(ENDPOINTS.keys()) == expected
