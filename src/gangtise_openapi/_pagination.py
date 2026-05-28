from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ValidationError

MAX_PAGES = 1000

PageFetcher = Callable[[dict[str, Any]], Any]


def _is_paginated_response(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("total"), int)
        and isinstance(value.get("list"), list)
    )


def _validate_paging_args(body: dict[str, Any]) -> None:
    if "from" in body:
        v = body["from"]
        if not isinstance(v, int) or v < 0:
            raise ValidationError("Invalid 'from': expected a non-negative int")
    if "size" in body and body["size"] is not None:
        v = body["size"]
        if not isinstance(v, int) or v <= 0:
            raise ValidationError("Invalid 'size': expected a positive int")


def collect_paginated(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: PageFetcher,
    concurrency: int,
) -> Any:
    if endpoint.pagination is None:
        return fetch(body)

    initial = dict(body)
    _validate_paging_args(initial)

    raw_from = initial.get("from")
    start_from = raw_from if isinstance(raw_from, int) else 0
    raw_size = initial.get("size")
    requested_size = raw_size if isinstance(raw_size, int) else None
    max_page_size = endpoint.pagination.max_page_size

    first_page_size = (
        max_page_size if requested_size is None else min(max_page_size, requested_size)
    )
    first_body = {**initial, "from": start_from, "size": first_page_size}
    first_page = fetch(first_body)

    if not _is_paginated_response(first_page):
        return first_page

    total = first_page["total"]
    collected: list[Any] = list(first_page["list"])

    if first_page["list"] and len(first_page["list"]) < first_page_size:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}

    available = max(total - start_from, 0)
    target = available if requested_size is None else min(requested_size, available)

    if len(collected) >= target:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}

    remaining_requests: list[dict[str, Any]] = []
    next_from = start_from + len(first_page["list"])
    end_from = start_from + target
    while next_from < end_from:
        size = min(max_page_size, end_from - next_from)
        remaining_requests.append({**initial, "from": next_from, "size": size})
        next_from += size
    if len(remaining_requests) + 1 > MAX_PAGES:
        remaining_requests = remaining_requests[: MAX_PAGES - 1]

    if remaining_requests:
        workers = max(1, min(concurrency, len(remaining_requests)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pages = list(pool.map(fetch, remaining_requests))
        for page in pages:
            if _is_paginated_response(page) and page["list"]:
                collected.extend(page["list"])

    if requested_size is not None:
        collected = collected[:requested_size]
    return {**first_page, "total": total, "list": collected}


AsyncPageFetcher = Callable[[dict[str, Any]], Any]  # returns Awaitable


async def collect_paginated_async(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: Callable[[dict[str, Any]], Any],
    concurrency: int,
) -> Any:
    if endpoint.pagination is None:
        return await fetch(body)
    initial = dict(body)
    _validate_paging_args(initial)
    raw_from = initial.get("from")
    start_from = raw_from if isinstance(raw_from, int) else 0
    raw_size = initial.get("size")
    requested_size = raw_size if isinstance(raw_size, int) else None
    max_page_size = endpoint.pagination.max_page_size
    first_page_size = (
        max_page_size if requested_size is None else min(max_page_size, requested_size)
    )
    first_body = {**initial, "from": start_from, "size": first_page_size}
    first_page = await fetch(first_body)
    if not _is_paginated_response(first_page):
        return first_page
    total = first_page["total"]
    collected: list[Any] = list(first_page["list"])
    if first_page["list"] and len(first_page["list"]) < first_page_size:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}
    available = max(total - start_from, 0)
    target = available if requested_size is None else min(requested_size, available)
    if len(collected) >= target:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}
    remaining_requests: list[dict[str, Any]] = []
    next_from = start_from + len(first_page["list"])
    end_from = start_from + target
    while next_from < end_from:
        size = min(max_page_size, end_from - next_from)
        remaining_requests.append({**initial, "from": next_from, "size": size})
        next_from += size
    if len(remaining_requests) + 1 > MAX_PAGES:
        remaining_requests = remaining_requests[: MAX_PAGES - 1]

    pages: list[Any | None] = [None] * len(remaining_requests)
    if remaining_requests:
        semaphore = anyio.Semaphore(max(1, min(concurrency, len(remaining_requests))))

        async def run_one(idx: int, req: dict[str, Any]) -> None:
            async with semaphore:
                pages[idx] = await fetch(req)

        async with anyio.create_task_group() as tg:
            for idx, req in enumerate(remaining_requests):
                tg.start_soon(run_one, idx, req)

    for page in pages:
        if page is not None and _is_paginated_response(page) and page["list"]:
            collected.extend(page["list"])
    if requested_size is not None:
        collected = collected[:requested_size]
    return {**first_page, "total": total, "list": collected}
