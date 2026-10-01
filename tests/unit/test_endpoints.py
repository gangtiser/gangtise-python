import math

import pytest

from gangtise_openapi._endpoints import (
    ENDPOINTS,
    NO_REPLAY_ABOVE_CREDITS,
    EndpointDef,
    lookup,
    weekdays_between,
    worst_request_credits,
)
from gangtise_openapi._errors import ValidationError


def test_endpoint_count():
    assert len(ENDPOINTS) == 151


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
        "insight.opinion.list-with-content": 50,
        "insight.summary.list": 50,
        "insight.pamirs-summary.list": 50,
        "insight.roadshow.list": 50,
        "insight.site-visit.list": 50,
        "insight.strategy.list": 50,
        "insight.forum.list": 50,
        "insight.performance-calendar.list": 50,
        "insight.research.list": 50,
        "insight.foreign-report.list": 50,
        "insight.announcement.list": 50,
        "insight.announcement-hk.list": 50,
        "insight.announcement-us.list": 50,
        "insight.foreign-opinion.list": 50,
        "insight.foreign-opinion.list-with-content": 50,
        "insight.independent-opinion.list": 50,
        "insight.official-account.list": 50,
        "insight.qa.list": 500,
        "insight.highlight.list": 50,
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
    # Translated 1:1 from gangtise-openapi-cli v0.44.0 endpoints.ts.
    # These annotations are billing-safety-critical — a drifted entry either
    # double-bills (missing no-replay) or degrades reliability (spurious one).
    expected_no_replay = {
        "insight.opinion.list-with-content",
        "insight.opinion.detail",
        "insight.summary.download",
        "insight.pamirs-summary.download",
        "insight.foreign-report.download",
        "insight.foreign-opinion.list-with-content",
        "insight.foreign-opinion.detail",
        "insight.highlight.list",
        "fundamental.earning-forecast",
        "bond.basic-info",
        "bond.issuer-info",
        "bond.daily-quote",
        "bond.valuation",
        "bond.cash-flow",
        "bond.announcement",
        "bond.issuance-detail",
        "bond.rating-overview",
        "bond.rating-change",
        "bond.issuer-rating-change",
        "bond.issuance-plan",
        "bond.exercise-notice",
        "fund.basic-info",
        "fund.nav",
        "fund.fee-rate",
        "fund.manager-info",
        "fund.manager-history",
        "fund.asset-allocation",
        "fund.asset-size",
        "fund.holder-structure",
        "fund.top10-holders",
        "fund.stock-portfolio",
        "fund.industry-allocation",
        "fund.bond-portfolio",
        "fund.bond-type-allocation",
        "fund.fund-portfolio",
        "fund.fund-type-allocation",
        "fund.etf-pcf-header",
        "fund.etf-pcf-components",
        "fund.etf-share-change",
        "ai.stock-summary.list",
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
        "vault.drive.upload",
        "vault.drive.create-folder",
        "vault.drive.delete-file",
        "vault.drive.delete-folder",
        "vault.drive.copy",
        "vault.my-conference.download",
        "vault.stock-pool.create",
        "alternative.concept-info",
        "alternative.concept-info-full",
        "alternative.concept-securities",
        "alternative.concept-securities-full",
        "tool.file-parse.submit",
        "tool.web-search",
    }
    expected_no_999999 = {
        "indicator.search",
        "indicator.cross-section",
        "indicator.time-series",
        "indicator.screener",
    }
    assert {k for k, ep in ENDPOINTS.items() if ep.retry == "no-replay"} == expected_no_replay
    assert {k for k, ep in ENDPOINTS.items() if ep.retry == "no-999999"} == expected_no_999999


