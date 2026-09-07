import json
from dataclasses import replace

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains.quote import Quote, _finalize_quote_result, _normalize_quote_rows


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        page_concurrency=2,
    )


def test_day_kline_single_security(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {"securityCode": "000001.SH", "date": "2026-01-02", "close": 12.3},
                        ]
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).day_kline(security="000001.SH")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["close"] == 12.3


def test_day_kline_single_security_with_dates_does_not_shard(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline(
                security="000001.SH",
                start_date="2026-01-01",
                end_date="2026-12-31",  # 1 year range - would be 365 shards if mis-fired
            )
        assert route.call_count == 1


def test_day_kline_all_market_injects_limit_10000(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-02",
                end_date="2026-01-02",
            )
        body = route.calls.last.request.read()
        assert b'"limit":10000' in body.replace(b" ", b"")


def test_day_kline_us_shard_count(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline-us/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline_us(
                security="all",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-07",  # Wed
            )
        # 1-day shards x 3 weekdays
        assert route.call_count == 3


def _partial_failure_responder(request):
    """Mon-Wed shards: the Tuesday shard fails with a business error."""
    body = json.loads(request.read())
    if body["startDate"] == "2026-01-06":
        return httpx.Response(200, json={"code": "100001", "status": False, "msg": "boom"})
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "tradeDate", "close"],
                "list": [["000001.SH", body["startDate"], 1.0]],
            },
        },
    )


def test_day_kline_partial_shard_failure_aborts_and_sets_flags(tmp_path):
    # TS v0.27.0 parity: the Tuesday hard error aborts the fan-out, so Wednesday
    # is never fetched and lands in failedShards too. page_concurrency=1 makes
    # the dispatch order deterministic (Mon -> Tue -> Wed).
    cfg = replace(_cfg(tmp_path), page_concurrency=1)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            side_effect=_partial_failure_responder
        )
        with (
            GangtiseClient(_config=cfg) as client,
            pytest.warns(UserWarning, match="2/3 day-kline shards failed"),
        ):
            out = Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-07",  # Wed
                raw=True,
            )
        # Only Mon and Tue were requested; Wed was skipped after the hard error.
        assert route.call_count == 2
    assert out["partial"] is True
    assert out["failedShards"] == [
        {"startDate": "2026-01-06", "endDate": "2026-01-06"},
        {"startDate": "2026-01-07", "endDate": "2026-01-07"},
    ]
    assert sorted(row[1] for row in out["list"]) == ["2026-01-05"]


def _malformed_shard_responder(request):
    """Mon-Wed shards: the Tuesday shard returns 2xx but malformed (non-list) data."""
    body = json.loads(request.read())
    if body["startDate"] == "2026-01-06":
        return httpx.Response(
            200, json={"code": "000000", "status": True, "data": {"unexpected": "shape"}}
        )
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "tradeDate", "close"],
                "list": [["000001.SH", body["startDate"], 1.0]],
            },
        },
    )


def test_day_kline_malformed_shard_response_sets_partial(tmp_path):
    # A shard returning 2xx but an unrecognized shape is recorded in failedShards
    # with its window (TS v0.27.0) — but unlike a hard error it does NOT abort
    # the fan-out, so the other shards still merge.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(
            side_effect=_malformed_shard_responder
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.warns(UserWarning, match="1/3 day-kline shards failed"),
        ):
            out = Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-07",  # Wed
                raw=True,
            )
    assert out["partial"] is True
    assert out["failedShards"] == [{"startDate": "2026-01-06", "endDate": "2026-01-06"}]
    # the two well-formed shards still merged
    assert sorted(row[1] for row in out["list"]) == ["2026-01-05", "2026-01-07"]


def test_day_kline_all_shards_failed_raises_api_error(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "100001", "status": False, "msg": "boom"}
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(ApiError) as excinfo,
        ):
            Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-06",  # Tue
            )
    assert excinfo.value.code == "100001"


