# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import datetime as dt
import warnings
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi._quote_sharding import (
    DEFAULT_FULL_MARKET_LIMIT,
    SHARD_DAYS,
    drop_weekend_shards,
    fetch_shards,
    fetch_shards_async,
    is_all_market,
    needs_limit_injection,
    plan_shards,
)
from gangtise_openapi.domains._common import _as_list, _strip_none


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


def _normalize_quote_rows(rows: list[Any], fields: Any) -> list[dict[str, Any]]:
    """Transpose K-line / realtime rows against the response ``fieldList``.

    The quote endpoints return a columnar matrix ``{fieldList, list:[[...]]}``;
    each array row is zipped with ``fieldList`` into a dict keyed by the real
    field names. Rows that are already dicts pass through unchanged. The real
    field names are returned verbatim (no schema, no aliases), so the DataFrame
    columns stay in lockstep with the API.
    """
    normalized: list[dict[str, Any]] = []
    field_names = (
        fields if isinstance(fields, list) and all(isinstance(f, str) for f in fields) else None
    )
    for row in rows:
        if isinstance(row, dict):
            item = dict(row)
        elif isinstance(row, list) and field_names:
            item = {
                field: row[index] for index, field in enumerate(field_names) if index < len(row)
            }
        else:
            continue
        normalized.append(item)
    return normalized


def _kline_dataframe(rows: list[Any], fields: Any) -> pd.DataFrame:
    """Build the K-line DataFrame, preferring direct columnar construction.

    When ``fields`` is a list of column names and every row is a list of
    exactly ``len(fields)`` values, ``pd.DataFrame(rows, columns=fields)``
    skips the dict-per-row transpose (2-3x faster, ~half the peak memory at
    full-market scale). Any other shape — dict rows, ragged rows, missing or
    non-string ``fieldList`` — falls back to the normalize path, preserving
    its pad/drop behavior for ragged rows.
    """
    if (
        isinstance(fields, list)
        and fields
        and all(isinstance(f, str) for f in fields)
        and rows
        and all(isinstance(r, list) and len(r) == len(fields) for r in rows)
    ):
        return pd.DataFrame(rows, columns=fields)
    return to_dataframe(_normalize_quote_rows(rows, fields), schema=None)


