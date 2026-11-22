# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import calendar
import datetime as dt
import re
import warnings
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import (
    _BEIJING,
    FilterValue,
    _as_list,
    _extract_rows,
    _refuse_empty,
    _request_body,
    _result_to_dataframe,
    _validate_date,
)


def _flatten_earning_forecast(result: Any, *, latest: bool) -> list[dict[str, Any]]:
    """Flatten the nested earning-forecast payload into a flat row list.

    The endpoint returns
    ``{securityCode, securityName, updateList: [{date, fieldList: [{...}]}]}``;
    this produces one row per (update date x forecast year), prefixed with
    ``securityCode`` / ``securityName`` / ``date``. With ``latest=True`` only the
    most recent update date is kept.
    """
    if not isinstance(result, dict):
        return []
    security_code = result.get("securityCode")
    security_name = result.get("securityName")
    updates = result.get("updateList")
    if not isinstance(updates, list):
        return []
    valid = [u for u in updates if isinstance(u, dict)]
    if latest and valid:
        # ISO date strings sort lexically; newest = max.
        valid = [max(valid, key=lambda u: u.get("date") or "")]
    rows: list[dict[str, Any]] = []
    for upd in valid:
        forecasts = upd.get("fieldList")
        if not isinstance(forecasts, list):
            continue
        for forecast in forecasts:
            if not isinstance(forecast, dict):
                continue
            rows.append(
                {
                    "securityCode": security_code,
                    "securityName": security_name,
                    "date": upd.get("date"),
                    **forecast,
                }
            )
    return rows


def _earning_forecast_dates(
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str]:
    # "Today" is BEIJING's day, whatever the machine's zone: the data is published on
    # Beijing dates, and a UTC host (CI, a cloud server) is still on yesterday until
    # 08:00 Beijing, so the day's new rows went missing (TS v0.43.0 ⑪). The registry's
    # credit estimate (``_endpoints._estimate_earning_forecast_rows``) uses the same
    # defaults, so a wrapper call and a direct ``_call`` are priced alike.
    end = end_date or dt.datetime.now(_BEIJING).date().isoformat()
    if start_date is not None:
        return start_date, end
    # end_date is consumed locally to anchor the default start_date, ahead of
    # ``_request_body`` — validate here so a bad layout raises ValidationError with
    # the explanation rather than a bare ValueError from ``fromisoformat``. Keep the
    # NORMALIZED value: ``fromisoformat`` cannot read ``2026/09/30``.
    end = _validate_date(end, "endDate")
    anchor = dt.date.fromisoformat(end)
    return (anchor - dt.timedelta(days=365)).isoformat(), end


# ---- valuation-analysis helpers (TS v0.39.0 ⑥, v0.41.1 ②-④, v0.42.0 ⑤) ----

# The endpoint's own default, sent explicitly so the sent limit and the truncation
# check compare the same number by construction. Omitted, the server applies it
# anyway and keeps the MOST RECENT rows: a ten-year start_date silently came back as
# its last 2000 days (probed by the CLI 2026-09-24: 茅台 peTtm 2016-01-01..2026-09-24 →
# 2000 rows from 2021-04-04; limit=5000 → all 3920). One row per CALENDAR day.
_VALUATION_DEFAULT_LIMIT = 2000
# Every column but ``tradeDate``. A fieldList with none of them — ``tradeDate`` alone,
# or only names the endpoint does not know — is answered with an EMPTY list, not an
# error (probed 2026-09-25, three samples each).
_VALUATION_VALUE_COLUMNS = (
    "value",
    "percentileRank",
    "average",
    "median",
    "upper1Std",
    "lower1Std",
)
# The two columns ``skip_null`` judges.
_VALUATION_FILTER_COLUMNS = ("value", "percentileRank")


def _valuation_limit(limit: int | None) -> int:
    """``limit`` as sent: the API default when omitted, else a positive integer — a
    ``limit`` below 1 would make the ``rows >= limit`` truncation check fire on every
    answer (TS parses it with ``{integer: true, min: 1}``)."""
    if limit is None:
        return _VALUATION_DEFAULT_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValidationError(f"limit must be a positive integer (got {limit!r})")
    return limit


def _valuation_fields_to_send(fields: list[Any]) -> list[Any]:
    """The fieldList actually sent: each name once, and no ``tradeDate`` unless it is
    all that was asked for.

    The endpoint always answers with ``tradeDate`` first. Asking for it anyway, or
    naming a column twice, once repeated that value in every row while the echoed field
    list named it once (probed 2026-09-25); since 2026-10-14 names and values line up
    and an unknown name is refused with 100005. Kept because the request means the same
    without the repeats. ``tradeDate`` alone is kept: dropping it would ask for every
    column, and the endpoint answers it with no rows.
    """
    unique = list(dict.fromkeys(fields))
    values = [f for f in unique if f != "tradeDate"]
    return values or unique


_VALUATION_INDICATORS = ("peTtm", "pbMrq", "peg", "psTtm", "pcfTtm", "em")


