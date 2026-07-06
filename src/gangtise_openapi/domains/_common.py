"""Shared helpers for domain wrappers.

These were previously duplicated verbatim across every ``domains/*.py`` file.
Keeping a single copy avoids drift — the per-file ``_extract_rows`` had already
diverged into two incompatible variants (one handled bare lists, one did not).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeAlias

from gangtise_openapi._normalize import normalize_rows

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
