from __future__ import annotations

import hashlib
import json
import math
import threading
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

from gangtise_openapi._endpoints import COSTLY_FETCH_CREDITS, EndpointDef
from gangtise_openapi._errors import ApiError, ValidationError

MAX_PAGES = 1000

# A guarded list whose full first page would cost more than this learns its total from a
# one-row probe first, so a refused fetch pays for one row rather than a page (TS v0.43.0).
PROBE_ABOVE_CREDITS = 50

# How a list endpoint refuses an offset past its window: 140002 (at HTTP 500) on the vault
# message list (probed 2026-09-25), 100006 on the insight lists that declare ``max_window``.
# A total-cap probe answered with one of these sat on a window; any other failure (a 503
# that outlived its retries, a dropped connection) says nothing about the total, so it
# stays silent (TS v0.43.0).
OFFSET_REFUSAL_CODES = frozenset({"140002", "100006"})

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


def warn_if_server_partial(payload: Any, label: str) -> bool:
    """Announce a ``partial`` marker that arrived IN THE RESPONSE.

    Every marker the SDK sets itself is announced where it is set. One the server
    put there was the gap: it rode through into the result dict and then vanished on
    the default return path, which is a DataFrame and carries none of these keys — so
    a caller who never passes ``raw=True`` saw a frame that looked complete.

    Call this BEFORE the SDK's own completeness checks, so a response that is both
    server-flagged and (say) limit-truncated reports the cause it arrived with rather
    than only the one we detected. Returns whether a marker was found.
    """
    if not (isinstance(payload, dict) and payload.get("partial") is True):
        return False
    warnings.warn(
        f"{label}: the server marked this response partial — it is not the complete "
        "result set. Pass raw=True to inspect the response's own markers.",
        stacklevel=3,
    )
    return True


def _first_page_shape_drift(endpoint: EndpointDef, first_page: Any) -> Any:
    """Shape drift silently degrades fetch-all to a single page.

    Applies to EVERY malformed shape, not just ``None``: a string ``total``
    truncates the result to page 1, which LOOKS complete and is therefore worse
    than an obviously empty payload. All the paginated endpoints are genuine
    ``{total, list}`` lists (the odd-shaped ones like ``reference.constant-list``
    are not marked paginated), and the endpoints where ``null`` is a legitimate
    answer (``ai.one-pager`` for a security with no generated content) are
    unpaginated and never reach here — so there is no valid response in this
    branch (TS v0.33.0).

    A warning only helps a human; a caller keys off ``partial``, so mark the
    payload too when it is a dict that can carry the flag.
    """
    warnings.warn(
        f"{endpoint.key} is marked paginated but the first page has an unexpected "
        "shape (no numeric total + list); returning it as-is — fetch-all silently "
        "degraded to one page, so this is NOT a complete result",
        stacklevel=4,
    )
    if isinstance(first_page, dict):
        return {**first_page, "partial": True}
    return first_page


