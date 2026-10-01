"""Auto-pagination guards ported from CLI v0.41.0 - v0.44.0 (core/client.ts
``requestPaginated``), each run against BOTH collectors: the ``collect`` fixture is
parametrized over ``collect_paginated`` and ``collect_paginated_async``.

- ``{total: 0, list: null}`` is an empty list, nothing looser (v0.43.0 ②)
- rows repeated / changed across page boundaries, by ``row_id`` (v0.43.0 ②, v0.43.1 ②)
- the declared offset window ``max_window`` (v0.41.0 ⑤, v0.43.0 ②)
- a total-cap probe the server refuses (v0.43.0 ②)
- the per-row credit guard and its one-row probe (v0.43.0 ①, v0.44.0 ⑧)
- the fan-out: no head-of-line blocking, no new page after a hard failure
"""

from __future__ import annotations

import functools
import json
import threading

import anyio
import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import Billing, EndpointDef, Pagination, lookup
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._pagination import collect_paginated, collect_paginated_async


@pytest.fixture(params=["sync", "async"])
def collect(request):
    """Run one collector with a plain fetch stub (wrapped in a coroutine for async)."""

    def run(endpoint, *, fetch, body=None, concurrency=3, allow_costly=False):
        kwargs = {"body": body or {}, "concurrency": concurrency, "allow_costly": allow_costly}
        if request.param == "sync":
            return collect_paginated(endpoint, fetch=fetch, **kwargs)

        async def afetch(page_body):
            return fetch(page_body)

        return anyio.run(
            functools.partial(collect_paginated_async, endpoint, fetch=afetch, **kwargs)
        )

    return run


class Server:
    """Serves ``total`` rows page by page and records every ``(from, size)`` asked for.
    ``edit(from_, rows)`` may rewrite a page before it is returned."""

    def __init__(self, total, row=lambda i: {"id": i}, edit=None):
        self.total = total
        self.row = row
        self.edit = edit
        self.sent: list[tuple[int, int]] = []
        self._lock = threading.Lock()

    def __call__(self, body):
        with self._lock:
            self.sent.append((body["from"], body["size"]))
        start, size = body["from"], body["size"]
        rows = [self.row(i) for i in range(start, min(start + size, self.total))]
        if self.edit is not None:
            self.edit(start, rows)
        return {"total": self.total, "list": rows}


def _messages(record) -> str:
    return "\n".join(str(w.message) for w in record)


def _endpoint(**kw) -> EndpointDef:
    pagination = Pagination(
        max_page_size=kw.pop("max_page_size", 10), max_window=kw.pop("max_window", None)
    )
    return EndpointDef(
        key="x.list",
        method="POST",
        path="/p",
        kind="json",
        description="d",
        pagination=pagination,
        **kw,
    )


# ─── {total: 0, list: null} (CLI v0.43.0 ②) ───


def test_a_first_page_of_total_0_with_list_null_is_an_empty_result(collect):
    # summary / announcement lists answer "nothing matched" with list: null (probed
    # 2026-09-25). An empty result, not a broken one: no warning, no partial.
    out = collect(lookup("insight.summary.list"), fetch=lambda b: {"total": 0, "list": None})
    assert out == {"total": 0, "list": []}


@pytest.mark.parametrize(
    "broken",
    [
        {"total": 3, "list": None},
        {"total": "0", "list": None},
        {"total": 0},
        {"total": False, "list": None},
    ],
)
def test_a_null_list_under_any_other_total_stays_shape_broken(collect, broken):
    with pytest.warns(UserWarning, match="unexpected shape"):
        out = collect(lookup("insight.summary.list"), fetch=lambda b: dict(broken))
    assert out == {**broken, "partial": True}


def test_a_later_page_of_total_0_with_list_null_is_total_drift_not_a_failed_page(collect):
    # The page carries no rows to refetch: calling it failed would send the caller to
    # re-pull a page that is empty by the server's own count.
    def fetch(body):
        if body["from"] == 0:
            return {"total": 100, "list": [{"n": i} for i in range(50)]}
        return {"total": 0, "list": None}

    with pytest.warns(UserWarning) as record:
        out = collect(lookup("vault.drive.list"), fetch=fetch)
    assert len(out["list"]) == 50
    assert out["partial"] is True
    assert "failedPages" not in out
    assert "'total' changed across pages" in _messages(record)
    assert "not fetched" not in _messages(record)


