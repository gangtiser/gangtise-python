import datetime as dt

import pytest

from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._quote_sharding import (
    MARKET_SHARD_DAYS,
    canonicalize_market_keywords,
    check_market_keywords,
    describe_error,
    extra_columns,
    fetch_shards,
    fetch_shards_async,
    is_full_market,
    plan_shards,
    resolve_full_market,
)


def test_shard_days_table():
    # Translated 1:1 from gangtise-openapi-cli v0.44.0 commands/quote.ts (KLINE_MARKETS /
    # LEGACY_ALL_MARKET), in WEEKDAYS per shard. The unified day-kline shards per
    # market; the retired HK / US endpoints keep `all`; index-day-kline takes none.
    assert MARKET_SHARD_DAYS == {
        "quote.day-kline": {"aShares": 1, "hkStocks": 2, "usStocks": 1},
        "quote.day-kline-hk": {"all": 2},
        "quote.day-kline-us": {"all": 1},
        "quote.index-day-kline": {},
        "quote.fund-flow": {"aShares": 1},
    }


def test_index_day_kline_takes_no_keyword_and_says_why():
    # TS v0.41.1: the endpoint answers `all` with total 0 and no error, so the keyword
    # is refused locally — with the reason appended, so it does not read as a typo.
    assert MARKET_SHARD_DAYS["quote.index-day-kline"] == {}
    with pytest.raises(ValidationError, match=r"explicit security codes only.*: the reason"):
        check_market_keywords("all", (), "quote index-day-kline", no_keyword_reason="the reason")


def test_day_kline_rejects_retired_all_keyword():
    with pytest.raises(ValidationError, match="aShares"):
        check_market_keywords("all", ("aShares", "hkStocks", "usStocks"), "quote day-kline")


def test_market_keyword_must_be_passed_alone():
    with pytest.raises(ValidationError, match="alone"):
        check_market_keywords(
            ["aShares", "600519.SH"], ("aShares", "hkStocks", "usStocks"), "quote day-kline"
        )


def test_fund_flow_rejects_keyword_mixed_with_codes():
    # The server SILENTLY drops the keyword here and answers with just the explicit
    # codes — "whole market plus this one" quietly becomes "only this one".
    with pytest.raises(ValidationError, match="alone"):
        check_market_keywords(["aShares", "600519.SH"], ("aShares",), "quote fund-flow")


def test_fund_flow_rejects_foreign_keyword():
    with pytest.raises(ValidationError, match="aShares"):
        check_market_keywords("hkStocks", ("aShares",), "quote fund-flow")


def test_no_keyword_endpoint_reports_codes_only():
    with pytest.raises(ValidationError, match="explicit security codes only"):
        check_market_keywords("aShares", (), "ai stock_summary_list")


def test_explicit_codes_pass_the_keyword_check():
    check_market_keywords(["600519.SH", "000858.SZ"], ("aShares",), "quote fund-flow")


def test_keyword_case_is_folded_to_the_canonical_spelling():
    # fund-flow is the one endpoint that does NOT fold case server-side: only the
    # literal `aShares` works, so this normalization is what makes `ashares` usable.
    assert canonicalize_market_keywords("ashares", ("aShares",)) == "aShares"
    assert canonicalize_market_keywords(["ASHARES"], ("aShares",)) == ["aShares"]
    check_market_keywords("ashares", ("aShares",), "quote fund-flow")


def test_canonicalize_leaves_non_keywords_untouched():
    assert canonicalize_market_keywords(["600519.SH"], ("aShares",)) == ["600519.SH"]


def test_resolve_full_market_picks_the_requested_market():
    markets = MARKET_SHARD_DAYS["quote.day-kline"]
    assert resolve_full_market("hkStocks", markets) == "hkStocks"
    assert resolve_full_market(["usStocks"], markets) == "usStocks"
    assert resolve_full_market(["600519.SH"], markets) is None


def _weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    return [d for d in days if d.weekday() < 5]


