import datetime as dt

import pytest

from gangtise_openapi._quote_sharding import (
    SHARD_DAYS,
    fetch_shards,
    needs_limit_injection,
    plan_shards,
)


def test_shard_days_table():
    assert SHARD_DAYS["quote.day-kline"] == 1
    assert SHARD_DAYS["quote.day-kline-hk"] == 2
    assert SHARD_DAYS["quote.day-kline-us"] == 1
    assert SHARD_DAYS["quote.index-day-kline"] == 30


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


def test_needs_limit_injection_only_for_all_market():
    assert needs_limit_injection(security="all", explicit_limit=None) is True
    assert needs_limit_injection(security="all", explicit_limit=5000) is False
    assert needs_limit_injection(security="000001.SH", explicit_limit=None) is False
    assert needs_limit_injection(security=["all"], explicit_limit=None) is True
    assert needs_limit_injection(security=["000001.SH"], explicit_limit=None) is False


def test_plan_shards_zero_days_per_shard_raises():
    with pytest.raises(ValueError):
        plan_shards(
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 1, 5),
            days_per_shard=0,
        )


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

    results = fetch_shards(shards, fetch=fetch, concurrency=2)

    # Order-preservation contract: pool.map returns results in input order
    assert results == ["2026-01-01", "2026-01-02", "2026-01-03"]
    # Each shard invoked exactly once
    assert sorted(called) == sorted(shards)
    assert len(called) == 3