# ─── rows repeated across page boundaries (CLI v0.43.0 ②, v0.43.1 ②) ───

OPINION = "insight.opinion.list"  # row_id chiefOpinionId, 1 credit/row, pages of 50


def _shifted_pages(second_page_head):
    """Page 2 (from 50) starts with page 1's last row again and skips row 51: a
    same-timestamp group reordered between the two requests (server-side P2-26)."""

    def edit(start, rows):
        if start == 50 and rows:
            rows[0] = second_page_head(50)

    return Server(
        100, row=lambda i: {"chiefOpinionId": str(i + 1), "title": f"t{i + 1}"}, edit=edit
    )


def test_drops_a_whole_row_repeat_and_marks_duplicate_rows(collect):
    server = _shifted_pages(lambda last: {"chiefOpinionId": str(last), "title": f"t{last}"})
    with pytest.warns(UserWarning) as record:
        out = collect(lookup(OPINION), fetch=server)
    assert len(out["list"]) == 99
    assert len({r["chiefOpinionId"] for r in out["list"]}) == 99
    assert out["duplicateRows"] == 1
    assert out["partial"] is True
    notes = _messages(record)
    assert "more than once" in notes and "sort order is not unique" in notes
    assert "shorter time range" in notes
    # Every row arrived, so no page came back short, and the total is still checked.
    assert "end of data" not in notes
    assert (100, 1) in server.sent


def test_a_total_on_the_declared_window_is_still_capped_when_repeats_made_it_short(collect):
    # vault.wechat-message.list declares a 10000-row window. A repeat drops the row count
    # below total; the cap on total is the larger loss and must not be hidden by it.
    def edit(start, rows):
        if start == 50:
            rows[0] = {"msgId": "50"}

    server = Server(10000, row=lambda i: {"msgId": str(i + 1)}, edit=edit)
    with pytest.warns(UserWarning) as record:
        out = collect(lookup("vault.wechat-message.list"), fetch=server)
    assert len(out["list"]) == 9999
    assert out["duplicateRows"] == 1
    assert out["totalCapped"] is True
    assert out["partial"] is True
    assert "equals its 10000-row offset window" in _messages(record)
    assert all(start + size <= 10000 for start, size in server.sent)  # no probe past it


def test_keeps_both_versions_of_an_id_that_changed_between_pages(collect):
    server = _shifted_pages(
        lambda last: {"chiefOpinionId": str(last), "title": "the same row, edited in between"}
    )
    with pytest.warns(UserWarning, match="later page with different content") as record:
        out = collect(lookup(OPINION), fetch=server)
    assert len(out["list"]) == 100
    assert "duplicateRows" not in out
    assert out["changedRows"] == 1
    assert out["partial"] is True
    assert "chiefOpinionId" in _messages(record)


def _boundary_rows(id_field, at):
    """Three pages of 50 (total 150); ``at(from)`` replaces the row at the page boundary:
    the last row of the first page, the first row of each later page."""

    def edit(start, rows):
        row = at(start)
        if row is not None and rows:
            rows[49 if start == 0 else 0] = row

    return Server(150, row=lambda i: {id_field: str(i + 1), "title": f"t{i + 1}"}, edit=edit)


def test_drops_a_repeat_of_an_ids_later_version_not_only_of_its_first(collect):
    server = _boundary_rows(
        "chiefOpinionId",
        lambda start: {"chiefOpinionId": "a", "title": "v1" if start == 0 else "v2"},
    )
    with pytest.warns(UserWarning):
        out = collect(lookup(OPINION), fetch=server)
    assert [r["title"] for r in out["list"] if r["chiefOpinionId"] == "a"] == ["v1", "v2"]
    assert out["duplicateRows"] == 1
    assert out["changedRows"] == 1
    assert out["partial"] is True
    assert "totalCapped" not in out


