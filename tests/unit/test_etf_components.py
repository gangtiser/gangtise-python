"""ETF component codes matched by name (TS v0.49.0 ``core/etfComponents.ts``).

Names, codes and prices are taken from the CLI's live answers of 2026-10-27 (14 ETFs);
the cases mirror ``tests/unit/etfComponents.test.ts`` in the TS repo.
"""

from __future__ import annotations

from typing import Any

import pytest

from gangtise_openapi._errors import ApiError
from gangtise_openapi._etf_components import (
    AsyncCodeLookup,
    CodeLookup,
    _Fill,
    _TableSearch,
    fill_component_codes,
    fill_component_codes_async,
)

Listing = tuple  # (code, name) or (code, name, category)


class _Api:
    """A fake lookup: search hits per keyword, quote prices per code, daily closes."""

    def __init__(
        self,
        search: dict[str, list[Listing]],
        prices: dict[str, list[float]],
        *,
        fail_search: str | None = None,
        fail_quote: str | None = None,
        history: dict[str, list[tuple]] | None = None,
    ) -> None:
        self._search = search
        self._prices = prices
        self._fail_search = fail_search
        self._fail_quote = fail_quote
        self._history = history or {}
        self.searched: list[str] = []
        self.quoted: list[list[str]] = []
        self.asked: list[list[str]] = []

    def search(self, keyword: str) -> list[dict[str, Any]]:
        self.searched.append(keyword)
        if keyword == self._fail_search:
            raise RuntimeError("search failed")
        return [
            {"gtsCode": hit[0], "gtsName": hit[1], "category": hit[2] if len(hit) > 2 else "stock"}
            for hit in self._search.get(keyword, [])
        ]

    def quotes(self, codes: list[str]) -> dict[str, list[float]]:
        self.quoted.append(codes)
        # The quote answers 120001 for the whole batch when one code is unknown.
        if self._fail_quote and self._fail_quote in codes:
            raise ApiError("证券代码无效", code="120001")
        return {c: self._prices[c] for c in codes if c in self._prices}

    def closes(self, codes: list[str], start: str, end: str) -> dict[str, Any]:
        self.asked.append(codes)
        return {c: self._history[c] for c in codes if c in self._history}


class _AsyncApi:
    """The same fake behind async methods."""

    def __init__(self, api: _Api) -> None:
        self.api = api

    async def search(self, keyword: str) -> list[dict[str, Any]]:
        return self.api.search(keyword)

    async def quotes(self, codes: list[str]) -> dict[str, list[float]]:
        return self.api.quotes(codes)

    async def closes(self, codes: list[str], start: str, end: str) -> dict[str, Any]:
        return self.api.closes(codes, start, end)


def _fill(rows: list[dict[str, Any]], api: Any) -> tuple[list[dict[str, Any]], list[dict]]:
    return fill_component_codes(_Fill(rows), api, concurrency=5).result()


def row(fund_code: str, serial: int, name: str, close: float | None) -> dict[str, Any]:
    return {"fundCode": fund_code, "serialNumber": serial, "componentName": name, "close": close}


def codes_of(rows: list[dict[str, Any]]) -> list[Any]:
    return [r.get("componentCode") for r in rows]


AH_MOBILE = [("600941.SH", "中国移动"), ("00941.HK", "中国移动")]
MOBILE_PRICES = {"600941.SH": [101.3, 100.7], "00941.HK": [77.3, 78.1]}
# Recent daily closes that rule each listing out for the other share class's row: a quote
# that agrees counts across markets only once the other market's listing is ruled out.
MOBILE_HISTORY = {"600941.SH": [("2026-10-27", 101.3)], "00941.HK": [("2026-10-27", 77.3)]}


@pytest.mark.parametrize("order", [[77.3, 101.3], [101.3, 77.3]])
def test_tells_the_a_and_h_rows_of_one_name_apart_by_price(order):
    pair = [row("517180.SH", i + 1, "中国移动", close) for i, close in enumerate(order)]
    rows, unresolved = _fill(
        pair, _Api({"中国移动": AH_MOBILE}, MOBILE_PRICES, history=MOBILE_HISTORY)
    )
    assert codes_of(rows) == ["00941.HK" if c == 77.3 else "600941.SH" for c in order]
    assert unresolved == []
    # Without daily closes the other listing cannot be ruled out: a lagging list could
    # equal the other market's quote by chance, so neither row is taken on the quote alone.
    unaided, _ = _fill(pair, _Api({"中国移动": AH_MOBILE}, MOBILE_PRICES))
    assert codes_of(unaided) == [None, None]


def test_takes_the_confirmed_listing_and_puts_component_code_after_serial_number():
    api = _Api(
        {
            "建设银行": [("00939.HK", "建设银行"), ("601939.SH", "建设银行")],
            "小米集团": [
                ("01810.HK", "小米集团-W"),
                ("81810.HK", "小米集团-WR"),
                ("XC180001.SH", "小米集团-D", "dr"),
            ],
        },
        {
            "00939.HK": [9.92, 9.95],
            "601939.SH": [9.1, 9.2],
            "01810.HK": [26.9, 27.1],
            "81810.HK": [24.6, 24.8],
        },
        # The A share's recent closes rule it out for the H row.
        history={"601939.SH": [("2026-10-27", 9.1)]},
    )
    rows, _ = _fill(
        [row("159920.SZ", 4, "建设银行", 9.92), row("159920.SZ", 5, "小米集团", 26.9)], api
    )
    assert codes_of(rows) == ["00939.HK", "01810.HK"]
    assert list(rows[0]) == ["fundCode", "serialNumber", "componentCode", "componentName", "close"]


def test_searches_a_padded_name_without_its_spaces():
    api = _Api({"五粮液": [("000858.SZ", "五粮液")]}, {"000858.SZ": [75.63, 75.1]})
    rows, _ = _fill([row("510300.SH", 9, "五 粮 液", 75.63)], api)
    assert api.searched == ["五粮液"]
    assert codes_of(rows) == ["000858.SZ"]


def test_an_exact_name_in_the_etfs_market_stands_when_no_price_agrees_never_a_prefix():
    # Ex-dividend day: the previous close is adjusted (9.25), the component list keeps 9.55.
    api = _Api(
        {
            "上海银行": [("601229.SH", "上海银行"), ("212480009.IB", "24上海银行债01", "bond")],
            "贵州茅台": [("600519.SH", "贵州茅台")],
            "中海油": [("601808.SH", "中海油服"), ("02883.HK", "中海油田服务")],
        },
        {
            "601229.SH": [9.25, 9.45],
            "600519.SH": [1335, 1349.98],
            "601808.SH": [14.6, 14.7],
            "02883.HK": [7.5, 7.6],
        },
    )
    rows3 = [
        row("510300.SH", 1, "贵州茅台", 1349.98),
        row("510300.SH", 2, "上海银行", 9.55),
        row("510300.SH", 3, "中海油", 20.1),
    ]
    # 中海油's prefix candidates trade in two markets; their recent closes rule both out.
    api._history = {"601808.SH": [("2026-10-27", 14.6)], "02883.HK": [("2026-10-27", 7.5)]}
    rows, unresolved = _fill(rows3, api)
    assert codes_of(rows) == ["600519.SH", "601229.SH", None]
    assert unresolved == [{"fundCode": "510300.SH", "serialNumber": 3, "componentName": "中海油"}]
    # Without daily closes 中海油 could still be either, so the ETF's market is not known.
    api._history = {}
    assert codes_of(_fill(rows3, api)[0]) == ["600519.SH", None, None]


def test_a_name_match_outside_the_etfs_market_does_not_stand_on_the_name_alone():
    # A Hong Kong ETF's 中国石化 row is the H share, which the search lists as 中国石油化工股份.
    api = _Api(
        {
            "中国石化": [("600028.SH", "中国石化")],
            "腾讯控股": [("00700.HK", "腾讯控股")],
            "汇丰控股": [("00005.HK", "汇丰控股")],
        },
        {"600028.SH": [5.56, 5.51], "00700.HK": [386.4, 390], "00005.HK": [120, 121]},
    )
    rows, _ = _fill(
        [
            row("159920.SZ", 1, "腾讯控股", 386.4),
            row("159920.SZ", 2, "汇丰控股", 120),
            row("159920.SZ", 3, "中国石化", 4.64),
        ],
        api,
    )
    assert codes_of(rows) == ["00700.HK", "00005.HK", None]


