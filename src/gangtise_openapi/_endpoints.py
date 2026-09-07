from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HttpMethod = Literal["GET", "POST"]
# "upload": a multipart POST that streams a local file up (tool.file-parse.submit);
# it shares requestJson's auth / retry / envelope handling but not its JSON body.
EndpointKind = Literal["json", "download", "upload"]

# "no-replay": never resend a request the server may already have executed, because
# a replay can double-bill (probed 2026-07-11: the generation endpoints charge per
# call with NO cache-hit exemption). Only connect-phase errors (request provably
# never sent), 429 (rejected before processing) and the client-level token
# self-heal retry; 5xx / response timeouts / 999999 fail fast.
# ⚠️ This is a REPLAY-SAFETY marker, not a billing-model one — do not read it as
# "per-call billed". Most endpoints carrying it are, but `ai.hot-topic` is not: it
# prices per item (50 per 篇 = per whole report) and is marked because replaying a
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
    expects: Literal["list"] | None = None


def _ep(
    key: str,
    method: HttpMethod,
    path: str,
    description: str,
    *,
    kind: EndpointKind = "json",
    paginated: int | None = None,
    retry: RetryPolicy = "default",
    timeout_ms: int | None = None,
    big_int_fields: tuple[str, ...] = (),
    file_types: tuple[int, ...] = (),
    expects: Literal["list"] | None = None,
) -> EndpointDef:
    return EndpointDef(
        key=key,
        method=method,
        path=path,
        kind=kind,
        description=description,
        pagination=Pagination(max_page_size=paginated) if paginated else None,
        retry=retry,
        timeout_ms=timeout_ms,
        big_int_fields=big_int_fields,
        file_types=file_types,
        expects=expects,
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
        "/application/open-insight/chief-opinion/getList",
        "List domestic institution chief opinions",
        paginated=50,
    ),
    "insight.summary.list": _ep(
        "insight.summary.list",
        "POST",
        "/application/open-insight/summary/v2/getList",
        "List summaries",
        paginated=50,
    ),
    "insight.summary.download": _ep(
        "insight.summary.download",
        "GET",
        "/application/open-insight/summary/v2/download/file",
        "Download summary file",
        kind="download",
        # 50/篇 — same price tier as the AI Agent calls; billing probed non-idempotent.
        retry="no-replay",
        file_types=(1, 2),
    ),
    "insight.pamirs-summary.list": _ep(
        "insight.pamirs-summary.list",
        "POST",
        "/application/open-insight/pamirs-summary/getList",
        "List Pamirs expert summaries (requires the expert-summary database)",
        paginated=50,
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
    "insight.roadshow.list": _ep(
        "insight.roadshow.list",
        "POST",
        "/application/open-insight/schedule/roadshow/getList",
        "List roadshows",
        paginated=50,
    ),
    "insight.site-visit.list": _ep(
        "insight.site-visit.list",
        "POST",
        "/application/open-insight/schedule/site-visit/getList",
        "List site visits",
        paginated=50,
    ),
    "insight.strategy.list": _ep(
        "insight.strategy.list",
        "POST",
        "/application/open-insight/schedule/strategy-meeting/getList",
        "List strategy meetings",
        paginated=50,
    ),
    "insight.forum.list": _ep(
        "insight.forum.list",
        "POST",
        "/application/open-insight/schedule/forum/getList",
        "List forums",
        paginated=50,
    ),
    "insight.performance-calendar.list": _ep(
        "insight.performance-calendar.list",
        "POST",
        "/application/open-insight/schedule/performance-calendar/getList",
        "List earnings calendar events (forecast / express / announcement)",
        paginated=50,
    ),
    "insight.performance-calendar.download": _ep(
        "insight.performance-calendar.download",
        "GET",
        "/application/open-insight/schedule/performance-calendar/download/file",
        "Download an earnings report file (A-share 10 credits, HK/US 20)",
        kind="download",
    ),
    "insight.research.list": _ep(
        "insight.research.list",
        "POST",
        "/application/open-insight/broker-report/getList",
        "List broker research reports",
        paginated=50,
    ),
    "insight.research.download": _ep(
        "insight.research.download",
        "GET",
        "/application/open-insight/broker-report/download/file",
        "Download broker research report",
        kind="download",
        file_types=(1, 2),
    ),
    "insight.foreign-report.list": _ep(
        "insight.foreign-report.list",
        "POST",
        "/application/open-insight/foreign-report/getList",
        "List foreign reports",
        paginated=50,
    ),
    "insight.foreign-report.download": _ep(
        "insight.foreign-report.download",
        "GET",
        "/application/open-insight/foreign-report/download/file",
        "Download foreign report",
        kind="download",
        retry="no-replay",
        file_types=(1, 2, 3, 4),
    ),
    "insight.announcement.list": _ep(
        "insight.announcement.list",
        "POST",
        "/application/open-insight/announcement/getList",
        "List A-share announcements",
        paginated=50,
    ),
    "insight.announcement.download": _ep(
        "insight.announcement.download",
        "GET",
        "/application/open-insight/announcement/download/file",
        "Download A-share announcement file",
        kind="download",
        file_types=(1, 2),
    ),
    "insight.announcement-hk.list": _ep(
        "insight.announcement-hk.list",
        "POST",
        "/application/open-insight/announcement-hk/getList",
        "List HK announcements",
        paginated=50,
    ),
    "insight.announcement-hk.download": _ep(
        "insight.announcement-hk.download",
        "GET",
        "/application/open-insight/announcement-hk/download/file",
        "Download HK announcement file",
        kind="download",
        file_types=(1, 2),
    ),
    "insight.announcement-us.list": _ep(
        "insight.announcement-us.list",
        "POST",
        "/application/open-insight/announcement-us/getList",
        "List US announcements",
        paginated=50,
    ),
    "insight.announcement-us.download": _ep(
        "insight.announcement-us.download",
        "GET",
        "/application/open-insight/announcement-us/download/file",
        "Download US announcement file",
        kind="download",
        file_types=(1, 2),
    ),
    "insight.foreign-opinion.list": _ep(
        "insight.foreign-opinion.list",
        "POST",
        "/application/open-insight/foreign-opinion/getList",
        "List foreign institution opinions",
        paginated=50,
    ),
    "insight.independent-opinion.list": _ep(
        "insight.independent-opinion.list",
        "POST",
        "/application/open-insight/independent-opinion/getList",
        "List foreign independent analyst opinions",
        paginated=50,
    ),
    "insight.independent-opinion.download": _ep(
        "insight.independent-opinion.download",
        "GET",
        "/application/open-insight/independent-opinion/download/file",
        "Download foreign independent opinion file",
        kind="download",
        file_types=(1, 2),
    ),
    "insight.official-account.list": _ep(
        "insight.official-account.list",
        "POST",
        "/application/open-insight/officialAccount/getList",
        "List WeChat official account articles",
        paginated=50,
    ),
    "insight.official-account.download": _ep(
        "insight.official-account.download",
        "GET",
        "/application/open-insight/officialAccount/download/file",
        "Download WeChat official account article (txt/HTML)",
        kind="download",
        file_types=(1, 2),
    ),
    "insight.qa.list": _ep(
        "insight.qa.list",
        "POST",
        # The literal '&' is the vendor's path segment (Q&A-data), not a query separator.
        "/application/open-insight/Q&A-data/getList",
        "List investor Q&A (conference/interactive/survey) for a security",
        paginated=500,
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
    ),
    # ─── ai ───
    "ai.stock-summary.list": _ep(
        "ai.stock-summary.list",
        "POST",
        "/application/open-ai/stock-summary/getList",
        "Stock highlights (refined research summary per security)",
    ),
    "ai.knowledge-batch": _ep(
        "ai.knowledge-batch",
        "POST",
        "/application/open-data/ai/search/knowledge/batch",
        "Batch knowledge search",
        retry="no-replay",
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
    ),
    "ai.one-pager": _ep(
        "ai.one-pager",
        "POST",
        "/application/open-ai/agent/one-pager",
        "Generate one pager",
        retry="no-replay",
        timeout_ms=120_000,
    ),
    "ai.investment-logic": _ep(
        "ai.investment-logic",
        "POST",
        "/application/open-ai/agent/investment-logic",
        "Generate investment logic",
        retry="no-replay",
        timeout_ms=120_000,
    ),
    "ai.peer-comparison": _ep(
        "ai.peer-comparison",
        "POST",
        "/application/open-ai/agent/peer-comparison",
        "Generate peer comparison",
        retry="no-replay",
        timeout_ms=120_000,
    ),
    "ai.earnings-review.get-id": _ep(
        "ai.earnings-review.get-id",
        "POST",
        "/application/open-ai/agent/earnings-review-getid",
        "Get earnings review ID",
        retry="no-replay",
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
    ),
    "ai.research-outline": _ep(
        "ai.research-outline",
        "POST",
        "/application/open-ai/agent/research-outline",
        "Get company research outline",
        retry="no-replay",
        timeout_ms=120_000,
    ),
    "ai.hot-topic": _ep(
        "ai.hot-topic",
        "POST",
        "/application/open-ai/hot-topic/getList",
        "List hot topic reports",
        paginated=20,
        retry="no-replay",
    ),
    "ai.management-discuss-announcement": _ep(
        "ai.management-discuss-announcement",
        "POST",
        "/application/open-ai/management-discuss/from-announcement",
        "Management discussion from financial reports (half-year/annual)",
        retry="no-replay",
        timeout_ms=120_000,
    ),
    "ai.management-discuss-earnings-call": _ep(
        "ai.management-discuss-earnings-call",
        "POST",
        "/application/open-ai/management-discuss/from-earningsCall",
        "Management discussion from earnings calls",
        retry="no-replay",
        timeout_ms=120_000,
    ),
    "ai.viewpoint-debate.get-id": _ep(
        "ai.viewpoint-debate.get-id",
        "POST",
        "/application/open-ai/agent/viewpoint-debate-getid",
        "Get viewpoint debate ID",
        retry="no-replay",
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
    ),
    "vault.my-conference.download": _ep(
        "vault.my-conference.download",
        "GET",
        "/application/open-vault/my-conference/download/file",
        "Download my conference resource",
        kind="download",
        retry="no-replay",
    ),
    "vault.wechat-message.list": _ep(
        "vault.wechat-message.list",
        "POST",
        "/application/open-vault/wechatgroupmsg/list",
        "List WeChat group messages",
        paginated=50,
    ),
    "vault.wechat-chatroom.list": _ep(
        "vault.wechat-chatroom.list",
        "POST",
        "/application/open-vault/wechatgroupmsg/chatroomId",
        "List WeChat group chatroom IDs",
        # Response is `{ total, list }` (server caps size at 50); auto-paginate by total.
        paginated=50,
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
    ),
    "alternative.concept-info": _ep(
        "alternative.concept-info",
        "POST",
        "/application/open-alternative/concept/info",
        "Query latest concept (theme index) profile by conceptId",
        retry="no-replay",
    ),
    "alternative.concept-securities": _ep(
        "alternative.concept-securities",
        "POST",
        "/application/open-alternative/concept/securities",
        "Query concept (theme index) constituent securities, grouped",
        retry="no-replay",
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
    ),
    "tool.file-parse.result": _ep(
        "tool.file-parse.result",
        "POST",
        "/application/open-tool/file-parse/result",
        "Fetch a file-parse result ZIP by taskId (140001 = still generating)",
        kind="download",
    ),
}


def lookup(key: str) -> EndpointDef:
    try:
        return ENDPOINTS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown endpoint key: {key}") from exc
