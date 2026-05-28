import pytest

from gangtise_openapi._normalize import to_dataframe


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