def test_timeout_floor_registry_matches_ts_source():
    # The 7 synchronous AI generation endpoints get a 120s floor (TS v0.24.0);
    # the file-parse upload gets 300s because a 100MB multipart POST does not fit
    # in the default window (TS v0.29.0).
    expected = {
        "ai.stock-summary.list": 120_000,
        "ai.one-pager": 120_000,
        "ai.investment-logic": 120_000,
        "ai.peer-comparison": 120_000,
        "ai.theme-tracking": 120_000,
        "ai.research-outline": 120_000,
        "ai.management-discuss-announcement": 120_000,
        "ai.management-discuss-earnings-call": 120_000,
        "vault.drive.upload": 300_000,
        "tool.file-parse.submit": 300_000,
    }
    floors = {k: ep.timeout_ms for k, ep in ENDPOINTS.items() if ep.timeout_ms is not None}
    assert floors == expected


def test_big_int_fields_registry_matches_ts_source():
    # Only the file-parse taskId is guarded (TS v0.29.0) — a rounded ID would
    # strand an already-billed parse job.
    assert {k: ep.big_int_fields for k, ep in ENDPOINTS.items() if ep.big_int_fields} == {
        "tool.file-parse.submit": ("taskId",),
    }


def test_upload_endpoints_marked():
    assert [k for k, ep in ENDPOINTS.items() if ep.kind == "upload"] == [
        "tool.file-parse.submit",
        "vault.drive.upload",
    ]


def test_all_endpoint_keys_match_ts_source():
    expected = {
        "auth.login",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "insight.opinion.list",
        "insight.opinion.list-with-content",
        "insight.opinion.detail",
        "insight.summary.list",
        "insight.summary.download",
        "insight.pamirs-summary.list",
        "insight.pamirs-summary.download",
        "insight.roadshow.list",
        "insight.site-visit.list",
        "insight.strategy.list",
        "insight.forum.list",
        "insight.performance-calendar.list",
        "insight.performance-calendar.download",
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
        "insight.foreign-opinion.list-with-content",
        "insight.foreign-opinion.detail",
        "insight.independent-opinion.list",
        "insight.independent-opinion.download",
        "insight.official-account.list",
        "insight.official-account.download",
        "insight.qa.list",
        "insight.report-image.list",
        "insight.highlight.list",
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
        "bond.basic-info",
        "bond.issuer-info",
        "bond.daily-quote",
        "bond.valuation",
        "bond.cash-flow",
        "bond.announcement",
        "bond.issuance-detail",
        "bond.rating-overview",
        "bond.rating-change",
        "bond.issuer-rating-change",
        "bond.issuance-plan",
        "bond.exercise-notice",
        "fund.basic-info",
        "fund.nav",
        "fund.fee-rate",
        "fund.manager-info",
        "fund.manager-history",
        "fund.asset-allocation",
        "fund.asset-size",
        "fund.holder-structure",
        "fund.top10-holders",
        "fund.stock-portfolio",
        "fund.industry-allocation",
        "fund.bond-portfolio",
        "fund.bond-type-allocation",
        "fund.fund-portfolio",
        "fund.fund-type-allocation",
        "fund.etf-pcf-header",
        "fund.etf-pcf-components",
        "fund.etf-share-change",
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
        "vault.drive.upload",
        "vault.drive.folder-list",
        "vault.drive.create-folder",
        "vault.drive.rename",
        "vault.drive.delete-file",
        "vault.drive.delete-folder",
        "vault.drive.move-file",
        "vault.drive.move-folder",
        "vault.drive.copy",
        "vault.record.list",
        "vault.record.download",
        "vault.my-conference.list",
        "vault.my-conference.download",
        "vault.wechat-message.list",
        "vault.wechat-chatroom.list",
        "vault.stock-pool.list",
        "vault.stock-pool.stocks",
        "vault.stock-pool.create",
        "vault.stock-pool.delete",
        "vault.stock-pool.rename",
        "vault.stock-pool.add-stock",
        "vault.stock-pool.remove-stock",
        "alternative.edb-search",
        "alternative.edb-data",
        "alternative.concept-info",
        "alternative.concept-info-full",
        "alternative.concept-securities",
        "alternative.concept-securities-full",
        "indicator.search",
        "indicator.cross-section",
        "indicator.time-series",
        "indicator.screener",
        "tool.file-parse.submit",
        "tool.file-parse.result",
        "tool.web-search",
    }
    assert set(ENDPOINTS.keys()) == expected


