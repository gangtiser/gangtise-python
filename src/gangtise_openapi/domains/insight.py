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
from gangtise_openapi.domains._common import _as_list, _extract_rows, _strip_none


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
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            # Naive datetime string: local timezone, matching `new Date()` in the CLI.
            parsed = parsed.astimezone()
        else:
            # Date-only string: UTC midnight, matching `new Date("YYYY-MM-DD")`.
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
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
        research_area: Any = None,
        chief: Any = None,
        security: Any = None,
        broker: Any = None,
        industry: Any = None,
        concept: Any = None,
        llm_tag: Any = None,
        source: Any = None,
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
        return to_dataframe(_extract_rows(result), schema=None)

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
        source: Any = None,
        research_area: Any = None,
        security: Any = None,
        institution: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
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

    # ---- schedule helpers (roadshow / site-visit / strategy / forum) ----

    def _schedule_list(
        self,
        endpoint_key: str,
        *,
        from_: int,
        size: int | None,
        start_time: str | None,
        end_time: str | None,
        keyword: str | None,
        research_area: Any,
        institution: Any,
        security: Any,
        category: Any,
        market: Any,
        participant_role: Any,
        broker_type: Any,
        object_: Any,
        permission: Any,
        location: Any,
        raw: bool,
    ) -> pd.DataFrame | dict[str, Any]:
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
                "objectList": _as_list(object_),
                "permission": _as_list(permission),
                "locationList": _as_list(location),
            }
        )
        result = self._client._call(endpoint_key, body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    def roadshow_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询路演日程列表（insight.roadshow.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return self._schedule_list(
            "insight.roadshow.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

    def site_visit_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询调研/实地走访日程列表（insight.site-visit.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return self._schedule_list(
            "insight.site-visit.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

    def strategy_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询策略会日程列表（insight.strategy.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return self._schedule_list(
            "insight.strategy.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

    def forum_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询论坛/电话会日程列表（insight.forum.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return self._schedule_list(
            "insight.forum.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

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
        broker: Any = None,
        security: Any = None,
        industry: Any = None,
        category: Any = None,
        llm_tag: Any = None,
        rating: Any = None,
        rating_change: Any = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        source: Any = None,
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
        security: Any = None,
        region: Any = None,
        category: Any = None,
        industry: Any = None,
        broker: Any = None,
        llm_tag: Any = None,
        rating: Any = None,
        rating_change: Any = None,
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
        security: Any = None,
        announcement_type: Any = None,
        category: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股公告列表（insight.announcement.list）。

        start_time/end_time 接受日期字符串或 13 位毫秒时间戳。
        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
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
                "announcementTypeList": _as_list(announcement_type),
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
        security: Any = None,
        announcement_type: Any = None,
        category: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股公告列表（insight.announcement-hk.list）。

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
                "announcementTypeList": _as_list(announcement_type),
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
        security: Any = None,
        region: Any = None,
        industry: Any = None,
        broker: Any = None,
        rating: Any = None,
        rating_change: Any = None,
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
        return to_dataframe(_extract_rows(result), schema=None)

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
        security: Any = None,
        industry: Any = None,
        rating: Any = None,
        rating_change: Any = None,
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
        output: str | Path | None = None,
    ) -> Path:
        """下载港股公告（insight.announcement-hk.download）。"""
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement-hk.download",
            query={"announcementId": announcement_id},
            output=output,
            fallback_name=f"announcement-hk-{announcement_id}",
            title_lookup=("insight.announcement-hk.list", "announcementId", announcement_id),
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
        research_area: Any = None,
        chief: Any = None,
        security: Any = None,
        broker: Any = None,
        industry: Any = None,
        concept: Any = None,
        llm_tag: Any = None,
        source: Any = None,
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
        return to_dataframe(_extract_rows(result), schema=None)

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
        source: Any = None,
        research_area: Any = None,
        security: Any = None,
        institution: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
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

    async def _schedule_list(
        self,
        endpoint_key: str,
        *,
        from_: int,
        size: int | None,
        start_time: str | None,
        end_time: str | None,
        keyword: str | None,
        research_area: Any,
        institution: Any,
        security: Any,
        category: Any,
        market: Any,
        participant_role: Any,
        broker_type: Any,
        object_: Any,
        permission: Any,
        location: Any,
        raw: bool,
    ) -> pd.DataFrame | dict[str, Any]:
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
                "objectList": _as_list(object_),
                "permission": _as_list(permission),
                "locationList": _as_list(location),
            }
        )
        result = await self._client._call(endpoint_key, body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    async def roadshow_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询路演日程列表（insight.roadshow.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return await self._schedule_list(
            "insight.roadshow.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

    async def site_visit_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询调研/实地走访日程列表（insight.site-visit.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return await self._schedule_list(
            "insight.site-visit.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

    async def strategy_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询策略会日程列表（insight.strategy.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return await self._schedule_list(
            "insight.strategy.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

    async def forum_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        research_area: Any = None,
        institution: Any = None,
        security: Any = None,
        category: Any = None,
        market: Any = None,
        participant_role: Any = None,
        broker_type: Any = None,
        object_: Any = None,
        permission: Any = None,
        location: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询论坛/电话会日程列表（insight.forum.list）。

        object_ 取值 company=公司 / industry=行业（映射为请求字段 object）；market 例如 SH/SZ/HK/US；
        location 为城市/省份 ID（用 reference.constant_list(category="domesticCity") 查询）。
        """
        return await self._schedule_list(
            "insight.forum.list",
            from_=from_,
            size=size,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            research_area=research_area,
            institution=institution,
            security=security,
            category=category,
            market=market,
            participant_role=participant_role,
            broker_type=broker_type,
            object_=object_,
            permission=permission,
            location=location,
            raw=raw,
        )

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
        broker: Any = None,
        security: Any = None,
        industry: Any = None,
        category: Any = None,
        llm_tag: Any = None,
        rating: Any = None,
        rating_change: Any = None,
        min_pages: int | None = None,
        max_pages: int | None = None,
        source: Any = None,
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
        security: Any = None,
        region: Any = None,
        category: Any = None,
        industry: Any = None,
        broker: Any = None,
        llm_tag: Any = None,
        rating: Any = None,
        rating_change: Any = None,
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
        security: Any = None,
        announcement_type: Any = None,
        category: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股公告列表（insight.announcement.list）。

        start_time/end_time 接受日期字符串或 13 位毫秒时间戳。
        search_type 取值 1=标题 2=全文；rank_type 取值 1=综合 2=时间倒序。
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
                "announcementTypeList": _as_list(announcement_type),
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
        security: Any = None,
        announcement_type: Any = None,
        category: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股公告列表（insight.announcement-hk.list）。

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
                "announcementTypeList": _as_list(announcement_type),
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

    async def foreign_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: Any = None,
        region: Any = None,
        industry: Any = None,
        broker: Any = None,
        rating: Any = None,
        rating_change: Any = None,
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
        return to_dataframe(_extract_rows(result), schema=None)

    async def independent_opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        security: Any = None,
        industry: Any = None,
        rating: Any = None,
        rating_change: Any = None,
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
        output: str | Path | None = None,
    ) -> Path:
        """下载港股公告（insight.announcement-hk.download）。"""
        return await download_to_path_async(
            client=self._client,
            endpoint_key="insight.announcement-hk.download",
            query={"announcementId": announcement_id},
            output=output,
            fallback_name=f"announcement-hk-{announcement_id}",
            title_lookup=(
                "insight.announcement-hk.list",
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
