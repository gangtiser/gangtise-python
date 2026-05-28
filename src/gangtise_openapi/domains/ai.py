from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._async_content import poll_content
from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import ApiError
from gangtise_openapi._normalize import to_dataframe

_HOT_TOPIC_DEFAULT_CATEGORIES = [
    "morningBriefing",
    "noonBriefing",
    "afternoonFlash",
    "eveningBriefing",
]


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


def _extract_rows(result: Any) -> list[Any]:
    if isinstance(result, dict):
        rows = result.get("list", [])
        return rows if isinstance(rows, list) else []
    if isinstance(result, list):
        return result
    return []


class AI:
    """`gangtise.ai.*` — AI-generated insights and structured outputs."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    # ---- knowledge-batch ----

    def knowledge_batch(
        self,
        *,
        query: Any,
        top: int = 10,
        resource_type: Any = None,
        knowledge_name: Any = None,
        start_time: int | None = None,
        end_time: int | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
            {
                "queries": _as_list(query),
                "top": top,
                "resourceTypes": _as_list(resource_type),
                "knowledgeNames": _as_list(knowledge_name),
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        result = self._client._call("ai.knowledge-batch", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- security-clue.list ----

    def security_clue_list(
        self,
        *,
        start_time: str,
        end_time: str,
        query_mode: str,
        from_: int = 0,
        size: int | None = None,
        gts_code: Any = None,
        source: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- security-only agent endpoints ----

    def _security_only(self, endpoint_key: str, security_code: str) -> Any:
        return self._client._call(endpoint_key, body={"securityCode": security_code})

    def one_pager(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        return self._security_only("ai.one-pager", security_code)  # type: ignore[no-any-return]

    def investment_logic(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        return self._security_only("ai.investment-logic", security_code)  # type: ignore[no-any-return]

    def peer_comparison(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        return self._security_only("ai.peer-comparison", security_code)  # type: ignore[no-any-return]

    def research_outline(self, *, security_code: str, raw: bool = False) -> dict[str, Any]:
        return self._security_only("ai.research-outline", security_code)  # type: ignore[no-any-return]

    # ---- theme-tracking ----

    def theme_tracking(
        self,
        *,
        theme_id: str,
        date: str,
        type_: Any = None,
        raw: bool = False,
    ) -> dict[str, Any]:
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
        category: Any = None,
        with_related_securities: bool = True,
        with_close_reading: bool = True,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
            {
                "from": from_,
                "size": size,
                "startDate": start_date,
                "endDate": end_date,
                "categoryList": _as_list(category) or _HOT_TOPIC_DEFAULT_CATEGORIES,
                "withRelatedSecurities": True if with_related_securities else None,
                "withCloseReading": True if with_close_reading else None,
            }
        )
        result = self._client._call("ai.hot-topic", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- management-discuss ----

    def management_discuss_announcement(
        self,
        *,
        report_date: str,
        security_code: str,
        dimension: str,
        raw: bool = False,
    ) -> dict[str, Any]:
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
        period: str,           # e.g. "2025q3", "2025interim", "2025annual"
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
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
            return self._client._call(
                "ai.earnings-review.get-content", body={"dataId": data_id}
            )

        return poll_content(fetch)  # type: ignore[no-any-return]

    def earnings_review_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """Non-blocking single check. Returns whatever the server returns
        (including `{"content": null}` for still-pending). Does NOT raise on
        pending; callers handle that.
        """
        return self._client._call(  # type: ignore[no-any-return]
            "ai.earnings-review.get-content", body={"dataId": data_id}
        )

    def viewpoint_debate(
        self,
        *,
        viewpoint: str,        # max 1000 chars
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        id_result = self._client._call(
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

        def fetch() -> Any:
            return self._client._call(
                "ai.viewpoint-debate.get-content", body={"dataId": data_id}
            )

        return poll_content(fetch)  # type: ignore[no-any-return]

    def viewpoint_debate_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        return self._client._call(  # type: ignore[no-any-return]
            "ai.viewpoint-debate.get-content", body={"dataId": data_id}
        )
