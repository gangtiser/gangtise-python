from __future__ import annotations

import pytest

from gangtise_openapi._endpoints import EndpointDef, Pagination
from gangtise_openapi._errors import ValidationError
from gangtise_openapi._pagination import collect_paginated_async


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

    out = await collect_paginated_async(
        _ep(max_page_size=5), body={}, fetch=fetch, concurrency=4
    )
    assert [r["i"] for r in out["list"]] == list(range(12))


@pytest.mark.anyio
async def test_async_invalid_from_raises():
    async def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        await collect_paginated_async(
            _ep(), body={"from": -1}, fetch=fetch, concurrency=3
        )
