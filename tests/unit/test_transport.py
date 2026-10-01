import json
from dataclasses import replace

import httpx
import pytest
import respx

from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import Billing, EndpointDef, RetryPolicy
from gangtise_openapi._errors import (
    EDE_NO_DATA_HINT,
    ERROR_HINTS,
    NO_REPLAY_SIDE_EFFECT_HINT,
    NO_REPLAY_UNCERTAIN_HINT,
    ApiError,
)
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
    key: str = "x",
) -> EndpointDef:
    return EndpointDef(
        key=key,
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
        request_json(
            http,
            _endpoint("/p", retry="no-999999", key="indicator.cross-section"),
            body={},
            token="tok",
        )
    assert route.call_count == 1
    assert exc.value.code == "999999"
    assert exc.value.hint == EDE_NO_DATA_HINT


def test_request_json_no_999999_search_keeps_generic_hint(respx_mock, config: Config):
    # indicator.search shares the no-999999 policy but takes only a keyword, so a
    # 999999 keeps the generic hint — the fetch hint's date/scopeList/param
    # guidance would be nonsense there (TS v0.28.2 scoping fix).
    respx_mock.post("/p").mock(
        return_value=httpx.Response(
            500, json={"code": "999999", "status": False, "msg": "系统错误"}
        )
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(
            http,
            _endpoint("/p", retry="no-999999", key="indicator.search"),
            body={},
            token="tok",
        )
    assert exc.value.code == "999999"
    # Exact: the generic 999999 hint, NOT the EDE data-fetch hint (and not None).
    assert exc.value.hint == ERROR_HINTS["999999"]


def test_request_json_no_replay_999999_gets_billing_caution_hint(respx_mock, config: Config):
    # The generic "请稍后重试" hint would invite a manual double-bill on a per-call
    # billed endpoint whose request may already have executed.
    respx_mock.post("/p").mock(
        return_value=httpx.Response(500, json={"code": "999999", "status": False, "msg": "err"})
    )
    billed = replace(_endpoint("/p", retry="no-replay"), billing=Billing("call", 50))
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, billed, body={}, token="tok")
    assert exc.value.hint == NO_REPLAY_UNCERTAIN_HINT


def test_request_json_free_no_replay_999999_gets_side_effect_hint(respx_mock, config: Config):
    """A free no-replay write (drive create-folder, stock-pool create) risks a second
    copy or a false "not found" on a manual retry, not a second charge — the billing
    caution would name a cost that does not exist."""
    respx_mock.post("/p").mock(
        return_value=httpx.Response(500, json={"code": "999999", "status": False, "msg": "err"})
    )
    with build_sync_client(config) as http, pytest.raises(ApiError) as exc:
        request_json(http, _endpoint("/p", retry="no-replay"), body={}, token="tok")
    assert exc.value.hint == NO_REPLAY_SIDE_EFFECT_HINT


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


# ── envelope traceId propagation (CLI v0.31.0) ──


def test_unwrap_envelope_carries_the_trace_id_onto_the_payload():
    # unwrap_envelope discards the envelope, and with it the one correlation id
    # support can trace a failure by. A shape error raised downstream (an EDE
    # matrix that no longer matches) would otherwise reach the user trace-less.
    data = unwrap_envelope(
        {"code": "000000", "status": True, "traceId": 830965044897325056, "data": {"a": 1}}
    )
    assert data == {"a": 1}
    assert ApiError("shape mismatch", details=data).trace_id == "830965044897325056"


def test_traced_payload_still_behaves_like_a_plain_dict():
    data = unwrap_envelope({"code": "000000", "status": True, "traceId": "t-1", "data": {"a": 1}})
    assert isinstance(data, dict)
    assert data == {"a": 1}
    assert json.dumps(data) == '{"a": 1}'
    assert list(data) == ["a"]  # the id is an attribute, not a key


def test_payload_without_a_trace_id_is_left_alone():
    data = unwrap_envelope({"code": "000000", "status": True, "data": {"a": 1}})
    assert type(data) is dict
    assert ApiError("x", details=data).trace_id is None


def test_a_payload_that_is_not_a_dict_is_left_alone():
    assert unwrap_envelope(
        {"code": "000000", "status": True, "traceId": "t-1", "data": [1, 2]}
    ) == [1, 2]


def test_an_explicit_trace_id_on_the_payload_wins_over_the_carried_one():
    # The inner envelope of a double-wrapped EDE response carries no traceId, so
    # the carried one is a FALLBACK — a payload with its own id keeps it.
    data = unwrap_envelope(
        {"code": "000000", "status": True, "traceId": "outer", "data": {"traceId": "inner"}}
    )
    assert ApiError("x", details=data).trace_id == "inner"


def test_double_unwrap_keeps_the_outer_trace_id():
    # The EDE endpoints have historically double-wrapped. Peeling the inner
    # envelope must not drop the OUTER id — that is the one the server logged.
    outer = unwrap_envelope(
        {
            "code": "000000",
            "status": True,
            "traceId": "outer",
            "data": {"code": "000000", "status": True, "data": {"values": []}},
        }
    )
    inner = unwrap_envelope(outer)
    assert inner == {"values": []}
    assert ApiError("shape mismatch", details=inner).trace_id == "outer"


# ─── v0.4.0: `expects="list"` shape guard (TS v0.38.0) ───


def _quote_ep() -> EndpointDef:
    return EndpointDef(
        key="quote.realtime",
        method="POST",
        path="/q",
        kind="json",
        description="d",
        expects="list",
    )


@pytest.mark.parametrize(
    ("data", "described"),
    [
        (None, "null"),
        ([{"a": 1}], "an array"),
        ({"total": 0}, "an object with no list"),
    ],
)
def test_expects_list_refuses_a_payload_without_a_list(data, described):
    """Every legitimate answer from these endpoints is `{total, list}` — including an
    empty date range and an unknown code (probed live on all seven, 2026-09-07). So a
    `data: null` or bare object is a BROKEN response, not an empty one; without this
    the normalizers hand it back as "no data"."""
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/q").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "traceId": "t-1", "data": data}
            )
        )
        with httpx.Client(base_url="https://api.test") as http:  # noqa: SIM117
            with pytest.raises(ApiError, match=f"got {described}") as excinfo:
                request_json(http, _quote_ep(), body={}, token="tok")
    assert excinfo.value.structural is True
    # The envelope is carried as `details` so the failure stays traceable: `None`
    # itself has nowhere to hold the id, which is why the check lives here.
    assert excinfo.value.trace_id == "t-1"