def test_plan_shards_single_weekday():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 5),
        end_date=dt.date(2026, 1, 5),
        weekdays_per_shard=1,
    )
    assert shards == [(dt.date(2026, 1, 5), dt.date(2026, 1, 5))]


def test_plan_shards_one_weekday_each_skips_the_weekend():
    # 2026-01-01 Thu .. 01-07 Wed: Sat 01-03 and Sun 01-04 get no request.
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 7),
        weekdays_per_shard=1,
    )
    assert [s for s, _ in shards] == _weekdays(dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert all(s == e for s, e in shards)


def test_plan_shards_hk_two_weekdays_straddle_the_weekend():
    # TS v0.43.0 test: 07-03 Fri .. 07-08 Wed -> [Fri + Mon], [Tue + Wed]. Calendar-day
    # shards sent three, one of them Sat + Sun.
    shards = plan_shards(
        start_date=dt.date(2026, 7, 3),
        end_date=dt.date(2026, 7, 8),
        weekdays_per_shard=2,
    )
    assert shards == [
        (dt.date(2026, 7, 3), dt.date(2026, 7, 6)),
        (dt.date(2026, 7, 7), dt.date(2026, 7, 8)),
    ]


def test_plan_shards_cover_every_weekday_once_n_weekdays_each():
    # TS v0.43.0 test: 2026-04-01 (Wed) .. 04-19 (Sun): 13 weekdays across two weekends.
    start, end = dt.date(2026, 4, 1), dt.date(2026, 4, 19)
    shards = plan_shards(start_date=start, end_date=end, weekdays_per_shard=3)
    covered = [d for s, e in shards for d in _weekdays(s, e)]
    assert covered == _weekdays(start, end)
    assert [len(_weekdays(s, e)) for s, e in shards] == [3, 3, 3, 3, 1]
    # A shard starts and ends on a weekday: none is a weekend-only request.
    assert all(s.weekday() < 5 and e.weekday() < 5 for s, e in shards)


def test_plan_shards_year_of_daily_shards_is_one_per_weekday():
    # 2025-06-01 (Sun) .. 2026-05-31 (Sun): 365 calendar days, 260 weekdays.
    shards = plan_shards(
        start_date=dt.date(2025, 6, 1),
        end_date=dt.date(2026, 5, 31),
        weekdays_per_shard=1,
    )
    assert len(shards) == 260


def test_plan_shards_all_weekend_range_is_empty():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 3),  # Sat
        end_date=dt.date(2026, 1, 4),  # Sun
        weekdays_per_shard=2,
    )
    assert shards == []


def test_plan_shards_invalid_order():
    from gangtise_openapi._errors import ValidationError

    with pytest.raises(ValidationError, match="is after end_date"):
        plan_shards(
            start_date=dt.date(2026, 1, 5),
            end_date=dt.date(2026, 1, 1),
            weekdays_per_shard=1,
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


def test_plan_shards_zero_weekdays_per_shard_raises():
    with pytest.raises(ValueError):
        plan_shards(
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 1, 5),
            weekdays_per_shard=0,
        )


def test_extra_columns_checks_the_other_direction():
    # TS v0.39.0: "every header column is in the shard" accepts a WIDER shard and then
    # drops its surplus by omission; the surplus must be named instead.
    assert extra_columns(["close", "volume"], ["close", "volume", "amount"]) == ["amount"]
    assert extra_columns(["close", "volume"], ["volume", "close"]) == []


def _payload(window: tuple[dt.date, dt.date]) -> dict:
    s, _ = window
    return {"fieldList": ["tradeDate"], "list": [[s.isoformat()]]}


