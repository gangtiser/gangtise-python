# ruff: noqa: RUF002, RUF003
# (Disabled file-wide: the docstrings quote Chinese indicator/column names from
# live probes and intentionally use fullwidth punctuation.)
"""Flatten the EDE matrix payloads into the wide row shape the wrappers expect.

The ``indicator.cross-section`` / ``time-series`` / ``screener`` endpoints answer
with a ``values`` matrix plus axis lists rather than ready-made rows. Ported from
``gangtise-openapi-cli/src/core/indicatorMatrix.ts``.

Shapes here match the EDE response as of the **2026-08-01 API revision**, which
replaced the parallel ``indicatorCodeList`` / ``indicatorNameList`` arrays with a
single structured ``indicatorList`` and **transposed** the cross-section matrix.
``values`` is ``[security][indicator]`` for cross-section and the screener, and
stays ``[series][date]`` for time-series.

Failure model, mapped from the CLI's exit codes onto SDK conventions:

* a shape that would **misattribute values** raises :class:`ApiError` (the CLI's
  exit 1) — a fabricated identity looks like a valid answer, so it must be loud;
* a shape that only costs **information** (a dropped caption, a missing output
  column) emits ``warnings.warn`` and marks the result ``partial`` (exit 3),
  matching what ``_pagination`` / ``quote`` already do for short pulls.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterable, Sequence
from typing import Any

from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._transport import unwrap_envelope

KeyBy = str

# Metadata column names the flatteners write themselves. Pre-seeded into the
# header set so an indicator literally named "security" / "name" / "date" gets a
# suffixed header instead of clobbering the cell that identifies the row.
CROSS_SECTION_COLUMNS = ("security", "name")
TIME_SERIES_COLUMNS = ("date",)


def unwrap_indicator_data(raw: Any) -> Any:
    """Peel the inner ``{code, status, data}`` envelope the EDE endpoints add.

    The shared client strips the outer envelope; historically these endpoints
    left a second one around the real payload. A failure code carried only by
    that inner envelope must surface as an :class:`ApiError` instead of rendering
    its null payload as success. Delegates to the shared ``unwrap_envelope`` so
    envelope handling stays single-sourced.
    """
    return unwrap_envelope(raw)


def _as_string_array(value: Any) -> list[str] | None:
    return [str(item) for item in value] if isinstance(value, list) else None


def _as_identity_array(data: Any, value: Any, key: str) -> list[str] | None:
    """An IDENTITY axis — the security a row belongs to, the date a column does.

    ``str(item)`` would turn a ``None`` into the literal ``"null"``/``"None"`` and
    render it as a perfectly plausible label (probed by the CLI 2026-08-02:
    ``dates: [null]`` produced ``date: "null"``), so a fabricated identity would
    reach the caller as a successful answer. Nothing here may be coerced: every
    entry must already be a non-empty string.
    """
    if not isinstance(value, list):
        return None
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ApiError(
                f"Indicator matrix shape mismatch: {key}[{i}] is not a usable identifier "
                f"({item!r}) — rows would be labelled with a value that identifies nothing",
                details=data,
            )
    return list(value)


def _as_indicator_meta_list(data: Any, value: Any) -> list[dict[str, Any]] | None:
    """Indicator metadata is an identity axis too: ``key_by='code'`` addresses
    columns by ``code``, so an entry without one cannot be mapped back to what was
    asked for. A non-dict entry used to collapse into ``{}`` and surface as
    ``col0``."""
    if not isinstance(value, list):
        return None
    for i, item in enumerate(value):
        code = item.get("code") if isinstance(item, dict) else None
        if not isinstance(item, dict) or not isinstance(code, str) or not code.strip():
            raise ApiError(
                f"Indicator matrix shape mismatch: indicatorList[{i}] carries no usable "
                f"`code` ({item!r}) — the column could not be mapped back to a requested "
                "indicator",
                details=data,
            )
    return list(value)


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _build_headers(
    bases: Sequence[str | None],
    suffixes: Sequence[str | None],
    reserved: Iterable[str],
) -> list[str]:
    """One column header per series; prefer the human-readable name, append a
    disambiguator on a duplicate so a column is never silently overwritten.

    An empty/missing name falls through to the suffix (Python ``or`` vs TS ``??``)
    — a blank column header is useless, so this minor divergence from the CLI is
    intentional and predates this module."""
    used: set[str] = set(reserved)
    headers: list[str] = []
    for i, raw_base in enumerate(bases):
        suffix = suffixes[i] if i < len(suffixes) else None
        base = raw_base or suffix or f"col{i}"
        header = base
        attempt = 1
        while header in used:
            tag = suffix if suffix is not None else i
            header = f"{base} ({tag})" if attempt == 1 else f"{base} ({tag})_{attempt}"
            attempt += 1
        used.add(header)
        headers.append(header)
    return headers


def _indicator_headers(
    indicators: Sequence[dict[str, Any]], key_by: KeyBy, reserved: Iterable[str]
) -> list[str]:
    """Column headers for a list of indicator metadata.

    ``key_by='code'`` makes each column its ``code`` (unique, and independent of
    the display name or the server's column order) instead of the human name —
    required for batch code→value mapping, where names collide (many indicators
    share a display name) and the server reorders columns relative to the request.
    The screener disambiguates by ``field`` instead, because there the SAME code
    may legitimately appear twice under two variables with different parameters.
    """
    codes = [_optional_string(meta.get("code")) for meta in indicators]
    fields: list[str | None] = []
    for i, meta in enumerate(indicators):
        field = _optional_string(meta.get("field"))
        fields.append(codes[i] if field is None else field)
    bases: list[str | None] = (
        list(codes) if key_by == "code" else [_optional_string(m.get("name")) for m in indicators]
    )
    # On a screener payload every column carries its variable, so a repeated base
    # can suffix ALL of its occurrences instead of leaving the first one bare. A
    # bare `收盘价` next to `收盘价 (F2)` reads as "the" close price when it is
    # really just whichever variable the server happened to list first.
    is_screener = any("field" in meta for meta in indicators)
    if not is_screener:
        return _build_headers(bases, fields, reserved)
    repeated = {base for i, base in enumerate(bases) if base is not None and bases.index(base) != i}
    tagged: list[str | None] = [
        f"{base} ({fields[i] if fields[i] is not None else i})"
        if base is not None and base in repeated
        else base
        for i, base in enumerate(bases)
    ]
    return _build_headers(tagged, fields, reserved)


def is_empty_matrix(data: Any) -> bool:
    """A response carrying neither securities nor indicators: the query as a whole
    resolved to nothing. This is NOT a dropped axis, so it must not be reported as
    partial — calling every requested code "omitted" would be false metadata, the
    diff against the request is total by construction.

    What it MEANS changed on 2026-08-07: a genuine no-data answer (non-trading
    date, uncovered market, future date) now comes back as a null cell with its
    row and column intact, so an all-empty matrix no longer means "no data". It
    now means nothing in the request RESOLVED — every security code or every
    indicator code was unrecognised — or a parameter name is wrong.

    The check covers every STRUCTURAL array, not just the two axis lists: anything
    looser would let a malformed payload (``values: null``, a missing ``values``,
    dates with no matrix) pass as "legitimately empty". Probed by the CLI
    2026-08-02: a time-series all-empty answer is five empty arrays, a
    cross-section one is four (it carries no ``dates`` key at all), hence "absent
    or empty" rather than a flat count.

    ``securityNameList`` is deliberately NOT checked: it holds display labels, not
    structure, so a ``None`` there cannot misalign anything — and rejecting it
    would re-introduce the false-partial this function exists to prevent.
    """
    if not isinstance(data, dict):
        return False
    securities = _as_string_array(data.get("securityCodeList"))
    if securities is None or len(securities) != 0:
        return False
    indicators = data.get("indicatorList")
    if not isinstance(indicators, list) or len(indicators) != 0:
        return False
    values = data.get("values")
    if not isinstance(values, list) or len(values) != 0:
        return False
    # `dates` is time-series only; when present it must be empty too.
    if "dates" not in data:
        return True
    dates = data.get("dates")
    return isinstance(dates, list) and len(dates) == 0


def dropped_from_matrix(
    data: Any, requested_securities: Sequence[str], requested_indicators: Sequence[str]
) -> tuple[list[str], list[str]]:
    """What the caller asked for that the response does not contain.

    The server used to drop any axis it had no DATA for, which made this a
    coverage check. Re-probed 2026-08-08: a coverage gap is now padded with
    ``null`` and keeps its row and column, down to the 1×1 case. What still
    disappears is a code the server cannot RESOLVE: an unknown indicator code, or
    a security code with the wrong market suffix (``AAPL.US`` vanishes, ``AAPL.O``
    returns).

    So the remaining shape is the dangerous one: a misspelled code is invisible
    otherwise — ``key_by='code'`` batch mapping finds no key at all rather than a
    null, and the pull quietly returns fewer rows than requested.

    Universe entries with no ``.`` are skipped — those are sector IDs, which the
    server expands into constituents, so their absence from the response is
    expected rather than a dropped row.
    """
    if not isinstance(data, dict):
        return [], []
    returned_securities = set(_as_string_array(data.get("securityCodeList")) or [])
    meta_list = data.get("indicatorList")
    returned_indicators = {
        _optional_string(meta.get("code"))
        for meta in (meta_list if isinstance(meta_list, list) else [])
        if isinstance(meta, dict)
    }
    return (
        [c for c in requested_securities if "." in c and c not in returned_securities],
        [c for c in requested_indicators if c not in returned_indicators],
    )


def _assert_matrix_payload(data: Any, payload: dict[str, Any]) -> None:
    """True only when the payload carries NONE of the EDE matrix keys — a foreign
    shape. Nothing legitimately reaches the flatteners in that state (``search``
    prints its unwrapped list directly, ``raw=True`` bypasses them), so this is a
    protocol failure, not a payload to hand back: returning it would surface the
    raw envelope as a successful answer."""
    if not any(
        key in payload
        for key in ("securityCodeList", "securityNameList", "indicatorList", "dates", "values")
    ):
        raise ApiError(
            "Indicator matrix shape mismatch: the response carries none of the matrix "
            "fields — the response layout may have changed",
            details=data,
        )


def _assert_axis(data: Any, axis: Any, key: str) -> None:
    if axis is None:
        raise ApiError(
            f"Indicator matrix shape mismatch: the response is missing `{key}` or it is "
            "not an array — the response layout may have changed",
            details=data,
        )


def _assert_values_present(data: Any, values: Any) -> None:
    if not isinstance(values, list):
        raise ApiError(
            "Indicator matrix shape mismatch: the response carries axis lists but no "
            "`values` array — the response layout may have changed",
            details=data,
        )


def _assert_matrix_shape(
    data: Any, values: list[Any], rows: int, row_axis: str, cols: int, col_axis: str
) -> None:
    """The matrix and its axis labels must agree on BOTH dimensions, or cells are
    dropped or misread. The 2026-08-01 revision transposed cross-section without a
    version marker, so a re-transpose has to fail loudly rather than silently
    relabel columns — with the caveat that this only catches a NON-SQUARE change.

    Row length is checked exactly, not leniently: the server pads a row with
    ``null`` rather than truncating it (probed 2026-08-02 across A/HK/US, where a
    US security missing 3 of 4 indicators still came back with a full-length row).
    A short or long row is therefore a structural change, not missing data.
    """
    if len(values) != rows:
        raise ApiError(
            f"Indicator matrix shape mismatch: got {len(values)} value rows for {rows} "
            f"{row_axis} — the response layout may have changed",
            details=data,
        )
    for i, row in enumerate(values):
        width = len(row) if isinstance(row, list) else -1
        if width != cols:
            shown = "no array of" if width < 0 else str(width)
            raise ApiError(
                f"Indicator matrix shape mismatch: value row {i} has {shown} cells for "
                f"{cols} {col_axis} — the response layout may have changed",
                details=data,
            )


def _resolve_security_names(names: Any, codes: Sequence[str]) -> list[str] | None:
    """Resolve display names for a security axis, degrading instead of failing.

    Names are consumed POSITIONALLY, so a list that does not line up cannot be
    trusted at all: ``["泡泡玛特"]`` against ``["600519.SH","09992.HK"]`` labels
    茅台's series 泡泡玛特, and a ``[None]`` element used to render a column
    literally headed ``"None"`` (both probed by the CLI 2026-08-02).

    But a name is a LABEL, not structure — ``securityCodeList`` already carries
    identity and every header falls back to the code. So an anomaly here drops the
    names and keeps the values rather than killing a query whose numbers are all
    correct. That is a deliberate asymmetry with the other guards in this module:
    they protect against MISATTRIBUTED VALUES and must be fatal; this one protects
    a caption.
    """
    if names is None:
        return None
    if not isinstance(names, list) or len(names) != len(codes):
        shown = f"{len(names)} entries" if isinstance(names, list) else "no array"
        warnings.warn(
            f"securityNameList carries {shown} for {len(codes)} securities; names are "
            "positional, so all of them were dropped — columns fall back to the "
            "security code.",
            stacklevel=2,
        )
        return None
    warned = False
    resolved: list[str] = []
    for i, name in enumerate(names):
        if isinstance(name, str) and name.strip():
            resolved.append(name)
            continue
        # A blank or null name is a plausible gap for one security — fall back
        # quietly. A non-string (a dict, a number) means the field changed type,
        # which is worth saying once.
        if not isinstance(name, str) and name is not None and not warned:
            warned = True
            warnings.warn(
                "securityNameList holds non-string entries; those columns fall back to "
                "the security code.",
                stacklevel=2,
            )
        resolved.append(codes[i])
    return resolved


def require_indicator_matrix(raw: Any) -> dict[str, Any]:
    """Unwrap and demand an object payload.

    The matrix endpoints cannot legitimately answer with a non-object payload:
    ``indicator.search`` never reaches the flatteners and ``raw=True`` bypasses
    them, so there is no caller for which ``None``, a list, or a foreign scalar is
    a valid cross-section / time-series / screener body. Checked BEFORE the
    payload is handed on, because a ``data: null`` cannot carry any of the
    response context an :class:`ApiError` needs to stay traceable.
    """
    data = unwrap_indicator_data(raw)
    if not isinstance(data, dict):
        got = (
            "null"
            if data is None
            else "an array"
            if isinstance(data, list)
            else type(data).__name__
        )
        raise ApiError(
            f"Indicator API returned no matrix object (got {got}) — the response layout "
            "may have changed",
            details=raw,
        )
    return data


def _require_object(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        got = (
            "null"
            if data is None
            else "an array"
            if isinstance(data, list)
            else type(data).__name__
        )
        raise ApiError(
            f"Indicator API returned no matrix object (got {got}) — the response layout "
            "may have changed",
            details=data,
        )
    return data


def flatten_cross_section(data: Any, key_by: KeyBy = "name") -> dict[str, Any]:
    """Cross-section (and the screener, whose payload is the same shape plus a
    per-indicator ``field``): one row per security, one column per indicator.

    ``values`` is ``[security][indicator]``, so security ``i``'s value for
    indicator ``j`` is ``values[i][j]``. There is no row-level date any more — the
    query date now lives in each indicator's own parameters and may legitimately
    differ per column.
    """
    payload = _require_object(data)
    _assert_matrix_payload(data, payload)
    # Past this point the payload claims to be a matrix, so every axis it needs
    # must actually be there. A null or absent axis is a broken response.
    security_code = _as_identity_array(data, payload.get("securityCodeList"), "securityCodeList")
    indicators = _as_indicator_meta_list(data, payload.get("indicatorList"))
    _assert_axis(data, security_code, "securityCodeList")
    _assert_axis(data, indicators, "indicatorList")
    assert security_code is not None and indicators is not None  # narrowed by _assert_axis
    values = payload.get("values")
    _assert_values_present(data, values)
    assert isinstance(values, list)
    _assert_matrix_shape(
        data, values, len(security_code), "securities", len(indicators), "indicators"
    )

    security_name = _resolve_security_names(payload.get("securityNameList"), security_code)
    headers = _indicator_headers(indicators, key_by, CROSS_SECTION_COLUMNS)

    rows: list[dict[str, Any]] = []
    for i, code in enumerate(security_code):
        # Only create `name` when there IS one: an always-present `name: None` is
        # invisible in JSON but renders as a real empty column in a DataFrame.
        row: dict[str, Any] = (
            {"security": code, "name": security_name[i]}
            if security_name is not None
            else {"security": code}
        )
        cells = values[i]
        for j, header in enumerate(headers):
            row[header] = cells[j]
        rows.append(row)
    return {"list": rows, "total": len(rows)}


def flatten_time_series(
    data: Any, key_by: KeyBy = "name", requested_universe: Sequence[str] | None = None
) -> dict[str, Any]:
    """Time-series: one row per date.

    Columns are the indicators (single-security case) or the securities
    (single-indicator case) — exactly one dimension varies, per the API contract.
    ``values`` stays a 2D ``[series][date]`` matrix.

    Axis rule, in priority order:

    1. More than one indicator came back → multi-indicator × single-security.
    2. More than one security came back → single-indicator × multi-security. This
       is what a sector ID produces: the request carries ONE universe entry and
       the server expands it into N constituents, so the request count says
       nothing about the axis.
    3. Both are 1 → genuinely ambiguous, so fall back to what was REQUESTED: a
       universe holding a sector ID always takes the security axis (the caller
       asked "which securities", and an indicator-named column would erase whose
       series this is); otherwise the entry count decides, because the server
       drops securities with no data at all and a two-security request that comes
       back with one must still be labelled by security.
    """
    payload = _require_object(data)
    _assert_matrix_payload(data, payload)
    dates = _as_identity_array(data, payload.get("dates"), "dates")
    security_code = _as_identity_array(data, payload.get("securityCodeList"), "securityCodeList")
    indicators = _as_indicator_meta_list(data, payload.get("indicatorList"))
    _assert_axis(data, dates, "dates")
    _assert_axis(data, security_code, "securityCodeList")
    _assert_axis(data, indicators, "indicatorList")
    assert dates is not None and security_code is not None and indicators is not None
    values = payload.get("values")
    _assert_values_present(data, values)
    assert isinstance(values, list)

    security_name = _resolve_security_names(payload.get("securityNameList"), security_code)
    # Data with only one identity axis is unattributable: `securityCodeList: []`
    # alongside a populated matrix leaves every row belonging to no security at
    # all, and the row/column counts still line up so no other guard notices. A
    # response that resolved to nothing empties `dates` too (probed 2026-08-02),
    # so dates alongside a missing axis is always a broken response.
    if dates and (not security_code or not indicators):
        raise ApiError(
            f"Indicator matrix shape mismatch: the time-series response carries "
            f"{len(dates)} dates but {len(security_code)} securities and "
            f"{len(indicators)} indicators — the data could not be attributed",
            details=data,
        )
    # The API permits multi-indicator × single-security OR single-indicator ×
    # multi-security, never both — the server rejects such a REQUEST with 100003.
    # A RESPONSE carrying both axes plural is therefore unattributable: whichever
    # axis becomes the columns, the other one's identity is silently discarded
    # (probed 2026-08-02: 2×2 rendered as 收盘价/成交量 with both securities gone,
    # and dropped_from_matrix sees nothing missing so it would not even flag).
    if len(security_code) > 1 and len(indicators) > 1:
        raise ApiError(
            f"Indicator matrix shape mismatch: the time-series response carries "
            f"{len(security_code)} securities AND {len(indicators)} indicators, which "
            "the endpoint does not support — one of the two identities would be lost",
            details=data,
        )
    # A universe entry without a `.` is a sector ID — the server expands it, so
    # neither its presence nor the entry count says anything about the axis.
    requested = None if requested_universe is None else list(dict.fromkeys(requested_universe))
    has_sector = any("." not in entry for entry in requested) if requested is not None else False
    if len(indicators) > 1:
        series_are_indicators = True
    elif len(security_code) > 1 or has_sector:
        # A sector request always takes the security axis: the sector may expand to
        # one constituent, or the rest may have been dropped for lack of data —
        # either way an indicator-named column would erase whose series this is.
        series_are_indicators = False
    else:
        series_are_indicators = (
            len(requested) if requested is not None else len(security_code)
        ) <= 1
    series_count = len(indicators) if series_are_indicators else len(security_code)
    _assert_matrix_shape(
        data,
        values,
        series_count,
        "indicators" if series_are_indicators else "securities",
        len(dates),
        "dates",
    )
    # Build over securityCode rather than securityNameList directly: a response
    # that omits the names must still yield one header per security (falling back
    # to the code), not zero columns.
    if series_are_indicators:
        headers = _indicator_headers(indicators, key_by, TIME_SERIES_COLUMNS)
    else:
        bases: list[str | None] = [
            code if key_by == "code" else (security_name[i] if security_name else None)
            for i, code in enumerate(security_code)
        ]
        headers = _build_headers(bases, list(security_code), TIME_SERIES_COLUMNS)

    rows: list[dict[str, Any]] = []
    for k, date in enumerate(dates):
        row: dict[str, Any] = {"date": date}
        for i, header in enumerate(headers):
            row[header] = values[i][k]
        rows.append(row)
    return {"list": rows, "total": len(rows)}


# ─────────────────────────── screener expressions ───────────────────────────

# Screener variables are `F` + a positive integer; the server rejects anything
# else, and a typo'd variable would otherwise surface as an opaque expression
# error rather than pointing at the binding that is wrong.
_SCREENER_FIELD = re.compile(r"^F[1-9][0-9]*$", re.ASCII)
# Variable references inside an expression, e.g. the F1/F2 in `F1 >= 800 && F2 <= 30`.
_SCREENER_FIELD_REF = re.compile(r"\bF[1-9][0-9]*\b", re.ASCII)
# String literals are stripped first, so a `contains 'F2 系列'` operand is never
# mistaken for a reference.
_SCREENER_STRING_LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"")


def screener_expression_fields(expression: str | None) -> list[str]:
    """Variables the expression actually filters on, string literals stripped.

    These are the bindings whose VALUES the result depends on — a column missing
    for one of them means the filter cannot be shown to have been applied."""
    stripped = _SCREENER_STRING_LITERAL.sub("", expression or "")
    return _SCREENER_FIELD_REF.findall(stripped)


def _tokenize_screener_expression(src: str) -> list[str]:
    """Split an expression into ``(``, ``)``, ``&&``, ``||`` and the atoms between
    them. String literals are copied verbatim so a ``||`` or an ``F2`` inside one
    is never mistaken for syntax."""
    tokens: list[str] = []
    atom = ""
    i = 0
    while i < len(src):
        ch = src[i]
        if ch in ("'", '"'):
            close = src.find(ch, i + 1)
            stop = len(src) if close == -1 else close + 1
            atom += src[i:stop]
            i = stop
        elif src.startswith("&&", i) or src.startswith("||", i):
            if atom.strip():
                tokens.append(atom)
            atom = ""
            tokens.append(src[i : i + 2])
            i += 2
        elif ch in ("(", ")"):
            if atom.strip():
                tokens.append(atom)
            atom = ""
            tokens.append(ch)
            i += 1
        else:
            atom += ch
            i += 1
    if atom.strip():
        tokens.append(atom)
    return tokens


def screener_expression_is_evaluable(expression: str | None, present: set[str]) -> bool:
    """Whether the expression still has a path that could have been evaluated,
    given the variables the response actually returned a column for.

    The boolean structure decides, not the mere presence of a ``||``:

    * a term is evaluable when every variable it names has a column;
    * ``A && B`` needs BOTH sides — a missing mandatory conjunct is an unprovable
      claim even if the other side is a disjunction;
    * ``A || B`` needs only one — a row can legitimately match through one operand
      while the other is not evaluable at all (probed 2026-08-03: ``F1 > 0 || F2 >
      0`` over 09992.HK, where ``finc_pe_ttm`` has no HK coverage, matches on F2).

    So ``F1 && (F2 || F3)`` missing F1, and ``F1 || F2`` missing both, are both
    unevaluable and must fail — checking only for a ``||`` anywhere would let them
    through.
    """
    tokens = _tokenize_screener_expression(expression or "")
    pos = 0

    def unit() -> bool:
        nonlocal pos
        if pos < len(tokens) and tokens[pos] == "(":
            pos += 1
            value = or_()
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return value
        atom = tokens[pos] if pos < len(tokens) else ""
        pos += 1
        # A term naming no variable (a literal comparison) is always evaluable.
        refs = _SCREENER_FIELD_REF.findall(_SCREENER_STRING_LITERAL.sub("", atom))
        return all(ref in present for ref in refs)

    def and_() -> bool:
        nonlocal pos
        value = unit()
        # Evaluate both sides before combining: short-circuiting would leave the
        # parser mid-expression.
        while pos < len(tokens) and tokens[pos] == "&&":
            pos += 1
            right = unit()
            value = value and right
        return value

    def or_() -> bool:
        nonlocal pos
        value = and_()
        while pos < len(tokens) and tokens[pos] == "||":
            pos += 1
            right = and_()
            value = value or right
        return value

    return or_()


def parse_screener_indicators(
    bindings: dict[str, str],
    params: dict[str, dict[str, Any]] | None,
    expression: str | None,
) -> list[dict[str, Any]]:
    """Turn ``{"F1": "qte_mkt_cptl"}`` bindings plus per-variable params into the
    ``indicatorList`` the screener endpoint expects.

    Params key off the VARIABLE, not the code, because the same indicator may
    legitimately appear under two variables with different parameters (e.g. the
    same price on two dates) — only the variable tells them apart.
    """
    param_map = params or {}
    indicators: list[dict[str, Any]] = []
    for field, code in bindings.items():
        if not isinstance(field, str) or not _SCREENER_FIELD.match(field):
            raise ValidationError(
                f"invalid indicator variable {field!r}: expected F followed by a positive "
                "integer, e.g. F1"
            )
        if not isinstance(code, str) or not code.strip():
            raise ValidationError(
                f"invalid indicator binding for {field!r}: expected an indicator code, got {code!r}"
            )
        indicators.append(
            {
                "field": field,
                "indicatorCode": code,
                # A ``None`` value is a SUPPRESSION MARKER, not a value ("this
                # indicator does not take this key"), so it must never reach the
                # wire — mirrors ``domains.indicator._param_groups``.
                "parameters": [
                    {"paramKey": k, "paramValue": str(v)}
                    for k, v in (param_map.get(field) or {}).items()
                    if v is not None
                ],
            }
        )
    bound = {item["field"] for item in indicators}
    # A param for an unbound variable is silently dropped by the server, so the
    # query would run with a filter the caller believes is applied but is not.
    for field in param_map:
        if field not in bound:
            raise ValidationError(f"indicator_param references {field!r}, which no indicator binds")
    # The server does reject this (100003), but only after a round trip — and the
    # symmetric mistake (binding a variable the expression never uses) it accepts
    # silently while still billing the extra column.
    for ref in screener_expression_fields(expression):
        if ref not in bound:
            raise ValidationError(f"expression references {ref!r}, which no indicator binds")
    return indicators


def check_screener_bindings(
    data: Any, requested: Sequence[dict[str, Any]], expression: str | None
) -> list[str]:
    """Validate the variable bindings a screener answered with, returning the bound
    variables that are merely missing.

    The screener answers with the variable each column was requested under, and
    that binding is the ONLY thing tying a column back to the filter it came from
    — nothing else in the payload can catch it going wrong. A swapped or unknown
    ``field`` renders as a perfectly ordinary result (probed 2026-08-02: a
    response labelling a requested ``F1`` as ``F9`` printed a normal table), which
    would make every screening decision downstream unfounded.

    Every returned entry must therefore name a REQUESTED variable and carry that
    variable's code, and no variable may appear twice. A wholly empty result binds
    nothing and is left alone.
    """
    if not isinstance(data, dict):
        return []
    securities = data.get("securityCodeList")
    # A result with no securities matched nothing and binds nothing — the
    # canonical empty answer, left alone.
    if not isinstance(securities, list) or not securities:
        return []
    meta_list = data.get("indicatorList")
    indicators = meta_list if isinstance(meta_list, list) else []
    wanted = {item["field"]: item["indicatorCode"] for item in requested}
    seen: set[str] = set()
    for i, meta in enumerate(indicators):
        field = _optional_string(meta.get("field")) if isinstance(meta, dict) else None
        code = _optional_string(meta.get("code")) if isinstance(meta, dict) else None
        if not field or field not in wanted:
            named = f'"{field}"' if field else "no variable"
            raise ApiError(
                f"Screener binding mismatch: indicatorList[{i}] is bound to {named}, which "
                "was never requested — the column cannot be traced to a filter",
                details=data,
            )
        if wanted[field] != code:
            raise ApiError(
                f'Screener binding mismatch: variable {field} came back as "{code}" but was '
                f'requested as "{wanted[field]}" — the filter and the column disagree',
                details=data,
            )
        if field in seen:
            raise ApiError(
                f"Screener binding mismatch: variable {field} appears twice in the response "
                "— the mapping back to a filter is ambiguous",
                details=data,
            )
        seen.add(field)
    # Securities came back, so the filter ran. A column vanishing is never "it got
    # filtered out" — filtering removes securities (rows), never indicators
    # (columns). Since 2026-08-07 a covered-but-empty indicator keeps a null
    # column, so an absent column means the server did not resolve that indicator
    # code at all. Whether that is fatal follows the expression's BOOLEAN
    # STRUCTURE, not the mere presence of a `||`.
    if not screener_expression_is_evaluable(expression, seen):
        absent = [f for f in dict.fromkeys(screener_expression_fields(expression)) if f not in seen]
        plural = len(absent) > 1
        raise ApiError(
            "Screener binding mismatch: the expression cannot be evaluated from what came "
            f"back — {', '.join(absent)} {'have' if plural else 'has'} no column, and no "
            f"branch of the expression survives without {'them' if plural else 'it'}, so the "
            "rows cannot be shown to satisfy it",
            details=data,
        )
    # Whatever survives is an output column that went missing: information lost,
    # correctness intact.
    return [field for field in wanted if field not in seen]
