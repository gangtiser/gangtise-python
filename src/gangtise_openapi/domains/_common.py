"""Shared helpers for domain wrappers.

These were previously duplicated verbatim across every ``domains/*.py`` file.
Keeping a single copy avoids drift — the per-file ``_extract_rows`` had already
diverged into two incompatible variants (one handled bare lists, one did not).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeAlias

import pandas as pd

from gangtise_openapi._normalize import normalize_rows, to_dataframe

# A filter argument: one value or a list of values, funneled through ``_as_list``
# into a camelCase ``...List`` body field. Elements are ``str | int`` because these
# are ID / enum / code filters the API accepts as either — the npm CLI sends strings,
# the SDK's own tests send ints (e.g. industry=1, permission=1), and ``source`` is
# numeric in one endpoint yet a string in another. A ``str``-only type would reject
# valid calls (regression caught by Codex review of 810bf19).
FilterValue: TypeAlias = str | int | Sequence[str | int]


def _as_list(value: Any) -> list[Any] | None:
    """Wrap a scalar in a list, pass lists/tuples through, leave ``None`` as ``None``."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None`` (unset optional fields)."""
    return {k: v for k, v in body.items() if v is not None}


def _extract_rows(result: Any) -> list[Any]:
    """Pull the row list out of any supported API payload shape.

    Runs the payload through :func:`normalize_rows` first, so columnar /
    matrix / single-object responses become a proper list of dicts instead of
    yielding an empty DataFrame.
    """
    normalized = normalize_rows(result)
    if isinstance(normalized, dict):
        rows = normalized.get("list", [])
        return rows if isinstance(rows, list) else []
    if isinstance(normalized, list):
        return normalized
    return []


def _columnar_dataframe(result: Any) -> pd.DataFrame | None:
    """Fast path for the columnar matrix payload ``{fieldList, list: [[...], ...]}``.

    When ``fieldList`` is a non-empty list of column-name strings and every row is a
    list of exactly ``len(fieldList)`` values, ``pd.DataFrame(rows, columns=fieldList)``
    builds the frame directly — skipping the per-row dict transpose in
    :func:`normalize_rows`, which is 2-5x slower and roughly doubles peak memory at
    K-line / financial-statement scale. Returns ``None`` for any other shape (dict
    rows, ragged rows, missing / non-string ``fieldList``, **duplicate** field names,
    empty ``list``) so the caller falls back to the normalize path, whose output is
    identical for those cases.

    The duplicate-name guard matters: ``normalize_rows`` builds a dict per row, so a
    repeated field collapses to its last value (one column); ``pd.DataFrame(rows,
    columns=fields)`` would instead emit two same-named columns. Falling back keeps
    the two paths equivalent. Mirrors the guard in quote's ``_kline_dataframe``.
    """
    if not isinstance(result, dict):
        return None
    fields = result.get("fieldList")
    rows = result.get("list")
    if (
        isinstance(fields, list)
        and fields
        and all(isinstance(f, str) for f in fields)
        and len(set(fields)) == len(fields)
        and isinstance(rows, list)
        and rows
        and all(isinstance(r, list) and len(r) == len(fields) for r in rows)
    ):
        return pd.DataFrame(rows, columns=fields)
    return None


def _result_to_dataframe(result: Any) -> pd.DataFrame:
    """Build a schema-less DataFrame from an API payload.

    Uses the columnar fast path when ``result`` is a clean matrix and otherwise falls
    back to ``to_dataframe(_extract_rows(result))``. The two produce identical frames
    (verified across numeric / None / mixed / bool dtypes) — the fast path is only
    quicker, so wrappers can call this in place of the explicit two-step form.
    """
    fast = _columnar_dataframe(result)
    if fast is not None:
        return fast
    return to_dataframe(_extract_rows(result), schema=None)
