import pytest

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import ConfigError
from gangtise_openapi._facade import _Facade


@pytest.fixture(autouse=True)
def isolated_facade(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "ak")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "sk")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("GANGTISE_TITLE_CACHE_PATH", str(tmp_path / "title.json"))
    yield


def test_configure_pins_default_client():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    assert isinstance(f._client, GangtiseClient)
    assert f._client.config.base_url == "https://test.one"


def test_configure_same_config_is_idempotent():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    client_one = f._client
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    assert f._client is client_one


def test_configure_different_config_raises():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    with pytest.raises(ConfigError):
        f.configure(base_url="https://test.two", access_key="ak", secret_key="sk")


def test_configure_replace_true_switches():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    f.configure(
        base_url="https://test.two",
        access_key="ak",
        secret_key="sk",
        replace=True,
    )
    assert f._client.config.base_url == "https://test.two"


def test_reset_clears_default_client():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    assert f._client is not None
    f.reset()
    assert f._client is None


def test_lazy_default_client_on_attribute_access(monkeypatch):
    monkeypatch.setenv("GANGTISE_BASE_URL", "https://lazy.test")
    f = _Facade()
    client = f._ensure_client()
    assert client.config.base_url == "https://lazy.test"
