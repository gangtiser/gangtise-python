# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio
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
from gangtise_openapi._logging import get_logger
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _request_body,
    _result_to_dataframe,
    _validate_date,
    _validate_top,
)

logger = get_logger()

_KEY_BY_CHOICES = ("name", "code")

# A parameter whose KEY ends in "date" (any case — reportDate, tradeDate, sDate,
# baseDate …) gets the same check as ``date``: the three year-first layouts are
# normalized to YYYY-MM-DD and a year-last one is refused, because the API reads
# "01-07-2026" as 7 January (TS v0.44.0 ⑧, ``/date$/i`` in parseParamSpecs).
_DATE_PARAM_SUFFIX = re.compile(r"date\Z", re.IGNORECASE)

# ── time-series calendar auto-selection (TS v0.40.0 ⑬-⑮, core/calendarType.ts) ──
# `tradeDate` is the only key that makes a trading-day axis correct; the other two
# mark an indicator whose values land on dates the trading calendar may not contain.
# `fiscalYear` stays although it names a forecast year, not a date: the indicators
# that take it with `tradeDate` (frcst_*) carry values on every calendar day, holidays
# included, and those values move (CLI probe 2026-09-30: frcst_pe, 600519.SH,
# 2025-09-25..10-15 — ND 21 of 21 cells filled; TD keeps 11 and drops the changes).
_TRADE_DATE_KEY = "tradeDate"
_PERIOD_DATE_KEYS = frozenset({"reportDate", "fiscalYear"})
# How many `indicator.search` probes run at once. They are free and read-only, and a
# time series takes at most a handful of indicators, so this only bounds the burst.
_PROBE_CONCURRENCY = 5
# `indicator.search` matches on a keyword, so the code itself is the query and the
# answer is picked out of the hits by exact code (near-matches come back too).
_PROBE_LIMIT = 100

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
    indicators = _as_list(indicator, "indicator") or []
    securities = _as_list(security, "security") or []
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
    unreachable. The CLI carries the same escape hatch — it took it in v0.35.0
    (``--indicator-param "<code>:"`` on cross-section) and v0.36.0
    (``--indicator-param "<var>:"`` on the screener). Same semantics, different
    spelling — and on the screener both key it by the VARIABLE, not the code.

    Opt-in on purpose: it only fires on an explicit marker, so no existing call
    changes behaviour. ``key`` is the indicator code for cross-section and the
    VARIABLE for the screener, matching how each indexes ``indicator_param``.

    ``None`` is not a new convention: across every wrapper boundary in this SDK a
    ``None`` already means "do not send this field" — that is exactly what
    ``_request_body`` → ``_strip_none`` does for every optional kwarg. This is the
    same convention one level down, which is why it beats inventing a sentinel.

    ⚠️ **Known blind spot**: a misspelled PARAM KEY in a suppression marker is
    silently inert — ``{"tradDate": None}`` neither suppresses nor errors locally,
    and the injection happens as usual. Param keys are per-indicator (whatever
    ``parameterList`` declares), so there is no local whitelist to check against;
    a ``None`` never reaches the server, which would otherwise name a misspelled key
    in a 100003. (A misspelled INDICATOR CODE — the outer key — IS caught: see
    :func:`_assert_param_codes_bound`.)
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


