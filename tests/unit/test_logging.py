import logging

from gangtise_openapi._config import load_config


def test_verbose_env_enables_debug(monkeypatch):
    monkeypatch.setenv("GANGTISE_VERBOSE", "1")
    cfg = load_config()
    assert cfg.verbose is True


def test_logger_is_named_gangtise_openapi():
    logger = logging.getLogger("gangtise_openapi")
    assert logger.name == "gangtise_openapi"
