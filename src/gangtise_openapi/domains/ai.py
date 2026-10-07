# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# strings that intentionally use fullwidth punctuation.)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from gangtise_openapi._async_content import (
    check_content,
    check_content_async,
    poll_content,
    poll_content_async,
)
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._endpoints import lookup
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._quote_sharding import NO_MARKET_KEYWORDS, check_market_keywords
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _as_named_list,
    _refuse_empty,
    _request_body,
    _result_to_dataframe,
    _to_end_timestamp13,
    _to_timestamp13,
    _validate_choices,
    _validate_top,
)

# Hot-topic report types. Checked locally: an unknown category is not refused (probed
# by the CLI 2026-09-25 on a window with no data — whether it is ignored or filters to
# nothing was not measured), so a misspelling reads as an ordinary answer. Every
# category is sent when none is named: the API has no "all" of its own (TS v0.43.0).
_HOT_TOPIC_CATEGORIES = ("morningBriefing", "noonBriefing", "afternoonFlash", "eveningBriefing")

# Security-clue sources. Checked locally: an unknown value is not refused but ignored —
# the answer is the unfiltered set (CLI probed 2026-09-25: no source and "bogusSource"
# both total 8, "announcement" 0), so a misspelling reads as an ordinary, fully billed
# answer (TS v0.43.0).
_SECURITY_CLUE_SOURCES = ("researchReport", "conference", "announcement", "view")
_SECURITY_CLUE_QUERY_MODES = ("bySecurity", "byIndustry")


def _stock_summary_max_securities() -> int:
    billing = lookup("ai.stock-summary.list").billing
    assert billing is not None and billing.max_units is not None
    return int(billing.max_units)


# Local ceiling on codes per ``ai.stock_summary_list`` call: the documented limit of
# 6000, read from the registry (``billing.max_units``). A live whole-market A-share
# batch — the largest set that exists, well past the ~5042 codes where this endpoint
# used to answer with an empty list — came back complete, with every omitted code
# confirmed to have no highlights on its own, so the guard sits at the documented limit
# rather than below it (TS v0.39.0). The stretch from a full A-share batch up to 6000
# rests on that documented limit, not on a probe. If a request inside it ever answers
# with an empty list again, lower this.
STOCK_SUMMARY_MAX_SECURITIES = _stock_summary_max_securities()


