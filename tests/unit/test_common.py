"""Tests for the domain-layer DataFrame helpers in ``domains/_common.py``.

Focus on ``_columnar_dataframe`` (the matrix fast path) and ``_result_to_dataframe``
(fast path + fallback), especially that the fast path stays byte-for-byte equivalent
to the ``to_dataframe(_extract_rows(...))`` path it replaces.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from typing import Any

import pytest

from gangtise_openapi._errors import ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import (
    _columnar_dataframe,
    _extract_rows,
    _request_body,
    _result_to_dataframe,
    _to_timestamp13,
)


def _slow(result: Any):
    """The exact two-step path the fast path replaces."""
    return to_dataframe(_extract_rows(result), schema=None)


def test_columnar_dataframe_fires_on_matrix():
    df = _columnar_dataframe({"fieldList": ["a", "b"], "list": [[1, 2], [3, 4]]})
    assert df is not None
    assert list(df.columns) == ["a", "b"]
    assert df["a"].tolist() == [1, 3]
    assert df["b"].tolist() == [2, 4]


@pytest.mark.parametrize(
    "result",
    [
        {"fieldList": ["a"], "list": []},  # empty rows
        {"fieldList": ["a", "b"], "list": [[1]]},  # ragged row (too short)
        {"fieldList": ["a"], "list": [[1, 2]]},  # ragged row (too long)
        {"fieldList": ["a", "a"], "list": [[1, 2]]},  # duplicate field names
        {"fieldList": ["a", 1], "list": [[1, 2]]},  # non-string field
        {"fieldList": [], "list": [[]]},  # empty fieldList
        {"list": [{"a": 1}]},  # dict rows, no fieldList
        {"fieldList": ["a"], "list": [{"a": 1}]},  # row is a dict, not a list
        [{"a": 1}],  # bare list, not a dict
        {"total": 0},  # unrelated dict shape
        "not a dict",  # non-dict payload
        None,
    ],
)
def test_columnar_dataframe_falls_back(result: Any):
    assert _columnar_dataframe(result) is None


@pytest.mark.parametrize(
    "result",
    [
        # clean matrices (fast path) across dtypes
        {"fieldList": ["d", "rev", "np"], "list": [["Q1", 100.5, None], ["Q2", 200, 30.1]]},
        {"fieldList": ["code"], "list": [[600519], [1913]]},
        {"fieldList": ["flag"], "list": [[True], [False]]},
        {"fieldList": ["s"], "list": [[""], [None]]},
        # duplicate field names — fast path must decline so both dedup identically
        {"fieldList": ["a", "a"], "list": [[1, 2], [3, 4]]},
        # fallback shapes
        {"fieldList": ["a"], "list": []},  # empty
        {"list": [{"x": 1}, {"x": 2}]},  # already dict rows
        {"constants": [{"c": 1}]},  # constant-list alias
    ],
)
def test_result_to_dataframe_matches_slow_path(result: Any):
    fast = _result_to_dataframe(result)
    slow = _slow(result)
    assert list(fast.columns) == list(slow.columns)
    assert list(fast.dtypes) == list(slow.dtypes)
    assert fast.equals(slow)


def test_ragged_row_raises_on_both_paths():
    # The fast path declines a ragged matrix and the slow path now refuses it
    # outright, so the two stay equivalent — both raise rather than one silently
    # padding (TS v0.28.3).
    ragged: Any = {"fieldList": ["a", "b"], "list": [[1]]}
    assert _columnar_dataframe(ragged) is None
    with pytest.raises(ValidationError, match="响应字段数与 fieldList 不匹配"):
        _result_to_dataframe(ragged)
    with pytest.raises(ValidationError, match="响应字段数与 fieldList 不匹配"):
        _slow(ragged)


def test_duplicate_fields_produce_single_deduped_column():
    """Regression: duplicate fieldList must not leak two same-named columns."""
    df = _result_to_dataframe({"fieldList": ["a", "a"], "list": [[1, 2], [3, 4]]})
    assert list(df.columns) == ["a"]
    assert df["a"].tolist() == [2, 4]  # dict last-wins semantics preserved


def test_validate_top_accepts_range_and_rejects_out_of_range():
    from gangtise_openapi._errors import ValidationError
    from gangtise_openapi.domains._common import _validate_top

    assert _validate_top(1, name="top", max_value=10) == 1
    assert _validate_top(10, name="top", max_value=10) == 10
    for bad in (0, 11, -1, True, "10"):
        with pytest.raises(ValidationError):
            _validate_top(bad, name="top", max_value=10)  # type: ignore[arg-type]


def test_validate_choices_passes_whitelist_and_rejects_unknown():
    from gangtise_openapi._errors import ValidationError
    from gangtise_openapi.domains._common import _validate_choices

    assert _validate_choices(None, name="category", allowed=("a", "b")) is None
    assert _validate_choices("a", name="category", allowed=("a", "b")) == ["a"]
    assert _validate_choices(["a", "b"], name="category", allowed=("a", "b")) == ["a", "b"]
    with pytest.raises(ValidationError):
        _validate_choices("c", name="category", allowed=("a", "b"))
    with pytest.raises(ValidationError):
        _validate_choices(["a", "c"], name="category", allowed=("a", "b"))


# ── Date / datetime validation before the request goes out ──
#
# Year-FIRST layouts are all accepted and normalized to YYYY-MM-DD: "2026/07/01"
# and "20260701" read as the same day to everyone, so refusing them buys nothing.
#
# Year-LAST stays refused, and the asymmetry is the whole point. The server does
# parse it, month-first — the US convention (re-probed 2026-08-17: "01-07-2026"
# and "01/07/2026" are both 7 January, "07-01-2026" and "07/01/2026" both 1 July).
# That is a platform convention, not a defect. But "01-07-2026" means 7 January to
# an American and 1 July to a European, so forwarding it hands half the callers
# data six months off with HTTP 200 and a plausible row count.


@pytest.mark.parametrize("field", ["startDate", "endDate", "date", "reportDate"])
@pytest.mark.parametrize(
    "value",
    [
        "07/01/2026",  # year-last: 1 July to the server, 7 January to a European
        "07-01-2026",
        "01-07-2026",
        "01/07/2026",
        "2026-07/01",  # mixed separator — a typo, not a layout
        "2026/07-01",
        "2026-7-1",
        "2026-07-01 09:30:00",  # a date field must not carry a time
        "2026-02-30",  # well-shaped but not a real calendar day
        "2026-13-01",
        "20260230",  # same, in the compact layout
        "",
    ],
)
def test_request_body_rejects_bad_date(field, value):
    with pytest.raises(ValidationError):
        _request_body({field: value})


@pytest.mark.parametrize("field", ["startDate", "endDate", "date", "reportDate"])
@pytest.mark.parametrize("value", ["2026-07-01", "2024-02-29", "0050-06-15"])
def test_request_body_accepts_iso_date(field, value):
    assert _request_body({field: value}) == {field: value}


# Normalized on the way out, so only one layout ever reaches the wire: the
# server's lenient parsing is not guaranteed uniform across endpoint groups, and
# YYYY-MM-DD is the form every group is probed against.
@pytest.mark.parametrize("field", ["startDate", "endDate", "date", "reportDate"])
@pytest.mark.parametrize("value", ["2026/07/01", "20260701"])
def test_request_body_normalizes_year_first_date(field, value):
    assert _request_body({field: value}) == {field: "2026-07-01"}


@pytest.mark.parametrize("field", ["startTime", "endTime"])
@pytest.mark.parametrize(
    "value",
    [
        "2026-07-01",
        "2026-07-01 09:30",
        "2026-07-01 09:30:00",
        "2026-07-01T09:30:00",
        "1751328000",  # 10-digit epoch seconds
        "1751328000000",  # 13-digit epoch millis
        1751328000000,
        1751328000,
        # Timezone-free by design: this wall-clock instant does not exist under
        # America/New_York, but the SDK forwards the string and the SERVER resolves
        # it in its own zone — the client's timezone must not decide validity.
        "2026-03-08 02:30:00",
    ],
)
def test_request_body_accepts_datetime_passthrough(field, value):
    # Returned verbatim: these fields are echoed to the server as-is, never converted.
    assert _request_body({field: value}) == {field: value}


# Only the DATE half is rewritten. The time half — its separator (space vs T) and
# whether seconds are present — is echoed verbatim by these endpoints, so it stays.
@pytest.mark.parametrize("field", ["startTime", "endTime"])
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026/07/01", "2026-07-01"),
        ("20260701", "2026-07-01"),
        ("2026/07/01 09:30:00", "2026-07-01 09:30:00"),
        ("20260701T09:30", "2026-07-01T09:30"),
    ],
)
def test_request_body_normalizes_year_first_datetime(field, value, expected):
    assert _request_body({field: value}) == {field: expected}


# Python's `$` also matches just BEFORE a trailing newline, so "2026-07-01\n" is a
# match with `m.end() == 10 < len(value)`. `re.sub` leaves that newline in place, so
# a tail slice that ran to the end of the string appended it a SECOND time and put
# "2026-07-01\n\n" on the wire. Pinning 0.3.0 parity here: the trailing newline is
# forwarded once, exactly as before. Rejecting it outright is the stricter option
# and is tracked as bug/python-open.md P9 — it belongs in a minor, not a patch.
@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("date", "2026-07-01\n", "2026-07-01\n"),
        ("date", "20260701\n", "2026-07-01\n"),
        ("startTime", "2026/07/01 09:30\n", "2026-07-01 09:30\n"),
        ("startTime", "2026-07-01T09:30:00\n", "2026-07-01T09:30:00\n"),
    ],
)
def test_request_body_does_not_duplicate_a_trailing_newline(field, value, expected):
    assert _request_body({field: value}) == {field: expected}


@pytest.mark.parametrize("field", ["startTime", "endTime"])
@pytest.mark.parametrize(
    "value",
    [
        "07/01/2026",
        "07-01-2026",
        "2026-07-01 24:00:00",
        "2026-07-01 09:60",
        "2026-02-30 09:30:00",
        "1e12",  # scientific notation must not coerce into an epoch
        "0x64",
        " 1751328000 ",
        "17513280000",  # 11 digits — neither seconds nor millis
        "175132800000",  # 12 digits
        "2026-07-01T09:30:00.123",  # millisecond tail was silently swallowed before
        "2026-07-01T09:30:00+08:00",
    ],
)
def test_request_body_rejects_bad_datetime(field, value):
    with pytest.raises(ValidationError):
        _request_body({field: value})


def test_request_body_error_names_the_python_kwarg():
    # The wire field is camelCase; the user typed the snake_case kwarg.
    with pytest.raises(ValidationError) as exc:
        _request_body({"startDate": "07/01/2026"})
    assert "start_date" in str(exc.value)
    assert "startDate" not in str(exc.value)


def test_request_body_still_drops_none():
    assert _request_body({"a": 1, "b": None, "startDate": None}) == {"a": 1}


def test_request_body_leaves_unrelated_fields_alone():
    body = {"securityCode": "600519.SH", "period": ["annual"], "size": 0}
    # `dict(body)`: _request_body writes normalized dates back into the dict it is
    # given, so passing `body` itself would compare the object against itself and
    # pass no matter what the guard did.
    assert _request_body(dict(body)) == body


# ── TS v0.28.0: the CONVERTING datetime guard (ai.knowledge_batch, A-share announcement) ──


def test_to_timestamp13_passes_millis_through():
    assert _to_timestamp13(1767225600000, "start_time") == 1767225600000
    assert _to_timestamp13("1767225600000", "start_time") == 1767225600000


def test_to_timestamp13_scales_seconds():
    assert _to_timestamp13(1767225600, "start_time") == 1767225600000
    assert _to_timestamp13("1767225600", "start_time") == 1767225600000


def test_to_timestamp13_13_digit_1e12_boundary_is_not_rescaled():
    # The magnitude test this replaces was `> 1e12`, and 1000000000000 == 1e12
    # exactly — so a real 13-digit epoch fell into the SECONDS branch and came out
    # 1000x too large. Digit count has no boundary to get wrong.
    assert _to_timestamp13(1000000000000, "start_time") == 1000000000000


def test_to_timestamp13_converts_local_datetime():
    import datetime as dt

    expected = int(dt.datetime(2026, 6, 1, 9, 0, 0).timestamp() * 1000)
    assert _to_timestamp13("2026-06-01 09:00:00", "start_time") == expected
    assert _to_timestamp13("2026-06-01T09:00:00", "start_time") == expected


def test_to_timestamp13_date_only_anchors_to_local_midnight():
    import datetime as dt

    expected = int(dt.datetime(2026, 1, 1).timestamp() * 1000)
    assert _to_timestamp13("2026-01-01", "start_time") == expected


@pytest.mark.parametrize(
    "value",
    ["07/01/2026", "1e12", "0x64", " 1767225600 ", "17672256000", "2026-02-30", 1, -1, True],
)
def test_to_timestamp13_rejects_junk(value):
    with pytest.raises(ValidationError):
        _to_timestamp13(value, "start_time")


def test_to_timestamp13_none_passes_through():
    assert _to_timestamp13(None, "start_time") is None


def test_knowledge_batch_accepts_datetime_string_and_converts():
    # TS v0.28.0 routed knowledge-batch through parseTimestamp13: it now takes a
    # 10/13-digit epoch OR a datetime string, and always sends 13-digit millis.
    import datetime as dt
    from unittest.mock import MagicMock

    from gangtise_openapi.domains.ai import AI

    client = MagicMock()
    client._call.return_value = []
    AI(client).knowledge_batch(query="q", start_time="2026-06-01 09:00:00", end_time=1767225600)
    body = client._call.call_args.kwargs["body"]
    assert body["startTime"] == int(dt.datetime(2026, 6, 1, 9, 0, 0).timestamp() * 1000)
    assert body["endTime"] == 1767225600000


def test_knowledge_batch_rejects_ambiguous_datetime():
    from unittest.mock import MagicMock

    from gangtise_openapi.domains.ai import AI

    with pytest.raises(ValidationError):
        AI(MagicMock()).knowledge_batch(query="q", start_time="07/01/2026")


# ── Python-side affordance beyond the TS CLI: an offset-bearing ISO string ──
# Only on the CONVERTING path, where an explicit offset is unambiguous and the
# conversion is exact. The pass-through fields still refuse it — there the server
# parses the string in its own zone, so the offset's meaning is not ours to assume.


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-01T00:00:00+00:00", 1767225600000),
        ("2026-01-01T00:00:00Z", 1767225600000),
        ("2026-01-01T08:00:00+08:00", 1767225600000),
        ("2026-01-01 08:00:00+0800", 1767225600000),
        ("2026-01-01T00:00+00:00", 1767225600000),
    ],
)
def test_to_timestamp13_accepts_offset_iso(value, expected):
    assert _to_timestamp13(value, "start_time") == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-01-01T00:00:00.123+00:00",  # millisecond tail still refused
        "2026-01-01T00:00:00+99:00",
        "07/01/2026T00:00:00+00:00",
        "2026-02-30T00:00:00+00:00",
    ],
)
def test_to_timestamp13_rejects_bad_offset_iso(value):
    with pytest.raises(ValidationError):
        _to_timestamp13(value, "start_time")


def test_request_body_still_refuses_offset_iso_on_passthrough_fields():
    # insight/vault list endpoints echo the string verbatim; the server resolves it
    # in its own zone, so an offset the SDK does not convert would be a guess.
    with pytest.raises(ValidationError):
        _request_body({"startTime": "2026-01-01T00:00:00+00:00"})


# ── Review round 1: the converted timestamp must not be re-validated as input ──


def _local_millis(value: str) -> int:
    """Expected epoch millis for a local wall-clock string, computed in the CURRENT
    timezone — a literal would only be right in whatever zone it was written in."""
    return int(dt.datetime.fromisoformat(value).timestamp() * 1000)


@pytest.mark.parametrize(
    "value", ["1999-01-01", "1970-01-02", "2001-09-08", "2026-06-01", "2026-06-01 09:00:00"]
)
def test_converted_timestamp_survives_the_body_guard(value):
    millis = _to_timestamp13(value, "start_time")
    assert millis == _local_millis(value)
    assert _request_body({"startTime": millis}) == {"startTime": millis}


@pytest.mark.parametrize("value", ["1999-01-01", "1970-01-02", "2001-09-08"])
def test_historical_millis_are_neither_10_nor_13_digits(value):
    # This is WHY the double-validation was a bug rather than a nitpick: epoch millis
    # only reach 13 digits in Sept 2001 and go negative before 1970, so re-running
    # the "exactly 10 or 13 digits" INPUT rule over the OUTPUT rejected every earlier
    # date. Holds in every timezone — a +/-14h offset cannot move these magnitudes
    # across a digit boundary.
    digits = len(str(abs(_to_timestamp13(value, "start_time"))))
    assert digits not in (10, 13)


def test_knowledge_batch_accepts_a_historical_date():
    from unittest.mock import MagicMock

    from gangtise_openapi.domains.ai import AI

    client = MagicMock()
    client._call.return_value = []
    AI(client).knowledge_batch(query="q", start_time="1999-01-01")
    assert client._call.call_args.kwargs["body"]["startTime"] == _local_millis("1999-01-01")


# ── Review round 1: a DST-gap wall clock cannot be converted faithfully ──


def _under_tz(tz: str, snippet: str) -> str:
    """Run a snippet in a fresh interpreter under ``tz``.

    ``time.tzset`` is unavailable in this CPython build, so the process timezone
    cannot be changed in place — and DST behavior is exactly what these assert.
    """
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        env={**os.environ, "TZ": tz},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize(
    ("tz", "value"),
    [
        ("America/New_York", "2026-03-08 02:30:00"),  # 1-hour spring-forward gap
        ("Australia/Lord_Howe", "2026-10-04 02:15:00"),  # 30-minute gap
    ],
)
def test_to_timestamp13_rejects_dst_gap(tz, value):
    # Converting is not pass-through: this endpoint sends a NUMBER, so a wall clock
    # the local zone skips has no faithful representation. datetime.timestamp()
    # silently maps it to the far side of the gap (02:30 -> 03:30), which would
    # query a different hour than the caller asked for. The 30-minute Lord Howe gap
    # is why the check has to be minute-level, not hour-level.
    out = _under_tz(
        tz,
        "from gangtise_openapi.domains._common import _to_timestamp13\n"
        "from gangtise_openapi._errors import ValidationError\n"
        f"try:\n"
        f"    print('GOT', _to_timestamp13({value!r}, 'start_time'))\n"
        "except ValidationError:\n"
        "    print('REJECTED')\n",
    )
    assert out == "REJECTED"


@pytest.mark.parametrize("tz", ["America/New_York", "Australia/Lord_Howe", "Asia/Shanghai"])
def test_to_timestamp13_keeps_working_outside_the_gap(tz):
    out = _under_tz(
        tz,
        "import datetime as dt\n"
        "from gangtise_openapi.domains._common import _to_timestamp13\n"
        "want = int(dt.datetime(2026, 6, 15, 12, 0, 0).timestamp() * 1000)\n"
        "got = _to_timestamp13('2026-06-15 12:00:00', 'start_time')\n"
        "print('MATCH' if got == want else f'MISMATCH {got} != {want}')\n",
    )
    assert out == "MATCH"


def test_request_body_still_allows_dst_gap_on_passthrough_fields():
    # The pass-through fields forward the STRING; the server resolves it in its own
    # zone, so the client's timezone must not decide validity.
    body = {"startTime": "2026-03-08 02:30:00"}
    assert _request_body(dict(body)) == body  # copy: the guard writes back in place


# ── Review round 1: "digits" must mean ASCII digits ──


def _fullwidth(text: str) -> str:
    """ASCII digits -> their U+FF10..U+FF19 fullwidth counterparts.

    Built from code points rather than written literally so the file itself stays
    free of the ambiguous characters it is testing for.
    """
    return "".join(chr(0xFF10 + ord(ch) - ord("0")) if "0" <= ch <= "9" else ch for ch in text)


@pytest.mark.parametrize("ascii_value", ["2026-07-01", "1767225600", "1767225600000"])
@pytest.mark.parametrize("partial", [False, True])
def test_guards_reject_fullwidth_digits(ascii_value, partial):
    # Python's \d matches any Unicode decimal and int() parses fullwidth digits — so
    # these cleared the shape check and were forwarded verbatim to an API that cannot
    # read them. `partial` covers a mixed string, where only one digit is fullwidth.
    value = (
        ascii_value[:5] + _fullwidth(ascii_value[5:6]) + ascii_value[6:]
        if partial
        else _fullwidth(ascii_value)
    )
    assert value != ascii_value
    with pytest.raises(ValidationError):
        _request_body({"startDate": value})
    with pytest.raises(ValidationError):
        _request_body({"startTime": value})
    with pytest.raises(ValidationError):
        _to_timestamp13(value, "start_time")


# ── Review round 1: years datetime cannot construct ──


@pytest.mark.parametrize("value", ["0000-07-01", "0000-01-01"])
def test_year_zero_is_rejected_not_leaked_as_valueerror(value):
    # datetime's MINYEAR is 1; year 0 passed the arithmetic calendar check and then
    # leaked a bare ValueError out of the converting path.
    with pytest.raises(ValidationError):
        _request_body({"startDate": value})
    with pytest.raises(ValidationError):
        _to_timestamp13(value, "start_time")


def test_validate_datetime_rejects_non_int_non_str():
    # The bypass for _to_timestamp13's output must be narrow: that helper only ever
    # returns int, so anything else here is a caller mistake and should not sail
    # through to json.dumps.
    for value in [1.5, [1767225600000], {"ts": 1}, object()]:
        with pytest.raises(ValidationError):
            _request_body({"startTime": value})
