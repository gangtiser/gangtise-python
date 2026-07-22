# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _extract_rows,
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
    end = end_date or dt.date.today().isoformat()
    if start_date is not None:
        return start_date, end
    # end_date is consumed locally to anchor the default start_date, ahead of
    # ``_request_body`` — validate here so a bad layout raises ValidationError with
    # the explanation rather than a bare ValueError from ``fromisoformat``.
    _validate_date(end, "endDate")
    anchor = dt.date.fromisoformat(end)
    return (anchor - dt.timedelta(days=365)).isoformat(), end


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
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "fiscalYear": _as_list(fiscal_year),
                "period": _as_list(period),
                "reportType": _as_list(report_type),
                "fieldList": _as_list(field),
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
                "periodList": _as_list(period),
                "fieldList": _as_list(field),
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
        """查询估值分析与历史分位（fundamental.valuation-analysis）。

        indicator 取值 peTtm/pbMrq/peg/psTtm/pcfTtm/em；
        skip_null=True 时过滤 value/percentileRank 为空的行。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "indicator": indicator,
                "startDate": start_date,
                "endDate": end_date,
                "limit": limit,
                "fieldList": _as_list(field),
            }
        )
        result = self._client._call("fundamental.valuation-analysis", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        if skip_null:
            rows = [
                r
                for r in rows
                if isinstance(r, dict)
                and r.get("value") is not None
                and r.get("percentileRank") is not None
            ]
        return to_dataframe(rows, schema=None)

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
                "fiscalYear": _as_list(fiscal_year),
                "period": _as_list(period),
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询盈利预测一致预期（fundamental.earning-forecast）。

        start_date/end_date 缺省时自动取最近一年；latest=True（默认）仅保留最新一次更新。
        consensus 取值 netIncome/netIncomeYoy/eps/pe/bps/pb/peg/roe/ps，支持单值或列表。
        """
        # TS HEAD parity: default the window to the year before endDate.
        start_date, end_date = _earning_forecast_dates(start_date, end_date)
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "consensusList": _as_list(consensus),
            }
        )
        result = self._client._call("fundamental.earning-forecast", body=body)
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
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "fiscalYear": _as_list(fiscal_year),
                "period": _as_list(period),
                "reportType": _as_list(report_type),
                "fieldList": _as_list(field),
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
                "periodList": _as_list(period),
                "fieldList": _as_list(field),
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
        """查询估值分析与历史分位（fundamental.valuation-analysis）。

        indicator 取值 peTtm/pbMrq/peg/psTtm/pcfTtm/em；
        skip_null=True 时过滤 value/percentileRank 为空的行。
        """
        body = _request_body(
            {
                "securityCode": security_code,
                "indicator": indicator,
                "startDate": start_date,
                "endDate": end_date,
                "limit": limit,
                "fieldList": _as_list(field),
            }
        )
        result = await self._client._call("fundamental.valuation-analysis", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows = _extract_rows(result)
        if skip_null:
            rows = [
                r
                for r in rows
                if isinstance(r, dict)
                and r.get("value") is not None
                and r.get("percentileRank") is not None
            ]
        return to_dataframe(rows, schema=None)

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
                "fiscalYear": _as_list(fiscal_year),
                "period": _as_list(period),
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
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询盈利预测一致预期（fundamental.earning-forecast）。

        start_date/end_date 缺省时自动取最近一年；latest=True（默认）仅保留最新一次更新。
        consensus 取值 netIncome/netIncomeYoy/eps/pe/bps/pb/peg/roe/ps，支持单值或列表。
        """
        # TS HEAD parity: default the window to the year before endDate.
        start_date, end_date = _earning_forecast_dates(start_date, end_date)
        body = _request_body(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "consensusList": _as_list(consensus),
            }
        )
        result = await self._client._call("fundamental.earning-forecast", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_flatten_earning_forecast(result, latest=latest), schema=None)