def _normalize_param_dates(
    spec: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]] | None:
    """``indicator_param`` with every date-keyed value checked like ``date``.

    Param values travel nested inside ``indicatorParamList`` / ``indicatorList``, so
    ``_request_body``'s date guard never sees them — without this a year-last
    ``{"reportDate": "12-31-2025"}`` reached a server that reads it month-first (a
    different day for half the callers, answered with HTTP 200). Keyed on the KEY, like
    the CLI: any ``*Date`` parameter, whichever indicator it belongs to. A ``None``
    suppression marker is left alone — it never reaches the wire (TS v0.44.0 ⑧).
    """
    if not spec:
        return spec
    normalized: dict[str, dict[str, Any]] = {}
    for code, params in spec.items():
        if not isinstance(params, dict):
            normalized[code] = params
            continue
        fixed: dict[str, Any] = {}
        for key, value in params.items():
            if value is not None and isinstance(key, str) and _DATE_PARAM_SUFFIX.search(key):
                try:
                    value = _validate_date(str(value), key)
                except ValidationError as error:
                    raise ValidationError(f"indicator_param[{code!r}][{key!r}]: {error}") from None
            fixed[key] = value
        normalized[code] = fixed
    return normalized


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
    # separator, with nothing in the response saying which. Keep the NORMALIZED
    # value: validating and then injecting the original sent "2026/03/31" verbatim.
    date = _validate_date(date, "date")
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
    date = _validate_date(date, "date")
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
    """An all-empty matrix is not a known answer.

    Since 2026-08-07 a real coverage gap comes back as a null cell with its row and
    column intact, and an unrecognised code or parameter name as an error (100003,
    re-probed by the CLI 2026-09-25) — so an empty answer is neither (TS v0.43.0 ⑩)."""
    warnings.warn(
        "the indicator query returned no data at all. A missing value comes back as a "
        "null cell and an unrecognised code or parameter name as an error (100003), so an "
        "empty answer is neither. Cross-check the codes against "
        "gangtise.indicator.search(...) and gangtise.reference.securities_search(...); if "
        "they are right, report it with the call.",
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
    # An empty screen is a normal answer AND what a report-period indicator gives on
    # a date off the period end (all null, so nothing passes) or an indicator that
    # does not cover these securities (a wrong code or parameter name is a 100003
    # error now, not an empty screen). Keyed on "nothing matched" rather than the
    # strict canonical-empty shape — a response returning zero securities while
    # still echoing `indicatorList` is just as empty to the caller, and just as
    # ambiguous, but would slip past ``is_empty_matrix``.
    if not data.get("securityCodeList"):
        warnings.warn(
            "nothing matched the expression. That is a normal answer — but it is ALSO "
            "what a report-period indicator (is_* etc.) gives on a date that is not a "
            "period end (every value null, so nothing passes), or an indicator that does "
            "not cover these securities. Check the date (reportDate for report-period "
            "indicators) and the coverage (scopeList) in gangtise.indicator.search(...).",
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


def _probe_codes(indicators: Sequence[str]) -> list[str]:
    """Each distinct, non-empty indicator code once, in request order."""
    return list(dict.fromkeys(code for code in indicators if isinstance(code, str) and code))


def _is_trading_day_typed(result: Any, code: str) -> bool:
    """One indicator's verdict from its ``indicator.search`` answer.

    ``False`` covers every form of "not proven": the code missing from the hits, an
    empty ``parameterList`` (the static-attribute families report one, and so does
    ``cdr_conv_ratio``, which takes a date anyway), any ``reportDate`` / ``fiscalYear``
    key — ``div_cash_yld`` declares BOTH reportDate and tradeDate, so a check that
    merely looked for tradeDate would pick TD and lose every value.
    """
    data = _search_result(result)
    rows = data.get("list") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return False
    entry = next(
        (row for row in rows if isinstance(row, dict) and row.get("indicatorCode") == code), None
    )
    if entry is None:
        return False
    params = entry.get("parameterList")
    keys = (
        [
            p["paramKey"]
            for p in params
            if isinstance(p, dict) and isinstance(p.get("paramKey"), str)
        ]
        if isinstance(params, list)
        else []
    )
    if not keys or any(key in _PERIOD_DATE_KEYS for key in keys):
        return False
    return _TRADE_DATE_KEY in keys


def _probe_body(code: str) -> dict[str, Any]:
    return {"keyword": code, "limit": _PROBE_LIMIT}


def _note_calendar_choice() -> None:
    logger.info(
        "[gangtise] indicator.time_series: every requested indicator takes tradeDate, so the "
        "series is fetched on the trading-day calendar (calendarType=TD) instead of the "
        "server default ND — no all-null non-trading rows, and fewer cells against the "
        "30000 cap. Pass calendar_type='ND' to override."
    )


def _resolve_calendar_type(client: GangtiseClient, indicators: Sequence[str]) -> str | None:
    """The ``calendarType`` for a time series the caller left unset: ``"TD"`` when EVERY
    indicator is provably trading-day typed, otherwise ``None`` (send nothing and let the
    server apply its default ``ND``).

    The server default is deliberately the SAFE one: report-period indicators carry
    values on dates like 2024-03-31 and 2024-06-30, both Sundays, which a trading-day
    axis does not contain — ``TD`` there answers 200 with a full grid of ``null`` (CLI
    probe 2026-09-19: ``is_op_rev`` 2024-03-25..07-05 gives 72 all-null columns under
    ``TD``). But ``ND`` on a pure quote series is waste: a year is 366 columns against
    248 (``qte_close``), a third of them weekend nulls billed and counted against the
    30000-cell cap. Guessing ``ND`` wrong only wastes cells, guessing ``TD`` wrong
    silently empties the result — so an empty ``parameterList``, an unresolvable code
    or a failed probe all land on ``ND``: a search outage must not change the axis.
    """
    codes = _probe_codes(indicators)
    if not codes:
        return None

    def verdict(code: str) -> bool:
        try:
            return _is_trading_day_typed(
                client._call("indicator.search", body=_probe_body(code)), code
            )
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=min(_PROBE_CONCURRENCY, len(codes))) as pool:
        verdicts = list(pool.map(verdict, codes))
    return "TD" if all(verdicts) else None


async def _resolve_calendar_type_async(
    client: AsyncGangtiseClient, indicators: Sequence[str]
) -> str | None:
    """Async mirror of :func:`_resolve_calendar_type` (same verdicts, same concurrency cap)."""
    codes = _probe_codes(indicators)
    if not codes:
        return None
    semaphore = anyio.Semaphore(_PROBE_CONCURRENCY)
    verdicts = [False] * len(codes)

    async def run_one(index: int, code: str) -> None:
        async with semaphore:
            try:
                result = await client._call("indicator.search", body=_probe_body(code))
                verdicts[index] = _is_trading_day_typed(result, code)
            except Exception:
                verdicts[index] = False

    async with anyio.create_task_group() as tg:
        for index, code in enumerate(codes):
            tg.start_soon(run_one, index, code)
    return "TD" if all(verdicts) else None


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
        服务端会改参数名; 传错名报 100003 并点名是哪个指标的哪个参数, 按报错改即可。
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
        10 位 sectorId, 与证券代码混传取并集）——⚠️ 服务端会把板块展开成**全部成分股**, 实际
        证券数远大于传入的条数。currency 取值 DFT/CNY/HKD/USD/EUR/GBP/JPY/TWD/MOP/AUD
        （默认 DFT）; scale 取值 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）。根级 scale
        只作用于支持该参数的指标, 价格类与金额类可以混查; 精确到单个指标用 indicator_param。

        🔴 **单次 30000 单元格上限**: 证券数 × 指标数超过 30000 报 100006, 不返回部分结果、
        不截断; 按这个乘积拆批（拆证券或拆指标）后自己合并。

        date 作为每个指标各自的 tradeDate 下发（根级 date 已于 2026-08-01 废弃）。
        ⚠️ 报告期类指标（is_* 等）**拒收 tradeDate**（只给 date 报 100003）, 须用
        indicator_param={"is_xxx": {"reportDate": "2025-12-31"}}; 哪个指标吃哪个日期不能按
        code 前缀推断, 以 search 的 parameterList 为准。例: finc_roe_avg_avg（平均 ROE N 期
        均值）属报告期类, 要 {"finc_roe_avg_avg": {"periodNum": "4", "reportDate":
        "2025-12-31"}}。tradeDate 与 reportDate 都必填的（如 div_cash_yld）两个都用
        indicator_param 显式给——只给 reportDate 时 SDK 不再注入 date, 服务端报 100001。
        indicator_param 里键名以 Date 结尾的值（reportDate / tradeDate / sDate …）与 date
        同样校验: 年在前的三种写法统一成 YYYY-MM-DD, 年在后的本地拒绝。前复权参数名是
        **adjustType**（不是 adjustmentType）。

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

        🔴 **fiscalYear 漏传不报错**: parameterList 标必填的 fiscalYear 漏传时, 服务端按它
        自定的默认年度取数（不随 date 变）——该年度有数就返回它, 看着完全正常但未必是你要的
        那一年; 没有就是 null。预测类（frcst_*, 与 tradeDate 同时必填）与分红类
        （div_cash_yr / div_cash_paid_ratio）都受影响, 一律显式传 fiscalYear。

        报错与缺数: code 或参数名写错报 100003 并点名, 缺其余必填参数报 100001 并点名;
        无数据是保留行列的 null 单元格（不是空表, 也不报错）。

        key_by 取 name（默认, 列头用服务端给的指标显示名）或 code（列头就是你传进去的
        indicatorCode）。服务端按自己的顺序返回列, 位置索引不可靠; 批量按 code 回填用 code 模式。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        params = _normalize_param_dates(indicator_param)
        body = _request_body(
            {
                "indicatorCodeList": indicators,
                "universe": securities,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _with_query_date(params, indicators, date),
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

        每行一个日期。security 也接受板块 ID（仅单指标时; 服务端把它展开成全部成分股,
        此时列头按证券出）。currency / scale / indicator_param 同 cross_section（参数日期
        校验、fiscalYear 漏传不报错、100003 / 100001 / null 的含义都相同）; 时序的区间由
        start_date / end_date 统管, 不要再用 indicator_param 传 tradeDate。

        calendar_type 取值 ND=自然日 TD=交易日 WD=工作日, **服务端默认 ND**; TD 且跨市场时
        日期列是各市场交易日的并集。**不传时 SDK 自动选**: 先用免费的 indicator.search 读
        各指标的 parameterList（去重后每个指标码查一次, 并发 ≤ 5）——**全部**声明 tradeDate
        且**都不**声明 reportDate / fiscalYear 才发 TD（行情 / 日频估值序列, 省掉非交易日的
        null 行与单元格）; 任一指标声明 reportDate 或 fiscalYear、parameterList 为空、
        查不到该 code 或这次查询失败, 都不发（服务端按 ND）。报告期末常落在非交易日, TD 会
        让报告期类指标整行全 null 且不报错, 所以只往 ND 一边兜底。**显式传了就原样发送,
        不查询也不改。**

        🔴 **单次 30000 单元格上限**: 序列数 × 日期数（序列 = 单指标时的证券数, 或单证券
        时的指标数）超过 30000 报 100006, 不返回部分结果、不截断; 缩短区间或拆证券分批取。
        ND 的日期列约是 TD 的 1.5 倍, 同一查询在 ND 下更容易超限。

        key_by 取 name（默认）或 code（列头就是你传进去的 indicatorCode / securityCode;
        服务端按自己的顺序返回列, 位置索引不可靠）。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        params = _normalize_param_dates(indicator_param)
        # Build first: every local check has to fire before ANY request goes out —
        # including the free calendar probe below.
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
                "indicatorParamList": list(_param_groups(params).values()),
            }
        )
        # Then pick the date axis, and only when the caller left it unset: an explicit
        # value is an instruction, not a default to improve on.
        if calendar_type is None and _resolve_calendar_type(self._client, indicators) == "TD":
            body["calendarType"] = "TD"
            _note_calendar_choice()
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

        date 作为每个变量的 tradeDate 下发（已带 tradeDate / reportDate 的不覆盖）; 绝大多数
        指标必填 tradeDate, 漏传服务端报 100001, 因此它是必填的。报告期类指标同
        cross_section, 用 indicator_param 传 reportDate; indicator_param 里 *Date 键的值同样
        校验并统一成 YYYY-MM-DD。fiscalYear 漏传不报错（按服务端默认年度取数）, 同
        cross_section, 一律显式传。security 传板块 ID 时服务端展开成全部成分股。

        输出同 cross_section 的宽表（每行一只命中的证券）。空结果是正常答案, 但也可能是
        报告期类指标的日期不在报告期末（全为 null, 无一通过）或指标不覆盖这些证券——
        对照 search 的 parameterList 与 scopeList 核对日期与覆盖。

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
        params = _normalize_param_dates(indicator_param)
        bindings = _screener_indicator_list(indicator, params, expression, date)
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
        服务端会改参数名; 传错名报 100003 并点名是哪个指标的哪个参数, 按报错改即可。
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
        10 位 sectorId, 与证券代码混传取并集）——⚠️ 服务端会把板块展开成**全部成分股**, 实际
        证券数远大于传入的条数。currency 取值 DFT/CNY/HKD/USD/EUR/GBP/JPY/TWD/MOP/AUD
        （默认 DFT）; scale 取值 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）。根级 scale
        只作用于支持该参数的指标, 价格类与金额类可以混查; 精确到单个指标用 indicator_param。

        🔴 **单次 30000 单元格上限**: 证券数 × 指标数超过 30000 报 100006, 不返回部分结果、
        不截断; 按这个乘积拆批（拆证券或拆指标）后自己合并。

        date 作为每个指标各自的 tradeDate 下发（根级 date 已于 2026-08-01 废弃）。
        ⚠️ 报告期类指标（is_* 等）**拒收 tradeDate**（只给 date 报 100003）, 须用
        indicator_param={"is_xxx": {"reportDate": "2025-12-31"}}; 哪个指标吃哪个日期不能按
        code 前缀推断, 以 search 的 parameterList 为准。例: finc_roe_avg_avg（平均 ROE N 期
        均值）属报告期类, 要 {"finc_roe_avg_avg": {"periodNum": "4", "reportDate":
        "2025-12-31"}}。tradeDate 与 reportDate 都必填的（如 div_cash_yld）两个都用
        indicator_param 显式给——只给 reportDate 时 SDK 不再注入 date, 服务端报 100001。
        indicator_param 里键名以 Date 结尾的值（reportDate / tradeDate / sDate …）与 date
        同样校验: 年在前的三种写法统一成 YYYY-MM-DD, 年在后的本地拒绝。前复权参数名是
        **adjustType**（不是 adjustmentType）。

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

        🔴 **fiscalYear 漏传不报错**: parameterList 标必填的 fiscalYear 漏传时, 服务端按它
        自定的默认年度取数（不随 date 变）——该年度有数就返回它, 看着完全正常但未必是你要的
        那一年; 没有就是 null。预测类（frcst_*, 与 tradeDate 同时必填）与分红类
        （div_cash_yr / div_cash_paid_ratio）都受影响, 一律显式传 fiscalYear。

        报错与缺数: code 或参数名写错报 100003 并点名, 缺其余必填参数报 100001 并点名;
        无数据是保留行列的 null 单元格（不是空表, 也不报错）。

        key_by 取 name（默认, 列头用服务端给的指标显示名）或 code（列头就是你传进去的
        indicatorCode）。服务端按自己的顺序返回列, 位置索引不可靠; 批量按 code 回填用 code 模式。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        params = _normalize_param_dates(indicator_param)
        body = _request_body(
            {
                "indicatorCodeList": indicators,
                "universe": securities,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _with_query_date(params, indicators, date),
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

        每行一个日期。security 也接受板块 ID（仅单指标时; 服务端把它展开成全部成分股,
        此时列头按证券出）。currency / scale / indicator_param 同 cross_section（参数日期
        校验、fiscalYear 漏传不报错、100003 / 100001 / null 的含义都相同）; 时序的区间由
        start_date / end_date 统管, 不要再用 indicator_param 传 tradeDate。

        calendar_type 取值 ND=自然日 TD=交易日 WD=工作日, **服务端默认 ND**; TD 且跨市场时
        日期列是各市场交易日的并集。**不传时 SDK 自动选**: 先用免费的 indicator.search 读
        各指标的 parameterList（去重后每个指标码查一次, 并发 ≤ 5）——**全部**声明 tradeDate
        且**都不**声明 reportDate / fiscalYear 才发 TD（行情 / 日频估值序列, 省掉非交易日的
        null 行与单元格）; 任一指标声明 reportDate 或 fiscalYear、parameterList 为空、
        查不到该 code 或这次查询失败, 都不发（服务端按 ND）。报告期末常落在非交易日, TD 会
        让报告期类指标整行全 null 且不报错, 所以只往 ND 一边兜底。**显式传了就原样发送,
        不查询也不改。**

        🔴 **单次 30000 单元格上限**: 序列数 × 日期数（序列 = 单指标时的证券数, 或单证券
        时的指标数）超过 30000 报 100006, 不返回部分结果、不截断; 缩短区间或拆证券分批取。
        ND 的日期列约是 TD 的 1.5 倍, 同一查询在 ND 下更容易超限。

        key_by 取 name（默认）或 code（列头就是你传进去的 indicatorCode / securityCode;
        服务端按自己的顺序返回列, 位置索引不可靠）。
        """
        _check_key_by(key_by)
        indicators, securities = _require_scope(indicator, security)
        _assert_param_codes_bound(indicator_param, indicators)
        params = _normalize_param_dates(indicator_param)
        # Build first: every local check has to fire before ANY request goes out —
        # including the free calendar probe below.
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
                "indicatorParamList": list(_param_groups(params).values()),
            }
        )
        # Then pick the date axis, and only when the caller left it unset: an explicit
        # value is an instruction, not a default to improve on.
        if (
            calendar_type is None
            and await _resolve_calendar_type_async(self._client, indicators) == "TD"
        ):
            body["calendarType"] = "TD"
            _note_calendar_choice()
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

        date 作为每个变量的 tradeDate 下发（已带 tradeDate / reportDate 的不覆盖）; 绝大多数
        指标必填 tradeDate, 漏传服务端报 100001, 因此它是必填的。报告期类指标同
        cross_section, 用 indicator_param 传 reportDate; indicator_param 里 *Date 键的值同样
        校验并统一成 YYYY-MM-DD。fiscalYear 漏传不报错（按服务端默认年度取数）, 同
        cross_section, 一律显式传。security 传板块 ID 时服务端展开成全部成分股。

        输出同 cross_section 的宽表（每行一只命中的证券）。空结果是正常答案, 但也可能是
        报告期类指标的日期不在报告期末（全为 null, 无一通过）或指标不覆盖这些证券——
        对照 search 的 parameterList 与 scopeList 核对日期与覆盖。

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
        params = _normalize_param_dates(indicator_param)
        bindings = _screener_indicator_list(indicator, params, expression, date)
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