def test_row_id_registry_matches_ts_source():
    """TS v0.43.0: the id auto-pagination dedupes repeated rows by (server P2-26)."""
    assert {k: ep.row_id for k, ep in ENDPOINTS.items() if ep.row_id} == {
        "insight.opinion.list": "chiefOpinionId",
        "insight.summary.list": "summaryId",
        "insight.pamirs-summary.list": "summaryId",
        "insight.roadshow.list": "id",
        "insight.site-visit.list": "id",
        "insight.strategy.list": "id",
        "insight.forum.list": "id",
        "insight.performance-calendar.list": "performanceReportId",
        "insight.research.list": "reportId",
        "insight.foreign-report.list": "reportId",
        "insight.announcement.list": "announcementId",
        "insight.announcement-hk.list": "announcementId",
        "insight.announcement-us.list": "announcementId",
        "insight.foreign-opinion.list": "foreignOpinionId",
        "insight.independent-opinion.list": "independentOpinionId",
        "insight.official-account.list": "articleId",
        "insight.highlight.list": "highlightId",
        "vault.drive.list": "fileId",
        "vault.record.list": "recordId",
        "vault.my-conference.list": "conferenceId",
        "vault.wechat-message.list": "msgId",
        "vault.wechat-chatroom.list": "chatroomId",
    }
    assert {k for k, ep in ENDPOINTS.items() if ep.row_id_unverified} == {
        "insight.roadshow.list",
        "insight.site-visit.list",
        "insight.strategy.list",
        "insight.forum.list",
        "insight.independent-opinion.list",
    }


def test_offset_window_registry_matches_ts_source():
    """TS v0.41.0: rows past from + size = 10000 are refused outright."""
    assert {
        k: ep.pagination.max_window
        for k, ep in ENDPOINTS.items()
        if ep.pagination is not None and ep.pagination.max_window is not None
    } == {
        "insight.highlight.list": 10000,
        "vault.wechat-message.list": 10000,
    }


def test_expects_registry_matches_ts_source():
    assert {k for k, ep in ENDPOINTS.items() if ep.expects == "array"} == {
        "insight.opinion.detail",
        "insight.foreign-opinion.detail",
    }
    assert {k for k, ep in ENDPOINTS.items() if ep.expects == "list"} == {
        "insight.highlight.list",
        "quote.day-kline",
        "quote.day-kline-hk",
        "quote.day-kline-us",
        "quote.index-day-kline",
        "quote.minute-kline",
        "quote.realtime",
        "quote.fund-flow",
        "fundamental.valuation-analysis",
        "bond.basic-info",
        "bond.issuer-info",
        "bond.daily-quote",
        "bond.valuation",
        "bond.cash-flow",
        "bond.announcement",
        "bond.issuance-detail",
        "bond.rating-overview",
        "bond.rating-change",
        "bond.issuer-rating-change",
        "bond.issuance-plan",
        "bond.exercise-notice",
        "fund.basic-info",
        "fund.nav",
        "fund.fee-rate",
        "fund.manager-info",
        "fund.manager-history",
        "fund.asset-allocation",
        "fund.asset-size",
        "fund.holder-structure",
        "fund.top10-holders",
        "fund.stock-portfolio",
        "fund.industry-allocation",
        "fund.bond-portfolio",
        "fund.bond-type-allocation",
        "fund.fund-portfolio",
        "fund.fund-type-allocation",
        "fund.etf-pcf-header",
        "fund.etf-pcf-components",
        "fund.etf-share-change",
        "tool.web-search",
    }


def test_destructive_and_item_failure_registry_matches_ts_source():
    """TS v0.40.0 / v0.41.0: irreversible endpoints need confirm=True on every entry
    point; batch writes report per-item failures inside a 000000 success."""
    assert {k for k, ep in ENDPOINTS.items() if ep.destructive} == {
        "vault.drive.delete-file",
        "vault.drive.delete-folder",
        "vault.stock-pool.delete",
    }
    assert {k for k, ep in ENDPOINTS.items() if ep.item_failures} == {
        "vault.drive.delete-file",
        "vault.drive.move-file",
        "vault.drive.copy",
        "vault.stock-pool.delete",
        "vault.stock-pool.add-stock",
        "vault.stock-pool.remove-stock",
    }
    for key in {
        "vault.drive.delete-file",
        "vault.drive.delete-folder",
        "vault.stock-pool.delete",
    }:
        # The warning is shown to a Python caller: it must name SDK methods, not the
        # CLI commands the upstream text was written for.
        assert "gangtise." in (ENDPOINTS[key].destructive or ""), key
        assert "gangtise vault" not in (ENDPOINTS[key].destructive or ""), key