def test_the_same_later_version_repeat_is_partial_on_an_unverified_id_list(collect):
    endpoint = lookup("insight.independent-opinion.list")
    assert endpoint.row_id_unverified
    server = _boundary_rows(
        "independentOpinionId",
        lambda start: {"independentOpinionId": "a", "title": "v1" if start == 0 else "v2"},
    )
    with pytest.warns(UserWarning) as record:
        out = collect(endpoint, fetch=server, allow_costly=True)
    assert len([r for r in out["list"] if r["independentOpinionId"] == "a"]) == 2
    assert out["duplicateRows"] == 1
    assert "changedRows" not in out
    assert out["partial"] is True
    assert "totalCapped" not in out
    assert "different content" not in _messages(record)


def _second_page_opens(first, second):
    """Page 1 ends with id "a" as v1; page 2 opens with the two versions given."""

    def edit(start, rows):
        if start == 0:
            rows[49] = {"chiefOpinionId": "a", "title": "v1"}
        if start == 50:
            rows[0] = {"chiefOpinionId": "a", "title": first}
            rows[1] = {"chiefOpinionId": "a", "title": second}

    return Server(
        100, row=lambda i: {"chiefOpinionId": str(i + 1), "title": f"t{i + 1}"}, edit=edit
    )


def test_a_later_version_repeated_on_one_page_is_one_changed_row_and_one_repeat(collect):
    with pytest.warns(UserWarning):
        out = collect(lookup(OPINION), fetch=_second_page_opens("v2", "v2"))
    assert len(out["list"]) == 99
    assert out["duplicateRows"] == 1
    assert out["changedRows"] == 1
    assert out["partial"] is True


def test_two_versions_of_an_id_on_one_page_mean_it_is_no_row_key(collect):
    # ...even when one of them repeats an earlier page: the repeat is still dropped.
    with pytest.warns(UserWarning) as record:
        out = collect(lookup(OPINION), fetch=_second_page_opens("v2", "v1"))
    assert len(out["list"]) == 99
    assert out["duplicateRows"] == 1
    assert "changedRows" not in out
    assert "different content" not in _messages(record)


def test_a_repeat_whose_keys_come_in_another_order_is_the_same_row(collect):
    def at(start):
        if start == 0:
            return {"chiefOpinionId": "a", "title": "t", "meta": {"x": 1, "y": [1, 2]}}
        if start == 50:
            return {"meta": {"y": [1, 2], "x": 1}, "title": "t", "chiefOpinionId": "a"}
        return None

    with pytest.warns(UserWarning, match="more than once"):
        out = collect(lookup(OPINION), fetch=_boundary_rows("chiefOpinionId", at))
    assert len([r for r in out["list"] if r["chiefOpinionId"] == "a"]) == 1
    assert out["duplicateRows"] == 1
    assert "changedRows" not in out
    assert "totalCapped" not in out


def test_array_order_is_kept_when_comparing_rows(collect):
    # Only object keys are sorted: a list in another order is another version.
    def at(start):
        if start == 0:
            return {"chiefOpinionId": "a", "tags": [1, 2]}
        if start == 50:
            return {"chiefOpinionId": "a", "tags": [2, 1]}
        return None

    with pytest.warns(UserWarning, match="different content"):
        out = collect(lookup(OPINION), fetch=_boundary_rows("chiefOpinionId", at))
    assert out["changedRows"] == 1
    assert "duplicateRows" not in out


def test_an_id_one_page_carries_twice_with_different_content_marks_nothing(collect):
    # One response is a consistent snapshot, so two different rows under one id there
    # mean the declared field does not identify a row on this list.
    def edit(start, rows):
        if start == 0:
            rows[1] = {"chiefOpinionId": "1", "title": "another row under id 1"}
        if start == 50:
            rows[0] = {"chiefOpinionId": "50", "title": "another row under id 50"}

    server = Server(
        100, row=lambda i: {"chiefOpinionId": str(i + 1), "title": f"t{i + 1}"}, edit=edit
    )
    out = collect(lookup(OPINION), fetch=server)  # no warning expected
    assert len(out["list"]) == 100
    assert "changedRows" not in out
    assert "partial" not in out


