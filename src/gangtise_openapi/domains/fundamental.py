from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe

_VALUATION_ANALYSIS_SCHEMA = [
    "securityCode",
    "indicator",
    "date",
    "value",
    "percentileRank",
    "average",
    "median",
    "upper1Std",
    "lower1Std",
]


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


def _extract_rows(result: Any) -> list[Any]:
    if isinstance(result, dict):
        rows = result.get("list", [])
        return rows if isinstance(rows, list) else []
    if isinstance(result, list):
        return result
    return []


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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- 8 statement endpoints ----

    def income_statement(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
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

    # ---- main-business ----

    def main_business(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        breakdown: str = "product",
        period: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- valuation-analysis (with client-side skip_null filter) ----

    def valuation_analysis(
        self,
        *,
        security_code: str,
        indicator: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        field: Any = None,
        skip_null: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(rows, schema=_VALUATION_ANALYSIS_SCHEMA)

    # ---- top-holders ----

    def top_holders(
        self,
        *,
        security_code: str,
        holder_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(_extract_rows(result), schema=None)

    # ---- earning-forecast ----

    def earning_forecast(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        consensus: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(_extract_rows(result), schema=None)


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
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(_extract_rows(result), schema=None)

    async def income_statement(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.income-statement",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def income_statement_quarterly(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.income-statement-quarterly",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def balance_sheet(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.balance-sheet",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def cash_flow(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.cash-flow",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def cash_flow_quarterly(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.cash-flow-quarterly",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def income_statement_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.income-statement-hk",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def balance_sheet_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.balance-sheet-hk",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def cash_flow_hk(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        report_type: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return await self._statement(
            "fundamental.cash-flow-hk",
            security_code=security_code, start_date=start_date, end_date=end_date,
            fiscal_year=fiscal_year, period=period, report_type=report_type,
            field=field, raw=raw,
        )

    async def main_business(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        breakdown: str = "product",
        period: Any = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(_extract_rows(result), schema=None)

    async def valuation_analysis(
        self,
        *,
        security_code: str,
        indicator: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        field: Any = None,
        skip_null: bool = False,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
            {
                "securityCode": security_code,
                "indicator": indicator,
                "startDate": start_date,
                "endDate": end_date,
                "limit": limit,
                "fieldList": _as_list(field),
            }
        )
        result = await self._client._call(
            "fundamental.valuation-analysis", body=body
        )
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
        return to_dataframe(rows, schema=_VALUATION_ANALYSIS_SCHEMA)

    async def top_holders(
        self,
        *,
        security_code: str,
        holder_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
        fiscal_year: Any = None,
        period: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
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
        return to_dataframe(_extract_rows(result), schema=None)

    async def earning_forecast(
        self,
        *,
        security_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        consensus: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none(
            {
                "securityCode": security_code,
                "startDate": start_date,
                "endDate": end_date,
                "consensusList": _as_list(consensus),
            }
        )
        result = await self._client._call(
            "fundamental.earning-forecast", body=body
        )
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(result), schema=None)
