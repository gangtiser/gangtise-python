from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi._quote_sharding import (
    DEFAULT_FULL_MARKET_LIMIT,
    SHARD_DAYS,
    fetch_shards,
    needs_limit_injection,
    plan_shards,
)

_DAY_KLINE_SCHEMA = [
    "securityCode", "date", "open", "high", "low", "close",
    "volume", "amount", "preClose", "changePct", "turnover",
]
_MINUTE_KLINE_SCHEMA = [
    "securityCode", "datetime", "open", "high", "low", "close", "volume", "amount",
]
_REALTIME_SCHEMA = [
    "securityCode", "name", "price", "open", "high", "low", "preClose",
    "volume", "amount", "changePct",
]


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


def _parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _date_to_iso(value: str | dt.date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


class Quote:
    """`gangtise.quote.*` — K-line + realtime quote endpoints."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def _day_kline(
        self,
        endpoint_key: str,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        days_per_shard = SHARD_DAYS[endpoint_key]
        if needs_limit_injection(security=security, explicit_limit=limit):
            limit = DEFAULT_FULL_MARKET_LIMIT

        if start_date and end_date:
            shards = plan_shards(
                start_date=_parse_date(start_date),
                end_date=_parse_date(end_date),
                days_per_shard=days_per_shard,
            )
        else:
            shards = []

        def fetch_shard(window: tuple[dt.date, dt.date]) -> Any:
            s, e = window
            body = _strip_none({
                "securityList": _as_list(security),
                "startDate": s.isoformat(),
                "endDate": e.isoformat(),
                "limit": limit,
                "fieldList": _as_list(field),
            })
            return self._client._call(endpoint_key, body=body)

        if shards:
            page_results = fetch_shards(
                shards, fetch=fetch_shard, concurrency=self._client.config.page_concurrency
            )
        else:
            body = _strip_none({
                "securityList": _as_list(security),
                "startDate": _date_to_iso(start_date),
                "endDate": _date_to_iso(end_date),
                "limit": limit,
                "fieldList": _as_list(field),
            })
            page_results = [self._client._call(endpoint_key, body=body)]

        merged: dict[str, Any] = {}
        rows: list[Any] = []
        for result in page_results:
            if isinstance(result, dict) and isinstance(result.get("list"), list):
                merged.update({k: v for k, v in result.items() if k != "list"})
                rows.extend(result["list"])
            elif isinstance(result, list):
                rows.extend(result)
        result_payload: dict[str, Any] = {**merged, "list": rows} if merged else {"list": rows}
        if raw:
            return result_payload
        return to_dataframe(rows, schema=_DAY_KLINE_SCHEMA)

    def day_kline(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.day-kline",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def day_kline_hk(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.day-kline-hk",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def day_kline_us(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.day-kline-us",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def index_day_kline(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.index-day-kline",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def minute_kline(
        self,
        *,
        security: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        body = _strip_none({
            "securityCode": security,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
            "fieldList": _as_list(field),
        })
        result = self._client._call("quote.minute-kline", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows: list[Any] = result.get("list", []) if isinstance(result, dict) else result
        return to_dataframe(rows, schema=_MINUTE_KLINE_SCHEMA)

    def realtime(
        self,
        *,
        security: Any,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        body = _strip_none({
            "securityList": _as_list(security),
            "fieldList": _as_list(field),
        })
        result = self._client._call("quote.realtime", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows: list[Any] = result if isinstance(result, list) else result.get("list", [])
        return to_dataframe(rows, schema=_REALTIME_SCHEMA)