def _validate_paging_args(body: dict[str, Any]) -> None:
    # ``bool`` is an ``int`` subclass; reject it explicitly (mirrors quote's
    # ``_validate_limit``) so ``from=True`` can't slip through as ``1``.
    if "from" in body:
        v = body["from"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ValidationError("Invalid 'from': expected a non-negative int")
    if "size" in body and body["size"] is not None:
        v = body["size"]
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise ValidationError("Invalid 'size': expected a positive int")


def _build_remaining_requests(
    *,
    initial: dict[str, Any],
    next_from: int,
    end_from: int,
    max_page_size: int,
    max_pages: int,
) -> tuple[list[dict[str, Any]], int]:
    """Build fan-out page requests while enforcing the page cap during generation."""
    remaining_requests: list[dict[str, Any]] = []
    dropped = 0
    max_remaining_pages = max(max_pages - 1, 0)
    while next_from < end_from:
        if len(remaining_requests) >= max_remaining_pages:
            remaining_rows = max(end_from - next_from, 0)
            dropped = (remaining_rows + max_page_size - 1) // max_page_size
            break
        size = min(max_page_size, end_from - next_from)
        remaining_requests.append({**initial, "from": next_from, "size": size})
        next_from += size
    return remaining_requests, dropped


# Marks a fan-out page that was never fetched (it raised, or the fan-out had already
# stopped): the page goes to ``failedPages``.
_NOT_FETCHED: Any = object()


def _read_empty_list(page: Any) -> Any:
    """Several lists answer "nothing matched" with ``list: null`` instead of ``[]`` —
    hot-topic, summary, the A-share and HK announcement lists, performance-calendar
    (probed 2026-09-25), and the roadshow / site-visit / forum lists (probed by the CLI
    2026-10-07). A numeric total of exactly 0 says what an empty
    list would, so it is read as one; a null list under any other total, a string total
    or a missing list is still a broken page and takes the unexpected-shape path
    (TS v0.43.0). Returns a copy: the caller's payload is never mutated."""
    if (
        isinstance(page, dict)
        and "list" in page
        and page["list"] is None
        and type(page.get("total")) is int
        and page["total"] == 0
    ):
        return {**page, "list": []}
    return page


def _row_digest(row: Any) -> bytes:
    """JSON with object keys sorted and array order kept, so two copies of one row that
    differ only in key order digest the same when paging drops repeats."""
    text = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    # surrogatepass: a server string escaping a lone surrogate (``\udc80``) decodes into
    # one, and a strict encode would crash a fetch whose pages are already paid for.
    return hashlib.sha1(text.encode("utf-8", "surrogatepass"), usedforsecurity=False).digest()


def _row_id_value(row: Any, path: str) -> Any:
    """The value at a dotted ``path`` (``source.sourceId``) of a row, ``None`` when any
    step is missing or not an object."""
    value = row
    for key in path.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _row_id_name(row_id: str | tuple[str, ...]) -> str:
    return row_id if isinstance(row_id, str) else " + ".join(row_id)


def _credits(value: float) -> str:
    """A credit amount as the price list writes it: ``2500``, ``1000.1``."""
    return str(int(value)) if float(value).is_integer() else str(value)


def _mark_total_capped(out: dict[str, Any], why: str, collected: int, keep_below: int) -> None:
    """A fetch-all whose ``total`` is, or may be, a server-side cap: warn, and mark the
    result so a truncated fetch cannot pass as complete."""
    warnings.warn(
        f"{why}. This result is TRUNCATED at {collected} rows. Narrow the query (e.g. a "
        f"shorter time range) until total stays below {keep_below}, and fetch in slices.",
        stacklevel=4,
    )
    out["partial"] = True
    out["totalCapped"] = True


def _warn_capped(endpoint: EndpointDef, dropped: int) -> None:
    """Warn when the MAX_PAGES cap drops trailing pages from the result. Uses
    ``warnings.warn`` (not a silent ``logger``) so the truncation surfaces on the
    default DataFrame path too, consistent with the fail-soft warning below."""
    warnings.warn(
        f"pagination capped at MAX_PAGES={MAX_PAGES} for {endpoint.key}; "
        f"dropping {dropped} page(s) of results",
        stacklevel=4,
    )


class _PagedFetch:
    """One auto-paginated fetch: every decision the sync and async collectors share.

    The collectors only send the requests this object asks for — the credit probe, the
    first page, the fan-out pages, the total-cap probe — and hand the answers back, so
    the two cannot drift apart. Mirrors TS ``requestPaginated`` (core/client.ts v0.44.0).
    """

    def __init__(self, endpoint: EndpointDef, body: dict[str, Any], allow_costly: bool) -> None:
        pagination = endpoint.pagination
        assert pagination is not None
        self.endpoint = endpoint
        self.initial = dict(body)
        _validate_paging_args(self.initial)
        raw_from = self.initial.get("from")
        self.start_from: int = raw_from if isinstance(raw_from, int) else 0
        raw_size = self.initial.get("size")
        self.requested_size: int | None = raw_size if isinstance(raw_size, int) else None
        self.max_page_size = pagination.max_page_size
        # Rows past the offset window are unreachable (the server rejects the page), so
        # no page is planned across it — a page straddling it would fail the whole tail
        # (TS v0.41.0 ``maxWindow``).
        self.max_window = pagination.max_window
        if self.max_window is not None and self.start_from >= self.max_window:
            raise ValidationError(
                f"{endpoint.key} serves rows only up to offset {self.max_window} (from + size "
                f"<= {self.max_window}); from={self.start_from} is past it. Narrow the query "
                "(e.g. a shorter time range) instead of paging deeper."
            )
        self.window_room: int | None = (
            None if self.max_window is None else self.max_window - self.start_from
        )
        # A per-row billed list fetched without ``size`` — or with one large enough to
        # pass the guard by itself (``size=100000`` as "everything") — is priced from
        # ``total`` before the fetch fans out, and refused past COSTLY_FETCH_CREDITS
        # unless the caller passed ``confirm=True`` (TS v0.43.0 / v0.44.0).
        billing = endpoint.billing
        self.guarded = (
            billing is not None
            and billing.per == "row"
            and not allow_costly
            and (
                self.requested_size is None
                or self.requested_size * billing.price > COSTLY_FETCH_CREDITS
            )
        )
        # The one-row credit probe (see probe_body): ``probed`` means it stands in as
        # the first page.
        self.probe: Any = None
        self.probed = False
        self.probe_rows = 0
        # Row dedupe by ``endpoint.row_id``: per id, a digest of every version kept.
        self.seen: dict[str, set[bytes]] = {}
        self.duplicate_rows = 0
        self.changed_rows = 0
        self.id_is_row_key = True
        # Filled in by start().
        self.first_page: dict[str, Any] = {}
        self.total = 0
        self.wanted = 0
        self.target = 0
        self.collected: list[Any] = []
        # Filled in by plan().
        self.requests: list[dict[str, Any]] = []
        self.dropped_pages = 0

    # ── credit guard ──

    def _rows_left(self, total: int) -> int:
        """Rows a fetch against ``total`` would bring back: those past ``from``, inside
        the offset window, and no more than the requested size."""
        rows = max(total - self.start_from, 0)
        if self.window_room is not None:
            rows = min(rows, self.window_room)
        if self.requested_size is not None:
            rows = min(rows, self.requested_size)
        return rows

    def refuse_if_costly(self, total: int, fetched: int) -> None:
        billing = self.endpoint.billing
        if not self.guarded or billing is None:
            return
        rows = self._rows_left(total)
        # Rounded half-up to the cent, as the CLI does (Math.round).
        estimate = math.floor(rows * billing.price * 100 + 0.5) / 100
        if estimate <= COSTLY_FETCH_CREDITS:
            return
        if self.requested_size is None:
            what, escape = f"all {rows} rows", "Pass size=N for a bounded subset"
        else:
            what, escape = f"{rows} rows (size={self.requested_size})", "Pass a smaller size"
        raise ValidationError(
            f"fetching {what} of {self.endpoint.key} would cost about {_credits(estimate)} "
            f"credits ({_credits(billing.price)} per row), above the "
            f"{COSTLY_FETCH_CREDITS}-credit guard. Only {fetched} row(s) were fetched, to "
            f"learn the total. {escape}, or confirm=True to fetch them all."
        )

    def probe_body(self) -> dict[str, Any] | None:
        """The one-row request a guarded list learns its ``total`` from, or ``None``.

        A cheap list learns ``total`` from its first page. Where a full first page would
        itself cost more than PROBE_ABOVE_CREDITS, one row is asked for first, so a
        refused fetch pays for that row alone; the fetch then starts over from the same
        offset at the usual page size, keeping every page on the usual boundaries (the
        probe row is billed twice) rather than depending on how an endpoint reads an
        unaligned ``from``.
        """
        billing = self.endpoint.billing
        if not self.guarded or billing is None:
            return None
        page = self.max_page_size
        if self.window_room is not None:
            page = min(page, self.window_room)
        if page * billing.price <= PROBE_ABOVE_CREDITS:
            return None
        return {**self.initial, "from": self.start_from, "size": 1}

    def take_probe(self, probe: Any) -> None:
        """Read the credit probe (refusing a costly fetch). The probe stands in as the
        first page when it already answers the fetch: when its shape is unexpected
        (reported by start(), without paying a full page to see it again) and when it
        holds exactly the rows left to fetch (a result of one row or none; more rows than
        ``total`` leaves contradicts itself, and the first page is fetched as usual)."""
        probe = _read_empty_list(probe)
        self.probe = probe
        if not _is_paginated_response(probe):
            self.probed = True
            return
        self.refuse_if_costly(probe["total"], len(probe["list"]))
        self.probe_rows = len(probe["list"])
        self.probed = self.probe_rows == self._rows_left(probe["total"])

    # ── first page ──

    @property
    def first_page_size(self) -> int:
        if self.probed:
            return 1
        size = self.max_page_size
        if self.requested_size is not None:
            size = min(size, self.requested_size)
        if self.window_room is not None:
            size = min(size, self.window_room)
        return size

    def first_body(self) -> dict[str, Any]:
        return {**self.initial, "from": self.start_from, "size": self.first_page_size}

    def start(self, page: Any) -> tuple[Any, bool] | None:
        """Read the first page. Returns ``(result, check_total_cap)`` when it settles
        the fetch, ``None`` when more pages are needed (see plan())."""
        page = _read_empty_list(page)
        if not _is_paginated_response(page):
            return _first_page_shape_drift(self.endpoint, page), False
        warn_if_server_partial(page, self.endpoint.key)
        self.first_page = page
        self.total = total = page["total"]
        available = max(total - self.start_from, 0)
        self.wanted = (
            available if self.requested_size is None else min(self.requested_size, available)
        )
        self.target = (
            self.wanted if self.window_room is None else min(self.wanted, self.window_room)
        )
        self.collected = self._drop_repeats(page["list"])
        first_page_size = self.first_page_size

        # Last page reached on the first request. If `total` promises more rows than the
        # short page delivered, the server's page cap may be lower than max_page_size —
        # say so instead of silently returning a subset as "everything".
        if len(page["list"]) < first_page_size:
            out = self._result()
            if len(self.collected) < self.target:
                out["partial"] = True
                warnings.warn(
                    f"short first page for {self.endpoint.key}; results are partial — "
                    f"got {len(out['list'])}/{total} rows",
                    stacklevel=3,
                )
            return out, False

        if len(self.collected) >= self.target:
            # A fetch-all that STARTS INSIDE THE LAST PAGE (``from=9950`` against
            # ``total=10000``) returns here rather than through the fan-out, and is just
            # as exposed to a capped ``total``. ``total > first_page_size`` keeps the
            # request count unchanged for a result that genuinely fits in one page from
            # offset 0: only a late ``from`` can land here with a total larger than a
            # page (TS v0.38.0).
            check = (
                self.requested_size is None
                and total > first_page_size
                and self.target == self.wanted
            )
            return self._result(), check
        return None

    # ── fan-out ──

    def plan(self) -> list[dict[str, Any]]:
        """The remaining page requests (capped at MAX_PAGES while generating them)."""
        # A cheap guarded list reaches here with its first page in hand; the probe path
        # has already checked, and passes again unless `total` grew past the guard in
        # between.
        self.refuse_if_costly(
            self.total, len(self.collected) + (0 if self.probed else self.probe_rows)
        )
        self.requests, self.dropped_pages = _build_remaining_requests(
            initial=self.initial,
            next_from=self.start_from + len(self.first_page["list"]),
            end_from=self.start_from + self.target,
            max_page_size=self.max_page_size,
            max_pages=MAX_PAGES,
        )
        return self.requests

    def finish(
        self, outcomes: list[Any], first_error: BaseException | None
    ) -> tuple[dict[str, Any], bool]:
        """Merge the fan-out pages (in page order) and tag the result ``partial``
        whenever it is incomplete — fan-out pages failed, the ``MAX_PAGES`` cap dropped
        pages, the server drifted (``total`` changed, or fewer rows came back than it
        implied), a later page flagged itself partial. Each cause sets ``partial`` and
        warns so scripts can machine-detect the gap and the default DataFrame path still
        surfaces it. Returns ``(result, check_total_cap)``."""
        key = self.endpoint.key
        failed_pages: list[dict[str, Any]] = []
        total_drift = False
        later_partial = False
        for request, page in zip(self.requests, outcomes, strict=True):
            if page is _NOT_FETCHED:
                failed_pages.append(request)
                continue
            # A later page that says total 0 is a total that drifted mid-fetch, not a
            # broken page (TS v0.43.0).
            page = _read_empty_list(page)
            if not _is_paginated_response(page):
                # 2xx but malformed (no total/list): record it so the result is tagged
                # partial instead of silently dropping rows. Unlike a raised error it does
                # not stop the fan-out.
                failed_pages.append(request)
                continue
            if page["total"] != self.total:
                total_drift = True
            if page.get("partial") is True:
                later_partial = True
            self.collected.extend(self._drop_repeats(page["list"]))

        count = len(self.collected)
        short = count < self.target
        # Every row arrived and some were dropped as repeats: the fetch otherwise reached
        # `total`, so it is still checked against a capped total, and no page came back
        # short (TS v0.43.0).
        short_by_repeats_only = short and count + self.duplicate_rows >= self.target
        out = self._result()
        check = (
            self.requested_size is None
            and self.total > 0
            and self.target == self.wanted
            and (not short or short_by_repeats_only)
            and not total_drift
            and not self.dropped_pages
            and not failed_pages
        )

        if later_partial:
            # Only the FIRST page's metadata is spread into the merged result, so a later
            # page that flagged itself partial would otherwise lose the marker and the
            # merged result would read as complete (TS v0.38.0).
            out["partial"] = True
            warnings.warn(
                f"a later page reported itself partial for {key}; "
                "the merged result is marked partial",
                stacklevel=3,
            )
        if total_drift:
            # `total` changed between pages: data shifted under the fetch, so rows may be
            # duplicated or missing even when the counts happen to line up.
            out["partial"] = True
            warnings.warn(
                f"'total' changed across pages for {key} (data shifted during "
                "fetch); rows may be duplicated or missing",
                stacklevel=3,
            )
        if failed_pages:
            out["partial"] = True
            out["failedPages"] = [{"from": p["from"], "size": p["size"]} for p in failed_pages]
            detail = f": {first_error}" if first_error is not None else ""
            # Surface via warnings.warn (not logger) so the default DataFrame path —
            # which drops the partial/failedPages dict keys — still signals the gap to
            # callers who never set raw=True. The SDK's default logger is a NullHandler,
            # so logger.warning would be silent.
            warnings.warn(
                f"{len(failed_pages)} page(s) not fetched for {key}{detail}; "
                f"results are partial — got {len(out['list'])}/{self.total} rows "
                "(see failedPages in raw output)",
                stacklevel=3,
            )
        if self.dropped_pages:
            # MAX_PAGES safety cap: pages beyond the limit were never requested, so the
            # result is truncated. Flag it (not just warn) so it's machine-readable.
            out["partial"] = True
            _warn_capped(self.endpoint, self.dropped_pages)
        elif not failed_pages and short:
            # Total drift: the server reported a larger `total` than it actually returned
            # (a short/empty mid page). Treat the smaller result as the end of data but
            # flag it so callers don't mistake it for the full set. A shortfall that is
            # only the dropped repeats already has its own warning.
            out["partial"] = True
            if not short_by_repeats_only:
                warnings.warn(
                    f"server reported total={self.total} but only {len(out['list'])} row(s) "
                    f"came back for {key}; treating it as the end of data — results may "
                    "be incomplete",
                    stacklevel=3,
                )
        return out, check

    # ── total-cap probe ──

    def total_cap_probe(self, out: dict[str, Any]) -> dict[str, Any] | None:
        """The request that checks ``total`` is the real row count, or ``None`` when no
        request can tell (the result is then marked here).

        ``total`` is not always the real row count. Three opinion endpoints reported a
        fixed 10000 while ``from=30000`` still returned real rows with monotonically
        older publish times (the shape of Elasticsearch's default track_total_hits). A
        fetch-all then stops exactly at the cap with ``collected == total``, so every
        completeness check passes and the truncated export LOOKS complete — the worst
        failure mode there is.

        Only run on a genuine fetch-all that otherwise looked complete (``start`` /
        ``finish`` decide): when ``total`` is honest the probe comes back empty, and an
        endpoint that prices per item charges nothing for an empty answer — so the probe
        is free exactly when it finds nothing wrong.

        ⚠️ **Do NOT gate this on ``retry == "no-replay"``.** That flag reads like a
        per-call-billing marker; it is not one. ``no-replay``
        means "never resend a request the server may already have executed" — REPLAY
        safety — and the probe is a new request, never a resend, so the flag has
        nothing to say about it. Billing-wise the one endpoint that gate excluded,
        ``ai.hot-topic``, is priced per returned item (10 per 篇, where a 篇 is one whole
        report), and the platform does not charge a per-item endpoint for a query that
        finds nothing — so the gate saved no credits while costing that endpoint its
        only truncation check.

        Do NOT generalize that into "every paginated endpoint is per-item billed": this
        client cannot measure billing at all (no quota/usage API), at least one
        paginated endpoint has no published unit price, and several are free. What the
        probe relies on is narrower — on the endpoints where a capped ``total`` has been
        observed, an empty answer is not billed. The CLI reverted the same exclusion on
        2026-08-18.

        The probe asks for the row at offset ``total``; past a declared offset window
        the server rejects it outright, so a ``total`` that reaches the window cannot be
        probed: rows past it can be neither fetched nor counted, and the result is
        treated as truncated, as when a probe finds rows (vault.wechat-message.list: the
        unfiltered total stops at 10000 while its monthly totals add up to more — probed
        2026-09-25; TS v0.43.0).
        """
        if self.max_window is None or self.total + 1 <= self.max_window:
            return {**self.initial, "from": self.total, "size": 1}
        _mark_total_capped(
            out,
            f"{self.endpoint.key} reported total={self.total}, which equals its "
            f"{self.max_window}-row offset window: rows past it can be neither fetched "
            "nor counted",
            len(out["list"]),
            self.max_window,
        )
        return None

    def read_total_cap_probe(
        self, out: dict[str, Any], probe: Any = None, error: BaseException | None = None
    ) -> None:
        key = self.endpoint.key
        if error is not None:
            # A failed probe must never fail an otherwise-complete fetch. But a probe the
            # server REFUSED is not the same as one that never got through: the rows
            # before `total` were served and the one at `total` was refused, which is how
            # an offset window the endpoint did not declare answers (140002 is also the
            # generic business failure, so this is the likely reading, not a proven one)
            # — handled as the declared-window path is, the conservative way. Any other
            # failure says nothing about the total and stays silent (TS v0.43.0).
            if isinstance(error, ApiError) and error.code in OFFSET_REFUSAL_CODES:
                _mark_total_capped(
                    out,
                    f"{key} reported total={self.total} and refused the row right after it "
                    f"({error.code}) — most likely a server-side offset window at total, so "
                    "rows past it may exist and can be neither fetched nor counted",
                    len(out["list"]),
                    self.total,
                )
            return
        if _is_paginated_response(probe) and probe["list"]:
            _mark_total_capped(
                out,
                f"{key} reported total={self.total} but rows exist past that offset — "
                "'total' is a server-side cap, not the real count",
                len(out["list"]),
                self.total,
            )

    # ── rows ──

    def _drop_repeats(self, rows: list[Any]) -> list[Any]:
        """Drop a row already kept, seen again whole on a neighbouring page.

        Lists sorted on a non-unique key (``msgTime``, ``publishTime``) reorder a
        same-timestamp group between two page requests, so neighbouring pages both
        return some of it and miss the rest — the row count still equals ``total``
        (probed 2026-09-25). A row identical to ANY version kept under its
        ``row_id`` (not just the first) is dropped and counted; only the id and a digest
        per version are held, not the row itself (TS v0.43.0 / v0.43.1).

        An id seen again with different content on a LATER page is a row that moved or
        changed while paging, so its neighbours may have shifted too: both versions are
        kept and counted. The same on ONE page — a single consistent response — means
        the id does not identify a row on this list, and the count is then disregarded,
        as it is for an id field not yet seen to be one (``row_id_unverified``). Rows
        without the id (or any part of a composite one) are always kept.
        """
        row_id = self.endpoint.row_id
        if row_id is None:
            return list(rows)
        paths = (row_id,) if isinstance(row_id, str) else row_id
        on_this_page: dict[str, set[bytes]] = {}
        kept: list[Any] = []
        for row in rows:
            ids = [_row_id_value(row, path) for path in paths]
            if any(value is None for value in ids):
                kept.append(row)
                continue
            digest = _row_digest(row)
            key = str(ids[0]) if len(ids) == 1 else json.dumps([str(value) for value in ids])
            page_versions = on_this_page.get(key)
            if page_versions is None:
                on_this_page[key] = {digest}
            else:
                if digest not in page_versions:
                    self.id_is_row_key = False
                page_versions.add(digest)
            versions = self.seen.get(key)
            if versions is None:
                self.seen[key] = {digest}
                kept.append(row)
                continue
            if digest in versions:
                self.duplicate_rows += 1
                continue
            versions.add(digest)
            if page_versions is None:
                self.changed_rows += 1
            kept.append(row)
        return kept

    def _result(self) -> dict[str, Any]:
        """The merged result with the markers every return path shares: repeats
        dropped, rows that changed while paging, rows cut off by the offset window."""
        key = self.endpoint.key
        rows = (
            self.collected if self.requested_size is None else self.collected[: self.requested_size]
        )
        out: dict[str, Any] = {**self.first_page, "total": self.total, "list": rows}
        if self.duplicate_rows:
            # The count falls short by the same number, which marks the result partial
            # on every path anyway; this names the cause, since "short page" alone points
            # elsewhere.
            warnings.warn(
                f"{key} returned {self.duplicate_rows} row(s) more than once — its sort "
                "order is not unique, so paging also missed as many rows. The duplicates "
                "were dropped and the result is partial. Re-run over a shorter time range "
                "to fetch the missing rows.",
                stacklevel=4,
            )
            out["duplicateRows"] = self.duplicate_rows
            out["partial"] = True
        if self.changed_rows and self.id_is_row_key and not self.endpoint.row_id_unverified:
            assert self.endpoint.row_id is not None  # changed_rows is only counted under one
            row_id = _row_id_name(self.endpoint.row_id)
            warnings.warn(
                f"{key} returned {self.changed_rows} row(s) whose {row_id} came back on a "
                "later page with different content — the list changed while it was being "
                "paged, so rows may also have been missed. Both versions were kept "
                f"(deduplicating by {row_id} keeps one) and the result is partial. Re-run "
                "to fetch a consistent result.",
                stacklevel=4,
            )
            out["changedRows"] = self.changed_rows
            out["partial"] = True
        if self.target < self.wanted:
            # Rows the caller asked for that sit past the offset window: nothing can fetch
            # them, so the result is partial whatever else happens (TS v0.41.0 / v0.43.0).
            warnings.warn(
                f"{key} serves rows only up to offset {self.max_window} (from + size <= "
                f"{self.max_window}); {self.wanted - self.target} of the {self.wanted} "
                "requested rows lie past it and were not fetched. Narrow the query (e.g. a "
                "shorter time range) and fetch in slices.",
                stacklevel=4,
            )
            out["partial"] = True
        return out


def collect_paginated(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: PageFetcher,
    concurrency: int,
    allow_costly: bool = False,
) -> Any:
    """Fetch every page of a paginated list (or the ``size`` rows asked for) and merge
    them. ``allow_costly`` is ``_call``'s ``confirm``: it lets a per-row billed fetch
    past COSTLY_FETCH_CREDITS through. Decisions live in :class:`_PagedFetch`."""
    if endpoint.pagination is None:
        return fetch(body)
    run = _PagedFetch(endpoint, body, allow_costly)
    probe_body = run.probe_body()
    if probe_body is not None:
        run.take_probe(fetch(probe_body))
    # First page: serial — `total` decides how many more requests to fan out.
    settled = run.start(run.probe if run.probed else fetch(run.first_body()))
    if settled is None:
        settled = run.finish(*_fan_out(run.plan(), fetch, concurrency))
    out, check_total_cap = settled
    if check_total_cap:
        probe = run.total_cap_probe(out)
        if probe is not None:
            try:
                answer = fetch(probe)
            except Exception as error:
                run.read_total_cap_probe(out, error=error)
            else:
                run.read_total_cap_probe(out, answer)
    return out


def _fan_out(
    requests: list[dict[str, Any]], fetch: PageFetcher, concurrency: int
) -> tuple[list[Any], BaseException | None]:
    """Fetch the remaining pages; returns each page (or ``_NOT_FETCHED``) in request
    order, and the first error.

    Fail-soft (TS parity): a hard page failure (rate limit, no-perm, retries exhausted)
    must NOT discard the pages already fetched. Catch per page, record it, and stop
    starting new requests so we don't keep burning quota into a rate limit. Every page
    is queued up front, so one slow page never holds back the ones behind it.
    """
    outcomes: list[Any] = [_NOT_FETCHED] * len(requests)
    errors: list[BaseException] = []
    if not requests:
        return outcomes, None
    lock = threading.Lock()

    def run_page(index: int) -> None:
        with lock:
            if errors:
                return
        try:
            page = fetch(requests[index])
        except Exception as error:  # fail-soft: record and keep prior pages
            with lock:
                errors.append(error)
            return
        outcomes[index] = page

    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(requests)))) as pool:
        list(pool.map(run_page, range(len(requests))))
    return outcomes, errors[0] if errors else None


