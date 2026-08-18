"""Shared helpers for domain wrappers.

These were previously duplicated verbatim across every ``domains/*.py`` file.
Keeping a single copy avoids drift — the per-file ``_extract_rows`` had already
diverged into two incompatible variants (one handled bare lists, one did not).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from typing import Any, TypeAlias

import pandas as pd

from gangtise_openapi._errors import ValidationError
from gangtise_openapi._normalize import normalize_rows, to_dataframe

# A filter argument: one value or a list of values, funneled through ``_as_list``
# into a camelCase ``...List`` body field. Elements are ``str | int`` because these
# are ID / enum / code filters the API accepts as either — the npm CLI sends strings,
# the SDK's own tests send ints (e.g. industry=1, permission=1), and ``source`` is
# numeric in one endpoint yet a string in another. A ``str``-only type would reject
# valid calls (regression caught by Codex review of 810bf19).
FilterValue: TypeAlias = str | int | Sequence[str | int]


def _as_list(value: Any) -> list[Any] | None:
    """Wrap a scalar in a list, pass lists/tuples through, leave ``None`` as ``None``."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None`` (unset optional fields)."""
    return {k: v for k, v in body.items() if v is not None}


# ``re.ASCII`` throughout: Python's ``\d`` matches every Unicode decimal and ``int()``
# happily parses them, so a date written in fullwidth digits (U+FF10..U+FF19) would
# clear a bare ``\d`` check, convert to a plausible-looking year, and then be
# forwarded verbatim to an API that cannot read it.
# The three year-FIRST layouts (``YYYY-MM-DD`` / ``YYYY/MM/DD`` / ``YYYYMMDD``),
# all normalized to ``YYYY-MM-DD`` before the request goes out. The backreference
# keeps the separator consistent, so ``2026-07/01`` is a typo, not a date.
_YEAR_FIRST_DATE = re.compile(r"^(\d{4})([-/]?)(\d{2})\2(\d{2})$", re.ASCII)
# Same, plus an optional `` HH:mm[:ss]`` / ``THH:mm[:ss]`` tail.
_LOCAL_DATETIME = re.compile(
    r"^(\d{4})([-/]?)(\d{2})\2(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$", re.ASCII
)
_EPOCH_SECONDS = re.compile(r"^\d{10}$", re.ASCII)
_EPOCH_MILLIS = re.compile(r"^\d{13}$", re.ASCII)
# Same shape plus a mandatory UTC offset. Accepted only by ``_to_timestamp13``.
_OFFSET_DATETIME = re.compile(
    r"^(\d{4})([-/]?)(\d{2})\2(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(Z|z|[+-]\d{2}:?\d{2})$",
    re.ASCII,
)

# Shared by every message below: says what IS accepted, and why year-last is not.
_DATE_LAYOUT_HINT = (
    "YYYY-MM-DD (YYYY/MM/DD and YYYYMMDD also accepted) — year-last layouts are "
    'refused because the API reads them month-first (US convention): "01-07-2026" '
    "means 7 January, not 1 July"
)


def _normalize_year_first(value: str) -> str:
    """``YYYY/MM/DD`` / ``YYYYMMDD`` -> ``YYYY-MM-DD``; leaves any time tail alone.

    Only the leading date is rewritten, so ``"2026/07/01 09:30:00"`` becomes
    ``"2026-07-01 09:30:00"`` with the time part untouched — the pass-through
    endpoints echo it verbatim and accept both the space and ``T`` separators.

    🔴 The tail slice is bounded by ``m.end()``, NOT by the end of the string, and
    the two are not always the same: Python's ``$`` also matches just BEFORE a
    trailing newline, so ``"2026-07-01\\n"`` matches with ``m.end() == 10 < len``.
    ``re.sub`` only replaces ``m.start()..m.end()``, leaving that newline in place —
    an unbounded slice would append it a second time and send ``"2026-07-01\\n\\n"``.
    (The lax ``$`` is pre-existing and deliberately left alone here; tightening it to
    ``\\Z`` rejects input 0.3.0 forwarded, which is a minor-version change — tracked
    as bug/python-open.md P9.)
    """
    return _LOCAL_DATETIME.sub(
        lambda m: f"{m[1]}-{m[3]}-{m[4]}{value[m.end(4) : m.end()]}", value, count=1
    )