def test_a_price_confirmed_listing_goes_to_its_row_before_a_same_name_row_takes_it():
    # The H row (中国建筑国际, 8.44) is not found under this name; the A row's price confirms.
    api = _Api({"中国建筑": [("601668.SH", "中国建筑")]}, {"601668.SH": [4.58, 4.6]})
    rows, _ = _fill(
        [row("517180.SH", 1, "中国建筑", 8.44), row("517180.SH", 2, "中国建筑", 4.58)], api
    )
    assert codes_of(rows) == [None, "601668.SH"]


def test_matches_a_longer_hong_kong_name_by_prefix_when_the_price_confirms_it():
    api = _Api(
        {
            "比亚迪": [
                ("002594.SZ", "比亚迪"),
                ("00285.HK", "比亚迪电子"),
                ("01211.HK", "比亚迪股份"),
            ],
            "腾讯控股": [("00700.HK", "腾讯控股")],
        },
        {
            "002594.SZ": [82.4, 82.01],
            "00285.HK": [22.58, 22.3],
            "01211.HK": [70.8, 70.05],
            "00700.HK": [386.4, 390],
        },
        # The A share's recent closes rule it out for the row the H share's price confirms.
        history={"002594.SZ": [("2026-10-27", 82.4)]},
    )
    rows, _ = _fill(
        [row("159920.SZ", 1, "腾讯控股", 386.4), row("159920.SZ", 2, "比亚迪", 70.8)], api
    )
    assert codes_of(rows) == ["00700.HK", "01211.HK"]


def test_asks_for_a_us_ticker_with_its_exchange_suffix_when_the_search_finds_it_elsewhere():
    api = _Api(
        {
            "TRI": [("TRI.LON", "Trifast")],
            "TRI.O": [("TRI.O", "汤森路透"), ("ITRI.O", "埃创")],
            "NVDA": [("NVDA.O", "英伟达")],
        },
        {"TRI.O": [122.08, 121], "NVDA.O": [216, 218]},
    )
    rows, _ = _fill([row("513100.SH", 1, "NVDA", 216), row("513100.SH", 2, "TRI", 122.08)], api)
    assert codes_of(rows) == ["NVDA.O", "TRI.O"]
    assert sorted(api.searched) == ["NVDA", "TRI", "TRI.N", "TRI.O"]


def test_quotes_no_bond_and_takes_the_bond_listed_on_the_etfs_own_exchange():
    # 26国债08 has one listing, which shows the ETF holds Shanghai/Shenzhen/Beijing bonds only.
    api = _Api(
        {
            "26国债15": [("802615.BJ", "26国债15", "bond"), ("019848.SH", "26国债15", "bond")],
            "26国债08": [("019834.SH", "26国债08", "bond")],
        },
        {},
    )
    rows, _ = _fill(
        [row("511010.SH", 1, "26国债15", 100.264), row("511010.SH", 2, "26国债08", 100.746)], api
    )
    assert codes_of(rows) == ["019848.SH", "019834.SH"]
    assert api.quoted == []


def test_leaves_cash_lines_and_unmatched_names_none_and_a_row_with_a_code_untouched():
    api = _Api({"申赎现金": [], "黄金9999": []}, {})
    carried = {
        "fundCode": "510300.SH",
        "serialNumber": 1,
        "componentCode": "600519",
        "componentName": "贵州茅台",
        "close": 1,
    }
    rows, unresolved = _fill(
        [carried, row("510300.SH", 2, "申赎现金", None), row("518880.SH", 1, "黄金9999", None)], api
    )
    assert rows[0] is carried
    assert codes_of(rows) == ["600519", None, None]
    assert [u["componentName"] for u in unresolved] == ["申赎现金", "黄金9999"]
    assert sorted(api.searched) == ["申赎现金", "黄金9999"]


def test_isolates_a_code_the_quote_rejects_instead_of_losing_its_whole_batch():
    api = _Api(
        {"中国移动": AH_MOBILE, "某某控股": [("00001.HK", "某某控股")]},
        MOBILE_PRICES,
        fail_quote="00001.HK",
        history=MOBILE_HISTORY,
    )
    rows, _ = _fill(
        [
            row("517180.SH", 1, "某某控股", 5),
            row("517180.SH", 2, "中国移动", 77.3),
            row("517180.SH", 3, "中国移动", 101.3),
        ],
        api,
    )
    # The pair still gets its prices; the rejected code has none, and in an A+H ETF a row
    # its price cannot place stays None.
    assert codes_of(rows) == [None, "00941.HK", "600941.SH"]
    assert len(api.quoted) > 1


class _FailingQuotes(_Api):
    def __init__(self, search: dict[str, list[Listing]], code: str = "999999") -> None:
        super().__init__(search, {})
        self.code = code
        self.calls = 0

    def quotes(self, codes: list[str]) -> dict[str, list[float]]:
        self.calls += 1
        raise ApiError("服务故障", code=self.code)


def test_an_ah_name_stays_none_in_a_two_market_etf_without_a_price_but_not_in_a_one_market_etf():
    search = {
        "龙源电力": [("001289.SZ", "龙源电力"), ("00916.HK", "龙源电力")],
        "招商银行": [("600036.SH", "招商银行"), ("03968.HK", "招商银行")],
        "中国石油": [("601857.SH", "中国石油")],
        "华润啤酒": [("00291.HK", "华润啤酒")],
        "贵州茅台": [("600519.SH", "贵州茅台")],
    }
    mixed, _ = _fill(
        [
            row("517180.SH", 1, "中国石油", 13.38),
            row("517180.SH", 2, "华润啤酒", 19.48),
            row("517180.SH", 70, "龙源电力", 5.065),
        ],
        _FailingQuotes(search),
    )
    assert codes_of(mixed) == [None, None, None]
    # 招商银行 could be the H share: 贵州茅台 alone does not make the ETF an A-share one.
    pure_rows = [row("510300.SH", 1, "贵州茅台", 1349.98), row("510300.SH", 5, "招商银行", 42.5)]
    pure, _ = _fill(pure_rows, _FailingQuotes(search))
    assert codes_of(pure) == [None, None]
    # Unless the H share's recent closes rule it out.
    ruled_out = _FailingQuotes(search)
    ruled_out._history = {"03968.HK": [("2026-10-27", 39.0)]}
    assert codes_of(_fill(pure_rows, ruled_out)[0]) == ["600519.SH", "600036.SH"]


@pytest.mark.parametrize("mobile_a", [[0, 0], [99.9, 100.7]])
def test_in_a_two_market_etf_a_row_stays_none_when_its_price_decides_nothing(mobile_a):
    # 中国移动 is the A row: suspended (quote 0) or ex-dividend (quote off the list), and the
    # H quote is missing. Neither says which listing the row is.
    search = {
        "中国移动": AH_MOBILE,
        "中国石油": [("601857.SH", "中国石油")],
        "华润啤酒": [("00291.HK", "华润啤酒")],
    }
    prices = {"600941.SH": mobile_a, "601857.SH": [13.38, 13.2], "00291.HK": [19.48, 19.6]}
    rows, unresolved = _fill(
        [
            row("517180.SH", 1, "中国石油", 13.38),
            row("517180.SH", 2, "华润啤酒", 19.48),
            row("517180.SH", 3, "中国移动", 101.3),
        ],
        _Api(search, prices),
    )
    assert codes_of(rows) == ["601857.SH", "00291.HK", None]
    assert [u["componentName"] for u in unresolved] == ["中国移动"]


def test_a_listing_in_a_market_the_prices_never_confirmed_does_not_stand_on_the_name():
    # The search found only London's TRI (Trifast); the Nasdaq ETF's other rows are US.
    api = _Api(
        {"NVDA": [("NVDA.O", "英伟达")], "TRI": [("TRI.LON", "Trifast")]}, {"NVDA.O": [216, 218]}
    )
    rows, _ = _fill([row("513100.SH", 1, "NVDA", 216), row("513100.SH", 2, "TRI", 122.08)], api)
    assert codes_of(rows) == ["NVDA.O", None]


