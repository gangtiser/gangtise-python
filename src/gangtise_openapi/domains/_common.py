"""Shared helpers for domain wrappers.

These were previously duplicated verbatim across every ``domains/*.py`` file.
Keeping a single copy avoids drift — the per-file ``_extract_rows`` had already
diverged into two incompatible variants (one handled bare lists, one did not).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeAlias

from gangtise_openapi._normalize import normalize_rows

# A filter argument accepting a single value or a list of values. Domain wrappers
# funnel these through ``_as_list`` into camelCase ``...List`` body fields.
StrOrList: TypeAlias = str | Sequence[str]


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
