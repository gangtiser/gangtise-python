"""Async mirror of test_bond.py — `gangtise.async_.bond`."""

from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.bond import AsyncBond

_BASE = "/application/open-fundamental/bond/"
_COLUMNAR = {
    "fieldList": ["securityCode", "securityName"],
    "list": [["019742.SH", "24国债11"], ["220205.IB", "22国开05"]],
    "total": 2,
}


def _ok(data):
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


# (method, kwargs, path, exact wire body) — every body literal of TS src/commands/bond.ts.
CASES = [
    (
        "basic_info",
        {
            "security": ["019742.SH", "019742.SH", "220205.IB"],
            "field": ["securityName", "couponRate", "securityName"],
        },
        _BASE + "basic-info",
        {"securityList": ["019742.SH", "220205.IB"], "fieldList": ["securityName", "couponRate"]},
    ),
    (
        "issuer_info",
        {"issuer": ["国家电网有限公司", "国家电网有限公司"], "field": "issuerName"},
        _BASE + "issuer-info",
        {"issuerNameList": ["国家电网有限公司"], "fieldList": ["issuerName"]},
    ),
    (
        "daily_quote",
        {"security": "019742.SH", "start_date": "2026/09/15", "end_date": "20260919"},
        "/application/open-quote/bond/daily-quote-exchange-cfets",
        {"securityList": ["019742.SH"], "startDate": "2026-09-15", "endDate": "2026-09-19"},
    ),
    (
        "valuation",
        {
            "security": "019742.SH",
            "start_date": "2026-09-15",
            "end_date": "2026-09-19",
            "confidence_level": "推荐",
        },
        _BASE + "valuation-shclearing",
        {
            "securityList": ["019742.SH"],
            "startDate": "2026-09-15",
            "endDate": "2026-09-19",
            "confidenceLevel": "推荐",
        },
    ),
    (
        "cash_flow",
        {"security": "019742.SH", "start_date": "2026-01-01"},
        _BASE + "cash-flow",
        {"securityList": ["019742.SH"], "startDate": "2026-01-01"},
    ),
    (
        "announcement",
        {"start_date": "2026-09-18", "end_date": "2026-09-19", "page_no": 2, "page_size": 200},
        _BASE + "announcement",
        {"startDate": "2026-09-18", "endDate": "2026-09-19", "pageNo": 2, "pageSize": 200},
    ),
    (
        "issuance_detail",
        {"security": "019742.SH"},
        _BASE + "issuance-detail",
        {"securityList": ["019742.SH"]},
    ),
    (
        "rating_overview",
        {"security": ["136236.SH"] * 11},
        _BASE + "rating-overview",
        {"securityList": ["136236.SH"]},
    ),
    (
        "rating_change",
        {"security": ["149478.SZ"] * 11},
        _BASE + "rating-change",
        {"securityList": ["149478.SZ"]},
    ),
    (
        "issuer_rating_change",
        {"security": "136236.SH", "end_date": "2026-09-20"},
        _BASE + "issuer-rating-change",
        {"securityList": ["136236.SH"], "endDate": "2026-09-20"},
    ),
    (
        "issuance_plan",
        {"start_date": "2026-09-01", "end_date": "2026-09-30"},
        _BASE + "issuance-plan",
        {"startDate": "2026-09-01", "endDate": "2026-09-30"},
    ),
    (
        "exercise_notice",
        {"security": "136236.SH", "field": ["exerciseDate"]},
        _BASE + "exercise-notice",
        {"securityList": ["136236.SH"], "fieldList": ["exerciseDate"]},
    ),
]

_ELEVEN = [f"{100000 + i}.SH" for i in range(11)]

REFUSALS = [
    ("issuer_info", {"security": "136236.SH", "issuer": "国家电网"}, "mutually exclusive"),
    ("issuer_rating_change", {}, "pass either security"),
    (
        "announcement",
        {"security": "019742.SH", "start_date": "2026-09-01"},
        "mutually exclusive",
    ),
    ("announcement", {}, "pass either security"),
    ("announcement", {"security": "019742.SH", "page_size": 201}, "page_size"),
    ("cash_flow", {"security": []}, "security is required"),
    ("rating_overview", {"security": _ELEVEN}, "11 distinct bond codes"),
    ("rating_change", {"security": _ELEVEN}, "at most 10"),
    (
        "valuation",
        {
            "security": "019742.SH",
            "start_date": "2026-09-15",
            "end_date": "2026-09-19",
            "confidence_level": "全部",
        },
        "confidence_level",
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "kwargs", "path", "expected"), CASES)
async def test_async_body_mapping(seeded_config, method, kwargs, path, expected):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(path).mock(return_value=_ok(_COLUMNAR))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            df = await getattr(AsyncBond(client), method)(**kwargs)
    assert json.loads(route.calls.last.request.content) == expected
    assert isinstance(df, pd.DataFrame)


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "kwargs", "match"), REFUSALS)
async def test_async_local_refusals_send_nothing(seeded_config, method, kwargs, match):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        catch_all = router.route().mock(return_value=_ok(_COLUMNAR))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match=match):
                await getattr(AsyncBond(client), method)(**kwargs)
    assert not catch_all.called


@pytest.mark.anyio
async def test_async_columnar_payload_becomes_a_dataframe(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_BASE + "rating-overview").mock(return_value=_ok(_COLUMNAR))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            df = await AsyncBond(client).rating_overview(security=["019742.SH", "220205.IB"])
    assert list(df.columns) == ["securityCode", "securityName"]
    assert df["securityCode"].tolist() == ["019742.SH", "220205.IB"]


@pytest.mark.anyio
async def test_async_raw_returns_the_columnar_data_untouched(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_BASE + "cash-flow").mock(return_value=_ok(_COLUMNAR))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            data = await AsyncBond(client).cash_flow(security="019742.SH", raw=True)
    assert data == _COLUMNAR


@pytest.mark.anyio
async def test_async_announcement_past_the_last_page_is_an_empty_frame(seeded_config):
    empty = {"fieldList": ["announcementDate", "securityCode"], "list": []}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_BASE + "announcement").mock(return_value=_ok(empty))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            df = await AsyncBond(client).announcement(security="019742.SH", page_no=3)
    assert df.empty
    assert route.call_count == 1


@pytest.mark.anyio
async def test_async_a_5xx_is_not_replayed(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_BASE + "basic-info").mock(return_value=httpx.Response(502))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ApiError):
                await AsyncBond(client).basic_info(security="019742.SH")
    assert route.call_count == 1