def test_a_price_counts_only_when_it_is_the_rows_own():
    # The H quote is missing; 紫金矿业's A share (27.85) is close to the H row (27.74) by
    # chance. Not confirmed by it, the row falls to the name once the A share's recent
    # closes rule it out — in a HK ETF, the H share. Without them the row could be either.
    search = {
        "紫金矿业": [("02899.HK", "紫金矿业"), ("601899.SH", "紫金矿业")],
        "腾讯控股": [("00700.HK", "腾讯控股")],
    }
    prices = {"00700.HK": [386.4, 390], "601899.SH": [27.47, 27.85]}
    rows2 = [row("159920.SZ", 1, "腾讯控股", 386.4), row("159920.SZ", 2, "紫金矿业", 27.74)]
    history = {"601899.SH": [("2026-10-26", 27.47), ("2026-10-27", 27.85)]}
    rows, _ = _fill(rows2, _Api(search, prices, history=history))
    assert codes_of(rows) == ["00700.HK", "02899.HK"]
    assert codes_of(_fill(rows2, _Api(search, prices))[0]) == ["00700.HK", None]


NAMES16 = [f"名称{i}" for i in range(16)]
SEARCH16 = {name: [(f"{600000 + i}.SH", name)] for i, name in enumerate(NAMES16)}
ROWS16 = [row("510300.SH", i, name, 1) for i, name in enumerate(NAMES16)]


@pytest.mark.parametrize("code", ["999999", "429"])
def test_a_failed_quote_batch_is_sent_once_unless_it_failed_on_120001(code):
    api = _FailingQuotes(SEARCH16, code)
    _fill([dict(r) for r in ROWS16], api)
    assert api.calls == 1


def test_a_batch_failing_on_120001_is_halved_until_the_bad_code_is_alone():
    class Splitting(_Api):
        def quotes(self, codes: list[str]) -> dict[str, list[float]]:
            self.quoted.append(codes)
            if "600003.SH" in codes:
                raise ApiError("证券代码无效", code="120001")
            return {c: [1] for c in codes}

    api = Splitting(SEARCH16, {})
    rows, _ = _fill([dict(r) for r in ROWS16], api)
    # The rejected code has no price; in an ETF of one market its exact name stands.
    assert len([c for c in codes_of(rows) if c]) == 16
    # 16 → 8 + 8 → 4 + 4 → 2 + 2 → 1 + 1, each half after the other.
    assert [len(batch) for batch in api.quoted] == [16, 8, 4, 2, 2, 1, 1, 4, 8]


@pytest.mark.parametrize("given", [None, ""])
def test_fills_a_row_answered_with_a_none_or_empty_code_once_after_serial_number(given):
    api = _Api({"贵州茅台": [("600519.SH", "贵州茅台")]}, {"600519.SH": [1335, 1349.98]})
    rows, unresolved = _fill(
        [
            {
                "fundCode": "510300.SH",
                "serialNumber": 1,
                "componentCode": given,
                "componentName": "贵州茅台",
                "close": 1349.98,
            }
        ],
        api,
    )
    assert rows[0] == {
        "fundCode": "510300.SH",
        "serialNumber": 1,
        "componentCode": "600519.SH",
        "componentName": "贵州茅台",
        "close": 1349.98,
    }
    assert list(rows[0]) == ["fundCode", "serialNumber", "componentCode", "componentName", "close"]
    assert unresolved == []


def test_checks_a_list_whose_prices_lag_the_quote_against_the_closes_of_their_day():
    # 517180.SH's 10-28 list carried 10-26 closes for its A shares (its H shares were
    # current); the quote has moved on to 10-27. 中国铁建's A share has not traded since
    # 10-23 (suspended): its last close stands for 10-26.
    search = {
        "中国移动": AH_MOBILE,
        "中国石油": [("601857.SH", "中国石油")],
        "中国神华": [("601088.SH", "中国神华")],
        "华润啤酒": [("00291.HK", "华润啤酒")],
        "中国铁建": [("601186.SH", "中国铁建"), ("01186.HK", "中国铁建")],
    }
    history = {
        "601186.SH": [("2026-10-23", 6.11)],
        "01186.HK": [("2026-10-26", 4.5), ("2026-10-27", 4.6)],
        "600941.SH": [("2026-10-23", 99.14), ("2026-10-26", 101.3), ("2026-10-27", 100.7)],
        "00941.HK": [("2026-10-23", 77.1), ("2026-10-26", 77.3), ("2026-10-27", 78.1)],
        "601857.SH": [("2026-10-23", 12.75), ("2026-10-26", 13.38), ("2026-10-27", 13.2)],
        "601088.SH": [("2026-10-23", 38.1), ("2026-10-26", 38.6), ("2026-10-27", 38.4)],
        "00291.HK": [("2026-10-26", 19.3), ("2026-10-27", 19.48)],
    }
    prices = {
        "600941.SH": [100.7, 100.7],
        "00941.HK": [78.1, 78.1],
        "601857.SH": [13.2, 13.2],
        "601088.SH": [38.4, 38.4],
        "00291.HK": [19.48, 19.48],
    }

    def rows() -> list[dict[str, Any]]:
        return [
            row("517180.SH", 1, "中国石油", 13.38),
            row("517180.SH", 2, "中国神华", 38.6),
            row("517180.SH", 3, "中国移动", 101.3),
            row("517180.SH", 4, "中国移动", 78.1),
            row("517180.SH", 5, "华润啤酒", 19.48),
            row("517180.SH", 6, "中国铁建", 6.11),
        ]

    api = _Api(search, prices, history=history)
    out, _ = _fill(rows(), api)
    assert codes_of(out) == [
        "601857.SH",
        "601088.SH",
        "600941.SH",
        "00941.HK",
        "00291.HK",
        "601186.SH",
    ]
    assert len(api.asked) == 1
    # Without daily closes the lagging rows are left to the name: an A+H ETF places none.
    # Nor does the current H row of 中国移动 stand on its quote: nothing rules out the A share.
    unaided, _ = _fill(rows(), _Api(search, prices))
    assert codes_of(unaided) == [None, None, None, None, "00291.HK", None]


def _lagging(history: dict[str, list[tuple[str, float]]], extra: dict | None = None) -> _Api:
    """An A+H ETF (华润啤酒 is Hong Kong only and current) whose A rows lag; the quote is no
    help."""
    search = {
        "中国移动": AH_MOBILE,
        "中国石油": [("601857.SH", "中国石油")],
        "中国神华": [("601088.SH", "中国神华")],
        "华润啤酒": [("00291.HK", "华润啤酒")],
        **(extra or {}),
    }
    return _Api(search, {"00291.HK": [19.48, 19.48]}, history=history)


def _mobile_a() -> dict[str, Any]:
    return row("517180.SH", 3, "中国移动", 101.3)


def _beer() -> dict[str, Any]:
    return row("517180.SH", 2, "华润啤酒", 19.48)


def test_does_not_settle_a_lists_date_on_a_single_row():
    # Only 中国石油 has a single listing with daily closes: one row says 10-26.
    api = _lagging(
        {
            "600941.SH": [("2026-10-26", 101.3)],
            "00941.HK": [("2026-10-26", 77.3)],
            "601857.SH": [("2026-10-26", 13.38)],
        }
    )
    rows, _ = _fill([row("517180.SH", 1, "中国石油", 13.38), _beer(), _mobile_a()], api)
    assert codes_of(rows) == [None, "00291.HK", None]


def test_does_not_settle_a_markets_date_on_a_tie_between_two_days():
    # 中国石油 and 中国神华 say the A shares are 10-26; 贵州茅台 and 五粮液 say 10-27.
    api = _lagging(
        {
            "600941.SH": [("2026-10-26", 101.3)],
            "00941.HK": [("2026-10-26", 77.3)],
            "601857.SH": [("2026-10-26", 13.38)],
            "601088.SH": [("2026-10-26", 38.6)],
            "600519.SH": [("2026-10-27", 1349.98)],
            "000858.SZ": [("2026-10-27", 75.63)],
        },
        {"贵州茅台": [("600519.SH", "贵州茅台")], "五粮液": [("000858.SZ", "五粮液")]},
    )
    rows, _ = _fill(
        [
            row("517180.SH", 1, "中国石油", 13.38),
            row("517180.SH", 4, "中国神华", 38.6),
            row("517180.SH", 5, "贵州茅台", 1349.98),
            row("517180.SH", 6, "五粮液", 75.63),
            _beer(),
            _mobile_a(),
        ],
        api,
    )
    assert codes_of(rows) == [None, None, None, None, "00291.HK", None]


