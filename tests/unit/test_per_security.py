"""Per-security fan-out: the pure planning / merging half (TS v0.38.0 perSecurity)."""

from __future__ import annotations

import datetime as dt
import warnings
from typing import Any

import pytest

from gangtise_openapi._errors import ApiError
from gangtise_openapi._per_security import (
    check_part,
    estimate_trading_days,
    fetch_per_security,
    fetch_per_security_async,
    merge_parts,
    pack_securities,
)

# ── estimate_trading_days ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2026-09-07", "2026-09-11", 5),  # Mon..Fri
        ("2026-09-07", "2026-09-13", 5),  # + the weekend adds nothing
        ("2026-09-12", "2026-09-13", 0),  # Sat..Sun
        ("2026-09-07", "2026-09-07", 1),  # one weekday
        ("2026-09-07", "2026-09-18", 10),  # two whole weeks
        ("2026-01-01", "2026-12-31", 261),  # a full year of weekdays
    ],
)
def test_estimate_trading_days_counts_weekdays(start, end, expected):
    assert estimate_trading_days(start, end) == expected


def test_estimate_trading_days_never_under_estimates_a_real_calendar():
    # Holidays only REMOVE trading days, so the weekday count is an upper bound —
    # and over-estimating is the safe direction (one extra request beats a capped
    # answer). 2026-10-01..07 is the mainland National Day break: 5 weekdays by the
    # calendar, 0 actually traded.
    assert estimate_trading_days("2026-10-01", "2026-10-07") >= 0


def test_estimate_trading_days_falls_back_to_the_server_window():
    # No start date → the server applies its own one-year window whatever the end is.
    assert estimate_trading_days(None, "2026-09-11") == 262
    assert estimate_trading_days("", None) == 262
    # An inverted range: the server rejects it, so one request surfaces that more
    # cheaply than N identical failures.
    assert estimate_trading_days("2026-09-11", "2026-09-01") == 262


def test_estimate_trading_days_accepts_date_objects():
    assert estimate_trading_days(dt.date(2026, 9, 7), dt.date(2026, 9, 11)) == 5


# ── check_part ────────────────────────────────────────────────────────────────


def test_check_part_accepts_a_legitimately_empty_window():
    # Nothing traded is a real answer and says nothing about the column layout.
    check_part({"total": 0, "list": [], "fieldList": ["a"]}, "600519.SH", "quote day-kline")


@pytest.mark.parametrize(
    "part",
    [
        None,
        [],
        {"total": 0},
        {"list": "not a list"},
    ],
)
def test_check_part_rejects_a_payload_without_a_list(part):
    with pytest.raises(ApiError, match="returned no list payload") as excinfo:
        check_part(part, "600519.SH", "quote day-kline")
    assert excinfo.value.structural is True


@pytest.mark.parametrize(
    ("part", "match"),
    [
        ({"total": 7, "list": []}, "reported total=7"),
        ({"total": 0, "list": [], "partial": True}, "carried a partial marker"),
    ],
)
def test_check_part_rejects_an_empty_part_that_claims_rows(part, match):
    # A contradiction, not a quiet window: the caller NAMED this security, so its
    # rows going missing is exactly what has to surface.
    with pytest.raises(ApiError, match=match):
        check_part(part, "600519.SH", "quote day-kline")


@pytest.mark.parametrize(
    "part",
    [
        {"list": [[1, 2]]},  # array rows, no fieldList
        {"fieldList": ["a", "a"], "list": [[1, 2]]},  # duplicate names
        {"fieldList": ["a", "b"], "list": [[1]]},  # mis-sized row
    ],
)
def test_check_part_rejects_unreadable_columnar_rows(part):
    with pytest.raises(ApiError, match="without a usable fieldList") as excinfo:
        check_part(part, "600519.SH", "quote day-kline")
    assert excinfo.value.structural is True


def test_check_part_leaves_object_rows_alone():
    # Object rows carry their own keys; a fieldList is neither needed nor judged.
    check_part({"list": [{"close": 1}]}, "600519.SH", "quote day-kline")


# ── merge_parts ───────────────────────────────────────────────────────────────


def _part(rows: list[Any], fields: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"total": len(rows), "list": rows}
    if fields is not None:
        out["fieldList"] = fields
    out.update(extra)
    return out


def test_merge_parts_concatenates_in_input_order():
    parts = [
        _part([["a1", 1]], ["securityCode", "close"]),
        _part([["b1", 2], ["b2", 3]], ["securityCode", "close"]),
    ]
    out = merge_parts(parts, securities=["A", "B"], cap=6000, label="quote day-kline")
    assert out["total"] == 3
    assert out["list"] == [["a1", 1], ["b1", 2], ["b2", 3]]
    assert out["fieldList"] == ["securityCode", "close"]
    assert "partial" not in out


def test_merge_parts_refuses_parts_whose_columns_disagree():
    # Every part is the SAME endpoint with the SAME fieldList request, so a differing
    # layout is a broken response — merging would read `close` under `volume`.
    parts = [
        _part([["a1", 1]], ["securityCode", "close"]),
        _part([["b1", 2]], ["securityCode", "volume"]),
    ]
    with pytest.raises(ApiError, match="the parts cannot be merged") as excinfo:
        merge_parts(parts, securities=["A", "B"], cap=6000, label="quote day-kline")
    assert excinfo.value.structural is True


