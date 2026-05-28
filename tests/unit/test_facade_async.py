import pytest

from gangtise_openapi._facade import _Facade


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
