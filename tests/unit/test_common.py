"""Tests for the domain-layer DataFrame helpers in ``domains/_common.py``.

Focus on ``_columnar_dataframe`` (the matrix fast path) and ``_result_to_dataframe``
(fast path + fallback), especially that the fast path stays byte-for-byte equivalent
to the ``to_dataframe(_extract_rows(...))`` path it replaces.
"""

from __future__ import annotations

from typing import Any

import pytest

from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains._common import (
    _columnar_dataframe,
    _extract_rows,
    _result_to_dataframe,
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
        {"fieldList": ["a", "b"], "list": [[1]]},  # ragged
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


def test_duplicate_fields_produce_single_deduped_column():
    """Regression: duplicate fieldList must not leak two same-named columns."""
    df = _result_to_dataframe({"fieldList": ["a", "a"], "list": [[1, 2], [3, 4]]})
    assert list(df.columns) == ["a"]
    assert df["a"].tolist() == [2, 4]  # dict last-wins semantics preserved
