import httpx
import pytest

from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError
from gangtise_openapi._transport import (
    RETRYABLE_API_CODES,
    RETRYABLE_HTTP_STATUS,
    build_sync_client,
    is_retryable_error,
    request_json,
    unwrap_envelope,
)


def _endpoint(path: str = "/p") -> EndpointDef:
    return EndpointDef(key="x", method="POST", path=path, kind="json", description="d")


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