AsyncPageFetcher = Callable[[dict[str, Any]], Any]  # returns Awaitable


async def collect_paginated_async(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: AsyncPageFetcher,
    concurrency: int,
    allow_costly: bool = False,
) -> Any:
    """Async mirror of :func:`collect_paginated`."""
    if endpoint.pagination is None:
        return await fetch(body)
    run = _PagedFetch(endpoint, body, allow_costly)
    probe_body = run.probe_body()
    if probe_body is not None:
        run.take_probe(await fetch(probe_body))
    settled = run.start(run.probe if run.probed else await fetch(run.first_body()))
    if settled is None:
        settled = run.finish(*await _fan_out_async(run.plan(), fetch, concurrency))
    out, check_total_cap = settled
    if check_total_cap:
        probe = run.total_cap_probe(out)
        if probe is not None:
            try:
                answer = await fetch(probe)
            except Exception as error:
                run.read_total_cap_probe(out, error=error)
            else:
                run.read_total_cap_probe(out, answer)
    return out


async def _fan_out_async(
    requests: list[dict[str, Any]], fetch: AsyncPageFetcher, concurrency: int
) -> tuple[list[Any], BaseException | None]:
    """Async mirror of :func:`_fan_out`."""
    outcomes: list[Any] = [_NOT_FETCHED] * len(requests)
    errors: list[BaseException] = []
    if not requests:
        return outcomes, None
    semaphore = anyio.Semaphore(max(1, min(concurrency, len(requests))))

    async def run_page(index: int) -> None:
        async with semaphore:
            if errors:
                return
            try:
                outcomes[index] = await fetch(requests[index])
            except Exception as error:  # fail-soft: record and keep prior pages
                errors.append(error)

    async with anyio.create_task_group() as tg:
        for index in range(len(requests)):
            tg.start_soon(run_page, index)
    return outcomes, errors[0] if errors else None
