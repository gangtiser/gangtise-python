"""Client-level behaviour ported from CLI v0.40.0-v0.44.0.

- token cache bound to the credentials that minted it (``issuedFor``)
- auth recovery: a token someone else refreshed first, one login last
- ``login()`` reports the identity requests will actually use
- ``confirm=True`` gates: destructive endpoints, the earning-forecast price estimate
- per-item failures inside a 000000 success (``failList``) → partial
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from gangtise_openapi._auth import credential_fingerprint, read_token_cache
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError, ValidationError

BASE = "https://api.test"
LOGIN = "/application/auth/oauth/open/loginV2"
REALTIME = "/application/open-quote/quote/realtime"
FP = credential_fingerprint("ak", BASE)


def _cfg(tmp_path: Path, *, token: str | None = None, access_key: str | None = "ak") -> Config:
    return Config(
        base_url=BASE,
        access_key=access_key,
        secret_key="sk" if access_key else None,
        token=token,
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
        page_concurrency=3,
    )


def _seed(cfg: Config, token: str, issued_for: str | None = FP) -> None:
    payload: dict[str, object] = {
        "accessToken": token,
        "expiresIn": 3600,
        "time": 0,
        "expiresAt": 9999999999,
    }
    if issued_for is not None:
        payload["issuedFor"] = issued_for
    cfg.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_cache_path.write_text(json.dumps(payload))


def _login_response(token: str = "fresh") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": "000000",
            "status": True,
            "data": {"accessToken": token, "expiresIn": 3600, "time": 0, "uid": 1},
        },
    )


def _ok(data: object) -> httpx.Response:
    return httpx.Response(200, json={"code": "000000", "status": True, "data": data})


def _auth_fail() -> httpx.Response:
    return httpx.Response(200, json={"code": "0000001008", "status": False, "msg": "token 失效"})


# ─── token cache ↔ credentials ───


def test_cache_of_other_credentials_is_not_used(tmp_path):
    """TS v0.40.0: swapping GANGTISE_ACCESS_KEY must not keep sending the previous
    account's unexpired token — writes would land on the wrong account."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "other-account", issued_for=credential_fingerprint("another-ak", BASE))
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())
        data = router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert data.calls[0].request.headers["Authorization"] == "Bearer fresh"
    written = read_token_cache(cfg.token_cache_path)
    assert written is not None and written.issued_for == FP


def test_cache_without_fingerprint_is_a_miss_when_credentials_are_set(tmp_path):
    """A cache written before ``issuedFor`` existed has an unknown owner."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "legacy", issued_for=None)
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())
        router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1


def test_cache_without_fingerprint_is_used_when_no_access_key(tmp_path):
    """Without AK there is no second account to confuse it with; refusing the cache
    would only break the token-cache-only workflow."""
    cfg = _cfg(tmp_path, access_key=None)
    _seed(cfg, "legacy", issued_for=None)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN)
        data = router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 0
    assert data.calls[0].request.headers["Authorization"] == "Bearer legacy"


def test_fingerprint_matches_the_cli_digest():
    # sha256("ak1\0https://openapi.gangtise.com")[:16], computed with node's crypto.
    assert credential_fingerprint("ak1", "https://openapi.gangtise.com") == "1dde6c8f82abacc9"


# ─── auth recovery ───


def test_recovery_prefers_a_live_disk_token_before_logging_in(tmp_path):
    """TS v0.44.0: back-to-back logins can end each other's sessions, so a token
    another process already refreshed is tried first (once), then one login."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())

        def data(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer stale":
                # Another process refreshes the shared cache file meanwhile.
                _seed(cfg, "from-other-process")
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 0
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer from-other-process",
    ]


def test_recovery_logs_in_after_an_unproven_token_also_fails(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))

        def data(request: httpx.Request) -> httpx.Response:
            auth = request.headers["Authorization"]
            if auth == "Bearer stale":
                _seed(cfg, "also-dead")
                return _auth_fail()
            if auth == "Bearer also-dead":
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer also-dead",
        "Bearer fresh",
    ]