def test_day_kline_us_matrix_rows_are_normalized(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline-us/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "fieldList": [
                            "securityCode",
                            "tradeDate",
                            "open",
                            "high",
                            "low",
                            "close",
                            "preClose",
                            "pctChange",
                            "volume",
                            "amount",
                        ],
                        "list": [
                            [
                                "AAPL.O",
                                "2026-05-01",
                                278.855,
                                287.22,
                                278.37,
                                280.14,
                                271.35,
                                3.2394,
                                79915442,
                                22562318199.3578,
                            ],
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).day_kline_us(security="AAPL.O")
    # Columns are the REAL fieldList names verbatim (no date/changePct aliasing).
    assert list(df.columns) == [
        "securityCode",
        "tradeDate",
        "open",
        "high",
        "low",
        "close",
        "preClose",
        "pctChange",
        "volume",
        "amount",
    ]
    assert df.iloc[0]["securityCode"] == "AAPL.O"
    assert df.iloc[0]["tradeDate"] == "2026-05-01"
    assert df.iloc[0]["close"] == 280.14
    assert df.iloc[0]["pctChange"] == 3.2394


def test_day_kline_matrix_fast_path_matches_normalize_path(tmp_path):
    # The direct pd.DataFrame(matrix, columns=fieldList) fast path must be
    # byte-for-byte equivalent to the dict-per-row normalize path.
    fields = ["securityCode", "tradeDate", "open", "close", "volume"]
    rows = [
        ["000001.SH", "2026-01-05", 10.0, 10.5, 1000],
        ["000002.SZ", "2026-01-05", 5.0, 5.2, 2000],
    ]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"fieldList": fields, "list": rows},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).day_kline(security=["000001.SH", "000002.SZ"])
    expected = to_dataframe(_normalize_quote_rows(rows, fields), schema=None)
    pd.testing.assert_frame_equal(df, expected)
    assert list(df.columns) == fields


def test_day_kline_ragged_matrix_rows_are_refused(tmp_path):
    # Ragged rows used to fall back to the normalize path, which padded the short
    # row and dropped the extra value — a silently mis-columned table. Since
    # v0.28.3 a length disagreement with fieldList is a hard failure instead.
    fields = ["securityCode", "tradeDate", "close"]
    rows = [
        ["000001.SH", "2026-01-05", 1.0, "EXTRA"],
        ["000002.SZ", "2026-01-05"],
    ]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"fieldList": fields, "list": rows},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="响应字段数与 fieldList 不匹配"):
                Quote(client).day_kline(security=["000001.SH", "000002.SZ"])


def test_day_kline_duplicate_fields_are_refused(tmp_path):
    # Duplicate fieldList must NOT take the fast path (pd.DataFrame(columns=fields)
    # would emit two same-named columns) AND must not be quietly collapsed on the
    # normalize path either: through v0.3.1 the pair became one column holding the
    # LAST value, so `close` read 2.0 with the real 1.0 gone, exit 0. Refused since
    # v0.4.0 (TS v0.38.0 assertColumnarHeader).
    fields = ["securityCode", "close", "close"]
    rows = [["000001.SH", 1.0, 2.0], ["000002.SZ", 3.0, 4.0]]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"fieldList": fields, "list": rows},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="重复列名"):
                Quote(client).day_kline(security=["000001.SH", "000002.SZ"])


def test_day_kline_hk_shard_count(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline-hk/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline_hk(
                security="all",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-09",  # Fri
            )
        # 2-day shards x 5 weekdays -> 3 shards
        assert route.call_count == 3


def test_day_kline_shards_skip_all_weekend_windows(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-01",  # Thu
                end_date="2026-01-05",  # Mon
            )
        # 5 daily shards, Sat 01-03 + Sun 01-04 skipped -> 3 requests
        assert route.call_count == 3
        sent_dates = sorted(json.loads(call.request.read())["startDate"] for call in route.calls)
        assert sent_dates == ["2026-01-01", "2026-01-02", "2026-01-05"]


def test_day_kline_all_weekend_range_makes_no_requests(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-03",  # Sat
                end_date="2026-01-04",  # Sun
            )
            out = Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-03",
                end_date="2026-01-04",
                raw=True,
            )
        assert route.call_count == 0
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert out == {"list": []}


def test_index_day_kline_15_day_shards(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/index/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).index_day_kline(
                security="all",
                start_date="2026-01-01",
                end_date="2026-03-31",
            )
        # 90 days / 15 per shard = 6 shards. 30-day windows (~22 trading days x 531
        # index rows) blew past the 10000-row cap and lost ~11% of the range.
        assert route.call_count == 6


