from __future__ import annotations

import sys
import warnings

import pytest

if sys.version_info < (3, 11):
    # Backport; already a transitive anyio dependency on Python 3.10.
    from exceptiongroup import ExceptionGroup

from gangtise_openapi._endpoints import EndpointDef, Pagination
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._pagination import collect_paginated_async, first_leaf_exception


def _ep(max_page_size: int = 50) -> EndpointDef:
    return EndpointDef(
        key="x",
        method="POST",
        path="/p",
        kind="json",
        description="d",
        pagination=Pagination(max_page_size=max_page_size),
    )


@pytest.mark.anyio
async def test_async_single_page():
    async def fetch(body):
        return {"total": 3, "list": [{"i": 1}, {"i": 2}, {"i": 3}]}

    out = await collect_paginated_async(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"total": 3, "list": [{"i": 1}, {"i": 2}, {"i": 3}]}


@pytest.mark.anyio
async def test_async_fans_out_concurrently():
    async def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 12, "list": [{"i": j} for j in range(f, f + s)]}

    out = await collect_paginated_async(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert [r["i"] for r in out["list"]] == list(range(12))
    assert "partial" not in out  # all pages succeeded


@pytest.mark.anyio
async def test_async_invalid_from_raises():
    async def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        await collect_paginated_async(_ep(), body={"from": -1}, fetch=fetch, concurrency=3)


@pytest.mark.anyio
async def test_async_fanout_page_failure_returns_partial():
    # TS v0.20.0 fail-soft: a non-first page failing must NOT discard pages
    # already fetched; the task group catches per-page and tags the result
    # `partial` (sync sibling: test_pagination.test_fanout_page_failure_returns_partial).
    async def fetch(body):
        if body["from"] == 0:
            return {"total": 12, "list": [{"i": j} for j in range(5)]}
        raise ApiError("boom on a later page", code="100001")

    with pytest.warns(UserWarning, match="results are partial"):
        out = await collect_paginated_async(
            _ep(max_page_size=5), body={}, fetch=fetch, concurrency=4
        )
    assert out["total"] == 12
    assert out["partial"] is True
    assert [r["i"] for r in out["list"]] == list(range(5))  # only first page survived
    assert out["failedPages"]
    assert all({"from", "size"} <= set(p) for p in out["failedPages"])


def test_first_leaf_exception_descends_nested_groups():
    leaf = ApiError("boom", code="100001")
    inner = ExceptionGroup("inner", [leaf, ApiError("other")])
    outer = ExceptionGroup("outer", [inner, ApiError("sibling")])
    assert first_leaf_exception(outer) is leaf


def test_first_leaf_exception_passes_through_plain_errors():
    err = ApiError("plain")
    assert first_leaf_exception(err) is err


@pytest.mark.anyio
async def test_async_max_pages_cap():
    # Mirrors the sync test_max_pages_cap: total=10000 with maxPageSize=1 would
    # request 10000 pages; we cap at 1000 and emit a visible UserWarning.
    async def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 10000, "list": [{"i": j} for j in range(f, f + s)]}

    with pytest.warns(UserWarning, match="capped at MAX_PAGES"):
        out = await collect_paginated_async(
            _ep(max_page_size=1), body={}, fetch=fetch, concurrency=2
        )
    assert len(out["list"]) == 1000


def _seq_ep(max_page_size: int = 50) -> EndpointDef:
    # Sequential mode (TS v0.21.0): no `total`, list key `chatRoomList` (wechat chatroom).
    return EndpointDef(
        key="vault.wechat-chatroom.list",
        method="POST",
        path="/p",
        kind="json",
        description="d",
        pagination=Pagination(
            max_page_size=max_page_size, sequential=True, list_key="chatRoomList"
        ),
    )