def test_recovery_stops_when_the_freshly_minted_token_fails_too(tmp_path):
    """No login loop: a token this client's own login minted that is rejected ends
    the recovery."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(return_value=_auth_fail())
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError) as exc:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc.value.code == "0000001008"
    assert login.call_count == 1
    assert route.call_count == 2  # the stale token, then the fresh one — no third try


@pytest.mark.anyio
async def test_async_recovery_prefers_a_live_disk_token_before_logging_in(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())

        def data(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer stale":
                _seed(cfg, "from-other-process")
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        async with AsyncGangtiseClient(_config=cfg) as client:
            await client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 0
    assert route.call_count == 2


@pytest.mark.anyio
async def test_async_recovery_stops_when_the_freshly_minted_token_fails_too(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(return_value=_auth_fail())
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.raises(ApiError):
                await client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert route.call_count == 2


# ─── login() ───


def test_login_with_env_token_reports_it_and_contacts_nothing(tmp_path):
    """TS v0.40.0: GANGTISE_TOKEN wins for every other call, so reporting a freshly
    minted token would name an account no request uses — and a token-only setup (no
    AK/SK) has nothing to log in with."""
    cfg = _cfg(tmp_path, token="env-tok", access_key=None)
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        login = router.post(LOGIN)
        with GangtiseClient(_config=cfg) as client:
            out = client.login()
    assert login.call_count == 0
    assert out == {"authorization": "Bearer env-tok", "cache": None, "source": "env-token"}


def test_login_with_credentials_always_logs_in(tmp_path):
    """A valid cache must not stand in: after a credential swap it would report the
    previous account."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "cached")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))
        with GangtiseClient(_config=cfg) as client:
            out = client.login()
    assert login.call_count == 1
    assert out["source"] == "login"
    assert out["authorization"] == "Bearer fresh"
    assert out["cache"]["access_token"] == "fresh"
    assert out["cache"]["issued_for"] == FP


@pytest.mark.anyio
async def test_async_login_with_env_token_reports_it(tmp_path):
    cfg = _cfg(tmp_path, token="env-tok", access_key=None)
    async with AsyncGangtiseClient(_config=cfg) as client:
        out = await client.login()
    assert out["source"] == "env-token"


# ─── confirm gates ───