def test_index_day_kline_passes_through_security_name(tmp_path):
    # index-day-kline returns a list of dicts (not a columnar matrix); the v0.1.3
    # dynamic-schema path keeps every field the API sends, so the added
    # `securityName` column flows through with no wrapper change. Lock that.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/index/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [
                            {
                                "securityCode": "000001.SH",
                                "securityName": "上证指数",
                                "tradeDate": "2026-05-26",
                                "close": 4145.373,
                            }
                        ],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            # Single security + dates does NOT shard, so exactly one call is made.
            df = Quote(client).index_day_kline(
                security="000001.SH",
                start_date="2026-05-26",
                end_date="2026-05-26",
            )
    assert "securityName" in df.columns
    assert df.iloc[0]["securityName"] == "上证指数"


def test_minute_kline(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/minute").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "list": [
                            {
                                "securityCode": "000001.SH",
                                "datetime": "2026-01-02 10:00:00",
                                "close": 12.3,
                            },
                        ]
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).minute_kline(security="000001.SH")
        # minute-kline body uses `securityCode` (singular), not `securityList`
        sent = route.calls.last.request.read()
        assert b'"securityCode":"000001.SH"' in sent.replace(b" ", b"")
    assert df.iloc[0]["close"] == 12.3


def test_realtime(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "list": [{"securityCode": "000001.SH", "price": 12.34}],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).realtime(security=["000001.SH"])
    assert df.iloc[0]["price"] == 12.34


def test_fund_flow_single_security_body_and_default_limit(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/fund-flow/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "fieldList": ["securityCode", "tradeDate", "mainNetInflow"],
                        "list": [["600519.SH", "2026-06-03", 1234.5]],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).fund_flow(
                security="600519.SH",
                start_date="2026-06-01",
                end_date="2026-06-05",
                field="mainNetInflow",
            )
        body = json.loads(route.calls.last.request.read())
        assert body == {
            "securityList": ["600519.SH"],
            "startDate": "2026-06-01",
            "endDate": "2026-06-05",
            "limit": 6000,  # DEFAULT_QUOTE_LIMIT injected when --limit is omitted
            "fieldList": ["mainNetInflow"],
        }
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["mainNetInflow"] == 1234.5


def test_fund_flow_ashares_shards_by_day_with_lifted_limit(tmp_path):
    # aShares full market date-shards into one request per calendar day (shardDays=1),
    # each with the lifted 10000-row cap — same mechanism as `--security all` kline.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/fund-flow/daily").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).fund_flow(
                security="aShares",
                start_date="2026-06-29",  # Mon
                end_date="2026-07-01",  # Wed
            )
    assert route.call_count == 3  # 3 weekdays -> 3 per-day shards
    body = json.loads(route.calls[0].request.read())
    assert body["limit"] == 10000  # full-market lift, not the 6000 default


def test_fund_flow_ashares_without_dates_rejected_locally(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/fund-flow/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.raises(ValidationError, match="requires both start_date and end_date"),
        ):
            Quote(client).fund_flow(security="aShares")
    assert route.call_count == 0  # rejected up front, no doomed full-market request


def test_fund_flow_single_security_flags_partial_on_truncation(tmp_path):
    # Single-security fund-flow reports `total` as the returned count, so rows == the sent
    # limit is the only truncation signal: flag partial (raw) + warn.
    rows = [["600519.SH", "2026-06-03", i] for i in range(3)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/fund-flow/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 3,
                        "fieldList": ["securityCode", "tradeDate", "mainNetInflow"],
                        "list": rows,
                    },
                },
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.warns(UserWarning, match="fund-flow returned 3 rows"),
        ):
            out = Quote(client).fund_flow(
                security="600519.SH",
                start_date="2026-06-03",
                end_date="2026-06-03",
                limit=3,
                raw=True,
            )
    assert out["partial"] is True


def test_minute_kline_flags_partial_on_truncation(tmp_path):
    rows = [{"securityCode": "000001.SH", "datetime": f"2026-01-02 10:0{i}:00"} for i in range(3)]
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/minute").mock(
            return_value=httpx.Response(
                200,
                json={"code": "000000", "status": True, "data": {"total": 3, "list": rows}},
            )
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.warns(UserWarning, match="minute-kline returned 3 rows"),
        ):
            out = Quote(client).minute_kline(security="000001.SH", limit=3, raw=True)
    assert out["partial"] is True


