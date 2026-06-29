from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HttpMethod = Literal["GET", "POST"]
EndpointKind = Literal["json", "download"]


@dataclass(frozen=True)
class Pagination:
    max_page_size: int
    # Sequential mode: for endpoints that page by offset but return NO `total` and
    # use a non-standard list key (e.g. wechat chatroom's `chatRoomList`). The
    # client pages serially until a short page signals the end, accumulating
    # `list_key`. Omit both for the standard total-driven concurrent fan-out.
    sequential: bool = False
    list_key: str | None = None


@dataclass(frozen=True)
class EndpointDef:
    key: str
    method: HttpMethod
    path: str
    kind: EndpointKind
    description: str
    pagination: Pagination | None = None


def _ep(
    key: str,
    method: HttpMethod,
    path: str,
    description: str,
    *,
    kind: EndpointKind = "json",
    paginated: int | None = None,
    sequential: bool = False,
    list_key: str | None = None,
) -> EndpointDef:
    return EndpointDef(
        key=key,
        method=method,
        path=path,
        kind=kind,
        description=description,
        pagination=(
            Pagination(max_page_size=paginated, sequential=sequential, list_key=list_key)
            if paginated
            else None
        ),
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
    ),
    "quote.day-kline-hk": _ep(
        "quote.day-kline-hk",
        "POST",
        "/application/open-quote/kline-hk/daily",
        "Query HK stock historical daily kline (HK)",
    ),
    "quote.day-kline-us": _ep(
        "quote.day-kline-us",
        "POST",
        "/application/open-quote/kline-us/daily",
        "Query US stock historical daily kline (NYSE/NASDAQ/AMEX)",
    ),
    "quote.index-day-kline": _ep(
        "quote.index-day-kline",
        "POST",
        "/application/open-quote/index/kline/daily",
        "Query SH/SZ/BJ index daily kline",
    ),
    "quote.minute-kline": _ep(
        "quote.minute-kline",
        "POST",
        "/application/open-quote/kline/minute",
        "Query A-share minute kline (SH/SZ/BJ)",
    ),
    "quote.realtime": _ep(
        "quote.realtime",
        "POST",
        "/application/open-quote/quote/realtime",
        "Query realtime quote snapshot (A-share / HK / US)",
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
    ),
    "ai.investment-logic": _ep(
        "ai.investment-logic",
        "POST",
        "/application/open-ai/agent/investment-logic",
        "Generate investment logic",
    ),
    "ai.peer-comparison": _ep(
        "ai.peer-comparison",
        "POST",
        "/application/open-ai/agent/peer-comparison",
        "Generate peer comparison",
    ),
    "ai.earnings-review.get-id": _ep(
        "ai.earnings-review.get-id",
        "POST",
        "/application/open-ai/agent/earnings-review-getid",
        "Get earnings review ID",
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
    ),
    "ai.research-outline": _ep(
        "ai.research-outline",
        "POST",
        "/application/open-ai/agent/research-outline",
        "Get company research outline",
    ),
    "ai.hot-topic": _ep(
        "ai.hot-topic",
        "POST",
        "/application/open-ai/hot-topic/getList",
        "List hot topic reports",
        paginated=20,
    ),
    "ai.management-discuss-announcement": _ep(
        "ai.management-discuss-announcement",
        "POST",
        "/application/open-ai/management-discuss/from-announcement",
        "Management discussion from financial reports (half-year/annual)",
    ),
    "ai.management-discuss-earnings-call": _ep(
        "ai.management-discuss-earnings-call",
        "POST",
        "/application/open-ai/management-discuss/from-earningsCall",
        "Management discussion from earnings calls",
    ),
    "ai.viewpoint-debate.get-id": _ep(
        "ai.viewpoint-debate.get-id",
        "POST",
        "/application/open-ai/agent/viewpoint-debate-getid",
        "Get viewpoint debate ID",
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
        # No `total` in the response; list key is `chatRoomList`, server caps size at 50.
        paginated=50,
        sequential=True,
        list_key="chatRoomList",
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
    ),
    "alternative.concept-securities": _ep(
        "alternative.concept-securities",
        "POST",
        "/application/open-alternative/concept/securities",
        "Query concept (theme index) constituent securities, grouped",
    ),
    # ─── indicator (EDE: security-level data indicators) ───
    "indicator.search": _ep(
        "indicator.search",
        "POST",
        "/application/open-indicator/EDE/search",
        "Search data indicators by keyword (returns indicatorCode + params)",
    ),
    "indicator.cross-section": _ep(
        "indicator.cross-section",
        "POST",
        "/application/open-indicator/EDE/cross-section",
        "Get cross-section data (multi-indicator x multi-security, single date)",
    ),
    "indicator.time-series": _ep(
        "indicator.time-series",
        "POST",
        "/application/open-indicator/EDE/time-series",
        "Get time-series data (multi-indicator x single-security OR single-indicator x multi-security)",
    ),
}


def lookup(key: str) -> EndpointDef:
    try:
        return ENDPOINTS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown endpoint key: {key}") from exc
