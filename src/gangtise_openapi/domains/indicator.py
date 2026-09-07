# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import EDE_NO_DATA_HINT, ApiError, ValidationError
from gangtise_openapi._indicator_matrix import (
    check_screener_bindings,
    dropped_from_matrix,
    flatten_cross_section,
    flatten_time_series,
    is_empty_matrix,
    parse_screener_indicators,
    require_indicator_matrix,
    screener_expression_fields,
)
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _request_body,
    _result_to_dataframe,
    _validate_date,
    _validate_top,
)

_KEY_BY_CHOICES = ("name", "code")

# Date parameters an indicator may already carry: if the caller named the period
# themselves, the query date must not be injected on top.
#
# 🔴 `fiscalYear` is deliberately NOT here, and that was settled empirically rather
# than argued. It looks like a period selector, and adding it would fix the two
# indicators that take ONLY fiscalYear (`div_cash_paid_ratio`, `div_cash_yr`) — but
# a live `indicator.search` sweep of 323 indicators (2026-08-15, free endpoint)
# found **5 that require fiscalYear AND tradeDate**: `frcst_op_rev`,
# `frcst_op_rev_yoy`, `frcst_shnp`, `frcst_shnp_yoy`, `frcst_pe` (the consensus
# forecast family). Treating fiscalYear as "already dated" would suppress the
# injection on those and break a call that works today. The fiscalYear-only pair is
# served by the explicit suppression marker instead (see `_wants_injected_date`).
#
# `sDate` is not here either: for interval indicators (`qte_vol_intvl`,
# `qte_avg_vol`) it is the interval START while the required `tradeDate` is its
# END, so treating it as a replacement dropped the query date and silently moved
# the interval end (probed by the CLI 2026-08-02: 茅台 sDate=2024-01-02 returned
# 2,265,873,849 without a tradeDate vs 65,687,435 with tradeDate=2024-01-31, both
# "successful"). A SELECTOR replaces the query date; a RANGE BOUND does not.
_DATE_PARAM_KEYS = frozenset({"tradeDate", "reportDate"})


def _check_key_by(key_by: str) -> None:
    """key_by picks the column header source: ``name`` (display name, default) or
    ``code`` (indicatorCode / securityCode — unique and order-stable, required for
    batch code→value mapping; TS v0.28.2). Reject anything else rather than
    silently falling back to name, which would hand a code-batch caller name
    headers without warning — the exact failure this option exists to remove."""
    if key_by not in _KEY_BY_CHOICES:
        raise ValidationError(
            f"invalid key_by: {key_by!r} is not one of {'/'.join(_KEY_BY_CHOICES)}"
        )


def _require_scope(indicator: Any, security: Any) -> tuple[list[str], list[str]]:
    """Both axes are required by every matrix endpoint. Omitting one costs a round
    trip to be told ``100001``, whose message points at the API's own parameter
    names rather than the kwargs the caller typed."""
    indicators = _as_list(indicator) or []
    securities = _as_list(security) or []
    missing = [
        name for name, values in (("indicator", indicators), ("security", securities)) if not values
    ]
    if missing:
        raise ValidationError(
            f"{' and '.join(missing)} {'are' if len(missing) > 1 else 'is'} required — "
            "every EDE matrix endpoint needs at least one of each"
        )
    return [str(code) for code in indicators], [str(code) for code in securities]


