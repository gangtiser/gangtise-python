"""The time-series calendar auto-selection (TS v0.40.0 ⑬-⑮, core/calendarType.ts).

The decision is tested against a stubbed client here; the endpoint suites check that
``time_series`` still consults it and puts the answer on the wire.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import anyio
import pytest

from gangtise_openapi._errors import ApiError
from gangtise_openapi.domains._common import ValidationError
from gangtise_openapi.domains.indicator import (
    _normalize_param_dates,
    _resolve_calendar_type,
    _resolve_calendar_type_async,
)

# parameterList shapes are the real ones (CLI probe 2026-09-19 via `indicator search
# --keyword <code>`). The two that decide the guard are `div_cash_yld` (declares BOTH
# reportDate and tradeDate) and the empty-list families — both must land on ND, and
# both would be missed by a naive "does it mention tradeDate" check.
CATALOG: dict[str, list[str]] = {
    "qte_close": ["tradeDate", "adjustType", "baseDate", "currency"],
    "qte_vol": ["tradeDate"],
    "finc_pe_ttm": ["tradeDate"],
    "is_op_rev": ["reportDate", "reportType", "currency", "scale"],
    "div_cash_yld": ["reportDate", "tradeDate"],
    "div_cash_yr": ["fiscalYear"],
    "frcst_pe": ["tradeDate", "fiscalYear"],
    "cdr_conv_ratio": [],
    "pty_op_scope": [],
}


def _answer(keyword: str, unknown: set[str]) -> Any:
    # The server answers a code keyword with near-matches too, so the resolver has to
    # pick its entry out by exact indicatorCode rather than taking [0] — hence the
    # decoy first. Shaped as the historical double-wrapped answer (the inner EDE
    # envelope); the live, single-envelope shape is covered by `_LiveShapeStubClient`.
    rows: list[dict[str, Any]] = [
        {"indicatorCode": f"{keyword}_wk", "parameterList": [{"paramKey": "tradeDate"}]}
    ]
    if keyword in CATALOG and keyword not in unknown:
        rows.append(
            {
                "indicatorCode": keyword,
                "parameterList": [{"paramKey": key, "required": True} for key in CATALOG[keyword]],
            }
        )
    return {"code": "000000", "status": True, "data": rows}


class _StubClient:
    def __init__(self, *, fail: set[str] | None = None, unknown: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.unknown = unknown or set()
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def _call(self, key: str, body: Any = None) -> Any:
        assert key == "indicator.search"
        keyword = body["keyword"]
        with self.lock:
            self.calls.append(keyword)
        if keyword in self.fail:
            raise ApiError("search unavailable", code="999999")
        return _answer(keyword, self.unknown)


class _AsyncStubClient(_StubClient):
    async def _call(self, key: str, body: Any = None) -> Any:  # type: ignore[override]
        return _StubClient._call(self, key, body)


def _resolve(indicators: list[str], **kwargs: Any) -> str | None:
    return _resolve_calendar_type(_StubClient(**kwargs), indicators)  # type: ignore[arg-type]


async def _resolve_async(indicators: list[str], **kwargs: Any) -> str | None:
    return await _resolve_calendar_type_async(_AsyncStubClient(**kwargs), indicators)  # type: ignore[arg-type]


# (indicators, stub kwargs, expected verdict)
_CASES = [
    # Every indicator trading-day typed → TD.
    (["qte_close", "qte_vol", "finc_pe_ttm"], {}, "TD"),
    # One report-period indicator is enough to stay on the server default: TD would
    # answer is_op_rev with an all-null grid and no error.
    (["qte_close", "is_op_rev"], {}, None),
    # BOTH date keys: a check that merely looked for tradeDate would pick TD.
    (["div_cash_yld"], {}, None),
    (["qte_close", "div_cash_yld"], {}, None),
    # fiscalYear, alone or with tradeDate (frcst_* carry values on every calendar day).
    (["div_cash_yr"], {}, None),
    (["frcst_pe"], {}, None),
    # An empty parameterList is not evidence of anything.
    (["cdr_conv_ratio"], {}, None),
    (["pty_op_scope"], {}, None),
    # A probe that throws — a search outage must not change the axis.
    (["qte_close", "qte_vol"], {"fail": {"qte_vol"}}, None),
    # A code the search cannot resolve (only the decoy comes back).
    (["qte_close"], {"unknown": {"qte_close"}}, None),
    # Nothing to probe.
    ([], {}, None),
]


@pytest.mark.parametrize(("indicators", "kwargs", "expected"), _CASES)
def test_resolve_calendar_type(indicators, kwargs, expected):
    assert _resolve(indicators, **kwargs) == expected


@pytest.mark.anyio
@pytest.mark.parametrize(("indicators", "kwargs", "expected"), _CASES)
async def test_resolve_calendar_type_async(indicators, kwargs, expected):
    assert await _resolve_async(indicators, **kwargs) == expected


def test_each_distinct_code_is_probed_once():
    client = _StubClient()
    _resolve_calendar_type(client, ["qte_close", "qte_close", "qte_vol"])  # type: ignore[arg-type]
    assert sorted(client.calls) == ["qte_close", "qte_vol"]
    empty = _StubClient()
    _resolve_calendar_type(empty, [])  # type: ignore[arg-type]
    assert empty.calls == []


@pytest.mark.anyio
async def test_each_distinct_code_is_probed_once_async():
    client = _AsyncStubClient()
    await _resolve_calendar_type_async(client, ["qte_close", "qte_close", "qte_vol"])  # type: ignore[arg-type]
    assert sorted(client.calls) == ["qte_close", "qte_vol"]


def test_the_probe_sends_the_code_as_keyword_with_the_max_limit():
    seen: list[Any] = []

    class _Capture(_StubClient):
        def _call(self, key: str, body: Any = None) -> Any:
            seen.append(body)
            return super()._call(key, body)

    _resolve_calendar_type(_Capture(), ["qte_close"])  # type: ignore[arg-type]
    assert seen == [{"keyword": "qte_close", "limit": 100}]


def test_probes_run_at_most_five_at_once():
    codes = [f"qte_{i}" for i in range(12)]
    active = 0
    peak = 0
    lock = threading.Lock()

    class _Slow(_StubClient):
        def _call(self, key: str, body: Any = None) -> Any:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return [
                {"indicatorCode": body["keyword"], "parameterList": [{"paramKey": "tradeDate"}]}
            ]

    assert _resolve_calendar_type(_Slow(), codes) == "TD"  # type: ignore[arg-type]
    assert 1 < peak <= 5


@pytest.mark.anyio
async def test_probes_run_at_most_five_at_once_async():
    codes = [f"qte_{i}" for i in range(12)]
    active = 0
    peak = 0

    class _Slow:
        async def _call(self, key: str, body: Any = None) -> Any:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await anyio.sleep(0.01)
            active -= 1
            return [
                {"indicatorCode": body["keyword"], "parameterList": [{"paramKey": "tradeDate"}]}
            ]

    assert await _resolve_calendar_type_async(_Slow(), codes) == "TD"  # type: ignore[arg-type]
    assert 1 < peak <= 5


# ───────────── indicator_param date values (TS v0.44.0 ⑧) ─────────────


def test_date_keyed_params_are_normalized_like_date():
    spec = {
        "is_op_rev": {"reportDate": "2025/12/31", "reportType": "1"},
        "qte_vol_intvl": {"sDate": "20240102"},
        "div_cash_yld": {"tradeDate": "2026-03-31", "reportDate": "2025-12-31"},
        "pty_shr_reg": {"currency": "CNY", "tradeDate": None},
    }
    assert _normalize_param_dates(spec) == {
        "is_op_rev": {"reportDate": "2025-12-31", "reportType": "1"},
        "qte_vol_intvl": {"sDate": "2024-01-02"},
        "div_cash_yld": {"tradeDate": "2026-03-31", "reportDate": "2025-12-31"},
        # A suppression marker is not a value: left alone.
        "pty_shr_reg": {"currency": "CNY", "tradeDate": None},
    }


def test_date_keyed_params_refuse_year_last_and_name_the_param():
    with pytest.raises(ValidationError, match=r"indicator_param\['is_op_rev'\]\['reportDate'\]"):
        _normalize_param_dates({"is_op_rev": {"reportDate": "12-31-2025"}})
    with pytest.raises(ValidationError, match="not a real calendar date"):
        _normalize_param_dates({"qte_close": {"baseDate": "2025-02-30"}})


def test_non_date_params_pass_through_untouched():
    spec = {"qte_close": {"adjustType": "2"}, "finc_roe_avg_avg": {"periodNum": 4}}
    assert _normalize_param_dates(spec) == spec
    assert _normalize_param_dates(None) is None
    assert _normalize_param_dates({}) == {}


class _LiveShapeStubClient(_StubClient):
    """The live search answer is NOT double-wrapped (memory: ede-indicator-no-double-wrap):
    ``_call`` hands back the bare row list. The verdict must not depend on the inner
    envelope the other stubs return."""

    def _call(self, key: str, body: Any = None) -> Any:
        return _StubClient._call(self, key, body)["data"]


@pytest.mark.parametrize(
    ("indicators", "expected"),
    [
        (["qte_close", "qte_vol"], "TD"),
        (["qte_close", "is_op_rev"], None),
        (["cdr_conv_ratio"], None),
    ],
)
def test_verdict_on_the_live_single_envelope_shape(indicators, expected):
    assert _resolve_calendar_type(_LiveShapeStubClient(), indicators) == expected  # type: ignore[arg-type]


class _AsyncLiveShapeStubClient(_LiveShapeStubClient):
    async def _call(self, key: str, body: Any = None) -> Any:  # type: ignore[override]
        return _LiveShapeStubClient._call(self, key, body)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("indicators", "expected"),
    [(["qte_close", "qte_vol"], "TD"), (["qte_close", "is_op_rev"], None)],
)
async def test_async_verdict_on_the_live_single_envelope_shape(indicators, expected):
    client = _AsyncLiveShapeStubClient()
    assert await _resolve_calendar_type_async(client, indicators) == expected  # type: ignore[arg-type]