def test_matches_the_lagging_rows_against_that_one_days_closes_not_any_days():
    # On 10-23 the H share closed at 101.3 HKD — the A row's 10-26 price, by chance. The H
    # shares' day is 10-27.
    api = _lagging(
        {
            "600941.SH": [("2026-10-23", 99.14), ("2026-10-26", 101.3)],
            "00941.HK": [("2026-10-23", 101.3), ("2026-10-26", 77.3)],
            "601857.SH": [("2026-10-26", 13.38)],
            "601088.SH": [("2026-10-26", 38.6)],
            "00291.HK": [("2026-10-27", 19.48)],
            "00700.HK": [("2026-10-27", 385.2)],
        },
        {"腾讯控股": [("00700.HK", "腾讯控股")]},
    )
    rows, _ = _fill(
        [
            row("517180.SH", 1, "中国石油", 13.38),
            row("517180.SH", 4, "中国神华", 38.6),
            _beer(),
            row("517180.SH", 5, "腾讯控股", 385.2),
            _mobile_a(),
        ],
        api,
    )
    assert codes_of(rows) == ["601857.SH", "601088.SH", "00291.HK", "00700.HK", "600941.SH"]


# An A+H list whose A rows carry 10-20 closes and whose H rows 10-22's; the quote is no
# help. 恒瑞医药's H row (47.44 HKD on 10-22) is within 0.05% of the A share's 10-20 close.
SPLIT_DATES: dict[str, list[tuple[str, float]]] = {
    "601857.SH": [("2026-10-20", 13.38), ("2026-10-22", 13.0)],
    "601088.SH": [("2026-10-20", 38.6), ("2026-10-22", 38.0)],
    "600519.SH": [("2026-10-20", 1400), ("2026-10-22", 1420)],
    "600941.SH": [("2026-10-20", 101.3), ("2026-10-22", 100.2)],
    "00941.HK": [("2026-10-20", 77.0), ("2026-10-22", 77.3)],
    "00291.HK": [("2026-10-20", 19.0), ("2026-10-22", 19.48)],
    "00700.HK": [("2026-10-20", 380), ("2026-10-22", 385.2)],
    "00005.HK": [("2026-10-20", 118), ("2026-10-22", 120)],
    "600276.SH": [("2026-10-20", 47.45), ("2026-10-22", 48.3)],
    "01276.HK": [("2026-10-20", 46.1), ("2026-10-22", 47.44)],
    "001289.SZ": [("2026-10-20", 5.065), ("2026-10-22", 5.1)],
}
SPLIT_SEARCH = {
    "中国石油": [("601857.SH", "中国石油")],
    "中国神华": [("601088.SH", "中国神华")],
    "贵州茅台": [("600519.SH", "贵州茅台")],
    "中国移动": AH_MOBILE,
    "华润啤酒": [("00291.HK", "华润啤酒")],
    "腾讯控股": [("00700.HK", "腾讯控股")],
    "汇丰控股": [("00005.HK", "汇丰控股")],
    "恒瑞医药": [("600276.SH", "恒瑞医药"), ("01276.HK", "恒瑞医药")],
    "龙源电力": [("001289.SZ", "龙源电力"), ("00916.HK", "龙源电力")],
}


def _split_dates(
    history: dict[str, list[tuple[str, float]]] = SPLIT_DATES, prices: dict | None = None
) -> _Api:
    return _Api(SPLIT_SEARCH, prices or {}, history=history)


def _etf517(*rows: tuple[str, float]) -> list[dict[str, Any]]:
    return [row("517180.SH", i + 1, name, close) for i, (name, close) in enumerate(rows)]


def test_dates_each_markets_prices_on_their_own():
    rows, _ = _fill(
        _etf517(
            ("中国石油", 13.38),
            ("中国神华", 38.6),
            ("华润啤酒", 19.48),
            ("腾讯控股", 385.2),
            ("汇丰控股", 120),
            ("中国移动", 101.3),
        ),
        _split_dates(),
    )
    assert codes_of(rows) == [
        "601857.SH",
        "601088.SH",
        "00291.HK",
        "00700.HK",
        "00005.HK",
        "600941.SH",
    ]


def test_leaves_a_row_none_when_a_listing_it_could_be_is_undated_or_agrees_as_well():
    # Two H rows date the H shares to 10-22: both of 恒瑞医药's listings agree with the H row.
    dated, _ = _fill(
        _etf517(
            ("中国石油", 13.38),
            ("中国神华", 38.6),
            ("贵州茅台", 1400),
            ("华润啤酒", 19.48),
            ("腾讯控股", 385.2),
            ("恒瑞医药", 47.44),
        ),
        _split_dates(),
    )
    assert codes_of(dated) == ["601857.SH", "601088.SH", "600519.SH", "00291.HK", "00700.HK", None]
    # One H row dates nothing: the H share can be neither confirmed nor ruled out — by an
    # agreeing close (恒瑞医药), or by none at all (龙源电力's H share has no daily closes).
    undated, _ = _fill(
        _etf517(
            ("中国石油", 13.38),
            ("中国神华", 38.6),
            ("贵州茅台", 1400),
            ("华润啤酒", 19.48),
            ("恒瑞医药", 47.44),
            ("龙源电力", 5.065),
        ),
        _split_dates(),
    )
    assert codes_of(undated) == ["601857.SH", "601088.SH", "600519.SH", None, None, None]


def test_leaves_a_row_none_when_a_listing_it_could_be_has_no_close_on_its_markets_day():
    # Both markets are dated; 恒瑞医药's H share alone has no daily closes, and its A
    # share's 10-20 close agrees with the H row.
    without_h = {code: series for code, series in SPLIT_DATES.items() if code != "01276.HK"}
    rows, _ = _fill(
        _etf517(
            ("中国石油", 13.38),
            ("中国神华", 38.6),
            ("贵州茅台", 1400),
            ("华润啤酒", 19.48),
            ("腾讯控股", 385.2),
            ("恒瑞医药", 47.44),
        ),
        _split_dates(without_h),
    )
    assert codes_of(rows) == ["601857.SH", "601088.SH", "600519.SH", "00291.HK", "00700.HK", None]


@pytest.mark.parametrize("quote_h", [None, [0, 0]])
def test_does_not_take_a_quoted_listing_when_another_has_no_quote_or_quotes_zero(quote_h):
    # 恒瑞医药's H row; the A share's latest price happens to agree with it.
    search = {
        "中国石油": [("601857.SH", "中国石油")],
        "华润啤酒": [("00291.HK", "华润啤酒")],
        "恒瑞医药": [("600276.SH", "恒瑞医药"), ("01276.HK", "恒瑞医药")],
    }
    prices = {"601857.SH": [13.38, 13.2], "00291.HK": [19.48, 19.6], "600276.SH": [47.1, 47.45]}
    if quote_h:
        prices["01276.HK"] = quote_h
    rows, _ = _fill(
        _etf517(("中国石油", 13.38), ("华润啤酒", 19.48), ("恒瑞医药", 47.44)), _Api(search, prices)
    )
    assert codes_of(rows) == ["601857.SH", "00291.HK", None]


def test_an_exact_listing_its_price_confirms_stands_beside_a_longer_name_without_a_price():
    # 中国石油股份 (the H share's name) starts with the A row's name and quotes 0.
    search = {
        "中国石油": [("601857.SH", "中国石油"), ("00857.HK", "中国石油股份")],
        "华润啤酒": [("00291.HK", "华润啤酒")],
    }
    prices = {"601857.SH": [13.38, 13.2], "00857.HK": [0, 0], "00291.HK": [19.48, 19.6]}
    # Its recent closes rule the H share out, so the A share's quote stands.
    history = {"00857.HK": [("2026-10-27", 7.2)]}
    rows, _ = _fill(
        _etf517(("中国石油", 13.38), ("华润啤酒", 19.48)), _Api(search, prices, history=history)
    )
    assert codes_of(rows) == ["601857.SH", "00291.HK"]


def test_does_not_hold_a_row_back_for_a_listing_another_rows_price_has_taken():
    # The H row of 中国移动 is current and takes 00941.HK; the H shares have no day of their
    # own, and 00941.HK's 10-20 close happens to equal the A row's price.
    history = {**SPLIT_DATES, "00941.HK": [("2026-10-20", 101.3), ("2026-10-22", 77.3)]}
    api = _split_dates(history, {"00941.HK": [78.1, 78.1], "600941.SH": [100.7, 100.9]})
    rows, _ = _fill(
        _etf517(("中国石油", 13.38), ("中国神华", 38.6), ("中国移动", 78.1), ("中国移动", 101.3)),
        api,
    )
    assert codes_of(rows) == ["601857.SH", "601088.SH", "00941.HK", "600941.SH"]