def test_expects_list_accepts_an_empty_range():
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/q").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {"total": 0, "list": [], "fieldList": ["close"]},
                },
            )
        )
        with httpx.Client(base_url="https://api.test") as http:
            out = request_json(http, _quote_ep(), body={}, token="tok")
    assert out == {"total": 0, "list": [], "fieldList": ["close"]}


def test_expects_list_is_not_retried():
    """A 2xx with no code is not retryable, so the transport must not burn two more
    requests on a response that will come back identical."""
    calls = 0

    def responder(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": "000000", "status": True, "data": None})

    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/q").mock(side_effect=responder)
        with httpx.Client(base_url="https://api.test") as http:  # noqa: SIM117
            with pytest.raises(ApiError):
                request_json(http, _quote_ep(), body={}, token="tok")
    assert calls == 1


def test_endpoints_without_expects_are_untouched():
    ep = EndpointDef(key="x", method="POST", path="/q", kind="json", description="d")
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/q").mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": None})
        )
        with httpx.Client(base_url="https://api.test") as http:
            assert request_json(http, ep, body={}, token="tok") is None


# ─── expects="array" (TS v0.41.0: the opinion detail endpoints) ───


def _array_ep() -> EndpointDef:
    return EndpointDef(
        key="insight.opinion.detail",
        method="POST",
        path="/q",
        kind="json",
        description="d",
        expects="array",
    )


@pytest.mark.parametrize(
    ("data", "described"),
    [(None, "null"), ({"list": []}, "an object"), ("x", "str")],
)
def test_expects_array_refuses_anything_but_a_bare_array(data, described):
    """An ID with nothing to return is simply absent, so the empty answer is `[]`.
    Anything else is a changed layout — read as "no rows" it would report every
    paid-for body as missing."""
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/q").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "traceId": "t-2", "data": data}
            )
        )
        with httpx.Client(base_url="https://api.test") as http:  # noqa: SIM117
            with pytest.raises(ApiError, match=f"no array payload \\(got {described}\\)") as exc:
                request_json(http, _array_ep(), body={}, token="tok")
    assert exc.value.structural is True
    assert exc.value.trace_id == "t-2"


