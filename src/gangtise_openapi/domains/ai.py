# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# strings that intentionally use fullwidth punctuation.)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from gangtise_openapi._async_content import poll_content, poll_content_async
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _result_to_dataframe,
    _strip_none,
    _validate_top,
)

_HOT_TOPIC_DEFAULT_CATEGORIES = [
    "morningBriefing",
    "noonBriefing",
    "afternoonFlash",
    "eveningBriefing",
]


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
        start_time: int | None = None,
        end_time: int | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """知识库批量检索（ai.knowledge-batch）。

        query 必填，传至少一个检索词；start_time/end_time 为毫秒时间戳。
        """
        queries = _as_list(query)
        if not queries:
            raise ValidationError("query is required: pass at least one query string")
        body = _strip_none(
            {
                "queries": queries,
                "top": _validate_top(top, name="top", max_value=20),
                "resourceTypes": _as_list(resource_type) or None,
                "knowledgeNames": _as_list(knowledge_name),
                "startTime": start_time,
                "endTime": end_time,
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 证券线索列表（ai.security-clue.list）。

        query_mode 取值: bySecurity=按证券, byIndustry=按行业。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "queryMode": query_mode,
                "gtsCodeList": _as_list(gts_code),
                "source": _as_list(source),
            }
        )
        result = self._client._call("ai.security-clue.list", body=body)
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

        security 必填, 传证券代码(如 600519.SH / 00700.HK)或市场关键词
        aShares / hkStocks, 上限 6000; 支持单值或列表。省略会被后端当作全市场
        (每行约 3 积分 × 数千行), 故此处强制要求非空。
        """
        securities = _as_list(security)
        if not securities:
            raise ValidationError(
                "security is required: pass security code(s) or a market keyword "
                "(aShares / hkStocks)"
            )
        body = {"securityList": securities}
        result = self._client._call("ai.stock-summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- security-only agent endpoints ----

    def _security_only(self, endpoint_key: str, security_code: str) -> Any:
        return self._client._call(endpoint_key, body={"securityCode": security_code})

    def one_pager(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股一页通（ai.one-pager）。"""
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
        body = _strip_none(
            {
                "themeId": theme_id,
                "date": date,
                "type": _as_list(type_),
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 热点主题报告列表（ai.hot-topic）。

        category 取值: morningBriefing=早报 / noonBriefing=午报
        / afternoonFlash=午后快讯 / eveningBriefing=晚报; 支持单值或列表。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startDate": start_date,
                "endDate": end_date,
                "categoryList": _as_list(category) or _HOT_TOPIC_DEFAULT_CATEGORIES,
                "withRelatedSecurities": with_related_securities,
                "withCloseReading": with_close_reading,
            }
        )
        result = self._client._call("ai.hot-topic", body=body)
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
        body = {
            "reportDate": report_date,
            "securityCode": security_code,
            "discussionDimension": dimension,
        }
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
        body = {
            "reportDate": report_date,
            "securityCode": security_code,
            "discussionDimension": dimension,
        }
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
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 最长约 3 分钟);
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

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。
        """
        return self._client._call(  # type: ignore[no-any-return]
            "ai.earnings-review.get-content", body={"dataId": data_id}
        )

    def viewpoint_debate(
        self,
        *,
        viewpoint: str,  # max 1000 chars
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        """AI 观点辩论/PK, 异步生成（ai.viewpoint-debate.get-id / get-content）。

        viewpoint 为待辩论的投资观点文本, 建议不超过 1000 字。
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 最长约 3 分钟);
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

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。
        """
        return self._client._call(  # type: ignore[no-any-return]
            "ai.viewpoint-debate.get-content", body={"dataId": data_id}
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
        start_time: int | None = None,
        end_time: int | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """知识库批量检索（ai.knowledge-batch）。

        query 必填，传至少一个检索词；start_time/end_time 为毫秒时间戳。
        """
        queries = _as_list(query)
        if not queries:
            raise ValidationError("query is required: pass at least one query string")
        body = _strip_none(
            {
                "queries": queries,
                "top": _validate_top(top, name="top", max_value=20),
                "resourceTypes": _as_list(resource_type) or None,
                "knowledgeNames": _as_list(knowledge_name),
                "startTime": start_time,
                "endTime": end_time,
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 证券线索列表（ai.security-clue.list）。

        query_mode 取值: bySecurity=按证券, byIndustry=按行业。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "queryMode": query_mode,
                "gtsCodeList": _as_list(gts_code),
                "source": _as_list(source),
            }
        )
        result = await self._client._call("ai.security-clue.list", body=body)
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

        security 必填, 传证券代码(如 600519.SH / 00700.HK)或市场关键词
        aShares / hkStocks, 上限 6000; 支持单值或列表。省略会被后端当作全市场
        (每行约 3 积分 × 数千行), 故此处强制要求非空。
        """
        securities = _as_list(security)
        if not securities:
            raise ValidationError(
                "security is required: pass security code(s) or a market keyword "
                "(aShares / hkStocks)"
            )
        body = {"securityList": securities}
        result = await self._client._call("ai.stock-summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def _security_only(self, endpoint_key: str, security_code: str) -> Any:
        return await self._client._call(endpoint_key, body={"securityCode": security_code})

    async def one_pager(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        """生成个股一页通（ai.one-pager）。"""
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
        body = _strip_none(
            {
                "themeId": theme_id,
                "date": date,
                "type": _as_list(type_),
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 AI 热点主题报告列表（ai.hot-topic）。

        category 取值: morningBriefing=早报 / noonBriefing=午报
        / afternoonFlash=午后快讯 / eveningBriefing=晚报; 支持单值或列表。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startDate": start_date,
                "endDate": end_date,
                "categoryList": _as_list(category) or _HOT_TOPIC_DEFAULT_CATEGORIES,
                "withRelatedSecurities": with_related_securities,
                "withCloseReading": with_close_reading,
            }
        )
        result = await self._client._call("ai.hot-topic", body=body)
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
        body = {
            "reportDate": report_date,
            "securityCode": security_code,
            "discussionDimension": dimension,
        }
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
        body = {
            "reportDate": report_date,
            "securityCode": security_code,
            "discussionDimension": dimension,
        }
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
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 最长约 3 分钟);
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

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。
        """
        return await self._client._call(  # type: ignore[no-any-return]
            "ai.earnings-review.get-content", body={"dataId": data_id}
        )

    async def viewpoint_debate(
        self,
        *,
        viewpoint: str,
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        """AI 观点辩论/PK, 异步生成（ai.viewpoint-debate.get-id / get-content）。

        viewpoint 为待辩论的投资观点文本, 建议不超过 1000 字。
        wait=True 阻塞轮询至内容完成(退避 5→30 秒, 最多 14 次, 最长约 3 分钟);
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

        content 为 null 表示仍在生成(pending), 不抛错, 由调用方自行处理。
        """
        return await self._client._call(  # type: ignore[no-any-return]
            "ai.viewpoint-debate.get-content", body={"dataId": data_id}
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
