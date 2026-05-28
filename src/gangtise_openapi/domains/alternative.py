from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


class Alternative:
    """`gangtise.alternative.*` — economic indicators (EDB)."""

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
        body = _strip_none({
            "indicatorIdList": _as_list(indicator_id),
            "startDate": start_date,
            "endDate": end_date,
        })
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
        body = _strip_none({
            "indicatorIdList": _as_list(indicator_id),
            "startDate": start_date,
            "endDate": end_date,
        })
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