def test_day_kline_rejects_out_of_range_limit(tmp_path):
    # limit must be 1..10000 (TS parity). <=0 would also make the truncation check fire
    # spuriously; >10000 exceeds the server cap. Rejected locally, no request sent.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            for bad in (0, -1, 10001):
                with pytest.raises(ValidationError, match="between 1 and 10000"):
                    Quote(client).day_kline(security="000001.SZ", limit=bad)
    assert route.call_count == 0


def test_minute_kline_rejects_out_of_range_limit(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/minute").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            for bad in (0, 10001):
                with pytest.raises(ValidationError, match="between 1 and 10000"):
                    Quote(client).minute_kline(security="000001.SZ", limit=bad)
    assert route.call_count == 0


def test_day_kline_rejects_non_int_limit(tmp_path):
    # The guard mirrors the CLI integer validation: a float (1.5), a bool (True, an int
    # subclass), or a string ("10") must raise ValidationError — not slip past the range
    # check (1.5 / True) or leak a raw TypeError from the comparison ("10").
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}}
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            for bad in (1.5, True, "10"):
                with pytest.raises(ValidationError, match="integer between 1 and 10000"):
                    Quote(client).day_kline(security="000001.SZ", limit=bad)
    assert route.call_count == 0


def test_day_kline_shard_merge_keeps_first_fieldList(tmp_path):
    # A later shard returning an empty fieldList must NOT blank the columns and drop the
    # rows merged from earlier shards — the merge keeps the first non-empty fieldList
    # (TS parity). Without the fix, _kline_dataframe gets fields=[] and drops every row.
    fields = ["securityCode", "tradeDate", "close"]

    def responder(request):
        body = json.loads(request.read())
        if body["startDate"] == "2026-01-05":  # Mon: real data + fieldList
            return httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"fieldList": fields, "list": [["000001.SH", "2026-01-05", 1.0]]},
                },
            )
        # Tue (later shard): empty result carrying an EMPTY fieldList
        return httpx.Response(
            200, json={"code": "000000", "status": True, "data": {"fieldList": [], "list": []}}
        )

    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).day_kline(
                security="aShares", start_date="2026-01-05", end_date="2026-01-06"
            )
    assert list(df.columns) == fields
    assert len(df) == 1
    assert df.iloc[0]["close"] == 1.0


def test_day_kline_truncated_shard_windows_in_payload(tmp_path):
    # TS v0.27.0: record WHICH windows maxed out (truncatedShards), not just a
    # count — a consumer needs the concrete date ranges to re-pull narrower.
    def responder(request):
        body = json.loads(request.read())
        rows = [["000001.SH", body["startDate"], 1.0]]
        if body["startDate"] == "2026-01-06":
            rows = rows * body["limit"]  # exactly at the per-shard cap
        return httpx.Response(
            200,
            json={
                "code": "000000",
                "status": True,
                "data": {
                    "fieldList": ["securityCode", "tradeDate", "close"],
                    "list": rows,
                },
            },
        )

    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.warns(UserWarning, match="see truncatedShards"),
        ):
            out = Quote(client).day_kline(
                security="aShares",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-07",  # Wed
                raw=True,
            )
    assert out["partial"] is True
    assert out["truncatedShards"] == [{"startDate": "2026-01-06", "endDate": "2026-01-06"}]
    assert "failedShards" not in out


def test_realtime_column_mismatch_message_carries_the_trace_id(tmp_path):
    # realtime is the guard's HEADLINE case (a turnover rate landing under `close`),
    # so this path in particular must stay traceable — it was the call site the
    # traceId wiring originally missed.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "traceId": "830965044897325056",
                    "data": {
                        "fieldList": ["securityCode", "close", "turnoverRate"],
                        "list": [["600519.SH", 28.5573]],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="trace 830965044897325056"):
                Quote(client).realtime(
                    security="600519.SH", field=["securityCode", "close", "turnoverRate"]
                )


def test_day_kline_column_mismatch_keeps_the_trace_on_a_single_request(tmp_path):
    # The K-line path rebuilds its payload from the merged shards, which dropped the
    # envelope traceId — the wiring was in place but inert. A single (unsharded)
    # request has exactly one trace, so it can be carried honestly.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "traceId": "830965044897325056",
                    "data": {
                        "fieldList": ["securityCode", "tradeDate", "close"],
                        "list": [["600519.SH", "2026-01-05"]],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ValidationError, match="trace 830965044897325056"):
                Quote(client).day_kline(security="600519.SH")


