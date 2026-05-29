from __future__ import annotations

import logging

from gangtise_openapi._config import load_config
from gangtise_openapi._logging import (
    _VERBOSE_HANDLER_FLAG,
    configure_logging,
    get_logger,
    verbose_from_env,
)


def _verbose_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [h for h in logger.handlers if getattr(h, _VERBOSE_HANDLER_FLAG, False)]


# ---- pre-existing coverage ----


def test_verbose_env_enables_debug(monkeypatch):
    monkeypatch.setenv("GANGTISE_VERBOSE", "1")
    cfg = load_config()
    assert cfg.verbose is True


def test_logger_is_named_gangtise_openapi():
    logger = logging.getLogger("gangtise_openapi")
    assert logger.name == "gangtise_openapi"


# ---- configure_logging ----


def test_verbose_from_env_truthy():
    assert verbose_from_env("1") is True
    assert verbose_from_env("true") is True
    assert verbose_from_env("YES") is True
    assert verbose_from_env(None) is False
    assert verbose_from_env("0") is False
    assert verbose_from_env("nope") is False


def test_configure_logging_always_installs_null_handler():
    logger = get_logger()
    saved = list(logger.handlers)
    saved_level = logger.level
    try:
        configure_logging(False)
        assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)
    finally:
        logger.handlers[:] = saved
        logger.setLevel(saved_level)


def test_configure_logging_verbose_attaches_exactly_one_stream_handler():
    logger = get_logger()
    saved = list(logger.handlers)
    saved_level = logger.level
    try:
        logger.handlers[:] = [
            h for h in logger.handlers if not getattr(h, _VERBOSE_HANDLER_FLAG, False)
        ]
        configure_logging(True)
        configure_logging(True)  # idempotent: must not stack a second handler
        verbose = _verbose_handlers(logger)
        assert len(verbose) == 1
        assert isinstance(verbose[0], logging.StreamHandler)
        assert logger.level == logging.DEBUG
    finally:
        logger.handlers[:] = saved
        logger.setLevel(saved_level)
