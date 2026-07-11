import pytest

from gangtise_openapi._endpoints import EndpointDef, Pagination
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._pagination import _build_remaining_requests, collect_paginated


def _ep(max_page_size: int = 50) -> EndpointDef:
    return EndpointDef(
        key="x",
        method="POST",
        path="/p",
        kind="json",
        description="d",
        pagination=Pagination(max_page_size=max_page_size),
    )


def test_single_page_when_total_fits():
    pages_seen: list[tuple[int, int]] = []

    def fetch(body):
        pages_seen.append((body["from"], body["size"]))
        return {"total": 3, "list": [{"i": 1}, {"i": 2}, {"i": 3}]}

    out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"total": 3, "list": [{"i": 1}, {"i": 2}, {"i": 3}]}
    assert pages_seen == [(0, 50)]


def test_fetches_remaining_pages_concurrently():
    pages_seen: list[tuple[int, int]] = []

    def fetch(body):
        pages_seen.append((body["from"], body["size"]))
        if body["from"] == 0:
            return {"total": 12, "list": [{"i": j} for j in range(5)]}
        # remaining pages
        f, s = body["from"], body["size"]
        return {"total": 12, "list": [{"i": j} for j in range(f, f + s)]}

    out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert out["total"] == 12
    assert [row["i"] for row in out["list"]] == list(range(12))
    assert "partial" not in out  # all pages succeeded


def test_requested_size_truncates_collected():
    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 100, "list": [{"i": j} for j in range(f, f + s)]}

    out = collect_paginated(_ep(max_page_size=5), body={"size": 7}, fetch=fetch, concurrency=3)
    assert len(out["list"]) == 7
    assert [row["i"] for row in out["list"]] == list(range(7))


def test_non_paginated_response_returned_verbatim():
    def fetch(body):
        return {"total": 0, "list": []}

    out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"total": 0, "list": []}


def test_unexpected_shape_returned_as_is():
    def fetch(body):
        return {"unexpected": "shape"}

    out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"unexpected": "shape"}


def test_invalid_from_raises():
    def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        collect_paginated(_ep(), body={"from": -1}, fetch=fetch, concurrency=3)


def test_invalid_size_raises():
    def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        collect_paginated(_ep(), body={"size": 0}, fetch=fetch, concurrency=3)


def test_bool_paging_args_rejected():
    # bool is an int subclass; from=True / size=True must raise, not slip through as 1.
    def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        collect_paginated(_ep(), body={"from": True}, fetch=fetch, concurrency=3)
    with pytest.raises(ValidationError):
        collect_paginated(_ep(), body={"size": True}, fetch=fetch, concurrency=3)


def test_fanout_page_failure_returns_partial():
    # TS v0.20.0 fail-soft: a non-first page failing in the fan-out must NOT
    # discard the pages already fetched; the result is tagged `partial` with the
    # failed page specs (async sibling in test_pagination_async.py).
    def fetch(body):
        if body["from"] == 0:
            return {"total": 12, "list": [{"i": j} for j in range(5)]}
        raise ApiError("boom on a later page", code="100001")

    with pytest.warns(UserWarning, match="results are partial"):
        out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert out["total"] == 12
    assert out["partial"] is True
    assert [row["i"] for row in out["list"]] == list(range(5))  # only first page survived
    assert out["failedPages"]
    assert all({"from", "size"} <= set(p) for p in out["failedPages"])


def test_build_remaining_requests_caps_during_generation():
    # The cap must apply while generating requests, not after materializing a list
    # proportional to a corrupt server total.
    requests, dropped = _build_remaining_requests(
        initial={},
        next_from=1,
        end_from=10**12,
        max_page_size=1,
        max_pages=3,
    )
    assert requests == [{"from": 1, "size": 1}, {"from": 2, "size": 1}]
    assert dropped > 0


def test_max_pages_cap():
    # total=10000 with maxPageSize=1 would request 10000 pages; we cap at 1000 and
    # emit a UserWarning so the truncation is visible on the default DataFrame path.
    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 10000, "list": [{"i": j} for j in range(f, f + s)]}

    with pytest.warns(UserWarning, match="capped at MAX_PAGES"):
        out = collect_paginated(_ep(max_page_size=1), body={}, fetch=fetch, concurrency=2)
    assert len(out["list"]) == 1000
    assert out["partial"] is True  # cap-truncation is machine-readable, not just a warning


def test_fanout_total_drift_flags_partial():
    # Server reports total=12 but the data runs out early (a short mid page). No page
    # FAILED, yet collected < total → flag partial + warn (TS client.ts:242 parity).
    def fetch(body):
        f, s = body["from"], body["size"]
        # Server actually holds only 8 rows despite reporting total=12.
        return {"total": 12, "list": [{"i": j} for j in range(f, min(f + s, 8))]}

    with pytest.warns(UserWarning, match="end of data"):
        out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert out["partial"] is True
    assert "failedPages" not in out  # a drift shortfall, not a page failure
    assert [r["i"] for r in out["list"]] == list(range(8))


def test_empty_first_page_with_nonzero_total_does_not_refetch_same_offset():
    calls = 0

    def fetch(body):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"total": 100, "list": []}
        raise AssertionError("empty first page should stop instead of repeating from=0")

    with pytest.warns(UserWarning, match="short first page"):
        out = collect_paginated(_ep(max_page_size=50), body={}, fetch=fetch, concurrency=2)
    assert calls == 1
    assert out["partial"] is True
    assert out["list"] == []


def test_fanout_malformed_page_is_partial():
    # A 2xx fan-out page with a malformed shape (no total/list) must not silently drop
    # rows: it's recorded as a failed page so the result is tagged partial — symmetry
    # with the exception path.
    def fetch(body):
        if body["from"] == 0:
            return {"total": 12, "list": [{"i": j} for j in range(5)]}
        return {"unexpected": "shape"}  # 2xx but not a paginated-list shape

    with pytest.warns(UserWarning, match="results are partial"):
        out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert out["partial"] is True
    assert out["failedPages"]
    assert [r["i"] for r in out["list"]] == list(range(5))  # only the valid first page


def test_first_page_shape_drift_warns_and_returns_as_is(config):
    # A paginated endpoint answering a non-{total,list} shape silently degrades
    # fetch-all to a single page — surface it (TS v0.27.0 parity).
    from gangtise_openapi._endpoints import lookup

    endpoint = lookup("insight.summary.list")
    drifted = {"total": "123", "list": []}
    with pytest.warns(UserWarning, match="unexpected shape"):
        out = collect_paginated(endpoint, body={}, fetch=lambda body: drifted, concurrency=2)
    assert out is drifted
