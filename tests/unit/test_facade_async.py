import pytest

from gangtise_openapi._facade import _AsyncFacade, _Facade


@pytest.fixture()
def env_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "ak")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "sk")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))
    monkeypatch.setenv("GANGTISE_TITLE_CACHE_PATH", str(tmp_path / "title.json"))


def test_async_mirror_lazy_creates_async_client(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "ak")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "sk")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))
    monkeypatch.setenv("GANGTISE_TITLE_CACHE_PATH", str(tmp_path / "title.json"))

    f = _Facade()
    async_facade = f.async_
    # cached
    assert async_facade is f.async_

    from gangtise_openapi._client import AsyncGangtiseClient

    assert isinstance(async_facade._ensure_client(), AsyncGangtiseClient)


def test_async_facade_unknown_domain_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "ak")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "sk")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))

    f = _Facade()
    with pytest.raises(AttributeError):
        _ = f.async_.does_not_exist


def test_async_facade_underscore_attribute_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "ak")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "sk")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))

    f = _Facade()
    with pytest.raises(AttributeError):
        _ = f.async_._not_a_domain


def test_configure_propagates_to_async_facade(monkeypatch, tmp_path):
    monkeypatch.delenv("GANGTISE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("GANGTISE_SECRET_KEY", raising=False)
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))
    monkeypatch.setenv("GANGTISE_TITLE_CACHE_PATH", str(tmp_path / "title.json"))

    f = _Facade()
    f.configure(access_key="cfg-ak", secret_key="cfg-sk", base_url="https://cfg.test")
    async_client = f.async_._ensure_client()
    assert async_client.config == f._client.config
    assert async_client.config.access_key == "cfg-ak"


def test_async_facade_falls_back_to_env_without_configure(env_keys):
    f = _Facade()
    assert f.async_._ensure_client().config.access_key == "ak"


def test_reset_invalidates_cached_async_facade(env_keys):
    f = _Facade()
    f.configure(access_key="ak", secret_key="sk")
    async_facade = f.async_
    f.reset()
    assert f.async_ is not async_facade


@pytest.mark.parametrize("name", sorted(_AsyncFacade._DOMAIN_FACTORIES))
def test_async_domain_registry_resolves_to_declared_class(env_keys, name):
    f = _Facade()
    expected_class = _AsyncFacade._DOMAIN_FACTORIES[name].split(":")[1]
    assert type(getattr(f.async_, name)).__name__ == expected_class


def test_async_dir_lists_domains(env_keys):
    f = _Facade()
    assert set(_AsyncFacade._DOMAIN_FACTORIES) <= set(dir(f.async_))
