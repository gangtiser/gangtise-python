# ruff: noqa: RUF002
# (RUF002 disabled file-wide: method docstrings are user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

import datetime as dt
import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import GangtiseError, ValidationError
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
    pack_securities,
)
from gangtise_openapi._quote_sharding import (
    DEFAULT_FULL_MARKET_LIMIT,
    DEFAULT_QUOTE_LIMIT,
    MARKET_SHARD_DAYS,
    QUOTE_MAX_LIMIT,
    REALTIME_MARKETS,
    ShardFetch,
    canonicalize_market_keywords,
    check_market_keywords,
    column_remap,
    describe_error,
    extra_columns,
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
    _validate_datetime,
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
        and isinstance(rows, list)
        and all(isinstance(r, list) and len(r) == len(fields) for r in rows)
    ):
        # An empty ``list`` keeps its columns: a non-trading day must still give a frame
        # whose ``df["close"]`` exists (empty), not a column-less one that raises KeyError.
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


# The columns a row needs to be told apart when several securities share one result.
_DAILY_IDENTITY: tuple[str, ...] = ("securityCode", "tradeDate")
_MINUTE_IDENTITY: tuple[str, ...] = ("securityCode", "tradeTime")
_REALTIME_IDENTITY: tuple[str, ...] = ("securityCode",)

# Appended to the refusal of a keyword on an endpoint that takes none (TS v0.41.1).
_NO_KEYWORD_REASONS: dict[str, str] = {
    "quote.index-day-kline": (
        "the endpoint answers 'all' with total 0 and no error, indistinguishable from a "
        "day without data. List the index codes one by one — quote.day_kline takes the "
        "same codes; for index names call reference.securities_search(keyword=<index "
        'code>, category="index") and read gtsName. There is currently no way to fetch '
        "every SH/SZ/BJ index in one call"
    ),
}

# A first row this many calendar days after the requested start is not a weekend or a
# holiday (the longest market closure runs about nine days) — the series starts late.
_LATE_START_DAYS = 14
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}\Z", re.ASCII)


def _unique(values: list[Any] | None) -> list[Any] | None:
    """Drop repeated codes / field names, first occurrence kept (TS v0.44.0 ⑧).

    A code named twice means nothing more than once, and passing it on doubles every
    row of that security (``["600519.SH", "600519.SH"]``); a repeated field name
    misaligns columns. Exact comparison, like the CLI's ``collectList``.
    """
    return None if values is None else list(dict.fromkeys(values))


def _with_identity_fields(
    fields: list[Any] | None, identity: Sequence[str], label: str
) -> list[Any] | None:
    """``field`` plus the columns a row needs to be told apart (TS v0.43.0 ③).

    The quote endpoints return ONLY the requested columns (fund-flow excepted), so
    ``field="close"`` over several securities answers bare closes that cannot be tied
    to a security or a date — and their order differs between a single request (sorted
    by code) and a grouped merge (input order), so position does not help either. The
    missing ones are added IN FRONT, with a warning. Callers pass no identity for a
    single security: its rows cannot be mixed up with another's, and adding a date
    column would change what single-security scripts get.
    """
    if not fields:
        return fields
    have = {str(name) for name in fields}
    missing = [name for name in identity if name not in have]
    if not missing:
        return fields
    says = " and ".join(
        word
        for word, needed in (
            ("security", "securityCode" in missing),
            ("time", any(name != "securityCode" for name in missing)),
        )
        if needed
    )
    warnings.warn(
        f"{label} adds {', '.join(missing)} to field so each row says which {says} it "
        "belongs to (several securities share one result)",
        stacklevel=4,
    )
    return [*missing, *fields]


def _earliest_row_date(result: Any, field: str) -> str | None:
    """The earliest ``YYYY-MM-DD`` of ``field`` over all rows, columnar or object.
    Several securities merge one after another, so the first row is not the earliest."""
    if not isinstance(result, dict) or not isinstance(result.get("list"), list):
        return None
    fields = result.get("fieldList")
    index = fields.index(field) if isinstance(fields, list) and field in fields else -1
    earliest: str | None = None
    for row in result["list"]:
        if isinstance(row, list):
            value = row[index] if 0 <= index < len(row) else None
        elif isinstance(row, dict):
            value = row.get(field)
        else:
            continue
        if not isinstance(value, str):
            continue
        day = value[:10]
        if earliest is None or day < earliest:
            earliest = day
    return earliest


def _note_late_start(result: Any, requested_start: Any, field: str, label: str) -> None:
    """Warn when a quote series starts well after the requested start (TS v0.43.0 ⑥).

    The quote endpoints answer a range that reaches past the account's history window
    with what lies inside it and no error, so a clipped series otherwise looks like a
    complete one. A security that listed (or resumed trading) later reads the same,
    which is why this only warns and marks nothing partial. Stays quiet after a failed
    date shard: that alone can move the first row later, and its own warning names
    the gap.
    """
    if not isinstance(result, dict):
        return
    failed = result.get("failedShards")
    if isinstance(failed, list) and failed:
        return
    if not isinstance(requested_start, str) or not _ISO_DAY.match(requested_start[:10]):
        return
    start = requested_start[:10]
    first = _earliest_row_date(result, field)
    if first is None or not _ISO_DAY.match(first):
        return
    try:
        late = (dt.date.fromisoformat(first) - dt.date.fromisoformat(start)).days
    except ValueError:
        return
    if late <= _LATE_START_DAYS:
        return
    warnings.warn(
        f"{label} starts at {first}, {late} days after the requested start {start}. The "
        "security may have listed or resumed trading later, or the range reaches past "
        "your account's history window for this data — the endpoint returns what lies "
        "inside the window without an error.",
        stacklevel=4,
    )


