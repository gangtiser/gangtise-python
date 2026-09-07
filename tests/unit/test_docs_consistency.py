"""`sample/` is a second, hand-maintained copy of the wrapper surface — so it drifts.

Two ways it has drifted, both shipped before anyone noticed:

* `sample/API_PARAMETERS.md` documented parameters that no longer exist (calling a
  method as documented raises `TypeError`) and omitted ones that do.
* `sample/*/*.py` kept passing arguments to wrappers that had dropped them, so the
  scripts raised before reaching the network.

Neither is caught by running the samples — several need credentials, and the ones that
do run used `raw=True`, which skips the conversion where a bad field would surface.
These tests compare both against `inspect.signature`, so the drift is red instead.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Any

import pytest

import gangtise_openapi as g
from gangtise_openapi.domains._common import _ENUM_FIELDS

_ROOT = Path(__file__).resolve().parents[2]
_DOC = _ROOT / "sample" / "API_PARAMETERS.md"
_SAMPLES = _ROOT / "sample"
# Every domain the facade exposes; the parameter reference is expected to cover them all.
_DOMAINS = (
    "auth",
    "lookup",
    "reference",
    "insight",
    "quote",
    "fundamental",
    "ai",
    "vault",
    "alternative",
    "indicator",
    "tool",
)

pytestmark = pytest.mark.skipif(not _DOC.exists(), reason="sample/ is repo-only, not packaged")

# A table cell separator is an UNESCAPED `|`; a union type carries escaped ones.
_CELLS = re.compile(r"(?<!\\)\|")
_HEADING = re.compile(r"^### `([a-z_]+)\.([a-z_0-9]+)`")


def _resolve(domain: str, method: str) -> Any:
    facade = getattr(g.gangtise, domain, None)
    return getattr(facade, method, None) if facade is not None else None


def _documented_parameters() -> dict[str, set[str]]:
    """`{"domain.method": {param, ...}}` from the parameter tables."""
    tables: dict[str, set[str]] = {}
    current: str | None = None
    for line in _DOC.read_text().split("\n"):
        heading = _HEADING.match(line)
        if heading:
            current = f"{heading.group(1)}.{heading.group(2)}"
            tables.setdefault(current, set())
            continue
        if current and line.startswith("| `") and len(_CELLS.split(line)) == 8:
            name = _CELLS.split(line)[1].strip().strip("`")
            tables[current].add(name)
    return tables


def _signature_parameters(fn: Any) -> set[str]:
    return {
        name
        for name, p in inspect.signature(fn).parameters.items()
        if p.kind is not inspect.Parameter.VAR_KEYWORD
    }


def _public_methods() -> set[str]:
    """Every public `gangtise.<domain>.<method>` the facade exposes."""
    found: set[str] = set()
    for domain in _DOMAINS:
        facade = getattr(g.gangtise, domain, None)
        if facade is None:
            continue
        for name in dir(facade):
            if name.startswith("_"):
                continue
            member = getattr(facade, name, None)
            if callable(member) and not inspect.isclass(member):
                found.add(f"{domain}.{name}")
    return found


def test_the_documented_method_set_equals_the_public_one() -> None:
    """Set EQUALITY, not containment.

    Checking only "is every documented method real" leaves the other direction open:
    deleting a whole section — or shipping a new wrapper — stays green while the
    reference silently stops covering the SDK.
    """
    documented = set(_documented_parameters())
    public = _public_methods()
    assert not (documented - public), (
        f"documented but not a real method: {sorted(documented - public)}"
    )
    assert not (public - documented), (
        f"public methods with no section in API_PARAMETERS.md: {sorted(public - documented)}"
    )


def test_parameter_tables_match_the_signatures() -> None:
    """Both directions, for every method — not just the parameter of the day.

    The narrow version of this test (which checked `resolve_title` alone) passed while
    21 stale parameters and one omission sat in the same file.
    """
    extra: dict[str, list[str]] = {}
    absent: dict[str, list[str]] = {}
    for key, documented in _documented_parameters().items():
        fn = _resolve(*key.split("."))
        if fn is None:
            continue  # reported by test_every_documented_method_exists
        actual = _signature_parameters(fn)
        if documented - actual:
            extra[key] = sorted(documented - actual)
        if actual - documented:
            absent[key] = sorted(actual - documented)
    assert not extra, (
        "documented but NOT real parameters — calling these as documented raises "
        f"TypeError: {extra}"
    )
    assert not absent, f"real parameters missing from the table: {absent}"


def _sample_calls() -> list[tuple[Path, int, str, str, list[str]]]:
    """Every `gangtise[.async_].<domain>.<method>(...)` call in `sample/`."""
    calls = []
    for path in sorted(_SAMPLES.glob("*/*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            target, parts = node.func, []
            while isinstance(target, ast.Attribute):
                parts.append(target.attr)
                target = target.value
            if not isinstance(target, ast.Name) or target.id != "gangtise":
                continue
            parts.reverse()
            if parts[:1] == ["async_"]:
                parts = parts[1:]
            if len(parts) != 2:
                continue
            keywords = [kw.arg for kw in node.keywords if kw.arg]
            calls.append((path, node.lineno, parts[0], parts[1], keywords))
    return calls


class _Any:
    """Placeholder for `Signature.bind`, which only inspects argument NAMES."""


def test_sample_scripts_call_wrappers_correctly() -> None:
    """A sample that raises `TypeError` before the first request teaches nothing.

    `bind` covers BOTH directions in one call — an argument the wrapper does not take,
    and a required one the sample forgot. Checking only for extra keywords left the
    second open: dropping `security=` from the minute-kline sample stayed green.
    """
    problems = []
    for path, lineno, domain, method, keywords in _sample_calls():
        fn = _resolve(domain, method)
        where = f"{path.relative_to(_ROOT)}:{lineno}"
        if fn is None:
            problems.append(f"{where} calls {domain}.{method}, which does not exist")
            continue
        try:
            inspect.signature(fn).bind(**dict.fromkeys(keywords, _Any()))
        except TypeError as exc:
            problems.append(f"{where} {domain}.{method}({', '.join(keywords)}): {exc}")
    assert not problems, "\n".join(problems)


def test_the_sample_scan_actually_finds_calls() -> None:
    # Guards the guard: an AST walk that silently matches nothing would make both
    # sample tests vacuously green.
    assert len(_sample_calls()) > 300


def test_enum_examples_in_the_table_are_legal_values() -> None:
    """The Example column is prose the signature check cannot reach — but for the
    parameters the SDK itself whitelists, it is machine-checkable.

    All 13 `rank_type` / `search_type` examples said `0`, which every one of those
    endpoints rejects. Copy-pasted example values are the failure mode this catches.
    """
    legal = {f"`{v}`" for v in _ENUM_FIELDS["rankType"]}
    problems = []
    current: str | None = None
    for lineno, line in enumerate(_DOC.read_text().split("\n"), 1):
        heading = _HEADING.match(line)
        if heading:
            current = f"{heading.group(1)}.{heading.group(2)}"
            continue
        if not (current and line.startswith("| `") and len(_CELLS.split(line)) == 8):
            continue
        cells = [c.strip() for c in _CELLS.split(line)]
        if cells[1].strip("`") in ("rank_type", "search_type") and cells[5] not in legal:
            problems.append(f"{_DOC.name}:{lineno} {current}.{cells[1]} example is {cells[5]}")
    assert not problems, "legal values are 1/2:\n" + "\n".join(problems)
