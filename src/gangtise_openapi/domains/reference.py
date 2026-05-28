from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe

_SCHEMA_SECURITIES_SEARCH = [
    "code",
    "name",
    "market",
    "category",
    "industry",
    "industryCode",
    "pinyin",
]


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


class Reference:
    """`gangtise.reference.*` — reference data lookups."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def securities_search(
        self,
        *,
        keyword: str,
        category: Any = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        # TS body shape (cli.ts:503):
        #   { keyword, category: maybeArray(category) | undefined, top: int }
        # category choices the TS CLI enforces: stock/dr/index/fund.
        body = _strip_none({
            "keyword": keyword,
            "category": _as_list(category),
            "top": top,
        })
        result = self._client._call("reference.securities-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        if isinstance(result, list):
            rows: list[Any] = result
        elif isinstance(result, dict):
            rows = result.get("list", [])
        else:
            rows = []
        return to_dataframe(rows, schema=_SCHEMA_SECURITIES_SEARCH)


class AsyncReference:
    """Async mirror of `Reference`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def securities_search(
        self,
        *,
        keyword: str,
        category: Any = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        body = _strip_none({
            "keyword": keyword,
            "category": _as_list(category),
            "top": top,
        })
        result = await self._client._call("reference.securities-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        if isinstance(result, list):
            rows: list[Any] = result
        elif isinstance(result, dict):
            rows = result.get("list", [])
        else:
            rows = []
        return to_dataframe(rows, schema=_SCHEMA_SECURITIES_SEARCH)