def test_a_name_whose_exact_listings_all_trade_in_one_market_is_a_sign_of_that_market():
    # 腾讯控股 has two Hong Kong listings (HKD and RMB counters): the ETF holds Hong Kong
    # stocks too, so with no price to decide, the 中国移动 row is not taken for the A share.
    search = {
        "贵州茅台": [("600519.SH", "贵州茅台")],
        "腾讯控股": [("00700.HK", "腾讯控股"), ("80700.HK", "腾讯控股-R")],
        "中国移动": AH_MOBILE,
    }
    rows, _ = _fill(
        [
            row("517180.SH", 1, "贵州茅台", 1349.98),
            row("517180.SH", 2, "腾讯控股", 386.4),
            row("517180.SH", 3, "中国移动", 78.1),
        ],
        _FailingQuotes(search),
    )
    assert codes_of(rows) == [None, None, None]


def test_leaves_only_the_name_whose_search_failed_none():
    api = _Api(
        {"中国移动": AH_MOBILE}, MOBILE_PRICES, fail_search="腾讯控股", history=MOBILE_HISTORY
    )
    rows, _ = _fill(
        [row("517180.SH", 1, "腾讯控股", 386.4), row("517180.SH", 2, "中国移动", 101.3)], api
    )
    assert codes_of(rows) == [None, "600941.SH"]


def test_passes_rows_that_are_not_objects_through():
    api = _Api({"贵州茅台": [("600519.SH", "贵州茅台")]}, {"600519.SH": [1349.98]})
    rows, _ = _fill([None, row("510300.SH", 1, "贵州茅台", 1349.98)], api)
    assert rows[0] is None
    assert rows[1]["componentCode"] == "600519.SH"


# ---- async driver: same matching, requests awaited ----


@pytest.mark.anyio
async def test_async_driver_matches_like_the_sync_one():
    api = _Api(
        {"中国移动": AH_MOBILE, "某某控股": [("00001.HK", "某某控股")]},
        MOBILE_PRICES,
        fail_quote="00001.HK",
        history=MOBILE_HISTORY,
    )
    fill = await fill_component_codes_async(
        _Fill(
            [
                row("517180.SH", 1, "某某控股", 5),
                row("517180.SH", 2, "中国移动", 77.3),
                row("517180.SH", 3, "中国移动", 101.3),
            ]
        ),
        _AsyncApi(api),
        concurrency=5,
    )
    rows, unresolved = fill.result()
    assert codes_of(rows) == [None, "00941.HK", "600941.SH"]
    assert [u["componentName"] for u in unresolved] == ["某某控股"]


@pytest.mark.anyio
async def test_async_driver_checks_lagging_rows_against_daily_closes():
    fill = await fill_component_codes_async(
        _Fill(
            _etf517(
                ("中国石油", 13.38),
                ("中国神华", 38.6),
                ("华润啤酒", 19.48),
                ("腾讯控股", 385.2),
                ("汇丰控股", 120),
                ("中国移动", 101.3),
            )
        ),
        _AsyncApi(_split_dates()),
        concurrency=5,
    )
    rows, _ = fill.result()
    assert codes_of(rows) == [
        "601857.SH",
        "601088.SH",
        "00291.HK",
        "00700.HK",
        "00005.HK",
        "600941.SH",
    ]


@pytest.mark.anyio
async def test_async_driver_asks_for_a_us_ticker_with_its_exchange_suffix():
    api = _Api(
        {
            "TRI": [("TRI.LON", "Trifast")],
            "TRI.O": [("TRI.O", "汤森路透")],
            "NVDA": [("NVDA.O", "英伟达")],
        },
        {"TRI.O": [122.08, 121], "NVDA.O": [216, 218]},
    )
    fill = await fill_component_codes_async(
        _Fill([row("513100.SH", 1, "NVDA", 216), row("513100.SH", 2, "TRI", 122.08)]),
        _AsyncApi(api),
        concurrency=5,
    )
    assert codes_of(fill.result()[0]) == ["NVDA.O", "TRI.O"]


# ---- the securities table and the client lookups ----

# The three whole-market lists (全部A股 / 全部港股 / 全部美股), a few rows each.
SECTORS: dict[str, list[dict[str, str]]] = {
    "1000000002": [
        {"gtsCode": "600941.SH", "gtsName": "中国移动"},
        {"gtsCode": "002594.SZ", "gtsName": "比亚迪"},
        {"gtsCode": "000858.SZ", "gtsName": "五粮液"},
    ],
    "1000002615": [
        {"gtsCode": "00941.HK", "gtsName": "中国移动"},
        {"gtsCode": "01211.HK", "gtsName": "比亚迪股份"},
        {"gtsCode": "00285.HK", "gtsName": "比亚迪电子"},
        {"gtsCode": "01810.HK", "gtsName": "小米集团-W"},
        {"gtsCode": "81810.HK", "gtsName": "小米集团-WR"},
    ],
    "1000002618": [
        {"gtsCode": "TRI.O", "gtsName": "Thomson Reuters"},
        {"gtsCode": "BESS.A", "gtsName": "Bimergen Energy"},
    ],
}


class _Config:
    page_concurrency = 3


class _Client:
    """Answers the four endpoints the lookups call, and records every call."""

    config = _Config()

    def __init__(self, sectors: dict[str, Any] = SECTORS, day_kline: Any = None) -> None:
        self.sectors = sectors
        self.day_kline = day_kline
        self.calls: list[tuple[str, Any]] = []

    def _answer(self, endpoint: str, body: Any) -> Any:
        self.calls.append((endpoint, body))
        if endpoint == "reference.sector-constituents":
            listed = self.sectors[body["sectorId"]]
            if isinstance(listed, Exception):
                raise listed
            return {"total": 0, "list": listed}
        if endpoint == "reference.securities-search":
            return {"list": [{"gtsCode": "00285.HK", "gtsName": "比亚迪电子", "category": "stock"}]}
        if endpoint == "quote.realtime":
            return {"list": []}
        if endpoint == "quote.day-kline":
            return self.day_kline
        raise AssertionError(f"unexpected {endpoint}")

    def _call(self, endpoint: str, body: Any = None) -> Any:
        return self._answer(endpoint, body)


class _AsyncClient(_Client):
    async def _call(self, endpoint: str, body: Any = None) -> Any:
        return self._answer(endpoint, body)


def _table() -> _TableSearch:
    return _TableSearch([(r["gtsCode"], r["gtsName"]) for rows in SECTORS.values() for r in rows])


def _codes(search: _TableSearch, keyword: str) -> list[str] | None:
    hits = search(keyword)
    return None if hits is None else [hit["gtsCode"] for hit in hits]


def test_the_table_finds_a_name_exactly_by_ticker_or_code_with_the_names_starting_with_it():
    search = _table()
    assert _codes(search, "中国移动") == ["600941.SH", "00941.HK"]
    assert _codes(search, "比亚迪") == ["002594.SZ", "01211.HK", "00285.HK"]
    assert _codes(search, "小米集团") == ["01810.HK", "81810.HK"]
    assert _codes(search, "五 粮 液") == ["000858.SZ"]
    assert _codes(search, "TRI") == ["TRI.O"]
    assert _codes(search, "TRI.O") == ["TRI.O"]
    # Nothing carries these exactly: a truncated name, a bond, a cash line — left to search.
    for keyword in ("比亚迪电", "26国债15", "申赎现金"):
        assert search(keyword) is None


def test_the_table_is_three_markets_fetched_once_and_only_names_it_lacks_are_searched():
    client = _Client()
    lookup = CodeLookup(client)
    fill = _Fill(
        [
            row("159920.SZ", 1, "中国移动", None),
            row("159920.SZ", 2, "小米集团", None),
            row("159920.SZ", 3, "比亚迪电", None),
        ]
    )
    fill_component_codes(fill, lookup, concurrency=3)
    sectors = [
        body["sectorId"]
        for endpoint, body in client.calls
        if endpoint == "reference.sector-constituents"
    ]
    assert sorted(sectors) == ["1000000002", "1000002615", "1000002618"]
    assert [c for c in client.calls if c[0] == "reference.securities-search"] == [
        ("reference.securities-search", {"keyword": "比亚迪电", "top": 10})
    ]


