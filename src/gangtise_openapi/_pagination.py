from __future__ import annotations

import threading
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ValidationError

MAX_PAGES = 1000

PageFetcher = Callable[[dict[str, Any]], Any]


def first_leaf_exception(exc: BaseException) -> BaseException:
    """Descend (possibly nested) exception groups to the first leaf exception.

    anyio>=4 task groups wrap task failures in a ``BaseExceptionGroup``, which
    would break callers' ``except ApiError`` on the async path while the sync
    path raises the bare error. The check is structural (an ``exceptions``
    tuple of exceptions) because ``BaseExceptionGroup`` is not a builtin on
    Python 3.10.
    """
    while True:
        nested = getattr(exc, "exceptions", None)
        if isinstance(nested, tuple) and nested and isinstance(nested[0], BaseException):
            exc = nested[0]
        else:
            return exc


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

    if endpoint.pagination.sequential:
        return _collect_sequential(endpoint, body=body, fetch=fetch)

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
        _warn_capped(endpoint, len(remaining_requests) + 1 - MAX_PAGES)
        remaining_requests = remaining_requests[: MAX_PAGES - 1]

    # Fail-soft fan-out (TS parity): a hard page failure (rate limit, no-perm,
    # retries exhausted) must NOT discard the pages already fetched. Catch per
    # page, record it, and stop starting new requests so we don't keep burning
    # quota into a rate limit. firstPage already succeeded to get here.
    failed_pages: list[dict[str, Any]] = []
    state: dict[str, Any] = {"aborted": False, "first_error": None}
    if remaining_requests:
        workers = max(1, min(concurrency, len(remaining_requests)))
        lock = threading.Lock()

        def _run_page(req: dict[str, Any]) -> list[Any]:
            with lock:
                if state["aborted"]:
                    failed_pages.append(req)
                    return []
            try:
                page = fetch(req)
            except Exception as error:  # fail-soft: record and keep prior pages
                with lock:
                    if state["first_error"] is None:
                        state["first_error"] = error
                    state["aborted"] = True
                    failed_pages.append(req)
                return []
            if not _is_paginated_response(page):
                # 2xx but malformed (no total/list): record it so the result is tagged
                # partial instead of silently dropping rows. Don't set aborted — unlike
                # a rate limit, one malformed page is no reason to stop the whole batch.
                with lock:
                    failed_pages.append(req)
                return []
            return page["list"]  # type: ignore[no-any-return]  # may be [] (empty page)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            page_lists = list(pool.map(_run_page, remaining_requests))
        for page_list in page_lists:
            collected.extend(page_list)

    if requested_size is not None:
        collected = collected[:requested_size]
    return _finalize_partial(first_page, total, collected, failed_pages, state, endpoint)


def _extract_list_by_key(page: Any, list_key: str) -> list[Any] | None:
    """Return ``page[list_key]`` if it's a list, else ``None`` (shape mismatch)."""
    if not isinstance(page, dict):
        return None
    arr = page.get(list_key)
    return arr if isinstance(arr, list) else None


def _warn_sequential_partial(endpoint: EndpointDef, collected: int) -> None:
    warnings.warn(
        f"a page response had an unexpected shape for {endpoint.key}; "
        f"results are partial — {collected} row(s) fetched",
        stacklevel=2,
    )


def _warn_sequential_capped(endpoint: EndpointDef, collected: int) -> None:
    warnings.warn(
        f"sequential pagination hit the MAX_PAGES={MAX_PAGES} cap for {endpoint.key}; "
        f"fetched {collected} row(s) — pass size= to bound the result",
        stacklevel=2,
    )


def _collect_sequential(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: PageFetcher,
) -> Any:
    """Serial offset pagination for endpoints with NO ``total`` and a non-standard
    list key (wechat chatroom's ``chatRoomList``). Without ``total`` the page count
    is unknown, so we can't fan out — page serially until a short page (fewer rows
    than requested) signals the end. Returns ``{list_key: rows}`` so normalize /
    ``_extract_rows`` treat it like any list. Mirrors ``requestSequentialPaginated``
    in the TS CLI (core/client.ts)."""
    initial = dict(body)
    _validate_paging_args(initial)
    pagination = endpoint.pagination
    assert pagination is not None  # caller guards; narrows for mypy
    list_key = pagination.list_key or "list"
    max_page_size = pagination.max_page_size
    raw_from = initial.get("from")
    start_from = raw_from if isinstance(raw_from, int) else 0
    raw_size = initial.get("size")
    requested_size = raw_size if isinstance(raw_size, int) else None

    collected: list[Any] = []
    first_page: Any = None
    next_from = start_from
    truncated = False
    page = 0
    while True:
        remaining = max_page_size if requested_size is None else requested_size - len(collected)
        if requested_size is not None and remaining <= 0:
            break
        size = min(max_page_size, remaining)
        page_data = fetch({**initial, "from": next_from, "size": size})
        if first_page is None:
            first_page = page_data
        rows = _extract_list_by_key(page_data, list_key)
        if rows is None:
            # First response isn't a list shape → hand it back untouched. A LATER
            # page losing shape must NOT discard rows already collected (mirrors the
            # fail-soft fan-out): stop, keep them, warn.
            if page == 0:
                return first_page
            _warn_sequential_partial(endpoint, len(collected))
            break
        collected.extend(rows)
        if len(rows) < size:  # short page ⇒ no more rows
            break
        if requested_size is not None and len(collected) >= requested_size:
            break  # filled the request exactly — the page cap below must not fire
        if page + 1 >= MAX_PAGES:
            truncated = True
            break
        next_from += len(rows)
        page += 1

    if truncated:
        _warn_sequential_capped(endpoint, len(collected))
    result = collected if requested_size is None else collected[:requested_size]
    return {list_key: result}


