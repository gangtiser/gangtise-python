from dataclasses import replace

import httpx
import pytest

from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef, RetryPolicy
from gangtise_openapi._errors import EDE_NO_DATA_HINT, NO_REPLAY_UNCERTAIN_HINT, ApiError
from gangtise_openapi._transport import (
    RETRY_AFTER_CEILING_MS,
    RETRYABLE_API_CODES,
    RETRYABLE_HTTP_STATUS,
    TERMINAL_API_CODES,
    _effective_timeout,
    _retry_delay,
    build_sync_client,
    is_retryable_error,
    is_transient_error,
    parse_retry_after_ms,
    request_json,
    unwrap_envelope,
)


def _endpoint(
    path: str = "/p",
    retry: RetryPolicy = "default",
    timeout_ms: int | None = None,
) -> EndpointDef:
    return EndpointDef(
        key="x",
        method="POST",
        path=path,
        kind="json",
        description="d",
        retry=retry,
        timeout_ms=timeout_ms,
    )


def test_retryable_http_status_set():
    assert {429, 500, 502, 503, 504} == set(RETRYABLE_HTTP_STATUS)


def test_retryable_api_codes_set():
    assert "999999" in RETRYABLE_API_CODES


def test_unwrap_success():
    out = unwrap_envelope({"code": "000000", "status": True, "data": {"x": 1}})
    assert out == {"x": 1}


def test_unwrap_success_via_success_field():
    out = unwrap_envelope({"code": "000001", "success": True, "data": [1, 2]})
    assert out == [1, 2]


def test_unwrap_failure_raises():
    with pytest.raises(ApiError) as exc:
        unwrap_envelope({"code": "999997", "status": False, "msg": "no perm"})
    assert exc.value.code == "999997"


def test_unwrap_non_envelope_passthrough():
    # The TS client treats non-envelope payloads as the actual data.
    out = unwrap_envelope([1, 2, 3])
    assert out == [1, 2, 3]


def test_is_retryable_classifies_5xx():
    assert is_retryable_error(ApiError("boom", code=None, status_code=503))


def test_is_retryable_classifies_429():
    assert is_retryable_error(ApiError("boom", code=None, status_code=429))


def test_is_retryable_classifies_999999():
    assert is_retryable_error(ApiError("boom", code="999999"))


def test_is_retryable_rejects_other_api_codes():
    assert not is_retryable_error(ApiError("perm", code="999997", status_code=403))


def test_is_retryable_classifies_httpx_read_timeout():
    assert is_retryable_error(httpx.ReadTimeout("timeout"))


def test_is_retryable_classifies_httpx_connect_error():
    assert is_retryable_error(httpx.ConnectError("nope"))


def test_request_json_success(respx_mock, config: Config):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 1}})
    )
    with build_sync_client(config) as http:
        out = request_json(http, _endpoint("/p"), body={"k": "v"}, token="tok")
    assert out == {"v": 1}


def test_request_json_envelope_error_raises(respx_mock, config: Config):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "999997", "status": False, "msg": "no perm"})
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, _endpoint("/p"), body={}, token="tok")
    assert exc.value.code == "999997"


def test_request_json_http_500_retries_then_succeeds(respx_mock, config: Config):
    route = respx_mock.post("/p").mock(
        side_effect=[
            httpx.Response(500, json={"code": "500", "status": False, "msg": "boom"}),
            httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 2}}),
        ]
    )
    with build_sync_client(config) as http:
        out = request_json(http, _endpoint("/p"), body={}, token="tok")
    assert out == {"v": 2}
    assert route.call_count == 2


def test_request_json_http_500_exhausts_retries_raises(respx_mock, config: Config):
    respx_mock.post("/p").mock(return_value=httpx.Response(500, text="oops"))
    with build_sync_client(config) as http, pytest.raises(ApiError):
        request_json(http, _endpoint("/p"), body={}, token="tok")


def test_request_json_attaches_authorization_header(respx_mock, config: Config):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {}})
    )
    with build_sync_client(config) as http:
        request_json(http, _endpoint("/p"), body={}, token="tok")
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
    assert route.calls.last.request.headers["user-agent"].startswith("gangtise-openapi-python/")