@pytest.mark.parametrize("broken", [ApiError("120001", code="120001"), []])
def test_the_table_is_not_used_when_a_market_fails_or_lists_nothing(broken):
    client = _Client({**SECTORS, "1000002615": broken})
    assert CodeLookup(client)._local() is None
    hits = CodeLookup(client).search("中国移动")
    assert [h["gtsCode"] for h in hits] == ["00285.HK"]  # the search service's answer


def test_daily_closes_are_read_oldest_first_per_code_with_each_days_change():
    # The change comes from the two closes (TS v0.51.0); without a previous close, none.
    client = _Client(
        day_kline={
            "total": 3,
            "fieldList": ["securityCode", "tradeDate", "close", "preClose"],
            "list": [
                ["00941.HK", "2026-10-27", 78.1, 77.3],
                ["00941.HK", "2026-10-26", 77.3, None],
                ["600941.SH", "2026-10-26", 101.3, 100],
            ],
        }
    )
    closes = CodeLookup(client).closes(["00941.HK", "600941.SH"], "2026-10-18", "2026-10-28")
    rounded = {
        code: [(*bar[:2], round(bar[2], 4)) if len(bar) > 2 else bar for bar in bars]
        for code, bars in closes.items()
    }
    assert rounded == {
        "00941.HK": [("2026-10-26", 77.3), ("2026-10-27", 78.1, 1.0349)],
        "600941.SH": [("2026-10-26", 101.3, 1.3)],
    }
    assert client.calls == [
        (
            "quote.day-kline",
            {
                "securityList": ["00941.HK", "600941.SH"],
                "startDate": "2026-10-18",
                "endDate": "2026-10-28",
                "fieldList": ["securityCode", "tradeDate", "close", "preClose"],
                "limit": 10_000,
            },
        )
    ]


@pytest.mark.anyio
async def test_the_async_table_is_fetched_once_under_concurrent_searches():
    client = _AsyncClient()
    fill = _Fill(
        [
            row("159920.SZ", 1, "中国移动", None),
            row("159920.SZ", 2, "小米集团", None),
            row("159920.SZ", 3, "比亚迪电", None),
        ]
    )
    await fill_component_codes_async(fill, AsyncCodeLookup(client), concurrency=3)
    sectors = [c for c in client.calls if c[0] == "reference.sector-constituents"]
    assert len(sectors) == 3
    assert [c[1]["keyword"] for c in client.calls if c[0] == "reference.securities-search"] == [
        "比亚迪电"
    ]


# ---- paths the CLI's cases leave out: failed lookups, duplicate hits, price ties ----


def test_a_failed_lookup_leaves_the_etfs_market_unknown():
    # 腾讯控股's lookup fails and no quote answers. 贵州茅台 alone points to CN, but the failed
    # name may trade elsewhere: the 中国移动 (H) row must not be taken for the A share.
    api = _FailingQuotes({"贵州茅台": [("600519.SH", "贵州茅台")], "中国移动": AH_MOBILE})
    api._fail_search = "腾讯控股"
    rows, unresolved = _fill(
        [
            row("517180.SH", 1, "贵州茅台", 1349.98),
            row("517180.SH", 2, "腾讯控股", 386.4),
            row("517180.SH", 3, "中国移动", 78.1),
        ],
        api,
    )
    assert codes_of(rows) == [None, None, None]
    assert len(unresolved) == 3


def test_a_name_that_merely_finds_nothing_does_not_hide_the_market():
    # A cash line finds no listing without any lookup failing: the ETF is still CN.
    api = _FailingQuotes({"贵州茅台": [("600519.SH", "贵州茅台")], "申赎现金": []})
    rows, _ = _fill(
        [row("510300.SH", 1, "贵州茅台", 1349.98), row("510300.SH", 2, "申赎现金", None)], api
    )
    assert codes_of(rows) == ["600519.SH", None]


TRI_TWICE = {
    "TRI": [("TRI.LON", "Trifast")],
    "TRI.O": [("TRI.O", "汤森路透")],
    "TRI.N": [("TRI.O", "汤森路透")],
    "NVDA": [("NVDA.O", "英伟达")],
}
TRI_PRICES = {"TRI.O": [122.08, 121], "NVDA.O": [216, 218]}


def test_a_listing_two_searches_find_is_one_candidate():
    rows, _ = _fill(
        [row("513100.SH", 1, "NVDA", 216), row("513100.SH", 2, "TRI", 122.08)],
        _Api(TRI_TWICE, TRI_PRICES),
    )
    assert codes_of(rows) == ["NVDA.O", "TRI.O"]


CMB_TIE = {
    "贵州茅台": [("600519.SH", "贵州茅台")],
    "招商银行": [("600036.SH", "招商银行"), ("03968.HK", "招商银行")],
    "华润啤酒": [("00291.HK", "华润啤酒")],
}
# 招商银行's A share (42.5 CNY) and H share (42.5 HKD) both agree with the row.
CMB_TIE_PRICES = {
    "600519.SH": [1335, 1349.98],
    "600036.SH": [42.5, 42.3],
    "03968.HK": [42.5, 42.6],
    "00291.HK": [19.48, 19.6],
}


def test_a_price_tie_across_markets_is_settled_by_the_etfs_one_market():
    # Once the H share's recent closes rule it out, 招商银行 can only be an A share, and the
    # ETF's one market takes it.
    pair = [row("510300.SH", 1, "贵州茅台", 1349.98), row("510300.SH", 5, "招商银行", 42.5)]
    history = {"03968.HK": [("2026-10-27", 42.6)]}
    rows, _ = _fill(pair, _Api(CMB_TIE, CMB_TIE_PRICES, history=history))
    assert codes_of(rows) == ["600519.SH", "600036.SH"]
    # Without them the tie could be the H share: 贵州茅台 (confirmed by its own price) does
    # not make the ETF an A-share one.
    assert codes_of(_fill(pair, _Api(CMB_TIE, CMB_TIE_PRICES))[0]) == ["600519.SH", None]


def test_a_price_tie_across_markets_stays_none_in_an_etf_holding_both():
    rows, _ = _fill(
        [
            row("517180.SH", 1, "贵州茅台", 1349.98),
            row("517180.SH", 2, "华润啤酒", 19.48),
            row("517180.SH", 3, "招商银行", 42.5),
        ],
        _Api(CMB_TIE, CMB_TIE_PRICES),
    )
    assert codes_of(rows) == ["600519.SH", "00291.HK", None]


@pytest.mark.anyio
async def test_async_driver_keeps_a_failed_lookups_market_unknown_and_dedupes_hits():
    api = _FailingQuotes({"贵州茅台": [("600519.SH", "贵州茅台")], "中国移动": AH_MOBILE})
    api._fail_search = "腾讯控股"
    fill = await fill_component_codes_async(
        _Fill(
            [
                row("517180.SH", 1, "贵州茅台", 1349.98),
                row("517180.SH", 2, "腾讯控股", 386.4),
                row("517180.SH", 3, "中国移动", 78.1),
            ]
        ),
        _AsyncApi(api),
        concurrency=5,
    )
    assert codes_of(fill.result()[0]) == [None, None, None]
    fill = await fill_component_codes_async(
        _Fill([row("513100.SH", 1, "NVDA", 216), row("513100.SH", 2, "TRI", 122.08)]),
        _AsyncApi(_Api(TRI_TWICE, TRI_PRICES)),
        concurrency=5,
    )
    assert codes_of(fill.result()[0]) == ["NVDA.O", "TRI.O"]


def test_quotes_go_out_500_codes_a_request_and_daily_closes_1000():
    names = [f"成分{i}" for i in range(1001)]
    api = _Api({n: [(f"{600000 + i}.SH", n)] for i, n in enumerate(names)}, {})
    _fill([row("510300.SH", i, n, 1.0) for i, n in enumerate(names)], api)
    assert sorted(len(batch) for batch in api.quoted) == [1, 500, 500]
    assert sorted(len(batch) for batch in api.asked) == [1, 1000]


# 招商银行's first row agrees with both listings, its second with the H share only; the
# second takes 03968.HK, which leaves the first the A share — so the ETF holds both
# markets, and 中信银行's A/H tie decides nothing, whichever row comes first.
AH_TIES = {
    "招商银行": [("600036.SH", "招商银行"), ("03968.HK", "招商银行")],
    "中信银行": [("601998.SH", "中信银行"), ("00998.HK", "中信银行")],
}
AH_TIE_PRICES = {
    "600036.SH": [42.5, 42.3],
    "03968.HK": [39.0, 42.5],
    "601998.SH": [7.0, 7.1],
    "00998.HK": [7.0, 6.5],
}
# The A share's recent closes rule it out for the 39.0 row, whose H quote then stands.
AH_TIE_HISTORY = {"600036.SH": [("2026-10-27", 42.3)]}


