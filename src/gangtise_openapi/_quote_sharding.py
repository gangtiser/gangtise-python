from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

SHARD_DAYS: dict[str, int] = {
    "quote.day-kline": 1,
    "quote.day-kline-hk": 2,
    "quote.day-kline-us": 1,
    "quote.index-day-kline": 30,
}

DEFAULT_FULL_MARKET_LIMIT = 10_000


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


def is_all_market(security: Any) -> bool:
    if security == "all":
        return True
    return isinstance(security, (list, tuple)) and "all" in security


def needs_limit_injection(*, security: Any, explicit_limit: int | None) -> bool:
    return is_all_market(security) and explicit_limit is None


ShardFetcher = Callable[[tuple[dt.date, dt.date]], Any]


def fetch_shards(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: ShardFetcher,
    concurrency: int,
) -> list[Any]:
    if not shards:
        return []
    workers = max(1, min(concurrency, len(shards)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fetch, shards))


AsyncShardFetcher = Callable[[tuple[dt.date, dt.date]], Any]


async def fetch_shards_async(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: AsyncShardFetcher,
    concurrency: int,
) -> list[Any]:
    if not shards:
        return []
    workers = max(1, min(concurrency, len(shards)))
    semaphore = anyio.Semaphore(workers)
    results: list[Any] = [None] * len(shards)

    async def run_one(idx: int, window: tuple[dt.date, dt.date]) -> None:
        async with semaphore:
            results[idx] = await fetch(window)

    async with anyio.create_task_group() as tg:
        for idx, window in enumerate(shards):
            tg.start_soon(run_one, idx, window)
    return results
