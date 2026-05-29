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
      3. ``{"chatRoomList": [...]}`` — aliased to ``list`` (WeChat endpoints).
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

    # Case 3: WeChat chat-room alias.
    chat = payload.get("chatRoomList")
    if isinstance(chat, list):
        meta = {k: v for k, v in payload.items() if k != "chatRoomList"}
        return {**meta, "list": chat} if meta else chat

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
    for col in schema:
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df), dtype="object")
    result: pd.DataFrame = df[list(schema)]
    return result
