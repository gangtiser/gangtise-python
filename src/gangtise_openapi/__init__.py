import os as _os

from gangtise_openapi.__about__ import __version__
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
from gangtise_openapi._errors import (
    ApiError,
    ConfigError,
    DownloadError,
    GangtiseError,
    ValidationError,
)
from gangtise_openapi._facade import gangtise
from gangtise_openapi._logging import configure_logging, verbose_from_env

__all__ = [
    "ApiError",
    "AsyncGangtiseClient",
    "ConfigError",
    "DownloadError",
    "GangtiseClient",
    "GangtiseError",
    "ValidationError",
    "__version__",
    "gangtise",
]

# Honor GANGTISE_VERBOSE at import time. configure_logging always installs a
# NullHandler, and attaches a stderr DEBUG handler when verbose is on.
configure_logging(verbose_from_env(_os.environ.get("GANGTISE_VERBOSE")))
