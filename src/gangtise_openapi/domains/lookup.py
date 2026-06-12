# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe

_LOOKUP_ENDPOINT_BY_METHOD: dict[str, tuple[str, list[str]]] = {
    "research_areas": ("lookup.research-areas.list", ["id", "name"]),
    "broker_orgs": ("lookup.broker-orgs.list", ["id", "name"]),
    "meeting_orgs": ("lookup.meeting-orgs.list", ["id", "name"]),
    "industries": ("lookup.industries.list", ["id", "name", "taxonomy"]),
    "regions": ("lookup.regions.list", ["id", "name"]),
    "announcement_categories": (
        "lookup.announcement-categories.list",
        ["id", "name", "level", "parentId"],
    ),
    "industry_codes": ("lookup.industry-codes.list", ["name", "code"]),
    "theme_ids": ("lookup.theme-ids.list", ["id", "name"]),
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

    def research_areas(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出研究领域（lookup.research-areas.list）。本地数据、不发请求。"""
        return self._fetch("research_areas", raw=raw)

    def broker_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出券商机构（lookup.broker-orgs.list）。本地数据、不发请求。"""
        return self._fetch("broker_orgs", raw=raw)

    def meeting_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出会议机构（lookup.meeting-orgs.list）。本地数据、不发请求。"""
        return self._fetch("meeting_orgs", raw=raw)

    def industries(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出行业分类（lookup.industries.list）。本地数据、不发请求。"""
        return self._fetch("industries", raw=raw)

    def regions(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出地区（lookup.regions.list）。本地数据、不发请求。"""
        return self._fetch("regions", raw=raw)

    def announcement_categories(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出公告分类（lookup.announcement-categories.list）。本地数据、不发请求。"""
        return self._fetch("announcement_categories", raw=raw)

    def industry_codes(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出申万行业代码（lookup.industry-codes.list）。本地数据、不发请求。"""
        return self._fetch("industry_codes", raw=raw)

    def theme_ids(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出题材 ID（lookup.theme-ids.list）。本地数据、不发请求。"""
        return self._fetch("theme_ids", raw=raw)


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

    async def research_areas(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出研究领域（lookup.research-areas.list）。本地数据、不发请求。"""
        return await self._fetch("research_areas", raw=raw)

    async def broker_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出券商机构（lookup.broker-orgs.list）。本地数据、不发请求。"""
        return await self._fetch("broker_orgs", raw=raw)

    async def meeting_orgs(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出会议机构（lookup.meeting-orgs.list）。本地数据、不发请求。"""
        return await self._fetch("meeting_orgs", raw=raw)

    async def industries(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出行业分类（lookup.industries.list）。本地数据、不发请求。"""
        return await self._fetch("industries", raw=raw)

    async def regions(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出地区（lookup.regions.list）。本地数据、不发请求。"""
        return await self._fetch("regions", raw=raw)

    async def announcement_categories(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出公告分类（lookup.announcement-categories.list）。本地数据、不发请求。"""
        return await self._fetch("announcement_categories", raw=raw)

    async def industry_codes(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出申万行业代码（lookup.industry-codes.list）。本地数据、不发请求。"""
        return await self._fetch("industry_codes", raw=raw)

    async def theme_ids(self, *, raw: bool = False) -> pd.DataFrame | list[Any]:
        """列出题材 ID（lookup.theme-ids.list）。本地数据、不发请求。"""
        return await self._fetch("theme_ids", raw=raw)