def _note_empty_minutes(rows: list[Any], start_time: Any, end_time: Any) -> None:
    """Minute bars keep a far shorter history than daily bars, and a range entirely
    before it comes back as an empty SUCCESS, not the 110003 a daily range there gets
    (CLI probe 2026-09-25) — so an empty answer says nothing about whether trading
    happened (TS v0.43.0 ⑥)."""
    if rows or not (start_time or end_time):
        return
    warnings.warn(
        "quote minute-kline: no minute bars came back. Minute bars cover a much shorter "
        "history than daily bars, and a range entirely before it returns nothing rather "
        "than an error — try a recent range to check.",
        stacklevel=4,
    )


@dataclass(frozen=True)
class _KlinePlan:
    """Everything a daily-kline call decides before its first request (sync/async shared).

    Exactly one fetch mode applies: ``shards`` (a whole-market keyword, date-sharded),
    ``groups`` (several securities packed into requests that fit the row cap), or
    neither (one request).
    """

    label: str
    short: str
    securities: list[Any] | None
    fields: list[Any] | None
    start_date: str | None
    end_date: str | None
    limit: int
    shards: list[tuple[dt.date, dt.date]] | None
    groups: list[list[Any]] | None
    group_cap: int


def _plan_kline(
    endpoint_key: str,
    *,
    security: FilterValue,
    start_date: str | dt.date | None,
    end_date: str | dt.date | None,
    limit: int | None,
    field: FilterValue | None,
    identity: Sequence[str],
) -> _KlinePlan:
    """Validate a daily-kline call and plan its requests. Raises before any request."""
    _validate_limit(limit)
    # Normalize BEFORE the shard planner or the per-security estimate read these
    # (see `_date_to_iso`): both parse ISO only, and a legal `2016/01/01` used to
    # make the estimate silently skip the split.
    start = _date_to_iso(start_date, "startDate")
    end = _date_to_iso(end_date, "endDate")
    markets = MARKET_SHARD_DAYS[endpoint_key]
    short = endpoint_key.split(".", 1)[-1]
    label = f"quote {short}"
    securities = _unique(_as_list(security, "security"))
    # Validate before anything is sent: a keyword this endpoint does not take,
    # or one mixed with codes, is a local error — and these endpoints answer it
    # in the most misleading way (a 120001 pointing at codes that are fine, on
    # fund-flow no error at all, on index-day-kline an empty success).
    check_market_keywords(
        securities,
        tuple(markets),
        label,
        no_keyword_reason=_NO_KEYWORD_REASONS.get(endpoint_key),
    )
    securities = canonicalize_market_keywords(securities, tuple(markets))
    keyword = resolve_full_market(securities, markets)
    if keyword is not None and not (start and end):
        # A whole-market keyword is date-sharded, and the server answers an unbounded
        # whole-market request with 100003 查询规模过大 rather than a truncated page
        # (CLI probe 2026-09-25) — so the range is required up front (TS v0.43.0 ⑤).
        raise ValidationError(
            f"{label} full-market ({keyword!r}) requires both start_date and end_date "
            "(the full market is fetched via date shards; an unbounded whole-market "
            "request is rejected by the server)"
        )
    codes = securities or []
    several = len(codes) > 1 or keyword is not None
    fields = _with_identity_fields(
        _unique(_as_list(field, "field")), identity if several else (), label
    )
    if keyword is not None:
        assert start is not None and end is not None
        # Full-market lifts the per-request cap to the API max.
        return _KlinePlan(
            label=label,
            short=short,
            securities=securities,
            fields=fields,
            start_date=start,
            end_date=end,
            limit=limit if limit is not None else DEFAULT_FULL_MARKET_LIMIT,
            shards=plan_shards(
                start_date=_parse_date(start),
                end_date=_parse_date(end),
                weekdays_per_shard=markets[keyword],
            ),
            groups=None,
            group_cap=0,
        )
    # Explicit securities pin to the default so the sent limit and the truncation cap
    # are the same number.
    sent_limit = limit if limit is not None else DEFAULT_QUOTE_LIMIT
    groups: list[list[Any]] | None = None
    cap = sent_limit
    trading_days = estimate_trading_days(start, end)
    # Several securities over a range that would not fit one request go out in groups,
    # each packed to fit one request, merged in input order (TS v0.43.0 ④). One request
    # would come back capped at `limit` with the TAIL SECURITIES MISSING ENTIRELY — the
    # rows are filled in order, so truncation eats whole securities. `>=`: a request
    # planned exactly onto its cap would read as truncated. Without `limit` a group uses
    # the endpoint's row ceiling; with it, every request keeps the limit given.
    if len(codes) > 1 and len(codes) * trading_days >= sent_limit:
        cap = limit if limit is not None else QUOTE_MAX_LIMIT
        groups = pack_securities(codes, trading_days=trading_days, cap=cap)
    return _KlinePlan(
        label=label,
        short=short,
        securities=securities,
        fields=fields,
        start_date=start,
        end_date=end,
        limit=sent_limit,
        shards=None,
        groups=groups,
        group_cap=cap,
    )


