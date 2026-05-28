from __future__ import annotations

import json
from pathlib import Path

import pytest

from gangtise_openapi._config import Config


@pytest.fixture
def anyio_backend() -> str:
    """anyio uses this fixture to pick a backend; default to asyncio."""
    return "asyncio"


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """A Config pointing at a fake host with isolated cache paths.

    The token_cache_path is NOT pre-seeded; tests that want to skip the login
    round-trip should use `seeded_config` instead.
    """
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=None,
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
        page_concurrency=3,
    )


@pytest.fixture
def seeded_config(config: Config) -> Config:
    """A Config whose on-disk token cache already holds a valid token."""
    config.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    config.token_cache_path.write_text(
        json.dumps(
            {
                "accessToken": "seeded-tok",
                "expiresIn": 3600,
                "time": 0,
                "expiresAt": 9999999999,
            }
        )
    )
    return config
