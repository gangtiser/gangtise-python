import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError, ValidationError
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi.domains.quote import Quote, _normalize_quote_rows


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
                security="all",
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


def test_day_kline_partial_shard_failure_sets_flags(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(
            side_effect=_partial_failure_responder
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.warns(UserWarning, match="1/3 day-kline shards failed"),
        ):
            out = Quote(client).day_kline(
                security="all",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-07",  # Wed
                raw=True,
            )
    # TS quoteSharding parity: surviving shards merge, failure is flagged.
    assert out["partial"] is True
    assert out["failedShards"] == [{"startDate": "2026-01-06", "endDate": "2026-01-06"}]
    assert sorted(row[1] for row in out["list"]) == ["2026-01-05", "2026-01-07"]


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
    # A shard returning 2xx but an unrecognized shape must not silently drop rows:
    # it's counted and the result flagged partial (symmetry with shard failure).
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/open-quote/kline/daily").mock(
            side_effect=_malformed_shard_responder
        )
        with (
            GangtiseClient(_config=_cfg(tmp_path)) as client,
            pytest.warns(UserWarning, match="unexpected shape"),
        ):
            out = Quote(client).day_kline(
                security="all",
                start_date="2026-01-05",  # Mon
                end_date="2026-01-07",  # Wed
                raw=True,
            )
    assert out["partial"] is True
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
                security="all",
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


def test_day_kline_ragged_matrix_rows_fall_back_to_normalize(tmp_path):
    # Ragged rows must NOT take the fast path: the normalize path silently
    # drops extra elements and leaves missing trailing fields as NaN.
    fields = ["securityCode", "tradeDate", "close"]
    rows = [
        ["000001.SH", "2026-01-05", 1.0, "EXTRA"],  # too long -> extra dropped
        ["000002.SZ", "2026-01-05"],  # too short -> close missing
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
    assert list(df.columns) == fields
    assert df.shape == (2, 3)
    assert df.iloc[0]["close"] == 1.0
    assert pd.isna(df.iloc[1]["close"])


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
                security="all",
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
                security="all",
                start_date="2026-01-03",  # Sat
                end_date="2026-01-04",  # Sun
            )
            out = Quote(client).day_kline(
                security="all",
                start_date="2026-01-03",
                end_date="2026-01-04",
                raw=True,
            )
        assert route.call_count == 0
    assert isinstance(df, pd.DataFrame)
    assert df.empty
    assert out == {"list": []}


def test_index_day_kline_30_day_shards(tmp_path):
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
        # 90 days / 30 per shard = 3 shards
        assert route.call_count == 3


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
                    "data": [{"securityCode": "000001.SH", "price": 12.34}],
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
                security="all", start_date="2026-01-05", end_date="2026-01-06"
            )
    assert list(df.columns) == fields
    assert len(df) == 1
    assert df.iloc[0]["close"] == 1.0
