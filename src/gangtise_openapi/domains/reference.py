# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_named_list,
    _request_body,
    _result_to_dataframe,
    _validate_choices,
    _validate_date,
    _validate_top,
)

# Server-probed enum whitelists (TS CLI v0.25.0): these endpoints silently ignore
# an unknown category (or return empty) instead of erroring, so typos would
# masquerade as "no results" without a local check.
_SECURITIES_CATEGORIES = ("stock", "dr", "index", "fund", "bond")
_INSTITUTION_CATEGORIES = (
    "domesticBroker",
    "foreignInstitution",
    "leadInstitution",
    "opinionInstitution",
    "foreignOpinionInstitution",
)
_OFFICIAL_ACCOUNT_CATEGORIES = ("listedCompany", "broker", "government", "media")


def _index_weight_body(index: Any, date: Any) -> dict[str, Any]:
    return _request_body(
        {"indexCodeList": _as_named_list(index, "index"), "tradeDate": _validate_date(date, "date")}
    )


def _note_missing_indices(data: Any, body: dict[str, Any]) -> None:
    """Warn which requested indices came back without a row. The endpoint answers an
    unknown code, a non-trading day and a date it holds no weights for alike — an empty
    list, no error — and in the dates the CLI sampled (2026-11-07) it held weights for
    month-end trading days only, so an empty answer otherwise reads as "this index has no
    constituents" (TS v0.51.0)."""
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return
    # The server reads a code case-insensitively and answers it upper-case.
    found = {str(row.get("indexCode")).upper() for row in rows if isinstance(row, dict)}
    missing = [code for code in body.get("indexCodeList", []) if str(code).upper() not in found]
    if missing:
        warnings.warn(
            f"reference.index_weight: no constituent weights for {', '.join(map(str, missing))} "
            f"on {body['tradeDate']}. Weights come for the last trading day of each month — "
            "another date, like an unknown index code, comes back empty without an error. "
            "Check the date, and the code with "
            'reference.securities_search(category="index").',
            stacklevel=3,
        )


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

        category 分类: stock=股票 dr=存托凭证 index=指数 fund=基金 bond=债券；支持单值或列表。
        bond 覆盖交易所可转债、国债、地方债、金融债与银行间债券（后缀 .SH / .SZ / .IB），按
        代码或简称查；债券代码用于 gangtise.bond，quote、公告等其余方法不收债券代码（传了报
        120001）。fund 同时返回场内（.SH / .SZ）与场外（.OF）代码，同一基金的不同份额一起
        返回，按 gtsName 区分后取一个。

        🔴 **可转债在任何 category 下都可能出现**：按公司简称查 stock 时，同名可转债常排第一
        （「甬金」→ 113636.SH 甬金转债在 603995.SH 甬金股份之前）。**取第一条 category 等于
        所查类别的行**，别直接取第一行；查基金同理——债券代码传给 fund 方法返回空结果、不报错。
        """
        # TS body shape (cli.ts:503):
        #   { keyword, category: maybeArray(category) | undefined, top: int }
        # category choices the TS CLI enforces: stock/dr/index/fund/bond.
        body = _request_body(
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
        body = _request_body(
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

    def index_weight(
        self,
        *,
        index: FilterValue,
        date: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """指数成分股及权重（reference.index-weight），免费。

        - index: 指数代码（必填），单值或列表，如 000300.SH 沪深300、000905.SH 中证500、
          000852.SH 中证1000、000016.SH 上证50、000688.SH 科创50、399006.SZ 创业板指；不确定用
          reference.securities_search(keyword=<指数名>, category="index")。
        - date: 单个交易日（必填）。🔴 **只有每月最后一个交易日有数**（如 2026-09-30、
          2026-10-30）——其他交易日、非交易日与写错的指数代码都返回空结果、不报错，SDK 发
          UserWarning 点名没取到数据的指数。要「最新」权重就取上个月最后一个交易日；超出账号
          可查范围报 110003。

        不分页、不限条数：一次返回所选指数当日的全部成分股，多个指数合在同一张表里，按
        indexCode 区分。行字段：indexCode / indexName / tradeDate / securityCode / securityName /
        weight（**单位 %**，最多四位小数）。同一指数的权重合计约为 100，受舍入影响不严格等于
        100，校验合计时留容差。sector_constituents 是板块的纯成分名单、不带权重；要权重（基金
        归因、指数对标）用本方法。
        """
        body = _index_weight_body(index, date)
        result = self._client._call("reference.index-weight", body=body)
        _note_missing_indices(result, body)
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
        body = _request_body(
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
        body = _request_body(
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

        category 分类: stock=股票 dr=存托凭证 index=指数 fund=基金 bond=债券；支持单值或列表。
        bond 覆盖交易所可转债、国债、地方债、金融债与银行间债券（后缀 .SH / .SZ / .IB），按
        代码或简称查；债券代码用于 gangtise.bond，quote、公告等其余方法不收债券代码（传了报
        120001）。fund 同时返回场内（.SH / .SZ）与场外（.OF）代码，同一基金的不同份额一起
        返回，按 gtsName 区分后取一个。

        🔴 **可转债在任何 category 下都可能出现**：按公司简称查 stock 时，同名可转债常排第一
        （「甬金」→ 113636.SH 甬金转债在 603995.SH 甬金股份之前）。**取第一条 category 等于
        所查类别的行**，别直接取第一行；查基金同理——债券代码传给 fund 方法返回空结果、不报错。
        """
        body = _request_body(
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
        body = _request_body(
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

    async def index_weight(
        self,
        *,
        index: FilterValue,
        date: str,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """指数成分股及权重（reference.index-weight），免费。

        - index: 指数代码（必填），单值或列表，如 000300.SH 沪深300、000905.SH 中证500、
          000852.SH 中证1000、000016.SH 上证50、000688.SH 科创50、399006.SZ 创业板指；不确定用
          reference.securities_search(keyword=<指数名>, category="index")。
        - date: 单个交易日（必填）。🔴 **只有每月最后一个交易日有数**（如 2026-09-30、
          2026-10-30）——其他交易日、非交易日与写错的指数代码都返回空结果、不报错，SDK 发
          UserWarning 点名没取到数据的指数。要「最新」权重就取上个月最后一个交易日；超出账号
          可查范围报 110003。

        不分页、不限条数：一次返回所选指数当日的全部成分股，多个指数合在同一张表里，按
        indexCode 区分。行字段：indexCode / indexName / tradeDate / securityCode / securityName /
        weight（**单位 %**，最多四位小数）。同一指数的权重合计约为 100，受舍入影响不严格等于
        100，校验合计时留容差。sector_constituents 是板块的纯成分名单、不带权重；要权重（基金
        归因、指数对标）用本方法。
        """
        body = _index_weight_body(index, date)
        result = await self._client._call("reference.index-weight", body=body)
        _note_missing_indices(result, body)
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
        body = _request_body(
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
        body = _request_body(
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