# Wire fields carrying a bare calendar date, and those carrying a datetime. These
# are the only ``*Date`` / ``*Time`` keys any request body uses (verified across
# every wrapper), so keying the guard on them covers all of them at once.
_DATE_FIELDS = frozenset({"startDate", "endDate", "date", "reportDate"})
_DATETIME_FIELDS = frozenset({"startTime", "endTime"})
# Scalar enum wire fields and their legal values. Mounted here, on the body
# builder every wrapper already funnels through, so the guard covers all 19 list
# endpoints at once — and any added later.
_ENUM_FIELDS: dict[str, tuple[int, ...]] = {"searchType": (1, 2), "rankType": (1, 2)}


def _snake(field: str) -> str:
    """camelCase wire field -> the snake_case kwarg the caller actually typed."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", field).lower()


def _is_real_date(year: int, month: int, day: int) -> bool:
    """Calendar check by arithmetic, deliberately not via ``datetime``: building a
    date would make validity depend on the client's timezone (a DST-gap wall clock
    is a real instant to the server) and would remap two-digit years.

    Bounded by ``datetime``'s own MINYEAR/MAXYEAR even though no ``datetime`` is
    built here: year 0000 satisfies the arithmetic (0 % 400 == 0, so it even reads
    as a leap year) but cannot be constructed downstream, which leaked a bare
    ``ValueError`` out of the converting path."""
    if not dt.MINYEAR <= year <= dt.MAXYEAR:
        return False
    if not 1 <= month <= 12:
        return False
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    return 1 <= day <= days


def _validate_date(value: Any, field: str) -> Any:
    """Any year-FIRST layout, normalized to ``YYYY-MM-DD`` on the way out.

    The server parses year-last layouts too, and reads them month-first — the US
    convention (re-probed 2026-08-17: ``01-07-2026`` and ``01/07/2026`` are both
    7 January, ``07-01-2026`` and ``07/01/2026`` both 1 July). That is a platform
    convention, not a defect; an earlier build disagreed between separators and
    that half was fixed 2026-08-15.

    The asymmetry is the point: ``2026/07/01`` reads as one day to everyone, while
    ``01-07-2026`` is 7 January to an American and 1 July to a European. Forwarding
    it would hand half of the callers data six months off with HTTP 200 and a
    plausible row count. Refusing locally also skips a billed round trip, and the
    message names a layout that works.

    Normalizing rather than forwarding as typed keeps one shape on the wire: the
    server's lenient parsing is not guaranteed uniform across endpoint groups, and
    ``YYYY-MM-DD`` is the form every group is probed against."""
    if not isinstance(value, str) or not _YEAR_FIRST_DATE.match(value):
        raise ValidationError(
            f"invalid {_snake(field)}: expected {_DATE_LAYOUT_HINT}, got {value!r}"
        )
    normalized = _normalize_year_first(value)
    year, month, day = (int(part) for part in normalized.split("-"))
    if not _is_real_date(year, month, day):
        raise ValidationError(f"invalid {_snake(field)}: {value!r} is not a real calendar date")
    return normalized


def _datetime_fields_valid(value: str) -> bool:
    parts = _LOCAL_DATETIME.match(value)
    if not parts:
        return False
    year, _sep, month, day, hh, mm, ss = parts.groups()
    if not _is_real_date(int(year), int(month), int(day)):
        return False
    return int(hh or 0) <= 23 and int(mm or 0) <= 59 and int(ss or 0) <= 59


def _validate_datetime(value: Any, field: str) -> Any:
    """A 10/13-digit epoch or a year-first date with an optional `` HH:mm[:ss]`` /
    ``THH:mm[:ss]`` tail. Not converted — these fields are echoed to the server
    verbatim — but the DATE half is normalized to ``YYYY-MM-DD`` so only one layout
    reaches the wire. Epochs and the time half pass through untouched.

    Epochs are judged by digit count, not magnitude: a ``> 1e12`` test sends the
    real 13-digit ``1000000000000`` (which equals 1e12) down the seconds branch, and
    lets scientific / hex / whitespace-padded / 11-12-digit input coerce through as
    a "timestamp". Probed 2026-07-21 the pass-through list endpoints misread
    year-last separators exactly like the date endpoints — ``insight.research_list``
    read ``07/01/2026`` as 2026-01-07 but ``07-01-2026`` as 2026-07-01.

    An ``int`` passes through unchecked: it is always the OUTPUT of
    ``_to_timestamp13`` (the converting endpoints run it before the body is built,
    and every pass-through field is typed ``str``), and re-running an input-shape
    check over that output rejected every date before 2001-09-09 — epoch millis are
    only 13 digits from then on, and negative before 1970. The bypass is limited to
    ``int`` on purpose: that helper returns nothing else, so a float / list / dict
    here is a caller mistake and must not reach ``json.dumps``."""
    if isinstance(value, bool):
        raise ValidationError(f"invalid {_snake(field)}: expected a datetime, got {value!r}")
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise ValidationError(
            f"invalid {_snake(field)}: expected a datetime string or epoch int, "
            f"got {type(value).__name__}"
        )
    if _EPOCH_MILLIS.match(value) or _EPOCH_SECONDS.match(value):
        return value
    if _datetime_fields_valid(value):
        return _normalize_year_first(value)
    raise ValidationError(
        f"invalid {_snake(field)}: expected a 10/13-digit Unix timestamp or "
        f'"YYYY-MM-DD" optionally with " HH:mm[:ss]" (space or T separator), '
        f"got {value!r} — {_DATE_LAYOUT_HINT}"
    )


def _offset_seconds(raw: str) -> int | None:
    """``Z`` / ``+08:00`` / ``-0500`` -> seconds east of UTC. Parsed by hand rather
    than via ``datetime.fromisoformat``, which only learned ``Z`` and colon-less
    offsets in 3.11 — this package supports 3.10."""
    if raw in ("Z", "z"):
        return 0
    digits = raw[1:].replace(":", "")
    if len(digits) != 4:
        return None
    hours, minutes = int(digits[:2]), int(digits[2:])
    if hours > 23 or minutes > 59:
        return None
    return (1 if raw[0] == "+" else -1) * (hours * 3600 + minutes * 60)


def _offset_datetime_to_millis(text: str) -> int | None:
    """Epoch millis for an offset-bearing ISO string, or ``None`` if it is not one
    (or is not a real instant). Deliberately accepted ONLY here: converting to
    millis makes an explicit offset unambiguous, whereas the pass-through fields
    hand the raw string to the server, which resolves it in its own zone."""
    parts = _OFFSET_DATETIME.match(text)
    if not parts:
        return None
    year, _sep, month, day, hh, mm, ss, raw_offset = parts.groups()
    offset = _offset_seconds(raw_offset)
    if offset is None or not _is_real_date(int(year), int(month), int(day)):
        return None
    if int(hh) > 23 or int(mm) > 59 or int(ss or 0) > 59:
        return None
    as_utc = dt.datetime(
        int(year),
        int(month),
        int(day),
        int(hh),
        int(mm),
        int(ss or 0),
        tzinfo=dt.timezone.utc,
    )
    return int(as_utc.timestamp() * 1000) - offset * 1000


def _to_timestamp13(value: Any, name: str) -> int | None:
    """Same accepted shapes as :func:`_validate_datetime`, but CONVERTED to epoch
    millis — for the two endpoints that want a number on the wire
    (``ai.knowledge_batch``, the A-share ``insight.announcement_list``) rather than
    a string the server parses itself.

    A date-only string anchors to LOCAL midnight so ``"2026-01-01"`` and
    ``"2026-01-01 00:00:00"`` mean the same wall-clock day (``datetime`` would read
    the first as UTC and the second as local — 8 hours apart for CST users). An
    explicit UTC offset is also accepted here and nowhere else — see
    :func:`_offset_datetime_to_millis`.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"invalid {name}: expected a timestamp, got {value!r}")
    text = str(value) if isinstance(value, int) else value
    if isinstance(text, str):
        if _EPOCH_MILLIS.match(text):
            return int(text)
        if _EPOCH_SECONDS.match(text):
            return int(text) * 1000
        with_offset = _offset_datetime_to_millis(text)
        if with_offset is not None:
            return with_offset
        if _datetime_fields_valid(text):
            parts = _LOCAL_DATETIME.match(text)
            assert parts is not None  # _datetime_fields_valid already matched
            year, _sep, month, day, hh, mm, ss = parts.groups()
            moment = dt.datetime(
                int(year), int(month), int(day), int(hh or 0), int(mm or 0), int(ss or 0)
            )
            millis = int(moment.timestamp() * 1000)
            # Round-trip every field: a wall clock the local zone SKIPS (02:30 on a
            # US spring-forward morning, 02:15 in Lord Howe's 30-minute gap) has no
            # faithful epoch, and ``timestamp()`` silently resolves it to the far
            # side of the gap — querying a different hour than was asked for. The
            # pass-through fields accept such a string on purpose (the server
            # resolves it in its own zone); converting here does not have that out.
            # Minute-level because Lord Howe's gap is half an hour.
            if dt.datetime.fromtimestamp(millis / 1000) != moment:
                raise ValidationError(
                    f"invalid {name}: {value!r} does not exist in the local timezone "
                    "(a daylight-saving gap) — it cannot be converted to a timestamp "
                    "faithfully; pass an explicit UTC offset or an epoch instead"
                )
            return millis
    raise ValidationError(
        f"invalid {name}: expected a 10/13-digit Unix timestamp or "
        f'"YYYY-MM-DD" optionally with " HH:mm[:ss]" (space or T separator), got {value!r}'
    )


