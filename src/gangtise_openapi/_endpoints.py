# ruff: noqa: RUF001
# (RUF001 disabled file-wide: the destructive warnings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

HttpMethod = Literal["GET", "POST"]
# "upload": a multipart POST that streams a local file up (tool.file-parse.submit,
# vault.drive.upload); it shares requestJson's auth / retry / envelope handling but
# not its JSON body.
EndpointKind = Literal["json", "download", "upload"]

# "no-replay": never resend a request the server may already have executed, because
# a replay can double-bill (probed 2026-07-11: the generation endpoints charge per
# call with NO cache-hit exemption). Only connect-phase errors (request provably
# never sent), 429 (rejected before processing) and the client-level token
# self-heal retry; 5xx / response timeouts / 999999 fail fast.
# ⚠️ This is a REPLAY-SAFETY marker, not a billing-model one — do not read it as
# "per-call billed". Most endpoints carrying it are, but `ai.hot-topic` is not: it
# prices per item (10 per 篇 = per whole report) and is marked because replaying a
# page could re-bill rows the server already delivered. Using it as a billing proxy
# is what made the total-cap probe skip that endpoint (see _pagination.py).
# ⚠️ Nor does the converse hold: "paginated" does NOT imply "per-item billed" —
# one paginated endpoint has no published unit price and several are free.
# "no-999999" (EDE indicator endpoints): the server answers a no-data query with
# HTTP 500 + code 999999 (probed 2026-07-11) — retrying that is pure waste;
# everything else follows the default policy.
RetryPolicy = Literal["default", "no-replay", "no-999999"]


@dataclass(frozen=True)
class Pagination:
    max_page_size: int
    # Hard offset window: the server rejects any page with ``from + size`` above it
    # (100006 / 140002), however large ``total`` is. Pages are planned inside it, and
    # a fetch that would need rows past it comes back partial instead of failing on
    # the last page (TS v0.41.0 ``maxWindow``).
    max_window: int | None = None


# Billing units (the platform's price list; the client cannot measure billing — there
# is no usage API). "call" — each request; "page" — each page of the submitted
# document; "row" — each row returned (a paginated list bills every page's rows);
# "security" — each requested security that has data; "issuer" — each issuer matched;
# "indicator" — each indicator fetched; "document" — each file downloaded.
BillingUnit = Literal["call", "page", "row", "security", "issuer", "indicator", "document"]


@dataclass(frozen=True)
class Billing:
    """Published price of an endpoint (TS v0.43.0 ``billing``).

    Absent for free endpoints AND for those without a published price, so its
    absence never means "free" by itself. It drives three guards: an endpoint billed
    per call or per page must be ``no-replay`` (a replayed request can bill again);
    one billed by quantity must be too once one request can bill more than
    ``NO_REPLAY_ABOVE_CREDITS`` (see ``worst_request_credits``); and a per-row
    paginated list fetched without ``size`` is refused past
    ``COSTLY_FETCH_CREDITS`` unless the caller passed ``confirm=True``.
    ``max_units`` is how many units one request can be billed for when the endpoint
    is not paginated (a paginated one is bounded by its page size).
    """

    per: BillingUnit
    price: float
    max_units: float | None = None


# Credits above which a fetch whose size the caller left open is refused unless
# confirmed (``confirm=True``): a size-less fetch of a per-row billed list once its
# total is known (_pagination.py), and an open date range on a per-row billed endpoint
# that does not page (fundamental.earning-forecast). Omitting a bound means
# "everything", and priced per row everything can be tens of thousands of credits
# from one missing argument (TS v0.43.0).
COSTLY_FETCH_CREDITS = 1000

# Credits one request of an endpoint billed by quantity may bill before a 5xx or
# timeout replay is judged too costly (decided upstream 2026-09-25): above it the
# endpoint is ``no-replay``, at or below it a replay is left to the default policy.
NO_REPLAY_ABOVE_CREDITS = 3000

# Rows one earning-forecast date carries: one per forecast year (probed 2026-09-25:
# three). For the credit estimate, not a promise — a thinly covered security has fewer.
_FORECAST_ROWS_PER_DATE = 3

_BEIJING = dt.timezone(dt.timedelta(hours=8))


def weekdays_between(start: str, end: str) -> int:
    """Monday-Friday days from ``start`` to ``end`` (``YYYY-MM-DD``), both included;
    holidays counted, so an upper bound. 0 for a reversed range."""
    first = dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    if last < first:
        return 0
    days = (last - first).days + 1
    full_weeks, rest = divmod(days, 7)
    count = full_weeks * 5
    for offset in range(rest):
        if (first + dt.timedelta(days=full_weeks * 7 + offset)).weekday() < 5:
            count += 1
    return count


def _billed_date(value: Any, key: str) -> str:
    """A body date an estimate can use: the year-first layouts ``start_date`` takes,
    nothing else — a year-last date means another day to the API, and a date nobody
    can read cannot be priced (raises ``ValidationError``)."""
    # Imported here: domains/_common pulls in pandas and the domains package, which
    # this registry module must not depend on at import time.
    from gangtise_openapi.domains._common import _validate_date

    normalized: str = _validate_date(value, key)
    return normalized


def _estimate_earning_forecast_rows(body: dict[str, Any]) -> float:
    # A missing end is today (Beijing), a missing start the year before the end — the
    # wrapper's own defaults, so a direct ``_call`` without dates is priced the same way.
    end_raw = body.get("endDate")
    end = (
        dt.datetime.now(_BEIJING).date().isoformat()
        if end_raw is None
        else _billed_date(end_raw, "endDate")
    )
    start_raw = body.get("startDate")
    start = (
        (dt.date.fromisoformat(end) - dt.timedelta(days=365)).isoformat()
        if start_raw is None
        else _billed_date(start_raw, "startDate")
    )
    return weekdays_between(start, end) * _FORECAST_ROWS_PER_DATE