def test_fetch_shards_calls_each_shard_in_order():
    shards = [
        (dt.date(2026, 1, 1), dt.date(2026, 1, 1)),
        (dt.date(2026, 1, 2), dt.date(2026, 1, 2)),
        (dt.date(2026, 1, 3), dt.date(2026, 1, 3)),
    ]
    called: list[tuple[dt.date, dt.date]] = []

    def fetch(window: tuple[dt.date, dt.date]) -> dict:
        called.append(window)
        return _payload(window)

    fetched = fetch_shards(shards, fetch=fetch, concurrency=2)

    # Order-preservation contract: pool.map returns results in input order
    assert [r["list"][0][0] for r in fetched.results] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert fetched.failed == []
    assert fetched.out_of_window == []
    # Each shard invoked exactly once
    assert sorted(called) == sorted(shards)
    assert len(called) == 3


_THREE_SHARDS = [
    (dt.date(2026, 1, 5), dt.date(2026, 1, 5)),
    (dt.date(2026, 1, 6), dt.date(2026, 1, 6)),
    (dt.date(2026, 1, 7), dt.date(2026, 1, 7)),
]


def test_fetch_shards_aborts_remaining_after_hard_error():
    # TS v0.27.0 parity: the first hard error stops dispatching the remaining
    # shards (they are recorded as failed) instead of burning quota into the
    # same failure. concurrency=1 makes the ordering deterministic: Mon
    # succeeds, Tue fails hard, Wed is skipped without a fetch.
    called: list[dt.date] = []

    def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        called.append(s)
        if s == dt.date(2026, 1, 6):
            raise ApiError("shard boom", code="100001")
        return _payload(window)

    fetched = fetch_shards(_THREE_SHARDS, fetch=fetch, concurrency=1)

    assert fetched.results[0]["list"] == [["2026-01-05"]]
    assert fetched.results[1] is None and fetched.results[2] is None
    assert fetched.failed == [
        (dt.date(2026, 1, 6), dt.date(2026, 1, 6)),
        (dt.date(2026, 1, 7), dt.date(2026, 1, 7)),
    ]
    # Wednesday was never fetched — counted apart from the one that failed (TS v0.44.0).
    assert called == [dt.date(2026, 1, 5), dt.date(2026, 1, 6)]
    assert fetched.unsent == 1
    assert isinstance(fetched.first_error, ApiError) and fetched.first_error.code == "100001"


def test_fetch_shards_shape_broken_shard_fails_without_abort():
    # A 2xx shard without a list array is recorded as failed, but does NOT
    # abort the fan-out: one malformed shard is not systemic.
    def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        if s == dt.date(2026, 1, 6):
            return {"unexpected": "shape"}
        return _payload(window)

    fetched = fetch_shards(_THREE_SHARDS, fetch=fetch, concurrency=1)

    assert fetched.results[0]["list"] == [["2026-01-05"]]
    assert fetched.results[1] is None
    assert fetched.results[2]["list"] == [["2026-01-07"]]
    assert fetched.failed == [(dt.date(2026, 1, 6), dt.date(2026, 1, 6))]
    # A shape-broken shard has no exception to name.
    assert fetched.first_error is None and fetched.unsent == 0


def test_fetch_shards_all_failed_raises_first_error():
    def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        raise ApiError(f"boom {s.isoformat()}", code="100001")

    with pytest.raises(ApiError) as excinfo:
        fetch_shards(_THREE_SHARDS, fetch=fetch, concurrency=2)
    assert str(excinfo.value).startswith("boom 2026-01-05")


@pytest.mark.anyio
async def test_fetch_shards_async_aborts_remaining_after_hard_error():
    # Async mirror of the abort contract: Mon succeeds, Tue fails hard, Wed is
    # skipped (recorded as failed) without a fetch. concurrency=1 for determinism.
    called: list[dt.date] = []

    async def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        called.append(s)
        if s == dt.date(2026, 1, 6):
            raise ApiError("shard boom", code="100001")
        return _payload(window)

    fetched = await fetch_shards_async(_THREE_SHARDS, fetch=fetch, concurrency=1)

    assert fetched.results[0]["list"] == [["2026-01-05"]]
    assert fetched.results[1] is None and fetched.results[2] is None
    assert fetched.failed == [
        (dt.date(2026, 1, 6), dt.date(2026, 1, 6)),
        (dt.date(2026, 1, 7), dt.date(2026, 1, 7)),
    ]
    assert called == [dt.date(2026, 1, 5), dt.date(2026, 1, 6)]
    assert fetched.unsent == 1
    assert isinstance(fetched.first_error, ApiError) and fetched.first_error.code == "100001"


