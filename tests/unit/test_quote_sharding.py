import datetime as dt

import pytest

from gangtise_openapi._errors import ApiError
from gangtise_openapi._quote_sharding import (
    SHARD_DAYS,
    drop_weekend_shards,
    fetch_shards,
    fetch_shards_async,
    is_full_market,
    plan_shards,
)


def test_shard_days_table():
    assert SHARD_DAYS["quote.day-kline"] == 1
    assert SHARD_DAYS["quote.day-kline-hk"] == 2
    assert SHARD_DAYS["quote.day-kline-us"] == 1
    assert SHARD_DAYS["quote.index-day-kline"] == 30
    assert SHARD_DAYS["quote.fund-flow"] == 1


def test_plan_shards_single_day():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 5),
        end_date=dt.date(2026, 1, 5),
        days_per_shard=1,
    )
    assert shards == [(dt.date(2026, 1, 5), dt.date(2026, 1, 5))]


def test_plan_shards_two_days_a_share():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 2),
        days_per_shard=1,
    )
    assert shards == [
        (dt.date(2026, 1, 1), dt.date(2026, 1, 1)),
        (dt.date(2026, 1, 2), dt.date(2026, 1, 2)),
    ]


def test_plan_shards_hk_two_per_shard():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
        days_per_shard=2,
    )
    assert shards == [
        (dt.date(2026, 1, 1), dt.date(2026, 1, 2)),
        (dt.date(2026, 1, 3), dt.date(2026, 1, 4)),
        (dt.date(2026, 1, 5), dt.date(2026, 1, 5)),
    ]


def test_plan_shards_index_30_per_shard():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 3, 31),
        days_per_shard=30,
    )
    assert shards[0][0] == dt.date(2026, 1, 1)
    assert shards[-1][1] == dt.date(2026, 3, 31)
    for s, e in shards:
        assert (e - s).days <= 29


def test_plan_shards_invalid_order():
    with pytest.raises(ValueError):
        plan_shards(
            start_date=dt.date(2026, 1, 5),
            end_date=dt.date(2026, 1, 1),
            days_per_shard=1,
        )


def test_is_full_market_matches_only_the_exact_keyword():
    # Kline uses "all"; fund-flow uses "aShares". Sharding fires only for exactly
    # [keyword] (scalar or single-element list) — mirrors the TS predicate.
    assert is_full_market("all", "all") is True
    assert is_full_market(["all"], "all") is True
    assert is_full_market("aShares", "aShares") is True
    assert is_full_market(["aShares"], "aShares") is True
    # Wrong keyword for the endpoint must not trigger full-market sharding.
    assert is_full_market("all", "aShares") is False
    assert is_full_market("aShares", "all") is False
    assert is_full_market("000001.SH", "all") is False
    # Mixed list must NOT shard — only exactly [keyword].
    assert is_full_market(["all", "000001.SZ"], "all") is False


def test_plan_shards_zero_days_per_shard_raises():
    with pytest.raises(ValueError):
        plan_shards(
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 1, 5),
            days_per_shard=0,
        )


def test_drop_weekend_shards_filters_single_day_weekend_windows():
    # 2026-01-01 Thu .. 2026-01-07 Wed: Sat 01-03 and Sun 01-04 dropped.
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 7),
        days_per_shard=1,
    )
    kept = drop_weekend_shards(shards)
    assert len(kept) == 5
    assert set(shards) - set(kept) == {
        (dt.date(2026, 1, 3), dt.date(2026, 1, 3)),
        (dt.date(2026, 1, 4), dt.date(2026, 1, 4)),
    }


def test_drop_weekend_shards_keeps_windows_containing_a_weekday():
    fri_sat = (dt.date(2026, 1, 2), dt.date(2026, 1, 3))
    sat_sun = (dt.date(2026, 1, 3), dt.date(2026, 1, 4))
    assert drop_weekend_shards([fri_sat, sat_sun]) == [fri_sat]


