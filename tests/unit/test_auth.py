import json
import os
import time
from pathlib import Path

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


def test_normalize_token_canonicalizes_case_insensitive_bearer_prefix():
    assert normalize_token("bearer abc") == "Bearer abc"
    assert normalize_token("BEARER abc") == "Bearer abc"


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


def test_write_token_cache_tightens_lax_existing_file(tmp_path):
    # CLI v0.21.0 parity: a token.json restored from backup or written by an older
    # tool may be 0644; the temp-file + atomic replace must hand back a 0600 file
    # (the temp carries 0600, and replace adopts the temp's inode + perms).
    path = tmp_path / "tok.json"
    path.write_text("{}", encoding="utf8")
    os.chmod(path, 0o644)
    write_token_cache(path, _make_cache(expires_at=int(time.time()) + 1000))
    assert (path.stat().st_mode & 0o777) == 0o600
    loaded = read_token_cache(path)
    assert loaded is not None
    assert loaded.access_token == "tok"


def test_write_token_cache_creates_temp_0600_atomically(tmp_path, monkeypatch):
    # The temp file is created with mode 0600 at open() time — NOT written under a
    # umask default then chmod-ed, which would leave a brief window where the bearer
    # token is world-readable. CLI v0.21.0 parity (auth.ts: "0600 from the first byte").
    path = tmp_path / "tok.json"
    opens: list[tuple[str, int]] = []
    real_open = os.open

    def spy(file, flags, mode=0o777, *args, **kwargs):
        opens.append((str(file), mode))
        return real_open(file, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    write_token_cache(path, _make_cache(expires_at=int(time.time()) + 1000))
    # Exactly one temp opened, created 0600 (not chmod-ed afterward); the final file
    # inherits 0600 via the atomic rename.
    assert len(opens) == 1
    assert opens[0][1] == 0o600
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


def test_write_token_cache_tmp_name_unique_per_writer(tmp_path, monkeypatch):
    # token.json is shared across processes (npm CLI included); the temp
    # file name must differ per writer so concurrent refreshes never race
    # on the same tmp path.
    path = tmp_path / "tok.json"
    cache = _make_cache(expires_at=int(time.time()) + 1000)
    real_pid = os.getpid()
    tmp_names: list[str] = []
    original_replace = Path.replace

    def spy(self, *args, **kwargs):
        tmp_names.append(self.name)  # self is the temp file being renamed onto path
        return original_replace(self, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", spy)
    write_token_cache(path, cache)
    # Simulate a second process by faking a different pid.
    monkeypatch.setattr(os, "getpid", lambda: real_pid + 1)
    write_token_cache(path, cache)

    assert len(tmp_names) == 2
    assert tmp_names[0] != tmp_names[1]
    assert f".tmp-{real_pid}-" in tmp_names[0]
    assert f".tmp-{real_pid + 1}-" in tmp_names[1]
    # No leftover tmp files and the final file is still readable.
    assert list(tmp_path.iterdir()) == [path]
    assert read_token_cache(path) == cache


def test_require_credentials_missing():
    with pytest.raises(ConfigError) as exc:
        require_credentials(None, None)
    msg = str(exc.value)
    assert "GANGTISE_ACCESS_KEY" in msg and "GANGTISE_SECRET_KEY" in msg
    # only the actually-missing var is named in the "缺少环境变量" summary line
    with pytest.raises(ConfigError) as exc2:
        require_credentials("ak", None)
    assert "缺少环境变量: GANGTISE_SECRET_KEY" in str(exc2.value)


def test_require_credentials_ok():
    assert require_credentials("ak", "sk") == ("ak", "sk")