@pytest.mark.parametrize("first", [0, 1])
def test_a_tie_another_rows_listing_settles_counts_as_market_evidence(first):
    cmb = [row("517180.SH", 1, "招商银行", 42.5), row("517180.SH", 2, "招商银行", 39.0)]
    if first:
        cmb.reverse()
    rows, _ = _fill(
        [*cmb, row("517180.SH", 3, "中信银行", 7.0)],
        _Api(AH_TIES, AH_TIE_PRICES, history=AH_TIE_HISTORY),
    )
    by_close = {r["close"]: r["componentCode"] for r in rows}
    assert by_close == {42.5: "600036.SH", 39.0: "03968.HK", 7.0: None}


@pytest.mark.anyio
@pytest.mark.parametrize("first", [0, 1])
async def test_async_driver_counts_a_settled_tie_as_market_evidence(first):
    cmb = [row("517180.SH", 1, "招商银行", 42.5), row("517180.SH", 2, "招商银行", 39.0)]
    if first:
        cmb.reverse()
    fill = await fill_component_codes_async(
        _Fill([*cmb, row("517180.SH", 3, "中信银行", 7.0)]),
        _AsyncApi(_Api(AH_TIES, AH_TIE_PRICES, history=AH_TIE_HISTORY)),
        concurrency=5,
    )
    by_close = {r["close"]: r["componentCode"] for r in fill.result()[0]}
    assert by_close == {42.5: "600036.SH", 39.0: "03968.HK", 7.0: None}


# ---- an open row that could be in two markets, and quotes held to the other listing's
# closes (TS v0.50.0) ----


class _Down(_Api):
    """Quote and daily closes both fail."""

    def quotes(self, codes: list[str]) -> dict[str, list[float]]:
        raise ApiError("服务故障", code="999999")

    def closes(self, codes: list[str], start: str, end: str) -> dict[str, Any]:
        raise ApiError("服务故障", code="999999")


@pytest.mark.parametrize("order", [[77.3, 101.3], [101.3, 77.3]])
def test_an_ah_name_no_price_decides_is_not_filled_from_the_other_rows_market(order):
    # An A+H ETF can hold the H share of a dual-listed company beside A-only names, so
    # 贵州茅台 alone does not make the ETF an A-share one.
    search = {"贵州茅台": [("600519.SH", "贵州茅台")], "中国移动": AH_MOBILE}
    pair = [row("517180.SH", i + 2, "中国移动", close) for i, close in enumerate(order)]
    rows, _ = _fill([row("517180.SH", 1, "贵州茅台", 1349.98), *pair], _Down(search, {}))
    assert codes_of(rows)[1:] == [None, None]


@pytest.mark.parametrize("order", [[7.2, 13.38], [13.38, 7.2]])
def test_a_longer_hong_kong_name_is_a_market_the_row_could_be_in(order):
    # The H share is listed as 中国石油股份: it never fills the row, but it keeps the ETF's
    # market unknown.
    search = {"中国石油": [("601857.SH", "中国石油"), ("00857.HK", "中国石油股份")]}
    rows, _ = _fill(
        [row("517180.SH", i + 1, "中国石油", close) for i, close in enumerate(order)],
        _Down(search, {}),
    )
    assert codes_of(rows) == [None, None]


HENGRUI_SEARCH = {
    "中国石油": [("601857.SH", "中国石油")],
    "中国神华": [("601088.SH", "中国神华")],
    "华润啤酒": [("00291.HK", "华润啤酒")],
    "腾讯控股": [("00700.HK", "腾讯控股")],
    "恒瑞医药": [("600276.SH", "恒瑞医药"), ("01276.HK", "恒瑞医药")],
}
HENGRUI_PRICES = {
    "601857.SH": [13.0, 13.1],
    "601088.SH": [38.0, 38.1],
    "00291.HK": [19.6, 19.7],
    "00700.HK": [390, 392],
    "600276.SH": [47.1, 47.44],
    "01276.HK": [48.3, 48.5],
}
# The list carries A shares at 10-20 closes and H shares at 10-22's.
HENGRUI_HISTORY = {
    "601857.SH": [("2026-10-20", 13.38), ("2026-10-22", 13.0)],
    "601088.SH": [("2026-10-20", 38.6), ("2026-10-22", 38.0)],
    "00291.HK": [("2026-10-20", 19.0), ("2026-10-22", 19.48)],
    "00700.HK": [("2026-10-20", 380), ("2026-10-22", 385.2)],
    "600276.SH": [("2026-10-20", 46.9), ("2026-10-22", 47.6)],
    "01276.HK": [("2026-10-20", 46.1), ("2026-10-22", 47.44)],
}


def _hengrui() -> list[dict[str, Any]]:
    return _etf517(
        ("中国石油", 13.38),
        ("中国神华", 38.6),
        ("华润啤酒", 19.48),
        ("腾讯控股", 385.2),
        ("恒瑞医药", 47.44),
    )


def test_a_quote_that_agrees_does_not_stand_while_the_other_listing_closed_at_that_price():
    # 恒瑞医药 is the H row (47.44 on 10-22); the A share's latest price is 47.44 by chance.
    rows, _ = _fill(_hengrui(), _Api(HENGRUI_SEARCH, HENGRUI_PRICES, history=HENGRUI_HISTORY))
    assert codes_of(rows) == ["601857.SH", "601088.SH", "00291.HK", "00700.HK", "01276.HK"]
    # Without the H share's closes it cannot be ruled out, and this ETF holds both markets.
    no_h = {k: v for k, v in HENGRUI_HISTORY.items() if k != "01276.HK"}
    rows, _ = _fill(_hengrui(), _Api(HENGRUI_SEARCH, HENGRUI_PRICES, history=no_h))
    assert codes_of(rows)[4] is None


@pytest.mark.anyio
async def test_async_driver_holds_a_quote_to_the_other_listings_closes():
    api = _AsyncApi(_Api(HENGRUI_SEARCH, HENGRUI_PRICES, history=HENGRUI_HISTORY))
    fill = await fill_component_codes_async(_Fill(_hengrui()), api, concurrency=5)
    assert codes_of(fill.result()[0])[4] == "01276.HK"
    down = _AsyncApi(_Down({"贵州茅台": [("600519.SH", "贵州茅台")], "中国移动": AH_MOBILE}, {}))
    rows = [row("517180.SH", 1, "贵州茅台", 1349.98), row("517180.SH", 2, "中国移动", 77.3)]
    fill = await fill_component_codes_async(_Fill(rows), down, concurrency=5)
    assert codes_of(fill.result()[0]) == [None, None]


def test_a_failed_lookup_keeps_a_price_tie_from_the_other_rows_market():
    # 腾讯控股 would have shown the ETF holds Hong Kong stocks, so 招商银行's A/H price tie
    # is not settled for the A share.
    search = {"贵州茅台": [("600519.SH", "贵州茅台")], "招商银行": CMB_TIE["招商银行"]}
    api = _Api(search, CMB_TIE_PRICES, fail_search="腾讯控股")
    rows, _ = _fill(
        [
            row("517180.SH", 1, "贵州茅台", 1349.98),
            row("517180.SH", 2, "腾讯控股", 386.4),
            row("517180.SH", 3, "招商银行", 42.5),
        ],
        api,
    )
    assert codes_of(rows) == ["600519.SH", None, None]


# A row a price narrowed down but could not settle across markets is not filled from the
# market the other rows show: an A+H ETF can hold the H share beside A-only names.
HENGRUI_ALONE_SEARCH = {
    "中国石油": [("601857.SH", "中国石油")],
    "中国神华": [("601088.SH", "中国神华")],
    "恒瑞医药": HENGRUI_SEARCH["恒瑞医药"],
}
HENGRUI_ALONE_PRICES = {
    "601857.SH": [13.2, 13.38],
    "601088.SH": [38.4, 38.6],
    "600276.SH": [47.1, 47.44],
    "01276.HK": [48.3, 48.5],
}


def _hengrui_alone() -> list[dict[str, Any]]:
    return _etf517(("中国石油", 13.38), ("中国神华", 38.6), ("恒瑞医药", 47.44))


