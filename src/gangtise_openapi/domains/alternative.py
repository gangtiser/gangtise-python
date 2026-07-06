# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _result_to_dataframe,
    _strip_none,
)

# Stable columns for the flattened concept-securities frame. Used only to shape
# the *empty* result (a concept with no constituents) so the columns match the
# non-empty case; the non-empty path stays schema=None to pass through any
# field the API adds later.
_CONCEPT_SECURITIES_COLUMNS = [
    "groupName",
    "securityCode",
    "securityName",
    "isKey",
    "inclusionReason",
]


def _flatten_concept_securities(result: Any) -> list[dict[str, Any]] | None:
    """Flatten the grouped concept-securities payload to one row per security.

    The API returns ``{securityDetail: [{groupName, securityList: [{...}]}]}``.
    Each constituent dict is emitted with its ``groupName`` injected as the
    leading field (``groupName, securityCode, securityName, isKey,
    inclusionReason``).

    A concept with no constituents returns a successful payload whose
    ``securityDetail`` is ``null`` (or absent) — a valid empty result, so it
    yields an empty row list (``[]``), not ``None``. ``None`` is reserved for
    genuinely unexpected shapes (non-dict payload, or a ``securityDetail`` that
    is neither a list nor null), letting the caller fall back to the raw payload.
    """
    if not isinstance(result, dict):
        return None
    groups = result.get("securityDetail")
    if groups is None:
        return []
    if not isinstance(groups, list):
        return None
    rows: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_name = group.get("groupName")
        securities = group.get("securityList")
        if not isinstance(securities, list):
            continue
        for security in securities:
            if isinstance(security, dict):
                rows.append({"groupName": group_name, **security})
    return rows


class Alternative:
    """`gangtise.alternative.*` — economic indicators (EDB) + concept (theme) index."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def edb_search(
        self,
        *,
        keyword: str,
        limit: int = 100,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按关键词搜索行业指标（EDB）列表（alternative.edb-search）。"""
        body = {"keyword": keyword, "limit": limit}
        result = self._client._call("alternative.edb-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def edb_data(
        self,
        *,
        indicator_id: FilterValue,
        start_date: str,
        end_date: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按指标 ID 列表查询行业指标时间序列（alternative.edb-data）。"""
        body = _strip_none(
            {
                "indicatorIdList": _as_list(indicator_id),
                "startDate": start_date,
                "endDate": end_date,
            }
        )
        result = self._client._call("alternative.edb-data", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        if (
            isinstance(result, dict)
            and isinstance(result.get("fieldList"), list)
            and isinstance(result.get("dataList"), list)
        ):
            fields: list[str] = list(result["fieldList"])
            rows = [
                {field: row[i] for i, field in enumerate(fields)}
                for row in result["dataList"]
                if isinstance(row, list)
            ]
            return to_dataframe(rows, schema=fields)
        # Fallback: shape doesn't match — return raw.
        return result  # type: ignore[no-any-return]

    def concept_info(self, *, concept_id: str, raw: bool = False) -> dict[str, Any]:
        """查询概念（题材指数）最新画像：定义/投资逻辑/行业空间/竞争格局/keyEvents（alternative.concept-info）。

        concept_id 与题材 ID 共用体系，可用 reference.concept_search() 按名查询（机器人=121000130）。
        返回最新截面对象 dict（raw 仅为签名统一，返回相同）。
        """
        return self._client._call(  # type: ignore[no-any-return]
            "alternative.concept-info", body={"conceptId": concept_id}
        )

    def concept_securities(
        self, *, concept_id: str, raw: bool = False
    ) -> pd.DataFrame | dict[str, Any]:
        """查询概念（题材指数）成分股，按分组返回（alternative.concept-securities）。

        默认扁平化为每行一只成分股的 DataFrame（含 groupName/isKey/inclusionReason 列）；
        raw=True 返回嵌套分组原始 payload。concept_id 见 reference.concept_search()。
        """
        result = self._client._call(
            "alternative.concept-securities", body={"conceptId": concept_id}
        )
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _flatten_concept_securities(result)
        if rows is None:
            return result  # type: ignore[no-any-return]
        if not rows:
            # Valid empty concept — keep the documented columns so downstream
            # access stays stable across empty/non-empty results.
            return to_dataframe([], schema=_CONCEPT_SECURITIES_COLUMNS)
        return to_dataframe(rows, schema=None)


class AsyncAlternative:
    """Async mirror of `Alternative`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def edb_search(
        self,
        *,
        keyword: str,
        limit: int = 100,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按关键词搜索行业指标（EDB）列表（alternative.edb-search）。"""
        body = {"keyword": keyword, "limit": limit}
        result = await self._client._call("alternative.edb-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def edb_data(
        self,
        *,
        indicator_id: FilterValue,
        start_date: str,
        end_date: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """按指标 ID 列表查询行业指标时间序列（alternative.edb-data）。"""
        body = _strip_none(
            {
                "indicatorIdList": _as_list(indicator_id),
                "startDate": start_date,
                "endDate": end_date,
            }
        )
        result = await self._client._call("alternative.edb-data", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        if (
            isinstance(result, dict)
            and isinstance(result.get("fieldList"), list)
            and isinstance(result.get("dataList"), list)
        ):
            fields: list[str] = list(result["fieldList"])
            rows = [
                {field: row[i] for i, field in enumerate(fields)}
                for row in result["dataList"]
                if isinstance(row, list)
            ]
            return to_dataframe(rows, schema=fields)
        return result  # type: ignore[no-any-return]

    async def concept_info(self, *, concept_id: str, raw: bool = False) -> dict[str, Any]:
        """查询概念（题材指数）最新画像：定义/投资逻辑/行业空间/竞争格局/keyEvents（alternative.concept-info）。

        concept_id 与题材 ID 共用体系，可用 reference.concept_search() 按名查询（机器人=121000130）。
        返回最新截面对象 dict（raw 仅为签名统一，返回相同）。
        """
        return await self._client._call(  # type: ignore[no-any-return]
            "alternative.concept-info", body={"conceptId": concept_id}
        )

    async def concept_securities(
        self, *, concept_id: str, raw: bool = False
    ) -> pd.DataFrame | dict[str, Any]:
        """查询概念（题材指数）成分股，按分组返回（alternative.concept-securities）。

        默认扁平化为每行一只成分股的 DataFrame（含 groupName/isKey/inclusionReason 列）；
        raw=True 返回嵌套分组原始 payload。concept_id 见 reference.concept_search()。
        """
        result = await self._client._call(
            "alternative.concept-securities", body={"conceptId": concept_id}
        )
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _flatten_concept_securities(result)
        if rows is None:
            return result  # type: ignore[no-any-return]
        if not rows:
            # Valid empty concept — keep the documented columns so downstream
            # access stays stable across empty/non-empty results.
            return to_dataframe([], schema=_CONCEPT_SECURITIES_COLUMNS)
        return to_dataframe(rows, schema=None)