def test_expects_array_accepts_an_empty_array():
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/q").mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": []})
        )
        with httpx.Client(base_url="https://api.test") as http:
            assert request_json(http, _array_ep(), body={}, token="tok") == []


# ─── total request deadline (TS v0.44.0) ───


class _TrickleStream(httpx.SyncByteStream):
    """A body that keeps arriving, a little at a time — resets an idle timeout forever."""

    def __init__(self, clock: list[float]) -> None:
        self._clock = clock

    def __iter__(self):
        yield b'{"code": "000000", "status": true, "data": '
        for _ in range(10):
            self._clock[0] += 5.0  # 5 s pass between chunks
            yield b" "
        yield b"null}"


def test_trickling_response_is_cut_at_the_total_deadline(monkeypatch):
    """httpx's read timeout is an IDLE timeout: a server sending a few bytes per
    interval holds the request open indefinitely. A JSON request gets 2x its timeout
    in total, and is then a ReadTimeout — retried on the default policy, never on
    no-replay."""
    clock = [1000.0]
    monkeypatch.setattr("gangtise_openapi._transport.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("gangtise_openapi._transport._retry_delay", lambda e, a: 0.0)
    ep = EndpointDef(
        key="x", method="POST", path="/q", kind="json", description="d", retry="no-replay"
    )
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/q").mock(
            side_effect=lambda request: httpx.Response(200, stream=_TrickleStream(clock))
        )
        with httpx.Client(base_url="https://api.test", timeout=10.0) as http:  # noqa: SIM117
            with pytest.raises(httpx.ReadTimeout, match="overall deadline \\(20s\\)"):
                request_json(http, ep, body={}, token="tok")
    assert route.call_count == 1  # no-replay: a timed-out request may have run


def test_deadline_uses_the_endpoint_floor_and_transfer_factor():
    from gangtise_openapi._transport import request_deadline_seconds

    with httpx.Client(timeout=30.0) as http:
        plain = EndpointDef(key="x", method="POST", path="/q", kind="json", description="d")
        floored = replace(plain, timeout_ms=120_000)
        assert request_deadline_seconds(http, plain, transfer=False) == 60.0
        assert request_deadline_seconds(http, floored, transfer=False) == 240.0
        assert request_deadline_seconds(http, plain, transfer=True) == 1800.0


# ─── multipart upload fields (vault.drive.upload) ───


def test_upload_sends_the_extra_form_fields_next_to_the_file():
    from gangtise_openapi._transport import UploadFile

    ep = EndpointDef(key="u", method="POST", path="/up", kind="upload", description="d")
    upload = UploadFile("a.pdf", b"%PDF", fields=(("spaceType", "1"), ("title", "年报")))
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/up").mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {}})
        )
        with httpx.Client(base_url="https://api.test") as http:
            request_json(http, ep, body=upload, token="tok")
    sent = route.calls[0].request
    assert sent.headers["content-type"].startswith("multipart/form-data; boundary=")
    content = sent.read()
    assert b'name="spaceType"\r\n\r\n1\r\n' in content
    assert 'name="title"\r\n\r\n年报\r\n'.encode() in content
    assert b'name="file"; filename="a.pdf"' in content


def test_expects_array_payload_carries_the_envelope_trace_id():
    """A detail batch found malformed downstream must still be traceable."""
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/q").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "traceId": "t-9", "data": [{"a": 1}]}
            )
        )
        with httpx.Client(base_url="https://api.test") as http:
            out = request_json(http, _array_ep(), body={}, token="tok")
    assert out == [{"a": 1}]
    assert isinstance(out, list)
    assert out.envelope_trace_id == "t-9"


def test_retry_after_http_date_without_a_zone_is_gmt():
    """``-0000`` makes ``parsedate_to_datetime`` return a naive datetime; read as local
    time it was off by the machine's UTC offset."""
    now = 1_000_000_000.0  # 2001-09-09T01:46:40Z
    assert parse_retry_after_ms("Sun, 09 Sep 2001 01:47:40 -0000", now) == 60_000.0
    assert parse_retry_after_ms("Sun, 09 Sep 2001 01:47:40 GMT", now) == 60_000.0
