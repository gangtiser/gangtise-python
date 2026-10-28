# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
"""`gangtise.fund.*` — 公募基金 18 个方法（TS v0.44.0 `fund` 命令组）.

Every method is ONE request (none of the eighteen endpoints pages): ``data`` is
``{list}`` with no ``total``, past 10000 rows the whole query answers 100006 with no
partial list, so there is nothing to truncate-flag. All are billed 0.4 credits per
call and marked ``no-replay`` in the registry. ``etf_pcf_components`` then sends free
lookups to fill in ``componentCode`` (``_etf_components``; ``component_code=False``
skips them).

The enum-valued parameters (``position_type`` / ``industry_standard`` / ``fee_type`` /
``asset_level``) and ``field`` are NOT checked locally, exactly like the CLI: the
server rejects an unknown value with 100003, naming the parameter, before billing
anything (probed 2026-09-30 on all four enums), so a local list could only go stale.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ValidationError
from gangtise_openapi._etf_components import add_component_codes, add_component_codes_async
from gangtise_openapi.domains._common import (
    _as_list,
    _empty_list_error,
    _request_body,
    _result_to_dataframe,
)

# Names the method in the warning about the codes add_component_codes filled in.
_ETF_COMPONENTS = "fund.etf_pcf_components"


def _collect(value: str | Sequence[str] | None, *, name: str) -> list[str]:
    """``_as_list`` (trimmed, blanks dropped, de-duplicated — a code named twice would
    otherwise come back as its rows twice) plus a type check: every value here is a
    code, a name or an enum string. A string is ONE value, as everywhere else in the
    SDK: ``"A,B"`` is not split."""
    items = _as_list(value, name) or []
    for item in items:
        if not isinstance(item, str):
            raise ValidationError(f"invalid {name}: expected strings, got {item!r}")
    return items


def _required_list(value: str | Sequence[str], *, name: str) -> list[str]:
    """TS ``requiredList``: present but empty (``""``, ``[]``, ``["  "]``) is refused
    before any request — the server would get an empty list."""
    values = _collect(value, name=name)
    if not values:
        raise ValidationError(f"{name} is empty: pass at least one value")
    return values


def _optional_list(value: str | Sequence[str] | None, *, name: str) -> list[str] | None:
    """TS ``list``: left out of the body when not given. Given but empty (``[]`` or
    blank) is refused, like every explicit empty filter in the SDK."""
    if value is None:
        return None
    values = _collect(value, name=name)
    if not values:
        raise _empty_list_error(name)
    return values


def _fund_body(
    security: str | Sequence[str], fields: dict[str, Any] | None = None
) -> dict[str, Any]:
    """``{fundCodeList, ...fields}``; dates validated and unset fields dropped by
    ``_request_body``. Built before any request, so every local refusal is free."""
    codes = _required_list(security, name="security")
    return _request_body({"fundCodeList": codes, **(fields or {})})


class Fund:
    """`gangtise.fund.*` — 公募基金（资料/净值/费率/经理/规模/持有人/持仓与配置/ETF 申赎）。

    通则（18 个方法相同）:

    - **计费 0.4 积分/次**，与返回行数、基金只数无关；空结果与报错不扣。**超时 / 5xx /
      999999 不自动重发**（避免重复扣费）。
    - ``security``（``manager_info`` 为 ``manager``）必填: 基金交易代码，后缀大写——场外
      ``005827.OF``，场内 ``159967.SZ`` / ``510300.SH``。单值或列表（多只请传列表，字符串不按逗号
      拆分），重复值去掉；空值本地报 ValidationError、不发请求。
    - 🔴 **代码不存在、不带后缀（``005827``）、后缀小写（``.of``）或传成股票代码都返回空结果、
      不报错**——拿到空先核对代码与后缀。LOF / ETF 的场内与场外代码都能查，返回的
      ``fundCode`` / ``fundName`` 跟随传入的代码（同一只基金别两种代码混着传，会重复）；A / C
      等份额各有代码，合并用 ``basic_info`` 的 ``mainFundCode``。多只基金按 ``fundCode`` 列对应
      结果，别按传入顺序对位。
    - 只知道基金名称时: 用 ``reference.securities_search(keyword=<基金简称或 6 位代码>,
      category="fund")`` 换代码，🔴 **只取返回里 ``category`` 为 ``fund`` 的行**——结果里可能混有
      可转债等债券，债券代码传给基金方法返回空结果、不报错。场内（``.SH`` / ``.SZ``）与场外
      （``.OF``）都能搜到，同一只基金的不同份额与场内 / 场外代码一起返回，按 ``gtsName`` 区分
      后取一个；基金全称常搜不到（如「华泰柏瑞沪深300ETF」要搜「沪深300ETF」或 ``510300``）。
    - 多只基金横向比分类、复权净值与风险收益指标（夏普 / 最大回撤 / Alpha / 同类排名）用
      ``indicator.cross_section``（``security`` 传基金代码）。
    - **不分页**，一次返回全部；单次超过 10000 行整批报 100006、不返回部分结果——减少只数或
      缩短区间分批查。
    - 日期: 持仓 / 规模 / 持有人类方法筛**报告期**（季末日），``nav`` / ``etf_share_change``
      筛**交易日**。两端都不传 = 账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内的全部；
      起点早于窗口整批报 110003；起 > 止报 110002。
    - 枚举参数写错时服务端报 100003 并点名参数与取值，不会按默认值取数（本地不校验）。
    - 单位各方法不同，入库前逐列核对；百分比字段已是百分数（``5.72`` = 5.72%）。
    """

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def _query(
        self, endpoint_key: str, body: dict[str, Any], raw: bool
    ) -> pd.DataFrame | dict[str, Any]:
        result = self._client._call(endpoint_key, body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- 资料与经理 ----

    def basic_info(
        self,
        *,
        security: str | Sequence[str],
        field: str | Sequence[str] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金基本信息（fund.basic-info）：分类（一级 / 二级）、管理人与托管人、成立与存续、
        运行状态与运作方式、申赎规则、业绩比较基准、风险等级、投资范围、跟踪指数。

        当前资料，**不提供历史快照**，无日期参数。

        - security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带
          后缀、后缀小写或传成股票代码都返回空结果、不报错。
        - field: 要返回的字段名，单值或列表，不传返回全部；``fundCode`` 始终返回。字段名写错
          **整批报 100003** 并指名（本地不校验），不会静默丢列。``investScope`` 是长文本，批量
          导出时用 field 去掉可显著缩小体积。

        字段要点: ``mainFundCode`` 是 A / C 等份额共用的主代码，份额合并按它分组；
        ``investTypeCodeLevel1`` / ``investTypeCodeLevel2`` 与
        ``reference.constant_list(category="fundType")`` 的常量 ID 一致（FOF 类一级 ID 不是整百，
        如 149051404 混合型 FOF，按常量表的 level 判层级）；``exchange`` 场内为交易所名称（如
        上海证券交易所 / 深圳证券交易所），场外为 null；``isIndexFund`` 是布尔值，非指数基金的
        ``trackIndexCode`` / ``trackIndexName`` 为 null；``maturityDate`` 为 null 表示无固定存续期；
        ``largePurchaseLimit`` 为 null 表示不限。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.basic-info",
            _fund_body(security, {"fieldList": _optional_list(field, name="field")}),
            raw,
        )

    def nav(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金净值（fund.nav）：逐交易日一行，按日期倒序。

        - ``navUnit`` 单位净值、``navAccumulated`` 累计净值、``adjustFactor`` 复权因子、
          ``navAdjusted`` 复权净值（**元**）。**算区间收益用 navAdjusted**，单位净值在分红 /
          拆分时会跳变。
        - 货币基金另有 ``mmfAnnualizedYield``（7 日年化，%）与 ``mmfUnitYield``（每万份收益，元），
          其 ``adjustFactor`` 为 null；非货币基金这两列为 null。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**交易日**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部；只传 start_date = 从该日到
        最新，只传 end_date = 从窗口下界到该日。🔴 start_date 早于窗口下界时整批报 110003（不会只
        返回窗口内那段）；起 > 止报 110002。

        不分页，单次上限 10000 行（每只每年约 240～250 行），超出整批报 100006、无部分结果——多只
        基金 × 长区间按只数分批。0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx /
        999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.nav",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    def fee_rate(
        self,
        *,
        security: str | Sequence[str],
        fee_type: str | Sequence[str] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金费率（fund.fee-rate）：当前各类费率，按条件分档一档一行。无日期参数。

        - security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带
          后缀、后缀小写或传成股票代码都返回空结果、不报错。
        - fee_type: ``purchaseFee`` 申购 / ``redemptionFee`` 赎回 / ``managementFee`` 管理 /
          ``custodianFee`` 托管 / ``saleFee`` 销售服务；单值或列表，不传返回全部。写错时服务端
          报 100003 并点名（本地不校验）。

        一只基金一个费率类型可能多行——申购费按金额分档、赎回费按持有期限分档，每档一行，
        ``feeCondition`` 是条件区间（如 ``持有期限＜7日``），无分档为 null。🔴 ``feeRate`` 是
        **字符串**（``"1.5%"`` / ``"0%"``），大额固定收费时是金额描述（``"每笔1000元"``），
        不能直接当数字用。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.fee-rate",
            _fund_body(security, {"feeTypeList": _optional_list(fee_type, name="fee_type")}),
            raw,
        )

    def manager_info(
        self,
        *,
        manager: str | Sequence[str],
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金经理基本信息（fund.manager-info）：学历、从业日期与年限、在管规模与只数、历任基金数
        与公司数、简介。

        🔴 **查的是人名，不是基金代码**。manager: 经理姓名，单值或列表（如 ``"张坤"``）；多人请传
        列表，名字原样发送，重复值去掉；空值本地报 ValidationError、不发请求。按姓名**精确匹配**，查不到返回空结果；同名经理**全部返回**（常见名可能一次多位），
        用 ``currentCompany`` 区分（可能为 null）。

        - ``managedFundScale`` 在管规模单位**亿元**。
        - ⚠️ ``workingYears``（从业年限）与由 ``careerStartDate`` 推算出的年限、简介里写的从业
          年数**可能对不上**，``currentCompanyYears`` 同理——需要准确的从业年限时按
          ``careerStartDate`` 自行计算。
        - ``birthYear`` 未披露时为 null。

        按次计费 0.4 积分/次（与返回行数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        names = _required_list(manager, name="manager")
        return self._query("fund.manager-info", _request_body({"managerNameList": names}), raw)

    def manager_history(
        self,
        *,
        security: str | Sequence[str],
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金历任基金经理（fund.manager-history）：每位经理的每段任职各一行，同期共同管理的
        多位经理各占一行。无日期参数（返回全部任职记录）。

        ``endDate`` 为 null 的是**现任**；``managedDays`` 任职天数，``managedReturn`` 任职期间业绩
        表现（%）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query("fund.manager-history", _fund_body(security), raw)

    # ---- 规模与持有人 ----

    def asset_size(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """资产规模（fund.asset-size）：每个报告期一行。

        期初份额、期间申购 / 赎回 / 净申购份额（赎回大于申购时为负）、期末份额（**万份**），
        基金资产净值（**万元**）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（季末日，如 ``2026-06-30``；YYYY-MM-DD，YYYY/MM/DD、
        YYYYMMDD 也收）。两端都不传 = 账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内
        全部，不是只取最新一期——只要最新一期就把起止都设成那个报告期。🔴 start_date 早于窗口
        下界时整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.asset-size",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    def holder_structure(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """持有人结构（fund.holder-structure）：持有人户数、户均份额，机构 / 个人 / 员工持有份额
        （**份**）与占比（%）。**只有半年报与年报披露**，季报期没有行。

        - ``holderCount`` 为整数（如 ``2219140``）。
        - 占比字段可能为 null。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.holder-structure",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    def top10_holders(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """前十大持有人（fund.top10-holders）：**仅上市基金**（LOF / ETF 等）。

        每个报告期按 ``serialNumber`` 排名各一行：持有人名称、持有份额（**份**）、占上市总份额
        比例（%）。半年报与年报披露。

        - 🔴 ETF 在前十名之外可能多一行 ``serialNumber = 11``，是该 ETF 的**联接基金**（定期报告
          单列披露），它的占比可能高于前十中的多位。只要前十名就按 ``serialNumber <= 10`` 过滤。
        - 最新一期的更新可能晚于其他持仓类方法。按最新报告期查不到时，先不带日期查一次，看已有
          哪些报告期。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.top10-holders",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    # ---- 配置与持仓 ----

    def asset_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        asset_level: str | Sequence[str] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """资产配置（fund.asset-allocation）：「报告期末基金资产组合情况」口径，一只基金一个报告期
        按资产类型多行。

        ``assetType``（代码）+ ``assetTypeName``（中文）、``holdingValue``（**元**）、
        ``pctToTotalAsset``（**占基金资产总值**，不是占净值）。

        - asset_level: ``level1`` 一级 / ``level2`` 二级，单值或列表，不传两级都返回。写错时服务端
          报 100003 并点名（本地不校验）。**一二级混在同一结果里时别直接加总**，二级是一级的拆分。
        - 一级 assetType: ``equityInv`` 权益 / ``fundInv`` 基金 / ``fixedIncomeInv`` 固定收益 /
          ``preciousMetals`` 贵金属 / ``deriv`` 金融衍生品 / ``reverseRepo`` 买入返售 /
          ``moneyMarket`` 货币市场工具 / ``cash`` 银行存款和结算备付金 / ``otherAssets`` 其他。
        - 二级 assetType: ``stock`` 股票 / ``prefShares`` 优先股 / ``dr`` 存托凭证 / ``reits``
          （属权益）；``bond`` / ``abs``（属固定收益）；``forward`` / ``futures`` / ``option`` /
          ``warrant``（属衍生品）；``outrightReverseRepo``（属买入返售）。
        - 基金没有持有的资产类型可能不出现在结果里（而不是给一行 0），按「缺行 = 0」处理。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.asset-allocation",
            _fund_body(
                security,
                {
                    "startDate": start_date,
                    "endDate": end_date,
                    "assetLevelList": _optional_list(asset_level, name="asset_level"),
                },
            ),
            raw,
        )

    def stock_portfolio(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        position_type: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """股票持仓（fund.stock-portfolio）：每报告期按持仓多行。

        持股数量（**万股**）、占流通股比例、持仓市值（**万元**）、占净值比，以及 ``pctToNavChg``
        （较上一报告期的占净值比变化）。🔴 **只返回股票简称 ``stockName``，不返回代码**——要代码用
        ``reference.securities_search(keyword=<简称>)`` 换，注意 A / H 同名与改名。

        - position_type: ``top`` 重仓股票，各季度都披露（不传时的服务端默认）；``all`` 全部持股，
          **仅半年报与年报披露**——用 all 查一季度 / 三季度得到空结果，不是故障。all 的行数通常
          远多于 top（重仓只有前十只）。写错时服务端报 100003 并点名（本地不校验）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（季末日；YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都
        不传 = 账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部，不是只取最新一期——只要
        最新一期就把起止都设成那个报告期。🔴 start_date 早于窗口下界时整批报 110003（不会只返回
        窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.stock-portfolio",
            _fund_body(
                security,
                {"startDate": start_date, "endDate": end_date, "positionType": position_type},
            ),
            raw,
        )

    def industry_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        industry_standard: str | None = None,
        position_type: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """行业配置（fund.industry-allocation）：股票持仓按一级行业汇总的占净值比，每报告期按
        行业多行。

        - industry_standard: ``swIndustry`` 申万一级（不传时的服务端默认）/ ``citicIndustry`` 中信
          一级。``industryCode`` 与 ``reference.constant_list(category="swIndustry")`` /
          ``category="citicIndustry"`` 的常量 ID 一致。两套分类划分不同，跨基金比较时统一用一套。
          占比为 0 的行业也可能出现。
        - position_type: ``top`` 重仓（各季度都披露，服务端默认）/ ``all`` 全部持股（**仅半年报与
          年报披露**，查一季度 / 三季度得到空结果）。返回行带 ``positionType`` 列。
        - 两个枚举写错时服务端报 100003 并点名（本地不校验）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.industry-allocation",
            _fund_body(
                security,
                {
                    "startDate": start_date,
                    "endDate": end_date,
                    "industryStandard": industry_standard,
                    "positionType": position_type,
                },
            ),
            raw,
        )

    def bond_portfolio(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券持仓（fund.bond-portfolio）：每报告期按持仓多行。

        债券简称 ``bondName``（🔴 **无代码**）、持仓量（**万张**）、持仓市值（**万元**）、占净值比。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.bond-portfolio",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    def bond_type_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """券种配置（fund.bond-type-allocation）：债券持仓按券种汇总的占净值比，每报告期按券种多行。

        ``bondTypeCode`` 与 ``reference.constant_list(category="fundBondType")`` 一致。🔴
        **「金融债券」与「政策性金融债券」是两行、前者包含后者**，按券种加总会重复计算。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.bond-type-allocation",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    def fund_portfolio(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金持仓（fund.fund-portfolio，FOF）：持有其他基金的明细，每报告期按持仓多行。

        持仓基金简称 ``holdingFundName``（🔴 **无代码**）、持仓市值（**万元**）、占净值比。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.fund-portfolio",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    def fund_type_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """持仓基金类型配置（fund.fund-type-allocation，FOF）：持仓基金按基金分类（一级）汇总的
        占净值比。``investTypeCodeLevel1`` 与 ``reference.constant_list(category="fundType")`` 一致。

        🔴 **没有 position_type 参数**，口径随报告期而定、看返回的 ``positionType`` 列：季报期为
        ``top``（只含重仓基金），半年报 / 年报为 ``all``（全部持基）——同一只基金不同报告期的合计
        口径不同，做时序对比前先按 positionType 分开。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.fund-type-allocation",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    # ---- ETF ----

    def etf_pcf_header(
        self,
        *,
        security: str | Sequence[str],
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """ETF 申赎清单参数（fund.etf-pcf-header）：🔴 **只返回最新一份申购赎回清单**，无日期
        参数，查不了历史清单。``tradeDate`` 是清单对应的交易日（清单盘前发布，可能就是当天）。

        申赎允许情况（``允许申购·允许赎回`` 这种 ``·`` 分隔的组合）、最小申赎单位（份）及其净值
        （元）、单日申购 / 赎回上限（份，无上限为 null）、现金差额与预估现金（元，可为负）、现金
        替代比例上限（%）、``componentCount`` 成分记录数。

        security: ETF 交易代码（后缀大写 .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、后缀
        小写或传成股票代码都返回空结果、不报错。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query("fund.etf-pcf-header", _fund_body(security), raw)

    def etf_pcf_components(
        self,
        *,
        security: str | Sequence[str],
        component_code: bool = True,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """ETF 申赎成分清单（fund.etf-pcf-components）：🔴 **只返回最新一份申购赎回清单**，无
        日期参数，查不了历史清单。

        每个成分一行，按 ``serialNumber`` 排序：成分代码 ``componentCode``、成分名称
        ``componentName``、收盘价、涨跌幅、市值占比（%）、申购数量（股）、``cashSubstituteFlag``
        （``允许`` / ``必须``，中文）、申购 / 赎回现金替代溢价比例（%）、固定替代金额与申购 / 赎回
        替代金额（元）。

        - 🔴 **接口只返回成分名称，``componentCode`` 由 SDK 按名称匹配补上**，带市场后缀（如
          ``600519.SH`` / ``00941.HK`` / ``NVDA.O`` / 国债 ``019848.SH``）：

          - 按名称找证券（先查 A 股 / 港股 / 美股证券列表，没有再搜索），用该行的 ``close``
            核对候选证券的最新价或昨收；核对不上的（清单价格滞后于行情、停牌等）改按清单价格
            所属那天的收盘价核对，A 股与港股各自定日期。A+H 型 ETF 里同名的 A 股与 H 股两行
            靠价格分开。
          - 价格定不了时（债券、停牌、除权除息当天、行情查询失败，或价格同时对得上两个市场的
            同名证券）：成分都在同一市场的 ETF 取该市场里的那只，同市场多只时取与 ETF 同一
            交易所的；**A+H 等跨市场 ETF 里这类行为 null**，不按名称猜。有成分的名称查询失败时，
            无法确定 ETF 持有哪些市场，这类行同样为 null。
          - 匹配不到的为 null：现金行（如 ``申赎现金``）、商品（如 ``黄金9999``）、交易所简称
            与证券名称对不上的（如港股 ``港交所``、``中海油``）。每次匹配发一条 ``UserWarning``，
            写明匹配了多少行、列出为 null 的行。
        - 额外请求都免费：A 股 / 港股 / 美股证券列表各 1 次；列表里没有的名称（债券、被截断的
          简称、现金行等）逐个搜索；实时行情按候选代码每 500 个一次（多数 ETF 1 次）；有实时
          价格核对不上的行时，再按每 1000 个候选一次查日 K。某一批因含无效代码报 ``120001`` 时
          对半拆开重查，次数随之增加。``component_code=False`` 不发这些请求，返回接口原样的行
          （没有 ``componentCode``）。
        - ⚠️ 成分的 ``close`` 是清单给出的价格，日期可能早于 ``tradeDate`` 的前一交易日，一天之内
          还会更新，同一清单里 A 股与港股也可能不同；用价格计算请以 ``quote.day_kline`` /
          ``quote.realtime`` 为准。

        security: ETF 交易代码（后缀大写 .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、后缀
        小写或传成股票代码都返回空结果、不报错。

        宽基 ETF 动辄数百行，多只一起查注意单次 10000 行上限（超出整批报 100006、无部分结果）。
        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total；``componentCode`` 同样已补上）。
        """
        result = self._client._call("fund.etf-pcf-components", body=_fund_body(security))
        if component_code:
            result = add_component_codes(result, self._client, label=_ETF_COMPONENTS)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    def etf_share_change(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """ETF 份额变动（fund.etf-share-change）：逐交易日一行，按日期倒序。

        份额（**万份**）、规模（**万元**）及较上期变动，``sharesChangeRate`` 为份额变化率（%）。

        security: ETF 交易代码（后缀大写 .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、后缀
        小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**交易日**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部；只传 start_date = 从该日到
        最新，只传 end_date = 从窗口下界到该日。🔴 start_date 早于窗口下界时整批报 110003（不会只
        返回窗口内那段）；起 > 止报 110002。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return self._query(
            "fund.etf-share-change",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )


class AsyncFund:
    """Async mirror of `Fund`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def _query(
        self, endpoint_key: str, body: dict[str, Any], raw: bool
    ) -> pd.DataFrame | dict[str, Any]:
        result = await self._client._call(endpoint_key, body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- 资料与经理 ----

    async def basic_info(
        self,
        *,
        security: str | Sequence[str],
        field: str | Sequence[str] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金基本信息（fund.basic-info）：分类（一级 / 二级）、管理人与托管人、成立与存续、
        运行状态与运作方式、申赎规则、业绩比较基准、风险等级、投资范围、跟踪指数。

        当前资料，**不提供历史快照**，无日期参数。

        - security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带
          后缀、后缀小写或传成股票代码都返回空结果、不报错。
        - field: 要返回的字段名，单值或列表，不传返回全部；``fundCode`` 始终返回。字段名写错
          **整批报 100003** 并指名（本地不校验），不会静默丢列。``investScope`` 是长文本，批量
          导出时用 field 去掉可显著缩小体积。

        字段要点: ``mainFundCode`` 是 A / C 等份额共用的主代码，份额合并按它分组；
        ``investTypeCodeLevel1`` / ``investTypeCodeLevel2`` 与
        ``reference.constant_list(category="fundType")`` 的常量 ID 一致（FOF 类一级 ID 不是整百，
        如 149051404 混合型 FOF，按常量表的 level 判层级）；``exchange`` 场内为交易所名称（如
        上海证券交易所 / 深圳证券交易所），场外为 null；``isIndexFund`` 是布尔值，非指数基金的
        ``trackIndexCode`` / ``trackIndexName`` 为 null；``maturityDate`` 为 null 表示无固定存续期；
        ``largePurchaseLimit`` 为 null 表示不限。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.basic-info",
            _fund_body(security, {"fieldList": _optional_list(field, name="field")}),
            raw,
        )

    async def nav(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金净值（fund.nav）：逐交易日一行，按日期倒序。

        - ``navUnit`` 单位净值、``navAccumulated`` 累计净值、``adjustFactor`` 复权因子、
          ``navAdjusted`` 复权净值（**元**）。**算区间收益用 navAdjusted**，单位净值在分红 /
          拆分时会跳变。
        - 货币基金另有 ``mmfAnnualizedYield``（7 日年化，%）与 ``mmfUnitYield``（每万份收益，元），
          其 ``adjustFactor`` 为 null；非货币基金这两列为 null。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**交易日**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部；只传 start_date = 从该日到
        最新，只传 end_date = 从窗口下界到该日。🔴 start_date 早于窗口下界时整批报 110003（不会只
        返回窗口内那段）；起 > 止报 110002。

        不分页，单次上限 10000 行（每只每年约 240～250 行），超出整批报 100006、无部分结果——多只
        基金 × 长区间按只数分批。0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx /
        999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.nav",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    async def fee_rate(
        self,
        *,
        security: str | Sequence[str],
        fee_type: str | Sequence[str] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金费率（fund.fee-rate）：当前各类费率，按条件分档一档一行。无日期参数。

        - security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带
          后缀、后缀小写或传成股票代码都返回空结果、不报错。
        - fee_type: ``purchaseFee`` 申购 / ``redemptionFee`` 赎回 / ``managementFee`` 管理 /
          ``custodianFee`` 托管 / ``saleFee`` 销售服务；单值或列表，不传返回全部。写错时服务端
          报 100003 并点名（本地不校验）。

        一只基金一个费率类型可能多行——申购费按金额分档、赎回费按持有期限分档，每档一行，
        ``feeCondition`` 是条件区间（如 ``持有期限＜7日``），无分档为 null。🔴 ``feeRate`` 是
        **字符串**（``"1.5%"`` / ``"0%"``），大额固定收费时是金额描述（``"每笔1000元"``），
        不能直接当数字用。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.fee-rate",
            _fund_body(security, {"feeTypeList": _optional_list(fee_type, name="fee_type")}),
            raw,
        )

    async def manager_info(
        self,
        *,
        manager: str | Sequence[str],
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金经理基本信息（fund.manager-info）：学历、从业日期与年限、在管规模与只数、历任基金数
        与公司数、简介。

        🔴 **查的是人名，不是基金代码**。manager: 经理姓名，单值或列表（如 ``"张坤"``）；多人请传
        列表，名字原样发送，重复值去掉；空值本地报 ValidationError、不发请求。按姓名**精确匹配**，查不到返回空结果；同名经理**全部返回**（常见名可能一次多位），
        用 ``currentCompany`` 区分（可能为 null）。

        - ``managedFundScale`` 在管规模单位**亿元**。
        - ⚠️ ``workingYears``（从业年限）与由 ``careerStartDate`` 推算出的年限、简介里写的从业
          年数**可能对不上**，``currentCompanyYears`` 同理——需要准确的从业年限时按
          ``careerStartDate`` 自行计算。
        - ``birthYear`` 未披露时为 null。

        按次计费 0.4 积分/次（与返回行数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        names = _required_list(manager, name="manager")
        return await self._query(
            "fund.manager-info", _request_body({"managerNameList": names}), raw
        )

    async def manager_history(
        self,
        *,
        security: str | Sequence[str],
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金历任基金经理（fund.manager-history）：每位经理的每段任职各一行，同期共同管理的
        多位经理各占一行。无日期参数（返回全部任职记录）。

        ``endDate`` 为 null 的是**现任**；``managedDays`` 任职天数，``managedReturn`` 任职期间业绩
        表现（%）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query("fund.manager-history", _fund_body(security), raw)

    # ---- 规模与持有人 ----

    async def asset_size(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """资产规模（fund.asset-size）：每个报告期一行。

        期初份额、期间申购 / 赎回 / 净申购份额（赎回大于申购时为负）、期末份额（**万份**），
        基金资产净值（**万元**）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（季末日，如 ``2026-06-30``；YYYY-MM-DD，YYYY/MM/DD、
        YYYYMMDD 也收）。两端都不传 = 账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内
        全部，不是只取最新一期——只要最新一期就把起止都设成那个报告期。🔴 start_date 早于窗口
        下界时整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.asset-size",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    async def holder_structure(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """持有人结构（fund.holder-structure）：持有人户数、户均份额，机构 / 个人 / 员工持有份额
        （**份**）与占比（%）。**只有半年报与年报披露**，季报期没有行。

        - ``holderCount`` 为整数（如 ``2219140``）。
        - 占比字段可能为 null。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.holder-structure",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    async def top10_holders(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """前十大持有人（fund.top10-holders）：**仅上市基金**（LOF / ETF 等）。

        每个报告期按 ``serialNumber`` 排名各一行：持有人名称、持有份额（**份**）、占上市总份额
        比例（%）。半年报与年报披露。

        - 🔴 ETF 在前十名之外可能多一行 ``serialNumber = 11``，是该 ETF 的**联接基金**（定期报告
          单列披露），它的占比可能高于前十中的多位。只要前十名就按 ``serialNumber <= 10`` 过滤。
        - 最新一期的更新可能晚于其他持仓类方法。按最新报告期查不到时，先不带日期查一次，看已有
          哪些报告期。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.top10-holders",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    # ---- 配置与持仓 ----

    async def asset_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        asset_level: str | Sequence[str] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """资产配置（fund.asset-allocation）：「报告期末基金资产组合情况」口径，一只基金一个报告期
        按资产类型多行。

        ``assetType``（代码）+ ``assetTypeName``（中文）、``holdingValue``（**元**）、
        ``pctToTotalAsset``（**占基金资产总值**，不是占净值）。

        - asset_level: ``level1`` 一级 / ``level2`` 二级，单值或列表，不传两级都返回。写错时服务端
          报 100003 并点名（本地不校验）。**一二级混在同一结果里时别直接加总**，二级是一级的拆分。
        - 一级 assetType: ``equityInv`` 权益 / ``fundInv`` 基金 / ``fixedIncomeInv`` 固定收益 /
          ``preciousMetals`` 贵金属 / ``deriv`` 金融衍生品 / ``reverseRepo`` 买入返售 /
          ``moneyMarket`` 货币市场工具 / ``cash`` 银行存款和结算备付金 / ``otherAssets`` 其他。
        - 二级 assetType: ``stock`` 股票 / ``prefShares`` 优先股 / ``dr`` 存托凭证 / ``reits``
          （属权益）；``bond`` / ``abs``（属固定收益）；``forward`` / ``futures`` / ``option`` /
          ``warrant``（属衍生品）；``outrightReverseRepo``（属买入返售）。
        - 基金没有持有的资产类型可能不出现在结果里（而不是给一行 0），按「缺行 = 0」处理。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.asset-allocation",
            _fund_body(
                security,
                {
                    "startDate": start_date,
                    "endDate": end_date,
                    "assetLevelList": _optional_list(asset_level, name="asset_level"),
                },
            ),
            raw,
        )

    async def stock_portfolio(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        position_type: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """股票持仓（fund.stock-portfolio）：每报告期按持仓多行。

        持股数量（**万股**）、占流通股比例、持仓市值（**万元**）、占净值比，以及 ``pctToNavChg``
        （较上一报告期的占净值比变化）。🔴 **只返回股票简称 ``stockName``，不返回代码**——要代码用
        ``reference.securities_search(keyword=<简称>)`` 换，注意 A / H 同名与改名。

        - position_type: ``top`` 重仓股票，各季度都披露（不传时的服务端默认）；``all`` 全部持股，
          **仅半年报与年报披露**——用 all 查一季度 / 三季度得到空结果，不是故障。all 的行数通常
          远多于 top（重仓只有前十只）。写错时服务端报 100003 并点名（本地不校验）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（季末日；YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都
        不传 = 账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部，不是只取最新一期——只要
        最新一期就把起止都设成那个报告期。🔴 start_date 早于窗口下界时整批报 110003（不会只返回
        窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.stock-portfolio",
            _fund_body(
                security,
                {"startDate": start_date, "endDate": end_date, "positionType": position_type},
            ),
            raw,
        )

    async def industry_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        industry_standard: str | None = None,
        position_type: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """行业配置（fund.industry-allocation）：股票持仓按一级行业汇总的占净值比，每报告期按
        行业多行。

        - industry_standard: ``swIndustry`` 申万一级（不传时的服务端默认）/ ``citicIndustry`` 中信
          一级。``industryCode`` 与 ``reference.constant_list(category="swIndustry")`` /
          ``category="citicIndustry"`` 的常量 ID 一致。两套分类划分不同，跨基金比较时统一用一套。
          占比为 0 的行业也可能出现。
        - position_type: ``top`` 重仓（各季度都披露，服务端默认）/ ``all`` 全部持股（**仅半年报与
          年报披露**，查一季度 / 三季度得到空结果）。返回行带 ``positionType`` 列。
        - 两个枚举写错时服务端报 100003 并点名（本地不校验）。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.industry-allocation",
            _fund_body(
                security,
                {
                    "startDate": start_date,
                    "endDate": end_date,
                    "industryStandard": industry_standard,
                    "positionType": position_type,
                },
            ),
            raw,
        )

    async def bond_portfolio(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """债券持仓（fund.bond-portfolio）：每报告期按持仓多行。

        债券简称 ``bondName``（🔴 **无代码**）、持仓量（**万张**）、持仓市值（**万元**）、占净值比。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.bond-portfolio",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    async def bond_type_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """券种配置（fund.bond-type-allocation）：债券持仓按券种汇总的占净值比，每报告期按券种多行。

        ``bondTypeCode`` 与 ``reference.constant_list(category="fundBondType")`` 一致。🔴
        **「金融债券」与「政策性金融债券」是两行、前者包含后者**，按券种加总会重复计算。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.bond-type-allocation",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    async def fund_portfolio(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """基金持仓（fund.fund-portfolio，FOF）：持有其他基金的明细，每报告期按持仓多行。

        持仓基金简称 ``holdingFundName``（🔴 **无代码**）、持仓市值（**万元**）、占净值比。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.fund-portfolio",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    async def fund_type_allocation(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """持仓基金类型配置（fund.fund-type-allocation，FOF）：持仓基金按基金分类（一级）汇总的
        占净值比。``investTypeCodeLevel1`` 与 ``reference.constant_list(category="fundType")`` 一致。

        🔴 **没有 position_type 参数**，口径随报告期而定、看返回的 ``positionType`` 列：季报期为
        ``top``（只含重仓基金），半年报 / 年报为 ``all``（全部持基）——同一只基金不同报告期的合计
        口径不同，做时序对比前先按 positionType 分开。

        security: 基金交易代码（后缀大写 .OF / .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、
        后缀小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**报告期**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部。🔴 start_date 早于窗口下界时
        整批报 110003（不会只返回窗口内那段）；起 > 止报 110002；区间内没有报告期返回空。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.fund-type-allocation",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )

    # ---- ETF ----

    async def etf_pcf_header(
        self,
        *,
        security: str | Sequence[str],
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """ETF 申赎清单参数（fund.etf-pcf-header）：🔴 **只返回最新一份申购赎回清单**，无日期
        参数，查不了历史清单。``tradeDate`` 是清单对应的交易日（清单盘前发布，可能就是当天）。

        申赎允许情况（``允许申购·允许赎回`` 这种 ``·`` 分隔的组合）、最小申赎单位（份）及其净值
        （元）、单日申购 / 赎回上限（份，无上限为 null）、现金差额与预估现金（元，可为负）、现金
        替代比例上限（%）、``componentCount`` 成分记录数。

        security: ETF 交易代码（后缀大写 .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、后缀
        小写或传成股票代码都返回空结果、不报错。

        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query("fund.etf-pcf-header", _fund_body(security), raw)

    async def etf_pcf_components(
        self,
        *,
        security: str | Sequence[str],
        component_code: bool = True,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """ETF 申赎成分清单（fund.etf-pcf-components）：🔴 **只返回最新一份申购赎回清单**，无
        日期参数，查不了历史清单。

        每个成分一行，按 ``serialNumber`` 排序：成分代码 ``componentCode``、成分名称
        ``componentName``、收盘价、涨跌幅、市值占比（%）、申购数量（股）、``cashSubstituteFlag``
        （``允许`` / ``必须``，中文）、申购 / 赎回现金替代溢价比例（%）、固定替代金额与申购 / 赎回
        替代金额（元）。

        - 🔴 **接口只返回成分名称，``componentCode`` 由 SDK 按名称匹配补上**，带市场后缀（如
          ``600519.SH`` / ``00941.HK`` / ``NVDA.O`` / 国债 ``019848.SH``）：

          - 按名称找证券（先查 A 股 / 港股 / 美股证券列表，没有再搜索），用该行的 ``close``
            核对候选证券的最新价或昨收；核对不上的（清单价格滞后于行情、停牌等）改按清单价格
            所属那天的收盘价核对，A 股与港股各自定日期。A+H 型 ETF 里同名的 A 股与 H 股两行
            靠价格分开。
          - 价格定不了时（债券、停牌、除权除息当天、行情查询失败，或价格同时对得上两个市场的
            同名证券）：成分都在同一市场的 ETF 取该市场里的那只，同市场多只时取与 ETF 同一
            交易所的；**A+H 等跨市场 ETF 里这类行为 null**，不按名称猜。有成分的名称查询失败时，
            无法确定 ETF 持有哪些市场，这类行同样为 null。
          - 匹配不到的为 null：现金行（如 ``申赎现金``）、商品（如 ``黄金9999``）、交易所简称
            与证券名称对不上的（如港股 ``港交所``、``中海油``）。每次匹配发一条 ``UserWarning``，
            写明匹配了多少行、列出为 null 的行。
        - 额外请求都免费：A 股 / 港股 / 美股证券列表各 1 次；列表里没有的名称（债券、被截断的
          简称、现金行等）逐个搜索；实时行情按候选代码每 500 个一次（多数 ETF 1 次）；有实时
          价格核对不上的行时，再按每 1000 个候选一次查日 K。某一批因含无效代码报 ``120001`` 时
          对半拆开重查，次数随之增加。``component_code=False`` 不发这些请求，返回接口原样的行
          （没有 ``componentCode``）。
        - ⚠️ 成分的 ``close`` 是清单给出的价格，日期可能早于 ``tradeDate`` 的前一交易日，一天之内
          还会更新，同一清单里 A 股与港股也可能不同；用价格计算请以 ``quote.day_kline`` /
          ``quote.realtime`` 为准。

        security: ETF 交易代码（后缀大写 .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、后缀
        小写或传成股票代码都返回空结果、不报错。

        宽基 ETF 动辄数百行，多只一起查注意单次 10000 行上限（超出整批报 100006、无部分结果）。
        0.4 积分/次（与行数、只数无关；空结果与报错不扣）；超时 / 5xx / 999999 不自动重发。
        raw=True 返回原始 data（``{list}``，无 total；``componentCode`` 同样已补上）。
        """
        result = await self._client._call("fund.etf-pcf-components", body=_fund_body(security))
        if component_code:
            result = await add_component_codes_async(result, self._client, label=_ETF_COMPONENTS)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def etf_share_change(
        self,
        *,
        security: str | Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """ETF 份额变动（fund.etf-share-change）：逐交易日一行，按日期倒序。

        份额（**万份**）、规模（**万元**）及较上期变动，``sharesChangeRate`` 为份额变化率（%）。

        security: ETF 交易代码（后缀大写 .SH / .SZ），单值或列表。🔴 代码不存在、不带后缀、后缀
        小写或传成股票代码都返回空结果、不报错。

        start_date / end_date 筛**交易日**（YYYY-MM-DD，YYYY/MM/DD、YYYYMMDD 也收）。两端都不传 =
        账号可回溯窗口（正式账号 5 年、试用 3 年，以返回为准）内全部；只传 start_date = 从该日到
        最新，只传 end_date = 从窗口下界到该日。🔴 start_date 早于窗口下界时整批报 110003（不会只
        返回窗口内那段）；起 > 止报 110002。

        不分页，单次超 10000 行整批报 100006、无部分结果。0.4 积分/次（与行数、只数无关；空结果与
        报错不扣）；超时 / 5xx / 999999 不自动重发。raw=True 返回原始 data（``{list}``，无 total）。
        """
        return await self._query(
            "fund.etf-share-change",
            _fund_body(security, {"startDate": start_date, "endDate": end_date}),
            raw,
        )
