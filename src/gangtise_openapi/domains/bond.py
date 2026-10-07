# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
"""`gangtise.bond.*` — 债券（资料/行情/估值/评级/公告），12 个方法（TS v0.41.0）。

整族通用（逐条见上游 ``gangtise-openapi/references/commands/bond.md``）：

- **全部计费，0.4 积分起**：多数按次（与返回行数无关）；``rating_overview`` 按条、
  ``rating_change`` 按有数据的债券只数、``issuer_rating_change`` 按发行人计。
- **超时 / 5xx 不自动重试**（整族 no-replay：计费 + 可重放正是会重复扣费的组合），
  仅连接失败、429 与 token 自愈会重试；偶发失败自行重跑。
- ``security`` 只收**标准债券代码**（``019742.SH`` / ``123456.SZ`` / ``220205.IB``
  银行间），**不接受简称或拼音**——传了整批报 ``120001``，不会退化成模糊匹配；只有
  简称时先用 ``reference.securities_search(keyword=<简称>)`` 换代码。单值或列表，
  发送前去重；有单次只数上限的方法按**去重后**的只数计（与服务端一致）。
- ``field`` 不传返回全部字段；**传了不支持的字段名整批报 ``100003``** 并指名，不会
  静默丢列。各方法的默认列恒在最前，无需指定。
- 返回是**列式**的（``fieldList`` + 数组行），默认转成 DataFrame；``raw=True`` 返回原始 data。
- 条件合法但全部没有数据时抛 ``ApiError``（``404`` / ``130001`` 数据未找到）——表示没有
  数据、不是故障。只有部分代码有数据时不报错：``basic_info`` / ``rating_overview`` /
  按 ``security`` 查的 ``issuer_info`` 每个代码固定占一行（按去重后的请求顺序），没数据
  的行除代码外全为 null；其余方法（以及按 ``issuer`` 查的两个方法）没数据的代码不产生
  行，用「请求的代码 − 返回里出现的代码」判断哪些没数据。
- 字段里的枚举 ID 可用 ``reference.constant_list(category=...)`` 查全量：``bondType``
  债券类型 / ``interestRateType`` 利率类型 / ``interestFrequency`` 付息频率 /
  ``absUnderlyingAssetType`` ABS 基础资产类型 / ``ratingType`` 评级类型 / ``exchange`` 交易市场。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._endpoints import lookup
from gangtise_openapi._errors import ValidationError
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _empty_list_error,
    _request_body,
    _result_to_dataframe,
    _validate_top,
)

# `basic-info` takes at most 10000 bonds a call (bond.md; TS passes it literally to
# `requireBondCodes` — it is not a registry `max_units`, the endpoint bills per call).
_BASIC_INFO_MAX_CODES = 10000
_CONFIDENCE_LEVELS = ("推荐", "不推荐")
_ANNOUNCEMENT_MAX_PAGE_SIZE = 200


def _max_units(key: str) -> int:
    """The registry's per-request unit cap (TS ``maxUnitsOf``): the bond-count limit
    of the two rating endpoints lives in ONE place, next to their price."""
    billing = lookup(key).billing
    if billing is None or billing.max_units is None:
        raise RuntimeError(f"{key} declares no billing.max_units")
    return int(billing.max_units)


def _unique(value: Any, name: str) -> list[Any] | None:
    """Scalar or list -> trimmed, blanks dropped, de-duplicated in first-seen order
    (``_as_list``, the CLI's ``collectList``); ``None`` stays ``None``. An explicit list
    that comes out empty stays ``[]``, so the required-code checks and
    ``_request_body`` refuse it rather than dropping the filter. A blank code would
    otherwise fail the whole metered batch with 120001."""
    return _as_list(value, name)


def _bond_codes(security: Any, *, cap: int | None = None) -> list[Any]:
    """TS ``requireBondCodes``: at least one code, de-duplicated, and the per-call cap
    counted AFTER de-duplication — the server counts it that way, so a merged list
    with repeats is legal. Checked before the (metered) request."""
    codes = _unique(security, "security")
    if not codes:
        raise ValidationError(
            "security is required: pass one or more bond codes, "
            "e.g. security=['019742.SH', '220205.IB']"
        )
    if cap is not None and len(codes) > cap:
        raise ValidationError(
            f"{len(codes)} distinct bond codes in one call — this endpoint takes at most "
            f"{cap}. Split them into batches of {cap} and run one call per batch."
        )
    return codes


def _issuer_selector(security: Any, issuer: Any) -> dict[str, Any]:
    """The two issuer-keyed endpoints take bond codes (-> their issuers) OR issuer
    names (fuzzy, one best hit per name). Sending both answers 100003, sending
    neither has nothing to query — both refused locally, before a metered call."""
    codes = _unique(security, "security")
    names = _unique(issuer, "issuer")
    # An explicit empty list is refused, not read as "the other selector" (as in
    # announcement and every other list argument).
    if codes == []:
        raise _empty_list_error("security")
    if names == []:
        raise _empty_list_error("issuer")
    if codes and names:
        raise ValidationError(
            "security and issuer are mutually exclusive: pass bond codes or issuer names, not both"
        )
    if not codes and not names:
        raise ValidationError("pass either security (bond codes) or issuer (issuer names)")
    return {"securityList": codes} if codes else {"issuerNameList": names}


def _confidence_level(value: Any) -> Any:
    if value is not None and value not in _CONFIDENCE_LEVELS:
        raise ValidationError(
            f"invalid confidence_level: {value!r} is not one of {'/'.join(_CONFIDENCE_LEVELS)}"
        )
    return value


def _announcement_body(
    security: Any, start_date: Any, end_date: Any, page_no: Any, page_size: Any, field: Any
) -> dict[str, Any]:
    codes = _unique(security, "security")
    by_date = bool(start_date or end_date)
    if codes and by_date:
        raise ValidationError(
            "security and start_date/end_date are mutually exclusive on bond.announcement: "
            "filter by bond codes or by date range, not both"
        )
    if not codes and not by_date:
        raise ValidationError(
            "pass either security (bond codes) or start_date/end_date (announcement date range)"
        )
    if not isinstance(page_no, int) or isinstance(page_no, bool) or page_no < 1:
        raise ValidationError(f"page_no must be an integer >= 1 (got {page_no!r})")
    return _request_body(
        {
            "securityList": codes,
            "startDate": start_date,
            "endDate": end_date,
            "pageNo": page_no,
            "pageSize": _validate_top(
                page_size, name="page_size", max_value=_ANNOUNCEMENT_MAX_PAGE_SIZE
            ),
            "fieldList": _unique(field, "field"),
        }
    )


def _range_body(
    security: Any, start_date: Any, end_date: Any, field: Any, *, cap: int | None = None
) -> dict[str, Any]:
    """``securityList`` + optional date range + ``fieldList`` — the shape four of the
    twelve share (TS ``addBondRange``); the two dated quote endpoints reuse it with
    their dates required by signature."""
    return _request_body(
        {
            "securityList": _bond_codes(security, cap=cap),
            "startDate": start_date,
            "endDate": end_date,
            "fieldList": _unique(field, "field"),
        }
    )


def _frame(result: Any, raw: bool) -> pd.DataFrame | dict[str, Any]:
    if raw:
        return result  # type: ignore[no-any-return]
    return _result_to_dataframe(result)


class Bond:
    """`gangtise.bond.*` — 债券（资料/行情/估值/评级/公告）。

    全部计费（0.4 积分起）且超时 / 5xx 不自动重试；``security`` 只收标准债券代码；
    返回列式、默认转 DataFrame。通用约定见模块说明。
    """

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def basic_info(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券基本资料：发行、期限、票息、评级、担保、特殊条款（bond.basic-info）。

        0.4 积分/次。静态档案，**不提供历史快照**。单次最多 10000 只（按去重后计，超出
        本地拒绝）。默认返回 securityCode。格式合法但库中无资料的债券**不报错**，仍占
        一行、除 securityCode 外全为 null。

        字段分组：基础标识 / 发行信息 / 期限与日期 / 利率与付息 / 评级 / 担保 / 特殊条款 /
        质押回购 / ABS 专项（abs*，仅资产支持证券有值）/ 可转债专项（conversion*，仅可转债有值）。

        - parValue、issuePriceOrReferenceYield 是 / 分隔的**复合展示值**（"100.00/100.00"），
          某侧无数据时以 - 占位；要数值用 latestParValue
        - actualMaturityDate 含提前赎回 / 回售 / 全额转股，未提前终止时与 maturityDate
          一致；算剩余期限用前者
        - remainingDays 已到期返回 0
        """
        body = _request_body(
            {
                "securityList": _bond_codes(security, cap=_BASIC_INFO_MAX_CODES),
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(self._client._call("bond.basic-info", body=body), raw)

    def issuer_info(
        self,
        *,
        security: FilterValue | None = None,
        issuer: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """发债主体基本信息：性质、申万行业、注册信息、评级、存续债券（bond.issuer-info）。

        0.4 积分/次。🔴 **security（债券代码 → 其发行人）与 issuer（发行人名称）二选一**：
        同传服务端报 100003，都不传无从查询——两种情况都在本地拒绝、不发请求。issuer
        按公司全称或简称**模糊匹配**，一个名称只返回最匹配的一家，匹配不到不产生行。
        默认返回 issuerName。

        - 行业有两套：swIndustry 是**申万**「一级/二级」（如 "食品饮料/白酒Ⅱ"），
          nationalIndustry 是**国民经济行业分类**「一级/二级」（如
          "制造业/酒、饮料和精制茶制造业"）。某一级无数据时该侧以 - 占位；要申万一级按 /
          切前半段
        - latestIssuerRating 是复合值「评级(展望,日期)」（如 "AAA(维持,2026-08-11)"），但
          **括号部分可能缺省**、只返回评级符号（如 "AAA"）——解析时别用硬套括号的正则
        - ⚠️ latestIssuerRating **混合了境内与境外评级口径**：既可能是境内机构（中诚信、
          大公等）的评级，也可能是惠誉等国际机构的评级，两套口径不可直接比较。做信用
          排序或筛选前，**一并取 ratingAgency 判断口径**
        - outstandingBondList 是存续债券**简称**的中文逗号分隔串；要代码得拿简称去
          reference.securities_search 换
        """
        body = _request_body(
            {**_issuer_selector(security, issuer), "fieldList": _unique(field, "field")}
        )
        return _frame(self._client._call("bond.issuer-info", body=body), raw)

    def daily_quote(
        self,
        *,
        security: FilterValue,
        start_date: str,
        end_date: str,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券日收盘行情（交易所 + 银行间 CFETS）：全价/净价、YTM、久期、凸性（bond.daily-quote）。

        0.4 积分/次。**日期必填**（交易日区间），不限传入只数。默认返回 securityCode +
        tradeDate。字段分组：全价（dirty*）/ 净价（clean*）/ 成交与收益率（ytmClose volume
        turnover ytc ytp）/ 风险指标（duration modifiedDuration convexity）/ 票息要素。

        ⚠️ 历史范围正式账号前溯 5 年、试用 3 年。**start_date 早于可回溯下界时整批报
        110003「超出时间范围限制」**——即使 end_date 在窗口内，也不会只返回窗口内那一段；
        把 start_date 移进窗口再查（实际下界随账号服务等级而定，以返回为准）。

        ⚠️ 数据还可能比账号窗口短：区间在窗口内、但早于数据起点时整段抛 ApiError
        （130001「数据未找到」）；跨过数据起点时从有数据的那天起返回、不报错。**按年份
        取长序列时核对返回的首行日期。**
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(self._client._call("bond.daily-quote", body=body), raw)

    def valuation(
        self,
        *,
        security: FilterValue,
        start_date: str,
        end_date: str,
        confidence_level: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """上清所估值：估值价格、收益率、久期、凸性、PVBP（bond.valuation）。

        0.4 积分/次。**日期必填**（估值日区间）。默认返回 securityCode + tradeDate +
        confidenceLevel。风险指标含 pvbp、利率与利差各自的久期凸性。

        confidence_level 估值可信度："推荐" / "不推荐"，其他值本地拒绝。**不传时服务端
        默认只返回「推荐」的估值**——要看全部需显式传另一个值分别查。

        ⚠️ 历史范围正式账号前溯 5 年、试用 3 年。**start_date 早于可回溯下界时整批报
        110003「超出时间范围限制」**——即使 end_date 在窗口内，也不会只返回窗口内那一段；
        把 start_date 移进窗口再查（实际下界随账号服务等级而定，以返回为准）。

        ⚠️ 数据还可能比账号窗口短：区间在窗口内、但早于数据起点时整段抛 ApiError
        （130001「数据未找到」）；跨过数据起点时从有数据的那天起返回、不报错。**按年份
        取长序列时核对返回的首行日期。**
        """
        body = _request_body(
            {
                "securityList": _bond_codes(security),
                "startDate": start_date,
                "endDate": end_date,
                "confidenceLevel": _confidence_level(confidence_level),
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(self._client._call("bond.valuation", body=body), raw)

    def cash_flow(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券付息与兑付计划（bond.cash-flow）。

        0.4 积分/次。start_date / end_date 筛**兑付日**，可省略（省略返回全部历史）。
        默认返回 securityCode + paymentDate。
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(self._client._call("bond.cash-flow", body=body), raw)

    def announcement(
        self,
        *,
        security: FilterValue | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page_no: int = 1,
        page_size: int = 50,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券公告，🔴 **需手动翻页**（bond.announcement）。

        0.4 积分/次，**每翻一页扣一次**。🔴 **security 与 start_date/end_date 二选一**：
        同传服务端报 100003，都不传无从查询——两种情况都在本地拒绝、不发请求。默认返回
        announcementDate + securityCode。

        本族唯一分页的接口，且响应**没有 total**，所以 SDK **不自动翻页**：page_no 从 1
        开始逐页递增，page_size 取 1–200（默认 50，超出本地拒绝）。批量翻页显式传
        page_size=200，调用次数只有默认的四分之一。终止条件：

        - 翻过末页返回**空结果**（空 DataFrame；raw=True 时 list 为空）——到这一页就停
        - 条件下**一条公告都没有**时，任何页码都抛 ApiError（404 / 130001）——第 1 页
          收到它就是没有数据，不用再翻

        按日期区间查询时，部分行的 securityCode 为空（如不对应已上市证券的公告、部分新
        发行债券的发行文件），这类行无法接着传给其他 bond 方法；有代码的行都带市场后缀，
        可以直接传。
        """
        body = _announcement_body(security, start_date, end_date, page_no, page_size, field)
        return _frame(self._client._call("bond.announcement", body=body), raw)

    def issuance_detail(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券发行与增发记录：招标、定价、认购倍数（bond.issuance-detail）。

        0.4 积分/次。start_date / end_date 筛**发行公告日**，可省略（省略返回全部历史）。
        默认返回 securityCode + issueBatchNo。
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(self._client._call("bond.issuance-detail", body=body), raw)

    def rating_overview(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券评级一览：债项 / 发行人 / 担保人三套评级并列，一只债券一行（bond.rating-overview）。

        计费按**条**（0.4 积分/条；除代码外全为 null 的行不计）。🔴 **单次最多 10 只**
        （按去重后计，超出本地拒绝并提示分批）。没数据的代码仍占一行、除代码外全为 null；
        国债这类品种本身没有评级数据，全部无数据时报 130001 属正常。

        ⚠️ **评级值可能带小写后缀**：sf（结构化融资产品评级，如 AA+sf）、pi（中债资信
        主动评级，如 AAApi），紧跟评级符号、无分隔符。按档位匹配、排序或分档统计前先识别
        处理，否则 AAA 与 AAApi 会被当成两档。
        """
        body = _request_body(
            {
                "securityList": _bond_codes(security, cap=_max_units("bond.rating-overview")),
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(self._client._call("bond.rating-overview", body=body), raw)

    def rating_change(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债项评级变动历史（bond.rating-change）。

        计费按**有数据的债券只数**（0.4 积分/只）。🔴 **单次最多 10 只**（按去重后计，
        超出本地拒绝并提示分批）。start_date / end_date 筛**评级变动公告日**，可省略
        （省略返回全部历史）。默认返回 securityCode + announcementDate。

        一只债券每次评级变动一行，返回本次 / 上次评级（currentRating / previousRating）、
        变动方向、评级展望、评级类型与评级机构；首次评级的 previousRating 为 null。国债
        这类品种本身没有评级数据，报 130001 属正常。

        ⚠️ 评级值可能带小写后缀 sf / pi（如 AA+sf、AAApi），按档位统计前先处理，
        同 rating_overview。
        """
        body = _range_body(
            security, start_date, end_date, field, cap=_max_units("bond.rating-change")
        )
        return _frame(self._client._call("bond.rating-change", body=body), raw)

    def issuer_rating_change(
        self,
        *,
        security: FilterValue | None = None,
        issuer: FilterValue | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """发债主体评级变动历史（bond.issuer-rating-change）。

        计费按**发行人**（0.4 积分/个）。🔴 **security（债券代码）与 issuer（发行人名称，
        模糊匹配、一个名称取最匹配的一家）二选一**，同 issuer_info：同传或都不传都在本地
        拒绝。命中的发行人总数超过 10 个时服务端报 100006。start_date / end_date 筛
        **公告日**，可省略（省略返回全部历史）。默认返回 issuerName + announcementDate。

        ⚠️ 评级值可能带小写后缀 sf / pi（如 AA+sf、AAApi），按档位统计前先处理，
        同 rating_overview。
        """
        body = _request_body(
            {
                **_issuer_selector(security, issuer),
                "startDate": start_date,
                "endDate": end_date,
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(self._client._call("bond.issuer-rating-change", body=body), raw)

    def issuance_plan(
        self,
        *,
        start_date: str,
        end_date: str,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """利率债发行计划（bond.issuance-plan）。

        0.4 积分/次。🔴 **只按日期区间（发行日）查，不收债券码**，日期必填。默认返回
        issueDate。返回计划年份、发行人、债券性质与类型、期限、计划发行量、利率类型、付息
        频率、是否跨市场。区间内无发行计划时报 130001。

        ⚠️ 历史范围正式账号前溯 5 年、试用 3 年。**start_date 早于可回溯下界时整批报
        110003「超出时间范围限制」**——即使 end_date 在窗口内，也不会只返回窗口内那一段；
        把 start_date 移进窗口再查（实际下界随账号服务等级而定，以返回为准）。
        """
        body = _request_body(
            {"startDate": start_date, "endDate": end_date, "fieldList": _unique(field, "field")}
        )
        return _frame(self._client._call("bond.issuance-plan", body=body), raw)

    def exercise_notice(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """含权债的回售 / 赎回行权安排与结果（bond.exercise-notice）。

        0.4 积分/次。start_date / end_date 筛**行权日**，可省略（省略返回全部历史）。
        默认返回 securityCode + exerciseDate。国债这类品种本身没有行权数据，报 130001
        属正常。
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(self._client._call("bond.exercise-notice", body=body), raw)


class AsyncBond:
    """Async mirror of `Bond`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def basic_info(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券基本资料：发行、期限、票息、评级、担保、特殊条款（bond.basic-info）。

        0.4 积分/次。静态档案，**不提供历史快照**。单次最多 10000 只（按去重后计，超出
        本地拒绝）。默认返回 securityCode。格式合法但库中无资料的债券**不报错**，仍占
        一行、除 securityCode 外全为 null。

        字段分组：基础标识 / 发行信息 / 期限与日期 / 利率与付息 / 评级 / 担保 / 特殊条款 /
        质押回购 / ABS 专项（abs*，仅资产支持证券有值）/ 可转债专项（conversion*，仅可转债有值）。

        - parValue、issuePriceOrReferenceYield 是 / 分隔的**复合展示值**（"100.00/100.00"），
          某侧无数据时以 - 占位；要数值用 latestParValue
        - actualMaturityDate 含提前赎回 / 回售 / 全额转股，未提前终止时与 maturityDate
          一致；算剩余期限用前者
        - remainingDays 已到期返回 0
        """
        body = _request_body(
            {
                "securityList": _bond_codes(security, cap=_BASIC_INFO_MAX_CODES),
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(await self._client._call("bond.basic-info", body=body), raw)

    async def issuer_info(
        self,
        *,
        security: FilterValue | None = None,
        issuer: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """发债主体基本信息：性质、申万行业、注册信息、评级、存续债券（bond.issuer-info）。

        0.4 积分/次。🔴 **security（债券代码 → 其发行人）与 issuer（发行人名称）二选一**：
        同传服务端报 100003，都不传无从查询——两种情况都在本地拒绝、不发请求。issuer
        按公司全称或简称**模糊匹配**，一个名称只返回最匹配的一家，匹配不到不产生行。
        默认返回 issuerName。

        - 行业有两套：swIndustry 是**申万**「一级/二级」（如 "食品饮料/白酒Ⅱ"），
          nationalIndustry 是**国民经济行业分类**「一级/二级」（如
          "制造业/酒、饮料和精制茶制造业"）。某一级无数据时该侧以 - 占位；要申万一级按 /
          切前半段
        - latestIssuerRating 是复合值「评级(展望,日期)」（如 "AAA(维持,2026-08-11)"），但
          **括号部分可能缺省**、只返回评级符号（如 "AAA"）——解析时别用硬套括号的正则
        - ⚠️ latestIssuerRating **混合了境内与境外评级口径**：既可能是境内机构（中诚信、
          大公等）的评级，也可能是惠誉等国际机构的评级，两套口径不可直接比较。做信用
          排序或筛选前，**一并取 ratingAgency 判断口径**
        - outstandingBondList 是存续债券**简称**的中文逗号分隔串；要代码得拿简称去
          reference.securities_search 换
        """
        body = _request_body(
            {**_issuer_selector(security, issuer), "fieldList": _unique(field, "field")}
        )
        return _frame(await self._client._call("bond.issuer-info", body=body), raw)

    async def daily_quote(
        self,
        *,
        security: FilterValue,
        start_date: str,
        end_date: str,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券日收盘行情（交易所 + 银行间 CFETS）：全价/净价、YTM、久期、凸性（bond.daily-quote）。

        0.4 积分/次。**日期必填**（交易日区间），不限传入只数。默认返回 securityCode +
        tradeDate。字段分组：全价（dirty*）/ 净价（clean*）/ 成交与收益率（ytmClose volume
        turnover ytc ytp）/ 风险指标（duration modifiedDuration convexity）/ 票息要素。

        ⚠️ 历史范围正式账号前溯 5 年、试用 3 年。**start_date 早于可回溯下界时整批报
        110003「超出时间范围限制」**——即使 end_date 在窗口内，也不会只返回窗口内那一段；
        把 start_date 移进窗口再查（实际下界随账号服务等级而定，以返回为准）。

        ⚠️ 数据还可能比账号窗口短：区间在窗口内、但早于数据起点时整段抛 ApiError
        （130001「数据未找到」）；跨过数据起点时从有数据的那天起返回、不报错。**按年份
        取长序列时核对返回的首行日期。**
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(await self._client._call("bond.daily-quote", body=body), raw)

    async def valuation(
        self,
        *,
        security: FilterValue,
        start_date: str,
        end_date: str,
        confidence_level: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """上清所估值：估值价格、收益率、久期、凸性、PVBP（bond.valuation）。

        0.4 积分/次。**日期必填**（估值日区间）。默认返回 securityCode + tradeDate +
        confidenceLevel。风险指标含 pvbp、利率与利差各自的久期凸性。

        confidence_level 估值可信度："推荐" / "不推荐"，其他值本地拒绝。**不传时服务端
        默认只返回「推荐」的估值**——要看全部需显式传另一个值分别查。

        ⚠️ 历史范围正式账号前溯 5 年、试用 3 年。**start_date 早于可回溯下界时整批报
        110003「超出时间范围限制」**——即使 end_date 在窗口内，也不会只返回窗口内那一段；
        把 start_date 移进窗口再查（实际下界随账号服务等级而定，以返回为准）。

        ⚠️ 数据还可能比账号窗口短：区间在窗口内、但早于数据起点时整段抛 ApiError
        （130001「数据未找到」）；跨过数据起点时从有数据的那天起返回、不报错。**按年份
        取长序列时核对返回的首行日期。**
        """
        body = _request_body(
            {
                "securityList": _bond_codes(security),
                "startDate": start_date,
                "endDate": end_date,
                "confidenceLevel": _confidence_level(confidence_level),
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(await self._client._call("bond.valuation", body=body), raw)

    async def cash_flow(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券付息与兑付计划（bond.cash-flow）。

        0.4 积分/次。start_date / end_date 筛**兑付日**，可省略（省略返回全部历史）。
        默认返回 securityCode + paymentDate。
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(await self._client._call("bond.cash-flow", body=body), raw)

    async def announcement(
        self,
        *,
        security: FilterValue | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page_no: int = 1,
        page_size: int = 50,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券公告，🔴 **需手动翻页**（bond.announcement）。

        0.4 积分/次，**每翻一页扣一次**。🔴 **security 与 start_date/end_date 二选一**：
        同传服务端报 100003，都不传无从查询——两种情况都在本地拒绝、不发请求。默认返回
        announcementDate + securityCode。

        本族唯一分页的接口，且响应**没有 total**，所以 SDK **不自动翻页**：page_no 从 1
        开始逐页递增，page_size 取 1–200（默认 50，超出本地拒绝）。批量翻页显式传
        page_size=200，调用次数只有默认的四分之一。终止条件：

        - 翻过末页返回**空结果**（空 DataFrame；raw=True 时 list 为空）——到这一页就停
        - 条件下**一条公告都没有**时，任何页码都抛 ApiError（404 / 130001）——第 1 页
          收到它就是没有数据，不用再翻

        按日期区间查询时，部分行的 securityCode 为空（如不对应已上市证券的公告、部分新
        发行债券的发行文件），这类行无法接着传给其他 bond 方法；有代码的行都带市场后缀，
        可以直接传。
        """
        body = _announcement_body(security, start_date, end_date, page_no, page_size, field)
        return _frame(await self._client._call("bond.announcement", body=body), raw)

    async def issuance_detail(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券发行与增发记录：招标、定价、认购倍数（bond.issuance-detail）。

        0.4 积分/次。start_date / end_date 筛**发行公告日**，可省略（省略返回全部历史）。
        默认返回 securityCode + issueBatchNo。
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(await self._client._call("bond.issuance-detail", body=body), raw)

    async def rating_overview(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券评级一览：债项 / 发行人 / 担保人三套评级并列，一只债券一行（bond.rating-overview）。

        计费按**条**（0.4 积分/条；除代码外全为 null 的行不计）。🔴 **单次最多 10 只**
        （按去重后计，超出本地拒绝并提示分批）。没数据的代码仍占一行、除代码外全为 null；
        国债这类品种本身没有评级数据，全部无数据时报 130001 属正常。

        ⚠️ **评级值可能带小写后缀**：sf（结构化融资产品评级，如 AA+sf）、pi（中债资信
        主动评级，如 AAApi），紧跟评级符号、无分隔符。按档位匹配、排序或分档统计前先识别
        处理，否则 AAA 与 AAApi 会被当成两档。
        """
        body = _request_body(
            {
                "securityList": _bond_codes(security, cap=_max_units("bond.rating-overview")),
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(await self._client._call("bond.rating-overview", body=body), raw)

    async def rating_change(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债项评级变动历史（bond.rating-change）。

        计费按**有数据的债券只数**（0.4 积分/只）。🔴 **单次最多 10 只**（按去重后计，
        超出本地拒绝并提示分批）。start_date / end_date 筛**评级变动公告日**，可省略
        （省略返回全部历史）。默认返回 securityCode + announcementDate。

        一只债券每次评级变动一行，返回本次 / 上次评级（currentRating / previousRating）、
        变动方向、评级展望、评级类型与评级机构；首次评级的 previousRating 为 null。国债
        这类品种本身没有评级数据，报 130001 属正常。

        ⚠️ 评级值可能带小写后缀 sf / pi（如 AA+sf、AAApi），按档位统计前先处理，
        同 rating_overview。
        """
        body = _range_body(
            security, start_date, end_date, field, cap=_max_units("bond.rating-change")
        )
        return _frame(await self._client._call("bond.rating-change", body=body), raw)

    async def issuer_rating_change(
        self,
        *,
        security: FilterValue | None = None,
        issuer: FilterValue | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """发债主体评级变动历史（bond.issuer-rating-change）。

        计费按**发行人**（0.4 积分/个）。🔴 **security（债券代码）与 issuer（发行人名称，
        模糊匹配、一个名称取最匹配的一家）二选一**，同 issuer_info：同传或都不传都在本地
        拒绝。命中的发行人总数超过 10 个时服务端报 100006。start_date / end_date 筛
        **公告日**，可省略（省略返回全部历史）。默认返回 issuerName + announcementDate。

        ⚠️ 评级值可能带小写后缀 sf / pi（如 AA+sf、AAApi），按档位统计前先处理，
        同 rating_overview。
        """
        body = _request_body(
            {
                **_issuer_selector(security, issuer),
                "startDate": start_date,
                "endDate": end_date,
                "fieldList": _unique(field, "field"),
            }
        )
        return _frame(await self._client._call("bond.issuer-rating-change", body=body), raw)

    async def issuance_plan(
        self,
        *,
        start_date: str,
        end_date: str,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """利率债发行计划（bond.issuance-plan）。

        0.4 积分/次。🔴 **只按日期区间（发行日）查，不收债券码**，日期必填。默认返回
        issueDate。返回计划年份、发行人、债券性质与类型、期限、计划发行量、利率类型、付息
        频率、是否跨市场。区间内无发行计划时报 130001。

        ⚠️ 历史范围正式账号前溯 5 年、试用 3 年。**start_date 早于可回溯下界时整批报
        110003「超出时间范围限制」**——即使 end_date 在窗口内，也不会只返回窗口内那一段；
        把 start_date 移进窗口再查（实际下界随账号服务等级而定，以返回为准）。
        """
        body = _request_body(
            {"startDate": start_date, "endDate": end_date, "fieldList": _unique(field, "field")}
        )
        return _frame(await self._client._call("bond.issuance-plan", body=body), raw)

    async def exercise_notice(
        self,
        *,
        security: FilterValue,
        start_date: str | None = None,
        end_date: str | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """含权债的回售 / 赎回行权安排与结果（bond.exercise-notice）。

        0.4 积分/次。start_date / end_date 筛**行权日**，可省略（省略返回全部历史）。
        默认返回 securityCode + exerciseDate。国债这类品种本身没有行权数据，报 130001
        属正常。
        """
        body = _range_body(security, start_date, end_date, field)
        return _frame(await self._client._call("bond.exercise-notice", body=body), raw)
