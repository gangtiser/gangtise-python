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
from gangtise_openapi._normalize import (
    assert_columnar_header,
    columnar_schema_valid,
    to_dataframe,
    zip_field_row,
)
from gangtise_openapi._pagination import warn_if_server_partial
from gangtise_openapi._per_security import (
    estimate_trading_days,
    fetch_per_security,
    fetch_per_security_async,
    merge_parts,
)
from gangtise_openapi._quote_sharding import (
    DEFAULT_FULL_MARKET_LIMIT,
    DEFAULT_QUOTE_LIMIT,
    MARKET_SHARD_DAYS,
    REALTIME_MARKETS,
    canonicalize_market_keywords,
    check_market_keywords,
    column_remap,
    drop_weekend_shards,
    fetch_shards,
    fetch_shards_async,
    plan_shards,
    resolve_full_market,
)
from gangtise_openapi._transport import _attach_envelope_trace_id
from gangtise_openapi.domains._common import (
    FilterValue,
    _as_list,
    _request_body,
    _validate_date,
)


def _parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    # Guard before parsing: the all-market sharding planner consumes these dates
    # ahead of ``_request_body``, so without this the caller gets a bare
    # ``ValueError`` from ``fromisoformat`` instead of the message explaining why
    # the layout is refused.
    _validate_date(value, "startDate")
    return dt.date.fromisoformat(value)


def _date_to_iso(value: str | dt.date | None, field: str = "startDate") -> str | None:
    """Validate and normalize a date argument to ``YYYY-MM-DD`` (or ``None``).

    🔴 **Called EARLY, before anything reads the dates.** ``_request_body`` normalizes
    the body on the way out, but two things consume these values before a body exists
    — the shard planner and the per-security size estimate — and both are
    ``fromisoformat``-based, which accepts only ``YYYY-MM-DD``. Feeding them a raw
    ``2016/01/01`` (a layout this SDK accepts and normalizes) made the estimate fall
    back to the one-year default: a ten-year, three-security request measured 786 rows
    instead of 7830, skipped the per-security split, and came back capped with the tail
    securities missing entirely. Normalizing once up front is what keeps the estimate,
    the shard plan and the wire body reading the same dates.
    """
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value.isoformat()
    normalized: str = _validate_date(value, field)
    return normalized


def _normalize_quote_rows(rows: list[Any], fields: Any, source: Any = None) -> list[dict[str, Any]]:
    """Transpose K-line / realtime rows against the response ``fieldList``.

    The quote endpoints return a columnar matrix ``{fieldList, list:[[...]]}``;
    each array row is zipped with ``fieldList`` into a dict keyed by the real
    field names. Rows that are already dicts pass through unchanged. The real
    field names are returned verbatim (no schema, no aliases), so the DataFrame
    columns stay in lockstep with the API.

    A row whose length disagrees with ``fieldList`` is refused rather than padded
    — see :func:`zip_field_row`; ``quote.realtime`` is one of the endpoints that
    returns values for the valid fields only while echoing every requested name.
    ``source`` is the payload the rows came out of, passed through so that refusal
    keeps the response's traceId (the guard's own docstring names realtime as its
    headline case, so this path in particular must stay traceable).

    Array rows additionally require a USABLE header — present and free of duplicate
    names (:func:`assert_columnar_header`). Without one there is no column meaning
    to attach: rows used to be dropped silently, and a repeated name collapsed to
    its last value. Same rule ``normalize_rows`` applies, so the quote path (which
    zips directly, bypassing it) cannot be the loose one (TS v0.38.0).
    """
    normalized: list[dict[str, Any]] = []
    if any(isinstance(row, list) for row in rows):
        assert_columnar_header(fields if isinstance(fields, list) else None, source)
    field_names = (
        fields if isinstance(fields, list) and all(isinstance(f, str) for f in fields) else None
    )
    for row in rows:
        if isinstance(row, dict):
            item = dict(row)
        elif isinstance(row, list) and field_names:
            item = zip_field_row(field_names, row, source)
        else:
            continue
        normalized.append(item)
    return normalized