@pytest.mark.parametrize(
    "a_closes",
    [[("2026-10-20", 46.9), ("2026-10-22", 47.6)], [("2026-10-22", 47.44)]],
)
def test_a_contested_quote_is_not_filled_from_the_other_rows_market(a_closes):
    # Only A shares are confirmed elsewhere; 恒瑞医药's 47.44 equals the A share's latest
    # price and the H share's recent close.
    history = {"600276.SH": a_closes, "01276.HK": [("2026-10-22", 47.44)]}
    api = _Api(HENGRUI_ALONE_SEARCH, HENGRUI_ALONE_PRICES, history=history)
    rows, unresolved = _fill(_hengrui_alone(), api)
    assert codes_of(rows) == ["601857.SH", "601088.SH", None]
    assert [u["componentName"] for u in unresolved] == ["恒瑞医药"]


@pytest.mark.anyio
async def test_async_driver_does_not_fill_a_contested_quote_from_the_other_rows_market():
    history = {"600276.SH": [("2026-10-22", 47.6)], "01276.HK": [("2026-10-22", 47.44)]}
    api = _AsyncApi(_Api(HENGRUI_ALONE_SEARCH, HENGRUI_ALONE_PRICES, history=history))
    fill = await fill_component_codes_async(_Fill(_hengrui_alone()), api, concurrency=5)
    assert codes_of(fill.result()[0]) == ["601857.SH", "601088.SH", None]


# ---- a row's own change decides between listings its price leaves open (TS v0.51.0) ----

# 招商银行's A share (CNY) and H share (HKD) both closed at 42.5 on 10-27, moving +0.47%
# and -0.23%.
CMB_BARS = {
    "600036.SH": [("2026-10-27", 42.5, 0.4728)],
    "03968.HK": [("2026-10-27", 42.5, -0.2347)],
}
CMB_SEARCH = {**CMB_TIE, "华润啤酒": [("00291.HK", "华润啤酒")]}


def with_change(fund_code: str, serial: int, name: str, close: float, change: float) -> dict:
    return {**row(fund_code, serial, name, close), "pctChange": change}


def _a_only(change: float) -> list[dict[str, Any]]:
    return [
        with_change("510300.SH", 1, "贵州茅台", 1349.98, 1.12),
        with_change("510300.SH", 5, "招商银行", 42.5, change),
    ]


def _a_and_h(change: float) -> list[dict[str, Any]]:
    return [
        with_change("517180.SH", 1, "贵州茅台", 1349.98, 1.12),
        with_change("517180.SH", 2, "华润啤酒", 19.48, -0.61),
        with_change("517180.SH", 3, "招商银行", 42.5, change),
    ]


def test_a_rows_change_settles_a_price_tie_across_markets_also_in_an_etf_holding_both():
    api = _Api(CMB_SEARCH, CMB_TIE_PRICES, history=CMB_BARS)
    assert codes_of(_fill(_a_only(0.4728), api)[0]) == ["600519.SH", "600036.SH"]
    assert codes_of(_fill(_a_and_h(-0.2347), api)[0]) == ["600519.SH", "00291.HK", "03968.HK"]


@pytest.mark.parametrize(("change", "settled"), [(0.9362, "600276.SH"), (2.5065, "01276.HK")])
def test_a_rows_change_settles_a_quote_the_other_markets_close_contested(change, settled):
    # 恒瑞医药's A share quotes 47.44; its H share closed at 47.44 on 10-27, on another change.
    prices = {**HENGRUI_ALONE_PRICES, "600276.SH": [47.44, 47.0], "01276.HK": [52.1, 51.8]}
    history = {
        "600276.SH": [("2026-10-27", 47.44, 0.9362)],
        "01276.HK": [("2026-10-27", 47.44, 2.5065)],
    }
    rows = [
        with_change("510300.SH", 1, "中国石油", 13.38, 1.36),
        with_change("510300.SH", 2, "中国神华", 38.6, 1.05),
        with_change("510300.SH", 3, "恒瑞医药", 47.44, change),
    ]
    filled, unresolved = _fill(rows, _Api(HENGRUI_ALONE_SEARCH, prices, history=history))
    assert codes_of(filled) == ["601857.SH", "601088.SH", settled]
    assert unresolved == []


def test_a_rows_change_decides_nothing_without_every_listings_bars_or_when_it_fits_neither():
    partial = _Api(CMB_SEARCH, CMB_TIE_PRICES, history={"600036.SH": CMB_BARS["600036.SH"]})
    assert codes_of(_fill(_a_and_h(0.4728), partial)[0]) == ["600519.SH", "00291.HK", None]
    api = _Api(CMB_SEARCH, CMB_TIE_PRICES, history=CMB_BARS)
    assert codes_of(_fill(_a_and_h(3.1), api)[0]) == ["600519.SH", "00291.HK", None]


def test_a_listing_whose_day_at_the_rows_close_has_no_change_is_not_ruled_out():
    # The H share closed at 42.5 too, but without a previous close its change is unknown.
    unknown = {"600036.SH": CMB_BARS["600036.SH"], "03968.HK": [("2026-10-27", 42.5)]}
    api = _Api(CMB_SEARCH, CMB_TIE_PRICES, history=unknown)
    assert codes_of(_fill(_a_only(0.4728), api)[0]) == ["600519.SH", None]
    assert codes_of(_fill(_a_and_h(0.4728), api)[0]) == ["600519.SH", "00291.HK", None]
    # A day at another close without a change rules nothing out either way.
    elsewhere = {
        "600036.SH": CMB_BARS["600036.SH"],
        "03968.HK": [("2026-10-24", 41.9), ("2026-10-27", 42.5, -0.2347)],
    }
    api = _Api(CMB_SEARCH, CMB_TIE_PRICES, history=elsewhere)
    assert codes_of(_fill(_a_only(0.4728), api)[0]) == ["600519.SH", "600036.SH"]


@pytest.mark.parametrize("first", [0, 1])
def test_a_change_settled_row_frees_the_other_share_class_whichever_row_comes_first(first):
    # Both 招商银行 rows tie at 42.5 across markets; the A row's change takes the A share,
    # which leaves the H share to the other row — in either row order.
    pair = [
        with_change("517180.SH", 1, "招商银行", 42.5, 0.4728),
        with_change("517180.SH", 2, "招商银行", 42.5, 9.9),
    ]
    if first:
        pair.reverse()
    rows, _ = _fill(pair, _Api(CMB_SEARCH, CMB_TIE_PRICES, history=CMB_BARS))
    by_change = {r["pctChange"]: r["componentCode"] for r in rows}
    assert by_change == {0.4728: "600036.SH", 9.9: "03968.HK"}


@pytest.mark.anyio
async def test_async_driver_settles_a_tie_by_the_rows_change():
    api = _AsyncApi(_Api(CMB_SEARCH, CMB_TIE_PRICES, history=CMB_BARS))
    fill = await fill_component_codes_async(_Fill(_a_and_h(-0.2347)), api, concurrency=5)
    assert codes_of(fill.result()[0]) == ["600519.SH", "00291.HK", "03968.HK"]


# 招商银行's first row (42.5) ties across markets and its change takes the A share. The
# second row's 42.3 equals only the A share's quote, while the H share closed at 42.3 on
# 10-24: with the A share taken, its own change decides — in either row order.
TAKEN_PRICES = {"600036.SH": [42.3, 42.5], "03968.HK": [42.5, 42.6]}
TAKEN_BARS = {
    "600036.SH": [("2026-10-27", 42.5, 0.4728)],
    "03968.HK": [("2026-10-24", 42.3, -1.1), ("2026-10-27", 42.5, -0.2347)],
}


@pytest.mark.parametrize("first", [0, 1])
@pytest.mark.parametrize(("change", "h_row"), [(-1.1, "03968.HK"), (5.0, None)])
def test_a_row_whose_priced_listings_are_all_taken_still_gets_its_changes_say(first, change, h_row):
    pair = [
        with_change("517180.SH", 1, "招商银行", 42.5, 0.4728),
        with_change("517180.SH", 2, "招商银行", 42.3, change),
    ]
    if first:
        pair.reverse()
    rows, _ = _fill(pair, _Api(CMB_SEARCH, TAKEN_PRICES, history=TAKEN_BARS))
    by_close = {r["close"]: r["componentCode"] for r in rows}
    assert by_close == {42.5: "600036.SH", 42.3: h_row}