def _request_body(body: dict[str, Any]) -> dict[str, Any]:
    """Finalize a request body: validate date / datetime fields, then drop unset ones.

    Every wrapper funnels its body through here, so the date guards land on all of
    them at once — including wrappers added later, which is the point. ``None``
    (unset) skips validation and is dropped as before.

    The date guards RETURN a normalized value (``2026/07/01`` -> ``2026-07-01``),
    so their result is written back rather than discarded — dropping it would
    validate the input and then send the un-normalized original.
    """
    for field, value in list(body.items()):
        if value is None:
            continue
        if field in _DATE_FIELDS:
            body[field] = _validate_date(value, field)
        elif field in _DATETIME_FIELDS:
            body[field] = _validate_datetime(value, field)
        elif field in _ENUM_FIELDS:
            _validate_enum(value, name=_snake(field), allowed=_ENUM_FIELDS[field])
    return _strip_none(body)


def _extract_rows(result: Any) -> list[Any]:
    """Pull the row list out of any supported API payload shape.

    Runs the payload through :func:`normalize_rows` first, so columnar /
    matrix / single-object responses become a proper list of dicts instead of
    yielding an empty DataFrame.
    """
    normalized = normalize_rows(result)
    if isinstance(normalized, dict):
        rows = normalized.get("list", [])
        return rows if isinstance(rows, list) else []
    if isinstance(normalized, list):
        return normalized
    return []


