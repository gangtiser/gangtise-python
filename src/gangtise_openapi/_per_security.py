"""Fan a quote query out one request per security and merge the parts in order.

Used where the API takes a single security per request (``quote.minute-kline``),
and where one request naming N securities would blow past the per-request row cap
(``quote.day-kline`` over a long range). Ported from the TS CLI's
``core/perSecurity.ts`` (v0.38.0).

The contract deliberately differs from the date sharder in ``_quote_sharding``:
there a bad window is dropped and recorded in ``failedShards`` because the
surviving windows are still useful, whereas here the CALLER NAMED every security,
so one silently missing from the output is exactly the gap that has to surface.
Errors propagate and a structurally broken part fails the whole call.
"""

from __future__ import annotations

import datetime as dt
import threading
import warnings
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

from gangtise_openapi._errors import ApiError
from gangtise_openapi._normalize import columnar_schema_valid
from gangtise_openapi._pagination import first_leaf_exception

# The server's default window when no start date is given: one year ≈ 262 weekdays.
_DEFAULT_WINDOW_DAYS = 262
# What an UNREADABLE range estimates to. Deliberately larger than any per-request row
# cap (10000) divided by one security, so an unreadable range always splits: the two
# failure directions are not symmetric — over-estimating costs one extra request,
# under-estimating silently truncates the tail securities out of the result.
_UNREADABLE_RANGE_DAYS = 10_001


def estimate_trading_days(start_date: Any, end_date: Any) -> int:
    """Upper bound on trading days per security in a date range.

    The exact weekday count: holidays only ever REMOVE days, so this never
    under-estimates — and an under-estimate is the costly direction, sending one
    request where two were needed and getting a capped answer back. The server
    fills a missing end with the latest trading day, so only a missing start
    matters; without one it applies its own one-year window whatever the end is.

    🔴 **Pass NORMALIZED dates** (``YYYY-MM-DD`` or a ``date``). ``date.fromisoformat``
    rejects the other two layouts this SDK accepts — ``2016/01/01`` on every version,
    and ``20160101`` before Python 3.11 — and this used to answer such a range with
    the one-year default: a legal ten-year request for three securities then estimated
    786 rows instead of 7830, skipped the split, and came back capped with the tail
    securities missing. The callers normalize first (``_date_to_iso``); the unreadable
    branch below is a backstop, and it now errs toward splitting rather than toward
    that silent truncation.
    """
    if not start_date:
        return _DEFAULT_WINDOW_DAYS
    try:
        start = _as_date(start_date)
        end = _as_date(end_date) if end_date else dt.date.today() + dt.timedelta(days=1)
    except (TypeError, ValueError):
        return _UNREADABLE_RANGE_DAYS
    if end < start:
        # The server rejects an inverted range, so one request is the cheaper way to
        # surface that than N identical failures.
        return _DEFAULT_WINDOW_DAYS
    # Whole weeks contribute 5 weekdays each; the remainder is counted directly.
    span = (end - start).days + 1
    weeks, rest = divmod(span, 7)
    days = weeks * 5
    for offset in range(rest):
        if (start + dt.timedelta(days=weeks * 7 + offset)).weekday() < 5:
            days += 1
    return days


def _as_date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _structural(message: str, details: Any) -> ApiError:
    error = ApiError(message, details=details)
    error.structural = True
    return error


def check_part(part: Any, security: Any, label: str) -> None:
    """Reject a part that cannot be merged, before any cross-part comparison.

    Self-contained checks only (they need nothing from the other parts), so the
    fan-out can run them as each answer lands and stop dispatching the rest:

    * **No ``list``** — the layout changed; ``expects="list"`` catches this at the
      transport for the quote endpoints, so reaching here means a caller wired the
      helper to an endpoint without that marker.
    * **Empty but claiming rows** (``total > 0``, or an explicit ``partial``) — a
      contradiction, not a quiet window. The caller named this security; its rows
      going missing is precisely what has to be surfaced.
    * **Array rows with no usable ``fieldList``** (missing, duplicated, mis-sized)
      — they cannot be read by position, whatever order the parts arrived in.
    """
    if not (isinstance(part, dict) and isinstance(part.get("list"), list)):
        raise _structural(
            f"{label}: {security} returned no list payload — the response layout may have changed",
            part,
        )
    rows = part["list"]
    if not rows:
        total = part.get("total")
        claims = (isinstance(total, int) and not isinstance(total, bool) and total > 0) or part.get(
            "partial"
        ) is True
        if claims:
            claim = (
                f"reported total={total}"
                if isinstance(total, int) and not isinstance(total, bool) and total > 0
                else "carried a partial marker"
            )
            raise _structural(
                f"{label}: {security} {claim} but delivered no rows — the response is inconsistent",
                part,
            )
        return
    fields = part.get("fieldList")
    usable = fields if isinstance(fields, list) and fields else None
    if any(isinstance(row, list) for row in rows) and not columnar_schema_valid(usable, rows):
        raise _structural(
            f"{label}: {security} returned columnar rows without a usable fieldList "
            "(missing, duplicated or mis-sized) — they cannot be read by position",
            part,
        )