def test_no_changed_row_is_counted_on_an_unverified_id_list(collect):
    # insight.roadshow.list declares `id` from the response description only: a pair of
    # records sharing it across a page boundary must not mark every run partial.
    endpoint = lookup("insight.roadshow.list")
    assert endpoint.row_id == "id" and endpoint.row_id_unverified

    def edit(start, rows):
        if start == 50:
            rows[0] = {"id": "50", "title": "another record under id 50"}

    server = Server(100, row=lambda i: {"id": str(i + 1), "title": f"t{i + 1}"}, edit=edit)
    out = collect(endpoint, fetch=server, allow_costly=True)
    assert len(out["list"]) == 100
    assert "changedRows" not in out
    assert "partial" not in out


def test_a_list_without_a_declared_row_id_is_left_untouched(collect):
    # insight.qa.list rows carry no id field, so nothing is declared and nothing dropped.
    endpoint = lookup("insight.qa.list")
    assert endpoint.row_id is None
    out = collect(endpoint, fetch=lambda b: {"total": 2, "list": [{"q": "q"}, {"q": "q"}]})
    assert out == {"total": 2, "list": [{"q": "q"}, {"q": "q"}]}


def test_rows_without_the_id_are_always_kept(collect):
    # A null or missing id identifies nothing: identical rows are all kept.
    server = Server(100, row=lambda i: {"chiefOpinionId": None} if i % 2 else {"title": "t"})
    out = collect(lookup(OPINION), fetch=server)
    assert len(out["list"]) == 100
    assert "duplicateRows" not in out


def test_a_repeat_in_a_bounded_fetch_leaves_it_short_without_the_generic_warning(collect):
    # size=60: page 1 of 50, then 10 rows from 50 — whose first repeats row 50.
    server = _shifted_pages(lambda last: {"chiefOpinionId": str(last), "title": f"t{last}"})
    with pytest.warns(UserWarning) as record:
        out = collect(lookup(OPINION), fetch=server, body={"size": 60})
    assert len(out["list"]) == 59
    assert out["duplicateRows"] == 1
    assert out["partial"] is True
    assert "end of data" not in _messages(record)
    assert server.sent == [(0, 50), (50, 10)]  # a bounded fetch spends no total-cap probe


# ─── the offset window (CLI v0.41.0 ⑤, v0.43.0 ②) ───


@pytest.mark.parametrize("start", [100, 150])
def test_a_from_at_or_past_the_window_is_refused_before_any_request(collect, start):
    def fetch(body):
        raise AssertionError("no request may be sent")

    with pytest.raises(ValidationError, match="up to offset 100"):
        collect(_endpoint(max_window=100), fetch=fetch, body={"from": start})


def test_the_registry_window_is_enforced(collect):
    with pytest.raises(ValidationError, match="from=10000 is past it"):
        collect(lookup("vault.wechat-message.list"), fetch=Server(0), body={"from": 10000})


def test_pages_are_never_planned_past_the_window_and_cut_rows_are_partial(collect):
    server = Server(250)
    with pytest.warns(UserWarning, match="150 of the 250 requested rows lie past it") as record:
        out = collect(_endpoint(max_window=100), fetch=server)
    assert [r["id"] for r in out["list"]] == list(range(100))
    assert out["partial"] is True
    assert "totalCapped" not in out  # the window cut is reported instead
    assert all(start + size <= 100 for start, size in server.sent)
    assert len(record) == 1


def test_a_late_from_shrinks_the_first_page_to_the_window(collect):
    server = Server(250)
    with pytest.warns(UserWarning, match="150 of the 155 requested rows"):
        out = collect(_endpoint(max_window=100), fetch=server, body={"from": 95})
    assert server.sent == [(95, 5)]
    assert [r["id"] for r in out["list"]] == [95, 96, 97, 98, 99]
    assert out["partial"] is True


def test_an_explicit_size_past_the_window_is_cut_at_it(collect):
    server = Server(250)
    with pytest.warns(UserWarning, match="50 of the 150 requested rows"):
        out = collect(_endpoint(max_window=100), fetch=server, body={"size": 150})
    assert len(out["list"]) == 100
    assert out["partial"] is True


