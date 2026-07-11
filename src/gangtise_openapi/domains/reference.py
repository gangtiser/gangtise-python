# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi.domains._common import (
    FilterValue,
    _result_to_dataframe,
    _strip_none,
    _validate_choices,
    _validate_top,
)

# Server-probed enum whitelists (TS CLI v0.25.0): these endpoints silently ignore
# an unknown category (or return empty) instead of erroring, so typos would
# masquerade as "no results" without a local check.
_SECURITIES_CATEGORIES = ("stock", "dr", "index", "fund")
_INSTITUTION_CATEGORIES = (
    "domesticBroker",
    "foreignInstitution",
    "leadInstitution",
    "opinionInstitution",
    "foreignOpinionInstitution",
)
_OFFICIAL_ACCOUNT_CATEGORIES = ("listedCompany", "broker", "government", "media")


class Reference:
    """`gangtise.reference.*` — reference data lookups."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def securities_search(
        self,
        *,
        keyword: str,
        category: FilterValue | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索证券 GTS 代码（reference.securities-search）。

        category 分类: stock=股票 dr=存托凭证 index=指数 fund=基金；支持单值或列表。
        """
        # TS body shape (cli.ts:503):
        #   { keyword, category: maybeArray(category) | undefined, top: int }
        # category choices the TS CLI enforces: stock/dr/index/fund.
        body = _strip_none(
            {
                "keyword": keyword,
                "category": _validate_choices(
                    category, name="category", allowed=_SECURITIES_CATEGORIES
                ),
                "top": _validate_top(top, name="top", max_value=10),
            }
        )
        result = self._client._call("reference.securities-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def constant_category(
        self,
        *,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """列出常量分类及各分类适用的接口参数（reference.constant-category）。

        无需传参。返回字段：category / categoryName / structureType（flat 平铺
        | tree 树形）/ maxLevel / usageScopes（apiName + paramName）。
        """
        result = self._client._call("reference.constant-category")
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def constant_list(
        self,
        *,
        category: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """列出某分类下的全部常量值（reference.constant-list）。

        category 取值见 constant_category()，如 citicIndustry / swIndustry /
        domesticCity / aShareAnnouncementCategory / regionCategory。
        行字段：constantId / constantName / level；树形分类的父节点含
        children（DataFrame 不展开，需要层级用 raw=True 自行递归）。
        """
        body = {"category": category}
        result = self._client._call("reference.constant-list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def concept_search(
        self,
        *,
        keyword: str,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索题材（概念）ID（reference.concept-search）。

        结果的 conceptId 供 alternative.concept_info / concept_securities 与
        ai.theme_tracking 共用。keyword 支持中文名/拼音/首字母/分组名；
        top 默认 10、上限 10。行字段：conceptId / conceptName / matchScore。
        """
        body = {"keyword": keyword, "top": _validate_top(top, name="top", max_value=10)}
        result = self._client._call("reference.concept-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def sector_search(
        self,
        *,
        keyword: str | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索板块 ID（reference.sector-search）。

        结果的 sectorId 供 sector_constituents() 使用。top 默认 10、上限 10。
        行字段：sectorId / sectorName / hierarchy（层级路径）/ matchScore；
        同名板块可能出现在多个层级，用 hierarchy 区分。
        """
        body = _strip_none(
            {"keyword": keyword, "top": _validate_top(top, name="top", max_value=10)}
        )
        result = self._client._call("reference.sector-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def sector_constituents(
        self,
        *,
        sector_id: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """列出板块的全量成分股（reference.sector-constituents）。

        sector_id 必须来自 sector_search()（题材 conceptId 与板块 sectorId
        是两套 ID，不通用；返回 0 条通常是 ID 体系传错）。行字段：
        gtsCode / gtsName。
        """
        body = {"sectorId": sector_id}
        result = self._client._call("reference.sector-constituents", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def chiefs_search(
        self,
        *,
        keyword: str,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索首席分析师 ID（reference.chiefs-search）。

        keyword 支持首席姓名 / 机构 / 团队；top 默认 10、上限 10。
        结果的 chief ID 供 insight.opinion_list(chief=...) 等按首席筛选使用。
        """
        body = {"keyword": keyword, "top": _validate_top(top, name="top", max_value=10)}
        result = self._client._call("reference.chiefs-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def institution_search(
        self,
        *,
        keyword: str,
        category: FilterValue | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索机构 ID（reference.institution-search）。

        category 机构类型（可单值或列表，省略=全部）: domesticBroker=境内券商,
        foreignInstitution=外资机构, leadInstitution=牵头机构,
        opinionInstitution=观点机构, foreignOpinionInstitution=外资观点机构；
        top 默认 10、上限 10。结果自带 usageScopes 标明每个 ID 适用的接口/参数，
        覆盖各接口的 broker / institution 入参。免费。
        """
        body = _strip_none(
            {
                "keyword": keyword,
                "categoryList": _validate_choices(
                    category, name="category", allowed=_INSTITUTION_CATEGORIES
                ),
                "top": _validate_top(top, name="top", max_value=10),
            }
        )
        result = self._client._call("reference.institution-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def official_account_search(
        self,
        *,
        keyword: str,
        category: FilterValue | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按名称/机构/关键字搜索公众号 ID（reference.official-account-search）。

        结果的 accountId 喂 insight.official_account_list(account_id=...) 拉
        该公众号资讯。category 分类可多选：listedCompany=上市公司
        broker=券商团队 government=政府官方 media=媒体；部分公众号不属这
        四类（category 为 null），一旦传 category 就会漏掉它们，要全量
        （含未分类）就别传。top 默认 10、上限 10；结果按 matchScore（0~1）
        降序。行字段：accountId / accountName / category / matchScore。免费。
        """
        # TS body shape (cli.ts): request key is BARE `category` here (spec),
        # unlike institution-search's `categoryList`.
        body = _strip_none(
            {
                "keyword": keyword,
                "category": _validate_choices(
                    category, name="category", allowed=_OFFICIAL_ACCOUNT_CATEGORIES
                ),
                "top": _validate_top(top, name="top", max_value=10),
            }
        )
        result = self._client._call("reference.official-account-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)


class AsyncReference:
    """Async mirror of `Reference`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def securities_search(
        self,
        *,
        keyword: str,
        category: FilterValue | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索证券 GTS 代码（reference.securities-search）。

        category 分类: stock=股票 dr=存托凭证 index=指数 fund=基金；支持单值或列表。
        """
        body = _strip_none(
            {
                "keyword": keyword,
                "category": _validate_choices(
                    category, name="category", allowed=_SECURITIES_CATEGORIES
                ),
                "top": _validate_top(top, name="top", max_value=10),
            }
        )
        result = await self._client._call("reference.securities-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def constant_category(
        self,
        *,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """列出常量分类及各分类适用的接口参数（reference.constant-category）。

        无需传参。返回字段：category / categoryName / structureType（flat 平铺
        | tree 树形）/ maxLevel / usageScopes（apiName + paramName）。
        """
        result = await self._client._call("reference.constant-category")
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def constant_list(
        self,
        *,
        category: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """列出某分类下的全部常量值（reference.constant-list）。

        category 取值见 constant_category()，如 citicIndustry / swIndustry /
        domesticCity / aShareAnnouncementCategory / regionCategory。
        行字段：constantId / constantName / level；树形分类的父节点含
        children（DataFrame 不展开，需要层级用 raw=True 自行递归）。
        """
        body = {"category": category}
        result = await self._client._call("reference.constant-list", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def concept_search(
        self,
        *,
        keyword: str,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索题材（概念）ID（reference.concept-search）。

        结果的 conceptId 供 alternative.concept_info / concept_securities 与
        ai.theme_tracking 共用。keyword 支持中文名/拼音/首字母/分组名；
        top 默认 10、上限 10。行字段：conceptId / conceptName / matchScore。
        """
        body = {"keyword": keyword, "top": _validate_top(top, name="top", max_value=10)}
        result = await self._client._call("reference.concept-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def sector_search(
        self,
        *,
        keyword: str | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索板块 ID（reference.sector-search）。

        结果的 sectorId 供 sector_constituents() 使用。top 默认 10、上限 10。
        行字段：sectorId / sectorName / hierarchy（层级路径）/ matchScore；
        同名板块可能出现在多个层级，用 hierarchy 区分。
        """
        body = _strip_none(
            {"keyword": keyword, "top": _validate_top(top, name="top", max_value=10)}
        )
        result = await self._client._call("reference.sector-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def sector_constituents(
        self,
        *,
        sector_id: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """列出板块的全量成分股（reference.sector-constituents）。

        sector_id 必须来自 sector_search()（题材 conceptId 与板块 sectorId
        是两套 ID，不通用；返回 0 条通常是 ID 体系传错）。行字段：
        gtsCode / gtsName。
        """
        body = {"sectorId": sector_id}
        result = await self._client._call("reference.sector-constituents", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def chiefs_search(
        self,
        *,
        keyword: str,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索首席分析师 ID（reference.chiefs-search）。

        keyword 支持首席姓名 / 机构 / 团队；top 默认 10、上限 10。
        结果的 chief ID 供 insight.opinion_list(chief=...) 等按首席筛选使用。
        """
        body = {"keyword": keyword, "top": _validate_top(top, name="top", max_value=10)}
        result = await self._client._call("reference.chiefs-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def institution_search(
        self,
        *,
        keyword: str,
        category: FilterValue | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索机构 ID（reference.institution-search）。

        category 机构类型（可单值或列表，省略=全部）: domesticBroker=境内券商,
        foreignInstitution=外资机构, leadInstitution=牵头机构,
        opinionInstitution=观点机构, foreignOpinionInstitution=外资观点机构；
        top 默认 10、上限 10。结果自带 usageScopes 标明每个 ID 适用的接口/参数，
        覆盖各接口的 broker / institution 入参。免费。
        """
        body = _strip_none(
            {
                "keyword": keyword,
                "categoryList": _validate_choices(
                    category, name="category", allowed=_INSTITUTION_CATEGORIES
                ),
                "top": _validate_top(top, name="top", max_value=10),
            }
        )
        result = await self._client._call("reference.institution-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def official_account_search(
        self,
        *,
        keyword: str,
        category: FilterValue | None = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按名称/机构/关键字搜索公众号 ID（reference.official-account-search）。

        结果的 accountId 喂 insight.official_account_list(account_id=...) 拉
        该公众号资讯。category 分类可多选：listedCompany=上市公司
        broker=券商团队 government=政府官方 media=媒体；部分公众号不属这
        四类（category 为 null），一旦传 category 就会漏掉它们，要全量
        （含未分类）就别传。top 默认 10、上限 10；结果按 matchScore（0~1）
        降序。行字段：accountId / accountName / category / matchScore。免费。
        """
        # TS body shape (cli.ts): request key is BARE `category` here (spec),
        # unlike institution-search's `categoryList`.
        body = _strip_none(
            {
                "keyword": keyword,
                "category": _validate_choices(
                    category, name="category", allowed=_OFFICIAL_ACCOUNT_CATEGORIES
                ),
                "top": _validate_top(top, name="top", max_value=10),
            }
        )
        result = await self._client._call("reference.official-account-search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)
