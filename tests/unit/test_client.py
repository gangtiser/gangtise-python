import json

import httpx
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ConfigError


@pytest.fixture
def client_config(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=None,
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
        page_concurrency=3,
    )


def test_call_unknown_endpoint_raises(client_config):
    with GangtiseClient(_config=client_config) as client, pytest.raises(KeyError):
        client._call("does.not.exist")


def test_call_with_env_token_skips_login(client_config, monkeypatch):
    cfg = Config(
        base_url="https://api.test",
        access_key=None,
        secret_key=None,
        token="env-tok",
        token_cache_path=client_config.token_cache_path,
        title_cache_path=client_config.title_cache_path,
        timeout_ms=5000,
        page_concurrency=3,
    )
    # Use assert_all_called=False because the login route is intentionally
    # registered to prove it gets zero traffic.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login_route = router.post("/application/auth/oauth/open/loginV2")
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": []}
            )
        )
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["000001.SH"]})
        assert login_route.call_count == 0


def test_call_login_happens_when_no_token(client_config):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "fresh",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "x",
                        "tenantId": 1,
                    },
                },
            )
        )
        ep = router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": []})
        )
        with GangtiseClient(_config=client_config) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
        assert ep.calls.last.request.headers["Authorization"] == "Bearer fresh"


def test_call_auth_code_8000014_triggers_one_refresh(client_config, tmp_path):
    # Pre-seed an obviously expired-looking token to force refresh path.
    client_config.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    client_config.token_cache_path.write_text(
        json.dumps({
            "accessToken": "stale", "expiresIn": 1, "time": 0, "expiresAt": 9999999999,
        })
    )
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "refreshed",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "x",
                        "tenantId": 1,
                    },
                },
            )
        )
        ep_route = router.post("/application/open-quote/quote/realtime").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"code": "8000014", "status": False, "msg": "bad access key"},
                ),
                httpx.Response(200, json={"code": "000000", "status": True, "data": []}),
            ]
        )
        with GangtiseClient(_config=client_config) as client:
            out = client._call("quote.realtime", body={"securityList": ["x"]})
        assert out == []
        assert ep_route.call_count == 2


def test_login_returns_authorization_and_cache(client_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "tok",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "x",
                        "tenantId": 1,
                    },
                },
            )
        )
        with GangtiseClient(_config=client_config) as client:
            result = client.login()
        assert result["authorization"] == "Bearer tok"
        assert result["cache"]["access_token"] == "tok"


def test_call_lookup_endpoint_returns_local_data(client_config):
    with GangtiseClient(_config=client_config) as client:
        out = client._call("lookup.research-areas.list")
    assert isinstance(out, list)
    assert len(out) > 0


def test_missing_credentials_raises(tmp_path):
    cfg = Config(
        base_url="https://api.test",
        access_key=None,
        secret_key=None,
        token=None,
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
    )
    with GangtiseClient(_config=cfg) as client, pytest.raises(ConfigError):
        client._call("quote.realtime", body={"securityList": ["x"]})
