from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._download import download_to_path
from gangtise_openapi._normalize import to_dataframe


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


def _to_unix_ms(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)


def _extract_rows(result: Any) -> list[Any]:
    if isinstance(result, dict):
        rows = result.get("list", [])
        if isinstance(rows, list):
            return rows
    return []


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
        body = _strip_none({
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
        })
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
        body = _strip_none({
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
        })
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
        raw: bool,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none({
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
        })
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._schedule_list(
            "insight.roadshow.list",
            from_=from_, size=size, start_time=start_time, end_time=end_time,
            keyword=keyword, research_area=research_area, institution=institution,
            security=security, category=category, market=market,
            participant_role=participant_role, broker_type=broker_type,
            object_=object_, permission=permission, raw=raw,
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._schedule_list(
            "insight.site-visit.list",
            from_=from_, size=size, start_time=start_time, end_time=end_time,
            keyword=keyword, research_area=research_area, institution=institution,
            security=security, category=category, market=market,
            participant_role=participant_role, broker_type=broker_type,
            object_=object_, permission=permission, raw=raw,
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._schedule_list(
            "insight.strategy.list",
            from_=from_, size=size, start_time=start_time, end_time=end_time,
            keyword=keyword, research_area=research_area, institution=institution,
            security=security, category=category, market=market,
            participant_role=participant_role, broker_type=broker_type,
            object_=object_, permission=permission, raw=raw,
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._schedule_list(
            "insight.forum.list",
            from_=from_, size=size, start_time=start_time, end_time=end_time,
            keyword=keyword, research_area=research_area, institution=institution,
            security=security, category=category, market=market,
            participant_role=participant_role, broker_type=broker_type,
            object_=object_, permission=permission, raw=raw,
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
        body = _strip_none({
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
        })
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
        body = _strip_none({
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
        })
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
        body = _strip_none({
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
        })
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
        body = _strip_none({
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
        })
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
        body = _strip_none({
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
        })
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
        body = _strip_none({
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
        })
        result = self._client._call("insight.independent-opinion.list", body=body)
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
        return download_to_path(
            client=self._client,
            endpoint_key="insight.independent-opinion.download",
            query={
                "independentOpinionId": independent_opinion_id,
                "fileType": file_type,
            },
            output=output,
            fallback_name=f"independent-opinion-{independent_opinion_id}",
            title_lookup=None,
        )
