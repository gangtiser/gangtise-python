from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd


def to_dataframe(
    rows: Sequence[dict[str, Any]] | list[dict[str, Any]],
    *,
    schema: Sequence[str] | None,
) -> pd.DataFrame:
    if not isinstance(rows, list):
        raise TypeError(f"to_dataframe expects a list of dicts, got {type(rows).__name__}")
    if not rows:
        return pd.DataFrame({col: pd.Series(dtype="object") for col in (schema or [])})
    df = pd.DataFrame(rows)
    if schema is None:
        return df
    for col in schema:
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df), dtype="object")
    result: pd.DataFrame = df[list(schema)]
    return result
