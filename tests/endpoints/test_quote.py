import json

import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError
from gangtise_openapi.domains.quote import Quote


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
                start_date="2026-01-01",
                end_date="2026-01-03",
            )
        # 1-day shards x 3 days
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
            pytest.warns(UserWarning, match="1/3 kline shards failed"),
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
                start_date="2026-01-01",
                end_date="2026-01-05",
            )
        # 2-day shards x 5 days -> 3 shards
        assert route.call_count == 3


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