def test_billing_registry_matches_ts_source():
    expected = {
        "insight.opinion.list": ("row", 1),
        "insight.opinion.list-with-content": ("row", 30),
        "insight.opinion.detail": ("row", 30, 20),
        "insight.summary.list": ("row", 0.1),
        "insight.summary.download": ("document", 50),
        "insight.roadshow.list": ("row", 20),
        "insight.site-visit.list": ("row", 20),
        "insight.strategy.list": ("row", 20),
        "insight.forum.list": ("row", 20),
        "insight.performance-calendar.list": ("row", 0.1),
        "insight.performance-calendar.download": ("document", 20),
        "insight.research.list": ("row", 0.1),
        "insight.research.download": ("document", 10),
        "insight.foreign-report.list": ("row", 0.1),
        "insight.foreign-report.download": ("document", 50),
        "insight.announcement.list": ("row", 0.1),
        "insight.announcement.download": ("document", 10),
        "insight.announcement-hk.list": ("row", 0.1),
        "insight.announcement-hk.download": ("document", 20),
        "insight.announcement-us.list": ("row", 0.1),
        "insight.announcement-us.download": ("document", 20),
        "insight.foreign-opinion.list": ("row", 1),
        "insight.foreign-opinion.list-with-content": ("row", 30),
        "insight.foreign-opinion.detail": ("row", 30, 20),
        "insight.independent-opinion.list": ("row", 5),
        "insight.independent-opinion.download": ("document", 30),
        "insight.official-account.list": ("row", 0.1),
        "insight.official-account.download": ("document", 10),
        "insight.qa.list": ("row", 0.1),
        "insight.highlight.list": ("row", 5),
        "insight.report-image.download": ("document", 0.1),
        "fundamental.earning-forecast": ("row", 0.5, math.inf),
        "bond.basic-info": ("call", 0.4),
        "bond.issuer-info": ("call", 0.4),
        "bond.daily-quote": ("call", 0.4),
        "bond.valuation": ("call", 0.4),
        "bond.cash-flow": ("call", 0.4),
        "bond.announcement": ("call", 0.4),
        "bond.issuance-detail": ("call", 0.4),
        "bond.rating-overview": ("row", 0.4, 10),
        "bond.rating-change": ("security", 0.4, 10),
        "bond.issuer-rating-change": ("issuer", 0.4, 10),
        "bond.issuance-plan": ("call", 0.4),
        "bond.exercise-notice": ("call", 0.4),
        "fund.basic-info": ("call", 0.4),
        "fund.nav": ("call", 0.4),
        "fund.fee-rate": ("call", 0.4),
        "fund.manager-info": ("call", 0.4),
        "fund.manager-history": ("call", 0.4),
        "fund.asset-allocation": ("call", 0.4),
        "fund.asset-size": ("call", 0.4),
        "fund.holder-structure": ("call", 0.4),
        "fund.top10-holders": ("call", 0.4),
        "fund.stock-portfolio": ("call", 0.4),
        "fund.industry-allocation": ("call", 0.4),
        "fund.bond-portfolio": ("call", 0.4),
        "fund.bond-type-allocation": ("call", 0.4),
        "fund.fund-portfolio": ("call", 0.4),
        "fund.fund-type-allocation": ("call", 0.4),
        "fund.etf-pcf-header": ("call", 0.4),
        "fund.etf-pcf-components": ("call", 0.4),
        "fund.etf-share-change": ("call", 0.4),
        "ai.stock-summary.list": ("row", 3, 6000),
        "ai.knowledge-batch": ("call", 10),
        "ai.security-clue.list": ("row", 5),
        "ai.one-pager": ("call", 50),
        "ai.investment-logic": ("call", 50),
        "ai.peer-comparison": ("call", 50),
        "ai.earnings-review.get-id": ("call", 50),
        "ai.theme-tracking": ("call", 50),
        "ai.research-outline": ("call", 50),
        "ai.hot-topic": ("row", 50),
        "ai.management-discuss-announcement": ("call", 10),
        "ai.management-discuss-earnings-call": ("call", 10),
        "ai.viewpoint-debate.get-id": ("call", 50),
        "vault.my-conference.list": ("row", 0.1),
        "vault.my-conference.download": ("document", 50),
        "alternative.concept-info": ("call", 50),
        "alternative.concept-info-full": ("call", 500),
        "alternative.concept-securities": ("call", 50),
        "alternative.concept-securities-full": ("call", 500),
        "tool.file-parse.submit": ("page", 0.8),
        "tool.web-search": ("call", 1),
    }
    actual = {}
    for key, ep in ENDPOINTS.items():
        if ep.billing is None:
            continue
        b = ep.billing
        actual[key] = (b.per, b.price) if b.max_units is None else (b.per, b.price, b.max_units)
    assert actual == expected


