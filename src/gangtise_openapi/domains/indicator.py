# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese text
# that intentionally uses fullwidth punctuation.)
from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi._transport import unwrap_envelope
from gangtise_openapi.domains._common import _as_list, _extract_rows, _strip_none

# The EDE cross-section / time-series endpoints return a `values` matrix plus
# parallel code/name/date lists rather than ready-made rows. The helpers below
# flatten that matrix into the wide row shape to_dataframe expects. Ported 1:1
# from gangtise-openapi-cli/src/core/indicatorMatrix.ts; the live field names
# (securityCodeList / securityNameList / indicatorCodeList / indicatorNameList /
# values) match the real EDE response, not the published doc.


def _unwrap_indicator_data(raw: Any) -> Any:
    """Peel the inner ``{code, status, data}`` envelope the EDE endpoints add.

    The shared client strips the outer envelope but leaves an inner one around
    the real payload (list for search, matrix for cross-section/time-series). A
    failure code carried only by that inner envelope must surface as an ApiError
    instead of rendering its null payload as success. Delegates to the shared
    ``unwrap_envelope`` so envelope handling stays single-sourced.
    """
    return unwrap_envelope(raw)


def _as_str_list(value: Any) -> list[str] | None:
    return [str(item) for item in value] if isinstance(value, list) else None


def _row_of(values: Any, index: int) -> list[Any] | None:
    if isinstance(values, list) and index < len(values):
        row = values[index]
        if isinstance(row, list):
            return row
    return None


def _fill_row(headers: list[str], values: Any, idx: int) -> dict[str, Any]:
    """Pull column ``idx`` from each series row of the ``values`` matrix into a
    ``{header: cell}`` mapping; missing or ragged cells become None. Shared by the
    cross-section and time-series flatteners."""
    cells: dict[str, Any] = {}
    for i, header in enumerate(headers):
        series = _row_of(values, i)
        cells[header] = series[idx] if series and idx < len(series) else None
    return cells


def _build_headers(names: list[str] | None, codes: list[str] | None, count: int) -> list[str]:
    """One column header per series; prefer the name, append the code on a
    duplicate so a column is never silently overwritten. An empty/missing name
    falls through to the code (Python ``or`` vs TS ``??``) — a blank column header
    is useless, so this minor divergence from the CLI is intentional."""
    used: set[str] = set()
    headers: list[str] = []
    for i in range(count):
        base = str(
            (names[i] if names and i < len(names) else None)
            or (codes[i] if codes and i < len(codes) else None)
            or f"col{i}"
        )
        header = base
        attempt = 1
        while header in used:
            suffix = codes[i] if codes and i < len(codes) else i
            header = f"{base} ({suffix})" if attempt == 1 else f"{base} ({suffix})_{attempt}"
            attempt += 1
        used.add(header)
        headers.append(header)
    return headers


def _flatten_cross_section(data: Any) -> Any:
    """Cross-section: one row per security, one column per indicator. The live
    ``values`` is a 2D ``[numIndicators][numSecurities]`` indicator-major matrix,
    so indicator ``i`` on security ``j`` is ``values[i][j]``."""
    if not isinstance(data, dict):
        return data
    security_code = _as_str_list(data.get("securityCodeList"))
    indicators = _as_str_list(data.get("indicatorCodeList"))
    values = data.get("values")
    if not isinstance(values, list) or security_code is None or indicators is None:
        return data

    security_name = _as_str_list(data.get("securityNameList"))
    headers = _build_headers(
        _as_str_list(data.get("indicatorNameList")), indicators, len(indicators)
    )

    rows: list[dict[str, Any]] = []
    for j, code in enumerate(security_code):
        row: dict[str, Any] = {
            "date": data.get("date"),
            "security": code,
            "name": security_name[j] if security_name and j < len(security_name) else None,
        }
        row.update(_fill_row(headers, values, j))
        rows.append(row)
    return {"list": rows, "total": len(rows)}


def _flatten_time_series(data: Any) -> Any:
    """Time-series: one row per date. Columns are the indicators (single-security
    case) or the securities (single-indicator case) — exactly one dimension
    varies. ``values`` is a 2D ``[series][date]`` matrix."""
    if not isinstance(data, dict):
        return data
    dates = _as_str_list(data.get("dates"))
    security_code = _as_str_list(data.get("securityCodeList"))
    indicators = _as_str_list(data.get("indicatorCodeList"))
    values = data.get("values")
    if not isinstance(values, list) or dates is None or security_code is None or indicators is None:
        return data

    series_are_indicators = len(security_code) <= 1
    headers = (
        _build_headers(_as_str_list(data.get("indicatorNameList")), indicators, len(indicators))
        if series_are_indicators
        else _build_headers(
            _as_str_list(data.get("securityNameList")), security_code, len(security_code)
        )
    )

    rows: list[dict[str, Any]] = []
    for k, date in enumerate(dates):
        row: dict[str, Any] = {"date": date}
        row.update(_fill_row(headers, values, k))
        rows.append(row)
    return {"list": rows, "total": len(rows)}


