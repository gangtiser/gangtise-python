"""An explicit empty list — or a blank string — is refused before any request, and the
refusal names the caller's argument.

Swept over every public wrapper of every domain, sync AND async, and every list-typed
parameter, with ``[]``, ``"  "`` and ``["  "]``. The refusal must name the kwarg as written
(``type_``, ``security``, ``resource_type``), not its wire field (``type``,
``securityCodeList``, ``resourceTypes``). Required lists
are refused by their own "required" checks, which name the argument too; that is part
of the contract. The only empty filter allowed through is the one mapped to the CLI's
"all" (``vault.stock_pool_stocks(pool_id=[])``).
"""

from __future__ import annotations

import inspect
import re
import warnings
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from gangtise_openapi import domains as D
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ValidationError

_DOMAINS = (
    "Insight",
    "Quote",
    "Fundamental",
    "AI",
    "Vault",
    "Alternative",
    "Indicator",
    "Reference",
    "Bond",
    "Fund",
    "Tool",
)
_PLACEHOLDERS: dict[str, Any] = {
    "start_date": "2026-09-01",
    "end_date": "2026-09-05",
    "date": "2026-09-01",
    "start_time": "2026-09-01",
    "end_time": "2026-09-02",
    "query_mode": "bySecurity",
    "report_date": "2026-06-30",
    "period": "2025annual",
    "expression": "F1>0",
    "category": "industry",
    "type_": "file",
    "space_type": 1,
}
# Methods whose OTHER checks would refuse the placeholder call before the empty list is
# looked at; given what they need, the sweep reaches the argument under test.
_OVERRIDES: dict[str, dict[str, Any]] = {
    "performance_calendar_list": {"size": 5},
    "valuation_analysis": {"indicator": "peTtm"},
    "screener": {"indicator": {"F1": "qte_close"}},
    "announcement": {"security": "019742.SH"},
    "issuer_info": {"security": "019742.SH"},
    "issuer_rating_change": {"security": "019742.SH"},
    "default_list": {"security": "019742.SH"},
}
_SKIP = {"file_parse", "file_parse_check", "drive_upload"}
_ALLOWED_TO_SEND = {("Vault", "stock_pool_stocks", "pool_id")}
_EMPTIES: tuple[Any, ...] = ([], "  ", ["  "])
_REFUSAL = re.compile(r"empty|blank|required|at least one|pass either")


def _list_params(fn: Any) -> list[inspect.Parameter]:
    params = inspect.signature(fn).parameters.values()
    # Selection is by annotation, so an unannotated parameter would be skipped silently.
    assert all(p.annotation is not inspect.Parameter.empty for p in params), fn
    return [
        p
        for p in params
        if any(t in str(p.annotation) for t in ("list", "Sequence", "FilterValue"))
        or str(p.annotation) == "Any"
    ]


def _cases(client: Any, prefix: str) -> list[tuple[str, str, str, Any, Callable[..., Any], dict]]:
    out = []
    for name in _DOMAINS:
        obj = getattr(D, prefix + name)(client)
        for mname, fn in inspect.getmembers(obj, inspect.ismethod):
            if mname.startswith("_") or "download" in mname or mname in _SKIP:
                continue
            sig = inspect.signature(fn)
            for lp in _list_params(fn):
                for empty in _EMPTIES:
                    kwargs = {
                        p.name: _PLACEHOLDERS.get(p.name, ["600519.SH"])
                        for p in sig.parameters.values()
                        if p.default is inspect.Parameter.empty
                    }
                    kwargs.update(_OVERRIDES.get(mname, {}))
                    kwargs[lp.name] = empty
                    out.append((name, mname, lp.name, empty, fn, kwargs))
    return out


def _judge(name, mname, param, empty, error, sent, problems):
    if (name, mname, param) in _ALLOWED_TO_SEND:
        return
    if sent:
        problems.append((name, mname, param, empty, "reached the server"))
    elif not isinstance(error, ValidationError):
        problems.append((name, mname, param, empty, f"not refused locally: {error!r}"[:90]))
    elif not re.search(rf"(?<![A-Za-z_]){re.escape(param)}(?![A-Za-z_])", str(error)):
        problems.append((name, mname, param, empty, f"misnamed: {str(error)[:60]}"))
    elif not _REFUSAL.search(str(error)):
        # Names the argument but for some other reason (an unrelated check that happens
        # to mention it) — the empty value itself was never judged.
        problems.append((name, mname, param, empty, f"unrelated refusal: {str(error)[:60]}"))


def _router() -> tuple[Any, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        data = {"total": 0, "list": [], "fieldList": []}
        return httpx.Response(200, json={"code": "000000", "status": True, "data": data})

    router = respx.mock(base_url="https://api.test", assert_all_called=False)
    router.route().mock(side_effect=answer)
    return router, calls


def test_every_empty_list_is_refused_naming_the_argument(seeded_config):
    problems: list[tuple] = []
    router, calls = _router()
    with router, GangtiseClient(_config=seeded_config) as client, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cases = _cases(client, "")
        for name, mname, param, empty, fn, kwargs in cases:
            before, error = len(calls), None
            try:
                fn(**kwargs)
            except Exception as exc:
                error = exc
            _judge(name, mname, param, empty, error, len(calls) > before, problems)
    assert len(cases) > 400
    assert not problems, problems


@pytest.mark.anyio
async def test_async_every_empty_list_is_refused_naming_the_argument(seeded_config):
    problems: list[tuple] = []
    router, calls = _router()
    with router, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            cases = _cases(client, "Async")
            for name, mname, param, empty, fn, kwargs in cases:
                before, error = len(calls), None
                try:
                    await fn(**kwargs)
                except Exception as exc:
                    error = exc
                _judge(name, mname, param, empty, error, len(calls) > before, problems)
    assert len(cases) > 400
    assert not problems, problems


def test_list_arguments_name_the_parameter_they_came_from():
    """`_as_list(value, name)` names `name` in its type refusals (a set, bytes, …), which
    the sweep above never exercises: a call passing another argument's name would
    blame the wrong one. Every literal name must be the variable it is called on."""
    from pathlib import Path

    import gangtise_openapi.domains as pkg

    calls = 0
    for path in Path(pkg.__file__).parent.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for var, label in re.findall(r'\b(?:_as_list|_unique)\((\w+), "(\w+)"\)', text):
            calls += 1
            assert var == label, f"{path.name}: _as_list({var}, {label!r})"
    assert calls > 200