def test_drop_weekend_shards_year_of_daily_shards():
    # 2025-06-01 (Sun) .. 2026-05-31 (Sun): 365 daily shards, 105 weekend.
    shards = plan_shards(
        start_date=dt.date(2025, 6, 1),
        end_date=dt.date(2026, 5, 31),
        days_per_shard=1,
    )
    assert len(shards) == 365
    assert len(drop_weekend_shards(shards)) == 260


def test_drop_weekend_shards_all_weekend_range_is_empty():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 3),  # Sat
        end_date=dt.date(2026, 1, 4),  # Sun
        days_per_shard=1,
    )
    assert drop_weekend_shards(shards) == []


def test_drop_weekend_shards_never_touches_multi_day_windows():
    # Windows of >= 3 days always contain a weekday (e.g. index-day-kline's 30).
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 3, 31),
        days_per_shard=30,
    )
    assert drop_weekend_shards(shards) == shards


def test_fetch_shards_calls_each_shard_in_order():
    shards = [
        (dt.date(2026, 1, 1), dt.date(2026, 1, 1)),
        (dt.date(2026, 1, 2), dt.date(2026, 1, 2)),
        (dt.date(2026, 1, 3), dt.date(2026, 1, 3)),
    ]
    called: list[tuple[dt.date, dt.date]] = []

    def fetch(window: tuple[dt.date, dt.date]) -> str:
        called.append(window)
        s, _ = window
        return s.isoformat()

    results, failed = fetch_shards(shards, fetch=fetch, concurrency=2)

    # Order-preservation contract: pool.map returns results in input order
    assert results == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert failed == []
    # Each shard invoked exactly once
    assert sorted(called) == sorted(shards)
    assert len(called) == 3


_THREE_SHARDS = [
    (dt.date(2026, 1, 5), dt.date(2026, 1, 5)),
    (dt.date(2026, 1, 6), dt.date(2026, 1, 6)),
    (dt.date(2026, 1, 7), dt.date(2026, 1, 7)),
]


def test_fetch_shards_tolerates_partial_failure():
    def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        if s == dt.date(2026, 1, 6):
            raise ApiError("shard boom", code="100001")
        return s.isoformat()

    results, failed = fetch_shards(_THREE_SHARDS, fetch=fetch, concurrency=2)

    # Failing shard yields a None sentinel; survivors keep their slot.
    assert results == ["2026-01-05", None, "2026-01-07"]
    assert failed == [(dt.date(2026, 1, 6), dt.date(2026, 1, 6))]


def test_fetch_shards_all_failed_raises_first_error():
    def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        raise ApiError(f"boom {s.isoformat()}", code="100001")

    with pytest.raises(ApiError) as excinfo:
        fetch_shards(_THREE_SHARDS, fetch=fetch, concurrency=2)
    assert str(excinfo.value).startswith("boom 2026-01-05")


@pytest.mark.anyio
async def test_fetch_shards_async_tolerates_partial_failure():
    async def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        if s == dt.date(2026, 1, 6):
            raise ApiError("shard boom", code="100001")
        return s.isoformat()

    results, failed = await fetch_shards_async(_THREE_SHARDS, fetch=fetch, concurrency=2)

    assert results == ["2026-01-05", None, "2026-01-07"]
    assert failed == [(dt.date(2026, 1, 6), dt.date(2026, 1, 6))]


@pytest.mark.anyio
async def test_fetch_shards_async_all_failed_raises_bare_api_error():
    # Bare ApiError (not an ExceptionGroup): sync/async parity for `except ApiError`.
    async def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        raise ApiError(f"boom {s.isoformat()}", code="100001")

    with pytest.raises(ApiError) as excinfo:
        await fetch_shards_async(_THREE_SHARDS, fetch=fetch, concurrency=2)
    assert str(excinfo.value).startswith("boom 2026-01-05")
