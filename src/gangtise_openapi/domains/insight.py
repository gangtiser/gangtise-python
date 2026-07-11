# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._download import download_to_path, download_to_path_async
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _extract_rows,
    _result_to_dataframe,
    _strip_none,
    _validate_top,
)


def _to_unix_ms(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        # TS toTimestamp13: > 1e12 is already milliseconds, > 1e9 is seconds.
        if value > 1_000_000_000_000:
            return value
        if value > 1_000_000_000:
            return value * 1000
        return value
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # Naive datetime and date-only strings are anchored to local timezone,
        # matching TS HEAD's CLI argument parser.
        parsed = parsed.astimezone()
    return int(parsed.timestamp() * 1000)


class Insight:
    """`gangtise.insight.*` — research / report / announcement endpoints."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    # ---- opinion ----

    def opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        research_area: FilterValue | None = None,
        chief: FilterValue | None = None,
        security: FilterValue | None = None,
        broker: FilterValue | None = None,
        industry: FilterValue | None = None,
        concept: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        source: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内机构首席观点列表（insight.opinion.list）。"""
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "researchAreaList": _as_list(research_area),
                "chiefList": _as_list(chief),
                "securityList": _as_list(security),
                "brokerList": _as_list(broker),
                "industryList": _as_list(industry),
                "conceptList": _as_list(concept),
                "llmTagList": _as_list(llm_tag),
                "sourceList": _as_list(source),
            }
        )
        result = self._client._call("insight.opinion.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- summary ----

    def summary_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        source: FilterValue | None = None,
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        institution: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询纪要列表（insight.summary.list）。

        market 例如 SH/SZ/HK/US。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "sourceList": _as_list(source),
                "researchAreaList": _as_list(research_area),
                "securityList": _as_list(security),
                "institutionList": _as_list(institution),
                "categoryList": _as_list(category),
                "marketList": _as_list(market),
                "participantRoleList": _as_list(participant_role),
            }
        )
        result = self._client._call("insight.summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.summary.list",
            id_field="summaryId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- schedule (roadshow / site-visit / strategy / forum) ----
    #
    # v0.17.0 of the TS CLI tightened these four endpoints: each one accepts a
    # different subset of filters per the API spec, and the server silently
    # returned empty rows when given a field it doesn't recognise. The Python
    # SDK now mirrors the per-endpoint signatures exactly — unsupported kwargs
    # are removed rather than silently dropped, so callers get TypeError on
    # bad usage instead of empty DataFrames.

    def roadshow_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        broker_type: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询路演日程列表（insight.roadshow.list）。

        category 路演类型取值 earningsCall（业绩会）/ strategyMeeting（策略会）/
        companyAnalysis（公司分析）/ industryAnalysis（行业分析）/ fundRoadshow
        （基金路演）；market 取值 aShares / hkStocks / usChinaConcept / usStocks；
        participant_role 取值 management / expert；broker_type 取值
        cnBroker / otherBroker；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码（reference.constant_list 查询）；
        location 用 domesticCity 码。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "institutionList": _as_list(institution),
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
                "marketList": _as_list(market),
                "participantRoleList": _as_list(participant_role),
                "brokerTypeList": _as_list(broker_type),
                "permission": _as_list(permission),
                "locationList": _as_list(location),
            }
        )
        result = self._client._call("insight.roadshow.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def site_visit_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        object_: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询调研/实地走访日程列表（insight.site-visit.list）。

        object_ 取值 company / industry（请求字段 object）；category 调研形式取值
        single（单场）/ series（系列）；market 取值 aShares / hkStocks /
        usChinaConcept（site-visit 无 usStocks）；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码；location 用 domesticCity 码。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "institutionList": _as_list(institution),
                "securityList": _as_list(security),
                "objectList": _as_list(object_),
                "categoryList": _as_list(category),
                "marketList": _as_list(market),
                "permission": _as_list(permission),
                "locationList": _as_list(location),
            }
        )
        result = self._client._call("insight.site-visit.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def strategy_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        institution: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询线下策略会日程列表（insight.strategy.list）。

        服务端仅按 institution（主办机构 ID）和 location（domesticCity 城市/省份 ID）
        筛选，无 research_area / security / category 等。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "institutionList": _as_list(institution),
                "locationList": _as_list(location),
            }
        )
        result = self._client._call("insight.strategy.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def forum_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询论坛/电话会日程列表（insight.forum.list）。

        服务端仅按 research_area（gangtiseIndustry 码）和 location（domesticCity 码）
        筛选，无 institution / security / category 等。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "locationList": _as_list(location),
            }
        )
        result = self._client._call("insight.forum.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- research ----

    def research_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        broker: FilterValue | None = None,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        category: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        source: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内券商研报列表（insight.research.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "brokerList": _as_list(broker),
                "securityList": _as_list(security),
                "industryList": _as_list(industry),
                "categoryList": _as_list(category),
                "llmTagList": _as_list(llm_tag),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
                "sourceList": _as_list(source),
            }
        )
        result = self._client._call("insight.research.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.research.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- foreign-report ----

    def foreign_report_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外研报列表（insight.foreign-report.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "regionList": _as_list(region),
                "categoryList": _as_list(category),
                "industryList": _as_list(industry),
                "brokerList": _as_list(broker),
                "llmTagList": _as_list(llm_tag),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
            }
        )
        result = self._client._call("insight.foreign-report.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.foreign-report.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- announcement (A-share, 13-digit ms timestamps) ----

    def announcement_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: int | str | None = None,
        end_time: int | str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股公告列表（insight.announcement.list）。

        start_time/end_time 接受日期字符串或 13 位毫秒时间戳。
        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 公告分类 ID，用 reference.constant_list(category="aShareAnnouncementCategory")
        查询；常用 103910200 财务报告 / 103910201 业绩预告 / 103910700 股权股本 等。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": _to_unix_ms(start_time),
                "endTime": _to_unix_ms(end_time),
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
            }
        )
        result = self._client._call("insight.announcement.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.announcement.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- announcement-hk (plain string timestamps) ----

    def announcement_hk_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股公告列表（insight.announcement-hk.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 港股公告分类 ID，用 reference.constant_list(category="hkShareAnnouncementCategory")
        查询。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
            }
        )
        result = self._client._call("insight.announcement-hk.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.announcement-hk.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- announcement-us (plain string timestamps) ----

    def announcement_us_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股公告列表（insight.announcement-us.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        security 传美股代码如 TSLA.O；category 美股公告分类 ID，用
        reference.constant_list(category="usShareAnnouncementCategory") 查询。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
            }
        )
        result = self._client._call("insight.announcement-us.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.announcement-us.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- foreign-opinion ----

    def foreign_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外机构观点列表（insight.foreign-opinion.list）。

        rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "regionList": _as_list(region),
                "industryList": _as_list(industry),
                "securityList": _as_list(security),
                "brokerList": _as_list(broker),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
            }
        )
        result = self._client._call("insight.foreign-opinion.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- independent-opinion ----

    def independent_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外独立分析师观点列表（insight.independent-opinion.list）。

        rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "industryList": _as_list(industry),
                "securityList": _as_list(security),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
            }
        )
        result = self._client._call("insight.independent-opinion.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.independent-opinion.list",
            id_field="independentOpinionId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def official_account_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        account_id: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询产业公众号资讯列表（insight.official-account.list）。

        search_type 取值 1=标题搜索（默认） 2=全文搜索。
        rank_type 取值 1=综合（默认） 2=时间倒序。
        category 文章类型可多选：news/law/report/view/data/event/meeting/
        notice/recruit/investEdu/brand/notes/other。
        keyword 需用数据中的具体词（如「泡泡玛特」），不能用整句白话。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "searchType": search_type,
                "rankType": rank_type,
                "keyword": keyword,
                "accountIdList": _as_list(account_id),
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
                "industryList": _as_list(industry),
            }
        )
        result = self._client._call("insight.official-account.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        self._client._record_list_titles(
            list_endpoint_key="insight.official-account.list",
            id_field="articleId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    def qa_list(
        self,
        *,
        security_code: str,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: FilterValue | None = None,
        question_category: FilterValue | None = None,
        answer_important: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询投资者问答 QA（insight.qa.list）。

        按单只证券提取互动平台/电话会议/调研纪要中的提问与回答。
        source 问题来源可多选：conference=电话会议 interactive=互动平台
        survey=调研纪要。question_category 问题类型可多选（11 类）：
        productAndBusiness / capacityAndProjects / ordersAndCustomers /
        financialData / materialEvents / capitalOperations /
        shareholdersAndDividends / corporateGovernance / marketAndValuation /
        macroAndIndustry / risksAndOthers（枚举拼错服务端报 100003）。
        answer_important 答案是否涉及重要信息：1=是 0=否（可多选，省略=不筛）。
        start_time/end_time 格式 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss（字符串直传）。
        行字段：source / publishTime / question / answer / member（回答方身份）/
        securityCode / questionCategory / answerImportant。0.1 积分/条。
        """
        # TS body shape (cli.ts): request keys are BARE (source / questionCategory /
        # answerImportant), not the *List convention.
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "securityCode": security_code,
                "startTime": start_time,
                "endTime": end_time,
                "source": _as_list(source),
                "questionCategory": _as_list(question_category),
                "answerImportant": _as_list(answer_important),
            }
        )
        result = self._client._call("insight.qa.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    def report_image_list(
        self,
        *,
        keyword: str,
        top: int = 10,
        source_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索研报图片（insight.report-image.list）。

        返回 chunkId + 元数据，chunkId 供 report_image_download() 下载原图。
        top 默认 10、上限 20（超限服务端会静默截断，本地先报错）；source_id
        限定到某篇研报（可从研报列表或知识库取）。start_time/end_time 限定
        图片所属研报的发布时间。行字段：chunkId / title / sourceId / broker /
        category / typeList / industry / publishTime / page / totalPages /
        imageCaption / imageFootnote / pageContent。免费。
        """
        body = _strip_none(
            {
                "keyword": keyword,
                "top": _validate_top(top, name="top", max_value=20),
                "sourceId": source_id,
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        result = self._client._call("insight.report-image.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- Download endpoints ----

    def summary_download(
        self,
        *,
        summary_id: str,
        file_type: int | None = None,
        output: str | Path | None = None,
    ) -> Path:
        """下载纪要原文/HTML（insight.summary.download）。

        file_type 取值 1=原文（默认） 2=HTML，仅对会议平台纪要生效。
        """
        query: dict[str, str | int] = {"summaryId": summary_id}
        if file_type is not None:
            query["fileType"] = file_type
        return download_to_path(
            client=self._client,
            endpoint_key="insight.summary.download",
            query=query,
            output=output,
            fallback_name=f"summary-{summary_id}",
            title_lookup=("insight.summary.list", "summaryId", summary_id),
        )

    def research_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载国内券商研报（insight.research.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.research.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"research-{report_id}",
            title_lookup=("insight.research.list", "reportId", report_id),
        )

    def foreign_report_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载海外研报（insight.foreign-report.download）。

        file_type 取值 1=PDF（默认） 2=Markdown 3=中译PDF 4=中译Markdown。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.foreign-report.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"foreign-report-{report_id}",
            title_lookup=("insight.foreign-report.list", "reportId", report_id),
        )

    def announcement_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载 A 股公告（insight.announcement.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-{announcement_id}",
            title_lookup=("insight.announcement.list", "announcementId", announcement_id),
        )

    def announcement_hk_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载港股公告（insight.announcement-hk.download）。

        file_type 取值 1=原文（默认） 2=Markdown。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement-hk.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-hk-{announcement_id}",
            title_lookup=("insight.announcement-hk.list", "announcementId", announcement_id),
        )

    def announcement_us_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载美股公告（insight.announcement-us.download）。

        file_type 取值 1=原文 PDF（默认） 2=Markdown。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement-us.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-us-{announcement_id}",
            title_lookup=("insight.announcement-us.list", "announcementId", announcement_id),
        )

    def independent_opinion_download(
        self,
        *,
        independent_opinion_id: str,
        file_type: int,
        output: str | Path | None = None,
    ) -> Path:
        """下载海外独立分析师观点（insight.independent-opinion.download）。

        file_type 必填，取值 1=原文HTML 2=中译HTML。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.independent-opinion.download",
            query={
                "independentOpinionId": independent_opinion_id,
                "fileType": file_type,
            },
            output=output,
            fallback_name=f"independent-opinion-{independent_opinion_id}",
            title_lookup=(
                "insight.independent-opinion.list",
                "independentOpinionId",
                independent_opinion_id,
            ),
        )

    def official_account_download(
        self,
        *,
        article_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载产业公众号文章（insight.official-account.download）。

        file_type 取值 1=txt（默认） 2=HTML。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.official-account.download",
            query={"articleId": article_id, "fileType": file_type},
            output=output,
            fallback_name=f"official-account-{article_id}",
            title_lookup=("insight.official-account.list", "articleId", article_id),
        )

    def report_image_download(
        self,
        *,
        chunk_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载研报图片原图（insight.report-image.download）。

        chunk_id 取自 report_image_list() 返回的 chunkId；直接下载二进制
        原图（JPEG）。省略 output 时优先用服务端返回的文件名，无则按
        report-image-<chunkId> 命名。0.1 积分/张。
        """
        return download_to_path(
            client=self._client,
            endpoint_key="insight.report-image.download",
            query={"chunkId": chunk_id},
            output=output,
            fallback_name=f"report-image-{chunk_id}",
        )


