"""Logging setup for the ``gangtise_openapi`` logger.

A library should not emit log records unless the application opts in, so the
package logger carries a :class:`logging.NullHandler` by default. When verbose
mode is requested (``GANGTISE_VERBOSE`` env var or ``Config.verbose``) a single
stderr handler is attached and the level dropped to ``DEBUG`` — without this the
``logger.debug`` request-timing lines in the transport layer never surface,
because Python's last-resort handler only emits ``WARNING`` and above.
"""

from __future__ import annotations

import logging
import sys

_LOGGER_NAME = "gangtise_openapi"
_VERBOSE_HANDLER_FLAG = "_gangtise_verbose"

_TRUTHY = frozenset({"1", "true", "True", "yes", "YES"})


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def _ensure_null_handler() -> None:
    logger = get_logger()
    if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
        logger.addHandler(logging.NullHandler())


def configure_logging(verbose: bool) -> None:
    """Idempotently set up the package logger.

    Always installs a ``NullHandler``. When ``verbose`` is true, attaches a
    stderr ``StreamHandler`` at ``DEBUG`` (exactly once) and lowers the logger
    level to ``DEBUG``.
    """
    logger = get_logger()
    _ensure_null_handler()
    if not verbose:
        return
    logger.setLevel(logging.DEBUG)
    if any(getattr(h, _VERBOSE_HANDLER_FLAG, False) for h in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    setattr(handler, _VERBOSE_HANDLER_FLAG, True)
    logger.addHandler(handler)


def verbose_from_env(value: str | None) -> bool:
    return value in _TRUTHY