def merge_parts(
    parts: Sequence[Any],
    *,
    securities: Sequence[Any],
    cap: int,
    label: str,
) -> dict[str, Any]:
    """Merge per-security answers into one payload, in input order.

    Every part is the same endpoint with the same ``fieldList`` request, so the
    column layout must agree EXACTLY — a part whose columns differ is a broken
    response, not something to merge under the wrong names. An empty part is a
    legitimate answer (nothing traded in the window) and says nothing about the
    layout, so it neither sets the header nor is compared against it; its
    ``fieldList`` is used for the output only when NO part had rows, so that a
    requested-but-missing column is still reportable.

    A part filling its row cap lands in ``truncatedSecurities`` and marks the merge
    ``partial``; a part already carrying ``partial`` keeps the merge partial too.
    """
    field_list: list[Any] | None = None
    header_security: str | None = None
    empty_fields: list[Any] | None = None
    merged: list[Any] = []
    truncated: list[Any] = []
    partial_securities: list[Any] = []

    for part, security in zip(parts, securities, strict=True):
        check_part(part, security, label)
        if part.get("partial") is True:
            partial_securities.append(security)
        rows: list[Any] = part["list"]
        if not rows:
            if empty_fields is None and isinstance(part.get("fieldList"), list):
                empty_fields = part["fieldList"]
            continue
        fields = part.get("fieldList")
        usable = fields if isinstance(fields, list) and fields else None
        if usable is not None and field_list is None:
            field_list = usable
            header_security = security
        if (usable is not None or field_list is not None) and usable != field_list:
            raise _structural(
                f"{label}: {security} answered with columns {usable!r} while "
                f"{header_security} answered {field_list!r} — the parts cannot be merged",
                part,
            )
        if len(rows) >= cap:
            truncated.append(security)
        merged.extend(rows)

    out: dict[str, Any] = {"total": len(merged), "list": merged}
    if field_list is not None:
        out["fieldList"] = field_list
    elif not merged and empty_fields is not None:
        out["fieldList"] = empty_fields
    if partial_securities:
        out["partial"] = True
        # Warn, don't just set the key: the DEFAULT return path is a DataFrame, which
        # keeps none of these markers — a caller who never passes `raw=True` would see
        # a frame that looks complete. The date sharder and the paginated merge both
        # warn when they carry a marker across; this path was the one that did not.
        warnings.warn(
            f"{label}: {', '.join(str(code) for code in partial_securities)} reported "
            "itself partial; the merged result is marked partial (see raw output)",
            stacklevel=3,
        )
    if truncated:
        out["partial"] = True
        out["truncatedSecurities"] = truncated
        warnings.warn(
            f"{label}: {', '.join(str(code) for code in truncated)} returned {cap} rows = "
            f"the per-request limit; "
            "those securities are likely truncated (see truncatedSecurities in raw output) — "
            "narrow the date range for them or raise limit (max 10000)",
            stacklevel=3,
        )
    return out


PartFetcher = Callable[[Any], Any]


def fetch_per_security(
    securities: Sequence[Any],
    *,
    fetch: PartFetcher,
    label: str,
    concurrency: int,
) -> list[Any]:
    """Fetch one part per security concurrently, in input order.

    Each answer is structurally checked as it lands (:func:`check_part`) and a
    failure stops the remaining parts from being dispatched — an unusable answer
    fails the whole call, so spending the rest of the requests buys nothing. The
    first error is re-raised once the in-flight parts have settled.
    """
    if not securities:
        return []
    workers = max(1, min(concurrency, len(securities)))
    aborted = threading.Event()

    def run_one(security: Any) -> tuple[Any, Exception | None]:
        if aborted.is_set():
            return None, None
        try:
            part = fetch(security)
            check_part(part, security, label)
        except Exception as exc:
            aborted.set()
            return None, exc
        return part, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(run_one, securities))

    for _part, error in outcomes:
        if error is not None:
            raise error
    return [part for part, _error in outcomes]


async def fetch_per_security_async(
    securities: Sequence[Any],
    *,
    fetch: Callable[[Any], Any],
    label: str,
    concurrency: int,
) -> list[Any]:
    """Async mirror of :func:`fetch_per_security` (same abort + re-raise contract)."""
    if not securities:
        return []
    workers = max(1, min(concurrency, len(securities)))
    semaphore = anyio.Semaphore(workers)
    parts: list[Any] = [None] * len(securities)
    errors: list[Exception | None] = [None] * len(securities)
    aborted = False

    async def run_one(index: int, security: Any) -> None:
        nonlocal aborted
        async with semaphore:
            if aborted:
                return
            try:
                part = await fetch(security)
                check_part(part, security, label)
            except Exception as exc:
                aborted = True
                errors[index] = exc
                return
            parts[index] = part

    try:
        async with anyio.create_task_group() as tg:
            for index, security in enumerate(securities):
                tg.start_soon(run_one, index, security)
    except BaseException as eg:
        leaf = first_leaf_exception(eg)
        if leaf is eg:
            raise
        # Unwrap anyio's exception group so callers see the bare error.
        raise leaf from eg

    for error in errors:
        if error is not None:
            raise error
    return parts
