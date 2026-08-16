# ruff: noqa: RUF001
# (RUF001 disabled file-wide: the columnar mismatch message is user-facing Chinese
# text that intentionally uses fullwidth punctuation.)
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pandas as pd

from gangtise_openapi._errors import ValidationError


def zip_field_row(fields: Sequence[Any], row: Sequence[Any], source: Any = None) -> dict[str, Any]:
    """Zip one columnar row against ``fieldList``, refusing a length mismatch.

    Upstream has TWO behaviours for a ``fieldList`` naming a field the endpoint
    does not have (probed by the CLI 2026-07-24): ``day-kline`` / ``minute-kline``
    / ``fund-flow`` drop the name AND the value, and the three financial
    statements pad with null — both keep the lengths equal, so both are safe. But
    ``quote.realtime`` / ``fundamental.main-business`` /
    ``fundamental.valuation-analysis`` return values for the VALID fields only
    while echoing the requested field NAMES verbatim. Once the lengths differ,
    positional zipping pastes each value onto the wrong field: asking realtime for
    ``["securityCode", "close", "turnoverRate"]`` (realtime has no ``close``)
    returns 2 values, and a turnover rate of 28.5573 lands under ``close`` —
    reading as "茅台收盘价 28.56" when the real price is 1297.41. No error, a
    plausible number, an entirely different metric. Silent mis-columning has to
    become an explicit failure (TS v0.28.3).

    The message cannot assert "you passed a bad field name": ``alternative.edb_data``
    goes through the same zip and has no ``field`` parameter at all, so a mismatch
    there can only mean the upstream response shape changed.

    ``source`` is the payload the row came out of. A structural failure is exactly
    what support needs to trace, and ``ValidationError`` carries no ``trace_id``
    property of its own, so the id is appended to the message (mirrors the CLI's
    ``traceSuffix``). Passing it is optional so a caller holding only the rows can
    still use the helper.
    """
    if len(row) != len(fields):
        carried = getattr(source, "envelope_trace_id", None)
        trace = f"（trace {carried}）" if isinstance(carried, str) else ""
        raise ValidationError(
            f"响应字段数与 fieldList 不匹配（fieldList {len(fields)} 项、该行返回 "
            f"{len(row)} 个值）——按位置拍平会把值贴到错误的字段上，已拒绝输出。"
            "传了 field= 的方法多为写了该接口不存在的字段名（上游只返回有效字段的值、"
            "字段名却按请求回显）：核对 field 取值（如 quote.realtime 没有 close，"
            "最新价是 latestPrice），不确定就别传 field（返回全量字段最稳）。"
            "没有 field 参数的方法（如 alternative.edb_data）出现此错，"
            "是上游响应结构异常，请报障。" + trace
        )
    return {str(field): row[idx] for idx, field in enumerate(fields)}


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
        normalized: list[Any] = [
            zip_field_row(field_list, row, payload) if isinstance(row, list) else row
            for row in list_val
        ]
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