# ─── retry policies (TS v0.26/v0.27 parity: no-replay / no-999999) ───


def test_no_replay_rejects_5xx_and_999999_and_post_send_network():
    assert not is_retryable_error(ApiError("boom", status_code=503), "no-replay")
    assert not is_retryable_error(ApiError("boom", code="999999", status_code=500), "no-replay")
    assert not is_retryable_error(httpx.ReadTimeout("t"), "no-replay")
    assert not is_retryable_error(httpx.WriteError("w"), "no-replay")
    assert not is_retryable_error(httpx.RemoteProtocolError("p"), "no-replay")


def test_no_replay_allows_429_and_connect_phase_errors():
    # 429 was rejected before processing; connect-phase errors never reached the
    # server — neither can double-bill on resend.
    assert is_retryable_error(ApiError("rate", status_code=429), "no-replay")
    assert is_retryable_error(httpx.ConnectError("refused"), "no-replay")
    assert is_retryable_error(httpx.ConnectTimeout("t"), "no-replay")
    assert is_retryable_error(httpx.PoolTimeout("t"), "no-replay")


def test_no_999999_rejects_999999_even_on_http_500():
    assert not is_retryable_error(ApiError("no data", code="999999", status_code=500), "no-999999")


def test_no_999999_keeps_other_errors_retryable():
    assert is_retryable_error(ApiError("boom", code="430004", status_code=500), "no-999999")
    assert is_retryable_error(httpx.ReadTimeout("t"), "no-999999")


def test_is_transient_error_matches_default_policy():
    assert is_transient_error(ApiError("boom", status_code=503))
    assert is_transient_error(ApiError("sys", code="999999"))
    assert not is_transient_error(ApiError("perm", code="999997", status_code=403))


def test_request_json_no_replay_endpoint_does_not_retry_500(respx_mock, config: Config):
    route = respx_mock.post("/p").mock(return_value=httpx.Response(500, text="boom"))
    with build_sync_client(config) as http, pytest.raises(ApiError):
        request_json(http, _endpoint("/p", retry="no-replay"), body={}, token="tok")
    assert route.call_count == 1


def test_request_json_no_replay_endpoint_still_retries_429(respx_mock, config: Config):
    route = respx_mock.post("/p").mock(
        side_effect=[
            httpx.Response(429, text="rate", headers={"Retry-After": "0"}),
            httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 1}}),
        ]
    )
    with build_sync_client(config) as http:
        out = request_json(http, _endpoint("/p", retry="no-replay"), body={}, token="tok")
    assert out == {"v": 1}
    assert route.call_count == 2


def test_request_json_no_999999_fails_fast_with_ede_hint(respx_mock, config: Config):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(
            500, json={"code": "999999", "status": False, "msg": "系统错误"}
        )
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, _endpoint("/p", retry="no-999999"), body={}, token="tok")
    assert route.call_count == 1
    assert exc.value.code == "999999"
    assert exc.value.hint == EDE_NO_DATA_HINT


def test_request_json_no_replay_999999_gets_billing_caution_hint(respx_mock, config: Config):
    # The generic "请稍后重试" hint would invite a manual double-bill on a per-call
    # billed endpoint whose request may already have executed.
    respx_mock.post("/p").mock(
        return_value=httpx.Response(500, json={"code": "999999", "status": False, "msg": "err"})
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, _endpoint("/p", retry="no-replay"), body={}, token="tok")
    assert exc.value.hint == NO_REPLAY_UNCERTAIN_HINT


# ─── Retry-After (TS v0.24 parity) ───


def test_parse_retry_after_seconds_and_http_date():
    assert parse_retry_after_ms("5", now=0.0) == 5000.0
    # HTTP-date 10s in the future of `now`.
    assert parse_retry_after_ms("Thu, 01 Jan 1970 00:00:10 GMT", now=0.0) == 10_000.0
    # A date in the past clamps to zero rather than going negative.
    assert parse_retry_after_ms("Thu, 01 Jan 1970 00:00:00 GMT", now=100.0) == 0.0


