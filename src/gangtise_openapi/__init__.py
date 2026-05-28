import logging as _logging
import os as _os

from gangtise_openapi.__about__ import __version__
from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import (
    ApiError,
    ConfigError,
    DownloadError,
    GangtiseError,
    ValidationError,
)
from gangtise_openapi._facade import gangtise

__all__ = [
    "ApiError",
    "ConfigError",
    "DownloadError",
    "GangtiseClient",
    "GangtiseError",
    "ValidationError",
    "__version__",
    "gangtise",
]

if _os.environ.get("GANGTISE_VERBOSE") in {"1", "true", "True", "yes", "YES"}:
    _logging.getLogger("gangtise_openapi").setLevel(_logging.DEBUG)