def test_a_total_equal_to_the_window_is_capped_without_a_probe(collect):
    server = Server(100)
    with pytest.warns(UserWarning, match="equals its 100-row offset window") as record:
        out = collect(_endpoint(max_window=100), fetch=server)
    assert len(out["list"]) == 100
    assert out["totalCapped"] is True
    assert out["partial"] is True
    assert "TRUNCATED at 100 rows" in _messages(record)
    assert all(start < 100 for start, _ in server.sent)


def test_a_late_from_on_a_total_at_the_window_is_capped_too(collect):
    # The first-page-complete exit (from=95 against total=100) shares the check.
    server = Server(100)
    with pytest.warns(UserWarning, match="offset window"):
        out = collect(_endpoint(max_window=100), fetch=server, body={"from": 95})
    assert server.sent == [(95, 5)]
    assert out["totalCapped"] is True


def test_a_total_just_inside_the_window_is_still_probed(collect):
    # total + 1 <= max_window: the row at `total` can be asked for.
    server = Server(99)
    out = collect(_endpoint(max_window=100), fetch=server)
    assert len(out["list"]) == 99
    assert "partial" not in out
    assert (99, 1) in server.sent


# ─── a total-cap probe the server refuses (CLI v0.43.0 ②) ───


def _probe_answers(total, probe):
    """``total`` rows in pages; the request at ``from == total`` gets ``probe()``."""
    server = Server(total)

    def fetch(body):
        if body["from"] >= total:
            return probe()
        return server(body)

    return fetch


@pytest.mark.parametrize("code", ["140002", "100006"])
def test_a_probe_refused_with_an_offset_code_marks_the_total_capped(collect, code):
    def refuse():
        raise ApiError("业务处理失败", code=code, status_code=500)

    with pytest.warns(UserWarning, match="TRUNCATED") as record:
        out = collect(lookup(OPINION), fetch=_probe_answers(100, refuse))
    assert len(out["list"]) == 100
    assert out["partial"] is True
    assert out["totalCapped"] is True
    assert code in _messages(record)


@pytest.mark.parametrize(
    "error",
    [
        ApiError("系统错误", code="999999", status_code=503),
        ApiError("rate limited", code="903301"),
        ApiError("no code"),
        httpx.ConnectError("socket hang up"),
    ],
)
def test_any_other_probe_failure_stays_silent(collect, error):
    def fail():
        raise error

    out = collect(lookup(OPINION), fetch=_probe_answers(100, fail))  # no warning expected
    assert len(out["list"]) == 100
    assert "partial" not in out


def test_a_refused_probe_after_a_late_from_marks_the_total_capped(collect):
    # from=90 against total=100 is one FULL page: the first-page-complete exit (a short
    # page exits through the short-first-page branch, which probes nothing).
    def refuse():
        raise ApiError("offset too deep", code="100006")

    with pytest.warns(UserWarning, match="refused the row right after it"):
        out = collect(_endpoint(), fetch=_probe_answers(100, refuse), body={"from": 90})
    assert out["totalCapped"] is True


# ─── the per-row credit guard (CLI v0.43.0 ①, v0.44.0 ⑧) ───

RESEARCH = "insight.research.list"  # 0.1 per row, pages of 50: guard at 10000 rows


def test_fetches_everything_at_exactly_the_guard_and_refuses_just_past_it(collect):
    assert len(collect(lookup(RESEARCH), fetch=Server(10000))["list"]) == 10000

    server = Server(10001)
    with pytest.raises(ValidationError, match=r"1000\.1 credits.*size=N.*confirm=True") as info:
        collect(lookup(RESEARCH), fetch=server)
    assert server.sent == [(0, 50)]  # refused after the first page, before any fan-out
    assert "all 10001 rows" in str(info.value)
    assert "0.1 per row" in str(info.value)
    assert "Only 50 row(s) were fetched" in str(info.value)


