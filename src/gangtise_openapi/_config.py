from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://openapi.gangtise.com"
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_PAGE_CONCURRENCY = 5
DEFAULT_TOKEN_CACHE_PATH = Path.home() / ".config" / "gangtise" / "token.json"
DEFAULT_TITLE_CACHE_PATH = Path.home() / ".config" / "gangtise" / "title-cache.json"


@dataclass(frozen=True)
class Config:
    base_url: str = DEFAULT_BASE_URL
    access_key: str | None = None
    secret_key: str | None = None
    token: str | None = None
    token_cache_path: Path = field(default_factory=lambda: DEFAULT_TOKEN_CACHE_PATH)
    title_cache_path: Path = field(default_factory=lambda: DEFAULT_TITLE_CACHE_PATH)
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    page_concurrency: int = DEFAULT_PAGE_CONCURRENCY
    verbose: bool = False


# Fan-out cap for GANGTISE_PAGE_CONCURRENCY: an absurd value would fan out one
# worker per page/shard at once and can 429-storm the server (TS v0.27.0 parity).
MAX_PAGE_CONCURRENCY = 32


def _positive_int(value: str | None, default: int, maximum: int | None = None) -> int:
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return min(parsed, maximum) if maximum is not None else parsed


def _truthy(value: str | None) -> bool:
    return value in {"1", "true", "True", "yes", "YES"}


def load_config() -> Config:
    token_cache_env = os.environ.get("GANGTISE_TOKEN_CACHE_PATH")
    title_cache_env = os.environ.get("GANGTISE_TITLE_CACHE_PATH")
    return Config(
        base_url=os.environ.get("GANGTISE_BASE_URL", DEFAULT_BASE_URL),
        access_key=os.environ.get("GANGTISE_ACCESS_KEY"),
        secret_key=os.environ.get("GANGTISE_SECRET_KEY"),
        token=os.environ.get("GANGTISE_TOKEN"),
        token_cache_path=Path(token_cache_env) if token_cache_env else DEFAULT_TOKEN_CACHE_PATH,
        title_cache_path=Path(title_cache_env) if title_cache_env else DEFAULT_TITLE_CACHE_PATH,
        timeout_ms=_positive_int(os.environ.get("GANGTISE_TIMEOUT_MS"), DEFAULT_TIMEOUT_MS),
        page_concurrency=_positive_int(
            os.environ.get("GANGTISE_PAGE_CONCURRENCY"),
            DEFAULT_PAGE_CONCURRENCY,
            maximum=MAX_PAGE_CONCURRENCY,
        ),
        verbose=_truthy(os.environ.get("GANGTISE_VERBOSE")),
    )