def _warn_capped(endpoint: EndpointDef, dropped: int) -> None:
    """Warn when the MAX_PAGES cap drops trailing pages from the result. Uses
    ``warnings.warn`` (not a silent ``logger``) so the truncation surfaces on the
    default DataFrame path too, consistent with the fail-soft warning below."""
    warnings.warn(
        f"pagination capped at MAX_PAGES={MAX_PAGES} for {endpoint.key}; "
        f"dropping {dropped} page(s) of results",
        stacklevel=2,
    )


def _finalize_partial(
    first_page: dict[str, Any],
    total: int,
    collected: list[Any],
    failed_pages: list[dict[str, Any]],
    state: dict[str, Any],
    endpoint: EndpointDef,
) -> dict[str, Any]:
    """Assemble the paginated result, tagging it ``partial`` when fan-out pages
    failed. Shared by the sync and async collectors."""
    result: dict[str, Any] = {**first_page, "total": total, "list": collected}
    if failed_pages:
        result["partial"] = True
        result["failedPages"] = [{"from": p["from"], "size": p["size"]} for p in failed_pages]
        first_error = state.get("first_error")
        detail = f": {first_error}" if first_error is not None else ""
        # Surface via warnings.warn (not logger) so the default DataFrame path —
        # which drops the partial/failedPages dict keys — still signals the gap to
        # callers who never set raw=True. Mirrors the K-line shard path (quote.py);
        # the SDK's default logger is a NullHandler, so logger.warning is silent.
        warnings.warn(
            f"{len(failed_pages)} page(s) not fetched for {endpoint.key}{detail}; "
            f"results are partial — got {len(collected)}/{total} rows "
            "(see failedPages in raw output)",
            stacklevel=2,
        )
    return result


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
    if endpoint.pagination.sequential:
        return await _collect_sequential_async(endpoint, body=body, fetch=fetch)
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
        _warn_capped(endpoint, len(remaining_requests) + 1 - MAX_PAGES)
        remaining_requests = remaining_requests[: MAX_PAGES - 1]

    pages: list[Any | None] = [None] * len(remaining_requests)
    # Fail-soft fan-out (TS parity): keep pages already fetched when a later page
    # hits a non-retryable error; record the failures and stop starting new
    # requests. See the sync sibling in collect_paginated.
    failed_pages: list[dict[str, Any]] = []
    state: dict[str, Any] = {"aborted": False, "first_error": None}
    if remaining_requests:
        semaphore = anyio.Semaphore(max(1, min(concurrency, len(remaining_requests))))

        async def run_one(idx: int, req: dict[str, Any]) -> None:
            async with semaphore:
                if state["aborted"]:
                    failed_pages.append(req)
                    return
                try:
                    pages[idx] = await fetch(req)
                except Exception as error:  # fail-soft: record and keep prior pages
                    if state["first_error"] is None:
                        state["first_error"] = error
                    state["aborted"] = True
                    failed_pages.append(req)

        async with anyio.create_task_group() as tg:
            for idx, req in enumerate(remaining_requests):
                tg.start_soon(run_one, idx, req)

    for idx, page in enumerate(pages):
        if page is None:
            continue  # run_one already recorded this failure (the exception path)
        if not _is_paginated_response(page):
            # 2xx but malformed: record so it surfaces as partial, don't drop silently
            # (mirrors the sync _run_page branch).
            failed_pages.append(remaining_requests[idx])
            continue
        collected.extend(page["list"])  # may be [] — a legitimately empty page
    if requested_size is not None:
        collected = collected[:requested_size]
    return _finalize_partial(first_page, total, collected, failed_pages, state, endpoint)


async def _collect_sequential_async(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: Callable[[dict[str, Any]], Any],
) -> Any:
    """Async sibling of :func:`_collect_sequential` — serial offset pagination for
    no-``total`` endpoints, awaiting each page before fetching the next."""
    initial = dict(body)
    _validate_paging_args(initial)
    pagination = endpoint.pagination
    assert pagination is not None  # caller guards; narrows for mypy
    list_key = pagination.list_key or "list"
    max_page_size = pagination.max_page_size
    raw_from = initial.get("from")
    start_from = raw_from if isinstance(raw_from, int) else 0
    raw_size = initial.get("size")
    requested_size = raw_size if isinstance(raw_size, int) else None

    collected: list[Any] = []
    first_page: Any = None
    next_from = start_from
    truncated = False
    page = 0
    while True:
        remaining = max_page_size if requested_size is None else requested_size - len(collected)
        if requested_size is not None and remaining <= 0:
            break
        size = min(max_page_size, remaining)
        page_data = await fetch({**initial, "from": next_from, "size": size})
        if first_page is None:
            first_page = page_data
        rows = _extract_list_by_key(page_data, list_key)
        if rows is None:
            if page == 0:
                return first_page
            _warn_sequential_partial(endpoint, len(collected))
            break
        collected.extend(rows)
        if len(rows) < size:  # short page ⇒ no more rows
            break
        if requested_size is not None and len(collected) >= requested_size:
            break  # filled the request exactly — the page cap below must not fire
        if page + 1 >= MAX_PAGES:
            truncated = True
            break
        next_from += len(rows)
        page += 1

    if truncated:
        _warn_sequential_capped(endpoint, len(collected))
    result = collected if requested_size is None else collected[:requested_size]
    return {list_key: result}