def _columnar_dataframe(result: Any) -> pd.DataFrame | None:
    """Fast path for the columnar matrix payload ``{fieldList, list: [[...], ...]}``.

    When ``fieldList`` is a non-empty list of column-name strings and every row is a
    list of exactly ``len(fieldList)`` values, ``pd.DataFrame(rows, columns=fieldList)``
    builds the frame directly — skipping the per-row dict transpose in
    :func:`normalize_rows`, which is 2-5x slower and roughly doubles peak memory at
    K-line / financial-statement scale. Returns ``None`` for any other shape (dict
    rows, ragged rows, missing / non-string ``fieldList``, **duplicate** field names,
    empty ``list``) so the caller falls back to the normalize path, whose output is
    identical for those cases.

    The duplicate-name guard matters: ``normalize_rows`` builds a dict per row, so a
    repeated field collapses to its last value (one column); ``pd.DataFrame(rows,
    columns=fields)`` would instead emit two same-named columns. Falling back keeps
    the two paths equivalent. Mirrors the guard in quote's ``_kline_dataframe``.
    """
    if not isinstance(result, dict):
        return None
    fields = result.get("fieldList")
    rows = result.get("list")
    if (
        isinstance(fields, list)
        and fields
        and all(isinstance(f, str) for f in fields)
        and len(set(fields)) == len(fields)
        and isinstance(rows, list)
        and rows
        and all(isinstance(r, list) and len(r) == len(fields) for r in rows)
    ):
        return pd.DataFrame(rows, columns=fields)
    return None