def test_destructive_endpoint_refused_without_confirm_and_nothing_sent(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/stock-pool/deletePool")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError) as exc:
            client._call("vault.stock-pool.delete", body={"poolIdList": ["1"]})
    assert route.call_count == 0
    assert "confirm=True" in str(exc.value)
    assert "stock_pool_list" in str(exc.value)
    assert "poolIdList=['1']" in str(exc.value)


def test_destructive_endpoint_passes_with_confirm(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-vault/stock-pool/deletePool").mock(
            return_value=_ok({"successList": ["1"], "failList": []})
        )
        with GangtiseClient(_config=cfg) as client:
            out = client._call("vault.stock-pool.delete", body={"poolIdList": ["1"]}, confirm=True)
    assert route.call_count == 1
    assert "partial" not in out


@pytest.mark.anyio
async def test_async_destructive_endpoint_refused_without_confirm(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/drive/deleteFolder")
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.raises(ValidationError):
                await client._call("vault.drive.delete-folder", body={"folderId": "1"})
    assert route.call_count == 0


def test_earning_forecast_priced_above_guard_is_refused(tmp_path):
    """TS v0.44.0: weekdays x 3 rows x 0.5 credits; ten years ≈ 3900 credits."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    body = {"securityList": ["600519.SH"], "startDate": "2016-01-01", "endDate": "2026-01-01"}
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/earning-forecast")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError) as exc:
            client._call("fundamental.earning-forecast", body=body)
    assert route.call_count == 0
    assert "1000-credit guard" in str(exc.value)


def test_earning_forecast_small_range_or_confirm_goes_through(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        route = router.post("/application/open-fundamental/earning-forecast").mock(
            return_value=_ok({"fieldList": [], "list": []})
        )
        with GangtiseClient(_config=cfg) as client:
            client._call(
                "fundamental.earning-forecast",
                body={"securityList": ["x"], "startDate": "2026-01-01", "endDate": "2026-03-31"},
            )
            client._call(
                "fundamental.earning-forecast",
                body={"securityList": ["x"], "startDate": "2016-01-01", "endDate": "2026-01-01"},
                confirm=True,
            )
    assert route.call_count == 2


def test_earning_forecast_unreadable_date_is_refused_not_priced_at_zero(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-fundamental/earning-forecast")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError) as exc:
            client._call(
                "fundamental.earning-forecast",
                body={"securityList": ["x"], "startDate": "01-07-2026"},
            )
    assert route.call_count == 0
    assert "could not be priced" in str(exc.value)


# ─── per-item failures inside a success ───


def test_fail_list_marks_partial_and_warns(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    data = {
        "successList": [{"securityCode": "600519.SH"}],
        "failList": [{"securityCode": "BAD.XX", "failReason": "证券代码不存在"}],
    }
    with respx.mock(base_url=BASE) as router:
        router.post("/application/open-vault/stock-pool/addStock").mock(return_value=_ok(data))
        with (
            GangtiseClient(_config=cfg) as client,
            pytest.warns(UserWarning, match=r"1 item\(s\) failed.*BAD\.XX（证券代码不存在）"),  # noqa: RUF001
        ):
            out = client._call(
                "vault.stock-pool.add-stock",
                body={"poolId": "1", "securityList": ["600519.SH", "BAD.XX"]},
            )
    assert out["partial"] is True


def test_empty_fail_list_stays_clean(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        router.post("/application/open-vault/stock-pool/addStock").mock(
            return_value=_ok({"successList": [{"securityCode": "600519.SH"}], "failList": []})
        )
        with GangtiseClient(_config=cfg) as client:
            out = client._call(
                "vault.stock-pool.add-stock", body={"poolId": "1", "securityList": ["600519.SH"]}
            )
    assert "partial" not in out


@pytest.mark.anyio
async def test_async_fail_list_marks_partial(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE) as router:
        router.post("/application/open-vault/drive/moveFile").mock(
            return_value=_ok({"successList": [], "failList": [{"fileId": "9"}]})
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            with pytest.warns(UserWarning, match="1 item"):
                out = await client._call(
                    "vault.drive.move-file", body={"fileIdList": ["9"], "folderId": "1"}
                )
    assert out["partial"] is True


def test_call_refuses_a_download_endpoint_before_sending(tmp_path):
    """Through the JSON path a billed download would go out and only then fail to
    parse the file bytes."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.get("/application/open-insight/summary/v2/download/file")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError):
            client._call("insight.summary.download", query={"summaryId": "1"})
    assert route.call_count == 0


@pytest.mark.parametrize("value", ["false", "False", 0, 1, None, "yes"])
def test_confirm_must_be_a_real_bool(tmp_path, value):
    """It releases deletions and >1000-credit fetches: a truthy string from a config
    file must not pass as confirmation (and a falsy non-bool is a bug worth naming)."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/stock-pool/deletePool")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError, match="confirm"):
            client._call("vault.stock-pool.delete", body={"poolIdList": ["1"]}, confirm=value)
    assert route.call_count == 0


def test_call_refuses_an_upload_endpoint_with_a_json_body(tmp_path):
    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        route = router.post("/application/open-vault/drive/uploadFile")
        with GangtiseClient(_config=cfg) as client, pytest.raises(ValidationError, match="upload"):
            client._call("vault.drive.upload", body={"spaceType": 1})
    assert route.call_count == 0


def test_concurrent_first_calls_build_one_http_client(tmp_path):
    """An unguarded lazy init built one client per racing thread."""
    import threading
    import time

    from gangtise_openapi import _client as client_module

    built: list[object] = []
    real = client_module.build_sync_client
    gate = threading.Barrier(8)

    def slow_build(config):
        built.append(config)
        time.sleep(0.05)  # widen the check-then-set window
        return real(config)

    client = GangtiseClient(_config=_cfg(tmp_path, token="tok"))
    orig = client_module.build_sync_client
    client_module.build_sync_client = slow_build
    try:

        def worker():
            gate.wait()
            client._http_client()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        client_module.build_sync_client = orig
        client.close()
    assert len(built) == 1


def test_non_utf8_token_cache_is_a_miss_not_a_crash(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.token_cache_path.write_bytes(b"\xff\xfe\x00garbage")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response())
        router.post(REALTIME).mock(return_value=_ok({"total": 0, "list": []}))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1


def test_corrupt_title_cache_never_costs_the_paid_rows(tmp_path):
    """flush() re-reads the file to merge. A non-UTF-8 file there must not raise: it
    would do so AFTER the (billed) list call succeeded, losing the rows paid for."""
    from gangtise_openapi.domains.insight import Insight

    cfg = _cfg(tmp_path)
    _seed(cfg, "tok")
    cfg.title_cache_path.write_bytes(b"\xff\xfe\x00garbage")
    rows = [{"reportId": "1", "title": "年报"}, {"reportId": "2", "title": "\udc80孤立代理"}]
    with respx.mock(base_url=BASE) as router:
        # The server's JSON escapes a lone surrogate (``\\udc80``); json.loads decodes
        # it back into one, which is what the title cache then has to write.
        payload = {"code": "000000", "status": True, "data": {"total": 2, "list": rows}}
        router.post("/application/open-insight/broker-report/getList").mock(
            return_value=httpx.Response(
                200,
                content=json.dumps(payload).encode(),
                headers={"content-type": "application/json"},
            )
        )
        with GangtiseClient(_config=cfg) as client:
            out = Insight(client).research_list(size=2, raw=True)
    assert [r["reportId"] for r in out["list"]] == ["1", "2"]


def test_no_replay_endpoint_is_replayed_once_after_an_auth_rejection(tmp_path):
    """A rejected token means the request never ran, so even a billed no-replay
    endpoint (ai.one-pager, 50/call) is sent again with the recovered token — once."""
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))

        def one_pager(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer stale":
                return _auth_fail()
            return _ok({"date": "2026-09-30", "content": "x"})

        route = router.post("/application/open-ai/agent/one-pager").mock(side_effect=one_pager)
        with GangtiseClient(_config=cfg) as client:
            out = client._call("ai.one-pager", body={"securityCode": "600519.SH"})
    assert out["content"] == "x"
    assert login.call_count == 1
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer fresh",
    ]


def test_auth_replay_shares_one_transient_retry_budget(tmp_path, monkeypatch):
    """One transient-retry budget across auth replays: 5xx, auth, 5xx, 5xx, 5xx goes
    out 4 times, as in TS — a fresh budget per replay would send it 5 times."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    answers = iter(
        [
            httpx.Response(503, text="busy"),  # retry 1 of 2
            _auth_fail(),  # replay with a recovered token — not a retry
            httpx.Response(503, text="busy"),  # retry 2 of 2
            httpx.Response(503, text="busy"),  # budget spent: surfaces
            _ok({"total": 0, "list": []}),
        ]
    )
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(side_effect=lambda request: next(answers))
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError) as exc:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert exc.value.status_code == 503
    assert route.call_count == 4