def _indicator_param_list(spec: dict[str, dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Build the nested ``indicatorParamList`` the EDE endpoints expect from a
    ``{indicator_code: {param_key: param_value}}`` mapping."""
    if not spec:
        return None
    return [
        {
            "indicatorCode": code,
            "parameters": [{"paramKey": k, "paramValue": str(v)} for k, v in params.items()],
        }
        for code, params in spec.items()
    ]


class Indicator:
    """`gangtise.indicator.*` — 证券级数据指标 (EDE): 搜索指标码、截面、时序。"""

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
        limit 默认 50、上限 100。返回 indicatorCode 供 cross_section / time_series 使用。
        """
        body = {"keyword": keyword, "limit": limit}
        result = self._client._call("indicator.search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(_unwrap_indicator_data(result)), schema=None)

    def cross_section(
        self,
        *,
        date: str,
        indicator: Any = None,
        security: Any = None,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取截面数据（indicator.cross-section）: 多指标 × 多证券, 单日期。

        每行一只证券, 每列一个指标。currency 取值 DFT/CNY/HKD/USD/...（默认 DFT）;
        scale 取值 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）;
        indicator_param 形如 {"qte_close": {"adjustmentType": "2"}} 设置前复权等单指标参数。
        """
        body = _strip_none(
            {
                "indicatorCodeList": _as_list(indicator),
                "securityCodeList": _as_list(security),
                "date": date,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _indicator_param_list(indicator_param),
            }
        )
        result = self._client._call("indicator.cross-section", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        flattened = _flatten_cross_section(_unwrap_indicator_data(result))
        return to_dataframe(_extract_rows(flattened), schema=None)

    def time_series(
        self,
        *,
        start_date: str,
        end_date: str,
        indicator: Any = None,
        security: Any = None,
        calendar_type: str | None = None,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取时序数据（indicator.time-series）: 多指标 × 单证券 或 单指标 × 多证券。

        每行一个日期。calendar_type 取值 ND=自然日 TD=交易日 WD=工作日（默认 TD）;
        currency / scale / indicator_param 同 cross_section。
        """
        body = _strip_none(
            {
                "indicatorCodeList": _as_list(indicator),
                "securityCodeList": _as_list(security),
                "startDate": start_date,
                "endDate": end_date,
                "calendarType": calendar_type,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _indicator_param_list(indicator_param),
            }
        )
        result = self._client._call("indicator.time-series", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        flattened = _flatten_time_series(_unwrap_indicator_data(result))
        return to_dataframe(_extract_rows(flattened), schema=None)


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
        limit 默认 50、上限 100。返回 indicatorCode 供 cross_section / time_series 使用。
        """
        body = {"keyword": keyword, "limit": limit}
        result = await self._client._call("indicator.search", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_extract_rows(_unwrap_indicator_data(result)), schema=None)

    async def cross_section(
        self,
        *,
        date: str,
        indicator: Any = None,
        security: Any = None,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取截面数据（indicator.cross-section）: 多指标 × 多证券, 单日期。

        每行一只证券, 每列一个指标。currency 取值 DFT/CNY/HKD/USD/...（默认 DFT）;
        scale 取值 0=个 3=千 4=万 6=百万 8=亿 9=十亿（默认 0）;
        indicator_param 形如 {"qte_close": {"adjustmentType": "2"}} 设置前复权等单指标参数。
        """
        body = _strip_none(
            {
                "indicatorCodeList": _as_list(indicator),
                "securityCodeList": _as_list(security),
                "date": date,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _indicator_param_list(indicator_param),
            }
        )
        result = await self._client._call("indicator.cross-section", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        flattened = _flatten_cross_section(_unwrap_indicator_data(result))
        return to_dataframe(_extract_rows(flattened), schema=None)

    async def time_series(
        self,
        *,
        start_date: str,
        end_date: str,
        indicator: Any = None,
        security: Any = None,
        calendar_type: str | None = None,
        currency: str | None = None,
        scale: str | None = None,
        indicator_param: dict[str, dict[str, Any]] | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """获取时序数据（indicator.time-series）: 多指标 × 单证券 或 单指标 × 多证券。

        每行一个日期。calendar_type 取值 ND=自然日 TD=交易日 WD=工作日（默认 TD）;
        currency / scale / indicator_param 同 cross_section。
        """
        body = _strip_none(
            {
                "indicatorCodeList": _as_list(indicator),
                "securityCodeList": _as_list(security),
                "startDate": start_date,
                "endDate": end_date,
                "calendarType": calendar_type,
                "currency": currency,
                "scale": scale,
                "indicatorParamList": _indicator_param_list(indicator_param),
            }
        )
        result = await self._client._call("indicator.time-series", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        flattened = _flatten_time_series(_unwrap_indicator_data(result))
        return to_dataframe(_extract_rows(flattened), schema=None)
