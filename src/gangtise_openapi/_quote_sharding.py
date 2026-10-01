from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import anyio

from gangtise_openapi._errors import ApiError, GangtiseError, ValidationError
from gangtise_openapi._pagination import first_leaf_exception

# Sentinels marking a shard failed without its own exception: skipped because a
# prior shard hit a hard error, or resolved with a shape-broken payload. Neither
# is the "first error" surfaced when every shard fails.
_SKIPPED = Exception("shard skipped after a prior hard error")
_SHAPE_BROKEN = Exception("shard resolved without a list array")

# The code the API answers for a date range the account may not query (TS v0.44.0).
OUT_OF_WINDOW_CODE = "110003"

# Whole-market keyword -> WEEKDAYS per shard, per endpoint (TS v0.43.0: weekends never
# get a request of their own). A shard holds (rows per trading day x weekdays) and must
# stay under the 10000-row API cap: A-shares and US list several thousand securities
# per day and take one weekday per shard; HK is roughly half that and takes two
# (single-trading-day row counts probed 2026-08-13: A 5543 / US 5919 / HK 2810). These
# universes grow with listings — when a market's rows per trading day approach
# 10000 / weekdays, cut the width. The unified `day-kline` stopped accepting `["all"]`
# on 2026-08-14 and takes one of three market keywords; the menu-retired HK / US
# endpoints still take `all`.
#
# `index-day-kline` takes NO keyword (TS v0.41.1): it answers `all` with `000000` and an
# empty list (probed 2026-09-24 over four windows back to 2024, three samples each,
# while explicit index codes return rows), so `all` is refused before anything is sent.
MARKET_SHARD_DAYS: dict[str, dict[str, int]] = {
    "quote.day-kline": {"aShares": 1, "hkStocks": 2, "usStocks": 1},
    "quote.day-kline-hk": {"all": 2},
    "quote.day-kline-us": {"all": 1},
    "quote.index-day-kline": {},
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
# Compared lower-cased. The API's own case handling USED to differ by endpoint;
# re-probed by the CLI 2026-08-24 (curl direct, all six) it no longer does:
#
#   folds case:      ALL SIX, fund-flow included — `aShares` / `ashares` / `ASHARES` /
#                    `AShares` / `aSHARES` all return the same rows.
#
# Until 2026-08-21 `fund-flow` was the lone exception (only the literal `aShares`
# worked; every other casing came back `120001 非有效A股`), which made this folding the
# ONLY reason `ashares` worked there. That is fixed server-side, so canonicalising is no
# longer load-bearing for correctness anywhere — on every endpoint it now merely keeps
# the shard lookup in step with the server (drop it and a case variant degrades to an
# unsharded 6000-row request).
#
# Keep it anyway: it normalises rather than rejects, so it can only ever be more
# forgiving than the server, and it costs nothing. The fund-flow case test stays as a
# regression pin — but it now pins OUR normalisation, not a server-side quirk.
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

# The quote endpoints' per-request row ceiling (per docs); `limit` is validated to it.
QUOTE_MAX_LIMIT = 10_000
# Full-market requests are sent at the ceiling rather than the 6000-row default, so a
# shard is never cut short by the default.
DEFAULT_FULL_MARKET_LIMIT = QUOTE_MAX_LIMIT
# Explicit-security, non-paginated quote endpoints (fund-flow, kline, minute-kline) default
# to this server-side row cap. Sent EXPLICITLY when `limit` is omitted so the request limit
# and the truncation cap are always the same number — never a guess at the server default.
DEFAULT_QUOTE_LIMIT = 6_000


def plan_shards(
    *,
    start_date: dt.date,
    end_date: dt.date,
    weekdays_per_shard: int,
) -> list[tuple[dt.date, dt.date]]:
    """Split ``[start_date, end_date]`` into windows of ``weekdays_per_shard`` WEEKDAYS.

    A weekend day never has rows (A / HK / US markets closed), so counting calendar
    days spent requests on windows that could only come back empty or half empty
    (2-day hkStocks shards: every Sat + Sun pair, and every Fri + Sat). A shard runs
    from its first weekday to its last, so one straddling a weekend (Fri + Mon) still
    holds ``weekdays_per_shard`` trading days at most and stays inside the row cap its
    width was chosen for. An all-weekend range plans no shard at all. Holidays are left
    alone (calendar-dependent). TS v0.43.0 ``buildShards``.
    """
    if end_date < start_date:
        # A caller's reversed range, not a programming error: a ValidationError, so an
        # ``except GangtiseError`` catches it like every other local refusal.
        raise ValidationError(
            f"start_date {start_date.isoformat()} is after end_date {end_date.isoformat()}"
        )
    if weekdays_per_shard <= 0:
        raise ValueError("weekdays_per_shard must be positive")
    shards: list[tuple[dt.date, dt.date]] = []
    group: list[dt.date] = []
    day = start_date
    one_day = dt.timedelta(days=1)
    while day <= end_date:
        if day.weekday() < 5:
            group.append(day)
            if len(group) == weekdays_per_shard:
                shards.append((group[0], group[-1]))
                group = []
        day += one_day
    if group:
        shards.append((group[0], group[-1]))
    return shards


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


def check_market_keywords(
    security: Any,
    accepted: Sequence[str],
    command: str,
    *,
    no_keyword_reason: str | None = None,
) -> None:
    """Reject a whole-market keyword this endpoint does not take, or one sent
    alongside anything else.

    Both mistakes come back from the API as a bare ``120001 "invalid security
    code"``, which points at codes that are perfectly fine — or, on ``fund-flow``,
    do not come back as an error at all: the server silently DROPS the keyword and
    answers with just the explicit codes, so "the whole market plus this one"
    quietly becomes "only this one". Checked locally so no billed request is spent
    on a query that cannot work. ``no_keyword_reason`` is appended to the refusal
    of an endpoint that takes no keyword at all, so it does not read as a usage slip.
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
            + (f": {no_keyword_reason}" if no_keyword_reason else "")
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


def column_remap(header: Sequence[Any], shard: Sequence[Any]) -> list[int] | None:
    """Index map from ``header``'s columns into ``shard``'s own ``fieldList``.

    The merged result carries ONE ``fieldList`` (the first data shard's) and columnar
    rows are read against it by position, so a shard that orders its columns
    differently would be read under the wrong names — ``close`` landing in
    ``volume``, with nothing else in the payload to notice. Returns the mapping to
    re-order such a shard's rows onto the header, or ``None`` when a header column is
    absent from the shard and the rows cannot be aligned at all (TS v0.38.0
    ``columnRemap``). Callers skip this entirely when the two lists already agree.
    """
    index = {str(field): position for position, field in enumerate(shard)}
    mapping: list[int] = []
    for field in header:
        position = index.get(str(field))
        if position is None:
            return None
        mapping.append(position)
    return mapping


def extra_columns(header: Sequence[Any], shard: Sequence[Any]) -> list[str]:
    """The shard's columns the merged header has no slot for (TS v0.39.0).

    :func:`column_remap` checks one direction only — "is every header column in the
    shard" — which accepts a WIDER shard and then drops its surplus columns by
    omission. The merged ``fieldList`` stays the first data shard's (that is the
    contract), so those values cannot be carried; naming them is what keeps the loss
    from being silent.
    """
    names = {str(column) for column in header}
    return [str(column) for column in shard if str(column) not in names]


def _shape_broken(result: Any) -> bool:
    """A shard that resolves without a ``list`` array is shape-broken (an error
    object, a truncated envelope) — its rows are missing. Treated exactly like a
    thrown shard so the merged result is marked partial, not silently short.
    Unlike a hard error this doesn't abort the fan-out: one malformed shard
    isn't systemic. (TS quoteSharding parity, v0.27.0.)"""
    return not (isinstance(result, dict) and isinstance(result.get("list"), list))


@dataclass
class ShardFetch:
    """What a shard fan-out produced, in shard order.

    ``results[i]`` is shard ``i``'s payload, or ``None`` when it produced none. Every
    ``None`` is accounted for in exactly one of the two window lists:

    * ``failed`` — raised, came back shape-broken, or was never sent (``unsent`` of
      them) because an earlier hard error stopped the fan-out. The result is partial.
    * ``out_of_window`` — answered ``110003``: wholly before the account's history
      window. NOT a failure: a single request across the window's lower bound answers
      from the bound without an error, and a sharded one must mean the same, so these
      neither stop the fan-out nor mark the result partial (TS v0.44.0).

    ``first_error`` is the first real exception among ``failed`` (sentinels and
    ``110003`` excluded), named in the failure warning. ``window_error`` is the first
    ``110003``, raised when the merge finds nothing usable left: "outside your history
    window" is the reason a caller can act on, where a generic "all shards failed" is not.
    """

    results: list[Any]
    failed: list[tuple[dt.date, dt.date]]
    out_of_window: list[tuple[dt.date, dt.date]]
    first_error: Exception | None
    unsent: int
    window_error: Exception | None = None


def _out_of_window(error: BaseException | None) -> bool:
    return isinstance(error, ApiError) and error.code == OUT_OF_WINDOW_CODE


def describe_error(error: BaseException) -> str:
    """One line naming a shard failure: the API code and message, or the error's text.
    The bare message — ``str(ApiError)`` appends the multi-sentence hint, which does not
    belong inside a one-line warning."""
    if isinstance(error, ApiError):
        message = Exception.__str__(error)
        return f"({error.code}) {message}" if error.code else message
    return str(error) or type(error).__name__


def _collect(
    shards: Sequence[tuple[dt.date, dt.date]],
    results: list[Any],
    errors: Sequence[Exception | None],
) -> ShardFetch:
    """Classify each shard's outcome and raise when nothing at all was fetched."""
    failed: list[tuple[dt.date, dt.date]] = []
    out_of_window: list[tuple[dt.date, dt.date]] = []
    first_error: Exception | None = None
    window_error: Exception | None = None
    unsent = 0
    for window, error in zip(shards, errors, strict=True):
        if error is None:
            continue
        if _out_of_window(error):
            out_of_window.append(window)
            window_error = window_error or error
            continue
        failed.append(window)
        if error is _SKIPPED:
            unsent += 1
        elif error is not _SHAPE_BROKEN and first_error is None:
            first_error = error
    if len(failed) + len(out_of_window) == len(shards):
        # Nothing fetched — every shard failed or lay outside the history window.
        # Surface the error loudly rather than masking it as an empty success.
        if first_error is not None:
            raise first_error
        if window_error is not None:
            raise window_error
        raise GangtiseError(f"All {len(shards)} kline shards failed")
    return ShardFetch(results, failed, out_of_window, first_error, unsent, window_error)


def fetch_shards(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: ShardFetcher,
    concurrency: int,
) -> ShardFetch:
    """Fetch every shard, tolerating partial failures (TS quoteSharding parity).

    A failing or shape-broken shard contributes a ``None`` to ``results`` and its
    window to ``failed`` so the surviving shards still complete. After the first
    hard error the remaining undispatched shards are skipped (recorded as failed and
    counted in ``unsent``) rather than burning quota into the same failure. A
    ``110003`` shard lands in ``out_of_window`` and stops nothing. Only when no shard
    fetched anything is an error raised. See :class:`ShardFetch`.
    """
    if not shards:
        return ShardFetch([], [], [], None, 0)
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
            # A structural error is the client's verdict about THIS response's shape
            # (see ApiError.structural) — local to one shard, as is a window wholly
            # before the account's history (110003). Only a SYSTEMIC failure (rate
            # limit, no permission, retries exhausted) stops the rest from being
            # dispatched (TS v0.38.0 / v0.44.0).
            if not getattr(exc, "structural", False) and not _out_of_window(exc):
                aborted.set()
            return None, exc
        if _shape_broken(result):
            return None, _SHAPE_BROKEN
        return result, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(run_one, shards))

    return _collect(
        shards,
        [value for value, _error in outcomes],
        [error for _value, error in outcomes],
    )


AsyncShardFetcher = Callable[[tuple[dt.date, dt.date]], Any]


async def fetch_shards_async(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: AsyncShardFetcher,
    concurrency: int,
) -> ShardFetch:
    """Async mirror of `fetch_shards` (same partial-failure, abort and 110003 contract)."""
    if not shards:
        return ShardFetch([], [], [], None, 0)
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
                # Structural and 110003 errors do not abort the fan-out — see the sync mirror.
                if not getattr(exc, "structural", False) and not _out_of_window(exc):
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

    return _collect(shards, results, errors)
