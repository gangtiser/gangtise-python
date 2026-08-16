from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

from gangtise_openapi._errors import GangtiseError, ValidationError
from gangtise_openapi._pagination import first_leaf_exception

# Sentinels marking a shard failed without its own exception: skipped because a
# prior shard hit a hard error, or resolved with a shape-broken payload. Neither
# is the "first error" surfaced when every shard fails.
_SKIPPED = Exception("shard skipped after a prior hard error")
_SHAPE_BROKEN = Exception("shard resolved without a list array")

# Whole-market keyword -> shard width in days, per endpoint. The unified
# `day-kline` stopped accepting `["all"]` on 2026-08-14 and now takes one of three
# market keywords, each sharded at its own granularity (single-trading-day row
# counts probed 2026-08-13: A 5543 / US 5919 / HK 2810 — every window stays under
# the 10000-row API cap). The menu-retired per-market endpoints still take `all`.
MARKET_SHARD_DAYS: dict[str, dict[str, int]] = {
    "quote.day-kline": {"aShares": 1, "hkStocks": 2, "usStocks": 1},
    "quote.day-kline-hk": {"all": 2},
    "quote.day-kline-us": {"all": 1},
    # 15 days, not the historical 30: ~531 index rows per trading day x ~11 trading
    # days in a 15-day window is ~5.8K, while a 30-day window is ~11.7K — every
    # shard silently maxed out at the cap and lost ~11% of the range.
    "quote.index-day-kline": {"all": 15},
    # fund-flow errors server-side (430012/430013) on a multi-day full-market request
    # instead of truncating, so date-shard by day (~5.4k A-share rows/day, under the cap).
    "quote.fund-flow": {"aShares": 1},
}

# Endpoints that take a market keyword but never shard (one snapshot per security),
# so they only need the accepted-keyword + must-be-alone checks.
REALTIME_MARKETS: tuple[str, ...] = ("aShares", "hkStocks", "usStocks")
# `ai.stock-summary` lost whole-market batching on 2026-08-14 and now takes explicit
# codes only. It bills 3 credits per security, so the check must fire before the request.
NO_MARKET_KEYWORDS: tuple[str, ...] = ()

# Every keyword the quote APIs have ever taken, including ones a given endpoint no
# longer accepts. What an unrecognised keyword does depends on the endpoint, and BOTH
# outcomes are worth a local error: the unified `day-kline` / `realtime` / `fund-flow`
# answer `120001 "invalid security code"` (which sends the caller hunting for a typo in
# a code that is fine), while the menu-retired per-market endpoints answer with
# `total: 0` — a silent empty result indistinguishable from "no data".
#
# Compared lower-cased, and that folding is LOAD-BEARING, not tidiness — the API's own
# case handling differs BY ENDPOINT (probed 2026-08-15, all six):
#
#   folds case:      day-kline (aShares/…), realtime, day-kline-hk/-us/index (all)
#   case-SENSITIVE:  fund-flow — only the literal `aShares` works; `ashares` / `ASHARES`
#                    come back as `120001 非有效A股`
#
# So on five endpoints canonicalising merely keeps the shard lookup in step with the
# server (drop it and a case variant degrades to an unsharded 6000-row request), but on
# `fund-flow` it is the ONLY reason `ashares` works at all.
#
# ⚠️ `all` collides with a real ticker root (`ALL` is Allstate on the NYSE), so a bare
# `security="ALL"` fetches the whole US market instead of that stock. That resolution
# happens on the SERVER, so matching case-sensitively here would not prevent it — it
# would only stop us from sharding a request the server treats as whole-market anyway,
# turning a complete result into a truncated one. The fix for that caller is `ALL.N`.
#
# Unknown keywords are deliberately NOT rejected — this is a known-keyword list, so a
# future server-side addition degrades to "unsharded" rather than being refused outright.
MARKET_KEYWORDS = frozenset({"all", "ashares", "hkstocks", "usstocks"})

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
    # (``all`` for the retired endpoints, ``aShares``/``hkStocks``/``usStocks`` for the
    # unified ones); mirror the TS predicate.
    if security == full_market_value:
        return True
    return isinstance(security, (list, tuple)) and list(security) == [full_market_value]


def _security_entries(security: Any) -> list[Any]:
    if security is None:
        return []
    if isinstance(security, (list, tuple)):
        return list(security)
    return [security]


def check_market_keywords(security: Any, accepted: Sequence[str], command: str) -> None:
    """Reject a whole-market keyword this endpoint does not take, or one sent
    alongside anything else.

    Both mistakes come back from the API as a bare ``120001 "invalid security
    code"``, which points at codes that are perfectly fine — or, on ``fund-flow``,
    do not come back as an error at all: the server silently DROPS the keyword and
    answers with just the explicit codes, so "the whole market plus this one"
    quietly becomes "only this one". Checked locally so no billed request is spent
    on a query that cannot work.
    """
    entries = _security_entries(security)
    used = [s for s in entries if isinstance(s, str) and s.lower() in MARKET_KEYWORDS]
    if not used:
        return
    # Report an unsupported keyword before the alone-ness rule: when both are wrong,
    # the keyword itself is the thing the caller has to change.
    lowered = {a.lower() for a in accepted}
    unsupported = [k for k in used if k.lower() not in lowered]
    if unsupported:
        raise ValidationError(
            f"{command}: {unsupported[0]!r} is not a whole-market keyword for this "
            f"endpoint — use {' / '.join(accepted)}"
            if accepted
            else f"{command}: this endpoint takes explicit security codes only — "
            f"{unsupported[0]!r} and other whole-market keywords are not supported"
        )
    if len(entries) > 1:
        joined = ", ".join(str(e) for e in entries)
        raise ValidationError(
            f"{command}: a market keyword must be passed alone, got {joined!r} — the API "
            "rejects it mixed with security codes or another keyword"
        )


def canonicalize_market_keywords(security: Any, accepted: Sequence[str]) -> Any:
    """Fold a caller-typed keyword back to the spelling the API and the shard lookup
    expect, so a case variant reaches the same code path as the canonical form.
    Non-keywords pass through untouched, and a scalar stays a scalar."""
    if isinstance(security, str):
        return next((a for a in accepted if a.lower() == security.lower()), security)
    if isinstance(security, (list, tuple)):
        return [
            next((a for a in accepted if a.lower() == s.lower()), s) if isinstance(s, str) else s
            for s in security
        ]
    return security


def resolve_full_market(security: Any, markets: Mapping[str, int]) -> str | None:
    """Which whole-market keyword this request is, if any. Run AFTER
    ``canonicalize_market_keywords`` so a case variant still matches."""
    return next((keyword for keyword in markets if is_full_market(security, keyword)), None)


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
