from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import _as_list, _strip_none

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
        body = {"keyword": keyword, "limit": limit}
        result = self._client._call("alternative.edb-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows: list[Any]
        if isinstance(result, dict):
            maybe_rows = result.get("list", [])
            rows = maybe_rows if isinstance(maybe_rows, list) else []
        elif isinstance(result, list):
            rows = result
        else:
            rows = []
        return to_dataframe(rows, schema=None)

    def edb_data(
        self,
        *,
        indicator_id: Any,
        start_date: str,
        end_date: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        """Latest profile of a concept (theme index): definition, investment
        logic, industry space, competitive landscape, and ``keyEvents``.

        ``concept_id`` shares the theme-id namespace — discover it by name via
        ``gangtise.lookup.theme_ids()`` (e.g. 机器人 → ``121000130``). The
        response is a single cross-section object, so it is returned as a dict
        (``raw`` is accepted for signature uniformity; the return is the same).
        """
        return self._client._call(  # type: ignore[no-any-return]
            "alternative.concept-info", body={"conceptId": concept_id}
        )

    def concept_securities(
        self, *, concept_id: str, raw: bool = False
    ) -> pd.DataFrame | dict[str, Any]:
        """Constituent securities of a concept (theme index), grouped.

        Each security carries ``isKey`` (key-stock flag) and ``inclusionReason``.
        The default DataFrame flattens the groups one-row-per-security with a
        ``groupName`` column; ``raw=True`` returns the nested grouped payload.
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
        body = {"keyword": keyword, "limit": limit}
        result = await self._client._call("alternative.edb-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows: list[Any]
        if isinstance(result, dict):
            maybe_rows = result.get("list", [])
            rows = maybe_rows if isinstance(maybe_rows, list) else []
        elif isinstance(result, list):
            rows = result
        else:
            rows = []
        return to_dataframe(rows, schema=None)

    async def edb_data(
        self,
        *,
        indicator_id: Any,
        start_date: str,
        end_date: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        """Async mirror of `Alternative.concept_info`."""
        return await self._client._call(  # type: ignore[no-any-return]
            "alternative.concept-info", body={"conceptId": concept_id}
        )

    async def concept_securities(
        self, *, concept_id: str, raw: bool = False
    ) -> pd.DataFrame | dict[str, Any]:
        """Async mirror of `Alternative.concept_securities`."""
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
