from __future__ import annotations

import ipaddress
import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

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


# Bounds for GANGTISE_TIMEOUT_MS. Below a second every request times out before the
# server can answer; past an hour a hung request is indistinguishable from none.
MIN_TIMEOUT_MS = 1_000
MAX_TIMEOUT_MS = 3_600_000

_timeout_warned = False
_plain_http_warned = False


def resolve_timeout_env(raw: str | None) -> int:
    """GANGTISE_TIMEOUT_MS as whole milliseconds (TS v0.42.0).

    Anything that is not a plain decimal integer (``0.5``, ``1e12``, ``30s``) falls
    back to the default, the same way an invalid GANGTISE_PAGE_CONCURRENCY does; so
    does a value under a second, which is almost always seconds written where
    milliseconds were meant (``30``) and would time every request out. A value past
    the upper bound is capped to it."""
    if not raw or not re.fullmatch(r"\d+", raw.strip(), re.ASCII):
        return DEFAULT_TIMEOUT_MS
    ms = int(raw)
    return DEFAULT_TIMEOUT_MS if ms < MIN_TIMEOUT_MS else min(MAX_TIMEOUT_MS, ms)


def _env(name: str) -> str | None:
    """An environment variable, with an empty or blank value treated as unset.
    ``export GANGTISE_BASE_URL=`` (a common way to "clear" one) otherwise sends every
    request to an empty base URL, and an empty GANGTISE_TOKEN shadows working AK/SK
    credentials (TS v0.44.0)."""
    value = os.environ.get(name, "").strip()
    return value or None


def warn_if_plain_http(base_url: str) -> None:
    """Said once per process: over plain http the login body carries the access key and
    secret, and every request the token, all unencrypted (TS v0.45.0). Loopback is left
    alone — that is where a local proxy or a test stub lives. Checked on the base URL in
    effect, whether it came from GANGTISE_BASE_URL or ``base_url=``."""
    global _plain_http_warned
    if _plain_http_warned:
        return
    try:
        url = urlsplit(base_url)
        host = url.hostname or ""
        port = url.port
    except ValueError:
        return
    if url.scheme != "http" or host == "localhost":
        return
    try:
        # The 127. prefix only means loopback on an address: 127.proxy.example.com is a
        # remote name.
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    _plain_http_warned = True
    shown = f"{host}:{port}" if port is not None else host
    warnings.warn(
        f"base URL uses plain http ({shown}): the access key, secret and token are sent "
        "unencrypted. Use https unless this is a trusted local proxy.",
        UserWarning,
        stacklevel=3,
    )


def _truthy(value: str | None) -> bool:
    return value in {"1", "true", "True", "yes", "YES"}


def load_config() -> Config:
    global _timeout_warned
    raw_timeout = _env("GANGTISE_TIMEOUT_MS")
    timeout_ms = resolve_timeout_env(raw_timeout)
    # Said once per process: the AI generation methods are the ones this variable is
    # set for, they are not replayed on a timeout, and a rerun bills again — so a value
    # that quietly fell back to 30 s must not go unnoticed.
    in_effect = raw_timeout is None or (
        re.fullmatch(r"\d+", raw_timeout, re.ASCII) is not None and int(raw_timeout) == timeout_ms
    )
    if not in_effect and not _timeout_warned:
        _timeout_warned = True
        warnings.warn(
            f"GANGTISE_TIMEOUT_MS={raw_timeout} is not in effect, using {timeout_ms} ms: "
            f"expected whole milliseconds from {MIN_TIMEOUT_MS} to {MAX_TIMEOUT_MS}",
            UserWarning,
            stacklevel=2,
        )
    token_cache_env = _env("GANGTISE_TOKEN_CACHE_PATH")
    title_cache_env = _env("GANGTISE_TITLE_CACHE_PATH")
    return Config(
        base_url=_env("GANGTISE_BASE_URL") or DEFAULT_BASE_URL,
        access_key=_env("GANGTISE_ACCESS_KEY"),
        secret_key=_env("GANGTISE_SECRET_KEY"),
        token=_env("GANGTISE_TOKEN"),
        token_cache_path=Path(token_cache_env) if token_cache_env else DEFAULT_TOKEN_CACHE_PATH,
        title_cache_path=Path(title_cache_env) if title_cache_env else DEFAULT_TITLE_CACHE_PATH,
        timeout_ms=timeout_ms,
        page_concurrency=_positive_int(
            _env("GANGTISE_PAGE_CONCURRENCY"),
            DEFAULT_PAGE_CONCURRENCY,
            maximum=MAX_PAGE_CONCURRENCY,
        ),
        verbose=_truthy(_env("GANGTISE_VERBOSE")),
    )