def test_sharded_kline_does_not_claim_a_single_trace(tmp_path):
    # Merging N shards means merging N responses with N traceIds; picking one would
    # be a fabricated attribution, so the merged payload carries none.
    from gangtise_openapi._transport import unwrap_envelope

    sources = [
        unwrap_envelope(
            {
                "code": "000000",
                "status": True,
                "traceId": f"trace-{i}",
                "data": {"fieldList": ["a"], "list": [[i]]},
            }
        )
        for i in range(2)
    ]
    payload, _rows = _finalize_quote_result(
        sources,
        label="day-kline",
        limit=6000,
        sharded=True,
        shard_count=2,
        failed_shards=[],
        shards=None,
    )
    assert getattr(payload, "envelope_trace_id", None) is None


# ─── v0.4.0: response-shape guards + per-security fan-out (TS v0.37/v0.38) ───


def test_quote_endpoint_without_a_list_payload_is_refused_with_its_trace(tmp_path):
    """`data: null` on a quote endpoint is a BROKEN response, not an empty one.

    Every legitimate answer — an empty date range, an unknown code — is
    `{total: 0, list: []}` (probed live on all seven, 2026-09-07). Without the
    `expects="list"` guard the normalizers hand `None` back and the caller reads
    "no data". Checked at the transport so the envelope's traceId is still in hand:
    `None` has nowhere to carry it, so a check further down would report the
    failure trace-less.
    """
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "traceId": "830965044897325056",
                    "data": None,
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.raises(ApiError, match="returned no list payload") as excinfo:
                Quote(client).day_kline(security="000001.SH")
    assert excinfo.value.structural is True
    assert excinfo.value.trace_id == "830965044897325056"


def test_day_kline_flags_a_field_the_server_never_returned(tmp_path):
    """A `field=` name the server does not recognise is dropped NAME AND VALUE —
    HTTP 200, no error, one column simply absent. The SDK knows what was asked for,
    so the gap becomes `partial` + `missingFields` (TS v0.38.0)."""
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "fieldList": ["securityCode", "latestPrice"],
                        "list": [["600519.SH", 1297.41]],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="returned no column for turnoverRate"):
                out = Quote(client).realtime(
                    security="600519.SH",
                    field=["securityCode", "latestPrice", "turnoverRate"],
                    raw=True,
                )
    assert out["partial"] is True
    assert out["missingFields"] == ["turnoverRate"]


def test_realtime_does_not_flag_columns_the_server_volunteered(tmp_path):
    # Only "asked for but not returned" is judged — extras are fine, so the guard
    # needs no field whitelist and cannot go stale.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "fieldList": ["securityCode", "latestPrice", "tradeStatus"],
                        "list": [["600519.SH", 1297.41, "交易中"]],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            out = Quote(client).realtime(
                security="600519.SH", field=["securityCode", "latestPrice"], raw=True
            )
    assert "partial" not in out
    assert "missingFields" not in out