def _kline_body(
    plan: _KlinePlan, securities: list[Any] | None, start: Any, end: Any, limit: int
) -> dict[str, Any]:
    return _request_body(
        {
            "securityList": securities,
            "startDate": start,
            "endDate": end,
            "limit": limit,
            "fieldList": plan.fields,
        }
    )


def _finish_kline(
    result_payload: dict[str, Any], plan: _KlinePlan, raw: bool
) -> pd.DataFrame | dict[str, Any]:
    """Flag missing columns, note a late start, and render. Shared sync/async."""
    _flag_missing_fields(result_payload, plan.fields, plan.label)
    _note_late_start(result_payload, plan.start_date, "tradeDate", plan.label)
    if raw:
        return result_payload
    return _kline_dataframe(result_payload["list"], result_payload.get("fieldList"), result_payload)


def _finalize_sharded(
    fetched: ShardFetch, plan: _KlinePlan, raw: bool
) -> pd.DataFrame | dict[str, Any]:
    assert plan.shards is not None
    result_payload, _rows = _finalize_quote_result(
        fetched.results,
        label=plan.short,
        limit=plan.limit,
        sharded=True,
        shard_count=len(plan.shards),
        failed_shards=fetched.failed,
        shards=plan.shards,
        out_of_window=fetched.out_of_window,
        first_error=fetched.first_error,
        unsent=fetched.unsent,
        window_error=fetched.window_error,
    )
    return _finish_kline(result_payload, plan, raw)


def _finalize_single(result: Any, plan: _KlinePlan, raw: bool) -> pd.DataFrame | dict[str, Any]:
    result_payload, _rows = _finalize_quote_result(
        [result],
        label=plan.short,
        limit=plan.limit,
        sharded=False,
        shard_count=0,
        failed_shards=[],
    )
    return _finish_kline(result_payload, plan, raw)


