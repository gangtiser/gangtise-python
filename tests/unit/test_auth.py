import json
import time

import pytest

from gangtise_openapi._auth import (
    TokenCache,
    is_cache_valid,
    normalize_token,
    read_token_cache,
    require_credentials,
    write_token_cache,
)
from gangtise_openapi._errors import ConfigError


def _make_cache(*, expires_at: int) -> TokenCache:
    return TokenCache(
        access_token="tok",
        expires_in=3600,
        time=int(time.time()),
        expires_at=expires_at,
        uid=1,
        user_name="alice",
        tenant_id=10,
    )


def test_normalize_token_adds_bearer():
    assert normalize_token("abc") == "Bearer abc"


def test_normalize_token_preserves_bearer():
    assert normalize_token("Bearer abc") == "Bearer abc"


def test_is_cache_valid_with_buffer():
    now = int(time.time())
    assert is_cache_valid(_make_cache(expires_at=now + 1000)) is True


def test_is_cache_valid_near_expiry_fails_buffer():
    now = int(time.time())
    assert is_cache_valid(_make_cache(expires_at=now + 10)) is False


def test_is_cache_valid_none():
    assert is_cache_valid(None) is False


def test_read_token_cache_roundtrip(tmp_path):
    path = tmp_path / "tok.json"
    cache = _make_cache(expires_at=int(time.time()) + 1000)
    write_token_cache(path, cache)
    loaded = read_token_cache(path)
    assert loaded == cache
    assert (path.stat().st_mode & 0o777) == 0o600


def test_read_token_cache_missing(tmp_path):
    assert read_token_cache(tmp_path / "nope.json") is None


def test_read_token_cache_corrupt(tmp_path):
    path = tmp_path / "tok.json"
    path.write_text("not json", encoding="utf8")
    assert read_token_cache(path) is None


def test_read_token_cache_partial_schema(tmp_path):
    path = tmp_path / "tok.json"
    path.write_text(json.dumps({"accessToken": "x"}), encoding="utf8")
    assert read_token_cache(path) is None


def test_require_credentials_missing():
    with pytest.raises(ConfigError):
        require_credentials(None, None)
    with pytest.raises(ConfigError):
        require_credentials("ak", None)


def test_require_credentials_ok():
    assert require_credentials("ak", "sk") == ("ak", "sk")