def test_a_costly_first_page_learns_the_total_from_one_row(collect):
    # ai.security-clue.list: 5 per row, pages of 500 — a full first page would be 2500.
    server = Server(3000)
    with pytest.raises(ValidationError, match="Only 1 row") as info:
        collect(lookup("ai.security-clue.list"), fetch=server)
    assert server.sent == [(0, 1)]
    assert "15000 credits" in str(info.value)

    # insight.roadshow.list within the guard (40 rows at 20 = 800): the fetch starts over
    # on the usual page boundaries rather than continuing from offset 1.
    server = Server(40)
    out = collect(lookup("insight.roadshow.list"), fetch=server)
    assert len(out["list"]) == 40
    assert server.sent == [(0, 1), (0, 50)]


@pytest.mark.parametrize(
    "answer",
    [
        {"total": 1, "list": [{"id": 0}]},
        {"total": 0, "list": []},
        {"total": 0, "list": None},
    ],
)
def test_the_probe_alone_answers_a_result_of_one_row_or_none(collect, answer):
    # ai.hot-topic: 50 per report, pages of 20 — probed first. A one-row result is the
    # commonest query and must not be paid for twice.
    sent = []

    def fetch(body):
        sent.append((body["from"], body["size"]))
        return dict(answer)

    out = collect(lookup("ai.hot-topic"), fetch=fetch)
    assert sent == [(0, 1)]
    assert out["list"] == (answer["list"] or [])
    assert "partial" not in out


def test_a_probe_with_more_rows_than_its_total_leaves_is_not_the_result(collect):
    sent = []

    def fetch(body):
        sent.append((body["from"], body["size"]))
        return {"total": 0, "list": [{"id": 1}]}

    collect(lookup("ai.hot-topic"), fetch=fetch)
    assert sent == [(0, 1), (0, 20)]


def test_a_probe_of_unexpected_shape_is_reported_without_buying_a_page(collect):
    sent = []

    def fetch(body):
        sent.append((body["from"], body["size"]))

    with pytest.warns(UserWarning, match="unexpected shape"):
        out = collect(lookup("ai.hot-topic"), fetch=fetch)
    assert out is None
    assert sent == [(0, 1)]


def test_a_failing_credit_probe_fails_the_call(collect):
    def fetch(body):
        raise ApiError("rate limited", code="903301")

    with pytest.raises(ApiError, match="rate limited"):
        collect(lookup("ai.hot-topic"), fetch=fetch)


def test_only_the_rows_left_after_from_are_priced(collect):
    # 20000 rows from offset 10500: 9500 to fetch = 950 credits, under the guard — though
    # the whole list (2000 credits) is over it.
    out = collect(lookup(RESEARCH), fetch=Server(20000), body={"from": 10500})
    assert len(out["list"]) == 9500


def test_a_bounded_a_confirmed_and_a_free_fetch_are_left_alone(collect):
    assert len(collect(lookup(RESEARCH), fetch=Server(20000), body={"size": 120})["list"]) == 120
    assert len(collect(lookup(RESEARCH), fetch=Server(20000), allow_costly=True)["list"]) == 20000
    assert lookup("vault.drive.list").billing is None
    assert len(collect(lookup("vault.drive.list"), fetch=Server(20000))["list"]) == 20000


def test_a_size_large_enough_to_pass_the_guard_is_priced_as_well(collect):
    # CLI v0.44.0: `size=100000` as "everything" no longer walks around the guard.
    server = Server(20000)
    with pytest.raises(ValidationError, match=r"20000 rows \(size=100000\)") as info:
        collect(lookup(RESEARCH), fetch=server, body={"size": 100000})
    assert "Pass a smaller size" in str(info.value)
    assert server.sent == [(0, 50)]
    # The same size against a total the guard allows is priced by min(size, total)...
    assert len(collect(lookup(RESEARCH), fetch=Server(5000), body={"size": 100000})["list"]) == 5000
    # ...and a size at or under the guard on its own is never priced.
    assert (
        len(collect(lookup(RESEARCH), fetch=Server(20000), body={"size": 10000})["list"]) == 10000
    )