def test_merge_parts_ignores_an_empty_parts_columns():
    # An empty part says nothing about the layout: it must neither set the header nor
    # be compared against it. Its fieldList still serves as the output header when NO
    # part had rows, so a requested-but-missing column stays reportable.
    empty_first = [
        _part([], ["something", "else"]),
        _part([["b1", 2]], ["securityCode", "close"]),
    ]
    out = merge_parts(empty_first, securities=["A", "B"], cap=6000, label="q")
    assert out["fieldList"] == ["securityCode", "close"]
    assert out["list"] == [["b1", 2]]

    all_empty = [_part([], ["securityCode", "close"]), _part([], ["securityCode", "close"])]
    out = merge_parts(all_empty, securities=["A", "B"], cap=6000, label="q")
    assert out == {"total": 0, "list": [], "fieldList": ["securityCode", "close"]}


def test_merge_parts_flags_a_security_that_filled_its_row_cap():
    parts = [_part([[1]] * 3, ["close"]), _part([[2]], ["close"])]
    with pytest.warns(UserWarning, match="per-request limit"):
        out = merge_parts(parts, securities=["A", "B"], cap=3, label="quote day-kline")
    assert out["partial"] is True
    assert out["truncatedSecurities"] == ["A"]


def test_merge_parts_carries_a_parts_own_partial_marker():
    # Only the merged shape survives, so a part's own marker has to be carried across
    # or the merged result reads as complete.
    parts = [_part([[1]], ["close"], partial=True), _part([[2]], ["close"])]
    with pytest.warns(UserWarning, match="reported itself partial"):
        out = merge_parts(parts, securities=["A", "B"], cap=6000, label="q")
    assert out["partial"] is True
    assert "truncatedSecurities" not in out


# ── fetch_per_security ────────────────────────────────────────────────────────


def test_fetch_per_security_stops_dispatching_after_a_failure():
    """An unusable answer fails the whole call, so spending the rest buys nothing."""
    seen: list[str] = []

    def fetch(code: str) -> Any:
        seen.append(code)
        if code == "A":
            raise ApiError("120001 invalid security code")
        return _part([[1]], ["close"])

    with pytest.raises(ApiError, match="120001"):
        fetch_per_security(
            ["A", "B", "C", "D"], fetch=fetch, label="quote day-kline", concurrency=1
        )
    # Serial (concurrency=1): B/C/D must never have been sent.
    assert seen == ["A"]


def test_fetch_per_security_surfaces_a_structural_answer_as_an_error():
    # Unlike the date sharder, a broken part is NOT tolerated here.
    def fetch(code: str) -> Any:
        return {"total": 5, "list": []} if code == "B" else _part([[1]], ["close"])

    with pytest.raises(ApiError, match="reported total=5"):
        fetch_per_security(["A", "B"], fetch=fetch, label="quote day-kline", concurrency=1)


def test_fetch_per_security_returns_parts_in_input_order():
    def fetch(code: str) -> Any:
        return _part([[code]], ["securityCode"])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parts = fetch_per_security(["A", "B", "C"], fetch=fetch, label="q", concurrency=3)
    assert [p["list"][0][0] for p in parts] == ["A", "B", "C"]


# ─── Regression: estimate-before-normalize, and the silent partial ───


def test_estimate_takes_iso_only_and_says_so():
    """The estimator reads ISO; it cannot reach the domain layer's date parser.

    That is why every caller normalizes first (`_date_to_iso`). The end-to-end
    contract — the SPLIT DECISION is the same for all three accepted layouts — is
    pinned in `tests/endpoints/test_quote.py`, which is where the bug actually bit.
    """
    assert estimate_trading_days("2016-01-01", "2026-01-01") == 2610
    assert estimate_trading_days(dt.date(2016, 1, 1), dt.date(2026, 1, 1)) == 2610


def test_an_unreadable_range_errs_toward_splitting():
    # The two directions are not symmetric: over-estimating costs one extra request,
    # under-estimating silently truncates. So an unreadable range must split.
    assert estimate_trading_days("not-a-date", "2026-01-01") > 10_000
    assert estimate_trading_days("2016-01-01", "garbage") > 10_000


def test_merge_parts_warns_when_it_carries_a_partial_marker():
    """The DEFAULT return path is a DataFrame, which keeps none of these dict markers.

    Setting the key without warning left a caller who never passes `raw=True` holding
    a frame that looks complete. The date sharder and the paginated merge both warn
    when they carry a marker across; this path was the one that did not.
    """
    parts = [_part([[1]], ["close"], partial=True), _part([[2]], ["close"])]
    with pytest.warns(UserWarning, match="600519.SH reported itself partial"):
        out = merge_parts(
            parts, securities=["600519.SH", "000001.SZ"], cap=6000, label="quote day-kline"
        )
    assert out["partial"] is True