class AI:
    """`gangtise.ai.*` — AI-generated insights and structured outputs."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    # ---- knowledge-batch ----

    def knowledge_batch(
        self,
        *,
        query: FilterValue,
        top: int = 10,
        resource_type: FilterValue | None = None,
        knowledge_name: FilterValue | None = None,
        start_time: int | str | None = None,
        end_time: int | str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """知识库批量检索（ai.knowledge-batch）。

        query 必填，传至少一个检索词，最多 5 个（上限由接口校验，SDK 不拦）；多个问题传列表。
        **每个 query 整段送出**——句子里的逗号是标点，不会被当成分隔符拆成两个查询
        （``query="比较两家公司毛利率，并解释差异"`` 是一个问题）。
        start_time/end_time 收 10/13 位时间戳或 "YYYY-MM-DD[ HH:mm[:ss]]" 字符串，按北京时间
        统一转为 13 位毫秒发出；**end_time 只写日期时按当日 23:59:59 换算**，所以
        start_time 与 end_time 写同一天就是查这一整天。

        resource_type 取值 10=券商研报 / 11=外资研报 / 20=内部报告 / 40=首席观点 /
        50=公司公告 / 51=港股公告 / 60=会议平台纪要 / 70=调研纪要公告 / 80=网络资源纪要 /
        90=产业公众号；knowledge_name 取值 system_knowledge_doc=系统知识库 /
        tenant_knowledge_doc=机构知识库。

        计费 10 积分/次（按次计费；没检索到内容与报错不扣），超时 / 5xx 不自动重发。
        """
        # Each query trimmed, a blank one dropped, never split (TS ``collectText``). Unlike
        # the CLI, a query repeated verbatim is sent once (``_as_list``): the same question
        # twice in one billed call only duplicates its answer.
        queries = _as_list(query, "query") or []
        for q in queries:
            if not isinstance(q, str):
                raise ValidationError(f"invalid query: expected text, got {q!r}")
        if not queries:
            raise ValidationError("query is required: pass at least one query string")
        body = _request_body(
            {
                "queries": queries,
                "top": _validate_top(top, name="top", max_value=20),
                "resourceTypes": _as_named_list(resource_type, "resource_type"),
                "knowledgeNames": _as_named_list(knowledge_name, "knowledge_name"),
                "startTime": _to_timestamp13(start_time, "start_time"),
                "endTime": _to_end_timestamp13(end_time, "end_time"),
            }
        )
        result = self._client._call("ai.knowledge-batch", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- security-clue.list ----

    def security_clue_list(
        self,
        *,
        start_time: str,
        end_time: str,
        query_mode: str,
        from_: int = 0,
        size: int | None = None,
        gts_code: FilterValue | None = None,
        source: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 证券线索列表（ai.security-clue.list）。

        query_mode 取值: bySecurity=按证券, byIndustry=按行业。

        ⚠️ **gts_code 服务端要求非空**（缺省报 `410120 gtsCodeList不能为空`），签名上虽是
        可选，实际每次调用都要给：bySecurity 传证券代码，byIndustry 传行业码。

        source 取值 researchReport / conference / announcement / view，支持单值或列表；
        本地校验——接口对错值不报错，会返回不按来源过滤的全部结果并照常计费。

        🔴 计费 **5 积分/条**（按返回条数计），务必带 size：先 size=1 看 total 再估总价。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        if query_mode not in _SECURITY_CLUE_QUERY_MODES:
            # TS ``.choices(...)``: an unknown mode never reaches this 5-credits/row list.
            raise ValidationError(
                f"invalid query_mode: {query_mode!r} is not one of "
                f"{'/'.join(_SECURITY_CLUE_QUERY_MODES)}"
            )
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "queryMode": query_mode,
                "gtsCodeList": _as_list(gts_code, "gts_code"),
                "source": _validate_choices(source, name="source", allowed=_SECURITY_CLUE_SOURCES),
            }
        )
        result = self._client._call("ai.security-clue.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- stock-summary (个股看点) ----

    def stock_summary_list(
        self,
        *,
        security: FilterValue,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询个股看点, 每只证券的精炼研究摘要（ai.stock-summary.list）。

        security 必填, 传具体证券代码(如 600519.SH / 00700.HK), 单次最多 6000 个
        (接口上限, 本地同值拦截, 超过报错并提示分批); 支持单值或列表。仅支持 A 股和港股。

        计费 **3 积分/条**, 按返回条数计: 没有看点的证券不在返回列表里、也不扣分——所以
        **返回行数少于提交数是正常的**, 不是丢了数据。全 A 股可一次提交完, 但数千只就是
        上万积分, 提交前先估总价。🔴 整批返 0 行别直接读成「这批都没有看点」, 挑其中一两只
        单查确认后再下结论。超时 / 5xx 不自动重发(一次最多可扣 18000 积分, 重放可能重复
        扣费), 端点带 120 秒超时下限; 失败后先确认再重跑。

        ⚠️ 服务端 2026-08-14 起**移除了全市场批量能力**: aShares / hkStocks 等市场关键词
        不再返回全市场。本接口按 **3 积分/条**计费, 所以关键词在发请求前就被本地拦下——
        让失败落在请求之前而不是之后。省略 security 同样会被后端当作全市场, 故强制非空。
        """
        securities = _as_list(security, "security")
        if not securities:
            raise ValidationError(
                "security is required: pass explicit security code(s) — this endpoint no "
                "longer supports whole-market keywords"
            )
        if len(securities) > STOCK_SUMMARY_MAX_SECURITIES:
            raise ValidationError(
                f"ai stock_summary_list: {len(securities)} securities in one call — the "
                f"endpoint takes at most {STOCK_SUMMARY_MAX_SECURITIES}. Split the codes "
                f"into batches of at most {STOCK_SUMMARY_MAX_SECURITIES} and make one call "
                "per batch."
            )
        check_market_keywords(securities, NO_MARKET_KEYWORDS, "ai stock_summary_list")
        body = {"securityList": securities}
        result = self._client._call("ai.stock-summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- security-only agent endpoints ----

    def _security_only(self, endpoint_key: str, security_code: str) -> Any:
        return self._client._call(endpoint_key, body={"securityCode": security_code})

    def one_pager(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股一页通（ai.one-pager）: 返回 {date, content}, date 为该公司最新一份一页通的生成日期。"""
        return self._security_only("ai.one-pager", security_code)  # type: ignore[no-any-return]

    def investment_logic(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股投资逻辑（ai.investment-logic）。"""
        return self._security_only("ai.investment-logic", security_code)  # type: ignore[no-any-return]

    def peer_comparison(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股同业对比（ai.peer-comparison）。"""
        return self._security_only("ai.peer-comparison", security_code)  # type: ignore[no-any-return]

    def research_outline(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """获取个股调研提纲（ai.research-outline）。"""
        return self._security_only("ai.research-outline", security_code)  # type: ignore[no-any-return]

    # ---- theme-tracking ----

    def theme_tracking(
        self,
        *,
        theme_id: str,
        date: str,
        type_: FilterValue | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """获取主题/题材跟踪日报（ai.theme-tracking）。

        type_ 取值: morning=早报, night=晚报; 支持单值或列表。
        """
        body = _request_body(
            {
                "themeId": theme_id,
                "date": date,
                "type": _as_named_list(type_, "type_"),
            }
        )
        return self._client._call("ai.theme-tracking", body=body)  # type: ignore[no-any-return]

    # ---- hot-topic ----

    def hot_topic(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        category: FilterValue | None = None,
        with_related_securities: bool = True,
        with_close_reading: bool = True,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 热点主题报告列表（ai.hot-topic）。

        category 取值: morningBriefing=早报 / noonBriefing=午报
        / afternoonFlash=盘中快报 / eveningBriefing=晚报; 支持单值或列表, 省略=全部。
        本地校验——接口对错值不报错, 结果看着像正常查询。

        🔴 计费 **50 积分/篇**, 按返回条数计; 一「篇」= 一整份报告(一份早报 / 午报 /
        盘中快报 / 晚报), 不是报告里的一条话题——一页 20 条 = 1000 积分。先用
        start_date/end_date + category 收窄范围再考虑全量。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。
        省略 size 时先取 1 篇拿到总数来估算, 结果多于 1 篇时这 1 篇会多计一次——知道要几篇
        就直接传 size。可查的历史范围跟账号权限走, 超出范围的日期返回空结果、不报错。
        """
        _refuse_empty(category, "category")  # [] would widen to all four categories
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startDate": start_date,
                "endDate": end_date,
                "categoryList": _validate_choices(
                    category, name="category", allowed=_HOT_TOPIC_CATEGORIES
                )
                or list(_HOT_TOPIC_CATEGORIES),
                "withRelatedSecurities": with_related_securities,
                "withCloseReading": with_close_reading,
            }
        )
        result = self._client._call("ai.hot-topic", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- management-discuss ----

    def management_discuss_announcement(
        self,
        *,
        report_date: str,
        security_code: str,
        dimension: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """从定期报告(半年报/年报)提取管理层讨论（ai.management-discuss-announcement）。

        dimension 取值: all=全部 / businessOperation=经营情况
        / financialPerformance=财务表现 / developmentAndRisk=发展与风险。
        """
        body = _request_body(
            {
                "reportDate": report_date,
                "securityCode": security_code,
                "discussionDimension": dimension,
            }
        )
        return self._client._call("ai.management-discuss-announcement", body=body)  # type: ignore[no-any-return]

    def management_discuss_earnings_call(
        self,
        *,
        report_date: str,
        security_code: str,
        dimension: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """从业绩说明会提取管理层讨论（ai.management-discuss-earnings-call）。

        dimension 取值: all=全部 / businessOperation=经营情况
        / financialPerformance=财务表现 / developmentAndRisk=发展与风险。
        """
        body = _request_body(
            {
                "reportDate": report_date,
                "securityCode": security_code,
                "discussionDimension": dimension,
            }
        )
        return self._client._call("ai.management-discuss-earnings-call", body=body)  # type: ignore[no-any-return]

    # ---- Async-polled endpoints ----

    def earnings_review(
        self,
        *,
        security_code: str,
        period: str,  # e.g. "2025q3", "2025interim", "2025annual"
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        """AI 财报点评, 异步生成（ai.earnings-review.get-id / get-content）。

        period 取值: 如 2025annual=年报, 2025interim=中报, 2025q3=三季报。
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 累计约 316 秒 ≈ 5 分钟);
        wait=False 立即返回 {data_id, status}, 后续用 earnings_review_check 取结果。
        """
        id_result = self._client._call(
            "ai.earnings-review.get-id",
            body={"securityCode": security_code, "period": period},
        )
        if not isinstance(id_result, dict):
            raise ApiError(
                "earnings-review.get-id returned unexpected shape",
                details=id_result,
            )
        data_id = id_result.get("dataId")
        if not data_id:
            raise ApiError(
                "earnings-review.get-id did not return a dataId",
                details=id_result,
            )
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        def fetch() -> Any:
            return self._client._call("ai.earnings-review.get-content", body={"dataId": data_id})

        return poll_content(fetch)  # type: ignore[no-any-return]

    def earnings_review_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """非阻塞单次查询财报点评结果（ai.earnings-review.get-content）。

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。生成终态失败
        (410111 / 140002) 抛 ApiError: 重查同一 data_id 不会变, 重新提交会再次计费——msg
        指向参数或内容就先改再提交, msg 只是「业务处理失败」则与参数无关。
        """
        return check_content(  # type: ignore[no-any-return]
            lambda: self._client._call("ai.earnings-review.get-content", body={"dataId": data_id})
        )

    def viewpoint_debate(
        self,
        *,
        viewpoint: str,  # max 1000 chars
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        """AI 观点辩论/PK, 异步生成（ai.viewpoint-debate.get-id / get-content）。

        viewpoint 为待辩论的投资观点文本, 上限 1000 字。提交计费 50 积分/次(超时不自动重发,
        重提会再扣一次)。⚠️ 观点过不了平台的敏感词检测时, 提交照常受理并扣分, 生成阶段以
        410111 失败; 同样的内容重提仍会失败, 提交前自己把关措辞。
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 累计约 316 秒 ≈ 5 分钟);
        wait=False 立即返回 {data_id, status}, 后续用 viewpoint_debate_check 取结果。
        """
        id_result = self._client._call("ai.viewpoint-debate.get-id", body={"viewpoint": viewpoint})
        if not isinstance(id_result, dict):
            raise ApiError(
                "viewpoint-debate.get-id returned unexpected shape",
                details=id_result,
            )
        data_id = id_result.get("dataId")
        if not data_id:
            raise ApiError(
                "viewpoint-debate.get-id did not return a dataId",
                details=id_result,
            )
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        def fetch() -> Any:
            return self._client._call("ai.viewpoint-debate.get-content", body={"dataId": data_id})

        return poll_content(fetch)  # type: ignore[no-any-return]

    def viewpoint_debate_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """非阻塞单次查询观点辩论结果（ai.viewpoint-debate.get-content）。

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。生成终态失败
        (410111 / 140002) 抛 ApiError: 重查同一 data_id 不会变, 重新提交会再次计费——msg
        指向参数或内容就先改再提交, msg 只是「业务处理失败」则与参数无关。
        """
        return check_content(  # type: ignore[no-any-return]
            lambda: self._client._call("ai.viewpoint-debate.get-content", body={"dataId": data_id})
        )

    # ---- knowledge-resource download ----

    def knowledge_resource_download(
        self,
        *,
        resource_type: int,
        source_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载知识库资源文件（ai.knowledge-resource.download）。

        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="ai.knowledge-resource.download",
            query={"resourceType": resource_type, "sourceId": source_id},
            output=output,
            fallback_name=f"knowledge-{source_id}",
            title_lookup=None,
        )


class AsyncAI:
    """Async mirror of `AI`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def knowledge_batch(
        self,
        *,
        query: FilterValue,
        top: int = 10,
        resource_type: FilterValue | None = None,
        knowledge_name: FilterValue | None = None,
        start_time: int | str | None = None,
        end_time: int | str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """知识库批量检索（ai.knowledge-batch）。

        query 必填，传至少一个检索词，最多 5 个（上限由接口校验，SDK 不拦）；多个问题传列表。
        **每个 query 整段送出**——句子里的逗号是标点，不会被当成分隔符拆成两个查询
        （``query="比较两家公司毛利率，并解释差异"`` 是一个问题）。
        start_time/end_time 收 10/13 位时间戳或 "YYYY-MM-DD[ HH:mm[:ss]]" 字符串，按北京时间
        统一转为 13 位毫秒发出；**end_time 只写日期时按当日 23:59:59 换算**，所以
        start_time 与 end_time 写同一天就是查这一整天。

        resource_type 取值 10=券商研报 / 11=外资研报 / 20=内部报告 / 40=首席观点 /
        50=公司公告 / 51=港股公告 / 60=会议平台纪要 / 70=调研纪要公告 / 80=网络资源纪要 /
        90=产业公众号；knowledge_name 取值 system_knowledge_doc=系统知识库 /
        tenant_knowledge_doc=机构知识库。

        计费 10 积分/次（按次计费；没检索到内容与报错不扣），超时 / 5xx 不自动重发。
        """
        # Each query trimmed, a blank one dropped, never split (TS ``collectText``). Unlike
        # the CLI, a query repeated verbatim is sent once (``_as_list``): the same question
        # twice in one billed call only duplicates its answer.
        queries = _as_list(query, "query") or []
        for q in queries:
            if not isinstance(q, str):
                raise ValidationError(f"invalid query: expected text, got {q!r}")
        if not queries:
            raise ValidationError("query is required: pass at least one query string")
        body = _request_body(
            {
                "queries": queries,
                "top": _validate_top(top, name="top", max_value=20),
                "resourceTypes": _as_named_list(resource_type, "resource_type"),
                "knowledgeNames": _as_named_list(knowledge_name, "knowledge_name"),
                "startTime": _to_timestamp13(start_time, "start_time"),
                "endTime": _to_end_timestamp13(end_time, "end_time"),
            }
        )
        result = await self._client._call("ai.knowledge-batch", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def security_clue_list(
        self,
        *,
        start_time: str,
        end_time: str,
        query_mode: str,
        from_: int = 0,
        size: int | None = None,
        gts_code: FilterValue | None = None,
        source: FilterValue | None = None,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 证券线索列表（ai.security-clue.list）。

        query_mode 取值: bySecurity=按证券, byIndustry=按行业。

        ⚠️ **gts_code 服务端要求非空**（缺省报 `410120 gtsCodeList不能为空`），签名上虽是
        可选，实际每次调用都要给：bySecurity 传证券代码，byIndustry 传行业码。

        source 取值 researchReport / conference / announcement / view，支持单值或列表；
        本地校验——接口对错值不报错，会返回不按来源过滤的全部结果并照常计费。

        🔴 计费 **5 积分/条**（按返回条数计），务必带 size：先 size=1 看 total 再估总价。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。
        """
        if query_mode not in _SECURITY_CLUE_QUERY_MODES:
            # TS ``.choices(...)``: an unknown mode never reaches this 5-credits/row list.
            raise ValidationError(
                f"invalid query_mode: {query_mode!r} is not one of "
                f"{'/'.join(_SECURITY_CLUE_QUERY_MODES)}"
            )
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "queryMode": query_mode,
                "gtsCodeList": _as_list(gts_code, "gts_code"),
                "source": _validate_choices(source, name="source", allowed=_SECURITY_CLUE_SOURCES),
            }
        )
        result = await self._client._call("ai.security-clue.list", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def stock_summary_list(
        self,
        *,
        security: FilterValue,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询个股看点, 每只证券的精炼研究摘要（ai.stock-summary.list）。

        security 必填, 传具体证券代码(如 600519.SH / 00700.HK), 单次最多 6000 个
        (接口上限, 本地同值拦截, 超过报错并提示分批); 支持单值或列表。仅支持 A 股和港股。

        计费 **3 积分/条**, 按返回条数计: 没有看点的证券不在返回列表里、也不扣分——所以
        **返回行数少于提交数是正常的**, 不是丢了数据。全 A 股可一次提交完, 但数千只就是
        上万积分, 提交前先估总价。🔴 整批返 0 行别直接读成「这批都没有看点」, 挑其中一两只
        单查确认后再下结论。超时 / 5xx 不自动重发(一次最多可扣 18000 积分, 重放可能重复
        扣费), 端点带 120 秒超时下限; 失败后先确认再重跑。

        ⚠️ 服务端 2026-08-14 起**移除了全市场批量能力**: aShares / hkStocks 等市场关键词
        不再返回全市场。本接口按 **3 积分/条**计费, 所以关键词在发请求前就被本地拦下——
        让失败落在请求之前而不是之后。省略 security 同样会被后端当作全市场, 故强制非空。
        """
        securities = _as_list(security, "security")
        if not securities:
            raise ValidationError(
                "security is required: pass explicit security code(s) — this endpoint no "
                "longer supports whole-market keywords"
            )
        if len(securities) > STOCK_SUMMARY_MAX_SECURITIES:
            raise ValidationError(
                f"ai stock_summary_list: {len(securities)} securities in one call — the "
                f"endpoint takes at most {STOCK_SUMMARY_MAX_SECURITIES}. Split the codes "
                f"into batches of at most {STOCK_SUMMARY_MAX_SECURITIES} and make one call "
                "per batch."
            )
        check_market_keywords(securities, NO_MARKET_KEYWORDS, "ai stock_summary_list")
        body = {"securityList": securities}
        result = await self._client._call("ai.stock-summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def _security_only(self, endpoint_key: str, security_code: str) -> Any:
        return await self._client._call(endpoint_key, body={"securityCode": security_code})

    async def one_pager(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股一页通（ai.one-pager）: 返回 {date, content}, date 为该公司最新一份一页通的生成日期。"""
        return await self._security_only(  # type: ignore[no-any-return]
            "ai.one-pager", security_code
        )

    async def investment_logic(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股投资逻辑（ai.investment-logic）。"""
        return await self._security_only(  # type: ignore[no-any-return]
            "ai.investment-logic", security_code
        )

    async def peer_comparison(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股同业对比（ai.peer-comparison）。"""
        return await self._security_only(  # type: ignore[no-any-return]
            "ai.peer-comparison", security_code
        )

    async def research_outline(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """获取个股调研提纲（ai.research-outline）。"""
        return await self._security_only(  # type: ignore[no-any-return]
            "ai.research-outline", security_code
        )

    async def theme_tracking(
        self,
        *,
        theme_id: str,
        date: str,
        type_: FilterValue | None = None,
        raw: bool = False,
    ) -> dict[str, Any]:
        """获取主题/题材跟踪日报（ai.theme-tracking）。

        type_ 取值: morning=早报, night=晚报; 支持单值或列表。
        """
        body = _request_body(
            {
                "themeId": theme_id,
                "date": date,
                "type": _as_named_list(type_, "type_"),
            }
        )
        return await self._client._call(  # type: ignore[no-any-return]
            "ai.theme-tracking", body=body
        )

    async def hot_topic(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        category: FilterValue | None = None,
        with_related_securities: bool = True,
        with_close_reading: bool = True,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 热点主题报告列表（ai.hot-topic）。

        category 取值: morningBriefing=早报 / noonBriefing=午报
        / afternoonFlash=盘中快报 / eveningBriefing=晚报; 支持单值或列表, 省略=全部。
        本地校验——接口对错值不报错, 结果看着像正常查询。

        🔴 计费 **50 积分/篇**, 按返回条数计; 一「篇」= 一整份报告(一份早报 / 午报 /
        盘中快报 / 晚报), 不是报告里的一条话题——一页 20 条 = 1000 积分。先用
        start_date/end_date + category 收窄范围再考虑全量。
        省略 size 时按 total × 单价估算、显式 size 按 min(size, total) × 单价估算，超过 1000 积分
        拒绝（ValidationError，不再往下拉）；传更小的 size 取一部分，或 confirm=True 确认全量。
        省略 size 时先取 1 篇拿到总数来估算, 结果多于 1 篇时这 1 篇会多计一次——知道要几篇
        就直接传 size。可查的历史范围跟账号权限走, 超出范围的日期返回空结果、不报错。
        """
        _refuse_empty(category, "category")  # [] would widen to all four categories
        body = _request_body(
            {
                "from": from_,
                "size": size,
                "startDate": start_date,
                "endDate": end_date,
                "categoryList": _validate_choices(
                    category, name="category", allowed=_HOT_TOPIC_CATEGORIES
                )
                or list(_HOT_TOPIC_CATEGORIES),
                "withRelatedSecurities": with_related_securities,
                "withCloseReading": with_close_reading,
            }
        )
        result = await self._client._call("ai.hot-topic", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def management_discuss_announcement(
        self,
        *,
        report_date: str,
        security_code: str,
        dimension: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """从定期报告(半年报/年报)提取管理层讨论（ai.management-discuss-announcement）。

        dimension 取值: all=全部 / businessOperation=经营情况
        / financialPerformance=财务表现 / developmentAndRisk=发展与风险。
        """
        body = _request_body(
            {
                "reportDate": report_date,
                "securityCode": security_code,
                "discussionDimension": dimension,
            }
        )
        return await self._client._call(  # type: ignore[no-any-return]
            "ai.management-discuss-announcement", body=body
        )

    async def management_discuss_earnings_call(
        self,
        *,
        report_date: str,
        security_code: str,
        dimension: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """从业绩说明会提取管理层讨论（ai.management-discuss-earnings-call）。

        dimension 取值: all=全部 / businessOperation=经营情况
        / financialPerformance=财务表现 / developmentAndRisk=发展与风险。
        """
        body = _request_body(
            {
                "reportDate": report_date,
                "securityCode": security_code,
                "discussionDimension": dimension,
            }
        )
        return await self._client._call(  # type: ignore[no-any-return]
            "ai.management-discuss-earnings-call", body=body
        )

    async def earnings_review(
        self,
        *,
        security_code: str,
        period: str,
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        """AI 财报点评, 异步生成（ai.earnings-review.get-id / get-content）。

        period 取值: 如 2025annual=年报, 2025interim=中报, 2025q3=三季报。
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 累计约 316 秒 ≈ 5 分钟);
        wait=False 立即返回 {data_id, status}, 后续用 earnings_review_check 取结果。
        """
        id_result = await self._client._call(
            "ai.earnings-review.get-id",
            body={"securityCode": security_code, "period": period},
        )
        if not isinstance(id_result, dict):
            raise ApiError(
                "earnings-review.get-id returned unexpected shape",
                details=id_result,
            )
        data_id = id_result.get("dataId")
        if not data_id:
            raise ApiError(
                "earnings-review.get-id did not return a dataId",
                details=id_result,
            )
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        async def fetch() -> Any:
            return await self._client._call(
                "ai.earnings-review.get-content", body={"dataId": data_id}
            )

        return await poll_content_async(fetch)  # type: ignore[no-any-return]

    async def earnings_review_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """非阻塞单次查询财报点评结果（ai.earnings-review.get-content）。

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。生成终态失败
        (410111 / 140002) 抛 ApiError: 重查同一 data_id 不会变, 重新提交会再次计费——msg
        指向参数或内容就先改再提交, msg 只是「业务处理失败」则与参数无关。
        """
        return await check_content_async(  # type: ignore[no-any-return]
            lambda: self._client._call("ai.earnings-review.get-content", body={"dataId": data_id})
        )

    async def viewpoint_debate(
        self,
        *,
        viewpoint: str,
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        """AI 观点辩论/PK, 异步生成（ai.viewpoint-debate.get-id / get-content）。

        viewpoint 为待辩论的投资观点文本, 上限 1000 字。提交计费 50 积分/次(超时不自动重发,
        重提会再扣一次)。⚠️ 观点过不了平台的敏感词检测时, 提交照常受理并扣分, 生成阶段以
        410111 失败; 同样的内容重提仍会失败, 提交前自己把关措辞。
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 累计约 316 秒 ≈ 5 分钟);
        wait=False 立即返回 {data_id, status}, 后续用 viewpoint_debate_check 取结果。
        """
        id_result = await self._client._call(
            "ai.viewpoint-debate.get-id", body={"viewpoint": viewpoint}
        )
        if not isinstance(id_result, dict):
            raise ApiError(
                "viewpoint-debate.get-id returned unexpected shape",
                details=id_result,
            )
        data_id = id_result.get("dataId")
        if not data_id:
            raise ApiError(
                "viewpoint-debate.get-id did not return a dataId",
                details=id_result,
            )
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        async def fetch() -> Any:
            return await self._client._call(
                "ai.viewpoint-debate.get-content", body={"dataId": data_id}
            )

        return await poll_content_async(fetch)  # type: ignore[no-any-return]

    async def viewpoint_debate_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """非阻塞单次查询观点辩论结果（ai.viewpoint-debate.get-content）。

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。生成终态失败
        (410111 / 140002) 抛 ApiError: 重查同一 data_id 不会变, 重新提交会再次计费——msg
        指向参数或内容就先改再提交, msg 只是「业务处理失败」则与参数无关。
        """
        return await check_content_async(  # type: ignore[no-any-return]
            lambda: self._client._call("ai.viewpoint-debate.get-content", body={"dataId": data_id})
        )

    async def knowledge_resource_download(
        self,
        *,
        resource_type: int,
        source_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载知识库资源文件（ai.knowledge-resource.download）。

        未指定 output 时文件名按 标题缓存 → Content-Disposition → fallback 自动解析。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="ai.knowledge-resource.download",
            query={"resourceType": resource_type, "sourceId": source_id},
            output=output,
            fallback_name=f"knowledge-{source_id}",
            title_lookup=None,
        )