def _kline_dataframe(rows: list[Any], fields: Any, source: Any = None) -> pd.DataFrame:
    """Build the K-line DataFrame, preferring direct columnar construction.

    When ``fields`` is a list of column names and every row is a list of
    exactly ``len(fields)`` values, ``pd.DataFrame(rows, columns=fields)``
    skips the dict-per-row transpose (2-3x faster, ~half the peak memory at
    full-market scale). Any other shape — dict rows, ragged rows, missing,
    non-string, or duplicate ``fieldList`` — falls back to the normalize path.
    The duplicate check is what keeps the two paths equivalent, and since v0.4.0
    equivalent means BOTH REFUSE: ``_normalize_quote_rows`` raises on a repeated
    name (it would otherwise collapse to the last value) while
    ``pd.DataFrame(columns=fields)`` would silently emit two same-named columns.
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
    return to_dataframe(_normalize_quote_rows(rows, fields, source), schema=None)


def _flag_missing_fields(result: Any, requested: Any, label: str) -> None:
    """Flag ``partial`` + ``missingFields`` for a requested column that never came back.

    ``realtime`` / ``day-kline`` / ``minute-kline`` / ``fund-flow`` answer a field
    name they do not recognise (a typo, or a column since retired) by dropping the
    NAME AND THE VALUE — HTTP 200, no error, one column simply absent. The caller
    then reads that column and gets nothing back rather than a failure. Since the
    SDK knows what was asked for, the gap is machine-detectable here (CLI probed
    2026-09-05: realtime given ``turnoverRate`` returns only the other columns).

    Only "asked for but not returned" is judged — extra columns the server volunteers
    are fine — so this depends on NO field whitelist and cannot go stale (TS v0.38.0
    ``flagMissingFields``).
    """
    if not requested or not isinstance(result, dict):
        return
    returned = result.get("fieldList")
    if not isinstance(returned, list):
        return
    have = {str(field) for field in returned}
    missing = [str(field) for field in requested if str(field) not in have]
    if not missing:
        return
    result["partial"] = True
    result["missingFields"] = missing
    warnings.warn(
        f"{label} returned no column for {', '.join(missing)} — the server drops a field "
        "name it does not recognise (or no longer serves) without an error; check the "
        "spelling against the endpoint's field list. Result marked partial.",
        stacklevel=3,
    )


def _wants_per_security(
    securities: Sequence[Any],
    full_market: bool,
    start_date: Any,
    end_date: Any,
    limit: int,
) -> bool:
    """Whether several explicit securities need one request each.

    One request naming N securities over a long range comes back capped at ``limit``
    with the TAIL SECURITIES MISSING ENTIRELY — the rows are filled in order, so the
    truncation eats whole securities rather than trimming each. Splitting keeps every
    part well under the cap. The bound is deliberately an over-estimate (weekday count
    ignoring holidays, :func:`estimate_trading_days`): under-estimating sends one
    request where two were needed and the answer comes back capped anyway (TS v0.38.0).
    """
    if full_market or len(securities) <= 1:
        return False
    return len(securities) * estimate_trading_days(start_date, end_date) > limit


def _finalize_per_security(
    parts: list[Any],
    *,
    securities: Sequence[Any],
    cap: int,
    label: str,
    field: Any,
    raw: bool,
) -> pd.DataFrame | dict[str, Any]:
    """Merge per-security parts, flag missing columns, and render. Shared sync/async."""
    result_payload = merge_parts(parts, securities=securities, cap=cap, label=label)
    _flag_missing_fields(result_payload, _as_list(field), label)
    if raw:
        return result_payload
    return _kline_dataframe(result_payload["list"], result_payload.get("fieldList"), result_payload)


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

    The sharded path applies four extra rules that the single-request path has no use
    for (TS v0.38.0). ``failed_shards`` is appended to in place by the first three:

    1. **An empty shard that claims rows** (``total > 0``, or its own ``partial``) is a
       contradiction, not a holiday — counted as failed rather than as a quiet window.
    2. **A shard whose columnar rows do not match its own ``fieldList``** (missing,
       duplicated or mis-sized) has no trustworthy column names; the single-request
       path lets ``zip_field_row`` refuse such a row, and the merge must not be the
       place it slips through padded, truncated, or read under a guessed header.
    3. **A shard ordering its columns differently** is re-mapped onto the header
       shard's order; one MISSING a header column cannot be aligned and is failed too.
       Read positionally under the wrong header, ``close`` would land in ``volume``
       with nothing in the payload to notice.
    4. **A shard carrying its own ``partial``** keeps the merged result partial — only
       the header shard's metadata survives the merge, so the marker must be carried.

    Metadata comes from the first shard that CONTRIBUTED ROWS; an all-empty result
    falls back to a legitimately-empty shard's metadata, never to one already judged
    failed (whose ``fieldList`` would become "the columns the server returned").
    """
    merged: dict[str, Any] = {}
    fallback: dict[str, Any] = {}
    field_list: Any = None
    # Insertion-ordered set of the object rows' keys — the returned columns when no
    # columnar header exists. Collected only while there is no header to collect.
    object_keys: dict[str, None] = {}
    rows: list[Any] = []
    malformed = 0
    truncated = 0
    partial_shards = 0
    truncated_windows: list[tuple[dt.date, dt.date]] = []

    def window(index: int) -> tuple[dt.date, dt.date] | None:
        return shards[index] if shards is not None and index < len(shards) else None

    def note_truncated(index: int) -> None:
        nonlocal truncated
        truncated += 1
        w = window(index)
        if w is not None:
            truncated_windows.append(w)

    def note_failed(index: int, reason: str) -> None:
        w = window(index)
        if w is None:
            return
        if w not in failed_shards:
            failed_shards.append(w)
        warnings.warn(
            f"{label} shard {w[0].isoformat()}..{w[1].isoformat()} {reason}; "
            "its rows were dropped (see failedShards in raw output)",
            stacklevel=4,
        )

    for i, result in enumerate(page_results):
        if isinstance(result, dict) and isinstance(result.get("list"), list):
            page_rows: list[Any] = result["list"]
            shard_fields = (
                result["fieldList"]
                if isinstance(result.get("fieldList"), list) and result["fieldList"]
                else None
            )
            if sharded and not page_rows:
                total = result.get("total")
                claims_rows = (
                    isinstance(total, int) and not isinstance(total, bool) and total > 0
                ) or result.get("partial") is True
                if claims_rows:
                    claim = (
                        f"reported total={total}"
                        if isinstance(total, int) and not isinstance(total, bool) and total > 0
                        else "carried a partial marker"
                    )
                    note_failed(i, f"{claim} but delivered no rows")
                    continue
                # A genuinely empty window (weekend / holiday) says nothing about the
                # column layout: it neither supplies the header — an empty fieldList
                # would swallow every later column — nor counts as failed for lacking
                # one. It is the only shard an all-empty result may take metadata from.
                if not fallback:
                    fallback = {k: v for k, v in result.items() if k != "list"}
                continue
            columnar = any(isinstance(row, list) for row in page_rows)
            if sharded and columnar and not columnar_schema_valid(shard_fields, page_rows):
                note_failed(
                    i,
                    "returned columnar rows that do not match its own fieldList "
                    "(missing, duplicated or mis-sized)",
                )
                continue
            # Keep the FIRST non-empty fieldList (TS parity): a later shard with an empty
            # or missing fieldList must not blank the columns and drop every merged row.
            # On the sharded path only a header VALIDATED against columnar rows may take
            # the slot — an object-row shard's fieldList constrains nothing of its own,
            # was never checked, and must not constrain the array shards that follow.
            if field_list is None and shard_fields is not None and (columnar or not sharded):
                field_list = shard_fields
            if sharded and columnar and field_list is not None and shard_fields != field_list:
                remap = column_remap(field_list, shard_fields or [])
                if remap is None:
                    note_failed(
                        i,
                        "returned columns that cannot be aligned with the first shard's fieldList",
                    )
                    continue
                page_rows = [
                    [row[k] for k in remap] if isinstance(row, list) else row for row in page_rows
                ]
            if result.get("partial") is True:
                if sharded:
                    partial_shards += 1
                else:
                    # Single-request path: a marker the SERVER set needs announcing
                    # too, or the default DataFrame return drops it silently.
                    warn_if_server_partial(result, label)
            merged.update({k: v for k, v in result.items() if k not in ("list", "fieldList")})
            if field_list is None:
                for row in page_rows:
                    if isinstance(row, dict):
                        object_keys.update(dict.fromkeys(row))
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

    base = merged if merged else fallback
    result_payload: dict[str, Any] = {**base, "list": rows} if base else {"list": rows}
    # Rebuilding the dict drops the envelope traceId the transport attached, which
    # is precisely what a downstream shape refusal needs (see `zip_field_row`).
    # Carried only for a SINGLE source payload: merging shards means merging N
    # responses with N different traceIds, and there is no honest way to pick one.
    if len(page_results) == 1:
        result_payload = _attach_envelope_trace_id(
            result_payload, getattr(page_results[0], "envelope_trace_id", None)
        )
    # Two jobs share the output's fieldList: zipping array rows by position (only a
    # header validated against columnar rows may do that) and telling
    # `_flag_missing_fields` which columns came back (which needs an honest answer for
    # EVERY shape). Hence: validated header → it; object rows and no header → the union
    # of their own keys, since the returned columns ARE the keys; nothing merged → the
    # server's explicit column set, even empty ("no requested column came back" is then
    # true); nothing at all → no fieldList, there being nothing to compare against.
    if field_list is not None:
        result_payload["fieldList"] = field_list
    elif sharded:
        if rows:
            result_payload["fieldList"] = list(object_keys)
        elif not isinstance(base.get("fieldList"), list):
            result_payload.pop("fieldList", None)
    if sharded and base:
        # A shard's own `total` is just that shard's row count; overwrite it with the
        # merged count so `total` reflects the whole combined result. Skipped when there
        # is no merged header (e.g. an all-weekend range → zero shards) so the empty
        # result stays a bare {"list": []} — TS parity (`if (!header) return {list: []}`).
        result_payload["total"] = len(rows)
    if partial_shards:
        result_payload["partial"] = True
        warnings.warn(
            f"{partial_shards}/{shard_count} {label} shard(s) reported themselves partial; "
            "the merged result is marked partial",
            stacklevel=3,
        )
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
        require_dates_for_full_market: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        _validate_limit(limit)
        # Normalize BEFORE the shard planner or the per-security estimate read these
        # (see `_date_to_iso`): both parse ISO only, and a legal `2016/01/01` used to
        # make the estimate silently skip the split.
        start_date = _date_to_iso(start_date, "startDate")
        end_date = _date_to_iso(end_date, "endDate")
        markets = MARKET_SHARD_DAYS[endpoint_key]
        label = endpoint_key.split(".", 1)[-1]
        # Validate before anything is sent: a keyword this endpoint does not take,
        # or one mixed with codes, is a local error — and these endpoints answer it
        # in the most misleading way (a 120001 pointing at codes that are fine, or
        # on fund-flow no error at all, just a silently narrowed result).
        check_market_keywords(security, tuple(markets), f"quote {label}")
        security = canonicalize_market_keywords(security, tuple(markets))
        keyword = resolve_full_market(security, markets)
        full_market = keyword is not None
        if require_dates_for_full_market and full_market and not (start_date and end_date):
            raise ValidationError(
                f"quote {label} full-market ({keyword!r}) requires both start_date "
                "and end_date (the full market is fetched via per-day shards)"
            )
        # Full-market lifts the per-request cap to the API max; explicit securities pin to
        # the default so the sent limit and the truncation cap are the same number.
        if limit is None:
            limit = DEFAULT_FULL_MARKET_LIMIT if full_market else DEFAULT_QUOTE_LIMIT

        if keyword is not None and start_date and end_date:
            # Each market shards at its own granularity: a whole-market HK pull
            # tolerates 2-day windows where A-share and US pulls need one day each.
            sharded = True
            shards = drop_weekend_shards(
                plan_shards(
                    start_date=_parse_date(start_date),
                    end_date=_parse_date(end_date),
                    days_per_shard=markets[keyword],
                )
            )
        else:
            sharded = False
            shards = []

        securities = _as_list(security) or []
        if _wants_per_security(securities, full_market, start_date, end_date, limit):

            def fetch_part(code: Any) -> Any:
                body = _request_body(
                    {
                        "securityList": [code],
                        "startDate": _date_to_iso(start_date),
                        "endDate": _date_to_iso(end_date),
                        "limit": limit,
                        "fieldList": _as_list(field),
                    }
                )
                return self._client._call(endpoint_key, body=body)

            parts = fetch_per_security(
                securities,
                fetch=fetch_part,
                label=f"quote {label}",
                concurrency=self._client.config.page_concurrency,
            )
            return _finalize_per_security(
                parts,
                securities=securities,
                cap=limit,
                label=f"quote {label}",
                field=field,
                raw=raw,
            )

        def fetch_shard(window: tuple[dt.date, dt.date]) -> Any:
            s, e = window
            body = _request_body(
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
            body = _request_body(
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
        _flag_missing_fields(result_payload, _as_list(field), f"quote {label}")
        if raw:
            return result_payload
        return _kline_dataframe(rows, result_payload.get("fieldList"), result_payload)

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
        """查询历史日 K 线（quote.day-kline）：A股 / 港股 / 美股个股、沪深 ETF
        （如 512800.SH）、交易所指数（沪深京）、概念指数（.GT）、行业指数
        （中信 .CI / 申万 .SWI）、全球指数（如 SPX.SPI / N225.NKI / HSI.HI），可一次混传。

        ⚠️ 服务端 2026-08-14 起**不再支持 "all"**，全市场改用 aShares / hkStocks /
        usStocks，且关键词必须单独传（不能与代码或另一个关键词混填）——两种写法服务端
        都回 120001「证券代码无效」，提示指向代码本身会把排查带偏，故本地先拦。
        **关键词只覆盖个股**，ETF 与各类指数必须逐个传代码。
        关键词+日期区间时自动按市场粒度分片并发拉取（aShares/usStocks 每片 1 天、
        hkStocks 每片 2 天，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。

        多只证券且「证券数 × 区间工作日数」超过 limit 时，自动改为逐只并发请求再按
        传入顺序合并——一次请求装不下时服务端是按行截断的，尾部证券会**整只消失**。
        某只填满 limit 会标 partial + truncatedSecurities。

        ETF 有复权因子（adjustFactor），volume 单位是「份」；全球指数的 amount 为 null，
        tradeDate 是交易所当地时间。
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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，请改用 day_kline()——它已覆盖港股
        并支持与其他市场混传。接口本身仍可调用，且保留 "all" 全市场关键词；本方法暂不删除，
        是因为它不校验代码而 day_kline 会校验，且 index_day_kline 另有 day_kline 做不到的能力。

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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，请改用 day_kline()——它已覆盖美股
        并支持与其他市场混传。接口本身仍可调用，且保留 "all" 全市场关键词；本方法暂不删除，
        是因为它不校验代码而 day_kline 会校验，且 index_day_kline 另有 day_kline 做不到的能力。

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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，请优先用 day_kline()。仍保留是因为
        本接口有两处 day_kline 做不到的能力——"all" 一次取全部指数，以及返回 securityName
        指数名称（day_kline 查指数只有代码没有名称）；反过来 day_kline 独有 adjustFactor。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 **15 天**——约 531 行/交易日 × 30 天窗口约 11.7K 必然撞 10000 行上限并静默
        截断，15 天窗口约 5.8K 安全），部分分片失败时结果带 partial/failedShards
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
            require_dates_for_full_market=True,
        )

    def minute_kline(
        self,
        *,
        security: FilterValue,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询分钟 K 线（quote.minute-kline）。

        仅支持沪深（不含北交所）：A 股个股 .SH/.SZ、ETF .SH/.SZ（如 512800.SH）、
        交易所指数 .SH/.SZ、概念指数 .GT、行业指数（中信 .CI / 申万 .SWI）、
        全球指数（如 SPX.SPI / N225.NKI / HSI.HI）；**没有全市场关键词**。
        接口本身一次只收一只，传列表时 SDK 逐只并发请求、按传入顺序合并；
        各只的列布局必须一致，某只填满 limit 会标 partial + truncatedSecurities。
        全球指数的 volume / amount 为 null，tradeTime 是交易所当地时间（时间过滤也按当地时间）。
        start_time/end_time 格式 yyyy-MM-dd HH:mm:ss。limit 默认 6000、最大 10000；
        该接口无翻页，返回行数撞上 limit 时结果标 partial（raw 可见）并发 warning，
        提示缩小时间范围或分批取数。

        ⚠️ 服务端只保留近期的分钟数据，日期过旧会返回**空表且不报错**——查不到数据时
        先确认日期在保留窗口内（日 K 的历史区间比这长得多）。
        """
        _validate_limit(limit)
        if limit is None:
            limit = DEFAULT_QUOTE_LIMIT
        securities = _as_list(security) or []
        if not securities:
            raise ValidationError("security is required: pass one or more security codes")

        def make_body(code: Any) -> dict[str, Any]:
            return _request_body(
                {
                    "securityCode": code,
                    "startTime": start_time,
                    "endTime": end_time,
                    "limit": limit,
                    "fieldList": _as_list(field),
                }
            )

        if len(securities) > 1:
            parts = fetch_per_security(
                securities,
                fetch=lambda code: self._client._call("quote.minute-kline", body=make_body(code)),
                label="quote minute-kline",
                concurrency=self._client.config.page_concurrency,
            )
            result_payload = merge_parts(
                parts, securities=securities, cap=limit, label="quote minute-kline"
            )
            _flag_missing_fields(result_payload, _as_list(field), "quote minute-kline")
            if raw:
                return result_payload
            rows, fields = _quote_rows_and_fields(result_payload)
            return to_dataframe(_normalize_quote_rows(rows, fields, result_payload), schema=None)

        result = self._client._call("quote.minute-kline", body=make_body(securities[0]))
        warn_if_server_partial(result, "quote minute-kline")
        rows, fields = _quote_rows_and_fields(result)
        _flag_single_truncation(result, rows, limit, "minute-kline")
        _flag_missing_fields(result, _as_list(field), "quote minute-kline")
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_normalize_quote_rows(rows, fields, result), schema=None)

    def realtime(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询实时行情快照（quote.realtime）：个股、沪深 ETF（如 512800.SH）、
        交易所/概念/行业指数，以及 20 个全球指数（如 SPX.SPI / N225.NKI / HSI.HI）。

        security 支持单值或列表，也可传市场关键词：
        aShares=全 A 股 / hkStocks=全港股 / usStocks=全美股——关键词**必须单独传**，
        与代码或另一个关键词混填服务端回 120001（提示指向代码本身，会把排查带偏），
        因此本地先拦。**关键词只覆盖个股**，ETF 与各类指数没有全市场关键词，要逐个传代码。

        字段：新增 tradeStatus（交易状态，仅 A 股 / 港股个股有值）；
        **turnoverRate / volumeRatio 不返回**——传了会连字段名一起被丢弃且不报错
        （SDK 会标 partial + missingFields 并 warn），换手率改走 EDE 指标 qte_turn。
        美股 amount 为 null；全球指数的 volume / amount / amplitude 均为 null，
        tradeDate / tradeTime 是交易所当地时间。
        """
        # Realtime takes the same keywords as day-kline but never shards (one
        # snapshot per security), so it only needs the alone-and-known check.
        check_market_keywords(security, REALTIME_MARKETS, "quote realtime")
        security = canonicalize_market_keywords(security, REALTIME_MARKETS)
        body = _request_body(
            {
                "securityList": _as_list(security),
                "fieldList": _as_list(field),
            }
        )
        result = self._client._call("quote.realtime", body=body)
        warn_if_server_partial(result, "quote realtime")
        _flag_missing_fields(result, _as_list(field), "quote realtime")
        if raw:
            return result  # type: ignore[no-any-return]
        rows, fields = _quote_rows_and_fields(result)
        return to_dataframe(_normalize_quote_rows(rows, fields, result), schema=None)


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
        require_dates_for_full_market: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        _validate_limit(limit)
        # Normalize BEFORE the shard planner or the per-security estimate read these
        # (see `_date_to_iso`): both parse ISO only, and a legal `2016/01/01` used to
        # make the estimate silently skip the split.
        start_date = _date_to_iso(start_date, "startDate")
        end_date = _date_to_iso(end_date, "endDate")
        markets = MARKET_SHARD_DAYS[endpoint_key]
        label = endpoint_key.split(".", 1)[-1]
        # Validate before anything is sent: a keyword this endpoint does not take,
        # or one mixed with codes, is a local error — and these endpoints answer it
        # in the most misleading way (a 120001 pointing at codes that are fine, or
        # on fund-flow no error at all, just a silently narrowed result).
        check_market_keywords(security, tuple(markets), f"quote {label}")
        security = canonicalize_market_keywords(security, tuple(markets))
        keyword = resolve_full_market(security, markets)
        full_market = keyword is not None
        if require_dates_for_full_market and full_market and not (start_date and end_date):
            raise ValidationError(
                f"quote {label} full-market ({keyword!r}) requires both start_date "
                "and end_date (the full market is fetched via per-day shards)"
            )
        # Full-market lifts the per-request cap to the API max; explicit securities pin to
        # the default so the sent limit and the truncation cap are the same number.
        if limit is None:
            limit = DEFAULT_FULL_MARKET_LIMIT if full_market else DEFAULT_QUOTE_LIMIT

        if keyword is not None and start_date and end_date:
            # Each market shards at its own granularity: a whole-market HK pull
            # tolerates 2-day windows where A-share and US pulls need one day each.
            sharded = True
            shards = drop_weekend_shards(
                plan_shards(
                    start_date=_parse_date(start_date),
                    end_date=_parse_date(end_date),
                    days_per_shard=markets[keyword],
                )
            )
        else:
            sharded = False
            shards = []

        securities = _as_list(security) or []
        if _wants_per_security(securities, full_market, start_date, end_date, limit):

            async def fetch_part(code: Any) -> Any:
                body = _request_body(
                    {
                        "securityList": [code],
                        "startDate": _date_to_iso(start_date),
                        "endDate": _date_to_iso(end_date),
                        "limit": limit,
                        "fieldList": _as_list(field),
                    }
                )
                return await self._client._call(endpoint_key, body=body)

            parts = await fetch_per_security_async(
                securities,
                fetch=fetch_part,
                label=f"quote {label}",
                concurrency=self._client.config.page_concurrency,
            )
            return _finalize_per_security(
                parts,
                securities=securities,
                cap=limit,
                label=f"quote {label}",
                field=field,
                raw=raw,
            )

        async def fetch_shard(window: tuple[dt.date, dt.date]) -> Any:
            s, e = window
            body = _request_body(
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
            body = _request_body(
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
        _flag_missing_fields(result_payload, _as_list(field), f"quote {label}")
        if raw:
            return result_payload
        return _kline_dataframe(rows, result_payload.get("fieldList"), result_payload)

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
        """查询历史日 K 线（quote.day-kline）：A股 / 港股 / 美股个股、沪深 ETF
        （如 512800.SH）、交易所指数（沪深京）、概念指数（.GT）、行业指数
        （中信 .CI / 申万 .SWI）、全球指数（如 SPX.SPI / N225.NKI / HSI.HI），可一次混传。

        ⚠️ 服务端 2026-08-14 起**不再支持 "all"**，全市场改用 aShares / hkStocks /
        usStocks，且关键词必须单独传（不能与代码或另一个关键词混填）——两种写法服务端
        都回 120001「证券代码无效」，提示指向代码本身会把排查带偏，故本地先拦。
        **关键词只覆盖个股**，ETF 与各类指数必须逐个传代码。
        关键词+日期区间时自动按市场粒度分片并发拉取（aShares/usStocks 每片 1 天、
        hkStocks 每片 2 天，周末分片自动跳过），部分分片失败时结果带 partial/failedShards
        标记并发出 warning（raw=True 可见）。limit 默认 6000，最大 10000。

        多只证券且「证券数 × 区间工作日数」超过 limit 时，自动改为逐只并发请求再按
        传入顺序合并——一次请求装不下时服务端是按行截断的，尾部证券会**整只消失**。
        某只填满 limit 会标 partial + truncatedSecurities。

        ETF 有复权因子（adjustFactor），volume 单位是「份」；全球指数的 amount 为 null，
        tradeDate 是交易所当地时间。
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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，请改用 day_kline()——它已覆盖港股
        并支持与其他市场混传。接口本身仍可调用，且保留 "all" 全市场关键词；本方法暂不删除，
        是因为它不校验代码而 day_kline 会校验，且 index_day_kline 另有 day_kline 做不到的能力。

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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，请改用 day_kline()——它已覆盖美股
        并支持与其他市场混传。接口本身仍可调用，且保留 "all" 全市场关键词；本方法暂不删除，
        是因为它不校验代码而 day_kline 会校验，且 index_day_kline 另有 day_kline 做不到的能力。

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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，请优先用 day_kline()。仍保留是因为
        本接口有两处 day_kline 做不到的能力——"all" 一次取全部指数，以及返回 securityName
        指数名称（day_kline 查指数只有代码没有名称）；反过来 day_kline 独有 adjustFactor。

        security 支持单值或列表，"all"=全市场；all+日期区间时自动按日分片并发拉取
        （每片 **15 天**——约 531 行/交易日 × 30 天窗口约 11.7K 必然撞 10000 行上限并静默
        截断，15 天窗口约 5.8K 安全），部分分片失败时结果带 partial/failedShards
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
            require_dates_for_full_market=True,
        )

    async def minute_kline(
        self,
        *,
        security: FilterValue,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询分钟 K 线（quote.minute-kline）。

        仅支持沪深（不含北交所）：A 股个股 .SH/.SZ、ETF .SH/.SZ（如 512800.SH）、
        交易所指数 .SH/.SZ、概念指数 .GT、行业指数（中信 .CI / 申万 .SWI）、
        全球指数（如 SPX.SPI / N225.NKI / HSI.HI）；**没有全市场关键词**。
        接口本身一次只收一只，传列表时 SDK 逐只并发请求、按传入顺序合并；
        各只的列布局必须一致，某只填满 limit 会标 partial + truncatedSecurities。
        全球指数的 volume / amount 为 null，tradeTime 是交易所当地时间（时间过滤也按当地时间）。
        start_time/end_time 格式 yyyy-MM-dd HH:mm:ss。limit 默认 6000、最大 10000；
        该接口无翻页，返回行数撞上 limit 时结果标 partial（raw 可见）并发 warning，
        提示缩小时间范围或分批取数。

        ⚠️ 服务端只保留近期的分钟数据，日期过旧会返回**空表且不报错**——查不到数据时
        先确认日期在保留窗口内（日 K 的历史区间比这长得多）。
        """
        _validate_limit(limit)
        if limit is None:
            limit = DEFAULT_QUOTE_LIMIT
        securities = _as_list(security) or []
        if not securities:
            raise ValidationError("security is required: pass one or more security codes")

        def make_body(code: Any) -> dict[str, Any]:
            return _request_body(
                {
                    "securityCode": code,
                    "startTime": start_time,
                    "endTime": end_time,
                    "limit": limit,
                    "fieldList": _as_list(field),
                }
            )

        if len(securities) > 1:

            async def fetch_part(code: Any) -> Any:
                return await self._client._call("quote.minute-kline", body=make_body(code))

            parts = await fetch_per_security_async(
                securities,
                fetch=fetch_part,
                label="quote minute-kline",
                concurrency=self._client.config.page_concurrency,
            )
            result_payload = merge_parts(
                parts, securities=securities, cap=limit, label="quote minute-kline"
            )
            _flag_missing_fields(result_payload, _as_list(field), "quote minute-kline")
            if raw:
                return result_payload
            rows, fields = _quote_rows_and_fields(result_payload)
            return to_dataframe(_normalize_quote_rows(rows, fields, result_payload), schema=None)

        result = await self._client._call("quote.minute-kline", body=make_body(securities[0]))
        warn_if_server_partial(result, "quote minute-kline")
        rows, fields = _quote_rows_and_fields(result)
        _flag_single_truncation(result, rows, limit, "minute-kline")
        _flag_missing_fields(result, _as_list(field), "quote minute-kline")
        if raw:
            return result  # type: ignore[no-any-return]
        return to_dataframe(_normalize_quote_rows(rows, fields, result), schema=None)

    async def realtime(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询实时行情快照（quote.realtime）：个股、沪深 ETF（如 512800.SH）、
        交易所/概念/行业指数，以及 20 个全球指数（如 SPX.SPI / N225.NKI / HSI.HI）。

        security 支持单值或列表，也可传市场关键词：
        aShares=全 A 股 / hkStocks=全港股 / usStocks=全美股——关键词**必须单独传**，
        与代码或另一个关键词混填服务端回 120001（提示指向代码本身，会把排查带偏），
        因此本地先拦。**关键词只覆盖个股**，ETF 与各类指数没有全市场关键词，要逐个传代码。

        字段：新增 tradeStatus（交易状态，仅 A 股 / 港股个股有值）；
        **turnoverRate / volumeRatio 不返回**——传了会连字段名一起被丢弃且不报错
        （SDK 会标 partial + missingFields 并 warn），换手率改走 EDE 指标 qte_turn。
        美股 amount 为 null；全球指数的 volume / amount / amplitude 均为 null，
        tradeDate / tradeTime 是交易所当地时间。
        """
        # Realtime takes the same keywords as day-kline but never shards (one
        # snapshot per security), so it only needs the alone-and-known check.
        check_market_keywords(security, REALTIME_MARKETS, "quote realtime")
        security = canonicalize_market_keywords(security, REALTIME_MARKETS)
        body = _request_body(
            {
                "securityList": _as_list(security),
                "fieldList": _as_list(field),
            }
        )
        result = await self._client._call("quote.realtime", body=body)
        warn_if_server_partial(result, "quote realtime")
        _flag_missing_fields(result, _as_list(field), "quote realtime")
        if raw:
            return result  # type: ignore[no-any-return]
        rows, fields = _quote_rows_and_fields(result)
        return to_dataframe(_normalize_quote_rows(rows, fields, result), schema=None)