def test_billing_invariants():
    """The TS endpoints.test.ts guards, ported: a replayed request can bill again, so

    - an endpoint billed per call or per page must be no-replay;
    - one billed by quantity must be too once one request can bill more than
      NO_REPLAY_ABOVE_CREDITS;
    - a per-row / per-security / per-issuer endpoint that does not page must declare
      max_units, so 1 never stands in for an unknown bound.
    """
    for key, ep in ENDPOINTS.items():
        if ep.billing is None:
            continue
        if ep.billing.per in ("call", "page"):
            assert ep.retry == "no-replay", key
        if ep.billing.per in ("row", "security", "issuer") and ep.pagination is None:
            assert ep.billing.max_units is not None, key
        if worst_request_credits(ep) > NO_REPLAY_ABOVE_CREDITS:
            assert ep.retry == "no-replay", key


def test_earning_forecast_estimate_prices_the_date_range():
    """TS v0.44.0: weekdays x 3 forecast rows, dates read like start_date (year-first
    layouts normalized, year-last refused)."""
    est = ENDPOINTS["fundamental.earning-forecast"].estimate_billed_units
    assert est is not None
    # 2026-01-05 (Mon) .. 2026-01-16 (Fri): 10 weekdays -> 30 rows
    assert est({"startDate": "2026-01-05", "endDate": "2026-01-16"}) == 30
    assert est({"startDate": "2026/01/05", "endDate": "20260116"}) == 30
    with pytest.raises(ValidationError):
        est({"startDate": "05-01-2026", "endDate": "2026-01-16"})
    # Missing start = a year before the end: ~261 weekdays
    assert 255 * 3 <= est({"endDate": "2026-01-16"}) <= 262 * 3
    assert weekdays_between("2026-01-16", "2026-01-05") == 0
    assert weekdays_between("2026-01-03", "2026-01-04") == 0  # a weekend


def test_every_unbounded_request_is_priced_before_it_is_sent():
    """TS endpoints.test.ts: ``max_units = inf`` says one request can bill any amount;
    without an estimator nothing holds it to the credit guard, on any entry point."""
    unpriced = [
        key
        for key, ep in ENDPOINTS.items()
        if ep.billing is not None
        and ep.billing.max_units == math.inf
        and ep.estimate_billed_units is None
    ]
    assert unpriced == []
    est = ENDPOINTS["fundamental.earning-forecast"].estimate_billed_units
    assert est is not None
    # 2026-09-28 (Mon) .. 2026-10-02 (Fri): 5 weekdays x 3 rows
    assert est({"startDate": "2026-09-28", "endDate": "2026-10-02"}) == 15
    with pytest.raises(ValidationError):
        est({"startDate": 20260928, "endDate": "2026-10-02"})