def test_the_guard_prices_only_the_rows_inside_the_window(collect):
    # insight.highlight.list: 5 per row, a 10000-row window, pages of 50 (250 > 50: probed).
    endpoint = lookup("insight.highlight.list")
    server = Server(50000)
    with pytest.raises(ValidationError, match=r"all 10000 rows.*50000 credits"):
        collect(endpoint, fetch=server)
    assert server.sent == [(0, 1)]


def test_an_endpoint_billed_per_call_is_not_guarded(collect):
    endpoint = _endpoint(billing=Billing(per="call", price=500))
    out = collect(endpoint, fetch=Server(300))
    assert len(out["list"]) == 300


# ─── the fan-out ───


def test_no_new_page_is_started_after_a_hard_failure(collect):
    server = Server(100)

    def fetch(body):
        if body["from"] == 20:
            raise ApiError("rate limited", code="903301")
        return server(body)

    with pytest.warns(UserWarning, match="rate limited"):
        out = collect(_endpoint(), fetch=fetch, concurrency=1)
    assert [start for start, _ in server.sent] == [0, 10]
    assert [p["from"] for p in out["failedPages"]] == [20, 30, 40, 50, 60, 70, 80, 90]
    assert [r["id"] for r in out["list"]] == list(range(20))


def test_a_stalled_page_does_not_hold_back_the_pages_behind_it():
    # The page at from=10 waits until every later page has been fetched: it only returns
    # if the other workers keep going meanwhile (TS v0.42.0 ⑦ widened its window for this).
    server = Server(200)
    later_pages_done = threading.Event()
    done = []

    def fetch(body):
        if body["from"] == 10:
            later_pages_done.wait(timeout=5)
        elif body["from"] > 10:
            done.append(body["from"])
            if len(done) == 18:
                later_pages_done.set()
        return server(body)

    out = collect_paginated(_endpoint(), body={}, fetch=fetch, concurrency=5)
    assert later_pages_done.is_set()
    assert [r["id"] for r in out["list"]] == list(range(200))


@pytest.mark.anyio
async def test_a_stalled_page_does_not_hold_back_the_pages_behind_it_async():
    server = Server(200)
    later_pages_done = anyio.Event()
    done = []

    async def fetch(body):
        if body["from"] == 10:
            with anyio.move_on_after(5):
                await later_pages_done.wait()
        elif body["from"] > 10:
            done.append(body["from"])
            if len(done) == 18:
                later_pages_done.set()
        return server(body)

    out = await collect_paginated_async(_endpoint(), body={}, fetch=fetch, concurrency=5)
    assert later_pages_done.is_set()
    assert [r["id"] for r in out["list"]] == list(range(200))


# ─── `_call(confirm=...)` reaches the guard ───


@pytest.fixture
def token_config(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key=None,
        secret_key=None,
        token="env-tok",
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
        page_concurrency=3,
    )


def _research_route(router, total):
    def answer(request):
        body = json.loads(request.content)
        start, size = body["from"], body["size"]
        rows = [{"reportId": str(i)} for i in range(start, min(start + size, total))]
        data = {"total": total, "list": rows}
        return httpx.Response(200, json={"code": "000000", "status": True, "data": data})

    return router.post(lookup(RESEARCH).path).mock(side_effect=answer)


def test_call_refuses_a_costly_fetch_unless_confirmed(token_config):
    with respx.mock(base_url="https://api.test") as router:
        route = _research_route(router, 10001)
        with GangtiseClient(_config=token_config) as client:
            with pytest.raises(ValidationError, match="confirm=True"):
                client._call(RESEARCH, body={})
            assert route.call_count == 1
            out = client._call(RESEARCH, body={}, confirm=True)
        assert len(out["list"]) == 10001


@pytest.mark.anyio
async def test_call_refuses_a_costly_fetch_unless_confirmed_async(token_config):
    with respx.mock(base_url="https://api.test") as router:
        route = _research_route(router, 10001)
        async with AsyncGangtiseClient(_config=token_config) as client:
            with pytest.raises(ValidationError, match="confirm=True"):
                await client._call(RESEARCH, body={})
            assert route.call_count == 1
            out = await client._call(RESEARCH, body={}, confirm=True)
        assert len(out["list"]) == 10001