class AsyncInsight:
    """Async mirror of `Insight`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        research_area: FilterValue | None = None,
        chief: FilterValue | None = None,
        security: FilterValue | None = None,
        broker: FilterValue | None = None,
        industry: FilterValue | None = None,
        concept: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        source: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内机构首席观点列表（insight.opinion.list）。"""
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "researchAreaList": _as_list(research_area),
                "chiefList": _as_list(chief),
                "securityList": _as_list(security),
                "brokerList": _as_list(broker),
                "industryList": _as_list(industry),
                "conceptList": _as_list(concept),
                "llmTagList": _as_list(llm_tag),
                "sourceList": _as_list(source),
            }
        )
        result = await self._client._call("insight.opinion.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def summary_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        source: FilterValue | None = None,
        research_area: FilterValue | None = None,
        security: FilterValue | None = None,
        institution: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询纪要列表（insight.summary.list）。

        market 例如 SH/SZ/HK/US。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "sourceList": _as_list(source),
                "researchAreaList": _as_list(research_area),
                "securityList": _as_list(security),
                "institutionList": _as_list(institution),
                "categoryList": _as_list(category),
                "marketList": _as_list(market),
                "participantRoleList": _as_list(participant_role),
            }
        )
        result = await self._client._call("insight.summary.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.summary.list",
            id_field="summaryId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    # ---- schedule (roadshow / site-visit / strategy / forum) ----
    # See sync Insight class for the v0.17.0 tightening rationale.

    async def roadshow_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        participant_role: FilterValue | None = None,
        broker_type: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询路演日程列表（insight.roadshow.list）。

        category 路演类型取值 earningsCall（业绩会）/ strategyMeeting（策略会）/
        companyAnalysis（公司分析）/ industryAnalysis（行业分析）/ fundRoadshow
        （基金路演）；market 取值 aShares / hkStocks / usChinaConcept / usStocks；
        participant_role 取值 management / expert；broker_type 取值
        cnBroker / otherBroker；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码（reference.constant_list 查询）；
        location 用 domesticCity 码。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "institutionList": _as_list(institution),
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
                "marketList": _as_list(market),
                "participantRoleList": _as_list(participant_role),
                "brokerTypeList": _as_list(broker_type),
                "permission": _as_list(permission),
                "locationList": _as_list(location),
            }
        )
        result = await self._client._call("insight.roadshow.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def site_visit_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        institution: FilterValue | None = None,
        security: FilterValue | None = None,
        object_: FilterValue | None = None,
        category: FilterValue | None = None,
        market: FilterValue | None = None,
        permission: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询调研/实地走访日程列表（insight.site-visit.list）。

        object_ 取值 company / industry（请求字段 object）；category 调研形式取值
        single（单场）/ series（系列）；market 取值 aShares / hkStocks /
        usChinaConcept（site-visit 无 usStocks）；permission 取值 1=公开 / 2=私密；
        research_area 用 gangtiseIndustry 码；location 用 domesticCity 码。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "institutionList": _as_list(institution),
                "securityList": _as_list(security),
                "objectList": _as_list(object_),
                "categoryList": _as_list(category),
                "marketList": _as_list(market),
                "permission": _as_list(permission),
                "locationList": _as_list(location),
            }
        )
        result = await self._client._call("insight.site-visit.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def strategy_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        institution: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询线下策略会日程列表（insight.strategy.list）。

        服务端仅按 institution（主办机构 ID）和 location（domesticCity 城市/省份 ID）
        筛选，无 research_area / security / category 等。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "institutionList": _as_list(institution),
                "locationList": _as_list(location),
            }
        )
        result = await self._client._call("insight.strategy.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def forum_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: FilterValue | None = None,
        location: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询论坛/电话会日程列表（insight.forum.list）。

        服务端仅按 research_area（gangtiseIndustry 码）和 location（domesticCity 码）
        筛选，无 institution / security / category 等。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "researchAreaList": _as_list(research_area),
                "locationList": _as_list(location),
            }
        )
        result = await self._client._call("insight.forum.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def research_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        broker: FilterValue | None = None,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        category: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        source: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询国内券商研报列表（insight.research.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "brokerList": _as_list(broker),
                "securityList": _as_list(security),
                "industryList": _as_list(industry),
                "categoryList": _as_list(category),
                "llmTagList": _as_list(llm_tag),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
                "sourceList": _as_list(source),
            }
        )
        result = await self._client._call("insight.research.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.research.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def foreign_report_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        llm_tag: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外研报列表（insight.foreign-report.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "regionList": _as_list(region),
                "categoryList": _as_list(category),
                "industryList": _as_list(industry),
                "brokerList": _as_list(broker),
                "llmTagList": _as_list(llm_tag),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
                "minReportPages": min_pages,
                "maxReportPages": max_pages,
            }
        )
        result = await self._client._call("insight.foreign-report.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.foreign-report.list",
            id_field="reportId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def announcement_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: int | str | None = None,
        end_time: int | str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股公告列表（insight.announcement.list）。

        start_time/end_time 接受日期字符串或 13 位毫秒时间戳。
        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 公告分类 ID，用 reference.constant_list(category="aShareAnnouncementCategory")
        查询；常用 103910200 财务报告 / 103910201 业绩预告 / 103910700 股权股本 等。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": _to_unix_ms(start_time),
                "endTime": _to_unix_ms(end_time),
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
            }
        )
        result = await self._client._call("insight.announcement.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.announcement.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def announcement_hk_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股公告列表（insight.announcement-hk.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        category 港股公告分类 ID，用 reference.constant_list(category="hkShareAnnouncementCategory")
        查询。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
            }
        )
        result = await self._client._call("insight.announcement-hk.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.announcement-hk.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def announcement_us_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股公告列表（insight.announcement-us.list）。

        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
        security 传美股代码如 TSLA.O；category 美股公告分类 ID，用
        reference.constant_list(category="usShareAnnouncementCategory") 查询。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "searchType": search_type,
                "rankType": rank_type,
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
            }
        )
        result = await self._client._call("insight.announcement-us.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.announcement-us.list",
            id_field="announcementId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def foreign_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        region: FilterValue | None = None,
        industry: FilterValue | None = None,
        broker: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外机构观点列表（insight.foreign-opinion.list）。

        rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "regionList": _as_list(region),
                "industryList": _as_list(industry),
                "securityList": _as_list(security),
                "brokerList": _as_list(broker),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
            }
        )
        result = await self._client._call("insight.foreign-opinion.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def independent_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: FilterValue | None = None,
        industry: FilterValue | None = None,
        rating: FilterValue | None = None,
        rating_change: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询海外独立分析师观点列表（insight.independent-opinion.list）。

        rank_type 取值 1=综合 2=时间倒序。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "keyword": keyword,
                "rankType": rank_type,
                "industryList": _as_list(industry),
                "securityList": _as_list(security),
                "ratingList": _as_list(rating),
                "ratingChangeList": _as_list(rating_change),
            }
        )
        result = await self._client._call("insight.independent-opinion.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.independent-opinion.list",
            id_field="independentOpinionId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def official_account_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        search_type: int = 1,
        rank_type: int = 1,
        account_id: FilterValue | None = None,
        security: FilterValue | None = None,
        category: FilterValue | None = None,
        industry: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询产业公众号资讯列表（insight.official-account.list）。

        search_type 取值 1=标题搜索（默认） 2=全文搜索。
        rank_type 取值 1=综合（默认） 2=时间倒序。
        category 文章类型可多选：news/law/report/view/data/event/meeting/
        notice/recruit/investEdu/brand/notes/other。
        keyword 需用数据中的具体词（如「泡泡玛特」），不能用整句白话。
        """
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startTime": start_time,
                "endTime": end_time,
                "searchType": search_type,
                "rankType": rank_type,
                "keyword": keyword,
                "accountIdList": _as_list(account_id),
                "securityList": _as_list(security),
                "categoryList": _as_list(category),
                "industryList": _as_list(industry),
            }
        )
        result = await self._client._call("insight.official-account.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        await self._client._record_list_titles(
            list_endpoint_key="insight.official-account.list",
            id_field="articleId",
            title_field="title",
            rows=rows,
        )
        return to_dataframe(rows, schema=None)

    async def qa_list(
        self,
        *,
        security_code: str,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        source: FilterValue | None = None,
        question_category: FilterValue | None = None,
        answer_important: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询投资者问答 QA（insight.qa.list）。

        按单只证券提取互动平台/电话会议/调研纪要中的提问与回答。
        source 问题来源可多选：conference=电话会议 interactive=互动平台
        survey=调研纪要。question_category 问题类型可多选（11 类）：
        productAndBusiness / capacityAndProjects / ordersAndCustomers /
        financialData / materialEvents / capitalOperations /
        shareholdersAndDividends / corporateGovernance / marketAndValuation /
        macroAndIndustry / risksAndOthers（枚举拼错服务端报 100003）。
        answer_important 答案是否涉及重要信息：1=是 0=否（可多选，省略=不筛）。
        start_time/end_time 格式 yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss（字符串直传）。
        行字段：source / publishTime / question / answer / member（回答方身份）/
        securityCode / questionCategory / answerImportant。0.1 积分/条。
        """
        # TS body shape (cli.ts): request keys are BARE (source / questionCategory /
        # answerImportant), not the *List convention.
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "securityCode": security_code,
                "startTime": start_time,
                "endTime": end_time,
                "source": _as_list(source),
                "questionCategory": _as_list(question_category),
                "answerImportant": _as_list(answer_important),
            }
        )
        result = await self._client._call("insight.qa.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def report_image_list(
        self,
        *,
        keyword: str,
        top: int = 10,
        source_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索研报图片（insight.report-image.list）。

        返回 chunkId + 元数据，chunkId 供 report_image_download() 下载原图。
        top 默认 10、上限 20（超限服务端会静默截断，本地先报错）；source_id
        限定到某篇研报（可从研报列表或知识库取）。start_time/end_time 限定
        图片所属研报的发布时间。行字段：chunkId / title / sourceId / broker /
        category / typeList / industry / publishTime / page / totalPages /
        imageCaption / imageFootnote / pageContent。免费。
        """
        body = _strip_none(
            {
                "keyword": keyword,
                "top": _validate_top(top, name="top", max_value=20),
                "sourceId": source_id,
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        result = await self._client._call("insight.report-image.list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def summary_download(
        self,
        *,
        summary_id: str,
        file_type: int | None = None,
        output: str | Path | None = None,
    ) -> Path:
        """下载纪要原文/HTML（insight.summary.download）。

        file_type 取值 1=原文（默认） 2=HTML，仅对会议平台纪要生效。
        """
        query: dict[str, str | int] = {"summaryId": summary_id}
        if file_type is not None:
            query["fileType"] = file_type
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.summary.download",
            query=query,
            output=output,
            fallback_name=f"summary-{summary_id}",
            title_lookup=("insight.summary.list", "summaryId", summary_id),
        )

    async def research_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载国内券商研报（insight.research.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.research.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"research-{report_id}",
            title_lookup=("insight.research.list", "reportId", report_id),
        )

    async def foreign_report_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载海外研报（insight.foreign-report.download）。

        file_type 取值 1=PDF（默认） 2=Markdown 3=中译PDF 4=中译Markdown。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.foreign-report.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"foreign-report-{report_id}",
            title_lookup=("insight.foreign-report.list", "reportId", report_id),
        )

    async def announcement_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载 A 股公告（insight.announcement.download）。

        file_type 取值 1=PDF（默认） 2=Markdown。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.announcement.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-{announcement_id}",
            title_lookup=(
                "insight.announcement.list",
                "announcementId",
                announcement_id,
            ),
        )

    async def announcement_hk_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载港股公告（insight.announcement-hk.download）。

        file_type 取值 1=原文（默认） 2=Markdown。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.announcement-hk.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-hk-{announcement_id}",
            title_lookup=(
                "insight.announcement-hk.list",
                "announcementId",
                announcement_id,
            ),
        )

    async def announcement_us_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载美股公告（insight.announcement-us.download）。

        file_type 取值 1=原文 PDF（默认） 2=Markdown。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.announcement-us.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-us-{announcement_id}",
            title_lookup=(
                "insight.announcement-us.list",
                "announcementId",
                announcement_id,
            ),
        )

    async def independent_opinion_download(
        self,
        *,
        independent_opinion_id: str,
        file_type: int,
        output: str | Path | None = None,
    ) -> Path:
        """下载海外独立分析师观点（insight.independent-opinion.download）。

        file_type 必填，取值 1=原文HTML 2=中译HTML。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.independent-opinion.download",
            query={
                "independentOpinionId": independent_opinion_id,
                "fileType": file_type,
            },
            output=output,
            fallback_name=f"independent-opinion-{independent_opinion_id}",
            title_lookup=(
                "insight.independent-opinion.list",
                "independentOpinionId",
                independent_opinion_id,
            ),
        )

    async def official_account_download(
        self,
        *,
        article_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        """下载产业公众号文章（insight.official-account.download）。

        file_type 取值 1=txt（默认） 2=HTML。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.official-account.download",
            query={"articleId": article_id, "fileType": file_type},
            output=output,
            fallback_name=f"official-account-{article_id}",
            title_lookup=("insight.official-account.list", "articleId", article_id),
        )

    async def report_image_download(
        self,
        *,
        chunk_id: str,
        output: str | Path | None = None,
    ) -> Path:
        """下载研报图片原图（insight.report-image.download）。

        chunk_id 取自 report_image_list() 返回的 chunkId；直接下载二进制
        原图（JPEG）。省略 output 时优先用服务端返回的文件名，无则按
        report-image-<chunkId> 命名。0.1 积分/张。
        """
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.report-image.download",
            query={"chunkId": chunk_id},
            output=output,
            fallback_name=f"report-image-{chunk_id}",
        )