def _finish_minutes(
    result: Any, fields: list[Any] | None, start_time: Any, end_time: Any, raw: bool
) -> pd.DataFrame | dict[str, Any] | list[Any]:
    """Flag missing columns, note a late or empty minute series, render. Sync/async shared."""
    _flag_missing_fields(result, fields, "quote minute-kline")
    _note_late_start(result, start_time, "tradeTime", "quote minute-kline")
    rows, row_fields = _quote_rows_and_fields(result)
    _note_empty_minutes(rows, start_time, end_time)
    if raw:
        return result  # type: ignore[no-any-return]
    return _kline_dataframe(rows, row_fields, result)


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
    out_of_window: Sequence[tuple[dt.date, dt.date]] = (),
    first_error: BaseException | None = None,
    unsent: int = 0,
    window_error: BaseException | None = None,
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

    Also on the sharded path: a column only a LATER shard returned has no slot in the
    merged header and is lost — named in ``droppedColumns`` + ``partial`` (TS v0.39.0);
    ``out_of_window`` shards (``110003``, wholly before the account's history window)
    are listed in ``outOfWindowShards`` with a warning but do NOT make the result partial
    (TS v0.44.0); the failure warning names ``first_error`` and counts the ``unsent``
    shards apart from the ones that failed.
    """
    merged: dict[str, Any] = {}
    header_taken = False
    fallback: dict[str, Any] | None = None
    field_list: Any = None
    # Insertion-ordered set of the object rows' keys — the returned columns when no
    # columnar header exists. Collected only while there is no header to collect.
    object_keys: dict[str, None] = {}
    rows: list[Any] = []
    malformed = 0
    truncated = 0
    partial_shards = 0
    truncated_windows: list[tuple[dt.date, dt.date]] = []
    # Insertion-ordered set of columns only later shards returned (see extra_columns).
    dropped_columns: dict[str, None] = {}

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
                if fallback is None:
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
                dropped_columns.update(dict.fromkeys(extra_columns(field_list, shard_fields or [])))
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
            if not header_taken:
                # Metadata from the FIRST shard that contributed rows (TS: ``if (!header)
                # header = rec``) — a later shard's must not overwrite it, even when the
                # first one carried no metadata at all.
                header_taken = True
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

    # Decided by WHETHER a shard contributed, not by whether it carried metadata: a
    # contributing shard with nothing but list + fieldList still outranks an empty one.
    base = merged if header_taken else (fallback or {})
    result_payload: dict[str, Any] = {**base, "list": rows} if base else {"list": rows}
    # Rebuilding the dict drops the envelope traceId the transport attached, which
    # is precisely what a downstream shape refusal needs (see `zip_field_row`).
    # Carried only for a SINGLE source payload: merging shards means merging N
    # responses with N different traceIds, and there is no honest way to pick one.
    if len(page_results) == 1:
        result_payload = _attach_envelope_trace_id(
            result_payload, getattr(page_results[0], "envelope_trace_id", None)
        )
    if sharded and shard_count and len(failed_shards) + len(out_of_window) >= shard_count:
        # Every shard failed or lay outside the history window, counting the ones only
        # the merge could judge (claimed rows but delivered none, unreadable columns):
        # an error, not an empty "partial" success — the fetch stage raises the same way
        # when the failures are visible there (TS judges after its merge too).
        if first_error is not None:
            raise first_error
        if window_error is not None:
            raise window_error
        raise GangtiseError(f"All {shard_count} {label} shards failed (see the warnings above)")
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
    if sharded and shard_count:
        # A shard's own `total` is just that shard's row count; overwrite it with the
        # merged count so `total` reflects the whole combined result. Skipped only when
        # nothing was sent (an all-weekend range → zero shards), so that result stays a
        # bare {"list": []} — TS parity (`if (shards.length === 0) return {list: []}`).
        result_payload["total"] = len(rows)
    if partial_shards:
        result_payload["partial"] = True
        warnings.warn(
            f"{partial_shards}/{shard_count} {label} shard(s) reported themselves partial; "
            "the merged result is marked partial",
            stacklevel=3,
        )
    if out_of_window:
        # Not partial: the account cannot query these dates, which a retry would not
        # change. Listed so a consumer knows which dates are not in the result.
        skipped = sorted(out_of_window)
        result_payload["outOfWindowShards"] = [
            {"startDate": s.isoformat(), "endDate": e.isoformat()} for s, e in skipped
        ]
        warnings.warn(
            f"{len(skipped)}/{shard_count} {label} shard(s) between "
            f"{skipped[0][0].isoformat()} and {skipped[-1][1].isoformat()} lie outside your "
            "account's history window (110003) and were skipped; the result covers the rest "
            "of the range (see outOfWindowShards in raw output)",
            stacklevel=3,
        )
    if failed_shards:
        result_payload["partial"] = True
        result_payload["failedShards"] = [
            {"startDate": s.isoformat(), "endDate": e.isoformat()} for s, e in sorted(failed_shards)
        ]
        not_sent = (
            f" ({unsent} of them not sent: the first error stopped the rest)" if unsent else ""
        )
        cause = f"; first error: {describe_error(first_error)}" if first_error else ""
        warnings.warn(
            f"{len(failed_shards)}/{shard_count} {label} shards failed{not_sent}{cause}; "
            "results are partial (see failedShards in raw output)",
            stacklevel=3,
        )
    if dropped_columns:
        result_payload["partial"] = True
        result_payload["droppedColumns"] = list(dropped_columns)
        warnings.warn(
            f"{label}: {len(dropped_columns)} column(s) came back only in later shards and "
            "could not be carried (see droppedColumns in raw output); the merged fieldList "
            "is the first data shard's — re-pull a narrower range to get them",
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
        identity: Sequence[str] = _DAILY_IDENTITY,
    ) -> pd.DataFrame | dict[str, Any]:
        plan = _plan_kline(
            endpoint_key,
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            identity=identity,
        )
        concurrency = self._client.config.page_concurrency
        if plan.groups is not None:
            parts = fetch_per_security(
                plan.groups,
                fetch=lambda codes: self._client._call(
                    endpoint_key,
                    body=_kline_body(plan, codes, plan.start_date, plan.end_date, plan.group_cap),
                ),
                label=plan.label,
                concurrency=concurrency,
            )
            merged = merge_parts(
                parts, securities=plan.groups, cap=plan.group_cap, label=plan.label
            )
            return _finish_kline(merged, plan, raw)
        if plan.shards is not None:
            # An all-weekend range plans zero shards -> zero requests and an empty
            # result via the merge path.
            fetched = fetch_shards(
                plan.shards,
                fetch=lambda w: self._client._call(
                    endpoint_key,
                    body=_kline_body(
                        plan, plan.securities, w[0].isoformat(), w[1].isoformat(), plan.limit
                    ),
                ),
                concurrency=concurrency,
            )
            return _finalize_sharded(fetched, plan, raw)
        result = self._client._call(
            endpoint_key,
            body=_kline_body(plan, plan.securities, plan.start_date, plan.end_date, plan.limit),
        )
        return _finalize_single(result, plan, raw)

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
        全市场关键词**必须同时传 start_date 与 end_date**（缺一个本地抛 ValidationError、
        不发请求——不分片的全市场请求会被服务端以「查询规模过大」拒绝）。按工作日自动
        分片并发拉取（aShares / usStocks 每片 1 个工作日、hkStocks 每片 2 个工作日，周末
        不单独发请求）；部分分片失败时结果带 partial/failedShards 并发 warning（写明首个
        错误码，并分开计数「失败」与「因此未发送」）。区间起点早于账号可回溯窗口时，
        窗口外的分片（110003）跳过、不影响其余分片，跳过的区间列在 outOfWindowShards
        并发 warning（不算 partial；整段都在窗口外时仍抛 110003）。
        limit 默认 6000，最大 10000；全市场未传 limit 时每片按 10000。

        多只证券且「证券数 × 区间工作日数」达到 limit 时，按行数上限把尽量多的证券装进
        一个请求（未传 limit 时按 10000 算），组内按传入顺序合并——一次请求装不下时
        服务端按行截断，尾部证券会**整只消失**。每组都规划在上限以下，完整的一组不会因
        行数恰好等于上限被判截断；单只证券的行数达到 limit 时仍标 partial +
        truncatedSecurities。security 里的重复代码自动去掉（否则每行输出两遍）。

        field 只返回点名的列：多只证券或全市场关键词时自动在最前补上 securityCode /
        tradeDate（缺哪个补哪个）并发 warning；单只证券按点名的列原样返回。

        区间跨过账号回溯下界时接口从下界起返回、不报错：首行比 start_date 晚 14 天以上
        时发 warning（也可能只是上市或复牌较晚），不标 partial。

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
        并支持与其他市场混传，且会校验代码（本接口传错代码返回空结果、不报错，与「该区间
        无数据」无法区分）。接口本身仍可调用，且保留 "all" 全市场关键词。

        security 支持单值或列表（重复代码自动去掉），"all"=全市场——必须同时传
        start_date 与 end_date（缺一个本地抛 ValidationError、不发请求），按工作日自动
        分片并发拉取（每片 2 个工作日，周末不单独发请求）；分片失败与窗口外分片
        （110003）的处理、多只证券按行数上限合批、field 自动补 securityCode / tradeDate、
        首行晚到 warning 均同 day_kline。limit 默认 6000，最大 10000。
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
        并支持与其他市场混传，且会校验代码（本接口传错代码返回空结果、不报错，与「该区间
        无数据」无法区分）。接口本身仍可调用，且保留 "all" 全市场关键词。

        security 支持单值或列表（重复代码自动去掉），"all"=全市场——必须同时传
        start_date 与 end_date（缺一个本地抛 ValidationError、不发请求），按工作日自动
        分片并发拉取（每片 1 个工作日，周末不单独发请求）；分片失败与窗口外分片
        （110003）的处理、多只证券按行数上限合批、field 自动补 securityCode / tradeDate、
        首行晚到 warning 均同 day_kline。limit 默认 6000，最大 10000。
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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，新代码直接用 day_kline() 传同样的
        指数代码——本接口没有 day_kline 做不到的能力。返回字段与 day_kline 相同
        （securityCode / tradeDate / open / high / low / close / preClose / change /
        pctChange / volume / amount / adjustFactor，指数的 adjustFactor 恒为 null），
        **不含指数名称**；要名称用 reference.securities_search(keyword=<指数代码>,
        category="index")，返回的 gtsName 即名称（如「上证指数」）。

        security 传沪深京指数代码（如 000001.SH / 399001.SZ），单值或列表（重复代码自动
        去掉）。**没有全市场关键词**：接口对 "all" 返回 total 0 的空结果、不报错，与
        「当天无数据」无法区分，所以 "all"（及其他市场关键词）在发请求前就抛
        ValidationError。**全部沪深京指数目前没有一次拿全的写法**，要逐个传代码。
        多只证券按行数上限合批、field 自动补 securityCode / tradeDate、首行晚到 warning
        均同 day_kline。limit 默认 6000，最大 10000。
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
        security 传具体代码（单值或列表，重复代码自动去掉；如 600519.SH / 872931.BJ），
        或 "aShares" 拉全 A 股——全市场按工作日自动分片（每片 1 个工作日）并发合并，
        须同时传 start_date/end_date（缺日期本地报错）；分片失败与窗口外分片（110003）
        的处理同 day_kline。多只代码且「证券数 × 工作日数」达到 limit 时，SDK 同样按
        行数上限分组请求、按传入顺序合并。securityCode / tradeDate 由服务端自动附带，
        field 不会另补。单只证券无翻页，返回行数撞上 limit（默认 6000、最大 10000）
        时结果标 partial（raw 可见）并发 warning。首行比 start_date 晚 14 天以上时
        发 warning（上市较晚，或区间越过了账号的回溯窗口）。
        """
        return self._day_kline(
            "quote.fund-flow",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
            identity=(),
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
        接口本身一次只收一只，传列表时 SDK 逐只并发请求、按传入顺序合并（重复代码
        自动去掉）；各只的列布局必须一致，某只填满 limit 会标 partial + truncatedSecurities。
        多只证券时 field 自动在最前补上 securityCode / tradeTime 并发 warning；单只不补。
        全球指数的 volume / amount 为 null，tradeTime 是交易所当地时间（时间过滤也按当地时间）。
        start_time/end_time 格式 yyyy-MM-dd HH:mm:ss。limit 默认 6000、最大 10000；
        该接口无翻页，返回行数撞上 limit 时结果标 partial（raw 可见）并发 warning，
        提示缩小时间范围或分批取数。

        ⚠️ 分钟数据的历史窗口比日 K 短得多，且随日期滚动（2026-09-25 实测某账号约 29 个
        交易日）：整段在窗口外返回**空表且不报错**（日 K 同样情况报 110003），
        SDK 在整段为空时发 warning；跨过窗口时从窗内起返回，首行比 start_time 晚 14 天
        以上时发 warning。

        🔴 分钟加总不等于日线，别把它当校验条件：正常交易日 241 根，多数日子 Σ分钟
        volume 与日线相等、amount 只差浮点尾差；但个别历史交易日的分钟数据与日线口径
        不一致，那几天怎么加都对不上，两条序列各自稳定、都不报错、历史也不回改。
        成交量 / 成交额统计一律以日线为准，不要用分钟加总反推或「修正」日线。
        """
        _validate_limit(limit)
        if limit is None:
            limit = DEFAULT_QUOTE_LIMIT
        securities = _unique(_as_list(security, "security")) or []
        if not securities:
            raise ValidationError("security is required: pass one or more security codes")
        # Normalized up front (and so validated before any request): the late-start
        # note reads its date half.
        if start_time is not None:
            start_time = _validate_datetime(start_time, "startTime")
        fields = _with_identity_fields(
            _unique(_as_list(field, "field")),
            _MINUTE_IDENTITY if len(securities) > 1 else (),
            "quote minute-kline",
        )

        def make_body(code: Any) -> dict[str, Any]:
            return _request_body(
                {
                    "securityCode": code,
                    "startTime": start_time,
                    "endTime": end_time,
                    "limit": limit,
                    "fieldList": fields,
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
            return _finish_minutes(result_payload, fields, start_time, end_time, raw)

        result = self._client._call("quote.minute-kline", body=make_body(securities[0]))
        warn_if_server_partial(result, "quote minute-kline")
        rows, _fields = _quote_rows_and_fields(result)
        _flag_single_truncation(result, rows, limit, "minute-kline")
        return _finish_minutes(result, fields, start_time, end_time, raw)

    def realtime(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询实时行情快照（quote.realtime）：个股、沪深 ETF（如 512800.SH）、
        交易所/概念/行业指数，以及 20 个全球指数（如 SPX.SPI / N225.NKI / HSI.HI）。

        security 支持单值或列表（重复代码自动去掉），也可传市场关键词：
        aShares=全 A 股 / hkStocks=全港股 / usStocks=全美股——关键词**必须单独传**，
        与代码或另一个关键词混填服务端回 120001（提示指向代码本身，会把排查带偏），
        因此本地先拦。**关键词只覆盖个股**，ETF 与各类指数没有全市场关键词，要逐个传代码。
        多只证券或市场关键词时 field 自动在最前补上 securityCode 并发 warning；单只不补。

        字段：新增 tradeStatus（交易状态，仅 A 股 / 港股个股有值）；
        **turnoverRate / volumeRatio 不返回**——传了会连字段名一起被丢弃且不报错
        （SDK 会标 partial + missingFields 并 warn），换手率改走 EDE 指标 qte_turn。
        美股 amount 为 null；全球指数的 volume / amount / amplitude 均为 null，
        tradeDate / tradeTime 是交易所当地时间。
        """
        # Realtime takes the same keywords as day-kline but never shards (one
        # snapshot per security), so it only needs the alone-and-known check.
        securities = _unique(_as_list(security, "security"))
        check_market_keywords(securities, REALTIME_MARKETS, "quote realtime")
        securities = canonicalize_market_keywords(securities, REALTIME_MARKETS)
        codes = securities or []
        several = len(codes) > 1 or any(code in REALTIME_MARKETS for code in codes)
        fields = _with_identity_fields(
            _unique(_as_list(field, "field")),
            _REALTIME_IDENTITY if several else (),
            "quote realtime",
        )
        body = _request_body({"securityList": securities, "fieldList": fields})
        result = self._client._call("quote.realtime", body=body)
        warn_if_server_partial(result, "quote realtime")
        _flag_missing_fields(result, fields, "quote realtime")
        if raw:
            return result  # type: ignore[no-any-return]
        rows, row_fields = _quote_rows_and_fields(result)
        return _kline_dataframe(rows, row_fields, result)


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
        identity: Sequence[str] = _DAILY_IDENTITY,
    ) -> pd.DataFrame | dict[str, Any]:
        plan = _plan_kline(
            endpoint_key,
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            identity=identity,
        )
        concurrency = self._client.config.page_concurrency
        if plan.groups is not None:

            async def fetch_group(codes: list[Any]) -> Any:
                return await self._client._call(
                    endpoint_key,
                    body=_kline_body(plan, codes, plan.start_date, plan.end_date, plan.group_cap),
                )

            parts = await fetch_per_security_async(
                plan.groups, fetch=fetch_group, label=plan.label, concurrency=concurrency
            )
            merged = merge_parts(
                parts, securities=plan.groups, cap=plan.group_cap, label=plan.label
            )
            return _finish_kline(merged, plan, raw)
        if plan.shards is not None:

            async def fetch_shard(window: tuple[dt.date, dt.date]) -> Any:
                return await self._client._call(
                    endpoint_key,
                    body=_kline_body(
                        plan,
                        plan.securities,
                        window[0].isoformat(),
                        window[1].isoformat(),
                        plan.limit,
                    ),
                )

            # An all-weekend range plans zero shards -> zero requests and an empty
            # result via the merge path.
            fetched = await fetch_shards_async(
                plan.shards, fetch=fetch_shard, concurrency=concurrency
            )
            return _finalize_sharded(fetched, plan, raw)
        result = await self._client._call(
            endpoint_key,
            body=_kline_body(plan, plan.securities, plan.start_date, plan.end_date, plan.limit),
        )
        return _finalize_single(result, plan, raw)

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
        全市场关键词**必须同时传 start_date 与 end_date**（缺一个本地抛 ValidationError、
        不发请求——不分片的全市场请求会被服务端以「查询规模过大」拒绝）。按工作日自动
        分片并发拉取（aShares / usStocks 每片 1 个工作日、hkStocks 每片 2 个工作日，周末
        不单独发请求）；部分分片失败时结果带 partial/failedShards 并发 warning（写明首个
        错误码，并分开计数「失败」与「因此未发送」）。区间起点早于账号可回溯窗口时，
        窗口外的分片（110003）跳过、不影响其余分片，跳过的区间列在 outOfWindowShards
        并发 warning（不算 partial；整段都在窗口外时仍抛 110003）。
        limit 默认 6000，最大 10000；全市场未传 limit 时每片按 10000。

        多只证券且「证券数 × 区间工作日数」达到 limit 时，按行数上限把尽量多的证券装进
        一个请求（未传 limit 时按 10000 算），组内按传入顺序合并——一次请求装不下时
        服务端按行截断，尾部证券会**整只消失**。每组都规划在上限以下，完整的一组不会因
        行数恰好等于上限被判截断；单只证券的行数达到 limit 时仍标 partial +
        truncatedSecurities。security 里的重复代码自动去掉（否则每行输出两遍）。

        field 只返回点名的列：多只证券或全市场关键词时自动在最前补上 securityCode /
        tradeDate（缺哪个补哪个）并发 warning；单只证券按点名的列原样返回。

        区间跨过账号回溯下界时接口从下界起返回、不报错：首行比 start_date 晚 14 天以上
        时发 warning（也可能只是上市或复牌较晚），不标 partial。

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
        并支持与其他市场混传，且会校验代码（本接口传错代码返回空结果、不报错，与「该区间
        无数据」无法区分）。接口本身仍可调用，且保留 "all" 全市场关键词。

        security 支持单值或列表（重复代码自动去掉），"all"=全市场——必须同时传
        start_date 与 end_date（缺一个本地抛 ValidationError、不发请求），按工作日自动
        分片并发拉取（每片 2 个工作日，周末不单独发请求）；分片失败与窗口外分片
        （110003）的处理、多只证券按行数上限合批、field 自动补 securityCode / tradeDate、
        首行晚到 warning 均同 day_kline。limit 默认 6000，最大 10000。
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
        并支持与其他市场混传，且会校验代码（本接口传错代码返回空结果、不报错，与「该区间
        无数据」无法区分）。接口本身仍可调用，且保留 "all" 全市场关键词。

        security 支持单值或列表（重复代码自动去掉），"all"=全市场——必须同时传
        start_date 与 end_date（缺一个本地抛 ValidationError、不发请求），按工作日自动
        分片并发拉取（每片 1 个工作日，周末不单独发请求）；分片失败与窗口外分片
        （110003）的处理、多只证券按行数上限合批、field 自动补 securityCode / tradeDate、
        首行晚到 warning 均同 day_kline。limit 默认 6000，最大 10000。
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

        ⚠️ **已下线（deprecated）**：官方菜单已移除，新代码直接用 day_kline() 传同样的
        指数代码——本接口没有 day_kline 做不到的能力。返回字段与 day_kline 相同
        （securityCode / tradeDate / open / high / low / close / preClose / change /
        pctChange / volume / amount / adjustFactor，指数的 adjustFactor 恒为 null），
        **不含指数名称**；要名称用 reference.securities_search(keyword=<指数代码>,
        category="index")，返回的 gtsName 即名称（如「上证指数」）。

        security 传沪深京指数代码（如 000001.SH / 399001.SZ），单值或列表（重复代码自动
        去掉）。**没有全市场关键词**：接口对 "all" 返回 total 0 的空结果、不报错，与
        「当天无数据」无法区分，所以 "all"（及其他市场关键词）在发请求前就抛
        ValidationError。**全部沪深京指数目前没有一次拿全的写法**，要逐个传代码。
        多只证券按行数上限合批、field 自动补 securityCode / tradeDate、首行晚到 warning
        均同 day_kline。limit 默认 6000，最大 10000。
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
        security 传具体代码（单值或列表，重复代码自动去掉；如 600519.SH / 872931.BJ），
        或 "aShares" 拉全 A 股——全市场按工作日自动分片（每片 1 个工作日）并发合并，
        须同时传 start_date/end_date（缺日期本地报错）；分片失败与窗口外分片（110003）
        的处理同 day_kline。多只代码且「证券数 × 工作日数」达到 limit 时，SDK 同样按
        行数上限分组请求、按传入顺序合并。securityCode / tradeDate 由服务端自动附带，
        field 不会另补。单只证券无翻页，返回行数撞上 limit（默认 6000、最大 10000）
        时结果标 partial（raw 可见）并发 warning。首行比 start_date 晚 14 天以上时
        发 warning（上市较晚，或区间越过了账号的回溯窗口）。
        """
        return await self._day_kline(
            "quote.fund-flow",
            security=security,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            field=field,
            raw=raw,
            identity=(),
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
        接口本身一次只收一只，传列表时 SDK 逐只并发请求、按传入顺序合并（重复代码
        自动去掉）；各只的列布局必须一致，某只填满 limit 会标 partial + truncatedSecurities。
        多只证券时 field 自动在最前补上 securityCode / tradeTime 并发 warning；单只不补。
        全球指数的 volume / amount 为 null，tradeTime 是交易所当地时间（时间过滤也按当地时间）。
        start_time/end_time 格式 yyyy-MM-dd HH:mm:ss。limit 默认 6000、最大 10000；
        该接口无翻页，返回行数撞上 limit 时结果标 partial（raw 可见）并发 warning，
        提示缩小时间范围或分批取数。

        ⚠️ 分钟数据的历史窗口比日 K 短得多，且随日期滚动（2026-09-25 实测某账号约 29 个
        交易日）：整段在窗口外返回**空表且不报错**（日 K 同样情况报 110003），
        SDK 在整段为空时发 warning；跨过窗口时从窗内起返回，首行比 start_time 晚 14 天
        以上时发 warning。

        🔴 分钟加总不等于日线，别把它当校验条件：正常交易日 241 根，多数日子 Σ分钟
        volume 与日线相等、amount 只差浮点尾差；但个别历史交易日的分钟数据与日线口径
        不一致，那几天怎么加都对不上，两条序列各自稳定、都不报错、历史也不回改。
        成交量 / 成交额统计一律以日线为准，不要用分钟加总反推或「修正」日线。
        """
        _validate_limit(limit)
        if limit is None:
            limit = DEFAULT_QUOTE_LIMIT
        securities = _unique(_as_list(security, "security")) or []
        if not securities:
            raise ValidationError("security is required: pass one or more security codes")
        # Normalized up front (and so validated before any request): the late-start
        # note reads its date half.
        if start_time is not None:
            start_time = _validate_datetime(start_time, "startTime")
        fields = _with_identity_fields(
            _unique(_as_list(field, "field")),
            _MINUTE_IDENTITY if len(securities) > 1 else (),
            "quote minute-kline",
        )

        def make_body(code: Any) -> dict[str, Any]:
            return _request_body(
                {
                    "securityCode": code,
                    "startTime": start_time,
                    "endTime": end_time,
                    "limit": limit,
                    "fieldList": fields,
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
            return _finish_minutes(result_payload, fields, start_time, end_time, raw)

        result = await self._client._call("quote.minute-kline", body=make_body(securities[0]))
        warn_if_server_partial(result, "quote minute-kline")
        rows, _fields = _quote_rows_and_fields(result)
        _flag_single_truncation(result, rows, limit, "minute-kline")
        return _finish_minutes(result, fields, start_time, end_time, raw)

    async def realtime(
        self,
        *,
        security: FilterValue,
        field: FilterValue | None = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        """查询实时行情快照（quote.realtime）：个股、沪深 ETF（如 512800.SH）、
        交易所/概念/行业指数，以及 20 个全球指数（如 SPX.SPI / N225.NKI / HSI.HI）。

        security 支持单值或列表（重复代码自动去掉），也可传市场关键词：
        aShares=全 A 股 / hkStocks=全港股 / usStocks=全美股——关键词**必须单独传**，
        与代码或另一个关键词混填服务端回 120001（提示指向代码本身，会把排查带偏），
        因此本地先拦。**关键词只覆盖个股**，ETF 与各类指数没有全市场关键词，要逐个传代码。
        多只证券或市场关键词时 field 自动在最前补上 securityCode 并发 warning；单只不补。

        字段：新增 tradeStatus（交易状态，仅 A 股 / 港股个股有值）；
        **turnoverRate / volumeRatio 不返回**——传了会连字段名一起被丢弃且不报错
        （SDK 会标 partial + missingFields 并 warn），换手率改走 EDE 指标 qte_turn。
        美股 amount 为 null；全球指数的 volume / amount / amplitude 均为 null，
        tradeDate / tradeTime 是交易所当地时间。
        """
        # Realtime takes the same keywords as day-kline but never shards (one
        # snapshot per security), so it only needs the alone-and-known check.
        securities = _unique(_as_list(security, "security"))
        check_market_keywords(securities, REALTIME_MARKETS, "quote realtime")
        securities = canonicalize_market_keywords(securities, REALTIME_MARKETS)
        codes = securities or []
        several = len(codes) > 1 or any(code in REALTIME_MARKETS for code in codes)
        fields = _with_identity_fields(
            _unique(_as_list(field, "field")),
            _REALTIME_IDENTITY if several else (),
            "quote realtime",
        )
        body = _request_body({"securityList": securities, "fieldList": fields})
        result = await self._client._call("quote.realtime", body=body)
        warn_if_server_partial(result, "quote realtime")
        _flag_missing_fields(result, fields, "quote realtime")
        if raw:
            return result  # type: ignore[no-any-return]
        rows, row_fields = _quote_rows_and_fields(result)
        return _kline_dataframe(rows, row_fields, result)
