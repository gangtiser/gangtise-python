import pytest

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


def test_normalize_rows_short_row_pads_with_none():
    assert normalize_rows({"fieldList": ["a", "b", "c"], "list": [[1]]}) == [
        {"a": 1, "b": None, "c": None}
    ]


def test_normalize_rows_list_of_dicts_passthrough():
    payload = {"holdType": "top10", "list": [{"rank": 1}]}
    assert normalize_rows(payload) == {"holdType": "top10", "list": [{"rank": 1}]}


def test_normalize_rows_bare_list_unchanged():
    assert normalize_rows([{"a": 1}]) == [{"a": 1}]


def test_normalize_rows_chatroomlist_aliased():
    assert normalize_rows({"chatRoomList": [{"id": 1}]}) == [{"id": 1}]


def test_normalize_rows_single_object_unchanged():
    payload = {"securityCode": "000001.SZ", "updateList": [1, 2]}
    assert normalize_rows(payload) == payload


def test_normalize_rows_non_dict_unchanged():
    assert normalize_rows("text") == "text"
    assert normalize_rows(None) is None
