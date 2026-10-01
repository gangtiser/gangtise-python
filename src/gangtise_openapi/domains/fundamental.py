# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import datetime as dt
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
    naming a column twice, repeats that value in every row while the echoed field list
    names it once; an unknown name drops its value (probed 2026-09-25, three samples
    each). One of each CANCELS OUT — ``tradeDate,value,percentileRank,foo`` came back
    with every value one column to the right and the widths equal, so the width guard
    passed it. With nothing that can add a value, an unknown name always leaves the
    rows short, which ``normalize_rows`` refuses. ``tradeDate`` alone is kept: dropping
    it would ask for every column, and the endpoint answers it with no rows.
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
        """Shared body builder for the eight statement endpoints.

        ⚠️ **Point-in-time alignment must use ``earliestAnncDate``** (首次公告日,
        added server-side 2026-08-14), not ``announcementDate``: some securities
        fill all four quarters of ``announcementDate`` with the ANNUAL report's
        publish date (五粮液 FY2025 returns 20260430 four times), while
        ``earliestAnncDate`` returns 20250426 / 20250828 / 20251031 / 20260430,
        matching the announcement list. After-hours disclosures count as the next
        day, so it is never EARLIER than the real disclosure — the safe direction.
        No column pinning here (``schema=None``), so both fields flow through as
        the server sends them.
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
        if raw:
            return result  # type: ignore[no-any-return]
        return _result_to_dataframe(result)

    # ---- 8 statement endpoints ----

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

        period 报告期支持单值或列表，如 "2025annual"、"2026q1"。
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

        period 单季报告期取值 q1/q2/q3/q4/latest，支持单值或列表。
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

        period 报告期支持单值或列表，如 "2025annual"、"2026q1"。
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

        period 报告期支持单值或列表，如 "2025annual"、"2026q1"。
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

        period 单季报告期取值 q1/q2/q3/q4/latest，支持单值或列表。
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
        period 取值 interim=中报 / annual=年报，支持单值或列表。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "breakdown": breakdown,
                "periodList": _as_list(period, "period"),
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
        upper1Std / lower1Std）：只传 tradeDate、只传不存在的名字（含 securityCode）时
        接口返回 0 行、不报错（SDK 发 UserWarning 说明原因）；数值列与不存在的名字混传时
        字段数对不上，抛 ValidationError、不返回错位数据。tradeDate 总在第一列返回，不用写进
        field——写了 SDK 会在发请求前去掉，同一字段写两次也只发一次（只传 tradeDate 一项时
        照常发送）。不确定字段名就别传 field。

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
        """Shared body builder for the eight statement endpoints.

        ⚠️ **Point-in-time alignment must use ``earliestAnncDate``** (首次公告日,
        added server-side 2026-08-14), not ``announcementDate``: some securities
        fill all four quarters of ``announcementDate`` with the ANNUAL report's
        publish date (五粮液 FY2025 returns 20260430 four times), while
        ``earliestAnncDate`` returns 20250426 / 20250828 / 20251031 / 20260430,
        matching the announcement list. After-hours disclosures count as the next
        day, so it is never EARLIER than the real disclosure — the safe direction.
        No column pinning here (``schema=None``), so both fields flow through as
        the server sends them.
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

        period 报告期支持单值或列表，如 "2025annual"、"2026q1"。
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

        period 单季报告期取值 q1/q2/q3/q4/latest，支持单值或列表。
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

        period 报告期支持单值或列表，如 "2025annual"、"2026q1"。
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

        period 报告期支持单值或列表，如 "2025annual"、"2026q1"。
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

        period 单季报告期取值 q1/q2/q3/q4/latest，支持单值或列表。
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
        period 取值 interim=中报 / annual=年报，支持单值或列表。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "breakdown": breakdown,
                "periodList": _as_list(period, "period"),
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
        upper1Std / lower1Std）：只传 tradeDate、只传不存在的名字（含 securityCode）时
        接口返回 0 行、不报错（SDK 发 UserWarning 说明原因）；数值列与不存在的名字混传时
        字段数对不上，抛 ValidationError、不返回错位数据。tradeDate 总在第一列返回，不用写进
        field——写了 SDK 会在发请求前去掉，同一字段写两次也只发一次（只传 tradeDate 一项时
        照常发送）。不确定字段名就别传 field。

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