def _param_groups(spec: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Normalize ``{code: {key: value}}`` into the nested wire form, keyed by code
    so the query date can be merged in without duplicating a group."""
    return {
        code: {
            "indicatorCode": code,
            # A ``None`` value is a SUPPRESSION MARKER, not a value: it says "this
            # indicator does not take this key", so it must never reach the wire
            # (``str(None)`` would send the literal "None").
            "parameters": [
                {"paramKey": k, "paramValue": str(v)} for k, v in params.items() if v is not None
            ],
        }
        for code, params in (spec or {}).items()
    }


def _wants_injected_date(
    key: str, explicit: dict[str, dict[str, Any]], group: dict[str, Any]
) -> bool:
    """Whether ``key`` still needs the query date injected as ``tradeDate``.

    No, if it already carries a date parameter of its own — the caller named the
    period. And no, if the caller explicitly marked it as taking no ``tradeDate``:

    * ``{"<code>": {}}`` — an empty mapping: the indicator takes no parameters at
      all (an empty ``parameterList``).
    * ``{"<code>": {"currency": "CNY", "tradeDate": None}}`` — a ``None`` marks that
      one key as unwanted while every other parameter still travels. Needed whenever
      ``parameterList`` has no ``tradeDate`` but does have something else:
      ``div_cash_yr`` (fiscalYear), ``pty_shr_reg`` (currency / scale), and others.
      This is also why ``fiscalYear`` is not simply listed in ``_DATE_PARAM_KEYS``:
      the ``frcst_*`` family requires fiscalYear AND tradeDate (probed 2026-08-15).

    🔴 **The criterion is the presence of ``tradeDate`` in ``parameterList``, and
    nothing else** — not the code prefix, not "is this a static attribute". The
    ``is_*`` family has ``reportDate`` but no ``tradeDate`` and is equally affected;
    it just happens to be served by the caller supplying ``reportDate``, which trips
    the ``_DATE_PARAM_KEYS`` branch above. Judging by "has tradeDate OR reportDate"
    would wrongly clear that whole family.

    The server REJECTS a stray ``tradeDate`` on all of these with
    ``100003 不支持参数 tradeDate``, so injecting unconditionally makes them
    unreachable. All three clients carry this escape hatch now — the CLI took it in
    v0.35.0 (``--indicator-param "<code>:"`` on cross-section) and v0.36.0
    (``--indicator-param "<var>:"`` on the screener, keyed by the variable exactly as
    here), gangtise-mcp spells it ``noQueryDate: true``. Same semantics, three
    spellings — and on the screener all three key it by the VARIABLE, not the code.

    Opt-in on purpose: it only fires on an explicit marker, so no existing call
    changes behaviour. ``key`` is the indicator code for cross-section and the
    VARIABLE for the screener, matching how each indexes ``indicator_param``.

    ``None`` is not a new convention: across every wrapper boundary in this SDK a
    ``None`` already means "do not send this field" — that is exactly what
    ``_request_body`` → ``_strip_none`` does for every optional kwarg. This is the
    same convention one level down, which is why it beats inventing a sentinel.

    ⚠️ **Known blind spot**: a misspelled PARAM KEY is silently inert —
    ``{"tradDate": None}`` neither suppresses nor errors, and the injection happens
    as usual. Param keys are per-indicator (whatever ``parameterList`` declares),
    so there is no local whitelist to check against; the server treats a
    misspelled param name the same way. Recorded rather than fixed — see
    bug/python-open.md P6. (A misspelled INDICATOR CODE — the outer key — IS caught:
    see :func:`_assert_param_codes_bound`.)
    """
    if any(p["paramKey"] in _DATE_PARAM_KEYS for p in group["parameters"]):
        return False
    marker = explicit.get(key)
    if marker is None:
        return True
    return marker != {} and "tradeDate" not in marker


def _assert_param_codes_bound(spec: dict[str, dict[str, Any]] | None, codes: Sequence[str]) -> None:
    """Every ``indicator_param`` key must name an indicator that ``indicator`` lists.

    The screener has enforced the equivalent since it shipped
    (:func:`check_screener_bindings` rejects a param for an unbound ``F<n>``);
    ``cross_section`` and ``time_series`` did not, so a mistyped code went out as a
    parameter group for an indicator that was never queried::

        indicator="is_op_rev", indicator_param={"is_op_rve": {"reportDate": "..."}}
        → indicatorCodeList: ["is_op_rev"],  indicatorParamList: [{"is_op_rve", …}]

    On ``time_series`` that is silent end to end — nothing there injects a date, so
    no conflict ever exposes it and the parameters the caller believes they set
    simply never apply; the query runs on whatever the server defaults to. Mistyping
    the SUPPRESSION marker (``{"<code>": {}}``) is worse still: the real indicator
    keeps the injected ``tradeDate``, which is the exact thing the marker exists to
    remove (TS v0.37.0 ``assertParamCodesBound``).
    """
    if not spec:
        return
    bound = set(codes)
    for code in spec:
        if code not in bound:
            raise ValidationError(
                f"indicator_param references {code!r}, which is not in indicator="
                f"{list(codes)!r} — check the spelling; a parameter group for an "
                "indicator that was never queried has no effect"
            )


def _with_query_date(
    spec: dict[str, dict[str, Any]] | None, codes: list[str], date: str
) -> list[dict[str, Any]]:
    """Send ``date`` as each indicator's own ``tradeDate``.

    The root-level ``date`` field was retired by the 2026-08-01 API revision; the
    query date now rides on every indicator's parameter list. An indicator that
    already carries a date parameter keeps the caller's — forwarding their own
    field is the more honest request, and it survives a server-side rollback.

    ⚠️ Report-period indicators (``is_*`` and friends) REJECT ``tradeDate`` since
    2026-08-14 (``100003 不支持参数 tradeDate; 缺少必填参数 reportDate``); pass
    ``indicator_param={"code": {"reportDate": "..."}}`` for those. Which date a
    given indicator wants is not derivable from its code prefix — read
    ``parameterList`` from ``indicator.search``.

    A few indicators take no date at all, or only ``fiscalYear``; see
    ``_wants_injected_date`` for the two explicit suppression markers.
    """
    # The query date no longer travels as a body field, so ``_request_body``'s
    # guard never sees it — validate here or an ambiguous layout like "07/01/2026"
    # reaches the server, which reads it as a different day depending on the
    # separator, with nothing in the response saying which.
    _validate_date(date, "date")
    merged = _param_groups(spec)
    explicit = spec or {}
    for code in codes:
        group = merged.get(code)
        if group is None:
            merged[code] = {
                "indicatorCode": code,
                "parameters": [{"paramKey": "tradeDate", "paramValue": date}],
            }
        elif _wants_injected_date(code, explicit, group):
            group["parameters"].append({"paramKey": "tradeDate", "paramValue": date})
    return list(merged.values())


def _screener_indicator_list(
    bindings: dict[str, str], params: dict[str, dict[str, Any]] | None, expression: str, date: str
) -> list[dict[str, Any]]:
    """Screener bindings with the query date attached to every variable that takes one.

    Same rule as cross-section, including the same opt-out: a variable whose
    indicator declares no ``tradeDate`` in its ``parameterList`` is excused by a
    suppression marker — ``{"F1": {}}`` or ``{"F1": {"tradeDate": None}}``, keyed by
    the VARIABLE rather than the indicator code. ``_wants_injected_date`` decides
    here exactly as it does there; the marker itself never reaches the wire.

    Worth spelling out because the opt-out was unreachable here until recently:
    through 2026-08-16 the screener silently DROPPED any binding sent with
    ``parameters: []``, so suppressing the date lost the variable instead of freeing
    it. Fixed 2026-08-17 (probed: ``scr_exchg_sctr contains '创业板'`` now survives
    and filters). Injecting unconditionally instead is not the safe default it looks
    like — these indicators answer ``100003 不支持参数 tradeDate`` for the WHOLE
    request, so it makes them unreachable from the other side.
    """
    _validate_date(date, "date")
    indicators = parse_screener_indicators(bindings, params, expression)
    explicit = params or {}
    for item in indicators:
        if _wants_injected_date(item["field"], explicit, item):
            item["parameters"] = [
                *item["parameters"],
                {"paramKey": "tradeDate", "paramValue": date},
            ]
    return indicators


def _note_empty_matrix(data: Any) -> None:
    """An all-empty matrix no longer means "no data".

    Since 2026-08-07 a real coverage gap comes back as a null cell with its row
    and column intact, so an empty answer means nothing in the request RESOLVED —
    every security code or every indicator code was unrecognised — or a parameter
    name is wrong."""
    warnings.warn(
        "the indicator query returned no data at all. Since a real coverage gap now "
        "comes back as a null cell rather than an empty table, this usually means "
        "NOTHING in the request resolved — every security code or every indicator code "
        "was unrecognised — or a parameter name is wrong. Cross-check codes against "
        "gangtise.indicator.search(...) and gangtise.reference.securities_search(...).",
        stacklevel=3,
    )


def _flag_dropped(
    rows: dict[str, Any], data: Any, securities: list[str], indicators: list[str]
) -> None:
    """Mark and announce the codes the server did not resolve.

    A coverage gap is padded with ``null`` these days, so an axis that vanished is
    a code the server could not RESOLVE — a misspelling, or a security with the
    wrong market suffix. That is invisible otherwise: ``key_by='code'`` mapping
    finds no key at all rather than a null. Flagged on the result dict (machine
    readable) and warned (visible on the DataFrame path, which drops the extra
    keys) — the same partial contract ``_pagination`` and ``quote`` already use.
    """
    if is_empty_matrix(data):
        _note_empty_matrix(data)
        return
    dropped_securities, dropped_indicators = dropped_from_matrix(data, securities, indicators)
    if not dropped_securities and not dropped_indicators:
        return
    rows["partial"] = True
    if dropped_securities:
        rows["omittedSecurities"] = dropped_securities
    if dropped_indicators:
        rows["omittedIndicators"] = dropped_indicators
    parts = []
    if dropped_securities:
        parts.append(f"securities {', '.join(dropped_securities)}")
    if dropped_indicators:
        parts.append(f"indicators {', '.join(dropped_indicators)}")
    warnings.warn(
        f"the server returned no row/column at all for {' and '.join(parts)}; results are "
        "partial. An indicator it merely has no data for still returns a null cell, so "
        "this normally means the code was not recognised — check spelling and market "
        "suffix (AAPL.O, not AAPL.US).",
        stacklevel=3,
    )


def _flag_screener(
    rows: dict[str, Any],
    data: Any,
    bindings: list[dict[str, Any]],
    expression: str,
) -> None:
    """Validate the screener's variable bindings and flag missing output columns.

    No dropped-row flag here: a security missing from a screener result means it
    failed the expression, which is the whole point of the endpoint.
    """
    unbound = check_screener_bindings(data, bindings, expression)
    # Same ambiguity as the other matrix endpoints: an empty screen is a normal
    # answer AND what a wrong parameter name produces. Keyed on "nothing matched"
    # rather than the strict canonical-empty shape — a response returning zero
    # securities while still echoing `indicatorList` is just as empty to the
    # caller, and just as ambiguous, but would slip past ``is_empty_matrix``.
    if not data.get("securityCodeList"):
        warnings.warn(
            "nothing matched the expression. That is a normal answer — but an empty "
            "result is ALSO what an unrecognised code or a wrong parameter name "
            "produces. Cross-check the indicator codes and parameters against "
            "gangtise.indicator.search(...).",
            stacklevel=3,
        )
    if not unbound:
        return
    # Whatever reached here still leaves the expression evaluable (or was never
    # read by it), so the rows stand: losing the column costs information, not
    # correctness, and it degrades rather than failing.
    by_field = {item["field"]: item["indicatorCode"] for item in bindings}
    rows["partial"] = True
    rows["omittedIndicators"] = [by_field.get(field, field) for field in unbound]
    filtered_on = set(screener_expression_fields(expression))
    also_filtered = [field for field in unbound if field in filtered_on]
    note = (
        f" The expression also filters on {', '.join(also_filtered)}, so that condition "
        "was applied to none of these rows — another branch of the expression could "
        "still have matched them legitimately, but verify before relying on that filter."
        if also_filtered
        else ""
    )
    warnings.warn(
        f"{', '.join(unbound)} produced no column at all — those output values are "
        "missing. An indicator the server merely has no data for still returns a null "
        "column, so this normally means the bound code was not recognised; check it "
        f"against gangtise.indicator.search(...).{note} Results are partial.",
        stacklevel=3,
    )


def _search_result(result: Any) -> Any:
    """Peel the (historically double-wrapped) search payload.

    ``indicator.search`` takes only a keyword, so the EDE date/scope/param hint
    would be nonsense here — a 999999 keeps the generic hint (TS v0.28.2).
    """
    from gangtise_openapi._transport import unwrap_envelope

    return unwrap_envelope(result)


def _matrix_payload(result: Any) -> dict[str, Any]:
    """Unwrap a matrix response, re-pointing a 999999 at the EDE no-data hint.

    This path is past the transport, so ``_apply_policy_hint`` never saw an inner
    envelope's code.
    """
    try:
        return require_indicator_matrix(result)
    except ApiError as error:
        if error.code == "999999":
            error.hint = EDE_NO_DATA_HINT
        raise


class Indicator:
    """`gangtise.indicator.*` — 证券级数据指标 (EDE): 搜索指标码、截面、时序、条件选股。"""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def search(
        self,
        *,
        keyword: str,
        limit: int = 50,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索数据指标（indicator.search）。

        keyword 传指标词如 "收盘价" "成交量" "营业收入"（不是自然语言问题）;
        limit 默认 50、上限 100。返回 indicatorCode 供 cross_section / time_series /
        screener 使用。**参数名一律以返回里的 parameterList 为准**, 不要照抄文档示例——
        服务端会改参数名, 而传错是静默失效。
        """
        body = {"keyword": keyword, "limit": _validate_top(limit, name="limit", max_value=100)}
        result = self._client._call("indicator.search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(_search_result(result))

    def cross_section(
        self,
        *,
        date: str,
        indicator: FilterValue,
        security: FilterValue,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        key_by: str = "name",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取截面数据（indicator.cross-section）: 多指标 × 多证券, 单日期。

        每行一只证券, 每列一个指标。security 也接受板块 ID（reference.sector_search 返回的
        10 位 sectorId, 与证券代码混传取并集）。currency 取值 DFT/CNY/HKD/USD/...（默认 DFT）;
        scale 取值 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0, 且根级 scale 会污染不声明
        scale 的指标, 价格与金额混查请改用 indicator_param）。

        date 作为每个指标各自的 tradeDate 下发（根级 date 已于 2026-08-01 废弃）。
        ⚠️ 报告期类指标（is_* 等）自 2026-08-14 起**拒收 tradeDate**, 须用
        indicator_param={"is_xxx": {"reportDate": "2025-12-31"}}; 哪个指标吃哪个日期不能按
        code 前缀推断, 以 search 的 parameterList 为准。前复权参数名是 **adjustType**
        （不是 adjustmentType, 传错会静默退回不复权）。

        ⚠️ **判据只看一个键**: 注入的 tradeDate 会被拒（100003 不支持参数 tradeDate）,
        当且仅当该指标的 parameterList 里**没有 tradeDate**。按 search() 返回的
        parameterList 分四种情形——别按指标类别猜:

        1. 有 tradeDate → 什么都不用做
        2. 无 tradeDate、有 reportDate（is_* 那族就是）→ 传
           {"<code>": {"reportDate": "2025-12-31"}}, SDK 见到日期键就不再注入
        3. 无 tradeDate、但有别的参数（currency / scale / fiscalYear / industryLevel …）
           → 传那些参数**再加** "tradeDate": None, 例如
           {"pty_shr_reg": {"currency": "CNY", "tradeDate": None}}——None 表示
           「该指标不要这个键」, 不会发到线上, 其余参数照常下发
        4. parameterList 为空 → 传 {"<code>": {}}

        第 3 种最容易写错成第 4 种: `pty_shr_reg` 看着像「静态属性」, 但它有
        currency / scale, 传 {} 会把这两个参数一起丢掉且没有任何提示。

        key_by 取 name（默认, 列头用服务端给的指标显示名）或 code（列头就是你传进去的
        indicatorCode）。服务端按自己的顺序返回列, 位置索引不可靠; 批量按 code 回填用 code 模式。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        body = _request_body(
            {
                "indicatorCodeList": indicators,
                "universe": securities,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _with_query_date(indicator_param, indicators, date),
            }
        )
        result = self._client._call("indicator.cross-section", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        data = _matrix_payload(result)
        rows = flatten_cross_section(data, key_by)
        _flag_dropped(rows, data, securities, indicators)
        return _result_to_dataframe(rows)

    def time_series(
        self,
        *,
        start_date: str,
        end_date: str,
        indicator: FilterValue,
        security: FilterValue,
        calendar_type: str | None = None,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        key_by: str = "name",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取时序数据（indicator.time-series）: 多指标 × 单证券 或 单指标 × 多证券。

        每行一个日期。security 也接受板块 ID（单个 sectorId 会被服务端展开成 N 只成分股,
        此时列头按证券出）。calendar_type 取值 ND=自然日 TD=交易日 WD=工作日（默认 TD）;
        currency / scale / indicator_param 同 cross_section。

        key_by 取 name（默认）或 code（列头就是你传进去的 indicatorCode / securityCode;
        服务端按自己的顺序返回列, 位置索引不可靠）。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        body = _request_body(
            {
                "indicatorCodeList": indicators,
                "universe": securities,
                "startDate": start_date,
                "endDate": end_date,
                "calendarType": calendar_type,
                "currency": currency,
                "scale": scale,
                # The endpoint requires the key even with nothing to configure.
                "indicatorParamList": list(_param_groups(indicator_param).values()),
            }
        )
        result = self._client._call("indicator.time-series", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        data = _matrix_payload(result)
        # Pass the universe itself, not a count: the flattener needs to know
        # whether a sector ID was asked for, since the server expands it and the
        # request count then says nothing about which axis the columns are.
        rows = flatten_time_series(data, key_by, securities)
        _flag_dropped(rows, data, securities, indicators)
        return _result_to_dataframe(rows)

    def screener(
        self,
        *,
        date: str,
        expression: str,
        indicator: dict[str, str],
        security: FilterValue,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        key_by: str = "name",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """条件选股（indicator.screener）: 按表达式从证券/板块范围里筛出命中的股票。

        indicator 是 {变量: 指标码} 绑定, 如 {"F1": "qte_mkt_cptl", "F2": "finc_pe_ttm"};
        变量名必须是 F + 正整数。expression 用这些变量组合筛选, 如
        "F1 >= 500 && F2 <= 30", 也支持 contains / notcontains 文本匹配（仅 dataType
        为 string 的指标）。同一个指标可以绑到两个变量取不同参数（如比较两个日期的收盘价）——
        所以 indicator_param **按变量索引**, 如 {"F1": {"scale": "8"}}, 不是按 code。

        date 作为每个变量的 tradeDate 下发; 漏传会让吃日期的指标不被过滤并静默返回空结果,
        因此它是必填的。报告期类指标同 cross_section, 用 indicator_param 传 reportDate。

        输出同 cross_section 的宽表（每行一只命中的证券）。

        ⚠️ 同 cross_section 的四种情形, 只是**按变量索引**: 判据是该指标的 parameterList
        里有没有 tradeDate。无 tradeDate、有别的参数时传那些参数再加 "tradeDate": None
        （如 {"F1": {"currency": "CNY", "tradeDate": None}}）; parameterList 为空才传
        {"F1": {}}。写成 {} 会把该指标本来要的参数一起丢掉且没有提示。
        """
        _check_key_by(key_by)
        if not isinstance(indicator, dict) or not indicator:
            raise ValidationError(
                "indicator is required and must be a {variable: code} mapping, "
                'e.g. {"F1": "qte_mkt_cptl"}'
            )
        _, securities = _require_scope(list(indicator.values()), security)
        bindings = _screener_indicator_list(indicator, indicator_param, expression, date)
        body = _request_body(
            {
                "universe": securities,
                "expression": expression,
                "indicatorList": bindings,
            }
        )
        result = self._client._call("indicator.screener", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        data = _matrix_payload(result)
        # Flatten FIRST: it asserts the payload's structural axes, and a response
        # missing `indicatorList` outright deserves that diagnosis rather than
        # being reported as a binding problem. Nothing is emitted in between, so
        # ordering the structural check ahead of the semantic one is free.
        rows = flatten_cross_section(data, key_by)
        _flag_screener(rows, data, bindings, expression)
        return _result_to_dataframe(rows)


class AsyncIndicator:
    """Async mirror of `Indicator`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def search(
        self,
        *,
        keyword: str,
        limit: int = 50,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """按关键词搜索数据指标（indicator.search）。

        keyword 传指标词如 "收盘价" "成交量" "营业收入"（不是自然语言问题）;
        limit 默认 50、上限 100。返回 indicatorCode 供 cross_section / time_series /
        screener 使用。**参数名一律以返回里的 parameterList 为准**, 不要照抄文档示例——
        服务端会改参数名, 而传错是静默失效。
        """
        body = {"keyword": keyword, "limit": _validate_top(limit, name="limit", max_value=100)}
        result = await self._client._call("indicator.search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(_search_result(result))

    async def cross_section(
        self,
        *,
        date: str,
        indicator: FilterValue,
        security: FilterValue,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        key_by: str = "name",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取截面数据（indicator.cross-section）: 多指标 × 多证券, 单日期。

        每行一只证券, 每列一个指标。security 也接受板块 ID（reference.sector_search 返回的
        10 位 sectorId, 与证券代码混传取并集）。currency 取值 DFT/CNY/HKD/USD/...（默认 DFT）;
        scale 取值 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0, 且根级 scale 会污染不声明
        scale 的指标, 价格与金额混查请改用 indicator_param）。

        date 作为每个指标各自的 tradeDate 下发（根级 date 已于 2026-08-01 废弃）。
        ⚠️ 报告期类指标（is_* 等）自 2026-08-14 起**拒收 tradeDate**, 须用
        indicator_param={"is_xxx": {"reportDate": "2025-12-31"}}; 哪个指标吃哪个日期不能按
        code 前缀推断, 以 search 的 parameterList 为准。前复权参数名是 **adjustType**
        （不是 adjustmentType, 传错会静默退回不复权）。

        ⚠️ **判据只看一个键**: 注入的 tradeDate 会被拒（100003 不支持参数 tradeDate）,
        当且仅当该指标的 parameterList 里**没有 tradeDate**。按 search() 返回的
        parameterList 分四种情形——别按指标类别猜:

        1. 有 tradeDate → 什么都不用做
        2. 无 tradeDate、有 reportDate（is_* 那族就是）→ 传
           {"<code>": {"reportDate": "2025-12-31"}}, SDK 见到日期键就不再注入
        3. 无 tradeDate、但有别的参数（currency / scale / fiscalYear / industryLevel …）
           → 传那些参数**再加** "tradeDate": None, 例如
           {"pty_shr_reg": {"currency": "CNY", "tradeDate": None}}——None 表示
           「该指标不要这个键」, 不会发到线上, 其余参数照常下发
        4. parameterList 为空 → 传 {"<code>": {}}

        第 3 种最容易写错成第 4 种: `pty_shr_reg` 看着像「静态属性」, 但它有
        currency / scale, 传 {} 会把这两个参数一起丢掉且没有任何提示。

        key_by 取 name（默认, 列头用服务端给的指标显示名）或 code（列头就是你传进去的
        indicatorCode）。服务端按自己的顺序返回列, 位置索引不可靠; 批量按 code 回填用 code 模式。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        body = _request_body(
            {
                "indicatorCodeList": indicators,
                "universe": securities,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _with_query_date(indicator_param, indicators, date),
            }
        )
        result = await self._client._call("indicator.cross-section", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        data = _matrix_payload(result)
        rows = flatten_cross_section(data, key_by)
        _flag_dropped(rows, data, securities, indicators)
        return _result_to_dataframe(rows)

    async def time_series(
        self,
        *,
        start_date: str,
        end_date: str,
        indicator: FilterValue,
        security: FilterValue,
        calendar_type: str | None = None,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        key_by: str = "name",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取时序数据（indicator.time-series）: 多指标 × 单证券 或 单指标 × 多证券。

        每行一个日期。security 也接受板块 ID（单个 sectorId 会被服务端展开成 N 只成分股,
        此时列头按证券出）。calendar_type 取值 ND=自然日 TD=交易日 WD=工作日（默认 TD）;
        currency / scale / indicator_param 同 cross_section。

        key_by 取 name（默认）或 code（列头就是你传进去的 indicatorCode / securityCode;
        服务端按自己的顺序返回列, 位置索引不可靠）。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        body = _request_body(
            {
                "indicatorCodeList": indicators,
                "universe": securities,
                "startDate": start_date,
                "endDate": end_date,
                "calendarType": calendar_type,
                "currency": currency,
                "scale": scale,
                # The endpoint requires the key even with nothing to configure.
                "indicatorParamList": list(_param_groups(indicator_param).values()),
            }
        )
        result = await self._client._call("indicator.time-series", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        data = _matrix_payload(result)
        # Pass the universe itself, not a count: the flattener needs to know
        # whether a sector ID was asked for, since the server expands it and the
        # request count then says nothing about which axis the columns are.
        rows = flatten_time_series(data, key_by, securities)
        _flag_dropped(rows, data, securities, indicators)
        return _result_to_dataframe(rows)

    async def screener(
        self,
        *,
        date: str,
        expression: str,
        indicator: dict[str, str],
        security: FilterValue,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        key_by: str = "name",
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """条件选股（indicator.screener）: 按表达式从证券/板块范围里筛出命中的股票。

        indicator 是 {变量: 指标码} 绑定, 如 {"F1": "qte_mkt_cptl", "F2": "finc_pe_ttm"};
        变量名必须是 F + 正整数。expression 用这些变量组合筛选, 如
        "F1 >= 500 && F2 <= 30", 也支持 contains / notcontains 文本匹配（仅 dataType
        为 string 的指标）。同一个指标可以绑到两个变量取不同参数（如比较两个日期的收盘价）——
        所以 indicator_param **按变量索引**, 如 {"F1": {"scale": "8"}}, 不是按 code。

        date 作为每个变量的 tradeDate 下发; 漏传会让吃日期的指标不被过滤并静默返回空结果,
        因此它是必填的。报告期类指标同 cross_section, 用 indicator_param 传 reportDate。

        输出同 cross_section 的宽表（每行一只命中的证券）。

        ⚠️ 同 cross_section 的四种情形, 只是**按变量索引**: 判据是该指标的 parameterList
        里有没有 tradeDate。无 tradeDate、有别的参数时传那些参数再加 "tradeDate": None
        （如 {"F1": {"currency": "CNY", "tradeDate": None}}）; parameterList 为空才传
        {"F1": {}}。写成 {} 会把该指标本来要的参数一起丢掉且没有提示。
        """
        _check_key_by(key_by)
        if not isinstance(indicator, dict) or not indicator:
            raise ValidationError(
                "indicator is required and must be a {variable: code} mapping, "
                'e.g. {"F1": "qte_mkt_cptl"}'
            )
        _, securities = _require_scope(list(indicator.values()), security)
        bindings = _screener_indicator_list(indicator, indicator_param, expression, date)
        body = _request_body(
            {
                "universe": securities,
                "expression": expression,
                "indicatorList": bindings,
            }
        )
        result = await self._client._call("indicator.screener", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        data = _matrix_payload(result)
        # Flatten FIRST: it asserts the payload's structural axes, and a response
        # missing `indicatorList` outright deserves that diagnosis rather than
        # being reported as a binding problem. Nothing is emitted in between, so
        # ordering the structural check ahead of the semantic one is free.
        rows = flatten_cross_section(data, key_by)
        _flag_screener(rows, data, bindings, expression)
        return _result_to_dataframe(rows)
