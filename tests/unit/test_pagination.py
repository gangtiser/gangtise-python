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
        # Honour `total`: a stub that yields rows for ANY `from` would make the
        # total-cap probe (which reads one row past the claimed end) see data and
        # correctly report the export as truncated.
        f, s = body["from"], body["size"]
        return {"total": 12, "list": [{"i": j} for j in range(f, min(f + s, 12))]}

    out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert out["total"] == 12
    assert [row["i"] for row in out["list"]] == list(range(12))
    assert "partial" not in out  # all pages succeeded
    # The last entry is the total-cap probe: one row at from == total.
    assert pages_seen[-1] == (12, 1)


def test_total_cap_probe_flags_a_capped_total():
    # Three opinion endpoints report a fixed total while rows keep coming past it.
    # A fetch-all then stops exactly at the cap with collected == total, so every
    # other completeness check passes and the truncated export looks complete.
    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 10, "list": [{"i": j} for j in range(f, f + s)]}

    with pytest.warns(UserWarning, match="server-side cap"):
        out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=3)
    assert out["partial"] is True
    assert out["totalCapped"] is True
    assert len(out["list"]) == 10


def test_total_cap_probe_skipped_for_a_bounded_request():
    # `--size`-style bounded pulls got exactly what they asked for; there is no
    # completeness claim to check, so no probe request is spent.
    pages_seen: list[tuple[int, int]] = []

    def fetch(body):
        pages_seen.append((body["from"], body["size"]))
        f, s = body["from"], body["size"]
        return {"total": 10, "list": [{"i": j} for j in range(f, f + s)]}

    out = collect_paginated(_ep(max_page_size=5), body={"size": 10}, fetch=fetch, concurrency=3)
    assert "totalCapped" not in out
    assert (10, 1) not in pages_seen


def test_total_cap_probe_failure_never_fails_the_pull():
    calls = {"n": 0}

    def fetch(body):
        calls["n"] += 1
        if body["from"] == 10:
            raise ApiError("probe blew up")
        f, s = body["from"], body["size"]
        return {"total": 10, "list": [{"i": j} for j in range(f, min(f + s, 10))]}

    out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=3)
    assert "partial" not in out
    assert len(out["list"]) == 10


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


def test_unexpected_shape_returned_as_is_but_marked_partial():
    # Fetch-all silently degraded to one page. A string `total` truncates the
    # result to page 1, which looks complete — worse than an obviously empty
    # payload — so the caller gets a machine-readable marker, not just a warning.
    def fetch(body):
        return {"unexpected": "shape"}

    with pytest.warns(UserWarning, match="unexpected shape"):
        out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"unexpected": "shape", "partial": True}


def test_non_dict_first_page_warns_without_a_marker():
    # `data: null` cannot carry a flag; the warning is the whole signal.
    def fetch(body):
        return None

    with pytest.warns(UserWarning, match="unexpected shape"):
        out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out is None


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
    # fetch-all to a single page — surface it (TS v0.27.0), and since v0.33.0 flag
    # it so a caller reading `partial` sees it too. A string `total` is the nastier
    # case: page 1 comes back looking like the whole answer.
    from gangtise_openapi._endpoints import lookup

    endpoint = lookup("insight.summary.list")
    drifted = {"total": "123", "list": []}
    with pytest.warns(UserWarning, match="unexpected shape"):
        out = collect_paginated(endpoint, body={}, fetch=lambda body: drifted, concurrency=2)
    assert out == {"total": "123", "list": [], "partial": True}
    assert drifted == {"total": "123", "list": []}  # caller's payload not mutated


def test_total_cap_probe_still_runs_on_a_no_replay_endpoint():
    # `ai.hot-topic` is the one endpoint that is both paginated and no-replay, and it
    # MUST still be probed. An earlier version skipped it, reading `no-replay` as a
    # per-call-billing marker; it is not one — it means "never resend a request the
    # server may already have executed", and the probe is a new request, not a resend.
    # hot-topic is priced per returned item, and the platform does not charge a
    # per-item endpoint for a query that finds nothing — so the gate saved no credits
    # while costing this endpoint its only truncation check.
    from gangtise_openapi._endpoints import lookup

    endpoint = lookup("ai.hot-topic")
    assert endpoint.pagination is not None and endpoint.retry == "no-replay"
    pages_seen: list[tuple[int, int]] = []

    def fetch(body):
        pages_seen.append((body["from"], body["size"]))
        f, s = body["from"], body["size"]
        rows = [{"i": j} for j in range(f, min(f + s, 40))]
        return {"total": 40, "list": rows}

    out = collect_paginated(endpoint, body={}, fetch=fetch, concurrency=3)
    assert "totalCapped" not in out  # honest total: the probe comes back empty
    assert (40, 1) in pages_seen  # ...but it WAS sent


def test_total_cap_probe_flags_a_capped_total_on_a_no_replay_endpoint():
    # The positive half: skipping the probe here used to make a truncated hot-topic
    # export indistinguishable from a complete one.
    from gangtise_openapi._endpoints import lookup

    endpoint = lookup("ai.hot-topic")

    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 40, "list": [{"i": j} for j in range(f, f + s)]}

    with pytest.warns(UserWarning, match="server-side cap"):
        out = collect_paginated(endpoint, body={}, fetch=fetch, concurrency=3)
    assert out["totalCapped"] is True
    assert out["partial"] is True


def test_total_cap_probe_still_runs_on_a_normal_billed_endpoint():
    # The counterpart: `insight.opinion.list` is where the capping was observed and
    # bills per row, so the probe must still fire there.
    from gangtise_openapi._endpoints import lookup

    endpoint = lookup("insight.opinion.list")
    assert endpoint.retry == "default"

    # total > one page: a single-page answer early-returns before the probe (same
    # as the CLI), so the fan-out has to actually run for this to exercise it.
    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 120, "list": [{"i": j} for j in range(f, f + s)]}

    with pytest.warns(UserWarning, match="server-side cap"):
        out = collect_paginated(endpoint, body={}, fetch=fetch, concurrency=3)
    assert out["totalCapped"] is True