def test_merge_parts_names_every_partial_security():
    parts = [_part([[1]], ["close"], partial=True), _part([[2]], ["close"], partial=True)]
    with pytest.warns(UserWarning, match="A, B"):
        merge_parts(parts, securities=["A", "B"], cap=6000, label="q")


def test_merge_parts_stays_quiet_when_nothing_is_partial():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = merge_parts([_part([[1]], ["close"])], securities=["A"], cap=6000, label="q")
    assert "partial" not in out


# ── grouped parts (TS v0.43.0 day-kline packing) ─────────────────────────────


@pytest.mark.parametrize(
    ("n", "days", "cap", "sizes"),
    [
        # 5 x 2 = 10 rows = cap 10: a group of 5 would land EXACTLY on the cap and read
        # as truncated, so groups are planned below it — 4, then 1.
        (5, 2, 10, [4, 1]),
        (6, 2, 10, [4, 2]),
        # TS: 30 securities x ~784 weekdays under the 10000 ceiling -> 12, 12, 6.
        (30, 784, 10_000, [12, 12, 6]),
        # A security longer than the cap still goes alone (and is flagged by the merge).
        (3, 2610, 500, [1, 1, 1]),
    ],
)
def test_pack_securities_plans_every_group_below_the_cap(n, days, cap, sizes):
    codes = [f"S{i:02d}.SZ" for i in range(n)]
    groups = pack_securities(codes, trading_days=days, cap=cap)
    assert [len(g) for g in groups] == sizes
    assert [c for g in groups for c in g] == codes  # input order, nothing lost


def test_merge_parts_puts_each_group_back_in_input_order():
    # The server answers a multi-security request sorted by securityCode; the merge
    # must list securities in the caller's order, each keeping its date order.
    groups = [["B.SZ", "A.SZ"], ["D.SZ", "C.SZ"], ["E.SZ"]]

    def server(codes: list[str]) -> dict[str, Any]:
        rows = [[c, d] for c in sorted(codes) for d in ("2026-06-01", "2026-06-02")]
        return _part(rows, ["securityCode", "tradeDate"])

    out = merge_parts([server(g) for g in groups], securities=groups, cap=6000, label="q")
    assert [" ".join(r) for r in out["list"]] == [
        "B.SZ 2026-06-01", "B.SZ 2026-06-02", "A.SZ 2026-06-01", "A.SZ 2026-06-02",
        "D.SZ 2026-06-01", "D.SZ 2026-06-02", "C.SZ 2026-06-01", "C.SZ 2026-06-02",
        "E.SZ 2026-06-01", "E.SZ 2026-06-02",
    ]  # fmt: skip
    assert out["total"] == 10


def test_merge_parts_matches_codes_case_blind():
    # The server takes `grp09.sz` and answers `GRP09.SZ`.
    part = _part([["GRP01.SZ", 1], ["GRP09.SZ", 2]], ["securityCode", "close"])
    out = merge_parts([part], securities=[["grp09.sz", "GRP01.SZ"]], cap=6000, label="q")
    assert [r[0] for r in out["list"]] == ["GRP09.SZ", "GRP01.SZ"]


def test_merge_parts_names_every_security_of_a_group_that_filled_the_cap():
    parts = [
        _part([["A.SZ"], ["B.SZ"], ["B.SZ"]], ["securityCode"]),
        _part([["C.SZ"]], ["securityCode"]),
    ]
    with pytest.warns(UserWarning, match="A.SZ, B.SZ returned 3 rows"):
        out = merge_parts(parts, securities=[["A.SZ", "B.SZ"], ["C.SZ"]], cap=3, label="q")
    assert out["partial"] is True
    assert out["truncatedSecurities"] == ["A.SZ", "B.SZ"]


def test_merge_parts_refuses_a_grouped_part_without_a_security_code_column():
    # Several securities in one answer without the column that says whose row is whose
    # cannot be merged in input order, or attributed at all.
    with pytest.raises(ApiError, match="securityCode") as excinfo:
        merge_parts(
            [_part([[1], [2]], ["close"])], securities=[["A.SZ", "B.SZ"]], cap=6000, label="q"
        )
    assert excinfo.value.structural is True


def test_fetch_per_security_hands_each_group_to_fetch():
    seen: list[list[str]] = []

    def fetch(codes: list[str]) -> dict[str, Any]:
        seen.append(codes)
        return _part([[c] for c in codes], ["securityCode"])

    parts = fetch_per_security([["A", "B"], ["C"]], fetch=fetch, label="q", concurrency=1)
    assert seen == [["A", "B"], ["C"]]
    assert [p["list"] for p in parts] == [[["A"], ["B"]], [["C"]]]


@pytest.mark.anyio
async def test_fetch_per_security_async_hands_each_group_to_fetch():
    seen: list[list[str]] = []

    async def fetch(codes: list[str]) -> dict[str, Any]:
        seen.append(codes)
        return _part([[c] for c in codes], ["securityCode"])

    parts = await fetch_per_security_async(
        [["A", "B"], ["C"]], fetch=fetch, label="q", concurrency=1
    )
    assert seen == [["A", "B"], ["C"]]
    assert len(parts) == 2