def _quote_rows_and_fields(result: Any) -> tuple[list[Any], Any]:
    """Pull (rows, fieldList) out of a single quote response payload."""
    if isinstance(result, dict):
        rows = result.get("list")
        return (rows if isinstance(rows, list) else []), result.get("fieldList")
    if isinstance(result, list):
        return result, None
    return [], None


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

        sharded = False
        if is_all_market(security) and start_date and end_date:
            sharded = True
            shards = drop_weekend_shards(
                plan_shards(
                    start_date=_parse_date(start_date),
                    end_date=_parse_date(end_date),
                    days_per_shard=days_per_shard,
                )
            )
        else:
            shards = []

        def fetch_shard(window: tuple[dt.date, dt.date]) -> Any:
            s, e = window
            body = _strip_none(
                {
                    "securityList": _as_list(security),
                    "startDate": s.isoformat(),
                    "endDate": e.isoformat(),
                    "limit": limit,
                    "fieldList": _as_list(field),
                }
            )
            return self._client._call(endpoint_key, body=body)

        failed_shards: list[tuple[dt.date, dt.date]] = []
        if sharded:
            # An all-weekend range filters down to zero shards -> zero requests
            # and an empty result via the merge path below.
            page_results, failed_shards = fetch_shards(
                shards, fetch=fetch_shard, concurrency=self._client.config.page_concurrency
            )
        else:
            body = _strip_none(
                {
                    "securityList": _as_list(security),
                    "startDate": _date_to_iso(start_date),
                    "endDate": _date_to_iso(end_date),
                    "limit": limit,
                    "fieldList": _as_list(field),
                }
            )
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
        if failed_shards:
            # Mirror TS quoteSharding partial-failure flags (camelCase).
            result_payload["partial"] = True
            result_payload["failedShards"] = [
                {"startDate": s.isoformat(), "endDate": e.isoformat()} for s, e in failed_shards
            ]
            warnings.warn(
                f"{len(failed_shards)}/{len(shards)} kline shards failed; results are partial "
                "(see failedShards in raw output)",
                stacklevel=3,
            )
        if raw:
            return result_payload
        return _kline_dataframe(rows, merged.get("fieldList"))

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
        """查询 A 股日 K 线（quote.day-kline）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 1 个交易日，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return self._day_kline(
            "quote.day-kline",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
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
        """查询港股日 K 线（quote.day-kline-hk）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 2 个交易日，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return self._day_kline(
            "quote.day-kline-hk",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
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
        """查询美股日 K 线（quote.day-kline-us）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 1 个交易日，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return self._day_kline(
            "quote.day-kline-us",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
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
        """查询 A 股指数日 K 线（quote.index-day-kline）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 30 个交易日），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return self._day_kline(
            "quote.index-day-kline",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
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
        """查询 A 股分钟 K 线（quote.minute-kline）。

        仅支持单只 A 股代码（不支持列表 / "all"）；
        start_time/end_time 格式 yyyy-MM-dd HH:mm:ss。limit 默认 5000，最大 10000。
        """
        body = _strip_none(
            {
                "securityCode": security,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
                "fieldList": _as_list(field),
            }
        )
        result = self._client._call("quote.minute-kline", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows, fields = _quote_rows_and_fields(result)
        return to_dataframe(_normalize_quote_rows(rows, fields), schema=None)

    def realtime(
        self,
        *,
        security: Any,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询实时行情快照（quote.realtime）。

        security 支持单值或列表，也可传市场关键词：
        aShares=全 A 股 / hkStocks=全港股 / usStocks=全美股。
        """
        body = _strip_none(
            {
                "securityList": _as_list(security),
                "fieldList": _as_list(field),
            }
        )
        result = self._client._call("quote.realtime", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows, fields = _quote_rows_and_fields(result)
        return to_dataframe(_normalize_quote_rows(rows, fields), schema=None)


class AsyncQuote:
    """Async mirror of `Quote`."""

    def __init__(self, client: AsyncGangtiseClient) -> None:
        self._client = client

    async def _day_kline(
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

        sharded = False
        if is_all_market(security) and start_date and end_date:
            sharded = True
            shards = drop_weekend_shards(
                plan_shards(
                    start_date=_parse_date(start_date),
                    end_date=_parse_date(end_date),
                    days_per_shard=days_per_shard,
                )
            )
        else:
            shards = []

        async def fetch_shard(window: tuple[dt.date, dt.date]) -> Any:
            s, e = window
            body = _strip_none(
                {
                    "securityList": _as_list(security),
                    "startDate": s.isoformat(),
                    "endDate": e.isoformat(),
                    "limit": limit,
                    "fieldList": _as_list(field),
                }
            )
            return await self._client._call(endpoint_key, body=body)

        failed_shards: list[tuple[dt.date, dt.date]] = []
        if sharded:
            # An all-weekend range filters down to zero shards -> zero requests
            # and an empty result via the merge path below.
            page_results, failed_shards = await fetch_shards_async(
                shards,
                fetch=fetch_shard,
                concurrency=self._client.config.page_concurrency,
            )
        else:
            body = _strip_none(
                {
                    "securityList": _as_list(security),
                    "startDate": _date_to_iso(start_date),
                    "endDate": _date_to_iso(end_date),
                    "limit": limit,
                    "fieldList": _as_list(field),
                }
            )
            page_results = [await self._client._call(endpoint_key, body=body)]

        merged: dict[str, Any] = {}
        rows: list[Any] = []
        for result in page_results:
            if isinstance(result, dict) and isinstance(result.get("list"), list):
                merged.update({k: v for k, v in result.items() if k != "list"})
                rows.extend(result["list"])
            elif isinstance(result, list):
                rows.extend(result)
        result_payload: dict[str, Any] = {**merged, "list": rows} if merged else {"list": rows}
        if failed_shards:
            # Mirror TS quoteSharding partial-failure flags (camelCase).
            result_payload["partial"] = True
            result_payload["failedShards"] = [
                {"startDate": s.isoformat(), "endDate": e.isoformat()} for s, e in failed_shards
            ]
            warnings.warn(
                f"{len(failed_shards)}/{len(shards)} kline shards failed; results are partial "
                "(see failedShards in raw output)",
                stacklevel=3,
            )
        if raw:
            return result_payload
        return _kline_dataframe(rows, merged.get("fieldList"))

    async def day_kline(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股日 K 线（quote.day-kline）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 1 个交易日，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return await self._day_kline(
            "quote.day-kline",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
        )

    async def day_kline_hk(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询港股日 K 线（quote.day-kline-hk）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 2 个交易日，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return await self._day_kline(
            "quote.day-kline-hk",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
        )

    async def day_kline_us(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询美股日 K 线（quote.day-kline-us）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 1 个交易日，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return await self._day_kline(
            "quote.day-kline-us",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
        )

    async def index_day_kline(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股指数日 K 线（quote.index-day-kline）。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 30 个交易日），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。
        """
        return await self._day_kline(
            "quote.index-day-kline",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
        )

    async def minute_kline(
        self,
        *,
        security: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询 A 股分钟 K 线（quote.minute-kline）。

        仅支持单只 A 股代码（不支持列表 / "all"）；
        start_time/end_time 格式 yyyy-MM-dd HH:mm:ss。limit 默认 5000，最大 10000。
        """
        body = _strip_none(
            {
                "securityCode": security,
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
                "fieldList": _as_list(field),
            }
        )
        result = await self._client._call("quote.minute-kline", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows, fields = _quote_rows_and_fields(result)
        return to_dataframe(_normalize_quote_rows(rows, fields), schema=None)

    async def realtime(
        self,
        *,
        security: Any,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询实时行情快照（quote.realtime）。

        security 支持单值或列表，也可传市场关键词：
        aShares=全 A 股 / hkStocks=全港股 / usStocks=全美股。
        """
        body = _strip_none(
            {
                "securityList": _as_list(security),
                "fieldList": _as_list(field),
            }
        )
        result = await self._client._call("quote.realtime", body=body)
        if raw:
            return result  # type: ignore[no-any-return]
        rows, fields = _quote_rows_and_fields(result)
        return to_dataframe(_normalize_quote_rows(rows, fields), schema=None)
