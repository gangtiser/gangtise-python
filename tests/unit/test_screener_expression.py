"""The screener's expression evaluator (CLI v0.31.0, commit 21798d3).

`check_screener_bindings` asks this whether a result whose columns are incomplete
can still be shown to satisfy the filter. The answer follows the expression's
BOOLEAN STRUCTURE, not the mere presence of a `||` — the earlier heuristic
("contains a ||, so something could still have matched") passes every test that
uses a pure conjunction or a pure disjunction, so only MIXED structures separate
the two. Those are the cases here.
"""

from __future__ import annotations

import pytest

from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._indicator_matrix import (
    check_screener_bindings,
    parse_screener_indicators,
    screener_expression_fields,
    screener_expression_is_evaluable,
)


@pytest.mark.parametrize(
    ("expression", "present", "expected"),
    [
        # ── mixed structures: where the boolean parse and the `||` heuristic differ.
        # A missing mandatory conjunct is an unprovable claim even though the OTHER
        # side is a disjunction.
        ("F1 > 0 && (F2 > 0 || F3 > 0)", {"F2", "F3"}, False),
        ("(F1 > 0 || F2 > 0) && F3 > 0", {"F1", "F2"}, False),
        # A disjunction with NOTHING evaluable: no branch could have matched.
        ("F1 > 0 || F2 > 0", set(), False),
        # ── the same shapes when the missing column does not matter.
        ("F1 > 0 && (F2 > 0 || F3 > 0)", {"F1", "F2"}, True),
        ("(F1 > 0 || F2 > 0) && F3 > 0", {"F1", "F3"}, True),
        # ── the pure extremes (already covered end-to-end, kept as anchors).
        ("F1 > 0 && F2 > 0", {"F2"}, False),
        ("F1 > 0 || F2 > 0", {"F2"}, True),
        ("F1 > 0", {"F1"}, True),
        # ── a term naming no variable is always evaluable.
        ("1 > 0", set(), True),
        ("", set(), True),
        # ── a `||` inside a STRING LITERAL is not syntax, and an F-looking token
        # inside one is not a reference.
        ("F1 contains 'A || B'", {"F1"}, True),
        ("F1 contains 'F2 系列'", {"F1"}, True),
        ("F1 contains 'F2 系列'", {"F2"}, False),
        # ── nesting.
        ("((F1 > 0 || F2 > 0) && F3 > 0) || F4 > 0", {"F4"}, True),
        ("((F1 > 0 || F2 > 0) && F3 > 0) || F4 > 0", {"F1", "F2"}, False),
    ],
)
def test_expression_evaluability_follows_the_boolean_structure(expression, present, expected):
    assert screener_expression_is_evaluable(expression, present) is expected


def test_expression_fields_ignores_string_literals():
    assert screener_expression_fields("F1 >= 500 && F2 contains 'F9 系列'") == ["F1", "F2"]
    assert screener_expression_fields(None) == []


def _matrix(fields: list[str], codes: dict[str, str]) -> dict:
    return {
        "securityCodeList": ["600519.SH"],
        "indicatorList": [{"code": codes[f], "name": codes[f], "field": f} for f in fields],
        "values": [[1.0] * len(fields)],
    }


def _requested(codes: dict[str, str]) -> list[dict]:
    return [{"field": f, "indicatorCode": c, "parameters": []} for f, c in codes.items()]


def test_mixed_expression_missing_mandatory_conjunct_is_fatal():
    # The end-to-end sibling in test_indicator.py uses a pure conjunction, which the
    # `||` heuristic also rejects. This one only fails under a real boolean parse.
    codes = {"F1": "a", "F2": "b", "F3": "c"}
    with pytest.raises(ApiError, match="no branch of the expression survives"):
        check_screener_bindings(
            _matrix(["F2", "F3"], codes), _requested(codes), "F1 > 0 && (F2 > 0 || F3 > 0)"
        )


def test_mixed_expression_with_the_mandatory_conjunct_present_is_partial():
    codes = {"F1": "a", "F2": "b", "F3": "c"}
    missing = check_screener_bindings(
        _matrix(["F1", "F2"], codes), _requested(codes), "F1 > 0 && (F2 > 0 || F3 > 0)"
    )
    assert missing == ["F3"]  # information lost, correctness intact


def test_disjunction_with_no_evaluable_branch_is_fatal():
    codes = {"F1": "a", "F2": "b"}
    with pytest.raises(ApiError, match="F1, F2"):
        check_screener_bindings(_matrix([], codes), _requested(codes), "F1 > 0 || F2 > 0")


def test_duplicate_binding_in_the_response_is_fatal():
    # The mapping from a column back to the filter it came from is ambiguous once a
    # variable appears twice — and every screening decision rests on that mapping.
    codes = {"F1": "a"}
    data = {
        "securityCodeList": ["600519.SH"],
        "indicatorList": [
            {"code": "a", "name": "A", "field": "F1"},
            {"code": "a", "name": "A", "field": "F1"},
        ],
        "values": [[1.0, 2.0]],
    }
    with pytest.raises(ApiError, match="variable F1 appears twice"):
        check_screener_bindings(data, _requested(codes), "F1 > 0")


def test_parse_screener_indicators_keeps_binding_order():
    # Params key off the variable, not the code: the same indicator may legitimately
    # appear under two variables with different parameters, and only the variable
    # tells them apart. dict ordering is the insertion order the caller wrote.
    out = parse_screener_indicators(
        {"F2": "qte_close", "F1": "qte_close"},
        {"F2": {"tradeDate": "2026-08-06"}},
        "F1 > F2",
    )
    assert [b["field"] for b in out] == ["F2", "F1"]
    assert out[0]["parameters"] == [{"paramKey": "tradeDate", "paramValue": "2026-08-06"}]
    assert out[1]["parameters"] == []


def test_parse_screener_indicators_rejects_an_unbound_expression_variable():
    with pytest.raises(ValidationError, match="expression references 'F2'"):
        parse_screener_indicators({"F1": "qte_close"}, None, "F1 > 0 && F2 > 0")