def test_auth_code_inside_a_500_is_recovered_at_once_and_keeps_the_budget(tmp_path, monkeypatch):
    """An auth code wrapped in HTTP 500 is recovered at once, as in the CLI. Retried
    as a 500 with the dead token, it would spend the shared budget, and one ordinary
    500 after the recovery would then fail the call."""
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    cfg = _cfg(tmp_path)
    _seed(cfg, "stale")
    auth_500 = httpx.Response(
        500, json={"code": "0000001008", "status": False, "msg": "token 失效"}
    )
    answers = iter([auth_500, httpx.Response(500, text="busy"), _ok({"total": 0, "list": []})])
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_login_response("fresh"))
        route = router.post(REALTIME).mock(side_effect=lambda request: next(answers))
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer stale",
        "Bearer fresh",
        "Bearer fresh",
    ]


def test_login_answer_without_a_token_is_a_named_api_error(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(return_value=_ok({"expiresIn": 3600}))
        with GangtiseClient(_config=cfg) as client, pytest.raises(ApiError, match="accessToken"):
            client.login()


def test_login_answer_with_a_bad_expiry_reads_as_expired(tmp_path):
    cfg = _cfg(tmp_path)
    with respx.mock(base_url=BASE) as router:
        router.post(LOGIN).mock(
            return_value=_ok({"accessToken": "t", "expiresIn": None, "time": "x"})
        )
        with GangtiseClient(_config=cfg) as client:
            out = client.login()
    assert out["cache"]["expires_in"] == 0


@pytest.mark.parametrize("timeout", [0, 0.5, -1, 7200, float("nan"), "30"])
def test_timeout_in_code_is_held_to_the_env_bounds(timeout):
    from gangtise_openapi._errors import ConfigError

    with pytest.raises(ConfigError, match="timeout must be"):
        GangtiseClient(access_key="ak", secret_key="sk", timeout=timeout)


def test_timeout_in_code_inside_the_bounds_is_kept():
    assert GangtiseClient(access_key="ak", secret_key="sk", timeout=45).config.timeout_ms == 45_000


def test_an_env_token_with_a_bearer_prefix_is_the_same_token(tmp_path):
    """``GANGTISE_TOKEN="Bearer x"`` and a cached ``x`` are one token: a rejected one must
    not be "replayed" as if it were a different, unproven token."""
    cfg = Config(
        base_url=BASE,
        access_key="ak",
        secret_key="sk",
        token="Bearer dead",
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
    )
    _seed(cfg, "dead")
    with respx.mock(base_url=BASE) as router:
        login = router.post(LOGIN).mock(return_value=_login_response("fresh"))

        def data(request):
            if request.headers["Authorization"] == "Bearer dead":
                return _auth_fail()
            return _ok({"total": 0, "list": []})

        route = router.post(REALTIME).mock(side_effect=data)
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
    assert login.call_count == 1
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer dead",
        "Bearer fresh",
    ]
