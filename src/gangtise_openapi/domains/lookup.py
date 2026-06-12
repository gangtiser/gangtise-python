# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe

# v0.16.0 of the TS CLI retired the API-covered local tables (research areas,
# industries, regions, announcement categories, Shenwan industry codes, theme
# IDs) — those IDs are now served by `gangtise.reference.*` (constant_list /
# concept_search / sector_constituents). Only IDs without API coverage remain
# bundled here.
_LOOKUP_ENDPOINT_BY_METHOD: dict[str, tuple[str, list[str]]] = {
    "broker_orgs": ("lookup.broker-orgs.list", ["id", "name"]),
    "meeting_orgs": ("lookup.meeting-orgs.list", ["id", "name"]),
}


class Lookup:
    """`gangtise.lookup.*` — local lookup tables (no network)."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def _fetch(self, method_name: str, *, raw: bool) -> pd.DataFrame | list[Any]:
        endpoint_key, schema = _LOOKUP_ENDPOINT_BY_METHOD[method_name]
        data = self._client._call(endpoint_key)
        if raw:
            return list(data)
        return to_dataframe(data, schema=schema)

    def broker_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出券商机构（lookup.broker-orgs.list）。本地数据、不发请求。"""
        return self._fetch("broker_orgs", raw=raw)

    def meeting_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出会议机构（lookup.meeting-orgs.list）。本地数据、不发请求。"""
        return self._fetch("meeting_orgs", raw=raw)


class AsyncLookup:
    """Async mirror of `Lookup`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def _fetch(self, method_name: str, *, raw: bool) -> pd.DataFrame | list[Any]:
        endpoint_key, schema = _LOOKUP_ENDPOINT_BY_METHOD[method_name]
        data = await self._client._call(endpoint_key)
        if raw:
            return list(data)
        return to_dataframe(data, schema=schema)

    async def broker_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出券商机构（lookup.broker-orgs.list）。本地数据、不发请求。"""
        return await self._fetch("broker_orgs", raw=raw)

    async def meeting_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出会议机构（lookup.meeting-orgs.list）。本地数据、不发请求。"""
        return await self._fetch("meeting_orgs", raw=raw)