def _result_to_dataframe(result: Any) -> pd.DataFrame:
    """Build a schema-less DataFrame from an API payload.

    Uses the columnar fast path when ``result`` is a clean matrix and otherwise falls
    back to ``to_dataframe(_extract_rows(result))``. The two produce identical frames
    (verified across numeric / None / mixed / bool dtypes) — the fast path is only
    quicker, so wrappers can call this in place of the explicit two-step form.
    """
    fast = _columnar_dataframe(result)
    if fast is not None:
        return fast
    return to_dataframe(_extract_rows(result), schema=None)


def _validate_top(value: int, *, name: str, max_value: int) -> int:
    """Local cap for count params (``top``/``limit``) where the server was probed
    to silently truncate over-limit values instead of erroring (TS CLI v0.25.0) —
    without this a ``top=50`` quietly returns fewer rows than asked."""
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= max_value:
        raise ValidationError(
            f"{name} must be an integer between 1 and {max_value} (got {value!r})"
        )
    return value


def _validate_enum(value: Any, *, name: str, allowed: tuple[int, ...]) -> Any:
    """Whitelist for a SCALAR enum kwarg (``search_type`` / ``rank_type`` /
    ``file_type``).

    The server treats an out-of-range enum exactly like an unknown field: it drops
    the condition and answers with the UNFILTERED set at HTTP 200. The worst case
    is ``search_type``, which takes ``keyword`` down with it — probed by the CLI
    2026-08-08: ``insight.summary_list(keyword=…)`` returns a few hundred rows
    normally and **the entire library** with ``search_type=99``, three orders of
    magnitude more; ``insight.research_list`` behaves the same way. The caller reads
    it as "results for that keyword" and gets a full dump, which an automated
    pipeline has almost no chance of noticing. So these are refused locally, before
    the request (TS v0.32.0).

    (Magnitudes rather than the measured row counts on purpose: this docstring
    ships inside the wheel, so absolute library sizes would be published with every
    release. The ratio is what makes the case for the guard.)
    """
    if value is None:
        return None
    if isinstance(value, bool) or value not in allowed:
        raise ValidationError(
            f"invalid {name}: {value!r} is not one of {'/'.join(str(a) for a in allowed)}"
        )
    return value


def _validate_choices(value: Any, *, name: str, allowed: tuple[str, ...]) -> list[Any] | None:
    """Whitelist for enum-valued filters. Only used where the server was probed NOT
    to reject bad values — it silently ignores the filter or returns empty instead,
    so a typo would masquerade as "no results" (TS CLI v0.25.0). Endpoints that
    answer 100003 keep server-side validation."""
    values = _as_list(value)
    if values is None:
        return None
    for item in values:
        if item not in allowed:
            raise ValidationError(f"invalid {name}: {item!r} is not one of {'/'.join(allowed)}")
    return values
