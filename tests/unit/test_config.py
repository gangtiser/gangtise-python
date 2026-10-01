from pathlib import Path

import pytest

from gangtise_openapi._config import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_MS,
    Config,
    load_config,
)


def test_default_base_url_is_openapi_host(monkeypatch):
    # v0.23.0: default host migrated open.gangtise.com -> openapi.gangtise.com.
    # GANGTISE_BASE_URL still pins the old host for anyone who needs it.
    monkeypatch.delenv("GANGTISE_BASE_URL", raising=False)
    assert DEFAULT_BASE_URL == "https://openapi.gangtise.com"
    assert load_config().base_url == "https://openapi.gangtise.com"
    monkeypatch.setenv("GANGTISE_BASE_URL", "https://open.gangtise.com")
    assert load_config().base_url == "https://open.gangtise.com"


def test_defaults(monkeypatch):
    for k in [
        "GANGTISE_BASE_URL",
        "GANGTISE_ACCESS_KEY",
        "GANGTISE_SECRET_KEY",
        "GANGTISE_TOKEN",
        "GANGTISE_TOKEN_CACHE_PATH",
        "GANGTISE_TIMEOUT_MS",
        "GANGTISE_PAGE_CONCURRENCY",
        "GANGTISE_VERBOSE",
    ]:
        monkeypatch.delenv(k, raising=False)
    cfg = load_config()
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.timeout_ms == DEFAULT_TIMEOUT_MS
    assert cfg.access_key is None
    assert cfg.secret_key is None
    assert cfg.token is None
    assert cfg.page_concurrency == 5
    assert cfg.verbose is False
    assert cfg.token_cache_path == Path.home() / ".config" / "gangtise" / "token.json"


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_BASE_URL", "https://test.example")
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "AK")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "SK")
    monkeypatch.setenv("GANGTISE_TOKEN", "tok")
    monkeypatch.setenv("GANGTISE_TIMEOUT_MS", "12345")
    monkeypatch.setenv("GANGTISE_PAGE_CONCURRENCY", "9")
    monkeypatch.setenv("GANGTISE_VERBOSE", "1")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))

    cfg = load_config()
    assert cfg.base_url == "https://test.example"
    assert cfg.access_key == "AK"
    assert cfg.secret_key == "SK"
    assert cfg.token == "tok"
    assert cfg.timeout_ms == 12345
    assert cfg.page_concurrency == 9
    assert cfg.verbose is True
    assert cfg.token_cache_path == tmp_path / "tok.json"


def test_invalid_timeout_falls_back_to_default(monkeypatch):
    import gangtise_openapi._config as config_module

    monkeypatch.setattr(config_module, "_timeout_warned", False)
    monkeypatch.setenv("GANGTISE_TIMEOUT_MS", "not-a-number")
    with pytest.warns(UserWarning, match="not in effect"):
        cfg = load_config()
    assert cfg.timeout_ms == DEFAULT_TIMEOUT_MS


@pytest.mark.parametrize(
    ("raw", "expected", "warns"),
    [
        ("45000", 45_000, False),
        ("045000", 45_000, False),
        (" 45000 ", 45_000, False),
        ("30", 30_000, True),  # seconds written where ms were meant
        ("0.5", 30_000, True),
        ("1e4", 30_000, True),
        ("30s", 30_000, True),
        ("9999999999", 3_600_000, True),  # capped to an hour
        ("", 30_000, False),  # blank = unset
    ],
)
def test_timeout_env_is_whole_milliseconds(monkeypatch, raw, expected, warns):
    """TS v0.42.0: only plain decimal integers in [1s, 1h]; anything else falls back
    (or caps) and says so once — the variable is set for the AI generators, which are
    not replayed on a timeout."""
    import warnings

    import gangtise_openapi._config as config_module

    monkeypatch.setattr(config_module, "_timeout_warned", False)
    monkeypatch.setenv("GANGTISE_TIMEOUT_MS", raw)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert load_config().timeout_ms == expected
    assert bool([w for w in caught if "not in effect" in str(w.message)]) is warns


def test_blank_env_values_count_as_unset(monkeypatch):
    """TS v0.44.0: ``export GANGTISE_BASE_URL=`` must not send requests to an empty
    base URL, and an empty GANGTISE_TOKEN must not shadow working AK/SK."""
    monkeypatch.setenv("GANGTISE_BASE_URL", "")
    monkeypatch.setenv("GANGTISE_TOKEN", "  ")
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "")
    cfg = load_config()
    assert cfg.base_url == "https://openapi.gangtise.com"
    assert cfg.token is None
    assert cfg.access_key is None


def test_invalid_concurrency_falls_back(monkeypatch):
    monkeypatch.setenv("GANGTISE_PAGE_CONCURRENCY", "0")
    cfg = load_config()
    assert cfg.page_concurrency == 5


def test_config_equality():
    a = Config(base_url="x", access_key="ak", secret_key="sk")
    b = Config(base_url="x", access_key="ak", secret_key="sk")
    assert a == b


def test_page_concurrency_defensive_parse(monkeypatch):
    # TS v0.27.0 parity: negative/zero/garbage falls back to the default (a
    # negative value used to silently degrade to a single serial worker), and
    # absurd values are capped so the fan-out can't 429-storm the server.
    from gangtise_openapi._config import MAX_PAGE_CONCURRENCY, load_config

    for raw, expected in [("-3", 5), ("0", 5), ("abc", 5), ("", 5), ("8", 8), ("999", 32)]:
        monkeypatch.setenv("GANGTISE_PAGE_CONCURRENCY", raw)
        assert load_config().page_concurrency == expected, raw
    assert MAX_PAGE_CONCURRENCY == 32
