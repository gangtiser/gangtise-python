"""Edge bodies (CLI parity: trimmed values, blanks dropped, no empty
lists sent, enum modes checked locally). Sync and async."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import ValidationError
from gangtise_openapi.domains.ai import AI, AsyncAI
from gangtise_openapi.domains.bond import AsyncBond, Bond
from gangtise_openapi.domains.tool import Tool
from gangtise_openapi.domains.vault import AsyncVault, Vault

BASE = "https://api.test"


def _ok(data: object) -> httpx.Response:
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


def _body(route: respx.Route, i: int = 0) -> dict:
    return json.loads(route.calls[i].request.content)


def test_bond_codes_are_trimmed_and_blanks_refused(seeded_config):
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/bond/basic-info").mock(
            return_value=_ok({"fieldList": [], "list": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            Bond(client).basic_info(security=["019742.SH ", " ", "019742.SH"], raw=True)
            with pytest.raises(ValidationError, match="security is required"):
                Bond(client).basic_info(security="  ")
            with pytest.raises(ValidationError):
                Bond(client).issuer_info(issuer="")
    assert route.call_count == 1
    assert _body(route)["securityList"] == ["019742.SH"]


@pytest.mark.anyio
async def test_async_bond_codes_are_trimmed(seeded_config):
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-fundamental/bond/basic-info").mock(
            return_value=_ok({"fieldList": [], "list": []})
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await AsyncBond(client).basic_info(security=[" 019742.SH"], raw=True)
    assert _body(route)["securityList"] == ["019742.SH"]


def test_web_search_drops_blank_sites(seeded_config):
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-tool/web-search/search").mock(
            return_value=_ok({"total": 0, "list": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            Tool(client).web_search(query="x", site=["", " a.com ", "a.com"], raw=True)
    assert _body(route).get("siteList") == ["a.com"]


def test_knowledge_batch_trims_queries_and_refuses_blank(seeded_config):
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-data/ai/search/knowledge/batch").mock(
            return_value=_ok([])
        )
        with GangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="query is required"):
                AI(client).knowledge_batch(query=" ")
            with pytest.raises(ValidationError, match="invalid query: expected text, got 2025"):
                AI(client).knowledge_batch(query=["毛利率", 2025])  # type: ignore[list-item]
            AI(client).knowledge_batch(query=[" 比较毛利率，并解释差异 ", ""], raw=True)  # noqa: RUF001
    assert route.call_count == 1
    assert _body(route)["queries"] == ["比较毛利率，并解释差异"]  # noqa: RUF001


def test_security_clue_refuses_unknown_mode_and_empty_source(seeded_config):
    kwargs = {"start_time": "2026-09-01", "end_time": "2026-09-02", "gts_code": "600519.SH"}
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-ai/security-clue/getList").mock(
            return_value=_ok({"total": 0, "list": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="invalid query_mode"):
                AI(client).security_clue_list(query_mode="bogus", size=1, **kwargs)
            with pytest.raises(ValidationError, match="source is an empty list"):
                AI(client).security_clue_list(
                    query_mode="bySecurity", source=[], size=1, raw=True, **kwargs
                )
    assert route.call_count == 0


@pytest.mark.anyio
async def test_async_security_clue_refuses_unknown_mode(seeded_config):
    async with AsyncGangtiseClient(_config=seeded_config) as client:
        with pytest.raises(ValidationError, match="invalid query_mode"):
            await AsyncAI(client).security_clue_list(
                query_mode="bogus", start_time="2026-09-01", end_time="2026-09-02", size=1
            )


def test_stock_pool_stocks_empty_pool_id_means_all(seeded_config):
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-vault/stock-pool/getStockList").mock(
            return_value=_ok([])
        )
        with GangtiseClient(_config=seeded_config) as client:
            Vault(client).stock_pool_stocks(pool_id=[], raw=True)
            Vault(client).stock_pool_stocks(pool_id=None, raw=True)  # type: ignore[arg-type]
    assert _body(route, 0) == {"poolIdList": ["all"]}
    assert _body(route, 1) == {"poolIdList": ["all"]}


@pytest.mark.anyio
async def test_async_stock_pool_stocks_empty_pool_id_means_all(seeded_config):
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-vault/stock-pool/getStockList").mock(
            return_value=_ok([])
        )
        async with AsyncGangtiseClient(_config=seeded_config) as client:
            await AsyncVault(client).stock_pool_stocks(pool_id=[], raw=True)
    assert _body(route) == {"poolIdList": ["all"]}


def test_independent_opinion_download_refuses_the_paid_title_lookup(seeded_config, tmp_path):
    """Its list bills per row: the 200-row filename lookup would cost 200 credits for a
    filename. Refused before anything is sent (the CLI never offers it)."""
    from gangtise_openapi.domains.insight import Insight

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        listing = router.post("/application/open-insight/independent-opinion/getList")
        download = router.get("/application/open-insight/independent-opinion/download/file")
        with GangtiseClient(_config=seeded_config) as client, pytest.raises(ValidationError):
            Insight(client).independent_opinion_download(
                independent_opinion_id="1", file_type=1, resolve_title=True
            )
    assert listing.call_count == 0
    assert download.call_count == 0


def test_bond_issuer_selector_refuses_an_explicit_empty_list(seeded_config):
    """security=[] beside an issuer must not be silently dropped."""
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/bond/issuer-info")
        with GangtiseClient(_config=seeded_config) as client:
            with pytest.raises(ValidationError, match="security is an empty list"):
                Bond(client).issuer_info(security=[], issuer="国家开发银行")
            with pytest.raises(ValidationError, match="issuer is an empty list"):
                Bond(client).issuer_rating_change(security="019742.SH", issuer=[" "])
    assert route.call_count == 0


def test_list_arguments_take_any_sequence_but_not_sets_or_iterators(seeded_config):
    """One rule for every domain: any sequence (UserList, a pandas Series via tolist)
    is a list of values; a set (no order) or a one-shot iterator is refused by name."""
    from collections import UserList

    import pandas as pd

    from gangtise_openapi.domains.fund import Fund
    from gangtise_openapi.domains.quote import Quote

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-quote/quote/realtime").mock(
            return_value=_ok({"total": 0, "list": [], "fieldList": []})
        )
        fund_route = router.post("/application/open-quote/fund/nav").mock(return_value=_ok([]))
        with GangtiseClient(_config=seeded_config) as client:
            Quote(client).realtime(security=UserList(["600519.SH"]), raw=True)
            Quote(client).realtime(security=pd.Series(["000001.SZ", "000001.SZ"]), raw=True)
            codes = {"600519.SH": 1}
            unordered = ({"600519.SH"}, codes, codes.keys(), codes.values(), iter(["600519.SH"]))
            for bad in unordered:
                with pytest.raises(ValidationError, match="security: pass a list"):
                    Quote(client).realtime(security=bad)
                with pytest.raises(ValidationError, match="security: pass a list"):
                    Fund(client).nav(security=bad)
            for bad in (b"600519.SH", [b"600519.SH"]):
                with pytest.raises(ValidationError, match=r"security: pass text \(str\)"):
                    Quote(client).realtime(security=bad)
            with pytest.raises(ValidationError, match="expected strings"):
                Fund(client).nav(security=510300)  # type: ignore[arg-type]
    assert _body(route, 0)["securityList"] == ["600519.SH"]
    assert _body(route, 1)["securityList"] == ["000001.SZ"]
    assert fund_route.call_count == 0


def test_valuation_indicator_is_checked_locally(seeded_config):
    from gangtise_openapi.domains.fundamental import Fundamental

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/valuation-analysis")
        with (
            GangtiseClient(_config=seeded_config) as client,
            pytest.raises(ValidationError, match="invalid indicator"),
        ):
            Fundamental(client).valuation_analysis(security_code="600519.SH", indicator="PE")
    assert route.call_count == 0


def test_indicator_refuses_dict_views_instead_of_sending_their_repr(seeded_config):
    # The EDE matrix wrappers str() every code; a dict view must be refused before that,
    # or it goes out as the text "dict_keys([...])" and comes back as an unknown indicator.
    from gangtise_openapi.domains.indicator import Indicator

    params = {"qte_close": {}}
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-indicator/EDE/cross-section")
        with GangtiseClient(_config=seeded_config) as client:
            for bad in (params.keys(), params.values()):
                with pytest.raises(ValidationError, match="indicator: pass a list"):
                    Indicator(client).cross_section(
                        date="2025-12-31", indicator=bad, security="600519.SH"
                    )
    assert route.call_count == 0


def test_numpy_scalars_in_a_list_go_out_as_plain_json(seeded_config):
    import numpy as np

    from gangtise_openapi.domains.fundamental import Fundamental

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/capital-structure/top-holders").mock(
            return_value=_ok({"total": 0, "list": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            Fundamental(client).top_holders(
                security_code="600519.SH",
                holder_type="top10",
                fiscal_year=[np.int64(2024), np.int64(2024), 2025],
                raw=True,
            )
    assert _body(route, 0)["fiscalYear"] == [2024, 2025]


def test_wechat_chatroom_room_names_are_joined_as_text(seeded_config):
    from gangtise_openapi.domains.vault import Vault

    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/wechatgroupmsg/chatroomId").mock(
            return_value=_ok({"total": 0, "list": []})
        )
        with GangtiseClient(_config=seeded_config) as client:
            Vault(client).wechat_chatroom_list(room_name=[2025, "投研群"], raw=True)
    assert _body(route)["roomName"] == "2025,投研群"