def test_minute_kline_fans_out_over_several_securities(tmp_path):
    """The API takes ONE securityCode per request; several go out concurrently and
    merge in input order (TS v0.38.0 repeatable --security)."""
    bodies = []

    def responder(request):
        body = json.loads(request.content)
        bodies.append(body["securityCode"])
        return httpx.Response(
            200,
            json={
                "code": "000000",
                "status": True,
                "data": {
                    "total": 1,
                    "fieldList": ["securityCode", "close"],
                    "list": [[body["securityCode"], 1.0]],
                },
            },
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/minute").mock(side_effect=responder)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).minute_kline(security=["600519.SH", "000001.SZ"])
    assert sorted(bodies) == ["000001.SZ", "600519.SH"]
    # Merged in INPUT order, not completion order.
    assert df["securityCode"].tolist() == ["600519.SH", "000001.SZ"]


def test_minute_kline_requires_a_security(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
        with pytest.raises(ValidationError, match="security is required"):
            Quote(client).minute_kline(security=[])


def test_day_kline_batches_per_security_when_the_range_would_not_fit(tmp_path):
    """securities x trading days over the limit → one request each.

    One request naming N securities comes back capped at `limit` with the TAIL
    SECURITIES MISSING ENTIRELY (rows fill in order), so the truncation eats whole
    securities rather than trimming each (TS v0.38.0).
    """
    sent = []

    def responder(request):
        body = json.loads(request.content)
        sent.append(body["securityList"])
        return httpx.Response(
            200,
            json={
                "code": "000000",
                "status": True,
                "data": {
                    "total": 1,
                    "fieldList": ["securityCode", "close"],
                    "list": [[body["securityList"][0], 1.0]],
                },
            },
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            # 3 securities x 262 default weekdays = 786 > limit 100.
            df = Quote(client).day_kline(security=["600519.SH", "000001.SZ", "00700.HK"], limit=100)
    assert sorted(sent) == [["000001.SZ"], ["00700.HK"], ["600519.SH"]]
    assert df["securityCode"].tolist() == ["600519.SH", "000001.SZ", "00700.HK"]


def test_day_kline_keeps_one_request_when_the_range_fits(tmp_path):
    # The split must not fire on a short window: 3 securities x 5 weekdays = 15,
    # well under the 6000 default, so one request is still correct and cheaper.
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"total": 0, "fieldList": ["securityCode"], "list": []},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline(
                security=["600519.SH", "000001.SZ", "00700.HK"],
                start_date="2026-09-07",
                end_date="2026-09-11",
            )
    assert route.call_count == 1


def _shard(rows, fields=None, **extra):
    out = {"total": len(rows), "list": rows}
    if fields is not None:
        out["fieldList"] = fields
    out.update(extra)
    return out


def _windows(n):
    import datetime as dt

    return [(dt.date(2026, 1, d), dt.date(2026, 1, d)) for d in range(1, n + 1)]


def test_shard_merge_realigns_a_shard_whose_columns_are_reordered():
    """The merged result carries ONE fieldList and rows are read against it by
    position, so a shard ordering its columns differently would land `close` under
    `volume` with nothing in the payload to notice (TS v0.38.0 columnRemap)."""
    shards = _windows(2)
    results = [
        _shard([["a", 1, 10]], ["securityCode", "close", "volume"]),
        _shard([["b", 20, 2]], ["securityCode", "volume", "close"]),
    ]
    failed = []
    out, rows = _finalize_quote_result(
        results,
        label="day-kline",
        limit=6000,
        sharded=True,
        shard_count=2,
        failed_shards=failed,
        shards=shards,
    )
    assert out["fieldList"] == ["securityCode", "close", "volume"]
    assert rows == [["a", 1, 10], ["b", 2, 20]]  # second shard re-ordered, not mis-read
    assert failed == []
    assert "partial" not in out


def test_shard_merge_drops_a_shard_missing_a_header_column():
    shards = _windows(2)
    results = [
        _shard([["a", 1, 10]], ["securityCode", "close", "volume"]),
        _shard([["b", 2]], ["securityCode", "close"]),
    ]
    failed = []
    with pytest.warns(UserWarning) as record:
        out, rows = _finalize_quote_result(
            results,
            label="day-kline",
            limit=6000,
            sharded=True,
            shard_count=2,
            failed_shards=failed,
            shards=shards,
        )
    assert any("cannot be aligned" in str(w.message) for w in record)
    assert rows == [["a", 1, 10]]
    assert out["partial"] is True
    assert failed == [shards[1]]


def test_shard_merge_treats_an_empty_shard_claiming_rows_as_failed():
    # total > 0 with no rows is a contradiction, not a holiday.
    shards = _windows(2)
    results = [_shard([["a", 1]], ["securityCode", "close"]), _shard([], total_override=None)]
    results[1]["total"] = 5
    failed = []
    with pytest.warns(UserWarning) as record:
        out, rows = _finalize_quote_result(
            results,
            label="day-kline",
            limit=6000,
            sharded=True,
            shard_count=2,
            failed_shards=failed,
            shards=shards,
        )
    assert any("reported total=5 but delivered no rows" in str(w.message) for w in record)
    assert rows == [["a", 1]]
    assert out["partial"] is True
    assert failed == [shards[1]]


def test_shard_merge_accepts_a_genuinely_empty_window():
    # A weekend / holiday shard is a real answer: not failed, and it must NOT supply
    # the merged header (an empty fieldList would swallow every later column).
    shards = _windows(2)
    results = [_shard([], []), _shard([["a", 1]], ["securityCode", "close"])]
    failed = []
    out, rows = _finalize_quote_result(
        results,
        label="day-kline",
        limit=6000,
        sharded=True,
        shard_count=2,
        failed_shards=failed,
        shards=shards,
    )
    assert out["fieldList"] == ["securityCode", "close"]
    assert rows == [["a", 1]]
    assert failed == []
    assert "partial" not in out


def test_shard_merge_drops_a_shard_whose_rows_do_not_match_its_own_field_list():
    shards = _windows(2)
    results = [
        _shard([["a", 1]], ["securityCode", "close"]),
        _shard([["b", 2, 3]], ["securityCode", "close"]),  # mis-sized row
    ]
    failed = []
    with pytest.warns(UserWarning) as record:
        out, rows = _finalize_quote_result(
            results,
            label="day-kline",
            limit=6000,
            sharded=True,
            shard_count=2,
            failed_shards=failed,
            shards=shards,
        )
    assert any("do not match its own fieldList" in str(w.message) for w in record)
    assert rows == [["a", 1]]
    assert failed == [shards[1]]
    assert out["partial"] is True


def test_shard_merge_carries_a_shards_own_partial_marker():
    # Only the header shard's metadata survives the merge, so the marker has to be
    # carried across or the merged result reads as complete.
    shards = _windows(2)
    results = [
        _shard([["a", 1]], ["securityCode", "close"]),
        _shard([["b", 2]], ["securityCode", "close"], partial=True),
    ]
    failed = []
    with pytest.warns(UserWarning) as record:
        out, _rows = _finalize_quote_result(
            results,
            label="day-kline",
            limit=6000,
            sharded=True,
            shard_count=2,
            failed_shards=failed,
            shards=shards,
        )
    assert any("reported themselves partial" in str(w.message) for w in record)
    assert out["partial"] is True
    assert failed == []


@pytest.mark.parametrize("layout", ["2016-01-01", "2016/01/01", "20160101"])
def test_day_kline_split_decision_does_not_depend_on_date_layout(tmp_path, layout):
    """All three accepted year-first layouts are the same day, so they must produce
    the same number of requests.

    They did not: the per-security size estimate ran BEFORE `_request_body`
    normalized the dates, and `date.fromisoformat` takes only `YYYY-MM-DD` (and
    `20160101` only on Python 3.11+). The other layouts fell through to the
    one-year default, so a legal ten-year, three-security request measured 786 rows
    against the 6000 limit, skipped the split, and came back capped — with the tail
    securities missing entirely and nothing in the payload saying so.
    """
    end = layout.replace("2016", "2026")

    def responder(request):
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": "000000",
                "status": True,
                "data": {
                    "total": 1,
                    "fieldList": ["securityCode", "close"],
                    "list": [[body["securityList"][0], 1.0]],
                },
            },
        )

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(side_effect=responder)
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).day_kline(
                security=["600519.SH", "000001.SZ", "00700.HK"],
                start_date=layout,
                end_date=end,
            )
    # 3 securities x ~2610 weekdays = ~7830 > the 6000 default -> one request each.
    assert route.call_count == 3
    assert df["securityCode"].tolist() == ["600519.SH", "000001.SZ", "00700.HK"]
    # And the dates actually sent are normalized, whatever the caller typed.
    for call in route.calls:
        body = json.loads(call.request.content)
        assert body["startDate"] == "2016-01-01"
        assert body["endDate"] == "2026-01-01"


@pytest.mark.parametrize(
    ("path", "call"),
    [
        ("/application/open-quote/quote/realtime", lambda q: q.realtime(security="600519.SH")),
        ("/application/open-quote/kline/minute", lambda q: q.minute_kline(security="600519.SH")),
        ("/application/open-quote/kline/daily", lambda q: q.day_kline(security="600519.SH")),
        ("/application/open-quote/fund-flow/daily", lambda q: q.fund_flow(security="600519.SH")),
    ],
)
def test_a_server_set_partial_marker_is_announced_on_single_request_paths(tmp_path, path, call):
    """Markers the SDK sets are announced where they are set; one the SERVER set was not.

    It rode into the result dict and then vanished on the default return path — a
    DataFrame, which carries none of these keys — so a caller who never passes
    `raw=True` saw a frame that looked complete.
    """
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post(path).mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "total": 1,
                        "partial": True,
                        "fieldList": ["securityCode", "close"],
                        "list": [["600519.SH", 1.0]],
                    },
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:  # noqa: SIM117
            with pytest.warns(UserWarning, match="marked this response partial"):
                call(Quote(client))
