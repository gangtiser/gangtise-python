"""`gangtise.bond` — body mapping, local refusals, columnar -> DataFrame (TS v0.41.0 ④)."""

from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi.domains.bond import Bond

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
        "basic_info",
        {"security": "019742.SH"},
        _BASE + "basic-info",
        {"securityList": ["019742.SH"]},
    ),
    (
        "issuer_info",
        {"security": "136236.SH"},
        _BASE + "issuer-info",
        {"securityList": ["136236.SH"]},
    ),
    (
        "issuer_info",
        {"issuer": ["国家电网有限公司", "国家电网有限公司"], "field": "issuerName"},
        _BASE + "issuer-info",
        {"issuerNameList": ["国家电网有限公司"], "fieldList": ["issuerName"]},
    ),
    (
        "daily_quote",
        {
            "security": "019742.SH",
            "start_date": "2026/09/15",
            "end_date": "20260919",
            "field": ["cleanClose", "ytmClose"],
        },
        "/application/open-quote/bond/daily-quote-exchange-cfets",
        {
            "securityList": ["019742.SH"],
            "startDate": "2026-09-15",
            "endDate": "2026-09-19",
            "fieldList": ["cleanClose", "ytmClose"],
        },
    ),
    (
        "valuation",
        {"security": "019742.SH", "start_date": "2026-09-15", "end_date": "2026-09-19"},
        _BASE + "valuation-shclearing",
        {"securityList": ["019742.SH"], "startDate": "2026-09-15", "endDate": "2026-09-19"},
    ),
    (
        "valuation",
        {
            "security": "019742.SH",
            "start_date": "2026-09-15",
            "end_date": "2026-09-19",
            "confidence_level": "不推荐",
        },
        _BASE + "valuation-shclearing",
        {
            "securityList": ["019742.SH"],
            "startDate": "2026-09-15",
            "endDate": "2026-09-19",
            "confidenceLevel": "不推荐",
        },
    ),
    ("cash_flow", {"security": "019742.SH"}, _BASE + "cash-flow", {"securityList": ["019742.SH"]}),
    (
        "announcement",
        {"security": "019742.SH"},
        _BASE + "announcement",
        {"securityList": ["019742.SH"], "pageNo": 1, "pageSize": 50},
    ),
    (
        "announcement",
        {"start_date": "2026-09-18", "end_date": "2026-09-19", "page_no": 2, "page_size": 200},
        _BASE + "announcement",
        {"startDate": "2026-09-18", "endDate": "2026-09-19", "pageNo": 2, "pageSize": 200},
    ),
    (
        "issuance_detail",
        {"security": "019742.SH", "start_date": "2024-01-01", "end_date": "2024-12-31"},
        _BASE + "issuance-detail",
        {"securityList": ["019742.SH"], "startDate": "2024-01-01", "endDate": "2024-12-31"},
    ),
    # TS cliBodyMapping: 11 copies of one code clear the 10-bond cap, since the
    # server counts it after de-duplication — and the de-duplicated list is sent.
    (
        "rating_overview",
        {"security": ["136236.SH"] * 11},
        _BASE + "rating-overview",
        {"securityList": ["136236.SH"]},
    ),
    (
        "rating_change",
        {"security": ["149478.SZ"] * 11, "start_date": "2023-01-01", "end_date": "2026-09-20"},
        _BASE + "rating-change",
        {"securityList": ["149478.SZ"], "startDate": "2023-01-01", "endDate": "2026-09-20"},
    ),
    (
        "issuer_rating_change",
        {"issuer": "国家电网有限公司", "start_date": "2026-01-01", "end_date": "2026-09-20"},
        _BASE + "issuer-rating-change",
        {
            "issuerNameList": ["国家电网有限公司"],
            "startDate": "2026-01-01",
            "endDate": "2026-09-20",
        },
    ),
    (
        "issuer_rating_change",
        {"security": ["136236.SH", "136236.SH"]},
        _BASE + "issuer-rating-change",
        {"securityList": ["136236.SH"]},
    ),
    (
        "issuance_plan",
        {"start_date": "2026-09-01", "end_date": "2026-09-30", "field": "issueDate"},
        _BASE + "issuance-plan",
        {"startDate": "2026-09-01", "endDate": "2026-09-30", "fieldList": ["issueDate"]},
    ),
    (
        "exercise_notice",
        {"security": "136236.SH"},
        _BASE + "exercise-notice",
        {"securityList": ["136236.SH"]},
    ),
]

_TEN = [f"{100000 + i}.SH" for i in range(10)]

