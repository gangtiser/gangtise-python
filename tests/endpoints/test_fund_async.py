"""Async mirror of `test_fund.py`."""

from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._errors import GangtiseError, ValidationError
from gangtise_openapi.domains.fund import AsyncFund

_FUNDAMENTAL = "/application/open-fundamental/fund/"
_NAV = "/application/open-quote/fund/nav"

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
    return httpx.Response(200, json={"code": "000000", "status": True, "data": {"list": rows}})


def _body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.read())


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path"), _BY_CODE)
async def test_async_security_goes_out_as_fund_code_list(seeded_config, method, path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(path).mock(return_value=_ok([]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await getattr(AsyncFund(client), method)(
                security=["005827.OF", "159967.SZ", "005827.OF"]
            )
    assert route.call_count == 1
    assert _body(route) == {"fundCodeList": ["005827.OF", "159967.SZ"]}


@pytest.mark.anyio
async def test_async_manager_info_sends_names_whole_and_deduped(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_FUNDAMENTAL + "manager-info").mock(return_value=_ok([]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await AsyncFund(client).manager_info(manager=["Morgan Stanley", "张坤", "张坤", "葛兰"])
    assert _body(route) == {"managerNameList": ["Morgan Stanley", "张坤", "葛兰"]}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "kwargs", "expected"),
    [
        (
            "basic_info",
            {"security": "005827.OF", "field": ["fundName", "setupDate", "fundName"]},
            {"fundCodeList": ["005827.OF"], "fieldList": ["fundName", "setupDate"]},
        ),
        (
            "nav",
            {"security": "159967.SZ", "start_date": "2026/08/25", "end_date": "20260827"},
            {"fundCodeList": ["159967.SZ"], "startDate": "2026-08-25", "endDate": "2026-08-27"},
        ),
        (
            "fee_rate",
            {"security": "003096.OF", "fee_type": ["managementFee", "custodianFee"]},
            {"fundCodeList": ["003096.OF"], "feeTypeList": ["managementFee", "custodianFee"]},
        ),
        (
            "asset_allocation",
            {
                "security": "005827.OF",
                "start_date": "2026-06-30",
                "end_date": "2026-06-30",
                "asset_level": "level1",
            },
            {
                "fundCodeList": ["005827.OF"],
                "startDate": "2026-06-30",
                "endDate": "2026-06-30",
                "assetLevelList": ["level1"],
            },
        ),
        (
            "stock_portfolio",
            {"security": "005827.OF", "position_type": "all"},
            {"fundCodeList": ["005827.OF"], "positionType": "all"},
        ),
        (
            "industry_allocation",
            {
                "security": "005827.OF",
                "industry_standard": "citicIndustry",
                "position_type": "all",
            },
            {
                "fundCodeList": ["005827.OF"],
                "industryStandard": "citicIndustry",
                "positionType": "all",
            },
        ),
        (
            "etf_share_change",
            {"security": "510300.SH", "start_date": "2026-09-17", "end_date": "2026-09-18"},
            {"fundCodeList": ["510300.SH"], "startDate": "2026-09-17", "endDate": "2026-09-18"},
        ),
        *[
            (
                m,
                {"security": "005827.OF", "start_date": "2026-03-31", "end_date": "2026-06-30"},
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
    ],
)
async def test_async_options_map_to_the_documented_body_fields(
    seeded_config, method, kwargs, expected
):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.route(method="POST").mock(return_value=_ok([]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await getattr(AsyncFund(client), method)(**kwargs)
    assert _body(route) == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "kwargs", "match"),
    [
        ("nav", {"security": ""}, "security is empty"),
        ("etf_pcf_components", {"security": [" ", ""]}, "security is empty"),
        ("manager_info", {"manager": " "}, "manager is empty"),
        ("nav", {"security": "159967.SZ", "start_date": "01-09-2026"}, "start_date"),
    ],
)
async def test_async_local_refusals_send_nothing(seeded_config, method, kwargs, match):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.route().mock(return_value=_ok([]))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match=match):
                await getattr(AsyncFund(client), method)(**kwargs)
    assert not route.called


@pytest.mark.anyio
async def test_async_rows_become_a_dataframe(seeded_config):
    rows = [
        {"fundCode": "510300.SH", "serialNumber": 1, "holderName": "A"},
        {"fundCode": "510300.SH", "serialNumber": 11, "holderName": "联接基金"},
    ]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_FUNDAMENTAL + "top10-holders").mock(return_value=_ok(rows))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            df = await AsyncFund(client).top10_holders(security="510300.SH")
    assert isinstance(df, pd.DataFrame)
    assert list(df["serialNumber"]) == [1, 11]


@pytest.mark.anyio
async def test_async_raw_returns_the_data_payload(seeded_config):
    rows = [{"fundCode": "510300.SH", "tradeDate": "2026-09-30", "componentCount": 300}]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(_FUNDAMENTAL + "etf-pcf-header").mock(return_value=_ok(rows))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            out = await AsyncFund(client).etf_pcf_header(security="510300.SH", raw=True)
    assert out == {"list": rows}


@pytest.mark.anyio
async def test_async_a_5xx_is_not_replayed(seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post(_NAV).mock(return_value=httpx.Response(502))
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            with pytest.raises(GangtiseError):
                await AsyncFund(client).nav(security="005827.OF")
    assert route.call_count == 1