@dataclass(frozen=True)
class EndpointDef:
    key: str
    method: HttpMethod
    path: str
    kind: EndpointKind
    description: str
    pagination: Pagination | None = None
    retry: RetryPolicy = "default"
    # Per-endpoint timeout floor in ms. Synchronous AI generation blocks well past
    # the 30s default; without a floor it times out — and a timed-out generation
    # must not be replayed (see "no-replay"). The transport lifts the request
    # timeout to this value, never lowering a higher user-configured timeout.
    timeout_ms: int | None = None
    # Response fields whose BARE numbers must be re-quoted before json.loads sees
    # them. Python ints are arbitrary precision, so a snowflake ID survives here
    # where JS would round it — but the value also has to survive a round-trip
    # back to the server as the same string, and `str(int)` of a float-parsed
    # number would not. Kept as a registry fact so the guard travels with the
    # endpoint (TS v0.29.0).
    big_int_fields: tuple[str, ...] = ()
    # Legal ``fileType`` values for a download endpoint that takes one. Declared
    # on the ENDPOINT rather than at each wrapper so a download added later cannot
    # forget it: ``download_to_path`` refuses a fileType the registry does not
    # cover. The server treats an out-of-range value like an unknown field —
    # it ignores it — so a typo would silently fetch the default format
    # (TS v0.32.0 made this a required field of the download spec).
    file_types: tuple[int, ...] = ()
    # "list": every successful answer is ``{..., "list": [...]}`` — an empty range
    # comes back as ``{"total": 0, "list": []}`` (CLI probed all seven quote
    # endpoints 2026-09-05) — so a payload without a ``list`` array (``data: null``,
    # a bare object) is a BROKEN response, not an empty one. Checked in the
    # transport, where the envelope's traceId is still in hand: ``None`` has nowhere
    # to carry it, so a check further downstream would report the failure
    # trace-less, and the normalizers would hand back ``None`` as a success
    # (TS v0.38.0 ``expects``).
    # "array": every successful answer is a bare JSON array — an ID with nothing to
    # return is simply absent, so the empty answer is ``[]`` (probed 2026-09-24 on
    # both opinion detail endpoints). Anything else is a changed layout, and must not
    # read as "no rows": on the detail endpoints that would report every paid-for
    # body as missing (TS v0.41.0).
    expects: Literal["list", "array"] | None = None
    # The row field that identifies a record of a paginated list. Auto-pagination
    # drops a row identical to one it already kept under the same id: lists sorted on
    # a non-unique key (``msgTime``, ``publishTime``) reorder a same-timestamp group
    # between two page requests, so neighbouring pages both return some of it and
    # miss the rest — the row count still equals ``total`` (probed 2026-09-25).
    # Dropping the duplicate makes the count fall short, which marks the
    # result partial. An id that comes back on a LATER page with different content
    # marks it partial too (``changedRows``) — unless one page carries it with two
    # contents, which shows the field is no row key for this list (TS v0.43.0).
    # A tuple of dotted paths (``source.sourceId``) together forms the id of a row that
    # no single field identifies (TS v0.48.0).
    row_id: str | tuple[str, ...] | None = None
    # ``row_id`` comes from the response description only, not from real responses:
    # whole-row repeats are still dropped; a repeat with different content is not
    # counted (a field that is not unique would flag every fetch whose repeated pair
    # straddles a page boundary).
    row_id_unverified: bool = False
    billing: Billing | None = None
    # For an endpoint billed by quantity whose one request has no bound the client can
    # rely on: how many billed units a request body asks for, estimated. ``_call``
    # refuses a request estimated above COSTLY_FETCH_CREDITS unless ``confirm=True``;
    # an estimate that raises refuses too, since "unknown" must not pass as "free".
    estimate_billed_units: Callable[[dict[str, Any]], float] | None = None
    # Irreversible once it lands: ``_call`` refuses it unless ``confirm=True``, on
    # EVERY entry point — marking it on the endpoint rather than in the wrapper is
    # what makes a direct ``client._call(key, ...)`` honour it too. The string is
    # what is lost, in the caller's terms (TS v0.40.0 ``destructive``).
    destructive: str | None = None
    # Reports per-item failures INSIDE a ``000000`` success: ``{successList,
    # failList}``, where an unresolvable item lands in ``failList`` while the
    # envelope still says 操作成功 (probed 2026-09-19 on the stock-pool batch
    # writes). ``_call`` warns and marks the result ``partial`` (TS v0.40.0).
    item_failures: bool = False


def worst_request_credits(endpoint: EndpointDef) -> float:
    """The most one request can bill: a page of a paginated list, ``max_units`` of a
    batch endpoint, one unit otherwise — a download is one document; a per-row /
    per-security / per-issuer / per-indicator endpoint that is not paginated must declare
    ``max_units`` (test_endpoints.py), so 1 never stands in for an unknown bound."""
    if endpoint.billing is None:
        return 0.0
    if endpoint.pagination is not None:
        units: float = endpoint.pagination.max_page_size
    elif endpoint.billing.max_units is not None:
        units = endpoint.billing.max_units
    else:
        units = 1
    return units * endpoint.billing.price


def _ep(
    key: str,
    method: HttpMethod,
    path: str,
    description: str,
    *,
    kind: EndpointKind = "json",
    paginated: int | None = None,
    max_window: int | None = None,
    retry: RetryPolicy = "default",
    timeout_ms: int | None = None,
    big_int_fields: tuple[str, ...] = (),
    file_types: tuple[int, ...] = (),
    expects: Literal["list", "array"] | None = None,
    row_id: str | tuple[str, ...] | None = None,
    row_id_unverified: bool = False,
    billing: Billing | None = None,
    estimate_billed_units: Callable[[dict[str, Any]], float] | None = None,
    destructive: str | None = None,
    item_failures: bool = False,
) -> EndpointDef:
    return EndpointDef(
        key=key,
        method=method,
        path=path,
        kind=kind,
        description=description,
        pagination=(
            Pagination(max_page_size=paginated, max_window=max_window) if paginated else None
        ),
        retry=retry,
        timeout_ms=timeout_ms,
        big_int_fields=big_int_fields,
        file_types=file_types,
        expects=expects,
        row_id=row_id,
        row_id_unverified=row_id_unverified,
        billing=billing,
        estimate_billed_units=estimate_billed_units,
        destructive=destructive,
        item_failures=item_failures,
    )