# (method, kwargs, message fragment) — all refused before any (metered) request.
REFUSALS = [
    ("issuer_info", {"security": "136236.SH", "issuer": "国家电网"}, "mutually exclusive"),
    ("issuer_info", {}, "pass either security"),
    ("issuer_rating_change", {}, "pass either security"),
    (
        "issuer_rating_change",
        {"security": "136236.SH", "issuer": "国家电网"},
        "mutually exclusive",
    ),
    (
        "announcement",
        {"security": "019742.SH", "start_date": "2026-09-01"},
        "mutually exclusive",
    ),
    ("announcement", {"security": "019742.SH", "end_date": "2026-09-01"}, "mutually exclusive"),
    ("announcement", {}, "pass either security"),
    ("announcement", {"security": "019742.SH", "page_size": 201}, "page_size"),
    ("announcement", {"security": "019742.SH", "page_size": 0}, "page_size"),
    ("announcement", {"security": "019742.SH", "page_no": 0}, "page_no"),
    ("announcement", {"security": "019742.SH", "page_no": True}, "page_no"),
    ("cash_flow", {"security": []}, "security is required"),
    ("basic_info", {"security": []}, "security is required"),
    ("rating_overview", {"security": [*_TEN, "999999.SH"]}, "11 distinct bond codes"),
    ("rating_change", {"security": [*_TEN, "999999.SH"]}, "at most 10"),
    ("basic_info", {"security": [str(i) for i in range(10001)]}, "at most 10000"),
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
    (
        "daily_quote",
        {"security": "019742.SH", "start_date": "09/15/2026", "end_date": "2026-09-19"},
        "start_date",
    ),
]


@pytest.mark.parametrize(("method", "kwargs", "path", "expected"), CASES)
def test_body_mapping(seeded_config, method, kwargs, path, expected):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(path).mock(return_value=_ok(_COLUMNAR))
        with GangtiseClient(_config=seeded_config) as client:
            df = getattr(Bond(client), method)(**kwargs)
    assert json.loads(route.calls.last.request.content) == expected
    assert isinstance(df, pd.DataFrame)


def test_ten_distinct_codes_are_accepted(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_BASE + "rating-overview").mock(return_value=_ok(_COLUMNAR))
        with GangtiseClient(_config=seeded_config) as client:
            Bond(client).rating_overview(security=_TEN)
    assert json.loads(route.calls.last.request.content) == {"securityList": _TEN}


@pytest.mark.parametrize(("method", "kwargs", "match"), REFUSALS)
def test_local_refusals_send_nothing(seeded_config, method, kwargs, match):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        catch_all = router.route().mock(return_value=_ok(_COLUMNAR))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match=match):
                getattr(Bond(client), method)(**kwargs)
    assert not catch_all.called


def test_columnar_payload_becomes_a_dataframe(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_BASE + "rating-overview").mock(return_value=_ok(_COLUMNAR))
        with GangtiseClient(_config=seeded_config) as client:
            df = Bond(client).rating_overview(security=["019742.SH", "220205.IB"])
    assert list(df.columns) == ["securityCode", "securityName"]
    assert df["securityCode"].tolist() == ["019742.SH", "220205.IB"]
    assert df.iloc[1]["securityName"] == "22国开05"


def test_raw_returns_the_columnar_data_untouched(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_BASE + "cash-flow").mock(return_value=_ok(_COLUMNAR))
        with GangtiseClient(_config=seeded_config) as client:
            data = Bond(client).cash_flow(security="019742.SH", raw=True)
    assert data == _COLUMNAR


def test_announcement_past_the_last_page_is_an_empty_frame(seeded_config):
    # No `total` on this endpoint: an empty page is the stop signal.
    empty = {"fieldList": ["announcementDate", "securityCode"], "list": []}
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_BASE + "announcement").mock(return_value=_ok(empty))
        with GangtiseClient(_config=seeded_config) as client:
            df = Bond(client).announcement(security="019742.SH", page_no=3)
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert route.call_count == 1  # one page asked, one page sent: never auto-paginated


def test_announcement_with_no_match_raises_130001(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_BASE + "announcement").mock(
            return_value=httpx.Response(
                404, json={"code": "130001", "msg": "数据未找到", "status": False}
            )
        )
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError) as excinfo:
                Bond(client).announcement(start_date="2026-09-18", end_date="2026-09-19")
    assert excinfo.value.code == "130001"


def test_a_5xx_is_not_replayed(seeded_config):
    # Metered family, marked no-replay: the server may already have billed the call.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_BASE + "basic-info").mock(return_value=httpx.Response(502))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ApiError):
                Bond(client).basic_info(security="019742.SH")
    assert route.call_count == 1