def test_every_billed_endpoint_has_a_positive_price_in_a_known_unit():
    for key, ep in ENDPOINTS.items():
        if ep.billing is None:
            continue
        assert ep.billing.per in ("call", "page", "row", "security", "issuer", "document"), key
        assert ep.billing.price > 0, key


def test_every_deletion_flavoured_endpoint_is_classified():
    """TS: the independent signal set-equality lacks — whether an endpoint DELETES
    something shows in its path, not in the marker being verified. A new one that is
    neither destructive nor reviewed as reversible fails here."""
    import re

    reviewed_reversible = {"vault.stock-pool.remove-stock"}
    flavoured = [
        key
        for key, ep in ENDPOINTS.items()
        if re.search(r"delete|remove|destroy|drop|purge", ep.path, re.I)
        or re.search(r"delete|remove|destroy", key, re.I)
    ]
    assert flavoured, "the heuristic matched nothing — it has stopped working"
    for key in flavoured:
        assert ENDPOINTS[key].destructive or key in reviewed_reversible, key


def test_the_no_replay_line_actually_bites():
    """Guards the guard (TS endpoints.test.ts): the "> NO_REPLAY_ABOVE_CREDITS ⇒
    no-replay" invariant must be checking real endpoints, not passing vacuously — a
    ``worst_request_credits`` that returned 0 would otherwise keep it green."""
    costly = {
        key
        for key, ep in ENDPOINTS.items()
        if ep.billing is not None
        and ep.billing.per not in ("call", "page")
        and worst_request_credits(ep) > NO_REPLAY_ABOVE_CREDITS
    }
    assert {"ai.stock-summary.list", "fundamental.earning-forecast"} <= costly
    assert worst_request_credits(ENDPOINTS["ai.stock-summary.list"]) == 18_000
    # The line is strict: a 500-row page of security clues at 5 credits stays under it.
    assert worst_request_credits(ENDPOINTS["ai.security-clue.list"]) == 2_500


def test_billed_endpoints_that_keep_the_default_retry_are_the_documented_26():
    """The CHANGELOG 0.5.0 billing note and README name these: billed, yet retried
    after an uncertain failure. A change here must update that note."""
    default_retry = {
        key for key, ep in ENDPOINTS.items() if ep.billing is not None and ep.retry != "no-replay"
    }
    lists = {
        "ai.security-clue.list",
        "insight.roadshow.list",
        "insight.site-visit.list",
        "insight.strategy.list",
        "insight.forum.list",
        "insight.independent-opinion.list",
        "insight.opinion.list",
        "insight.foreign-opinion.list",
        "insight.qa.list",
        "insight.summary.list",
        "insight.performance-calendar.list",
        "insight.research.list",
        "insight.foreign-report.list",
        "insight.announcement.list",
        "insight.announcement-hk.list",
        "insight.announcement-us.list",
        "insight.official-account.list",
        "vault.my-conference.list",
    }
    downloads = {
        "insight.independent-opinion.download",
        "insight.performance-calendar.download",
        "insight.announcement.download",
        "insight.announcement-hk.download",
        "insight.announcement-us.download",
        "insight.research.download",
        "insight.official-account.download",
        "insight.report-image.download",
    }
    assert default_retry == lists | downloads
    assert len(default_retry) == 26
    # The same note names the quantity-billed endpoints kept on no-replay although one
    # request stays under the line — pinned by name, so one swapped for another fails.
    under_the_line = {
        key
        for key, ep in ENDPOINTS.items()
        if ep.billing is not None
        and ep.retry == "no-replay"
        and ep.billing.per not in ("call", "page")
        and worst_request_credits(ep) <= NO_REPLAY_ABOVE_CREDITS
    }
    assert under_the_line == {
        "ai.hot-topic",
        "insight.highlight.list",
        "insight.opinion.list-with-content",
        "insight.opinion.detail",
        "insight.foreign-opinion.list-with-content",
        "insight.foreign-opinion.detail",
        "insight.summary.download",
        "insight.foreign-report.download",
        "vault.my-conference.download",
        "bond.rating-overview",
        "bond.rating-change",
        "bond.issuer-rating-change",
    }