def _valuation_request(
    *,
    security_code: str,
    indicator: str,
    start_date: str | None,
    end_date: str | None,
    limit: int | None,
    field: FilterValue | None,
    skip_null: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Request body plus the columns fetched only for ``skip_null`` (dropped again
    before output, so ``field`` still decides which columns the caller gets).

    ``skip_null`` judges ``value`` and ``percentileRank``; a ``field`` that names
    neither never brought them back, the filter read them as null and dropped EVERY
    row — an empty frame that reads as "no valuation history" (TS v0.39.0 ⑥)."""
    if indicator not in _VALUATION_INDICATORS:
        # The CLI refuses other values locally (commander ``.choices``); the server's
        # answer to an unknown indicator was never pinned, so refuse before sending.
        raise ValidationError(
            f"invalid indicator: {indicator!r} is not one of {'/'.join(_VALUATION_INDICATORS)}"
        )
    _refuse_empty(field, "field")
    requested = _as_list(field, "field") or None
    filter_fields = (
        [f for f in _VALUATION_FILTER_COLUMNS if f not in requested]
        if skip_null and requested
        else []
    )
    field_list = _valuation_fields_to_send([*requested, *filter_fields]) if requested else None
    body = _request_body(
        {
            "securityCode": security_code,
            "indicator": indicator,
            "startDate": start_date,
            "endDate": end_date,
            "limit": _valuation_limit(limit),
            "fieldList": field_list,
        }
    )
    return body, filter_fields


def _valuation_first_row(result: Any) -> tuple[int, str | None]:
    """Row count and the first row's ``tradeDate``, read straight off the columnar or
    object layout — without normalizing, so ``raw=True`` never raises on a layout the
    DataFrame path would refuse."""
    rows = result.get("list") if isinstance(result, dict) else result
    if not isinstance(rows, list) or not rows:
        return 0, None
    first = rows[0]
    value: Any = None
    if isinstance(first, dict):
        value = first.get("tradeDate")
    elif isinstance(first, list) and isinstance(result, dict):
        fields = result.get("fieldList")
        if isinstance(fields, list) and "tradeDate" in fields:
            index = fields.index("tradeDate")
            value = first[index] if index < len(first) else None
    return len(rows), value if isinstance(value, str) else None


def _check_valuation_result(result: Any, body: dict[str, Any], *, stacklevel: int = 3) -> None:
    """The three completeness signals of one valuation-analysis answer.

    The series is ascending with one row per calendar day, so its first date settles
    what a full page cannot: a first row ON ``start_date`` means nothing was cut (a
    range of exactly ``limit`` days), and a first row AFTER it on a page that did not
    fill means the server started late on its own — a later listing, or a range that
    reaches past the account's history window, which this endpoint clips without an
    error (probed 2026-09-24: 2015-01-01..2016-03-31 starts at the 2016-01-01 bound).
    """
    field_list = body.get("fieldList")
    limit: int = body["limit"]
    start = body.get("startDate")
    count, first_date = _valuation_first_row(result)
    if (
        field_list is not None
        and not any(f in _VALUATION_VALUE_COLUMNS for f in field_list)
        and count == 0
    ):
        warnings.warn(
            "fundamental.valuation_analysis: no rows came back, and field names no value "
            f"column ({', '.join(str(f) for f in field_list)}). This endpoint answers such "
            "a request with an empty list rather than an error, so it says nothing about "
            f"whether data exists: add one of {' / '.join(_VALUATION_VALUE_COLUMNS)}, or "
            "drop field.",
            stacklevel=stacklevel,
        )
    already_partial = isinstance(result, dict) and result.get("partial") is True
    if not (start and first_date == start) and not already_partial and count >= limit:
        if isinstance(result, dict):
            result["partial"] = True
        warnings.warn(
            f"fundamental.valuation_analysis returned {count} rows = the {limit}-row "
            "limit; results are likely truncated (this endpoint has no pagination). The "
            "API keeps the most recent rows, so it is the START of the range that is "
            "missing. The series has one row per calendar day (weekends included): raise "
            "limit to at least the number of days in the range (366 per year covers it, "
            "e.g. limit=1830 for five years), or move start_date later.",
            stacklevel=stacklevel,
        )
    partial = isinstance(result, dict) and result.get("partial") is True
    if start and first_date and first_date > start and not partial:
        warnings.warn(
            f"fundamental.valuation_analysis: the series starts at {first_date}, later "
            f"than start_date {start}. Either the security listed later, or the range "
            "reaches past your account's history window — this endpoint returns what "
            "lies inside the window without an error.",
            stacklevel=stacklevel,
        )


def _valuation_rows(rows: list[Any], *, skip_null: bool, filter_fields: list[str]) -> list[Any]:
    """DataFrame rows, with ``skip_null`` applied and the filter-only columns removed.
    Works on the normalized rows, so the bare-array and ``{…, list}`` layouts are
    filtered alike (TS v0.42.0 ⑤)."""
    if not skip_null:
        return rows
    kept = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("value") is not None
        and r.get("percentileRank") is not None
    ]
    if not filter_fields:
        return kept
    return [{k: v for k, v in r.items() if k not in filter_fields} for r in kept]


# ---- US statements: one fiscal year per request (TS v0.52.2) ----

# The US statements answer a request spanning more than one fiscal year with one fiscal
# year per period type and report type, not necessarily the latest, without an error
# (probed 2026-11-22: AAPL.O 2015-2025 annual → one report; 2024 + 2025 annual → one of
# the two; 2023-09-30..2024-09-28 annual → one; MSFT.O / NVDA.O and all three statements
# alike — which year stays differs between statements and over time). A single fiscal
# year comes back whole.
_US_STATEMENTS = frozenset(
    {
        "fundamental.income-statement-us",
        "fundamental.balance-sheet-us",
        "fundamental.cash-flow-us",
    }
)
_EIGHT_DIGITS = re.compile(r"\d{8}", re.ASCII)
_ISO_PREFIX = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


def _iso_day(value: Any) -> dt.date | None:
    """``yyyyMMdd`` or ``yyyy-MM-dd…`` as a date; None for anything that is not a real
    day (``00000000`` included) or lies near the calendar's edges, which the ±371-day
    arithmetic of :func:`_another_end` would cross."""
    text = "" if value is None else str(value)
    if _EIGHT_DIGITS.fullmatch(text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    elif _ISO_PREFIX.match(text):
        text = text[:10]
    else:
        return None
    try:
        day = dt.date.fromisoformat(text)
    except ValueError:
        return None
    return day if 1000 <= day.year <= 9000 else None


def _same_month_end(day: dt.date, years: int) -> dt.date:
    year = day.year + years
    return dt.date(year, day.month, calendar.monthrange(year, day.month)[1])


def _another_end(ends: list[dt.date], start: dt.date, last: dt.date) -> str | None:
    """How surely ``start..last`` holds another end of a period type it returned one end
    of: ``"surely"``, ``"maybe"`` or None.

    A 52/53-week year counts whole weeks, so all its ends fall on one weekday, and some
    of them on a month-end too (AAPL.O: Q1 2022-12-31 and FY 2023-09-30, both
    Saturdays); the four calendar quarter-ends of a year never all share a weekday. So
    ends that are all month-ends on two weekdays or more mean calendar quarters, and the
    other end is the same month-end a year away. Anything else — one weekday, one end
    alone, an end off a month-end — is read as whole weeks, the reading that errs toward
    a note: the other end lies 364 to 371 days away (AAPL.O annual: 2022-09-24,
    2023-09-30, 2024-09-28), so a range past 371 days holds it, one reaching only 364 may.
    """
    calendar_quarters = len({d.weekday() for d in ends}) > 1 and all(
        (d + dt.timedelta(days=1)).day == 1 for d in ends
    )
    maybe = False
    for end in ends:
        if calendar_quarters:
            if start <= _same_month_end(end, -1) or _same_month_end(end, 1) <= last:
                return "surely"
            continue
        if start <= end - dt.timedelta(days=371) or end + dt.timedelta(days=371) <= last:
            return "surely"
        if start <= end - dt.timedelta(days=364) or end + dt.timedelta(days=364) <= last:
            maybe = True
    return "maybe" if maybe else None


def _us_span(rows: list[Any], body: dict[str, Any], today: dt.date) -> str | None:
    """Whether a US-statement answer shows the one-fiscal-year cut: ``"surely"`` /
    ``"maybe"`` when no period type × report type covers two fiscal years and the
    request spans more than one — two or more ``fiscalYear``, none (the whole history),
    or dates (which override ``fiscalYear``) holding another end of a period type that
    came back. Once every year comes back a type covers two and this goes quiet.
    ``latest`` alone asks for the newest report (two rows on AAPL.O, two different
    labels), not a span."""
    requested = body.get("period") or []
    if requested and all(p == "latest" for p in requested):
        return None
    records = [r for r in rows if isinstance(r, dict)]
    if not records:
        return None
    covered: dict[tuple[str, str], set[str]] = {}
    for r in records:
        year = r.get("fiscalYear")
        key = (repr(r.get("period")), repr(r.get("reportType")))
        covered.setdefault(key, set()).add(repr(r.get("endDate") if year is None else year))
    if any(len(years) > 1 for years in covered.values()):
        return None
    start, end = _iso_day(body.get("startDate")), _iso_day(body.get("endDate"))
    if start is None and end is None:
        return "surely" if len(body.get("fiscalYear") or []) != 1 else None
    ends = [d for d in (_iso_day(r.get("endDate")) for r in records) if d is not None]
    if start is None:
        return "surely" if ends else None
    return _another_end(ends, start, end or today)


def _note_us_one_fiscal_year(
    endpoint_key: str, result: Any, body: dict[str, Any], *, stacklevel: int = 4
) -> None:
    """UserWarning when :func:`_us_span` reads the cut; the rows come back unchanged and
    unflagged. A layout the DataFrame path refuses is skipped here: ``raw=True`` hands
    it back as it came, and the DataFrame path raises right after."""
    try:
        rows = _extract_rows(result)
    except ValidationError:
        return
    span = _us_span(rows, body, dt.datetime.now(_BEIJING).date())
    method = endpoint_key.replace("-", "_")
    if span == "surely":
        warnings.warn(
            f"{method}: the request spans more than one fiscal year, yet each period type "
            "and report type came back for one fiscal year only. The US statements answer "
            "such a request with one fiscal year per period type and report type (not "
            "necessarily the latest), without an error — query one fiscal_year at a time.",
            stacklevel=stacklevel,
        )
    elif span == "maybe":
        warnings.warn(
            f"{method}: the date range may hold two ends of the same period type (52/53-week "
            "fiscal years end 364 to 371 days apart), yet each period type and report type "
            "came back for one fiscal year only. If it does, the US statements kept one of "
            "them, without an error — query one fiscal_year at a time to be sure.",
            stacklevel=stacklevel,
        )


class Fundamental:
    """`gangtise.fundamental.*` — financial statements + valuation + holders + forecasts."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    # ---- Internal helpers ----

    def _statement(
        self,
        endpoint_key: str,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """Shared body builder for the eleven statement endpoints.

        ⚠️ **The values are the latest version, restatements included** — also under
        ``consolidated``. ``announcementDate`` is the date of the announcement those
        values come from; ``earliestAnncDate`` (首次公告日, added server-side
        2026-08-14) is when the period was first disclosed. 五粮液 restated 2025
        Q1–Q3 on 2026-04-30: 2025Q1 ``consolidated`` returns the restated 44.16 亿
        归母净利 (as ``consolidatedRestated`` does; first disclosed 148.60 亿) with
        ``announcementDate`` 20260430 and ``earliestAnncDate`` 20250426. So
        ``earliestAnncDate`` tells whether a period was public on a date, but pairing
        it with these values backfills numbers that only became known later
        (look-ahead); a value is knowable from its ``announcementDate``, and the
        first-disclosed numbers of a restated period are not in this response. No
        column pinning here (``schema=None``), so both fields flow through as the
        server sends them.
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "fiscalYear": _as_list(fiscal_year, "fiscal_year"),
                "period": _as_list(period, "period"),
                "reportType": _as_list(report_type, "report_type"),
                "fieldList": _as_list(field, "field"),
            }
        )
        result = self._client._call(endpoint_key, body=body)
        if endpoint_key in _US_STATEMENTS:
            _note_us_one_fiscal_year(endpoint_key, result, body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- 11 statement endpoints ----

    def income_statement(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股利润表累计口径（fundamental.income-statement）。

        period 报告期取值 q1/interim/q3/annual/latest，支持单值或列表；年份放 fiscal_year
        （"2025annual" 这种写法服务端报 100005）。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，不是最新一期——只要最新一期就传
        period="latest"。fiscal_year 或 start_date/end_date 单传返回该范围内各期，period 单传返回
        所有该类报告（如 "annual" 即历年年报）；年份与日期都给时按日期取。latest 不受年份 / 日期
        约束（返回全部报告里的最新一期），与其他取值同传时另加上最新一期，按年份 / 日期取时别带它。
        多期结果不按报告期排序，按 endDate 排好再用。
        """
        return self._statement(
            "fundamental.income-statement",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def income_statement_quarterly(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股利润表单季口径（fundamental.income-statement-quarterly）。

        period 单季报告期取值 q1/interim/q3/annual/latest，支持单值或列表；interim、annual 分别是
        截至 6/30、12/31 的那一季（q2 / q4 服务端报 100005）。
        🔴 period、fiscal_year、日期的规则同累计表：都不传时返回全部历史报告期，只要最新一期就传
        period="latest"；年份或日期单传返回该范围内各期，都给时按日期取；latest 不受年份 / 日期
        约束，与其他取值同传时另加上最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        ⚠️ 返回行的 period 是报告名，不说明是单季值：除一季报外都是该季度单季值——中报、三季报两行
        与累计表同名（「2025年中报」「2025年三季报」），年报行写作「2025年报」（累计表是
        「2025年年报」）。别按 period 标签与累计表合并或对位。
        """
        return self._statement(
            "fundamental.income-statement-quarterly",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def balance_sheet(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股资产负债表（fundamental.balance-sheet）。

        period 报告期取值 q1/interim/q3/annual/latest，支持单值或列表；年份放 fiscal_year
        （"2025annual" 这种写法服务端报 100005）。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，不是最新一期——只要最新一期就传
        period="latest"。fiscal_year 或 start_date/end_date 单传返回该范围内各期，period 单传返回
        所有该类报告（如 "annual" 即历年年报）；年份与日期都给时按日期取。latest 不受年份 / 日期
        约束（返回全部报告里的最新一期），与其他取值同传时另加上最新一期，按年份 / 日期取时别带它。
        多期结果不按报告期排序，按 endDate 排好再用。
        """
        return self._statement(
            "fundamental.balance-sheet",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def cash_flow(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股现金流量表累计口径（fundamental.cash-flow）。

        period 报告期取值 q1/interim/q3/annual/latest，支持单值或列表；年份放 fiscal_year
        （"2025annual" 这种写法服务端报 100005）。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，不是最新一期——只要最新一期就传
        period="latest"。fiscal_year 或 start_date/end_date 单传返回该范围内各期，period 单传返回
        所有该类报告（如 "annual" 即历年年报）；年份与日期都给时按日期取。latest 不受年份 / 日期
        约束（返回全部报告里的最新一期），与其他取值同传时另加上最新一期，按年份 / 日期取时别带它。
        多期结果不按报告期排序，按 endDate 排好再用。
        """
        return self._statement(
            "fundamental.cash-flow",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def cash_flow_quarterly(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股现金流量表单季口径（fundamental.cash-flow-quarterly）。

        period 单季报告期取值 q1/interim/q3/annual/latest，支持单值或列表；interim、annual 分别是
        截至 6/30、12/31 的那一季（q2 / q4 服务端报 100005）。
        🔴 period、fiscal_year、日期的规则同累计表：都不传时返回全部历史报告期，只要最新一期就传
        period="latest"；年份或日期单传返回该范围内各期，都给时按日期取；latest 不受年份 / 日期
        约束，与其他取值同传时另加上最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        ⚠️ 返回行的 period 是报告名，不说明是单季值：除一季报外都是该季度单季值——中报、三季报两行
        与累计表同名（「2025年中报」「2025年三季报」），年报行写作「2025年报」（累计表是
        「2025年年报」）。别按 period 标签与累计表合并或对位。
        """
        return self._statement(
            "fundamental.cash-flow-quarterly",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def income_statement_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股利润表，中国会计准则（fundamental.income-statement-hk）。

        period 港股报告期取值 q1/h1/q3/h2/nsd/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，只要最新一期就传 period="latest"。
        fiscal_year 或日期单传返回该范围内各期，period 单传返回所有该类报告；年份与日期都给时按日期
        取。latest 单传时不受年份 / 日期约束（返回全部报告里的最新一期），与其他取值同传时不另加
        最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        🔴 非 12 月财年的公司，fiscal_year 与返回的 fiscalYear 都按期末（endDate）所在的自然年算，
        period 标签按公司财年：如 3 月财年的公司，fiscal_year=2026 返回截至 2026-03-31 的「2026年度
        报告」与 2026 年 4 月起的「2027一季报」「2027半年报告」，fiscal_year=2027 取不到这两期。按
        公司财年取数改用日期区间，或按 period 标签筛。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return self._statement(
            "fundamental.income-statement-hk",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def balance_sheet_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股资产负债表，中国会计准则（fundamental.balance-sheet-hk）。

        period 港股报告期取值 q1/h1/q3/h2/nsd/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，只要最新一期就传 period="latest"。
        fiscal_year 或日期单传返回该范围内各期，period 单传返回所有该类报告；年份与日期都给时按日期
        取。latest 单传时不受年份 / 日期约束（返回全部报告里的最新一期），与其他取值同传时不另加
        最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        🔴 非 12 月财年的公司，fiscal_year 与返回的 fiscalYear 都按期末（endDate）所在的自然年算，
        period 标签按公司财年：如 3 月财年的公司，fiscal_year=2026 返回截至 2026-03-31 的「2026年度
        报告」与 2026 年 4 月起的「2027一季报」「2027半年报告」，fiscal_year=2027 取不到这两期。按
        公司财年取数改用日期区间，或按 period 标签筛。
        """
        return self._statement(
            "fundamental.balance-sheet-hk",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def cash_flow_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股现金流量表，中国会计准则（fundamental.cash-flow-hk）。

        period 港股报告期取值 q1/h1/q3/h2/nsd/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，只要最新一期就传 period="latest"。
        fiscal_year 或日期单传返回该范围内各期，period 单传返回所有该类报告；年份与日期都给时按日期
        取。latest 单传时不受年份 / 日期约束（返回全部报告里的最新一期），与其他取值同传时不另加
        最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        🔴 非 12 月财年的公司，fiscal_year 与返回的 fiscalYear 都按期末（endDate）所在的自然年算，
        period 标签按公司财年：如 3 月财年的公司，fiscal_year=2026 返回截至 2026-03-31 的「2026年度
        报告」与 2026 年 4 月起的「2027一季报」「2027半年报告」，fiscal_year=2027 取不到这两期。按
        公司财年取数改用日期区间，或按 period 标签筛。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return self._statement(
            "fundamental.cash-flow-hk",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def income_statement_us(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股利润表（fundamental.income-statement-us）。

        period 美股报告期取值 q1/h1/q3/nsd/annual/latest，支持单值或列表。
        🔴 一次只取一个财年：请求跨多个财年（fiscal_year 给多个、日期区间覆盖同一报告期的两个期末、
        或年份与日期都不给——含 period="annual" 单传）时，每种报告期与 report_type 的组合只返回
        其中一年，不一定是最新那年、不报错。多年数据按 fiscal_year 逐年查；结果呈这种形态时发
        UserWarning（按日期区间查、只能估算区间里是否有两个期末时措辞为「可能」：52 / 53 周财年的
        两个期末相隔 364～371 天）。财年按公司财年计（如苹果的财年在 9 月底结束）。
        单个财年内：fiscal_year 或日期单传返回该范围内各期，都给时按日期取；只要最新一期就传
        period="latest"，它不受年份 / 日期约束，与其他取值同传时不另加最新一期。多期结果不按报告期
        排序，按 endDate 排好再用。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return self._statement(
            "fundamental.income-statement-us",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def balance_sheet_us(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股资产负债表（fundamental.balance-sheet-us）。

        period 美股报告期取值 q1/h1/q3/nsd/annual/latest，支持单值或列表。
        🔴 一次只取一个财年：请求跨多个财年（fiscal_year 给多个、日期区间覆盖同一报告期的两个期末、
        或年份与日期都不给——含 period="annual" 单传）时，每种报告期与 report_type 的组合只返回
        其中一年，不一定是最新那年、不报错。多年数据按 fiscal_year 逐年查；结果呈这种形态时发
        UserWarning（按日期区间查、只能估算区间里是否有两个期末时措辞为「可能」：52 / 53 周财年的
        两个期末相隔 364～371 天）。财年按公司财年计（如苹果的财年在 9 月底结束）。
        单个财年内：fiscal_year 或日期单传返回该范围内各期，都给时按日期取；只要最新一期就传
        period="latest"，它不受年份 / 日期约束，与其他取值同传时不另加最新一期。多期结果不按报告期
        排序，按 endDate 排好再用。
        """
        return self._statement(
            "fundamental.balance-sheet-us",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    def cash_flow_us(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股现金流量表（fundamental.cash-flow-us）。

        period 美股报告期取值 q1/h1/q3/nsd/annual/latest，支持单值或列表。
        🔴 一次只取一个财年：请求跨多个财年（fiscal_year 给多个、日期区间覆盖同一报告期的两个期末、
        或年份与日期都不给——含 period="annual" 单传）时，每种报告期与 report_type 的组合只返回
        其中一年，不一定是最新那年、不报错。多年数据按 fiscal_year 逐年查；结果呈这种形态时发
        UserWarning（按日期区间查、只能估算区间里是否有两个期末时措辞为「可能」：52 / 53 周财年的
        两个期末相隔 364～371 天）。财年按公司财年计（如苹果的财年在 9 月底结束）。
        单个财年内：fiscal_year 或日期单传返回该范围内各期，都给时按日期取；只要最新一期就传
        period="latest"，它不受年份 / 日期约束，与其他取值同传时不另加最新一期。多期结果不按报告期
        排序，按 endDate 排好再用。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return self._statement(
            "fundamental.cash-flow-us",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    # ---- main-business ----

    def main_business(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        breakdown: str = "product",
        period: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询主营业务构成（fundamental.main-business）。

        breakdown 取值 product=产品 / industry=行业 / region=地区；
        period 取值 interim=中报 / annual=年报，支持单值或列表。field 写了不存在的字段名时
        整条报 100005 并点名，不确定字段名就别传。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "breakdown": breakdown,
                # Not CLI's ``periodList``: the server ignores it and answers every period;
                # it filters by ``period`` (probed 2026-11-14).
                "period": _as_list(period, "period"),
                "fieldList": _as_list(field, "field"),
            }
        )
        result = self._client._call("fundamental.main-business", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- valuation-analysis (with client-side skip_null filter) ----

    def valuation_analysis(
        self,
        *,
        security_code: str,
        indicator: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        skip_null: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询估值分析与历史分位（fundamental.valuation-analysis），仅 A 股。

        indicator 取值 peTtm=滚动PE / pbMrq=PB / peg=PEG / psTtm=滚动PS / pcfTtm=滚动PCF /
        em=企业倍数。返回字段只有 7 个：tradeDate / value / percentileRank / average /
        median / upper1Std / lower1Std（**没有 securityCode**）。

        🔴 **序列按自然日逐日一行（含周末）**，行数超过 limit 时接口**保留最近的行、丢掉
        区间开头**。limit 省略时按接口默认 2000 显式发送；行数撞满 limit 即在 raw 结果上
        标 partial 并发 UserWarning（首行恰好就是 start_date 说明一行没丢，不标）。取长
        区间把 limit 设到不小于区间天数：取 N 年就设 limit ≥ 366 × N（如 5 年 1830）。

        🔴 start_date 早于账号回溯下界时，接口从下界起返回、不报错（整段都在界外才报
        110003）。首行晚于 start_date 时发 UserWarning——可能该证券上市较晚，也可能撞了
        权限窗口，看首行日期判断。

        field 里**至少要有一个数值列**（value / percentileRank / average / median /
        upper1Std / lower1Std）：只传 tradeDate 时接口返回 0 行、不报错（SDK 发 UserWarning
        说明原因）；不存在的名字（含 securityCode）整条报 100005 并点名。tradeDate 总在第一
        列返回，不用写进 field——写了 SDK 会在发请求前去掉，同一字段写两次也只发一次（只传
        tradeDate 一项时照常发送）。不确定字段名就别传 field。

        skip_null=True 时丢弃 value 或 percentileRank 为空的行（最新交易日可能未入库）；
        field 没点名这两列时 SDK 会补取、过滤后再删掉，输出列仍由 field 决定。raw=True 时
        skip_null 不生效（原样返回服务端 data）。
        """
        body, filter_fields = _valuation_request(
            security_code=security_code,
            indicator=indicator,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            skip_null=skip_null and not raw,
        )
        result = self._client._call("fundamental.valuation-analysis", body=body)
        if raw:
            _check_valuation_result(result, body)
            return result  # type: ignore[no-any-return]
        # Normalize FIRST: a field list the widths do not line up with is refused here,
        # before any note could read as if the rows were fine.
        rows = _extract_rows(result)
        _check_valuation_result(result, body)
        return to_dataframe(
            _valuation_rows(rows, skip_null=skip_null, filter_fields=filter_fields), schema=None
        )

    # ---- top-holders ----

    def top_holders(
        self,
        *,
        security_code: str,
        holder_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询前十大股东 / 前十大流通股东（fundamental.top-holders）。

        holder_type 取值 top10=前十大股东 / top10Float=前十大流通股东；
        period 取值 q1/interim/q3/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部报告期，只要最新一期就传 period="latest"；
        fiscal_year 或日期单传返回该范围内各期，年份与日期都给时按日期取。latest 不受年份 / 日期
        约束，与其他取值同传时另加上最新一期。多期结果按 reportPeriod 分组、期内按 rank 排，每期
        行数不固定（早年有的期只有 6～8 名），别按十行切分。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "holderType": holder_type,
                "startDate": start_date,
                "endDate": end_date,
                "fiscalYear": _as_list(fiscal_year, "fiscal_year"),
                "period": _as_list(period, "period"),
            }
        )
        result = self._client._call("fundamental.top-holders", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- earning-forecast ----

    def earning_forecast(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        consensus: FilterValue | None = None,
        latest: bool = True,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询盈利预测一致预期（fundamental.earning-forecast），仅 A 股。

        start_date/end_date 缺省时取截至**北京时间今天**、向前一年（与机器所在时区无关）；
        可查范围前溯 1 年（各档相同，个别账号更长，以实际返回为准）。
        latest=True（默认）仅保留最新一次更新。consensus 取值 netIncome/netIncomeYoy/eps/
        pe/bps/pb/peg/roe/ps，支持单值或列表。

        💰 **0.5 积分/条，行数随日期区间增长**（每个交易日一组、每组 3 年预测），长区间一次
        可达数千积分，所以超时 / 5xx **不自动重试**；长区间按年分段拉。发请求前按区间估算
        （工作日数 × 3 条 × 0.5 积分，节假日按工作日算，是上限），**超过 1000 积分（约两年半
        的区间）抛 ValidationError、不发请求**，报错写明估算值；确认要取就传 confirm=True，
        或缩短区间。

        ⚠️ **roe 的单位是百分比**（35.6 就是 35.6%），做过 ×100 换算的脚本要撤掉。
        """
        # Default window: the year before endDate, endDate defaulting to Beijing's today.
        start_date, end_date = _earning_forecast_dates(start_date, end_date)
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "consensusList": _as_list(consensus, "consensus"),
            }
        )
        # Priced before it is sent (``_client._refuse_unconfirmed``): billed per row with
        # the rows growing with the range; ``confirm`` lets a costly range through.
        result = self._client._call("fundamental.earning-forecast", body=body, confirm=confirm)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_flatten_earning_forecast(result, latest=latest), schema=None)


class AsyncFundamental:
    """Async mirror of `Fundamental`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def _statement(
        self,
        endpoint_key: str,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """Shared body builder for the eleven statement endpoints.

        ⚠️ **The values are the latest version, restatements included** — also under
        ``consolidated``. ``announcementDate`` is the date of the announcement those
        values come from; ``earliestAnncDate`` (首次公告日, added server-side
        2026-08-14) is when the period was first disclosed. 五粮液 restated 2025
        Q1–Q3 on 2026-04-30: 2025Q1 ``consolidated`` returns the restated 44.16 亿
        归母净利 (as ``consolidatedRestated`` does; first disclosed 148.60 亿) with
        ``announcementDate`` 20260430 and ``earliestAnncDate`` 20250426. So
        ``earliestAnncDate`` tells whether a period was public on a date, but pairing
        it with these values backfills numbers that only became known later
        (look-ahead); a value is knowable from its ``announcementDate``, and the
        first-disclosed numbers of a restated period are not in this response. No
        column pinning here (``schema=None``), so both fields flow through as the
        server sends them.
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "fiscalYear": _as_list(fiscal_year, "fiscal_year"),
                "period": _as_list(period, "period"),
                "reportType": _as_list(report_type, "report_type"),
                "fieldList": _as_list(field, "field"),
            }
        )
        result = await self._client._call(endpoint_key, body=body)
        if endpoint_key in _US_STATEMENTS:
            _note_us_one_fiscal_year(endpoint_key, result, body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def income_statement(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股利润表累计口径（fundamental.income-statement）。

        period 报告期取值 q1/interim/q3/annual/latest，支持单值或列表；年份放 fiscal_year
        （"2025annual" 这种写法服务端报 100005）。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，不是最新一期——只要最新一期就传
        period="latest"。fiscal_year 或 start_date/end_date 单传返回该范围内各期，period 单传返回
        所有该类报告（如 "annual" 即历年年报）；年份与日期都给时按日期取。latest 不受年份 / 日期
        约束（返回全部报告里的最新一期），与其他取值同传时另加上最新一期，按年份 / 日期取时别带它。
        多期结果不按报告期排序，按 endDate 排好再用。
        """
        return await self._statement(
            "fundamental.income-statement",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def income_statement_quarterly(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股利润表单季口径（fundamental.income-statement-quarterly）。

        period 单季报告期取值 q1/interim/q3/annual/latest，支持单值或列表；interim、annual 分别是
        截至 6/30、12/31 的那一季（q2 / q4 服务端报 100005）。
        🔴 period、fiscal_year、日期的规则同累计表：都不传时返回全部历史报告期，只要最新一期就传
        period="latest"；年份或日期单传返回该范围内各期，都给时按日期取；latest 不受年份 / 日期
        约束，与其他取值同传时另加上最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        ⚠️ 返回行的 period 是报告名，不说明是单季值：除一季报外都是该季度单季值——中报、三季报两行
        与累计表同名（「2025年中报」「2025年三季报」），年报行写作「2025年报」（累计表是
        「2025年年报」）。别按 period 标签与累计表合并或对位。
        """
        return await self._statement(
            "fundamental.income-statement-quarterly",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def balance_sheet(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股资产负债表（fundamental.balance-sheet）。

        period 报告期取值 q1/interim/q3/annual/latest，支持单值或列表；年份放 fiscal_year
        （"2025annual" 这种写法服务端报 100005）。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，不是最新一期——只要最新一期就传
        period="latest"。fiscal_year 或 start_date/end_date 单传返回该范围内各期，period 单传返回
        所有该类报告（如 "annual" 即历年年报）；年份与日期都给时按日期取。latest 不受年份 / 日期
        约束（返回全部报告里的最新一期），与其他取值同传时另加上最新一期，按年份 / 日期取时别带它。
        多期结果不按报告期排序，按 endDate 排好再用。
        """
        return await self._statement(
            "fundamental.balance-sheet",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def cash_flow(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股现金流量表累计口径（fundamental.cash-flow）。

        period 报告期取值 q1/interim/q3/annual/latest，支持单值或列表；年份放 fiscal_year
        （"2025annual" 这种写法服务端报 100005）。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，不是最新一期——只要最新一期就传
        period="latest"。fiscal_year 或 start_date/end_date 单传返回该范围内各期，period 单传返回
        所有该类报告（如 "annual" 即历年年报）；年份与日期都给时按日期取。latest 不受年份 / 日期
        约束（返回全部报告里的最新一期），与其他取值同传时另加上最新一期，按年份 / 日期取时别带它。
        多期结果不按报告期排序，按 endDate 排好再用。
        """
        return await self._statement(
            "fundamental.cash-flow",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def cash_flow_quarterly(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股现金流量表单季口径（fundamental.cash-flow-quarterly）。

        period 单季报告期取值 q1/interim/q3/annual/latest，支持单值或列表；interim、annual 分别是
        截至 6/30、12/31 的那一季（q2 / q4 服务端报 100005）。
        🔴 period、fiscal_year、日期的规则同累计表：都不传时返回全部历史报告期，只要最新一期就传
        period="latest"；年份或日期单传返回该范围内各期，都给时按日期取；latest 不受年份 / 日期
        约束，与其他取值同传时另加上最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        ⚠️ 返回行的 period 是报告名，不说明是单季值：除一季报外都是该季度单季值——中报、三季报两行
        与累计表同名（「2025年中报」「2025年三季报」），年报行写作「2025年报」（累计表是
        「2025年年报」）。别按 period 标签与累计表合并或对位。
        """
        return await self._statement(
            "fundamental.cash-flow-quarterly",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def income_statement_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股利润表，中国会计准则（fundamental.income-statement-hk）。

        period 港股报告期取值 q1/h1/q3/h2/nsd/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，只要最新一期就传 period="latest"。
        fiscal_year 或日期单传返回该范围内各期，period 单传返回所有该类报告；年份与日期都给时按日期
        取。latest 单传时不受年份 / 日期约束（返回全部报告里的最新一期），与其他取值同传时不另加
        最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        🔴 非 12 月财年的公司，fiscal_year 与返回的 fiscalYear 都按期末（endDate）所在的自然年算，
        period 标签按公司财年：如 3 月财年的公司，fiscal_year=2026 返回截至 2026-03-31 的「2026年度
        报告」与 2026 年 4 月起的「2027一季报」「2027半年报告」，fiscal_year=2027 取不到这两期。按
        公司财年取数改用日期区间，或按 period 标签筛。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return await self._statement(
            "fundamental.income-statement-hk",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def balance_sheet_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股资产负债表，中国会计准则（fundamental.balance-sheet-hk）。

        period 港股报告期取值 q1/h1/q3/h2/nsd/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，只要最新一期就传 period="latest"。
        fiscal_year 或日期单传返回该范围内各期，period 单传返回所有该类报告；年份与日期都给时按日期
        取。latest 单传时不受年份 / 日期约束（返回全部报告里的最新一期），与其他取值同传时不另加
        最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        🔴 非 12 月财年的公司，fiscal_year 与返回的 fiscalYear 都按期末（endDate）所在的自然年算，
        period 标签按公司财年：如 3 月财年的公司，fiscal_year=2026 返回截至 2026-03-31 的「2026年度
        报告」与 2026 年 4 月起的「2027一季报」「2027半年报告」，fiscal_year=2027 取不到这两期。按
        公司财年取数改用日期区间，或按 period 标签筛。
        """
        return await self._statement(
            "fundamental.balance-sheet-hk",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def cash_flow_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股现金流量表，中国会计准则（fundamental.cash-flow-hk）。

        period 港股报告期取值 q1/h1/q3/h2/nsd/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部历史报告期，只要最新一期就传 period="latest"。
        fiscal_year 或日期单传返回该范围内各期，period 单传返回所有该类报告；年份与日期都给时按日期
        取。latest 单传时不受年份 / 日期约束（返回全部报告里的最新一期），与其他取值同传时不另加
        最新一期。多期结果不按报告期排序，按 endDate 排好再用。
        🔴 非 12 月财年的公司，fiscal_year 与返回的 fiscalYear 都按期末（endDate）所在的自然年算，
        period 标签按公司财年：如 3 月财年的公司，fiscal_year=2026 返回截至 2026-03-31 的「2026年度
        报告」与 2026 年 4 月起的「2027一季报」「2027半年报告」，fiscal_year=2027 取不到这两期。按
        公司财年取数改用日期区间，或按 period 标签筛。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return await self._statement(
            "fundamental.cash-flow-hk",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def income_statement_us(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股利润表（fundamental.income-statement-us）。

        period 美股报告期取值 q1/h1/q3/nsd/annual/latest，支持单值或列表。
        🔴 一次只取一个财年：请求跨多个财年（fiscal_year 给多个、日期区间覆盖同一报告期的两个期末、
        或年份与日期都不给——含 period="annual" 单传）时，每种报告期与 report_type 的组合只返回
        其中一年，不一定是最新那年、不报错。多年数据按 fiscal_year 逐年查；结果呈这种形态时发
        UserWarning（按日期区间查、只能估算区间里是否有两个期末时措辞为「可能」：52 / 53 周财年的
        两个期末相隔 364～371 天）。财年按公司财年计（如苹果的财年在 9 月底结束）。
        单个财年内：fiscal_year 或日期单传返回该范围内各期，都给时按日期取；只要最新一期就传
        period="latest"，它不受年份 / 日期约束，与其他取值同传时不另加最新一期。多期结果不按报告期
        排序，按 endDate 排好再用。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return await self._statement(
            "fundamental.income-statement-us",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def balance_sheet_us(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股资产负债表（fundamental.balance-sheet-us）。

        period 美股报告期取值 q1/h1/q3/nsd/annual/latest，支持单值或列表。
        🔴 一次只取一个财年：请求跨多个财年（fiscal_year 给多个、日期区间覆盖同一报告期的两个期末、
        或年份与日期都不给——含 period="annual" 单传）时，每种报告期与 report_type 的组合只返回
        其中一年，不一定是最新那年、不报错。多年数据按 fiscal_year 逐年查；结果呈这种形态时发
        UserWarning（按日期区间查、只能估算区间里是否有两个期末时措辞为「可能」：52 / 53 周财年的
        两个期末相隔 364～371 天）。财年按公司财年计（如苹果的财年在 9 月底结束）。
        单个财年内：fiscal_year 或日期单传返回该范围内各期，都给时按日期取；只要最新一期就传
        period="latest"，它不受年份 / 日期约束，与其他取值同传时不另加最新一期。多期结果不按报告期
        排序，按 endDate 排好再用。
        """
        return await self._statement(
            "fundamental.balance-sheet-us",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def cash_flow_us(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        report_type: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股现金流量表（fundamental.cash-flow-us）。

        period 美股报告期取值 q1/h1/q3/nsd/annual/latest，支持单值或列表。
        🔴 一次只取一个财年：请求跨多个财年（fiscal_year 给多个、日期区间覆盖同一报告期的两个期末、
        或年份与日期都不给——含 period="annual" 单传）时，每种报告期与 report_type 的组合只返回
        其中一年，不一定是最新那年、不报错。多年数据按 fiscal_year 逐年查；结果呈这种形态时发
        UserWarning（按日期区间查、只能估算区间里是否有两个期末时措辞为「可能」：52 / 53 周财年的
        两个期末相隔 364～371 天）。财年按公司财年计（如苹果的财年在 9 月底结束）。
        单个财年内：fiscal_year 或日期单传返回该范围内各期，都给时按日期取；只要最新一期就传
        period="latest"，它不受年份 / 日期约束，与其他取值同传时不另加最新一期。多期结果不按报告期
        排序，按 endDate 排好再用。
        ⚠️ period 只给 latest 时（带不带年份 / 日期都一样）可能回两行：同一 endDate，一行是报告期
        累计，另一行 period 为空串、是最近一个季度的单季值（startDate 为该季度首日）。要累计数取
        period 非空那行；两行先后不固定，别直接取第一行。
        """
        return await self._statement(
            "fundamental.cash-flow-us",
            security_code=security_code,
            start_date=start_date,
            end_date=end_date,
            fiscal_year=fiscal_year,
            period=period,
            report_type=report_type,
            field=field,
            raw=raw,
        )

    async def main_business(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        breakdown: str = "product",
        period: FilterValue | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询主营业务构成（fundamental.main-business）。

        breakdown 取值 product=产品 / industry=行业 / region=地区；
        period 取值 interim=中报 / annual=年报，支持单值或列表。field 写了不存在的字段名时
        整条报 100005 并点名，不确定字段名就别传。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "breakdown": breakdown,
                # Not CLI's ``periodList``: the server ignores it and answers every period;
                # it filters by ``period`` (probed 2026-11-14).
                "period": _as_list(period, "period"),
                "fieldList": _as_list(field, "field"),
            }
        )
        result = await self._client._call("fundamental.main-business", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def valuation_analysis(
        self,
        *,
        security_code: str,
        indicator: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        skip_null: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询估值分析与历史分位（fundamental.valuation-analysis），仅 A 股。

        indicator 取值 peTtm=滚动PE / pbMrq=PB / peg=PEG / psTtm=滚动PS / pcfTtm=滚动PCF /
        em=企业倍数。返回字段只有 7 个：tradeDate / value / percentileRank / average /
        median / upper1Std / lower1Std（**没有 securityCode**）。

        🔴 **序列按自然日逐日一行（含周末）**，行数超过 limit 时接口**保留最近的行、丢掉
        区间开头**。limit 省略时按接口默认 2000 显式发送；行数撞满 limit 即在 raw 结果上
        标 partial 并发 UserWarning（首行恰好就是 start_date 说明一行没丢，不标）。取长
        区间把 limit 设到不小于区间天数：取 N 年就设 limit ≥ 366 × N（如 5 年 1830）。

        🔴 start_date 早于账号回溯下界时，接口从下界起返回、不报错（整段都在界外才报
        110003）。首行晚于 start_date 时发 UserWarning——可能该证券上市较晚，也可能撞了
        权限窗口，看首行日期判断。

        field 里**至少要有一个数值列**（value / percentileRank / average / median /
        upper1Std / lower1Std）：只传 tradeDate 时接口返回 0 行、不报错（SDK 发 UserWarning
        说明原因）；不存在的名字（含 securityCode）整条报 100005 并点名。tradeDate 总在第一
        列返回，不用写进 field——写了 SDK 会在发请求前去掉，同一字段写两次也只发一次（只传
        tradeDate 一项时照常发送）。不确定字段名就别传 field。

        skip_null=True 时丢弃 value 或 percentileRank 为空的行（最新交易日可能未入库）；
        field 没点名这两列时 SDK 会补取、过滤后再删掉，输出列仍由 field 决定。raw=True 时
        skip_null 不生效（原样返回服务端 data）。
        """
        body, filter_fields = _valuation_request(
            security_code=security_code,
            indicator=indicator,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            skip_null=skip_null and not raw,
        )
        result = await self._client._call("fundamental.valuation-analysis", body=body)
        if raw:
            _check_valuation_result(result, body)
            return result  # type: ignore[no-any-return]
        # Normalize FIRST: a field list the widths do not line up with is refused here,
        # before any note could read as if the rows were fine.
        rows = _extract_rows(result)
        _check_valuation_result(result, body)
        return to_dataframe(
            _valuation_rows(rows, skip_null=skip_null, filter_fields=filter_fields), schema=None
        )

    async def top_holders(
        self,
        *,
        security_code: str,
        holder_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: FilterValue | None = None,
        period: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询前十大股东 / 前十大流通股东（fundamental.top-holders）。

        holder_type 取值 top10=前十大股东 / top10Float=前十大流通股东；
        period 取值 q1/interim/q3/annual/latest，支持单值或列表。
        🔴 period、fiscal_year、日期都不传时返回全部报告期，只要最新一期就传 period="latest"；
        fiscal_year 或日期单传返回该范围内各期，年份与日期都给时按日期取。latest 不受年份 / 日期
        约束，与其他取值同传时另加上最新一期。多期结果按 reportPeriod 分组、期内按 rank 排，每期
        行数不固定（早年有的期只有 6～8 名），别按十行切分。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "holderType": holder_type,
                "startDate": start_date,
                "endDate": end_date,
                "fiscalYear": _as_list(fiscal_year, "fiscal_year"),
                "period": _as_list(period, "period"),
            }
        )
        result = await self._client._call("fundamental.top-holders", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    async def earning_forecast(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        consensus: FilterValue | None = None,
        latest: bool = True,
        confirm: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询盈利预测一致预期（fundamental.earning-forecast），仅 A 股。

        start_date/end_date 缺省时取截至**北京时间今天**、向前一年（与机器所在时区无关）；
        可查范围前溯 1 年（各档相同，个别账号更长，以实际返回为准）。
        latest=True（默认）仅保留最新一次更新。consensus 取值 netIncome/netIncomeYoy/eps/
        pe/bps/pb/peg/roe/ps，支持单值或列表。

        💰 **0.5 积分/条，行数随日期区间增长**（每个交易日一组、每组 3 年预测），长区间一次
        可达数千积分，所以超时 / 5xx **不自动重试**；长区间按年分段拉。发请求前按区间估算
        （工作日数 × 3 条 × 0.5 积分，节假日按工作日算，是上限），**超过 1000 积分（约两年半
        的区间）抛 ValidationError、不发请求**，报错写明估算值；确认要取就传 confirm=True，
        或缩短区间。

        ⚠️ **roe 的单位是百分比**（35.6 就是 35.6%），做过 ×100 换算的脚本要撤掉。
        """
        # Default window: the year before endDate, endDate defaulting to Beijing's today.
        start_date, end_date = _earning_forecast_dates(start_date, end_date)
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "consensusList": _as_list(consensus, "consensus"),
            }
        )
        # Priced before it is sent (``_client._refuse_unconfirmed``): billed per row with
        # the rows growing with the range; ``confirm`` lets a costly range through.
        result = await self._client._call(
            "fundamental.earning-forecast", body=body, confirm=confirm
        )
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_flatten_earning_forecast(result, latest=latest), schema=None)
