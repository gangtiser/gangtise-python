import pytest

from gangtise_openapi._endpoints import EndpointDef, Pagination
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._pagination import collect_paginated


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


def test_fanout_page_failure_raises_bare_api_error():
    # A non-first page failing in the thread-pool fan-out must surface as the
    # bare ApiError (sync/async parity contract; async sibling in
    # test_pagination_async.py).
    def fetch(body):
        if body["from"] == 0:
            return {"total": 12, "list": [{"i": j} for j in range(5)]}
        raise ApiError("boom on page 2", code="100001")

    with pytest.raises(ApiError) as excinfo:
        collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert excinfo.value.code == "100001"


def test_max_pages_cap():
    # total=10000 with maxPageSize=1 would request 10000 pages; we cap at 1000.
    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 10000, "list": [{"i": j} for j in range(f, f + s)]}

    out = collect_paginated(_ep(max_page_size=1), body={}, fetch=fetch, concurrency=2)
    assert len(out["list"]) == 1000