@pytest.mark.anyio
async def test_fetch_shards_async_all_failed_raises_bare_api_error():
    # Bare ApiError (not an ExceptionGroup): sync/async parity for `except ApiError`.
    async def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        raise ApiError(f"boom {s.isoformat()}", code="100001")

    with pytest.raises(ApiError) as excinfo:
        await fetch_shards_async(_THREE_SHARDS, fetch=fetch, concurrency=2)
    assert str(excinfo.value).startswith("boom 2026-01-05")


# 2015-12-28 (Mon) .. 2016-01-08 (Fri): ten weekdays; the account's window starts 2016.
_ACROSS_WINDOW = plan_shards(
    start_date=dt.date(2015, 12, 28), end_date=dt.date(2016, 1, 8), weekdays_per_shard=1
)


def _window_fetch(called: list[dt.date]):
    def fetch(window: tuple[dt.date, dt.date]):
        s, _ = window
        called.append(s)
        if s < dt.date(2016, 1, 1):
            raise ApiError("超出时间范围限制", code="110003", status_code=400)
        return _payload(window)

    return fetch


def test_fetch_shards_skips_out_of_window_shards_without_aborting():
    # TS v0.44.0: shards wholly before the history window answer 110003. They used to
    # abort every later shard, turning a mostly-in-window range into a near-empty,
    # "7/8 failed" result. Now they are skipped, listed, and stop nothing.
    called: list[dt.date] = []
    fetched = fetch_shards(_ACROSS_WINDOW, fetch=_window_fetch(called), concurrency=1)
    assert fetched.failed == []
    assert [s for s, _ in fetched.out_of_window] == [
        dt.date(2015, 12, 28),
        dt.date(2015, 12, 29),
        dt.date(2015, 12, 30),
        dt.date(2015, 12, 31),
    ]
    assert len(called) == len(_ACROSS_WINDOW)  # nothing was aborted
    kept = [r["list"][0][0] for r in fetched.results if r is not None]
    assert kept == [
        "2016-01-01",
        "2016-01-04",
        "2016-01-05",
        "2016-01-06",
        "2016-01-07",
        "2016-01-08",
    ]
    assert fetched.first_error is None


@pytest.mark.anyio
async def test_fetch_shards_async_skips_out_of_window_shards_without_aborting():
    called: list[dt.date] = []
    sync_fetch = _window_fetch(called)

    async def fetch(window: tuple[dt.date, dt.date]):
        return sync_fetch(window)

    fetched = await fetch_shards_async(_ACROSS_WINDOW, fetch=fetch, concurrency=1)
    assert fetched.failed == []
    assert len(fetched.out_of_window) == 4
    assert len(called) == len(_ACROSS_WINDOW)


def test_fetch_shards_still_fails_when_every_shard_is_out_of_window():
    def fetch(window: tuple[dt.date, dt.date]):
        raise ApiError("超出时间范围限制", code="110003", status_code=400)

    with pytest.raises(ApiError) as excinfo:
        fetch_shards(_THREE_SHARDS, fetch=fetch, concurrency=2)
    assert excinfo.value.code == "110003"


@pytest.mark.anyio
async def test_fetch_shards_async_still_fails_when_every_shard_is_out_of_window():
    async def fetch(window: tuple[dt.date, dt.date]):
        raise ApiError("超出时间范围限制", code="110003", status_code=400)

    with pytest.raises(ApiError) as excinfo:
        await fetch_shards_async(_THREE_SHARDS, fetch=fetch, concurrency=2)
    assert excinfo.value.code == "110003"


def test_describe_error_names_the_api_code():
    assert describe_error(ApiError("系统内部错误", code="999999")) == "(999999) 系统内部错误"
    assert describe_error(RuntimeError("boom")) == "boom"
