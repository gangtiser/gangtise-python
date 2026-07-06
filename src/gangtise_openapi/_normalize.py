from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd


def normalize_rows(payload: Any) -> Any:
    """Normalize a Gangtise API payload into a consistent row-list shape.

    The API returns several layouts depending on the endpoint:

      1. Columnar / matrix ``{"fieldList": [...], "list": [[...], ...]}`` — each
         array row is transposed into an object keyed by ``fieldList``. Any other
         top-level keys are preserved as metadata. (income-statement,
         balance-sheet, valuation-analysis, main-business, ... use this form.)
      2. ``{"list": [...]}`` — list of objects, passed through (meta preserved).
      3. ``{"constants": [...]}`` — aliased to ``list`` (reference.constant-list).
      4. Bare array ``[...]`` — returned unchanged.
      5. Anything else — returned unchanged.

    Returns either a bare list (when there is no surrounding metadata) or a dict
    with a ``list`` key. Mirrors ``normalizeRows`` in the TS CLI
    (``core/normalize.ts``); without it the matrix endpoints would tabulate with
    integer column names or produce an empty DataFrame.
    """
    if not isinstance(payload, dict):
        return payload

    field_list = payload.get("fieldList")
    list_val = payload.get("list")

    # Case 1: columnar matrix — transpose each array row against ``fieldList``.
    if isinstance(field_list, list) and isinstance(list_val, list):
        normalized: list[Any] = []
        for row in list_val:
            if not isinstance(row, list):
                normalized.append(row)
                continue
            normalized.append(
                {
                    str(field): (row[idx] if idx < len(row) else None)
                    for idx, field in enumerate(field_list)
                }
            )
        meta = {k: v for k, v in payload.items() if k not in ("fieldList", "list")}
        return {**meta, "list": normalized} if meta else normalized

    # Case 2: already a list of objects.
    if isinstance(list_val, list):
        meta = {k: v for k, v in payload.items() if k != "list"}
        return {**meta, "list": list_val} if meta else list_val

    # Case 3: constant-list alias (category/structureType/... kept as meta).
    constants = payload.get("constants")
    if isinstance(constants, list):
        meta = {k: v for k, v in payload.items() if k != "constants"}
        return {**meta, "list": constants} if meta else constants

    # Cases 4 & 5: nothing to normalize.
    return payload


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
    # Add all missing columns in one concat rather than a per-column ``df[col] =``
    # loop, which fragments the frame (and triggers a PerformanceWarning) on wide
    # schemas. Fill stays ``None``/object to preserve the output contract — a plain
    # ``reindex`` would fill NaN and change the column dtype.
    missing = [col for col in schema if col not in df.columns]
    if missing:
        filler = pd.DataFrame(
            {col: [None] * len(df) for col in missing}, index=df.index, dtype="object"
        )
        df = pd.concat([df, filler], axis=1)
    result: pd.DataFrame = df[list(schema)]
    return result
