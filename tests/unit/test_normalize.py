import pytest

from gangtise_openapi._errors import ValidationError
from gangtise_openapi._normalize import normalize_rows, to_dataframe


def test_empty_list_returns_empty_frame_with_schema():
    df = to_dataframe([], schema=["a", "b", "c"])
    assert list(df.columns) == ["a", "b", "c"]
    assert len(df) == 0


def test_column_order_locked_by_schema():
    rows = [{"b": 2, "a": 1, "c": 3}, {"b": 5, "a": 4, "c": 6}]
    df = to_dataframe(rows, schema=["a", "b", "c"])
    assert list(df.columns) == ["a", "b", "c"]
    assert df["a"].tolist() == [1, 4]


def test_missing_column_added_as_null():
    rows = [{"a": 1}, {"a": 2}]
    df = to_dataframe(rows, schema=["a", "b"])
    assert list(df.columns) == ["a", "b"]
    assert df["b"].isna().all()


def test_extra_columns_dropped():
    rows = [{"a": 1, "extra": "drop"}]
    df = to_dataframe(rows, schema=["a"])
    assert list(df.columns) == ["a"]


def test_no_schema_returns_all_columns():
    rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    df = to_dataframe(rows, schema=None)
    assert set(df.columns) == {"a", "b"}
    assert len(df) == 2


def test_non_list_input_raises():
    with pytest.raises(TypeError):
        to_dataframe({"not": "a list"}, schema=["x"])


# ---- normalize_rows ----


def test_normalize_rows_transposes_fieldlist_matrix():
    payload = {"fieldList": ["a", "b", "c"], "list": [[1, 2, 3], [4, 5, 6]]}
    assert normalize_rows(payload) == [
        {"a": 1, "b": 2, "c": 3},
        {"a": 4, "b": 5, "c": 6},
    ]


def test_normalize_rows_matrix_preserves_metadata():
    payload = {"indicator": "peTtm", "fieldList": ["x"], "list": [[1]]}
    assert normalize_rows(payload) == {"indicator": "peTtm", "list": [{"x": 1}]}


@pytest.mark.parametrize(
    "row",
    [
        [1],  # short — trailing fields would silently become None
        [1, 2, 3, 4],  # long — the extra value would be silently dropped
    ],
)
def test_normalize_rows_refuses_a_row_that_does_not_match_field_list(row):
    # Positional zipping pastes values onto the wrong fields once the lengths
    # disagree: quote.realtime returns values for the VALID fields only while
    # echoing every requested name, so a turnover rate lands under `close` and
    # reads as a plausible price. Silent mis-columning must be a hard failure
    # (TS v0.28.3).
    with pytest.raises(ValidationError, match="响应字段数与 fieldList 不匹配"):
        normalize_rows({"fieldList": ["a", "b", "c"], "list": [row]})


def test_normalize_rows_exact_length_row_is_zipped():
    assert normalize_rows({"fieldList": ["a", "b"], "list": [[1, 2]]}) == [{"a": 1, "b": 2}]


def test_normalize_rows_list_of_dicts_passthrough():
    payload = {"holdType": "top10", "list": [{"rank": 1}]}
    assert normalize_rows(payload) == {"holdType": "top10", "list": [{"rank": 1}]}


def test_normalize_rows_bare_list_unchanged():
    assert normalize_rows([{"a": 1}]) == [{"a": 1}]


def test_normalize_rows_constants_aliased_preserving_metadata():
    # Mirrors normalize.test.ts "unwraps constants rows preserving category metadata".
    result = normalize_rows(
        {
            "category": "citicIndustry",
            "structureType": "flat",
            "maxLevel": 1,
            "constantCount": 2,
            "constants": [
                {"constantId": "100800121", "constantName": "银行"},
                {"constantId": "100800122", "constantName": "房地产"},
            ],
        }
    )
    assert result == {
        "category": "citicIndustry",
        "structureType": "flat",
        "maxLevel": 1,
        "constantCount": 2,
        "list": [
            {"constantId": "100800121", "constantName": "银行"},
            {"constantId": "100800122", "constantName": "房地产"},
        ],
    }


def test_normalize_rows_bare_constants_returns_list():
    assert normalize_rows({"constants": [{"constantId": "1"}]}) == [{"constantId": "1"}]


def test_normalize_rows_single_object_unchanged():
    payload = {"securityCode": "000001.SZ", "updateList": [1, 2]}
    assert normalize_rows(payload) == payload


def test_normalize_rows_non_dict_unchanged():
    assert normalize_rows("text") == "text"
    assert normalize_rows(None) is None


def test_column_mismatch_message_carries_the_envelope_trace_id():
    # A structural failure is exactly what support needs to trace, and
    # ValidationError has no trace_id property — so the id goes in the message
    # (mirrors the CLI's traceSuffix). This is the one place in the SDK that
    # actively consumes the carried id besides ApiError.
    from gangtise_openapi._transport import unwrap_envelope

    payload = unwrap_envelope(
        {
            "code": "000000",
            "status": True,
            "traceId": "830965044897325056",
            "data": {"fieldList": ["a", "b", "c"], "list": [[1]]},
        }
    )
    with pytest.raises(ValidationError, match="trace 830965044897325056"):
        normalize_rows(payload)


def test_column_mismatch_without_a_trace_id_omits_the_suffix():
    with pytest.raises(ValidationError) as excinfo:
        normalize_rows({"fieldList": ["a", "b"], "list": [[1]]})
    assert "trace" not in str(excinfo.value)