ENDPOINTS: dict[str, EndpointDef] = {
    # ─── auth ───
    "auth.login": _ep(
        "auth.login",
        "POST",
        "/application/auth/oauth/open/loginV2",
        "Get access token",
    ),
    # ─── lookup (served from local data, not HTTP) ───
    "lookup.broker-orgs.list": _ep(
        "lookup.broker-orgs.list",
        "GET",
        "/guide/broker-orgs-local",
        "List broker orgs from local docs",
    ),
    "lookup.meeting-orgs.list": _ep(
        "lookup.meeting-orgs.list",
        "GET",
        "/guide/meeting-orgs-local",
        "List meeting orgs from local docs",
    ),
    # ─── insight ───
    "insight.opinion.list": _ep(
        "insight.opinion.list",
        "POST",
        "/application/open-insight/chief-opinion/v2/getList",
        "List domestic institution chief opinions (brief only; body via detail)",
        paginated=50,
        row_id="chiefOpinionId",
        billing=Billing("row", 1),
    ),
    "insight.summary.list": _ep(
        "insight.summary.list",
        "POST",
        "/application/open-insight/summary/v2/getList",
        "List summaries",
        paginated=50,
        row_id="summaryId",
        billing=Billing("row", 0.1),
    ),
    "insight.summary.download": _ep(
        "insight.summary.download",
        "GET",
        "/application/open-insight/summary/v2/download/file",
        "Download summary file",
        kind="download",
        # Billing probed non-idempotent.
        retry="no-replay",
        file_types=(1, 2),
        billing=Billing("document", 30),
    ),
    "insight.pamirs-summary.list": _ep(
        "insight.pamirs-summary.list",
        "POST",
        "/application/open-insight/pamirs-summary/getList",
        "List Pamirs expert summaries (requires the expert-summary database)",
        paginated=50,
        row_id="summaryId",
    ),
    "insight.pamirs-summary.download": _ep(
        "insight.pamirs-summary.download",
        "GET",
        "/application/open-insight/pamirs-summary/download/file",
        "Download a Pamirs expert summary file",
        kind="download",
        # The 2026-08-07 spec states an entitlement (the expert-summary database)
        # but no per-call price. Treated as non-idempotent anyway, like its
        # insight.summary.download sibling: if it does meter, a 5xx replay
        # double-bills, and the only cost of being wrong is losing one retry.
        retry="no-replay",
        file_types=(1, 2),
    ),
    # The four schedule lists name their row id per list (roadshowId, siteVisitId,
    # strategyMeetingId, forumId), not ``id`` as the response description and TS have
    # it: no real response carries ``id``, and a row without its id is never deduped.
    # Still unverified: every sample was one row, so uniqueness on a page is unproven.
    "insight.roadshow.list": _ep(
        "insight.roadshow.list",
        "POST",
        "/application/open-insight/schedule/roadshow/getList",
        "List roadshows",
        paginated=50,
        row_id="roadshowId",
        row_id_unverified=True,
        billing=Billing("row", 10),
    ),
    "insight.site-visit.list": _ep(
        "insight.site-visit.list",
        "POST",
        "/application/open-insight/schedule/site-visit/getList",
        "List site visits",
        paginated=50,
        row_id="siteVisitId",
        row_id_unverified=True,
        billing=Billing("row", 10),
    ),
    "insight.strategy.list": _ep(
        "insight.strategy.list",
        "POST",
        "/application/open-insight/schedule/strategy-meeting/getList",
        "List strategy meetings",
        paginated=50,
        row_id="strategyMeetingId",
        row_id_unverified=True,
        billing=Billing("row", 10),
    ),
    "insight.forum.list": _ep(
        "insight.forum.list",
        "POST",
        "/application/open-insight/schedule/forum/getList",
        "List forums",
        paginated=50,
        row_id="forumId",
        row_id_unverified=True,
        billing=Billing("row", 10),
    ),
    "insight.performance-calendar.list": _ep(
        "insight.performance-calendar.list",
        "POST",
        "/application/open-insight/schedule/performance-calendar/getList",
        "List earnings calendar events (forecast / express / announcement)",
        paginated=50,
        row_id="performanceReportId",
        billing=Billing("row", 0.1),
    ),
    "insight.performance-calendar.download": _ep(
        "insight.performance-calendar.download",
        "GET",
        "/application/open-insight/schedule/performance-calendar/download/file",
        "Download an earnings report file (A-share 1 credit, HK/US 2)",
        kind="download",
        billing=Billing("document", 2),
    ),
    "insight.research.list": _ep(
        "insight.research.list",
        "POST",
        "/application/open-insight/broker-report/getList",
        "List broker research reports",
        paginated=50,
        row_id="reportId",
        billing=Billing("row", 0.1),
    ),
    "insight.research.download": _ep(
        "insight.research.download",
        "GET",
        "/application/open-insight/broker-report/download/file",
        "Download broker research report",
        kind="download",
        file_types=(1, 2),
        billing=Billing("document", 10),
    ),
    "insight.foreign-report.list": _ep(
        "insight.foreign-report.list",
        "POST",
        "/application/open-insight/foreign-report/getList",
        "List foreign reports",
        paginated=50,
        row_id="reportId",
        billing=Billing("row", 0.1),
    ),
    "insight.foreign-report.download": _ep(
        "insight.foreign-report.download",
        "GET",
        "/application/open-insight/foreign-report/download/file",
        "Download foreign report",
        kind="download",
        retry="no-replay",
        file_types=(1, 2, 3, 4),
        billing=Billing("document", 30),
    ),
    "insight.announcement.list": _ep(
        "insight.announcement.list",
        "POST",
        "/application/open-insight/announcement/getList",
        "List A-share announcements",
        paginated=50,
        row_id="announcementId",
        billing=Billing("row", 0.1),
    ),
    "insight.announcement.download": _ep(
        "insight.announcement.download",
        "GET",
        "/application/open-insight/announcement/download/file",
        "Download A-share announcement file",
        kind="download",
        file_types=(1, 2),
        billing=Billing("document", 1),
    ),
    "insight.announcement-hk.list": _ep(
        "insight.announcement-hk.list",
        "POST",
        "/application/open-insight/announcement-hk/getList",
        "List HK announcements",
        paginated=50,
        row_id="announcementId",
        billing=Billing("row", 0.1),
    ),
    "insight.announcement-hk.download": _ep(
        "insight.announcement-hk.download",
        "GET",
        "/application/open-insight/announcement-hk/download/file",
        "Download HK announcement file",
        kind="download",
        file_types=(1, 2),
        billing=Billing("document", 2),
    ),
    "insight.announcement-us.list": _ep(
        "insight.announcement-us.list",
        "POST",
        "/application/open-insight/announcement-us/getList",
        "List US announcements",
        paginated=50,
        row_id="announcementId",
        billing=Billing("row", 0.1),
    ),
    "insight.announcement-us.download": _ep(
        "insight.announcement-us.download",
        "GET",
        "/application/open-insight/announcement-us/download/file",
        "Download US announcement file",
        kind="download",
        file_types=(1, 2),
        billing=Billing("document", 2),
    ),
    "insight.foreign-opinion.list": _ep(
        "insight.foreign-opinion.list",
        "POST",
        "/application/open-insight/foreign-opinion/v2/getList",
        "List foreign institution opinions (brief only; body via detail)",
        paginated=50,
        row_id="foreignOpinionId",
        billing=Billing("row", 1),
    ),
    "insight.independent-opinion.list": _ep(
        "insight.independent-opinion.list",
        "POST",
        "/application/open-insight/independent-opinion/getList",
        "List foreign independent analyst opinions",
        paginated=50,
        row_id="independentOpinionId",
        row_id_unverified=True,
        billing=Billing("row", 1),
    ),
    "insight.independent-opinion.download": _ep(
        "insight.independent-opinion.download",
        "GET",
        "/application/open-insight/independent-opinion/download/file",
        "Download foreign independent opinion file",
        kind="download",
        file_types=(1, 2),
        billing=Billing("document", 30),
    ),
    "insight.official-account.list": _ep(
        "insight.official-account.list",
        "POST",
        "/application/open-insight/officialAccount/getList",
        "List WeChat official account articles",
        paginated=50,
        row_id="articleId",
        billing=Billing("row", 0.1),
    ),
    "insight.official-account.download": _ep(
        "insight.official-account.download",
        "GET",
        "/application/open-insight/officialAccount/download/file",
        "Download WeChat official account article (txt/HTML)",
        kind="download",
        file_types=(1, 2),
        billing=Billing("document", 10),
    ),
    "insight.qa.list": _ep(
        "insight.qa.list",
        "POST",
        # The literal '&' is the vendor's path segment (Q&A-data), not a query separator.
        "/application/open-insight/Q&A-data/getList",
        "List investor Q&A (conference/interactive/survey) for a security",
        paginated=500,
        billing=Billing("row", 0.1),
    ),
    "insight.report-image.list": _ep(
        "insight.report-image.list",
        "POST",
        "/application/open-insight/report-image/getList",
        "Search research report images by keyword (returns chunkId + metadata)",
    ),
    "insight.report-image.download": _ep(
        "insight.report-image.download",
        "GET",
        "/application/open-insight/report-image/download/file",
        "Download a research report image by chunkId",
        kind="download",
        billing=Billing("document", 0.1),
    ),
    # ─── reference ───
    "reference.securities-search": _ep(
        "reference.securities-search",
        "POST",
        "/application/open-reference/securities/search",
        "Search GTS codes (securities)",
    ),
    "reference.chiefs-search": _ep(
        "reference.chiefs-search",
        "POST",
        "/application/open-reference/chiefs/search",
        "Search chief analyst IDs by name / institution / team",
    ),
    "reference.institution-search": _ep(
        "reference.institution-search",
        "POST",
        "/application/open-reference/institutions/search",
        "Search institution IDs by keyword (domestic broker / foreign / lead / opinion)",
    ),
    "reference.official-account-search": _ep(
        "reference.official-account-search",
        "POST",
        "/application/open-reference/officialAccount/search",
        "Search official account (WeChat public account) IDs by name / institution / category",
    ),
    "reference.constant-category": _ep(
        "reference.constant-category",
        "GET",
        "/application/open-reference/constants/category",
        "List constant categories and their API usage scopes",
    ),
    "reference.constant-list": _ep(
        "reference.constant-list",
        "POST",
        "/application/open-reference/constants/getList",
        "List all constant values of a category",
    ),
    "reference.concept-search": _ep(
        "reference.concept-search",
        "POST",
        "/application/open-reference/concepts/search",
        "Search concept (theme) IDs by keyword",
    ),
    "reference.sector-search": _ep(
        "reference.sector-search",
        "POST",
        "/application/open-reference/sectors/search",
        "Search sector IDs by keyword",
    ),
    "reference.sector-constituents": _ep(
        "reference.sector-constituents",
        "POST",
        "/application/open-reference/sectors/constituents",
        "List constituent securities of a sector",
    ),
    # ─── quote ───
    "quote.day-kline": _ep(
        "quote.day-kline",
        "POST",
        "/application/open-quote/kline/daily",
        "Query A-share historical daily kline (SH/SZ/BJ)",
        expects="list",
    ),
    "quote.day-kline-hk": _ep(
        "quote.day-kline-hk",
        "POST",
        "/application/open-quote/kline-hk/daily",
        "Query HK stock historical daily kline (HK)",
        expects="list",
    ),
    "quote.day-kline-us": _ep(
        "quote.day-kline-us",
        "POST",
        "/application/open-quote/kline-us/daily",
        "Query US stock historical daily kline (NYSE/NASDAQ/AMEX)",
        expects="list",
    ),
    "quote.index-day-kline": _ep(
        "quote.index-day-kline",
        "POST",
        "/application/open-quote/index/kline/daily",
        "Query SH/SZ/BJ index daily kline",
        expects="list",
    ),
    "quote.minute-kline": _ep(
        "quote.minute-kline",
        "POST",
        "/application/open-quote/kline/minute",
        "Query A-share minute kline (SH/SZ/BJ)",
        expects="list",
    ),
    "quote.realtime": _ep(
        "quote.realtime",
        "POST",
        "/application/open-quote/quote/realtime",
        "Query realtime quote snapshot (A-share / HK / US)",
        expects="list",
    ),
    "quote.fund-flow": _ep(
        "quote.fund-flow",
        "POST",
        "/application/open-quote/fund-flow/daily",
        "Query A-share daily fund flow (SH/SZ/BJ; small/medium/large/xlarge orders + main net inflow)",
        expects="list",
    ),
    # ─── fundamental ───
    "fundamental.income-statement": _ep(
        "fundamental.income-statement",
        "POST",
        "/application/open-fundamental/financial-report/income-statement/accumulated",
        "Query A-share income statement (accumulated)",
    ),
    "fundamental.income-statement-quarterly": _ep(
        "fundamental.income-statement-quarterly",
        "POST",
        "/application/open-fundamental/financial-report/income-statement/quarterly",
        "Query A-share income statement (quarterly)",
    ),
    "fundamental.balance-sheet": _ep(
        "fundamental.balance-sheet",
        "POST",
        "/application/open-fundamental/financial-report/balance-sheet/accumulated",
        "Query A-share balance sheet (accumulated)",
    ),
    "fundamental.cash-flow": _ep(
        "fundamental.cash-flow",
        "POST",
        "/application/open-fundamental/financial-report/cash-flow-statement/accumulated",
        "Query A-share cash flow statement (accumulated)",
    ),
    "fundamental.cash-flow-quarterly": _ep(
        "fundamental.cash-flow-quarterly",
        "POST",
        "/application/open-fundamental/financial-report/cash-flow-statement/quarterly",
        "Query A-share cash flow statement (quarterly)",
    ),
    "fundamental.income-statement-hk": _ep(
        "fundamental.income-statement-hk",
        "POST",
        "/application/open-fundamental/financial-report/income-statement/hk",
        "Query HK income statement (China GAAP)",
    ),
    "fundamental.balance-sheet-hk": _ep(
        "fundamental.balance-sheet-hk",
        "POST",
        "/application/open-fundamental/financial-report/balance-sheet/hk",
        "Query HK balance sheet (China GAAP)",
    ),
    "fundamental.cash-flow-hk": _ep(
        "fundamental.cash-flow-hk",
        "POST",
        "/application/open-fundamental/financial-report/cash-flow-statement/hk",
        "Query HK cash flow statement (China GAAP)",
    ),
    "fundamental.income-statement-us": _ep(
        "fundamental.income-statement-us",
        "POST",
        "/application/open-fundamental/financial-report/income-statement/us",
        "Query US income statement",
    ),
    "fundamental.balance-sheet-us": _ep(
        "fundamental.balance-sheet-us",
        "POST",
        "/application/open-fundamental/financial-report/balance-sheet/us",
        "Query US balance sheet",
    ),
    "fundamental.cash-flow-us": _ep(
        "fundamental.cash-flow-us",
        "POST",
        "/application/open-fundamental/financial-report/cash-flow-statement/us",
        "Query US cash flow statement",
    ),
    "fundamental.main-business": _ep(
        "fundamental.main-business",
        "POST",
        "/application/open-fundamental/main-business",
        "Query main business composition",
    ),
    "fundamental.valuation-analysis": _ep(
        "fundamental.valuation-analysis",
        "POST",
        "/application/open-fundamental/valuation-analysis",
        "Query valuation analysis",
        expects="list",
    ),
    "fundamental.top-holders": _ep(
        "fundamental.top-holders",
        "POST",
        "/application/open-fundamental/capital-structure/top-holders",
        "Query top holders (top10 / top10 float)",
    ),
    "fundamental.earning-forecast": _ep(
        "fundamental.earning-forecast",
        "POST",
        "/application/open-fundamental/earning-forecast",
        "Query earning forecast (consensus estimates)",
        billing=Billing("row", 0.5, max_units=float("inf")),
        estimate_billed_units=_estimate_earning_forecast_rows,
        retry="no-replay",
    ),
    # ─── ai ───
    "ai.stock-summary.list": _ep(
        "ai.stock-summary.list",
        "POST",
        "/application/open-ai/stock-summary/getList",
        "Stock highlights (refined research summary per security)",
        billing=Billing("row", 1, max_units=6000),
        retry="no-replay",
        timeout_ms=120_000,
    ),
    "ai.knowledge-batch": _ep(
        "ai.knowledge-batch",
        "POST",
        "/application/open-data/ai/search/knowledge/batch",
        "Batch knowledge search",
        retry="no-replay",
        billing=Billing("call", 10),
    ),
    "ai.knowledge-resource.download": _ep(
        "ai.knowledge-resource.download",
        "GET",
        "/application/open-data/ai/resource/download",
        "Download knowledge resource",
        kind="download",
    ),
    "ai.security-clue.list": _ep(
        "ai.security-clue.list",
        "POST",
        "/application/open-ai/security-clue/getList",
        "List security clues",
        paginated=500,
        billing=Billing("row", 5),
    ),
    "ai.one-pager": _ep(
        "ai.one-pager",
        "POST",
        "/application/open-ai/agent/one-pager",
        "Generate one pager",
        retry="no-replay",
        timeout_ms=120_000,
        billing=Billing("call", 10),
    ),
    "ai.investment-logic": _ep(
        "ai.investment-logic",
        "POST",
        "/application/open-ai/agent/investment-logic",
        "Generate investment logic",
        retry="no-replay",
        timeout_ms=120_000,
        billing=Billing("call", 10),
    ),
    "ai.peer-comparison": _ep(
        "ai.peer-comparison",
        "POST",
        "/application/open-ai/agent/peer-comparison",
        "Generate peer comparison",
        retry="no-replay",
        timeout_ms=120_000,
        billing=Billing("call", 10),
    ),
    "ai.earnings-review.get-id": _ep(
        "ai.earnings-review.get-id",
        "POST",
        "/application/open-ai/agent/earnings-review-getid",
        "Get earnings review ID",
        retry="no-replay",
        billing=Billing("call", 20),
    ),
    "ai.earnings-review.get-content": _ep(
        "ai.earnings-review.get-content",
        "POST",
        "/application/open-ai/agent/earnings-review-getcontent",
        "Get earnings review content",
    ),
    "ai.theme-tracking": _ep(
        "ai.theme-tracking",
        "POST",
        "/application/open-ai/agent/theme-tracking",
        "Get theme tracking daily report",
        retry="no-replay",
        timeout_ms=120_000,
        billing=Billing("call", 10),
    ),
    "ai.research-outline": _ep(
        "ai.research-outline",
        "POST",
        "/application/open-ai/agent/research-outline",
        "Get company research outline",
        retry="no-replay",
        timeout_ms=120_000,
        billing=Billing("call", 10),
    ),
    "ai.hot-topic": _ep(
        "ai.hot-topic",
        "POST",
        "/application/open-ai/hot-topic/getList",
        "List hot topic reports",
        paginated=20,
        retry="no-replay",
        billing=Billing("row", 10),
    ),
    "ai.management-discuss-announcement": _ep(
        "ai.management-discuss-announcement",
        "POST",
        "/application/open-ai/management-discuss/from-announcement",
        "Management discussion from financial reports (half-year/annual)",
        retry="no-replay",
        timeout_ms=120_000,
        billing=Billing("call", 5),
    ),
    "ai.management-discuss-earnings-call": _ep(
        "ai.management-discuss-earnings-call",
        "POST",
        "/application/open-ai/management-discuss/from-earningsCall",
        "Management discussion from earnings calls",
        retry="no-replay",
        timeout_ms=120_000,
        billing=Billing("call", 10),
    ),
    # Management sentiment (TS v0.48.0): one row per security x earnings call, newest
    # first. The two lists page at 100 (size 101 → 100006) and report the real count
    # (from = total → 0 rows; both probed 2026-10-24); at 5 per row a full page bills
    # 500, under NO_REPLAY_ABOVE_CREDITS, so they keep the default retry like
    # security-clue. A row is identified by its security and its source call together
    # (the response description's granularity; not yet seen unique across a full page).
    "ai.management-sentiment-indicator": _ep(
        "ai.management-sentiment-indicator",
        "POST",
        "/application/open-ai/management-sentiment/company/indicator",
        "Management sentiment scores per earnings call (responsiveness / polarity / conviction)",
        paginated=100,
        expects="list",
        row_id=("securityCode", "source.sourceType", "source.sourceId"),
        row_id_unverified=True,
        billing=Billing("row", 5),
    ),
    "ai.management-sentiment-conclusion": _ep(
        "ai.management-sentiment-conclusion",
        "POST",
        "/application/open-ai/management-sentiment/company/conclusion",
        "Management sentiment conclusions per earnings call, with changes against the previous call",
        paginated=100,
        expects="list",
        row_id=("securityCode", "source.sourceType", "source.sourceId"),
        row_id_unverified=True,
        billing=Billing("row", 5),
    ),
    "ai.management-sentiment-detail": _ep(
        "ai.management-sentiment-detail",
        "POST",
        "/application/open-ai/management-sentiment/company/detail",
        "Per-Q&A management sentiment scores and their supporting quotes, for one earnings call",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 10),
    ),
    "ai.viewpoint-debate.get-id": _ep(
        "ai.viewpoint-debate.get-id",
        "POST",
        "/application/open-ai/agent/viewpoint-debate-getid",
        "Get viewpoint debate ID",
        retry="no-replay",
        billing=Billing("call", 20),
    ),
    "ai.viewpoint-debate.get-content": _ep(
        "ai.viewpoint-debate.get-content",
        "POST",
        "/application/open-ai/agent/viewpoint-debate-getcontent",
        "Get viewpoint debate content",
    ),
    # ─── vault ───
    "vault.drive.list": _ep(
        "vault.drive.list",
        "POST",
        "/application/open-vault/drive/getList",
        "List vault drive files",
        paginated=50,
        row_id="fileId",
    ),
    "vault.drive.download": _ep(
        "vault.drive.download",
        "GET",
        "/application/open-vault/drive/download/file",
        "Download vault drive file",
        kind="download",
    ),
    "vault.record.list": _ep(
        "vault.record.list",
        "POST",
        "/application/open-vault/record/getList",
        "List voice recording transcriptions",
        paginated=50,
        row_id="recordId",
    ),
    "vault.record.download": _ep(
        "vault.record.download",
        "GET",
        "/application/open-vault/record/download/file",
        "Download voice recording transcription file",
        kind="download",
    ),
    "vault.my-conference.list": _ep(
        "vault.my-conference.list",
        "POST",
        "/application/open-vault/my-conference/getList",
        "List my conferences",
        paginated=50,
        row_id="conferenceId",
        billing=Billing("row", 0.1),
    ),
    "vault.my-conference.download": _ep(
        "vault.my-conference.download",
        "GET",
        "/application/open-vault/my-conference/download/file",
        "Download my conference resource",
        kind="download",
        retry="no-replay",
        billing=Billing("document", 30),
    ),
    "vault.wechat-message.list": _ep(
        "vault.wechat-message.list",
        "POST",
        "/application/open-vault/wechatgroupmsg/list",
        "List WeChat group messages",
        paginated=50,
        row_id="msgId",
        max_window=10000,
    ),
    "vault.wechat-chatroom.list": _ep(
        "vault.wechat-chatroom.list",
        "POST",
        "/application/open-vault/wechatgroupmsg/chatroomId",
        "List WeChat group chatroom IDs",
        # Response is `{ total, list }` (server caps size at 50); auto-paginate by total.
        paginated=50,
        row_id="chatroomId",
    ),
    "vault.stock-pool.list": _ep(
        "vault.stock-pool.list",
        "POST",
        "/application/open-vault/stock-pool/getPoolList",
        "List user stock pool IDs and names",
    ),
    "vault.stock-pool.stocks": _ep(
        "vault.stock-pool.stocks",
        "POST",
        "/application/open-vault/stock-pool/getStockList",
        "List securities in stock pool(s)",
    ),
    # ─── alternative ───
    "alternative.edb-search": _ep(
        "alternative.edb-search",
        "POST",
        "/application/open-alternative/EDB/search",
        "Search industry indicator list by keyword",
    ),
    "alternative.edb-data": _ep(
        "alternative.edb-data",
        "POST",
        "/application/open-alternative/EDB/getData",
        "Get industry indicator time-series data by indicator ID list",
        # At most 10 indicators a call, checked by the server.
        billing=Billing("indicator", 30, max_units=10),
    ),
    "alternative.concept-info": _ep(
        "alternative.concept-info",
        "POST",
        "/application/open-alternative/concept/v2/info",
        "Query latest concept (theme index) profile by conceptId",
        retry="no-replay",
        billing=Billing("call", 50),
    ),
    "alternative.concept-securities": _ep(
        "alternative.concept-securities",
        "POST",
        "/application/open-alternative/concept/v2/securities",
        "Query concept (theme index) constituent securities, grouped",
        retry="no-replay",
        billing=Billing("call", 50),
    ),
    # ─── indicator (EDE: security-level data indicators) ───
    "indicator.search": _ep(
        "indicator.search",
        "POST",
        "/application/open-indicator/EDE/search",
        "Search data indicators by keyword (returns indicatorCode + params)",
        retry="no-999999",
    ),
    "indicator.cross-section": _ep(
        "indicator.cross-section",
        "POST",
        "/application/open-indicator/EDE/cross-section",
        "Get cross-section data (multi-indicator x multi-security, single date)",
        retry="no-999999",
    ),
    "indicator.time-series": _ep(
        "indicator.time-series",
        "POST",
        "/application/open-indicator/EDE/time-series",
        "Get time-series data (multi-indicator x single-security OR single-indicator x multi-security)",
        retry="no-999999",
    ),
    # Note the path: the screener sits directly under open-indicator, NOT under
    # the EDE/ prefix its three siblings share.
    "indicator.screener": _ep(
        "indicator.screener",
        "POST",
        "/application/open-indicator/screener",
        "Screen securities by an expression over indicator values (条件选股)",
        retry="no-999999",
    ),
    # ─── tool (open-tool: async file parsing) ───
    "tool.file-parse.submit": _ep(
        "tool.file-parse.submit",
        "POST",
        "/application/open-tool/file-parse/submit",
        "Submit a PDF for parsing (multipart upload), returns taskId",
        kind="upload",
        # Billed per page (0.8/页) at submit time, and the upload itself can take
        # minutes on a 100MB file — never replay it, and don't let the default
        # 30s timeout kill an in-flight upload.
        timeout_ms=300_000,
        retry="no-replay",
        # Probed 2026-07-25: taskId comes back as a string today. Guard anyway —
        # if it ever arrives as a bare number, rounding would strand a paid job.
        big_int_fields=("taskId",),
        billing=Billing("page", 0.8),
    ),
    "tool.file-parse.result": _ep(
        "tool.file-parse.result",
        "POST",
        "/application/open-tool/file-parse/result",
        "Fetch a file-parse result ZIP by taskId (140001 = still generating)",
        kind="download",
    ),
    # ─── insight (TS v0.41.0: opinion v2 split + meeting highlights) ───
    "insight.opinion.list-with-content": _ep(
        "insight.opinion.list-with-content",
        "POST",
        "/application/open-insight/chief-opinion/getList",
        "List domestic institution chief opinions with the full body (v1 list)",
        paginated=50,
        retry="no-replay",
        billing=Billing("row", 30),
    ),
    "insight.opinion.detail": _ep(
        "insight.opinion.detail",
        "POST",
        "/application/open-insight/chief-opinion/getDetail",
        "Get domestic chief opinion bodies by ID (max 20 IDs per call)",
        retry="no-replay",
        expects="array",
        billing=Billing("row", 30, max_units=20),
    ),
    "insight.foreign-opinion.list-with-content": _ep(
        "insight.foreign-opinion.list-with-content",
        "POST",
        "/application/open-insight/foreign-opinion/getList",
        "List foreign institution opinions with the full body (v1 list)",
        paginated=50,
        retry="no-replay",
        billing=Billing("row", 30),
    ),
    "insight.foreign-opinion.detail": _ep(
        "insight.foreign-opinion.detail",
        "POST",
        "/application/open-insight/foreign-opinion/getDetail",
        "Get foreign opinion bodies by ID (max 20 IDs per call)",
        retry="no-replay",
        expects="array",
        billing=Billing("row", 30, max_units=20),
    ),
    "insight.highlight.list": _ep(
        "insight.highlight.list",
        "POST",
        "/application/open-insight/summary/highlight/getList",
        "List meeting highlights (核心要点信息流; content is an HTML fragment)",
        paginated=50,
        max_window=10000,
        retry="no-replay",
        expects="list",
        row_id="highlightId",
        billing=Billing("row", 5),
    ),
    # ─── alternative (TS v0.41.0: v1 paths back `full=True`, 500/call) ───
    "alternative.concept-info-full": _ep(
        "alternative.concept-info-full",
        "POST",
        "/application/open-alternative/concept/info",
        "Query latest concept profile incl. catalyst events (keyEvents; v1)",
        retry="no-replay",
        billing=Billing("call", 500),
    ),
    "alternative.concept-securities-full": _ep(
        "alternative.concept-securities-full",
        "POST",
        "/application/open-alternative/concept/securities",
        "Query concept constituents incl. isKey / inclusionReason (v1)",
        retry="no-replay",
        billing=Billing("call", 500),
    ),
    # ─── bond (TS v0.41.0) ───
    # All thirteen are metered (0.4 credits per call per the spec; three of them per
    # row / per bond / per issuer instead). Metered + replayable is the
    # combination that double-bills, hence `no-replay` across the family. They answer
    # COLUMNAR: `data` is `{fieldList, list}` where each row is an array ordered by
    # `fieldList` — `normalize_rows` zips each row into an object.
    "bond.basic-info": _ep(
        "bond.basic-info",
        "POST",
        "/application/open-fundamental/bond/basic-info",
        "Query bond static profiles (issuance, term, coupon, rating, options)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.issuer-info": _ep(
        "bond.issuer-info",
        "POST",
        "/application/open-fundamental/bond/issuer-info",
        "Query bond issuer profiles (by bond code or issuer name)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.daily-quote": _ep(
        "bond.daily-quote",
        "POST",
        "/application/open-quote/bond/daily-quote-exchange-cfets",
        "Query bond daily close quotes (exchange + CFETS; dirty/clean price, YTM, duration)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.valuation": _ep(
        "bond.valuation",
        "POST",
        "/application/open-fundamental/bond/valuation-shclearing",
        "Query Shanghai Clearing House bond valuations (price, yield, risk measures)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.cash-flow": _ep(
        "bond.cash-flow",
        "POST",
        "/application/open-fundamental/bond/cash-flow",
        "Query bond interest payment and redemption schedule",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.announcement": _ep(
        "bond.announcement",
        "POST",
        "/application/open-fundamental/bond/announcement",
        "Query bond announcements (pageNo/pageSize; the only paged endpoint of the family)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.issuance-detail": _ep(
        "bond.issuance-detail",
        "POST",
        "/application/open-fundamental/bond/issuance-detail",
        "Query bond issuance and re-issuance records (bidding, pricing, cover ratios)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.rating-overview": _ep(
        "bond.rating-overview",
        "POST",
        "/application/open-fundamental/bond/rating-overview",
        "Query bond / issuer / guarantor ratings side by side (max 10 bonds per call)",
        retry="no-replay",
        expects="list",
        billing=Billing("row", 0.4, max_units=10),
    ),
    "bond.rating-change": _ep(
        "bond.rating-change",
        "POST",
        "/application/open-fundamental/bond/rating-change",
        "Query bond rating change history (max 10 bonds per call)",
        retry="no-replay",
        expects="list",
        billing=Billing("security", 0.4, max_units=10),
    ),
    "bond.issuer-rating-change": _ep(
        "bond.issuer-rating-change",
        "POST",
        "/application/open-fundamental/bond/issuer-rating-change",
        "Query issuer rating change history (by bond code or issuer name)",
        retry="no-replay",
        expects="list",
        billing=Billing("issuer", 0.4, max_units=10),
    ),
    "bond.issuance-plan": _ep(
        "bond.issuance-plan",
        "POST",
        "/application/open-fundamental/bond/issuance-plan",
        "Query the rate-bond issuance calendar over a date range",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.exercise-notice": _ep(
        "bond.exercise-notice",
        "POST",
        "/application/open-fundamental/bond/exercise-notice",
        "Query put/call exercise schedules and results for option-embedded bonds",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "bond.default-list": _ep(
        "bond.default-list",
        "POST",
        "/application/open-fundamental/bond/default-list",
        "Query bond default records (by default-date range, bond codes or one issuer)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    # ─── fund (TS v0.44.0) ───
    # All eighteen are billed 0.4 credits per call (the 2026-09 spec), hence
    # `no-replay`. None of them pages: `data` is `{list}` with no `total`, and an
    # unknown code answers `{list: []}` (probed 2026-09-30 on all eighteen). Past the
    # 10000-row ceiling nothing is returned — a whole-query 100006, not a cut-short
    # list (probed on `nav`) — so there is no truncation to flag.
    "fund.basic-info": _ep(
        "fund.basic-info",
        "POST",
        "/application/open-fundamental/fund/basic-info",
        "Query fund profiles (category, manager, subscription rules, benchmark, tracked index)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.nav": _ep(
        "fund.nav",
        "POST",
        "/application/open-quote/fund/nav",
        "Query fund daily NAV (unit / accumulated / adjusted; money-market yields)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.fee-rate": _ep(
        "fund.fee-rate",
        "POST",
        "/application/open-fundamental/fund/fee-rate",
        "Query fund fee rates (purchase / redemption / management / custodian / sales service)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.manager-info": _ep(
        "fund.manager-info",
        "POST",
        "/application/open-fundamental/fund/manager-info",
        "Query fund manager profiles by name (exact match; same-name managers all returned)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.manager-history": _ep(
        "fund.manager-history",
        "POST",
        "/application/open-fundamental/fund/manager-history",
        "Query a fund's past and present managers (tenure + return over tenure)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.asset-allocation": _ep(
        "fund.asset-allocation",
        "POST",
        "/application/open-fundamental/fund/asset-allocation",
        "Query a fund's asset allocation per report date (equity / bonds / cash ...)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.asset-size": _ep(
        "fund.asset-size",
        "POST",
        "/application/open-fundamental/fund/asset-size",
        "Query a fund's shares, subscriptions / redemptions and net assets per report date",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.holder-structure": _ep(
        "fund.holder-structure",
        "POST",
        "/application/open-fundamental/fund/holder-structure",
        "Query a fund's holder structure per report date (institutional / individual / employee)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.top10-holders": _ep(
        "fund.top10-holders",
        "POST",
        "/application/open-fundamental/fund/top10-holders",
        "Query a listed fund's top 10 holders per report date",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.stock-portfolio": _ep(
        "fund.stock-portfolio",
        "POST",
        "/application/open-fundamental/fund/stock-portfolio",
        "Query a fund's stock holdings per report date",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.industry-allocation": _ep(
        "fund.industry-allocation",
        "POST",
        "/application/open-fundamental/fund/industry-allocation",
        "Query a fund's stock holdings grouped by industry (SW / CITIC level 1)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.bond-portfolio": _ep(
        "fund.bond-portfolio",
        "POST",
        "/application/open-fundamental/fund/bond-portfolio",
        "Query a fund's bond holdings per report date",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.bond-type-allocation": _ep(
        "fund.bond-type-allocation",
        "POST",
        "/application/open-fundamental/fund/bond-type-allocation",
        "Query a fund's bond holdings grouped by bond type",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.fund-portfolio": _ep(
        "fund.fund-portfolio",
        "POST",
        "/application/open-fundamental/fund/fund-portfolio",
        "Query a fund-of-funds' holdings of other funds",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.fund-type-allocation": _ep(
        "fund.fund-type-allocation",
        "POST",
        "/application/open-fundamental/fund/fund-type-allocation",
        "Query a fund-of-funds' holdings grouped by fund category",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.etf-pcf-header": _ep(
        "fund.etf-pcf-header",
        "POST",
        "/application/open-fundamental/fund/etf-pcf-header",
        "Query ETF creation/redemption parameters (latest trade date)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.etf-pcf-components": _ep(
        "fund.etf-pcf-components",
        "POST",
        "/application/open-fundamental/fund/etf-pcf-components",
        "Query the ETF creation/redemption component list (latest trade date)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    "fund.etf-share-change": _ep(
        "fund.etf-share-change",
        "POST",
        "/application/open-fundamental/fund/etf-share-change",
        "Query ETF shares and scale per trade date",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 0.4),
    ),
    # ─── vault drive management (TS v0.41.0, all free) ───
    # `no-replay` on five of these is about side effects, not billing:
    # - upload / createFolder / copy CREATE something, and names are never unique here
    #   (same-name files and folders are allowed, told apart only by ID), so a replay
    #   after a lost response leaves a second copy that nothing flags.
    # - deleteFile / deleteFolder report a replay of a delete that already landed as a
    #   failure: `failList: 文件不存在` / `130002` (probed 2026-09-24).
    # rename, moveFile and moveFolder answered identically when repeated (probed
    # 2026-09-24), so they keep the default policy.
    "vault.drive.upload": _ep(
        "vault.drive.upload",
        "POST",
        "/application/open-vault/drive/uploadFile",
        "Upload a file to the AI drive (multipart; max 100MB)",
        kind="upload",
        retry="no-replay",
        timeout_ms=300_000,
    ),
    "vault.drive.folder-list": _ep(
        "vault.drive.folder-list",
        "POST",
        "/application/open-vault/drive/getFolderList",
        "List the direct subfolders and files of a drive folder",
    ),
    "vault.drive.create-folder": _ep(
        "vault.drive.create-folder",
        "POST",
        "/application/open-vault/drive/createFolder",
        "Create a drive folder",
        retry="no-replay",
    ),
    "vault.drive.rename": _ep(
        "vault.drive.rename",
        "POST",
        "/application/open-vault/drive/rename",
        "Rename a drive file or folder",
    ),
    "vault.drive.delete-file": _ep(
        "vault.drive.delete-file",
        "POST",
        "/application/open-vault/drive/deleteFile",
        "Delete drive files",
        retry="no-replay",
        destructive="删除的云盘文件无法恢复；先用 gangtise.vault.drive_folder_list() 或 drive_list() 核对文件 ID 对应的文件名。",
        item_failures=True,
    ),
    "vault.drive.delete-folder": _ep(
        "vault.drive.delete-folder",
        "POST",
        "/application/open-vault/drive/deleteFolder",
        "Delete a drive folder and everything inside it",
        retry="no-replay",
        destructive="删除文件夹会连同其中全部子文件夹与文件一起删除，且无法恢复；先用 gangtise.vault.drive_folder_list(parent_id=...) 看清里面有什么。",
    ),
    "vault.drive.move-file": _ep(
        "vault.drive.move-file",
        "POST",
        "/application/open-vault/drive/moveFile",
        "Move drive files to a folder (same space only)",
        item_failures=True,
    ),
    "vault.drive.move-folder": _ep(
        "vault.drive.move-folder",
        "POST",
        "/application/open-vault/drive/moveFolder",
        "Move a drive folder under another folder (same space only)",
    ),
    "vault.drive.copy": _ep(
        "vault.drive.copy",
        "POST",
        "/application/open-vault/drive/copy",
        "Copy drive files or a folder to the OTHER space (my drive <-> tenant drive)",
        retry="no-replay",
        item_failures=True,
    ),
    # ─── vault stock-pool writes (TS v0.40.0) ───
    # Four of the five are idempotent by the server's own rules (probed 2026-09-14):
    # re-adding a security already in the pool, removing one that isn't, and deleting
    # a pool id that doesn't exist all answer `000000` with the item in `successList`.
    # `createPool` is the exception: a duplicate name is REJECTED with 230006, so
    # replaying a create whose first attempt succeeded reports a failure for a pool
    # that now exists — fail fast and let the caller check `stock_pool_list`.
    "vault.stock-pool.create": _ep(
        "vault.stock-pool.create",
        "POST",
        "/application/open-vault/stock-pool/createPool",
        "Create a stock pool",
        retry="no-replay",
    ),
    "vault.stock-pool.delete": _ep(
        "vault.stock-pool.delete",
        "POST",
        "/application/open-vault/stock-pool/deletePool",
        "Delete stock pools (removes every watch relation inside them)",
        destructive="删除股票池会同时移除池内全部证券的关注关系，且不可恢复（投资笔记不受影响）；先用 gangtise.vault.stock_pool_list() 核对 ID 对应的池名。",
        item_failures=True,
    ),
    "vault.stock-pool.rename": _ep(
        "vault.stock-pool.rename",
        "POST",
        "/application/open-vault/stock-pool/updatePool",
        "Rename a stock pool",
    ),
    "vault.stock-pool.add-stock": _ep(
        "vault.stock-pool.add-stock",
        "POST",
        "/application/open-vault/stock-pool/addStock",
        "Add securities to a stock pool",
        item_failures=True,
    ),
    "vault.stock-pool.remove-stock": _ep(
        "vault.stock-pool.remove-stock",
        "POST",
        "/application/open-vault/stock-pool/deleteStock",
        "Remove securities from a stock pool",
        item_failures=True,
    ),
    # ─── tool (TS v0.41.0) ───
    "tool.web-search": _ep(
        "tool.web-search",
        "POST",
        "/application/open-tool/web-search/search",
        "Search the public web for research (tiered sources, optional page content)",
        retry="no-replay",
        expects="list",
        billing=Billing("call", 1),
    ),
}


def lookup(key: str) -> EndpointDef:
    try:
        return ENDPOINTS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown endpoint key: {key}") from exc
