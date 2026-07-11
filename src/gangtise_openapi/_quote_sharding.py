from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

from gangtise_openapi._errors import GangtiseError
from gangtise_openapi._pagination import first_leaf_exception

# Sentinels marking a shard failed without its own exception: skipped because a
# prior shard hit a hard error, or resolved with a shape-broken payload. Neither
# is the "first error" surfaced when every shard fails.
_SKIPPED = Exception("shard skipped after a prior hard error")
_SHAPE_BROKEN = Exception("shard resolved without a list array")

SHARD_DAYS: dict[str, int] = {
    "quote.day-kline": 1,
    "quote.day-kline-hk": 2,
    "quote.day-kline-us": 1,
    "quote.index-day-kline": 30,
    # fund-flow errors server-side (430012/430013) on a multi-day full-market request
    # instead of truncating, so date-shard by day (~5.4k A-share rows/day, under the cap).
    "quote.fund-flow": 1,
}

# Full-market ("all"/"aShares") requests lift the per-request cap to the API max.
DEFAULT_FULL_MARKET_LIMIT = 10_000
# Explicit-security, non-paginated quote endpoints (fund-flow, kline, minute-kline) default
# to this server-side row cap. Sent EXPLICITLY when `limit` is omitted so the request limit
# and the truncation cap are always the same number — never a guess at the server default.
DEFAULT_QUOTE_LIMIT = 6_000


def plan_shards(
    *,
    start_date: dt.date,
    end_date: dt.date,
    days_per_shard: int,
) -> list[tuple[dt.date, dt.date]]:
    if end_date < start_date:
        raise ValueError("end_date < start_date")
    if days_per_shard <= 0:
        raise ValueError("days_per_shard must be positive")
    shards: list[tuple[dt.date, dt.date]] = []
    cursor = start_date
    one_day = dt.timedelta(days=1)
    while cursor <= end_date:
        shard_end = cursor + dt.timedelta(days=days_per_shard - 1)
        if shard_end > end_date:
            shard_end = end_date
        shards.append((cursor, shard_end))
        cursor = shard_end + one_day
    return shards


def drop_weekend_shards(
    shards: Sequence[tuple[dt.date, dt.date]],
) -> list[tuple[dt.date, dt.date]]:
    """Drop shards whose entire window falls on Saturday/Sunday.

    Markets are closed on weekends, so an all-weekend window is guaranteed to
    return an empty list; skipping it saves the request (~29% of a 1-year
    day-kline plan). The TS CLI does the same since v0.24.0 for 1-day shards;
    dropping all-weekend 2-day windows too (day-kline-hk) is a Python superset.
    Holidays are left alone (calendar-dependent).
    """
    return [
        (start, end)
        for start, end in shards
        if not all(
            (start + dt.timedelta(days=i)).weekday() >= 5 for i in range((end - start).days + 1)
        )
    ]


def is_full_market(security: Any, full_market_value: str) -> bool:
    # Whole-market sharding fires only when securityList is exactly [full_market_value]
    # (``all`` for kline, ``aShares`` for fund-flow); mirror the TS predicate.
    if security == full_market_value:
        return True
    return isinstance(security, (list, tuple)) and list(security) == [full_market_value]


ShardFetcher = Callable[[tuple[dt.date, dt.date]], Any]


def _shape_broken(result: Any) -> bool:
    """A shard that resolves without a ``list`` array is shape-broken (an error
    object, a truncated envelope) — its rows are missing. Treated exactly like a
    thrown shard so the merged result is marked partial, not silently short.
    Unlike a hard error this doesn't abort the fan-out: one malformed shard
    isn't systemic. (TS quoteSharding parity, v0.27.0.)"""
    return not (isinstance(result, dict) and isinstance(result.get("list"), list))


def fetch_shards(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: ShardFetcher,
    concurrency: int,
) -> tuple[list[Any], list[tuple[dt.date, dt.date]]]:
    """Fetch every shard, tolerating partial failures (TS quoteSharding parity).

    Returns ``(results, failed_windows)``: a failing or shape-broken shard
    contributes a ``None`` sentinel to ``results`` and its window to
    ``failed_windows`` so the surviving shards still complete. After the first
    hard error the remaining undispatched shards are skipped (recorded as
    failed) rather than burning quota into the same failure. Only when every
    shard fails is the first error re-raised.
    """
    if not shards:
        return [], []
    workers = max(1, min(concurrency, len(shards)))
    aborted = threading.Event()

    def run_one(window: tuple[dt.date, dt.date]) -> tuple[Any, Exception | None]:
        # A prior shard hit a hard error (rate limit, no-perm, retries exhausted):
        # stop dispatching the rest; in-flight shards still complete.
        if aborted.is_set():
            return None, _SKIPPED
        try:
            result = fetch(window)
        except Exception as exc:
            aborted.set()
            return None, exc
        if _shape_broken(result):
            return None, _SHAPE_BROKEN
        return result, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(run_one, shards))

    results: list[Any] = []
    failed: list[tuple[dt.date, dt.date]] = []
    first_error: Exception | None = None
    for window, (value, error) in zip(shards, outcomes, strict=True):
        results.append(value)
        if error is not None:
            failed.append(window)
            if first_error is None and error is not _SKIPPED and error is not _SHAPE_BROKEN:
                first_error = error
    if failed and len(failed) == len(shards):
        # Every shard failed → surface the error loudly rather than masking a
        # total outage as an empty success (TS parity).
        if first_error is not None:
            raise first_error
        raise GangtiseError(f"All {len(shards)} kline shards failed")
    return results, failed


AsyncShardFetcher = Callable[[tuple[dt.date, dt.date]], Any]


async def fetch_shards_async(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: AsyncShardFetcher,
    concurrency: int,
) -> tuple[list[Any], list[tuple[dt.date, dt.date]]]:
    """Async mirror of `fetch_shards` (same partial-failure + abort contract)."""
    if not shards:
        return [], []
    workers = max(1, min(concurrency, len(shards)))
    semaphore = anyio.Semaphore(workers)
    results: list[Any] = [None] * len(shards)
    errors: list[Exception | None] = [None] * len(shards)
    aborted = False

    async def run_one(idx: int, window: tuple[dt.date, dt.date]) -> None:
        nonlocal aborted
        async with semaphore:
            # A prior shard hit a hard error: stop dispatching the rest;
            # in-flight shards still complete.
            if aborted:
                errors[idx] = _SKIPPED
                return
            try:
                result = await fetch(window)
            except Exception as exc:
                aborted = True
                errors[idx] = exc
                return
            if _shape_broken(result):
                errors[idx] = _SHAPE_BROKEN
                return
            results[idx] = result

    try:
        async with anyio.create_task_group() as tg:
            for idx, window in enumerate(shards):
                tg.start_soon(run_one, idx, window)
    except BaseException as eg:
        leaf = first_leaf_exception(eg)
        if leaf is eg:
            raise
        # Unwrap anyio's exception group so callers see the bare error.
        raise leaf from eg

    failed = [window for window, error in zip(shards, errors, strict=True) if error is not None]
    if failed and len(failed) == len(shards):
        first_error = next(
            (e for e in errors if e is not None and e is not _SKIPPED and e is not _SHAPE_BROKEN),
            None,
        )
        if first_error is not None:
            raise first_error
        raise GangtiseError(f"All {len(shards)} kline shards failed")
    return results, failed
