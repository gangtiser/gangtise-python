"""Endpoint tests for `gangtise.fund` (TS v0.44.0 `fund` command group).

Bodies mirror `tests/unit/cliBodyMapping.test.ts` (the fund cases) in the TS repo.
"""

from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import GangtiseError, ValidationError
from gangtise_openapi.domains.fund import Fund

_FUNDAMENTAL = "/application/open-fundamental/fund/"
_NAV = "/application/open-quote/fund/nav"

# Every method that takes `security` (all but manager_info), with its path.
_BY_CODE = [
    ("basic_info", _FUNDAMENTAL + "basic-info"),
    ("nav", _NAV),
    ("fee_rate", _FUNDAMENTAL + "fee-rate"),
    ("manager_history", _FUNDAMENTAL + "manager-history"),
    ("asset_size", _FUNDAMENTAL + "asset-size"),
    ("holder_structure", _FUNDAMENTAL + "holder-structure"),
    ("top10_holders", _FUNDAMENTAL + "top10-holders"),
    ("asset_allocation", _FUNDAMENTAL + "asset-allocation"),
    ("stock_portfolio", _FUNDAMENTAL + "stock-portfolio"),
    ("industry_allocation", _FUNDAMENTAL + "industry-allocation"),
    ("bond_portfolio", _FUNDAMENTAL + "bond-portfolio"),
    ("bond_type_allocation", _FUNDAMENTAL + "bond-type-allocation"),
    ("fund_portfolio", _FUNDAMENTAL + "fund-portfolio"),
    ("fund_type_allocation", _FUNDAMENTAL + "fund-type-allocation"),
    ("etf_pcf_header", _FUNDAMENTAL + "etf-pcf-header"),
    ("etf_pcf_components", _FUNDAMENTAL + "etf-pcf-components"),
    ("etf_share_change", _FUNDAMENTAL + "etf-share-change"),
]


def _ok(rows: list[dict]) -> httpx.Response:
    # The fund endpoints answer `{list}` with no `total` and no `fieldList`.
    return httpx.Response(200, json={"code": "000000", "status": True, "data": {"list": rows}})


def _body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.read())


@pytest.mark.parametrize(("method", "path"), _BY_CODE)
def test_security_goes_out_as_fund_code_list_and_nothing_else(seeded_config, method, path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(path).mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            getattr(Fund(client), method)(security=["005827.OF", "159967.SZ", "005827.OF"])
    assert route.call_count == 1
    assert _body(route) == {"fundCodeList": ["005827.OF", "159967.SZ"]}


def test_manager_info_sends_manager_name_list(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_FUNDAMENTAL + "manager-info").mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            Fund(client).manager_info(manager=["张坤", "葛兰"])
    assert _body(route) == {"managerNameList": ["张坤", "葛兰"]}


def test_manager_names_are_sent_whole_and_deduped(seeded_config):
    # A name may hold a space or an ideographic comma: a string is one value, sent as
    # typed (trimmed). Repeats are dropped, first kept.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_FUNDAMENTAL + "manager-info").mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            Fund(client).manager_info(manager=["Morgan Stanley", "研究所、策略群", " 张坤", "张坤"])
    assert _body(route) == {"managerNameList": ["Morgan Stanley", "研究所、策略群", "张坤"]}


def test_a_code_string_is_one_value_not_split(seeded_config):
    """The SDK convention (quote, bond, …): a string is ONE value. The CLI splits
    because its flags are text; a Python caller passes a list."""
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_NAV).mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            Fund(client).nav(security=["005827.OF", " 159967.SZ ", "005827.OF"])
            Fund(client).nav(security="005827.OF,159967.SZ")
    assert json.loads(route.calls[0].request.content) == {
        "fundCodeList": ["005827.OF", "159967.SZ"]
    }
    assert json.loads(route.calls[1].request.content) == {"fundCodeList": ["005827.OF,159967.SZ"]}


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (
            lambda f: f.basic_info(security="005827.OF", field=["fundName", "setupDate"]),
            {"fundCodeList": ["005827.OF"], "fieldList": ["fundName", "setupDate"]},
        ),
        (
            lambda f: f.nav(security="159967.SZ", start_date="2026/08/25", end_date="20260827"),
            {"fundCodeList": ["159967.SZ"], "startDate": "2026-08-25", "endDate": "2026-08-27"},
        ),
        (
            lambda f: f.fee_rate(security="003096.OF", fee_type=["managementFee", "custodianFee"]),
            {"fundCodeList": ["003096.OF"], "feeTypeList": ["managementFee", "custodianFee"]},
        ),
        (
            lambda f: f.asset_allocation(
                security="005827.OF",
                start_date="2026-06-30",
                end_date="2026-06-30",
                asset_level="level1",
            ),
            {
                "fundCodeList": ["005827.OF"],
                "startDate": "2026-06-30",
                "endDate": "2026-06-30",
                "assetLevelList": ["level1"],
            },
        ),
        (
            lambda f: f.stock_portfolio(security="005827.OF", position_type="all"),
            {"fundCodeList": ["005827.OF"], "positionType": "all"},
        ),
        (
            lambda f: f.industry_allocation(
                security="005827.OF", industry_standard="citicIndustry", position_type="all"
            ),
            {
                "fundCodeList": ["005827.OF"],
                "industryStandard": "citicIndustry",
                "positionType": "all",
            },
        ),
        (
            lambda f: f.etf_share_change(
                security="510300.SH", start_date="2026-09-17", end_date="2026-09-18"
            ),
            {"fundCodeList": ["510300.SH"], "startDate": "2026-09-17", "endDate": "2026-09-18"},
        ),
        # One end only: the other stays out of the body (the server takes it as open).
        (
            lambda f: f.nav(security="159967.SZ", start_date="2026-09-01"),
            {"fundCodeList": ["159967.SZ"], "startDate": "2026-09-01"},
        ),
        (
            lambda f: f.stock_portfolio(security="005827.OF", end_date="2024-06-30"),
            {"fundCodeList": ["005827.OF"], "endDate": "2024-06-30"},
        ),
        # Every dated method carries both ends.
        *[
            (
                lambda f, m=m: getattr(f, m)(
                    security="005827.OF", start_date="2026-03-31", end_date="2026-06-30"
                ),
                {"fundCodeList": ["005827.OF"], "startDate": "2026-03-31", "endDate": "2026-06-30"},
            )
            for m in (
                "asset_size",
                "holder_structure",
                "top10_holders",
                "bond_portfolio",
                "bond_type_allocation",
                "fund_portfolio",
                "fund_type_allocation",
            )
        ],
        # Repeated values in the optional lists are dropped; an empty one is left out.
        (
            lambda f: f.basic_info(security="005827.OF", field=["fundName", "fundName"]),
            {"fundCodeList": ["005827.OF"], "fieldList": ["fundName"]},
        ),
    ],
)
def test_options_map_to_the_documented_body_fields(seeded_config, call, expected):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.route(method="POST").mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            call(Fund(client))
    assert _body(route) == expected