def test_parse_retry_after_garbage_returns_none():
    assert parse_retry_after_ms(None, now=0.0) is None
    assert parse_retry_after_ms("", now=0.0) is None
    assert parse_retry_after_ms("soon", now=0.0) is None
    assert parse_retry_after_ms("-5", now=0.0) is None


def test_retry_delay_prefers_retry_after_capped_at_ceiling():
    assert _retry_delay(ApiError("rate", status_code=429, retry_after_ms=2000.0), 0) == 2.0
    capped = _retry_delay(ApiError("rate", status_code=429, retry_after_ms=999_000.0), 0)
    assert capped == RETRY_AFTER_CEILING_MS / 1000.0
    # Without a Retry-After the jittered exponential backoff applies (400-800ms at attempt 0).
    assert 0.4 <= _retry_delay(ApiError("boom", status_code=503), 0) <= 0.8


def test_request_json_attaches_retry_after_to_api_error(respx_mock, config: Config):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(429, text="rate", headers={"Retry-After": "7"})
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, _endpoint("/p"), body={}, token="tok", max_retries=0)
    assert exc.value.retry_after_ms == 7000.0


# ─── per-endpoint timeout floor (TS v0.24 resolveTimeoutMs parity) ───


def test_effective_timeout_lifts_lower_client_timeout(config: Config):
    with build_sync_client(replace(config, timeout_ms=30_000)) as http:
        lifted = _effective_timeout(http, _endpoint(timeout_ms=120_000))
        assert lifted is not None and lifted.read == 120.0


def test_effective_timeout_keeps_higher_client_timeout(config: Config):
    with build_sync_client(replace(config, timeout_ms=300_000)) as http:
        assert _effective_timeout(http, _endpoint(timeout_ms=120_000)) is None


def test_effective_timeout_none_without_floor(config: Config):
    with build_sync_client(config) as http:
        assert _effective_timeout(http, _endpoint()) is None


def test_request_json_applies_timeout_floor_to_request(respx_mock, config: Config):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {}})
    )
    with build_sync_client(replace(config, timeout_ms=30_000)) as http:
        request_json(http, _endpoint("/p", timeout_ms=120_000), body={}, token="tok")
    assert route.calls.last.request.extensions["timeout"]["read"] == 120.0


# ── TS v0.28.0: terminal API codes (never replayed on any HTTP status) ──


def test_terminal_api_codes_set():
    assert frozenset({"999011", "140002"}) == TERMINAL_API_CODES


@pytest.mark.parametrize("code", ["999011", "140002"])
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_terminal_code_never_retryable(code, status):
    # 999011 (bad AK/SK) will not fix itself; 140002 (async generation failed) is
    # terminal by definition. Both must outrank the 429 and 5xx status rules.
    err = ApiError("boom", code=code, status_code=status)
    assert is_retryable_error(err, "default") is False


def test_request_json_terminal_code_500_does_not_retry(respx_mock, config: Config):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(
            500, json={"code": "140002", "status": False, "msg": "生成失败"}
        )
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, _endpoint("/p"), body={}, token="tok")
    assert route.call_count == 1
    assert exc.value.code == "140002"


# ── TS v0.28.0: HTTP 200 error envelopes must keep the server's Retry-After ──


def test_unwrap_envelope_error_carries_retry_after():
    with pytest.raises(ApiError) as exc:
        unwrap_envelope(
            {"code": "999006", "status": False, "msg": "限流"},
            status_code=200,
            retry_after_ms=1500.0,
        )
    assert exc.value.retry_after_ms == 1500.0


def test_request_json_200_envelope_error_keeps_retry_after(respx_mock, config: Config):
    # Gangtise wraps errors in HTTP 200 bodies too; dropping Retry-After there
    # degrades a rate-limit backoff into the blind exponential schedule.
    respx_mock.post("/p").mock(
        return_value=httpx.Response(
            200,
            json={"code": "999006", "status": False, "msg": "限流"},
            headers={"Retry-After": "2"},
        )
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, _endpoint("/p"), body={}, token="tok")
    assert exc.value.retry_after_ms == 2000.0