@pytest.mark.anyio
async def test_async_sequential_pages_until_short_page():
    pages_seen: list[tuple[int, int]] = []

    async def fetch(body):
        pages_seen.append((body["from"], body["size"]))
        f, s = body["from"], body["size"]
        return {"chatRoomList": [{"i": j} for j in range(f, min(f + s, 7))]}

    out = await collect_paginated_async(
        _seq_ep(max_page_size=3), body={}, fetch=fetch, concurrency=4
    )
    assert out == {"chatRoomList": [{"i": j} for j in range(7)]}
    assert pages_seen == [(0, 3), (3, 3), (6, 3)]  # 3,3,1 → short page stops


@pytest.mark.anyio
async def test_async_sequential_requested_size_truncates():
    async def fetch(body):
        f, s = body["from"], body["size"]
        return {"chatRoomList": [{"i": j} for j in range(f, f + s)]}

    out = await collect_paginated_async(
        _seq_ep(max_page_size=3), body={"size": 5}, fetch=fetch, concurrency=4
    )
    assert out == {"chatRoomList": [{"i": j} for j in range(5)]}


@pytest.mark.anyio
async def test_async_sequential_first_page_unexpected_shape():
    async def fetch(body):
        return {"unexpected": "shape"}

    out = await collect_paginated_async(_seq_ep(), body={}, fetch=fetch, concurrency=4)
    assert out == {"unexpected": "shape"}


@pytest.mark.anyio
async def test_async_sequential_later_page_shape_loss_is_partial():
    async def fetch(body):
        if body["from"] == 0:
            return {"chatRoomList": [{"i": j} for j in range(3)]}  # full page (size 3)
        return {"unexpected": "shape"}

    with pytest.warns(UserWarning, match="results are partial"):
        out = await collect_paginated_async(
            _seq_ep(max_page_size=3), body={}, fetch=fetch, concurrency=4
        )
    assert out == {"chatRoomList": [{"i": j} for j in range(3)]}


@pytest.mark.anyio
async def test_async_sequential_invalid_size_raises():
    async def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        await collect_paginated_async(_seq_ep(), body={"size": 0}, fetch=fetch, concurrency=4)


@pytest.mark.anyio
async def test_async_sequential_no_false_cap_when_requested_size_filled_exactly(monkeypatch):
    # Async sibling of test_sequential_no_false_cap_when_requested_size_filled_exactly.
    monkeypatch.setattr("gangtise_openapi._pagination.MAX_PAGES", 3)

    async def fetch(body):
        f, s = body["from"], body["size"]
        return {"chatRoomList": [{"i": j} for j in range(f, f + s)]}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = await collect_paginated_async(
            _seq_ep(max_page_size=2), body={"size": 6}, fetch=fetch, concurrency=4
        )
    assert out == {"chatRoomList": [{"i": j} for j in range(6)]}
    assert not caught, [str(w.message) for w in caught]


@pytest.mark.anyio
async def test_async_sequential_cap_warns_when_truly_truncated(monkeypatch):
    monkeypatch.setattr("gangtise_openapi._pagination.MAX_PAGES", 3)

    async def fetch(body):
        f, s = body["from"], body["size"]
        return {"chatRoomList": [{"i": j} for j in range(f, f + s)]}  # never short

    with pytest.warns(UserWarning, match="MAX_PAGES"):
        out = await collect_paginated_async(
            _seq_ep(max_page_size=2), body={}, fetch=fetch, concurrency=4
        )
    assert len(out["chatRoomList"]) == 6  # 3 pages * 2 rows, then capped


@pytest.mark.anyio
async def test_async_fanout_malformed_page_is_partial():
    # Async sibling of test_fanout_malformed_page_is_partial.
    async def fetch(body):
        if body["from"] == 0:
            return {"total": 12, "list": [{"i": j} for j in range(5)]}
        return {"unexpected": "shape"}  # 2xx but not a paginated-list shape

    with pytest.warns(UserWarning, match="results are partial"):
        out = await collect_paginated_async(
            _ep(max_page_size=5), body={}, fetch=fetch, concurrency=4
        )
    assert out["partial"] is True
    assert out["failedPages"]
    assert [r["i"] for r in out["list"]] == list(range(5))  # only the valid first page