def test_enum_values_are_left_to_the_server(seeded_config):
    # Like the CLI: an unknown value is answered with 100003 before billing, so no
    # local list that could go stale.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_FUNDAMENTAL + "industry-allocation").mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            Fund(client).industry_allocation(
                security="005827.OF", industry_standard="bogus", position_type="bogus"
            )
    assert _body(route) == {
        "fundCodeList": ["005827.OF"],
        "industryStandard": "bogus",
        "positionType": "bogus",
    }


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda f: f.nav(security=""), "security is empty"),
        (lambda f: f.nav(security=[]), "security is empty"),
        (lambda f: f.stock_portfolio(security="   "), "security is empty"),
        (lambda f: f.etf_pcf_header(security=[""]), "security is empty"),
        (lambda f: f.manager_info(manager=" "), "manager is empty"),
        (lambda f: f.manager_info(manager=[]), "manager is empty"),
        (lambda f: f.fee_rate(security="003096.OF", fee_type=[]), "fee_type is an empty list"),
        (lambda f: f.nav(security=[5827]), "invalid security"),
        (lambda f: f.nav(security="159967.SZ", start_date="01-09-2026"), "start_date"),
        (lambda f: f.asset_size(security="005827.OF", end_date="2026-02-30"), "end_date"),
    ],
)
def test_local_refusals_send_nothing(seeded_config, call, match):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.route().mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match=match):
                call(Fund(client))
    assert not route.called


def test_rows_become_a_dataframe(seeded_config):
    rows = [
        {"fundCode": "005827.OF", "reportDate": "2026-06-30", "holderCount": "2,219,140"},
        {"fundCode": "510300.SH", "reportDate": "2026-06-30", "holderCount": "1,000"},
    ]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_FUNDAMENTAL + "holder-structure").mock(return_value=_ok(rows))
        with GangtiseClient(_config=seeded_config) as client:
            df = Fund(client).holder_structure(security=["005827.OF", "510300.SH"])
    assert isinstance(df, pd.DataFrame)
    assert list(df["fundCode"]) == ["005827.OF", "510300.SH"]
    # Passed through untouched: the thousands-separated string is the server's shape.
    assert df.iloc[0]["holderCount"] == "2,219,140"


def test_empty_result_is_an_empty_dataframe(seeded_config):
    # An unknown / suffix-less / lowercase code answers `{list: []}` with no error.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_FUNDAMENTAL + "basic-info").mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            df = Fund(client).basic_info(security="005827")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_raw_returns_the_data_payload(seeded_config):
    rows = [{"managerName": "张坤", "currentCompany": None, "managedFundScale": 1.5}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_FUNDAMENTAL + "manager-info").mock(return_value=_ok(rows))
        with GangtiseClient(_config=seeded_config) as client:
            out = Fund(client).manager_info(manager="张坤", raw=True)
    assert out == {"list": rows}


def test_a_5xx_is_not_replayed(seeded_config):
    # Billed per call and marked no-replay: the server may already have run it.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_NAV).mock(return_value=httpx.Response(502))
        with GangtiseClient(_config=seeded_config) as client:  # noqa: SIM117
            with pytest.raises(GangtiseError):
                Fund(client).nav(security="005827.OF")
    assert route.call_count == 1


def test_any_sequence_of_codes_is_accepted(seeded_config):
    """The signature says Sequence[str]; a UserList must work."""
    from collections import UserList

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_NAV).mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            Fund(client).nav(security=UserList(["510300.SH", "510300.SH"]))
    assert _body(route) == {"fundCodeList": ["510300.SH"]}
