# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import datetime as dt
import warnings
from collections.abc import Sequence
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi._quote_sharding import (
    DEFAULT_FULL_MARKET_LIMIT,
    DEFAULT_QUOTE_LIMIT,
    SHARD_DAYS,
    drop_weekend_shards,
    fetch_shards,
    fetch_shards_async,
    is_full_market,
    plan_shards,
)
from gangtise_openapi.domains._common import FilterValue, _as_list, _strip_none


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
    full-market scale). Any other shape — dict rows, ragged rows, missing,
    non-string, or duplicate ``fieldList`` — falls back to the normalize path,
    preserving its pad/drop (and duplicate-name dedupe) behavior. The duplicate
    guard keeps the two paths equivalent: the dict transpose collapses a repeated
    field to one column, whereas ``pd.DataFrame(columns=fields)`` would emit two.
    """
    if (
        isinstance(fields, list)
        and fields
        and all(isinstance(f, str) for f in fields)
        and len(set(fields)) == len(fields)
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


def _finalize_quote_result(
    page_results: list[Any],
    *,
    label: str,
    limit: int,
    sharded: bool,
    shard_count: int,
    failed_shards: list[tuple[dt.date, dt.date]],
    shards: Sequence[tuple[dt.date, dt.date]] | None = None,
) -> tuple[dict[str, Any], list[Any]]:
    """Merge quote page/shard payloads into one result and flag ``partial``.

    Pure post-processing shared by the sync and async fetch paths (no I/O). Flags
    ``partial`` — and emits a ``warnings.warn`` visible on the default DataFrame path —
    on any of: a failed shard (``failedShards``), a malformed 2xx shape (rows dropped),
    or limit-truncation (a page/shard whose row count reached the sent ``limit``).
    ``shards`` (aligned with ``page_results``) lets the sharded path also record WHICH
    windows maxed out as ``truncatedShards`` — a script/agent consumer needs the concrete
    date ranges to re-pull narrower windows (mirrors ``failedShards``; TS v0.27.0).
    Returns ``(result_payload, rows)``.
    """
    merged: dict[str, Any] = {}
    field_list: Any = None
    rows: list[Any] = []
    malformed = 0
    truncated = 0
    truncated_windows: list[tuple[dt.date, dt.date]] = []

    def note_truncated(index: int) -> None:
        nonlocal truncated
        truncated += 1
        if shards is not None and index < len(shards):
            truncated_windows.append(shards[index])

    for i, result in enumerate(page_results):
        if isinstance(result, dict) and isinstance(result.get("list"), list):
            # Keep the FIRST non-empty fieldList (TS parity): a later shard with an empty
            # or missing fieldList must not blank the columns and drop every merged row.
            if (
                field_list is None
                and isinstance(result.get("fieldList"), list)
                and result["fieldList"]
            ):
                field_list = result["fieldList"]
            merged.update({k: v for k, v in result.items() if k not in ("list", "fieldList")})
            page_rows = result["list"]
            rows.extend(page_rows)
            if len(page_rows) >= limit:
                note_truncated(i)
        elif isinstance(result, list):
            rows.extend(result)
            if len(result) >= limit:
                note_truncated(i)
        elif result is not None:
            # 2xx but neither {list:[...]} nor a bare list — count it instead of silently
            # dropping, so the result is flagged partial. (None marks a shard already in
            # failed_shards; don't double-count. The sharded fan-out pre-filters broken
            # shapes into failed_shards, so this only fires on the single-request path.)
            malformed += 1

    result_payload: dict[str, Any] = {**merged, "list": rows} if merged else {"list": rows}
    if field_list is not None:
        result_payload["fieldList"] = field_list
    if sharded and merged:
        # A shard's own `total` is just that shard's row count; overwrite it with the
        # merged count so `total` reflects the whole combined result. Skipped when there
        # is no merged header (e.g. an all-weekend range → zero shards) so the empty
        # result stays a bare {"list": []} — TS parity (`if (!header) return {list: []}`).
        result_payload["total"] = len(rows)
    if failed_shards:
        result_payload["partial"] = True
        result_payload["failedShards"] = [
            {"startDate": s.isoformat(), "endDate": e.isoformat()} for s, e in failed_shards
        ]
        warnings.warn(
            f"{len(failed_shards)}/{shard_count} {label} shards failed; results are partial "
            "(see failedShards in raw output)",
            stacklevel=3,
        )
    if malformed:
        result_payload["partial"] = True
        warnings.warn(
            f"{malformed} {label} response(s) had an unexpected shape; their rows were "
            "dropped — results are partial",
            stacklevel=3,
        )
    if truncated:
        result_payload["partial"] = True
        if truncated_windows:
            result_payload["truncatedShards"] = [
                {"startDate": s.isoformat(), "endDate": e.isoformat()} for s, e in truncated_windows
            ]
        if sharded:
            warnings.warn(
                f"{truncated}/{shard_count} {label} shard(s) hit the {limit}-row limit; "
                "results are likely truncated (see truncatedShards in raw output) — "
                "narrow the range or raise limit (max 10000)",
                stacklevel=3,
            )
        else:
            warnings.warn(
                f"{label} returned {len(rows)} rows = the {limit}-row limit; results are "
                "likely truncated (this endpoint has no pagination) — narrow the date range "
                "or raise limit (max 10000)",
                stacklevel=3,
            )
    return result_payload, rows


def _validate_limit(limit: int | None) -> None:
    """The limit-capped quote endpoints accept an integer 1..10000 (TS ``parseNumberOption``).

    Reject out-of-range values locally: ``limit <= 0`` would make the ``rows >= limit``
    truncation check fire spuriously (and is a nonsensical request), and ``> 10000``
    exceeds the server row cap so the truncation ``cap`` could hide a real truncation.
    Also reject non-int inputs so a mistyped ``"10"`` raises ValidationError (not a raw
    ``TypeError`` from the comparison) and ``1.5`` / ``True`` can't slip past the range
    check — ``bool`` is excluded explicitly because it is an ``int`` subclass.
    """
    if limit is not None and (
        not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000
    ):
        raise ValidationError(f"limit must be an integer between 1 and 10000 (got {limit!r})")


def _flag_single_truncation(result: Any, rows: list[Any], limit: int, label: str) -> None:
    """Flag ``partial`` + warn when a non-paginated single-request quote endpoint
    (minute-kline) returns rows == the sent ``limit`` — its only truncation signal.
    ``limit`` MUST be the exact value sent on the request so the cap can't hide a
    truncation. Mirrors the TS ``flagIfLimitTruncated``.
    """
    if isinstance(result, dict) and result.get("partial") is True:
        return
    if len(rows) < limit:
        return
    if isinstance(result, dict):
        result["partial"] = True
    warnings.warn(
        f"{label} returned {len(rows)} rows = the {limit}-row limit; results are likely "
        "truncated (this endpoint has no pagination) — narrow the time range or raise limit "
        "(max 10000)",
        stacklevel=3,
    )


class Quote:
    """`gangtise.quote.*` — K-line + realtime quote endpoints."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def _day_kline(
        self,
        endpoint_key: str,
        *,
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
        full_market_value: str = "all",
        require_dates_for_full_market: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        _validate_limit(limit)
        days_per_shard = SHARD_DAYS[endpoint_key]
        label = endpoint_key.split(".", 1)[-1]
        full_market = is_full_market(security, full_market_value)
        if require_dates_for_full_market and full_market and not (start_date and end_date):
            raise ValidationError(
                f"quote {label} full-market ('{full_market_value}') requires both start_date "
                "and end_date (the full market is fetched via per-day shards)"
            )
        # Full-market lifts the per-request cap to the API max; explicit securities pin to
        # the default so the sent limit and the truncation cap are the same number.
        if limit is None:
            limit = DEFAULT_FULL_MARKET_LIMIT if full_market else DEFAULT_QUOTE_LIMIT

        if full_market and start_date and end_date:
            sharded = True
            shards = drop_weekend_shards(
                plan_shards(
                    start_date=_parse_date(start_date),
                    end_date=_parse_date(end_date),
                    days_per_shard=days_per_shard,
                )
            )
        else:
            sharded = False
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

        result_payload, rows = _finalize_quote_result(
            page_results,
            label=label,
            limit=limit,
            sharded=sharded,
            shard_count=len(shards),
            failed_shards=failed_shards,
            shards=shards if sharded else None,
        )
        if raw:
            return result_payload
        return _kline_dataframe(rows, result_payload.get("fieldList"))

    def day_kline(
        self,
        *,
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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

    def fund_flow(
        self,
        *,
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股个股日资金流向（quote.fund-flow）。

        沪深京个股，返回小/中/大/特大单流入流出金额及占比、主力净流入等；免费。
        security 传具体代码（单值或列表，如 600519.SH / 872931.BJ），或 "aShares"
        拉全 A 股——全市场按日自动分片并发合并，须同时传 start_date/end_date
        （缺日期本地报错）。单只证券无翻页，返回行数撞上 limit（默认 6000、最大 10000）
        时结果标 partial（raw 可见）并发 warning。
        """
        return self._day_kline(
            "quote.fund-flow",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
            full_market_value="aShares",
            require_dates_for_full_market=True,
        )

    def minute_kline(
        self,
        *,
        security: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询 A 股分钟 K 线（quote.minute-kline）。

        仅支持单只 A 股代码（不支持列表 / "all"）；start_time/end_time 格式
        yyyy-MM-dd HH:mm:ss。limit 默认 6000、最大 10000；该接口无翻页，返回行数撞上
        limit 时结果标 partial（raw 可见）并发 warning，提示缩小时间范围或分批取数。
        """
        _validate_limit(limit)
        if limit is None:
            limit = DEFAULT_QUOTE_LIMIT
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
        rows, fields = _quote_rows_and_fields(result)
        _flag_single_truncation(result, rows, limit, "minute-kline")
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_normalize_quote_rows(rows, fields), schema=None)

    def realtime(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
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
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
        full_market_value: str = "all",
        require_dates_for_full_market: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        _validate_limit(limit)
        days_per_shard = SHARD_DAYS[endpoint_key]
        label = endpoint_key.split(".", 1)[-1]
        full_market = is_full_market(security, full_market_value)
        if require_dates_for_full_market and full_market and not (start_date and end_date):
            raise ValidationError(
                f"quote {label} full-market ('{full_market_value}') requires both start_date "
                "and end_date (the full market is fetched via per-day shards)"
            )
        # Full-market lifts the per-request cap to the API max; explicit securities pin to
        # the default so the sent limit and the truncation cap are the same number.
        if limit is None:
            limit = DEFAULT_FULL_MARKET_LIMIT if full_market else DEFAULT_QUOTE_LIMIT

        if full_market and start_date and end_date:
            sharded = True
            shards = drop_weekend_shards(
                plan_shards(
                    start_date=_parse_date(start_date),
                    end_date=_parse_date(end_date),
                    days_per_shard=days_per_shard,
                )
            )
        else:
            sharded = False
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

        result_payload, rows = _finalize_quote_result(
            page_results,
            label=label,
            limit=limit,
            sharded=sharded,
            shard_count=len(shards),
            failed_shards=failed_shards,
            shards=shards if sharded else None,
        )
        if raw:
            return result_payload
        return _kline_dataframe(rows, result_payload.get("fieldList"))

    async def day_kline(
        self,
        *,
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
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

    async def fund_flow(
        self,
        *,
        security: FilterValue,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        """查询 A 股个股日资金流向（quote.fund-flow）。

        沪深京个股，返回小/中/大/特大单流入流出金额及占比、主力净流入等；免费。
        security 传具体代码（单值或列表，如 600519.SH / 872931.BJ），或 "aShares"
        拉全 A 股——全市场按日自动分片并发合并，须同时传 start_date/end_date
        （缺日期本地报错）。单只证券无翻页，返回行数撞上 limit（默认 6000、最大 10000）
        时结果标 partial（raw 可见）并发 warning。
        """
        return await self._day_kline(
            "quote.fund-flow",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
            full_market_value="aShares",
            require_dates_for_full_market=True,
        )

    async def minute_kline(
        self,
        *,
        security: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询 A 股分钟 K 线（quote.minute-kline）。

        仅支持单只 A 股代码（不支持列表 / "all"）；start_time/end_time 格式
        yyyy-MM-dd HH:mm:ss。limit 默认 6000、最大 10000；该接口无翻页，返回行数撞上
        limit 时结果标 partial（raw 可见）并发 warning，提示缩小时间范围或分批取数。
        """
        _validate_limit(limit)
        if limit is None:
            limit = DEFAULT_QUOTE_LIMIT
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
        rows, fields = _quote_rows_and_fields(result)
        _flag_single_truncation(result, rows, limit, "minute-kline")
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_normalize_quote_rows(rows, fields), schema=None)

    async def realtime(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
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
