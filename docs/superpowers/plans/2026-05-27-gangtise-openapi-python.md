# Gangtise OpenAPI Python SDK — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `gangtise-openapi` Python package on PyPI that reaches feature parity with `gangtise-openapi-cli` v0.14.2 (73 endpoints).

**Architecture:** Three-layer SDK — namespace facade (`gangtise.quote.day_kline(...)`) on top of hand-written domain wrappers, all funneling through a shared `_call(endpoint_key, body)` on `GangtiseClient` / `AsyncGangtiseClient`. Sync and async share endpoint registry, pagination orchestration, K-line sharding, and async-content polling — they diverge only in the underlying httpx client.

**Tech Stack:** Python 3.10+, httpx, pandas, anyio, uv, hatchling, pytest, respx, ruff, mypy.

**Reference sources (read these for ground truth):**
- Spec: `docs/superpowers/specs/2026-05-27-gangtise-openapi-python-design.md`
- TS CLI: `/Users/martin/Documents/claude_workspace/gangtise-openapi-cli/` (`src/cli.ts`, `src/core/*.ts`)

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | uv + hatchling + ruff + mypy + pytest config |
| `.gitignore` | exclude `.venv/`, `dist/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.env*`, `*.egg-info` |
| `LICENSE` | MIT |
| `README.md` | install + quickstart + link to npm CLI docs |
| `CHANGELOG.md` | keep-a-changelog format |
| `docs/RELEASE.md` | release checklist |
| `.github/workflows/ci.yml` | ruff + mypy + pytest on push/PR |
| `.github/workflows/release.yml` | tag `v*` → build → PyPI Trusted Publisher |
| `src/gangtise_openapi/__init__.py` | public exports: `gangtise`, `GangtiseClient`, `AsyncGangtiseClient`, errors, `__version__` |
| `src/gangtise_openapi/__about__.py` | `__version__` single source |
| `src/gangtise_openapi/py.typed` | PEP 561 marker (empty file) |
| `src/gangtise_openapi/_errors.py` | exception tree + `ERROR_HINTS` |
| `src/gangtise_openapi/_config.py` | `Config` dataclass + `load_config()` env reader |
| `src/gangtise_openapi/_auth.py` | `TokenCache` read/write/validity |
| `src/gangtise_openapi/_endpoints.py` | `EndpointDef` dataclass + `ENDPOINTS` dict (73 entries) |
| `src/gangtise_openapi/_lookup/__init__.py` | `LOOKUP_LOADERS` dict |
| `src/gangtise_openapi/_lookup/<topic>.py` | 8 modules holding bundled local data |
| `src/gangtise_openapi/_transport.py` | sync httpx client, retry, header build, envelope unwrap |
| `src/gangtise_openapi/_transport_async.py` | async httpx client variant |
| `src/gangtise_openapi/_pagination.py` | sync/async auto-pagination with concurrency |
| `src/gangtise_openapi/_quote_sharding.py` | K-line date sharding planner (pure function) + executor |
| `src/gangtise_openapi/_async_content.py` | polling state machine for `*.get-content` (sync + async) |
| `src/gangtise_openapi/_download.py` | streaming download (sync + async) |
| `src/gangtise_openapi/_title_cache.py` | atomic title-cache JSON |
| `src/gangtise_openapi/_normalize.py` | rows → `pandas.DataFrame` with schema lock |
| `src/gangtise_openapi/_client.py` | `GangtiseClient` + `AsyncGangtiseClient` + `_call` |
| `src/gangtise_openapi/_facade.py` | `_Facade` singleton + `configure`/`reset` + `async_` mirror |
| `src/gangtise_openapi/domains/__init__.py` | re-exports domain classes |
| `src/gangtise_openapi/domains/auth.py` | `Auth` / `AsyncAuth` |
| `src/gangtise_openapi/domains/lookup.py` | `Lookup` / `AsyncLookup` |
| `src/gangtise_openapi/domains/reference.py` | `Reference` / `AsyncReference` |
| `src/gangtise_openapi/domains/insight.py` | `Insight` / `AsyncInsight` (19 endpoints) |
| `src/gangtise_openapi/domains/quote.py` | `Quote` / `AsyncQuote` (6 endpoints, 4 sharded) |
| `src/gangtise_openapi/domains/fundamental.py` | `Fundamental` / `AsyncFundamental` (12) |
| `src/gangtise_openapi/domains/ai.py` | `AI` / `AsyncAI` (14 endpoints incl. 2 async polled) |
| `src/gangtise_openapi/domains/vault.py` | `Vault` / `AsyncVault` (10) |
| `src/gangtise_openapi/domains/alternative.py` | `Alternative` / `AsyncAlternative` (2) |
| `tests/conftest.py` | `respx` fixture, `Config` fixture, fake credentials |
| `tests/unit/test_*.py` | one file per `_module` |
| `tests/endpoints/test_<domain>.py` | smoke tests, sync + async |
| `tests/integration/test_live.py` | `@pytest.mark.live`, manual-only |

**Sizing rules:** every file ≤ 400 lines. `insight.py` and `ai.py` may need split (`insight_list.py` + `insight_download.py`); decide during the corresponding task if a single file exceeds 400 lines.

**Naming rule:** TS endpoint keys use kebab-case (`quote.day-kline`). Python wrapper method names use snake_case (`quote.day_kline`). The endpoint registry preserves the kebab-case keys verbatim.

**Body field translation rule:** the TS CLI builds request bodies using camelCase (`securityCode`, `startDate`, `fiscalYear`). Python wrappers accept snake_case kwargs (`security_code`, `start_date`, `fiscal_year`) and translate inside the wrapper. The translation is mechanical; each domain task lists the explicit mapping per endpoint.

---

## Conventions Used Throughout

**Test layout:** `tests/conftest.py` provides:

```python
import httpx
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config

@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak",
        secret_key="sk",
        token=None,
        token_cache_path=tmp_path / "token.json",
        timeout_ms=5000,
        page_concurrency=3,
    )

@pytest.fixture
def respx_mock():
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        yield router

@pytest.fixture
def sync_client(config, respx_mock):
    # pre-seed token cache so endpoint tests skip the login round-trip
    config.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    config.token_cache_path.write_text(
        '{"accessToken":"tok","expiresIn":3600,"time":0,"expiresAt":9999999999}'
    )
    return GangtiseClient(_config=config)
```

**Successful envelope shape (for mocks):**
```python
{"code": "000000", "status": True, "data": <payload>}
```

**Error envelope shape:**
```python
{"code": "999997", "status": False, "msg": "no permission"}
```

**Commit message convention:** Conventional Commits. Examples:
- `chore: scaffold pyproject + tooling`
- `feat(auth): add TokenCache`
- `feat(endpoints): register quote domain endpoints`
- `test(quote): add day-kline smoke tests`
- `fix(transport): retry on httpx ReadTimeout`

---

## Phase 1 — Project Scaffold

### Task 1: Initialize pyproject + tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `CHANGELOG.md`
- Create: `src/gangtise_openapi/__about__.py`
- Create: `src/gangtise_openapi/__init__.py`
- Create: `src/gangtise_openapi/py.typed`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "gangtise-openapi"
dynamic = ["version"]
description = "Python SDK for Gangtise OpenAPI"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
authors = [{ name = "gangtiser" }]
keywords = ["gangtise", "finance", "openapi", "sdk", "quote", "research"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Financial and Insurance Industry",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Office/Business :: Financial",
]
dependencies = [
    "httpx>=0.27",
    "pandas>=2.0",
    "anyio>=4.0",
]

[project.urls]
Homepage = "https://github.com/gangtiser/gangtise-openapi-python"
Source = "https://github.com/gangtiser/gangtise-openapi-python"
Issues = "https://github.com/gangtiser/gangtise-openapi-python/issues"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-anyio>=0.0.0; python_version<'0'",
    "anyio[trio]>=4.0",
    "respx>=0.21",
    "ruff>=0.6",
    "mypy>=1.10",
    "pandas-stubs",
    "types-requests",
]

[tool.hatch.version]
path = "src/gangtise_openapi/__about__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/gangtise_openapi"]

[tool.hatch.build.targets.sdist]
include = ["src/", "README.md", "LICENSE", "CHANGELOG.md", "pyproject.toml"]

[tool.ruff]
line-length = 100
target-version = "py310"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B008"]

[tool.mypy]
files = ["src"]
python_version = "3.10"
strict = true
warn_unused_ignores = true
warn_return_any = true
ignore_missing_imports = false

[[tool.mypy.overrides]]
module = ["pandas.*", "respx.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "live: hits real Gangtise API (skipped by default; run with `pytest -m live`)",
]
```

(The `pytest-anyio>=0.0.0; python_version<'0'` marker is intentional — anyio ships its own pytest plugin, so a separate `pytest-anyio` is unnecessary; this line is a no-op placeholder to confirm we rely on `anyio[trio]`.)

- [ ] **Step 2: Write `.gitignore`**

```gitignore
.venv/
dist/
build/
*.egg-info/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.env
.env.*
!.env.example
.DS_Store
```

- [ ] **Step 3: Write `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 gangtiser

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Write minimal `README.md`**

```markdown
# gangtise-openapi

Python SDK for [Gangtise OpenAPI](https://open.gangtise.com).

```bash
pip install gangtise-openapi
```

```python
from gangtise_openapi import gangtise
df = gangtise.quote.day_kline(security="000001.SH", start_date="2026-01-01")
```

Set `GANGTISE_ACCESS_KEY` and `GANGTISE_SECRET_KEY` in your environment.

For the full endpoint reference, see the [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) project; this SDK reaches feature parity with that CLI.

## License

MIT
```

- [ ] **Step 5: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial scaffold (pyproject, tooling, CI).
```

- [ ] **Step 6: Write `src/gangtise_openapi/__about__.py`**

```python
__version__ = "0.1.0.dev0"
```

- [ ] **Step 7: Write placeholder `src/gangtise_openapi/__init__.py`**

```python
from gangtise_openapi.__about__ import __version__

__all__ = ["__version__"]
```

- [ ] **Step 8: Write empty `src/gangtise_openapi/py.typed`**

```
```

(Empty file, PEP 561 marker.)

- [ ] **Step 9: Verify the package imports**

Run: `uv sync --all-extras && uv run python -c "import gangtise_openapi; print(gangtise_openapi.__version__)"`
Expected: prints `0.1.0.dev0`

- [ ] **Step 10: Verify tooling runs clean**

Run: `uv run ruff check . && uv run mypy src`
Expected: both exit 0 (no files to lint yet beyond `__init__.py` / `__about__.py`).

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml .gitignore LICENSE README.md CHANGELOG.md src
git commit -m "chore: scaffold pyproject, tooling, package skeleton"
```

---

### Task 2: CI workflow + GitHub repo metadata

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}
      - name: Sync dependencies
        run: uv sync --all-extras
      - name: Ruff lint
        run: uv run ruff check .
      - name: Ruff format check
        run: uv run ruff format --check .
      - name: Mypy
        run: uv run mypy src
      - name: Pytest
        run: uv run pytest -m "not live"
```

- [ ] **Step 2: Commit**

```bash
git add .github
git commit -m "ci: add ruff + mypy + pytest workflow on 3.10/3.12"
```

---

## Phase 2 — Foundation Modules

### Task 3: Exception tree (`_errors.py`)

**Files:**
- Create: `src/gangtise_openapi/_errors.py`
- Create: `tests/unit/test_errors.py`

- [ ] **Step 1: Write the failing test `tests/unit/test_errors.py`**

```python
import pytest

from gangtise_openapi._errors import (
    ApiError,
    ConfigError,
    DownloadError,
    GangtiseError,
    ValidationError,
)


def test_exception_hierarchy():
    assert issubclass(ConfigError, GangtiseError)
    assert issubclass(ApiError, GangtiseError)
    assert issubclass(ValidationError, GangtiseError)
    assert issubclass(DownloadError, GangtiseError)


def test_api_error_carries_metadata():
    err = ApiError("boom", code="999997", status_code=403, details={"raw": "x"})
    assert err.code == "999997"
    assert err.status_code == 403
    assert err.details == {"raw": "x"}


def test_api_error_known_code_attaches_hint():
    err = ApiError("permission denied", code="999997")
    assert "未开通" in err.hint
    assert "未开通" in str(err)


def test_api_error_unknown_code_no_hint():
    err = ApiError("weird", code="123456")
    assert err.hint is None
    assert str(err) == "weird"


def test_api_error_no_code():
    err = ApiError("network down")
    assert err.code is None
    assert err.hint is None


def test_config_error_subclass_only():
    with pytest.raises(GangtiseError):
        raise ConfigError("missing key")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gangtise_openapi._errors'`

- [ ] **Step 3: Write `src/gangtise_openapi/_errors.py`**

```python
from __future__ import annotations

from typing import Any

ERROR_HINTS: dict[str, str] = {
    "999999": "Gangtise 系统错误，请稍后重试。",
    "999997": "当前账号未开通该接口权限。",
    "999995": "当前账号积分不足。",
    "900002": "请求缺少 uid。",
    "900001": "请求参数为空或缺少必填项。",
    "8000014": "GANGTISE_ACCESS_KEY 错误。",
    "8000015": "GANGTISE_SECRET_KEY 错误。",
    "8000016": "开发账号状态异常。",
    "8000018": "开发账号已到期。",
    "903301": "今日调用次数已达上限。",
    "410110": "内容生成中，请稍后重试。",
    "410111": "内容生成失败，请勿重试。",
}


class GangtiseError(Exception):
    """Base class for all gangtise-openapi exceptions."""


class ConfigError(GangtiseError):
    """Missing or invalid configuration (env vars, cache file)."""


class ValidationError(GangtiseError):
    """Local argument validation failed before the request was issued."""


class DownloadError(GangtiseError):
    """Filesystem error while streaming a download."""


class ApiError(GangtiseError):
    """HTTP 4xx/5xx or business-envelope failure."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details
        self.hint = ERROR_HINTS.get(code) if code else None

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} — {self.hint}" if self.hint else base
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_errors.py tests/unit/test_errors.py
git commit -m "feat(errors): add exception tree with code hints"
```

---

### Task 4: Config dataclass + env loader (`_config.py`)

**Files:**
- Create: `src/gangtise_openapi/_config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test `tests/unit/test_config.py`**

```python
from pathlib import Path

import pytest

from gangtise_openapi._config import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_MS,
    Config,
    load_config,
)


def test_defaults(monkeypatch):
    for k in [
        "GANGTISE_BASE_URL",
        "GANGTISE_ACCESS_KEY",
        "GANGTISE_SECRET_KEY",
        "GANGTISE_TOKEN",
        "GANGTISE_TOKEN_CACHE_PATH",
        "GANGTISE_TIMEOUT_MS",
        "GANGTISE_PAGE_CONCURRENCY",
        "GANGTISE_VERBOSE",
    ]:
        monkeypatch.delenv(k, raising=False)
    cfg = load_config()
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.timeout_ms == DEFAULT_TIMEOUT_MS
    assert cfg.access_key is None
    assert cfg.secret_key is None
    assert cfg.token is None
    assert cfg.page_concurrency == 5
    assert cfg.verbose is False
    assert cfg.token_cache_path == Path.home() / ".config" / "gangtise" / "token.json"


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_BASE_URL", "https://test.example")
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "AK")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "SK")
    monkeypatch.setenv("GANGTISE_TOKEN", "tok")
    monkeypatch.setenv("GANGTISE_TIMEOUT_MS", "12345")
    monkeypatch.setenv("GANGTISE_PAGE_CONCURRENCY", "9")
    monkeypatch.setenv("GANGTISE_VERBOSE", "1")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))

    cfg = load_config()
    assert cfg.base_url == "https://test.example"
    assert cfg.access_key == "AK"
    assert cfg.secret_key == "SK"
    assert cfg.token == "tok"
    assert cfg.timeout_ms == 12345
    assert cfg.page_concurrency == 9
    assert cfg.verbose is True
    assert cfg.token_cache_path == tmp_path / "tok.json"


def test_invalid_timeout_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GANGTISE_TIMEOUT_MS", "not-a-number")
    cfg = load_config()
    assert cfg.timeout_ms == DEFAULT_TIMEOUT_MS


def test_invalid_concurrency_falls_back(monkeypatch):
    monkeypatch.setenv("GANGTISE_PAGE_CONCURRENCY", "0")
    cfg = load_config()
    assert cfg.page_concurrency == 5


def test_config_equality():
    a = Config(base_url="x", access_key="ak", secret_key="sk")
    b = Config(base_url="x", access_key="ak", secret_key="sk")
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://open.gangtise.com"
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


def _positive_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


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
            os.environ.get("GANGTISE_PAGE_CONCURRENCY"), DEFAULT_PAGE_CONCURRENCY
        ),
        verbose=_truthy(os.environ.get("GANGTISE_VERBOSE")),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_config.py tests/unit/test_config.py
git commit -m "feat(config): add Config dataclass + env loader"
```

---

### Task 5: Token cache (`_auth.py`)

**Files:**
- Create: `src/gangtise_openapi/_auth.py`
- Create: `tests/unit/test_auth.py`

- [ ] **Step 1: Write the failing test `tests/unit/test_auth.py`**

```python
import json
import time

import pytest

from gangtise_openapi._auth import (
    TokenCache,
    is_cache_valid,
    normalize_token,
    read_token_cache,
    require_credentials,
    write_token_cache,
)
from gangtise_openapi._errors import ConfigError


def _make_cache(*, expires_at: int) -> TokenCache:
    return TokenCache(
        access_token="tok",
        expires_in=3600,
        time=int(time.time()),
        expires_at=expires_at,
        uid=1,
        user_name="alice",
        tenant_id=10,
    )


def test_normalize_token_adds_bearer():
    assert normalize_token("abc") == "Bearer abc"


def test_normalize_token_preserves_bearer():
    assert normalize_token("Bearer abc") == "Bearer abc"


def test_is_cache_valid_with_buffer():
    now = int(time.time())
    assert is_cache_valid(_make_cache(expires_at=now + 1000)) is True


def test_is_cache_valid_near_expiry_fails_buffer():
    now = int(time.time())
    assert is_cache_valid(_make_cache(expires_at=now + 10)) is False


def test_is_cache_valid_none():
    assert is_cache_valid(None) is False


def test_read_token_cache_roundtrip(tmp_path):
    path = tmp_path / "tok.json"
    cache = _make_cache(expires_at=int(time.time()) + 1000)
    write_token_cache(path, cache)
    loaded = read_token_cache(path)
    assert loaded == cache
    assert (path.stat().st_mode & 0o777) == 0o600


def test_read_token_cache_missing(tmp_path):
    assert read_token_cache(tmp_path / "nope.json") is None


def test_read_token_cache_corrupt(tmp_path):
    path = tmp_path / "tok.json"
    path.write_text("not json", encoding="utf8")
    assert read_token_cache(path) is None


def test_read_token_cache_partial_schema(tmp_path):
    path = tmp_path / "tok.json"
    path.write_text(json.dumps({"accessToken": "x"}), encoding="utf8")
    assert read_token_cache(path) is None


def test_require_credentials_missing():
    with pytest.raises(ConfigError):
        require_credentials(None, None)
    with pytest.raises(ConfigError):
        require_credentials("ak", None)


def test_require_credentials_ok():
    assert require_credentials("ak", "sk") == ("ak", "sk")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_auth.py`**

```python
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from gangtise_openapi._errors import ConfigError


@dataclass(frozen=True)
class TokenCache:
    access_token: str
    expires_in: int
    time: int
    expires_at: int
    uid: int | None = None
    user_name: str | None = None
    tenant_id: int | None = None


_BUFFER_SECONDS = 300


def normalize_token(token: str) -> str:
    return token if token.startswith("Bearer ") else f"Bearer {token}"


def is_cache_valid(cache: TokenCache | None, buffer_seconds: int = _BUFFER_SECONDS) -> bool:
    if cache is None or not cache.access_token or not cache.expires_at:
        return False
    now = int(time.time())
    return (cache.expires_at - buffer_seconds) > now


def read_token_cache(path: Path) -> TokenCache | None:
    try:
        raw = path.read_text(encoding="utf8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    access_token = data.get("accessToken")
    expires_at = data.get("expiresAt")
    if not isinstance(access_token, str) or not isinstance(expires_at, int):
        return None
    return TokenCache(
        access_token=access_token,
        expires_in=int(data.get("expiresIn", 0)),
        time=int(data.get("time", 0)),
        expires_at=expires_at,
        uid=data.get("uid"),
        user_name=data.get("userName"),
        tenant_id=data.get("tenantId"),
    )


def write_token_cache(path: Path, cache: TokenCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "accessToken": cache.access_token,
        "expiresIn": cache.expires_in,
        "time": cache.time,
        "expiresAt": cache.expires_at,
        "uid": cache.uid,
        "userName": cache.user_name,
        "tenantId": cache.tenant_id,
    }
    # Atomic write: temp file + rename to avoid partial reads.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def require_credentials(access_key: str | None, secret_key: str | None) -> tuple[str, str]:
    if not access_key or not secret_key:
        raise ConfigError("Missing GANGTISE_ACCESS_KEY or GANGTISE_SECRET_KEY")
    return access_key, secret_key
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_auth.py tests/unit/test_auth.py
git commit -m "feat(auth): add TokenCache with atomic write + 0600 perms"
```

---

### Task 6: Endpoint registry (`_endpoints.py`)

**Files:**
- Create: `src/gangtise_openapi/_endpoints.py`
- Create: `tests/unit/test_endpoints.py`
- Reference: `/Users/martin/Documents/claude_workspace/gangtise-openapi-cli/src/core/endpoints.ts` (the 73 endpoints — translate verbatim)

- [ ] **Step 1: Write the failing test `tests/unit/test_endpoints.py`**

```python
import pytest

from gangtise_openapi._endpoints import ENDPOINTS, EndpointDef, lookup


def test_endpoint_count():
    assert len(ENDPOINTS) == 73


def test_lookup_known_endpoint():
    ep = lookup("quote.day-kline")
    assert ep.key == "quote.day-kline"
    assert ep.method == "POST"
    assert ep.path == "/application/open-quote/kline/daily"
    assert ep.kind == "json"


def test_lookup_unknown_raises():
    with pytest.raises(KeyError):
        lookup("does.not.exist")


def test_pagination_endpoints_have_max_page_size():
    paginated_keys = [k for k, ep in ENDPOINTS.items() if ep.pagination is not None]
    assert "insight.opinion.list" in paginated_keys
    for key in paginated_keys:
        assert ENDPOINTS[key].pagination is not None
        assert ENDPOINTS[key].pagination.max_page_size > 0


def test_download_endpoints_have_kind_download():
    download_keys = [k for k, ep in ENDPOINTS.items() if ep.kind == "download"]
    assert "insight.summary.download" in download_keys
    assert "insight.research.download" in download_keys
    for key in download_keys:
        assert ENDPOINTS[key].method in {"GET", "POST"}


def test_local_lookup_endpoints_marked():
    for key in [
        "lookup.research-areas.list",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "lookup.industries.list",
        "lookup.regions.list",
        "lookup.announcement-categories.list",
        "lookup.industry-codes.list",
        "lookup.theme-ids.list",
    ]:
        assert ENDPOINTS[key].path.startswith("/guide/")


def test_dataclass_equality():
    a = EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")
    b = EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_endpoints.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_endpoints.py`**

Translate `/Users/martin/Documents/claude_workspace/gangtise-openapi-cli/src/core/endpoints.ts` verbatim. The TS file enumerates 73 `EndpointDefinition` entries; copy every `key`, `method`, `path`, `kind`, `description`, and `pagination` into a Python dict.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HttpMethod = Literal["GET", "POST"]
EndpointKind = Literal["json", "download"]


@dataclass(frozen=True)
class Pagination:
    max_page_size: int


@dataclass(frozen=True)
class EndpointDef:
    key: str
    method: HttpMethod
    path: str
    kind: EndpointKind
    description: str
    pagination: Pagination | None = None


def _ep(
    key: str,
    method: HttpMethod,
    path: str,
    description: str,
    *,
    kind: EndpointKind = "json",
    paginated: int | None = None,
) -> EndpointDef:
    return EndpointDef(
        key=key,
        method=method,
        path=path,
        kind=kind,
        description=description,
        pagination=Pagination(max_page_size=paginated) if paginated else None,
    )


ENDPOINTS: dict[str, EndpointDef] = {
    # auth
    "auth.login": _ep(
        "auth.login", "POST",
        "/application/auth/oauth/open/loginV2",
        "Get access token",
    ),

    # lookup (served from local data; path is a sentinel, not hit on the network)
    "lookup.research-areas.list": _ep(
        "lookup.research-areas.list", "GET", "/guide/research-area-local",
        "List research areas from local docs",
    ),
    "lookup.broker-orgs.list": _ep(
        "lookup.broker-orgs.list", "GET", "/guide/broker-orgs-local",
        "List broker orgs from local docs",
    ),
    "lookup.meeting-orgs.list": _ep(
        "lookup.meeting-orgs.list", "GET", "/guide/meeting-orgs-local",
        "List meeting orgs from local docs",
    ),
    "lookup.industries.list": _ep(
        "lookup.industries.list", "GET", "/guide/industries-local",
        "List industries from local docs",
    ),
    "lookup.regions.list": _ep(
        "lookup.regions.list", "GET", "/guide/regions-local",
        "List regions from local docs",
    ),
    "lookup.announcement-categories.list": _ep(
        "lookup.announcement-categories.list", "GET",
        "/guide/announcement-categories-local",
        "List announcement categories from local docs",
    ),
    "lookup.industry-codes.list": _ep(
        "lookup.industry-codes.list", "GET", "/guide/industry-codes-local",
        "List Shenwan industry codes from local docs",
    ),
    "lookup.theme-ids.list": _ep(
        "lookup.theme-ids.list", "GET", "/guide/theme-ids-local",
        "List theme IDs from local docs",
    ),

    # ... CONTINUE for the remaining 64 endpoints from endpoints.ts.
    # IMPORTANT: copy every entry verbatim. The translation rule is:
    #   { key, method, path, kind, description, pagination: {enabled: true, maxPageSize: N} }
    # becomes:
    #   _ep(key, method, path, description, kind=..., paginated=N)
    # `kind` defaults to "json"; pass kind="download" when the TS entry has kind: "download".
}


def lookup(key: str) -> EndpointDef:
    try:
        return ENDPOINTS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown endpoint key: {key}") from exc
```

The full 73-entry dictionary is produced by translating `endpoints.ts`. The translation is mechanical — write each entry, do not paraphrase descriptions. Pagination flags appear on these TS entries: `insight.opinion.list`, `insight.summary.list`, `insight.roadshow.list`, `insight.site-visit.list`, `insight.strategy.list`, `insight.forum.list`, `insight.research.list`, `insight.foreign-report.list`, `insight.announcement.list`, `insight.announcement-hk.list`, `insight.foreign-opinion.list`, `insight.independent-opinion.list`, `ai.security-clue.list`, `vault.drive.list`, `vault.record.list`, `vault.my-conference.list`, `vault.wechat-message.list`, `vault.wechat-chatroom.list` (all `maxPageSize: 50`). Confirm by `grep -n pagination` on `endpoints.ts`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_endpoints.py -v`
Expected: 7 passed. `test_endpoint_count` will fail until all 73 entries are present.

- [ ] **Step 5: Add a parity sanity check**

Append to `tests/unit/test_endpoints.py`:

```python
def test_all_endpoint_keys_match_ts_source():
    expected = {
        "auth.login",
        "lookup.research-areas.list",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "lookup.industries.list",
        "lookup.regions.list",
        "lookup.announcement-categories.list",
        "lookup.industry-codes.list",
        "lookup.theme-ids.list",
        "insight.opinion.list",
        "insight.summary.list",
        "insight.summary.download",
        "insight.roadshow.list",
        "insight.site-visit.list",
        "insight.strategy.list",
        "insight.forum.list",
        "insight.research.list",
        "insight.research.download",
        "insight.foreign-report.list",
        "insight.foreign-report.download",
        "insight.announcement.list",
        "insight.announcement.download",
        "insight.announcement-hk.list",
        "insight.announcement-hk.download",
        "insight.foreign-opinion.list",
        "insight.independent-opinion.list",
        "insight.independent-opinion.download",
        "reference.securities-search",
        "quote.day-kline",
        "quote.day-kline-hk",
        "quote.day-kline-us",
        "quote.index-day-kline",
        "quote.minute-kline",
        "quote.realtime",
        "fundamental.income-statement",
        "fundamental.income-statement-quarterly",
        "fundamental.balance-sheet",
        "fundamental.cash-flow",
        "fundamental.cash-flow-quarterly",
        "fundamental.income-statement-hk",
        "fundamental.balance-sheet-hk",
        "fundamental.cash-flow-hk",
        "fundamental.main-business",
        "fundamental.valuation-analysis",
        "fundamental.top-holders",
        "fundamental.earning-forecast",
        "ai.knowledge-batch",
        "ai.knowledge-resource.download",
        "ai.security-clue.list",
        "ai.one-pager",
        "ai.investment-logic",
        "ai.peer-comparison",
        "ai.earnings-review.get-id",
        "ai.earnings-review.get-content",
        "ai.theme-tracking",
        "ai.research-outline",
        "ai.hot-topic",
        "ai.management-discuss-announcement",
        "ai.management-discuss-earnings-call",
        "ai.viewpoint-debate.get-id",
        "ai.viewpoint-debate.get-content",
        "vault.drive.list",
        "vault.drive.download",
        "vault.record.list",
        "vault.record.download",
        "vault.my-conference.list",
        "vault.my-conference.download",
        "vault.wechat-message.list",
        "vault.wechat-chatroom.list",
        "vault.stock-pool.list",
        "vault.stock-pool.stocks",
        "alternative.edb-search",
        "alternative.edb-data",
    }
    assert set(ENDPOINTS.keys()) == expected
```

Re-run: `uv run pytest tests/unit/test_endpoints.py -v` → 8 passed.

- [ ] **Step 6: Commit**

```bash
git add src/gangtise_openapi/_endpoints.py tests/unit/test_endpoints.py
git commit -m "feat(endpoints): register 73 endpoint definitions from TS source"
```

---

### Task 7: Bundled lookup data (`_lookup/`)

**Files:**
- Create: `src/gangtise_openapi/_lookup/__init__.py`
- Create: `src/gangtise_openapi/_lookup/research_areas.py`
- Create: `src/gangtise_openapi/_lookup/broker_orgs.py`
- Create: `src/gangtise_openapi/_lookup/meeting_orgs.py`
- Create: `src/gangtise_openapi/_lookup/industries.py`
- Create: `src/gangtise_openapi/_lookup/regions.py`
- Create: `src/gangtise_openapi/_lookup/announcement_categories.py`
- Create: `src/gangtise_openapi/_lookup/industry_codes.py`
- Create: `src/gangtise_openapi/_lookup/theme_ids.py`
- Create: `tests/unit/test_lookup.py`
- Reference: `/Users/martin/Documents/claude_workspace/gangtise-openapi-cli/src/core/lookupData/<topic>.ts` for the actual list contents.

- [ ] **Step 1: Translate each TS lookup file into a Python module**

Each TS file exports a single array. Convert to a Python list of dicts using snake_case-preserving field names (most are already simple `id` / `name` / `code` fields). Example for `research_areas.py`:

```python
from __future__ import annotations

RESEARCH_AREAS: list[dict[str, str | int]] = [
    {"id": 1, "name": "宏观策略"},
    {"id": 2, "name": "固定收益"},
    # ... (translate every entry from research-areas.ts)
]
```

Repeat the pattern for `broker_orgs.py`, `meeting_orgs.py`, `industries.py`, `regions.py`, `announcement_categories.py`, `industry_codes.py`, `theme_ids.py`. Preserve every entry, key names, and field order from the TS source.

For nested industries (the TS `industries.ts` may have hierarchical entries), translate the structure faithfully — if the TS exports `{ id, name, children: [...] }`, the Python list keeps the same shape.

- [ ] **Step 2: Write `src/gangtise_openapi/_lookup/__init__.py`**

```python
from __future__ import annotations

from typing import Any

from gangtise_openapi._lookup.announcement_categories import ANNOUNCEMENT_CATEGORIES
from gangtise_openapi._lookup.broker_orgs import BROKER_ORGS
from gangtise_openapi._lookup.industries import INDUSTRIES
from gangtise_openapi._lookup.industry_codes import INDUSTRY_CODES
from gangtise_openapi._lookup.meeting_orgs import MEETING_ORGS
from gangtise_openapi._lookup.regions import REGIONS
from gangtise_openapi._lookup.research_areas import RESEARCH_AREAS
from gangtise_openapi._lookup.theme_ids import THEME_IDS

LOOKUP_LOADERS: dict[str, list[Any]] = {
    "lookup.research-areas.list": RESEARCH_AREAS,
    "lookup.broker-orgs.list": BROKER_ORGS,
    "lookup.meeting-orgs.list": MEETING_ORGS,
    "lookup.industries.list": INDUSTRIES,
    "lookup.regions.list": REGIONS,
    "lookup.announcement-categories.list": ANNOUNCEMENT_CATEGORIES,
    "lookup.industry-codes.list": INDUSTRY_CODES,
    "lookup.theme-ids.list": THEME_IDS,
}


def get_lookup(endpoint_key: str) -> list[Any]:
    try:
        return LOOKUP_LOADERS[endpoint_key]
    except KeyError as exc:
        raise KeyError(f"Unknown lookup endpoint: {endpoint_key}") from exc
```

- [ ] **Step 3: Write `tests/unit/test_lookup.py`**

```python
import pytest

from gangtise_openapi._lookup import LOOKUP_LOADERS, get_lookup


def test_all_eight_lookup_keys_present():
    assert set(LOOKUP_LOADERS.keys()) == {
        "lookup.research-areas.list",
        "lookup.broker-orgs.list",
        "lookup.meeting-orgs.list",
        "lookup.industries.list",
        "lookup.regions.list",
        "lookup.announcement-categories.list",
        "lookup.industry-codes.list",
        "lookup.theme-ids.list",
    }


def test_each_loader_returns_non_empty_list():
    for key, data in LOOKUP_LOADERS.items():
        assert isinstance(data, list), key
        assert len(data) > 0, key
        assert isinstance(data[0], dict), key


def test_get_lookup_unknown():
    with pytest.raises(KeyError):
        get_lookup("nope")
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/unit/test_lookup.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_lookup tests/unit/test_lookup.py
git commit -m "feat(lookup): bundle 8 local lookup datasets from TS source"
```

---

## Phase 3 — Sync Transport, Retry, Pagination, Sharding, Polling

### Task 8: Sync transport (`_transport.py`)

**Files:**
- Create: `src/gangtise_openapi/_transport.py`
- Create: `tests/unit/test_transport.py`

The transport layer owns: building the httpx Client, attaching the auth header, executing one request, unwrapping the envelope, classifying retryable errors, and exponential-backoff retry.

- [ ] **Step 1: Write the failing test `tests/unit/test_transport.py`**

```python
import httpx
import pytest
import respx

from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError
from gangtise_openapi._transport import (
    RETRYABLE_API_CODES,
    RETRYABLE_HTTP_STATUS,
    build_sync_client,
    is_retryable_error,
    request_json,
    unwrap_envelope,
)


def _endpoint(path: str = "/p") -> EndpointDef:
    return EndpointDef(key="x", method="POST", path=path, kind="json", description="d")


def test_retryable_http_status_set():
    assert {429, 500, 502, 503, 504} == set(RETRYABLE_HTTP_STATUS)


def test_retryable_api_codes_set():
    assert "999999" in RETRYABLE_API_CODES


def test_unwrap_success():
    out = unwrap_envelope({"code": "000000", "status": True, "data": {"x": 1}})
    assert out == {"x": 1}


def test_unwrap_success_via_success_field():
    out = unwrap_envelope({"code": "000001", "success": True, "data": [1, 2]})
    assert out == [1, 2]


def test_unwrap_failure_raises():
    with pytest.raises(ApiError) as exc:
        unwrap_envelope({"code": "999997", "status": False, "msg": "no perm"})
    assert exc.value.code == "999997"


def test_unwrap_non_envelope_passthrough():
    # The TS client treats non-envelope payloads as the actual data.
    out = unwrap_envelope([1, 2, 3])
    assert out == [1, 2, 3]


def test_is_retryable_classifies_5xx():
    assert is_retryable_error(ApiError("boom", code=None, status_code=503))


def test_is_retryable_classifies_429():
    assert is_retryable_error(ApiError("boom", code=None, status_code=429))


def test_is_retryable_classifies_999999():
    assert is_retryable_error(ApiError("boom", code="999999"))


def test_is_retryable_rejects_other_api_codes():
    assert not is_retryable_error(ApiError("perm", code="999997", status_code=403))


def test_is_retryable_classifies_httpx_read_timeout():
    assert is_retryable_error(httpx.ReadTimeout("timeout"))


def test_is_retryable_classifies_httpx_connect_error():
    assert is_retryable_error(httpx.ConnectError("nope"))


def test_request_json_success(respx_mock, config):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 1}})
    )
    with build_sync_client(config) as http:
        out = request_json(http, config, _endpoint("/p"), body={"k": "v"}, token="tok")
    assert out == {"v": 1}


def test_request_json_envelope_error_raises(respx_mock, config):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "999997", "status": False, "msg": "no perm"})
    )
    with build_sync_client(config) as http:
        with pytest.raises(ApiError) as exc:
            request_json(http, config, _endpoint("/p"), body={}, token="tok")
    assert exc.value.code == "999997"


def test_request_json_http_500_retries_then_succeeds(respx_mock, config):
    route = respx_mock.post("/p").mock(
        side_effect=[
            httpx.Response(500, json={"code": "500", "status": False, "msg": "boom"}),
            httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 2}}),
        ]
    )
    with build_sync_client(config) as http:
        out = request_json(http, config, _endpoint("/p"), body={}, token="tok")
    assert out == {"v": 2}
    assert route.call_count == 2


def test_request_json_http_500_exhausts_retries_raises(respx_mock, config):
    respx_mock.post("/p").mock(return_value=httpx.Response(500, text="oops"))
    with build_sync_client(config) as http:
        with pytest.raises(ApiError):
            request_json(http, config, _endpoint("/p"), body={}, token="tok")


def test_request_json_attaches_authorization_header(respx_mock, config):
    route = respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {}})
    )
    with build_sync_client(config) as http:
        request_json(http, config, _endpoint("/p"), body={}, token="tok")
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_transport.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_transport.py`**

```python
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

import httpx

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError

logger = logging.getLogger("gangtise_openapi")

RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
RETRYABLE_API_CODES: frozenset[str] = frozenset({"999999"})
_RETRYABLE_HTTPX_EXC: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
)


def build_sync_client(config: Config) -> httpx.Client:
    timeout = httpx.Timeout(config.timeout_ms / 1000.0)
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=16, keepalive_expiry=60)
    return httpx.Client(base_url=config.base_url, timeout=timeout, limits=limits)


def _success_code(code: Any) -> bool:
    return str(code) in {"000000", "0"}


def is_envelope(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if "code" not in payload:
        return False
    return any(k in payload for k in ("msg", "data", "success", "status"))


def unwrap_envelope(payload: Any, status_code: int | None = None) -> Any:
    if not is_envelope(payload):
        return payload
    code = payload.get("code")
    code_str = str(code) if code is not None else None
    ok = (
        payload.get("status") is True
        or payload.get("success") is True
        or _success_code(code)
    )
    if not ok:
        raise ApiError(
            payload.get("msg") or "API request failed",
            code=code_str,
            status_code=status_code,
            details=payload,
        )
    return payload.get("data") if "data" in payload else payload


def is_retryable_error(error: BaseException) -> bool:
    if isinstance(error, ApiError):
        if error.status_code in RETRYABLE_HTTP_STATUS:
            return True
        if error.code in RETRYABLE_API_CODES:
            return True
        return False
    if isinstance(error, _RETRYABLE_HTTPX_EXC):
        return True
    return False


def _backoff_delay(attempt: int, base_ms: float = 400.0, max_ms: float = 4000.0) -> float:
    jitter = random.random() * base_ms
    return min(max_ms, base_ms * (2 ** attempt) + jitter) / 1000.0


def _do_request(
    http: httpx.Client,
    config: Config,
    endpoint: EndpointDef,
    body: Any,
    *,
    token: str | None,
    query: dict[str, str | int] | None,
) -> tuple[int, Any]:
    headers: dict[str, str] = {"content-type": "application/json"}
    if token is not None:
        headers["Authorization"] = normalize_token(token)
    started = time.monotonic()
    response = http.request(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
        content=None if endpoint.method == "GET" else json.dumps(body or {}).encode("utf8"),
    )
    elapsed_ms = (time.monotonic() - started) * 1000.0
    logger.debug(
        "[gangtise] %5.0fms %s %s (status=%s, bytes=%s)",
        elapsed_ms,
        endpoint.method,
        endpoint.path,
        response.status_code,
        len(response.content),
    )
    try:
        parsed = response.json()
    except ValueError:
        if response.status_code >= 400:
            raise ApiError(
                f"API request failed (HTTP {response.status_code})",
                status_code=response.status_code,
                details=response.text[:500],
            )
        raise ApiError(
            "Failed to parse API response",
            status_code=response.status_code,
            details=response.text[:500],
        )
    return response.status_code, parsed


def request_json(
    http: httpx.Client,
    config: Config,
    endpoint: EndpointDef,
    *,
    body: Any = None,
    token: str | None,
    query: dict[str, str | int] | None = None,
    max_retries: int = 2,
) -> Any:
    attempt = 0
    while True:
        try:
            status_code, parsed = _do_request(
                http, config, endpoint, body, token=token, query=query
            )
            if status_code >= 400:
                if is_envelope(parsed):
                    code = parsed.get("code")
                    raise ApiError(
                        parsed.get("msg") or f"API request failed (HTTP {status_code})",
                        code=str(code) if code is not None else None,
                        status_code=status_code,
                        details=parsed,
                    )
                raise ApiError(
                    f"API request failed (HTTP {status_code})",
                    status_code=status_code,
                    details=parsed,
                )
            return unwrap_envelope(parsed, status_code=status_code)
        except Exception as error:
            if attempt >= max_retries or not is_retryable_error(error):
                raise
            time.sleep(_backoff_delay(attempt))
            attempt += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_transport.py -v`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_transport.py tests/unit/test_transport.py
git commit -m "feat(transport): sync httpx wrapper with retry + envelope unwrap"
```

---

### Task 9: Pagination (`_pagination.py`)

**Files:**
- Create: `src/gangtise_openapi/_pagination.py`
- Create: `tests/unit/test_pagination.py`

Provides a sync `collect_paginated` that calls a generic page fetcher. The fetcher signature lets us reuse the same orchestration for the async client (Task 23).

- [ ] **Step 1: Write the failing test `tests/unit/test_pagination.py`**

```python
import pytest

from gangtise_openapi._endpoints import EndpointDef, Pagination
from gangtise_openapi._errors import ValidationError
from gangtise_openapi._pagination import collect_paginated


def _ep(max_page_size: int = 50) -> EndpointDef:
    return EndpointDef(
        key="x", method="POST", path="/p", kind="json",
        description="d", pagination=Pagination(max_page_size=max_page_size),
    )


def test_single_page_when_total_fits():
    pages_seen: list[tuple[int, int]] = []

    def fetch(body):
        pages_seen.append((body["from"], body["size"]))
        return {"total": 3, "list": [{"i": 1}, {"i": 2}, {"i": 3}]}

    out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"total": 3, "list": [{"i": 1}, {"i": 2}, {"i": 3}]}
    assert pages_seen == [(0, 50)]


def test_fetches_remaining_pages_concurrently():
    pages_seen: list[tuple[int, int]] = []

    def fetch(body):
        pages_seen.append((body["from"], body["size"]))
        if body["from"] == 0:
            return {"total": 12, "list": [{"i": j} for j in range(5)]}
        # remaining pages
        f, s = body["from"], body["size"]
        return {"total": 12, "list": [{"i": j} for j in range(f, f + s)]}

    out = collect_paginated(_ep(max_page_size=5), body={}, fetch=fetch, concurrency=4)
    assert out["total"] == 12
    assert [row["i"] for row in out["list"]] == list(range(12))


def test_requested_size_truncates_collected():
    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 100, "list": [{"i": j} for j in range(f, f + s)]}

    out = collect_paginated(_ep(max_page_size=5), body={"size": 7}, fetch=fetch, concurrency=3)
    assert len(out["list"]) == 7
    assert [row["i"] for row in out["list"]] == list(range(7))


def test_non_paginated_response_returned_verbatim():
    def fetch(body):
        return {"total": 0, "list": []}

    out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"total": 0, "list": []}


def test_unexpected_shape_returned_as_is():
    def fetch(body):
        return {"unexpected": "shape"}

    out = collect_paginated(_ep(), body={}, fetch=fetch, concurrency=3)
    assert out == {"unexpected": "shape"}


def test_invalid_from_raises():
    def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        collect_paginated(_ep(), body={"from": -1}, fetch=fetch, concurrency=3)


def test_invalid_size_raises():
    def fetch(body):
        raise AssertionError("should not call")

    with pytest.raises(ValidationError):
        collect_paginated(_ep(), body={"size": 0}, fetch=fetch, concurrency=3)


def test_max_pages_cap():
    # total=10000 with maxPageSize=1 would request 10000 pages; we cap at 1000.
    def fetch(body):
        f, s = body["from"], body["size"]
        return {"total": 10000, "list": [{"i": j} for j in range(f, f + s)]}

    out = collect_paginated(_ep(max_page_size=1), body={}, fetch=fetch, concurrency=2)
    assert len(out["list"]) == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_pagination.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_pagination.py`**

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ValidationError

MAX_PAGES = 1000

PageFetcher = Callable[[dict[str, Any]], Any]


def _is_paginated_response(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("total"), int)
        and isinstance(value.get("list"), list)
    )


def _validate_paging_args(body: dict[str, Any]) -> None:
    if "from" in body:
        v = body["from"]
        if not isinstance(v, int) or v < 0:
            raise ValidationError("Invalid 'from': expected a non-negative int")
    if "size" in body and body["size"] is not None:
        v = body["size"]
        if not isinstance(v, int) or v <= 0:
            raise ValidationError("Invalid 'size': expected a positive int")


def collect_paginated(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: PageFetcher,
    concurrency: int,
) -> Any:
    if endpoint.pagination is None:
        return fetch(body)

    initial = {k: v for k, v in body.items()}
    _validate_paging_args(initial)

    start_from = initial.get("from", 0) if isinstance(initial.get("from"), int) else 0
    requested_size = initial.get("size") if isinstance(initial.get("size"), int) else None
    max_page_size = endpoint.pagination.max_page_size

    first_page_size = max_page_size if requested_size is None else min(max_page_size, requested_size)
    first_body = {**initial, "from": start_from, "size": first_page_size}
    first_page = fetch(first_body)

    if not _is_paginated_response(first_page):
        return first_page

    total = first_page["total"]
    collected: list[Any] = list(first_page["list"])

    if first_page["list"] and len(first_page["list"]) < first_page_size:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}

    available = max(total - start_from, 0)
    target = available if requested_size is None else min(requested_size, available)

    if len(collected) >= target:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}

    remaining_requests: list[dict[str, Any]] = []
    next_from = start_from + len(first_page["list"])
    end_from = start_from + target
    while next_from < end_from:
        size = min(max_page_size, end_from - next_from)
        remaining_requests.append({**initial, "from": next_from, "size": size})
        next_from += size
    if len(remaining_requests) + 1 > MAX_PAGES:
        remaining_requests = remaining_requests[: MAX_PAGES - 1]

    if remaining_requests:
        workers = max(1, min(concurrency, len(remaining_requests)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pages = list(pool.map(fetch, remaining_requests))
        for page in pages:
            if _is_paginated_response(page) and page["list"]:
                collected.extend(page["list"])

    if requested_size is not None:
        collected = collected[:requested_size]
    return {**first_page, "total": total, "list": collected}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_pagination.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_pagination.py tests/unit/test_pagination.py
git commit -m "feat(pagination): auto-paginate with ThreadPool fan-out (cap 1000 pages)"
```

---

### Task 10: K-line sharding (`_quote_sharding.py`)

**Files:**
- Create: `src/gangtise_openapi/_quote_sharding.py`
- Create: `tests/unit/test_quote_sharding.py`

Per spec §7: A-share day-kline = 1 day/shard, HK = 2, US = 1, index = 30. When `security == "all"` and the user did not pass `limit`, the wrapper injects `limit=10000` (TS source `cli.ts:307-321`). Shards are pulled concurrently using the same thread pool size as pagination.

- [ ] **Step 1: Write the failing test `tests/unit/test_quote_sharding.py`**

```python
import datetime as dt

import pytest

from gangtise_openapi._quote_sharding import (
    SHARD_DAYS,
    plan_shards,
    needs_limit_injection,
)


def test_shard_days_table():
    assert SHARD_DAYS["quote.day-kline"] == 1
    assert SHARD_DAYS["quote.day-kline-hk"] == 2
    assert SHARD_DAYS["quote.day-kline-us"] == 1
    assert SHARD_DAYS["quote.index-day-kline"] == 30


def test_plan_shards_single_day():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 5),
        end_date=dt.date(2026, 1, 5),
        days_per_shard=1,
    )
    assert shards == [(dt.date(2026, 1, 5), dt.date(2026, 1, 5))]


def test_plan_shards_two_days_a_share():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 2),
        days_per_shard=1,
    )
    assert shards == [
        (dt.date(2026, 1, 1), dt.date(2026, 1, 1)),
        (dt.date(2026, 1, 2), dt.date(2026, 1, 2)),
    ]


def test_plan_shards_hk_two_per_shard():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
        days_per_shard=2,
    )
    assert shards == [
        (dt.date(2026, 1, 1), dt.date(2026, 1, 2)),
        (dt.date(2026, 1, 3), dt.date(2026, 1, 4)),
        (dt.date(2026, 1, 5), dt.date(2026, 1, 5)),
    ]


def test_plan_shards_index_30_per_shard():
    shards = plan_shards(
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 3, 31),
        days_per_shard=30,
    )
    assert shards[0][0] == dt.date(2026, 1, 1)
    assert shards[-1][1] == dt.date(2026, 3, 31)
    for s, e in shards:
        assert (e - s).days <= 29


def test_plan_shards_invalid_order():
    with pytest.raises(ValueError):
        plan_shards(
            start_date=dt.date(2026, 1, 5),
            end_date=dt.date(2026, 1, 1),
            days_per_shard=1,
        )


def test_needs_limit_injection_only_for_all_market():
    assert needs_limit_injection(security="all", explicit_limit=None) is True
    assert needs_limit_injection(security="all", explicit_limit=5000) is False
    assert needs_limit_injection(security="000001.SH", explicit_limit=None) is False
    assert needs_limit_injection(security=["all"], explicit_limit=None) is True
    assert needs_limit_injection(security=["000001.SH"], explicit_limit=None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_quote_sharding.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_quote_sharding.py`**

```python
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Sequence

SHARD_DAYS: dict[str, int] = {
    "quote.day-kline": 1,
    "quote.day-kline-hk": 2,
    "quote.day-kline-us": 1,
    "quote.index-day-kline": 30,
}

DEFAULT_FULL_MARKET_LIMIT = 10_000


def plan_shards(
    *,
    start_date: dt.date,
    end_date: dt.date,
    days_per_shard: int,
) -> list[tuple[dt.date, dt.date]]:
    if end_date < start_date:
        raise ValueError("end_date < start_date")
    if days_per_shard <= 0:
        raise ValueError("days_per_shard must be positive")
    shards: list[tuple[dt.date, dt.date]] = []
    cursor = start_date
    one_day = dt.timedelta(days=1)
    while cursor <= end_date:
        shard_end = cursor + dt.timedelta(days=days_per_shard - 1)
        if shard_end > end_date:
            shard_end = end_date
        shards.append((cursor, shard_end))
        cursor = shard_end + one_day
    return shards


def _is_all_market(security: Any) -> bool:
    if security == "all":
        return True
    if isinstance(security, (list, tuple)) and "all" in security:
        return True
    return False


def needs_limit_injection(*, security: Any, explicit_limit: int | None) -> bool:
    return _is_all_market(security) and explicit_limit is None


ShardFetcher = Callable[[tuple[dt.date, dt.date]], Any]


def fetch_shards(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: ShardFetcher,
    concurrency: int,
) -> list[Any]:
    if not shards:
        return []
    workers = max(1, min(concurrency, len(shards)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fetch, shards))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_quote_sharding.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_quote_sharding.py tests/unit/test_quote_sharding.py
git commit -m "feat(sharding): K-line date sharding planner + concurrent executor"
```

---

### Task 11: Async-content polling (`_async_content.py`)

**Files:**
- Create: `src/gangtise_openapi/_async_content.py`
- Create: `tests/unit/test_async_content.py`

Per spec §5 Path B: poll the same `*.get-content` endpoint, classify `410110` (pending) and `410111` (terminal failure), backoff 5/8/13/20/30/30…, `POLL_MAX_ATTEMPTS = 14`.

- [ ] **Step 1: Write the failing test `tests/unit/test_async_content.py`**

```python
import pytest

from gangtise_openapi._async_content import (
    POLL_MAX_ATTEMPTS,
    next_delay_seconds,
    poll_content,
)
from gangtise_openapi._errors import ApiError


def test_poll_max_attempts():
    assert POLL_MAX_ATTEMPTS == 14


def test_next_delay_sequence():
    # 5s, 8s, 13s, 20s, 30s, 30s, ...
    sequence = [next_delay_seconds(attempt) for attempt in range(1, 8)]
    assert sequence == [5, 8, 13, 20, 30, 30, 30]


def test_poll_returns_on_first_ready():
    calls = []

    def fetch():
        calls.append(1)
        return {"content": "ready"}

    out = poll_content(fetch, sleep=lambda s: None)
    assert out == {"content": "ready"}
    assert len(calls) == 1


def test_poll_retries_on_410110_then_succeeds():
    state = {"i": 0}
    delays: list[float] = []

    def fetch():
        state["i"] += 1
        if state["i"] < 3:
            raise ApiError("pending", code="410110")
        return {"content": "done"}

    out = poll_content(fetch, sleep=delays.append)
    assert out == {"content": "done"}
    assert state["i"] == 3
    assert delays == [5.0, 8.0]


def test_poll_terminal_failure_raises_immediately():
    def fetch():
        raise ApiError("terminal", code="410111")

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert exc.value.code == "410111"


def test_poll_unrelated_error_propagates():
    def fetch():
        raise ApiError("auth bad", code="8000014")

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert exc.value.code == "8000014"


def test_poll_exhaustion_raises():
    def fetch():
        raise ApiError("pending", code="410110")

    with pytest.raises(ApiError) as exc:
        poll_content(fetch, sleep=lambda s: None)
    assert "14 attempts" in str(exc.value)


def test_poll_missing_content_keeps_polling():
    state = {"i": 0}

    def fetch():
        state["i"] += 1
        if state["i"] < 2:
            return {"content": None}
        return {"content": "ready"}

    out = poll_content(fetch, sleep=lambda s: None)
    assert out == {"content": "ready"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_async_content.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_async_content.py`**

```python
from __future__ import annotations

import time
from typing import Any, Callable, Iterable

from gangtise_openapi._errors import ApiError

POLL_MAX_ATTEMPTS = 14
_INITIAL_DELAY_S = 5.0
_MAX_DELAY_S = 30.0
_GROWTH = 1.6

CODE_PENDING = "410110"
CODE_TERMINAL = "410111"


def next_delay_seconds(attempt: int) -> float:
    grown = _INITIAL_DELAY_S * (_GROWTH ** (attempt - 1))
    return min(_MAX_DELAY_S, float(round(grown)))


Fetcher = Callable[[], Any]
Sleeper = Callable[[float], None]


def _classify(error: ApiError) -> str:
    if error.code == CODE_PENDING:
        return "pending"
    if error.code == CODE_TERMINAL:
        return "terminal"
    return "other"


def poll_content(
    fetch: Fetcher,
    *,
    sleep: Sleeper = time.sleep,
    max_attempts: int = POLL_MAX_ATTEMPTS,
) -> Any:
    last_pending: ApiError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fetch()
        except ApiError as error:
            kind = _classify(error)
            if kind == "terminal":
                raise ApiError(
                    "Content generation failed (terminal). Do not retry.",
                    code=CODE_TERMINAL,
                ) from error
            if kind == "other":
                raise
            last_pending = error
        else:
            if isinstance(result, dict) and result.get("content") is not None:
                return result
        if attempt < max_attempts:
            sleep(next_delay_seconds(attempt))
    raise ApiError(
        f"Content not available after {max_attempts} attempts",
        code=CODE_PENDING,
    ) from last_pending
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_async_content.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_async_content.py tests/unit/test_async_content.py
git commit -m "feat(async-content): poll *.get-content with 410110/410111 classification"
```

---

## Phase 4 — Sync Client, Normalize, Facade

### Task 12: DataFrame normalization (`_normalize.py`)

**Files:**
- Create: `src/gangtise_openapi/_normalize.py`
- Create: `tests/unit/test_normalize.py`

Per spec §3 step 5: tabular endpoints return `pandas.DataFrame` by default. The wrapper declares a `schema` (ordered list of columns); the normalizer enforces column presence and order, leaves dtype inference to pandas, and tolerates missing columns by inserting empty Series.

- [ ] **Step 1: Write the failing test `tests/unit/test_normalize.py`**

```python
import pandas as pd
import pytest

from gangtise_openapi._normalize import to_dataframe


def test_empty_list_returns_empty_frame_with_schema():
    df = to_dataframe([], schema=["a", "b", "c"])
    assert list(df.columns) == ["a", "b", "c"]
    assert len(df) == 0


def test_column_order_locked_by_schema():
    rows = [{"b": 2, "a": 1, "c": 3}, {"b": 5, "a": 4, "c": 6}]
    df = to_dataframe(rows, schema=["a", "b", "c"])
    assert list(df.columns) == ["a", "b", "c"]
    assert df["a"].tolist() == [1, 4]


def test_missing_column_added_as_null():
    rows = [{"a": 1}, {"a": 2}]
    df = to_dataframe(rows, schema=["a", "b"])
    assert list(df.columns) == ["a", "b"]
    assert df["b"].isna().all()


def test_extra_columns_dropped():
    rows = [{"a": 1, "extra": "drop"}]
    df = to_dataframe(rows, schema=["a"])
    assert list(df.columns) == ["a"]


def test_no_schema_returns_all_columns():
    rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    df = to_dataframe(rows, schema=None)
    assert set(df.columns) == {"a", "b"}
    assert len(df) == 2


def test_non_list_input_raises():
    with pytest.raises(TypeError):
        to_dataframe({"not": "a list"}, schema=["x"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_normalize.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_normalize.py`**

```python
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd


def to_dataframe(
    rows: Sequence[dict[str, Any]] | list[dict[str, Any]],
    *,
    schema: Sequence[str] | None,
) -> pd.DataFrame:
    if not isinstance(rows, list):
        raise TypeError(f"to_dataframe expects a list of dicts, got {type(rows).__name__}")
    if not rows:
        return pd.DataFrame({col: pd.Series(dtype="object") for col in (schema or [])})
    df = pd.DataFrame(rows)
    if schema is None:
        return df
    for col in schema:
        if col not in df.columns:
            df[col] = pd.Series([None] * len(df), dtype="object")
    return df[list(schema)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_normalize.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/_normalize.py tests/unit/test_normalize.py
git commit -m "feat(normalize): rows -> DataFrame with schema-locked column order"
```

---

### Task 13: GangtiseClient (`_client.py`)

**Files:**
- Create: `src/gangtise_openapi/_client.py`
- Create: `tests/unit/test_client.py`
- Modify: `src/gangtise_openapi/__init__.py` (add `GangtiseClient` to public exports)

The sync client owns: lazy login, token cache, the public `_call(endpoint_key, body, query)` method, and the registry of domain accessors. Domains are attached in Task 14+ once the domain classes exist; for now the client exposes `_call` and `login()` only.

- [ ] **Step 1: Write the failing test `tests/unit/test_client.py`**

```python
import json

import httpx
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._errors import ApiError, ConfigError


@pytest.fixture
def client_config(tmp_path) -> Config:
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


def test_call_unknown_endpoint_raises(client_config):
    with GangtiseClient(_config=client_config) as client:
        with pytest.raises(KeyError):
            client._call("does.not.exist")


def test_call_with_env_token_skips_login(client_config, monkeypatch):
    cfg = Config(
        base_url="https://api.test",
        access_key=None,
        secret_key=None,
        token="env-tok",
        token_cache_path=client_config.token_cache_path,
        title_cache_path=client_config.title_cache_path,
        timeout_ms=5000,
        page_concurrency=3,
    )
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/auth/oauth/open/loginV2")
        # The login endpoint must NOT be hit because GANGTISE_TOKEN is set.
        with GangtiseClient(_config=cfg) as client:
            router.post("/application/open-quote/quote/realtime").mock(
                return_value=httpx.Response(
                    200, json={"code": "000000", "status": True, "data": []}
                )
            )
            client._call("quote.realtime", body={"securityList": ["000001.SH"]})
        assert route.call_count == 0


def test_call_login_happens_when_no_token(client_config):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "fresh",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "x",
                        "tenantId": 1,
                    },
                },
            )
        )
        ep = router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": []})
        )
        with GangtiseClient(_config=client_config) as client:
            client._call("quote.realtime", body={"securityList": ["x"]})
        assert ep.calls.last.request.headers["Authorization"] == "Bearer fresh"


def test_call_auth_code_8000014_triggers_one_refresh(client_config, tmp_path):
    # Pre-seed an obviously expired-looking token to force refresh path.
    client_config.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    client_config.token_cache_path.write_text(
        json.dumps({
            "accessToken": "stale", "expiresIn": 1, "time": 0, "expiresAt": 9999999999,
        })
    )
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "refreshed",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "x",
                        "tenantId": 1,
                    },
                },
            )
        )
        ep_route = router.post("/application/open-quote/quote/realtime").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"code": "8000014", "status": False, "msg": "bad access key"},
                ),
                httpx.Response(200, json={"code": "000000", "status": True, "data": []}),
            ]
        )
        with GangtiseClient(_config=client_config) as client:
            out = client._call("quote.realtime", body={"securityList": ["x"]})
        assert out == []
        assert ep_route.call_count == 2


def test_login_returns_authorization_and_cache(client_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000",
                    "status": True,
                    "data": {
                        "accessToken": "tok",
                        "expiresIn": 3600,
                        "time": 0,
                        "uid": 1,
                        "userName": "x",
                        "tenantId": 1,
                    },
                },
            )
        )
        with GangtiseClient(_config=client_config) as client:
            result = client.login()
        assert result["authorization"] == "Bearer tok"
        assert result["cache"]["access_token"] == "tok"


def test_call_lookup_endpoint_returns_local_data(client_config):
    with GangtiseClient(_config=client_config) as client:
        out = client._call("lookup.research-areas.list")
    assert isinstance(out, list)
    assert len(out) > 0


def test_missing_credentials_raises(tmp_path):
    cfg = Config(
        base_url="https://api.test",
        access_key=None,
        secret_key=None,
        token=None,
        token_cache_path=tmp_path / "token.json",
        title_cache_path=tmp_path / "title.json",
    )
    with GangtiseClient(_config=cfg) as client:
        with pytest.raises(ConfigError):
            client._call("quote.realtime", body={"securityList": ["x"]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_client.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_client.py`**

```python
from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Any

import httpx

from gangtise_openapi._auth import (
    TokenCache,
    is_cache_valid,
    normalize_token,
    read_token_cache,
    require_credentials,
    write_token_cache,
)
from gangtise_openapi._config import Config, load_config
from gangtise_openapi._endpoints import ENDPOINTS, EndpointDef, lookup
from gangtise_openapi._errors import ApiError
from gangtise_openapi._lookup import LOOKUP_LOADERS
from gangtise_openapi._pagination import collect_paginated
from gangtise_openapi._transport import (
    build_sync_client,
    request_json,
)

AUTH_RETRY_CODES = frozenset({"8000014", "8000015"})


class GangtiseClient:
    """Synchronous client for the Gangtise OpenAPI."""

    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        _config: Config | None = None,
    ) -> None:
        if _config is not None:
            cfg = _config
        else:
            cfg = load_config()
            overrides: dict[str, Any] = {}
            if access_key is not None:
                overrides["access_key"] = access_key
            if secret_key is not None:
                overrides["secret_key"] = secret_key
            if base_url is not None:
                overrides["base_url"] = base_url
            if token is not None:
                overrides["token"] = token
            if timeout is not None:
                overrides["timeout_ms"] = int(timeout * 1000)
            if overrides:
                cfg = Config(**{**asdict(cfg), **overrides})
        self._config = cfg
        self._http: httpx.Client | None = None
        self._memo_cache: TokenCache | None = None
        self._lock = threading.Lock()

    @property
    def config(self) -> Config:
        return self._config

    def __enter__(self) -> "GangtiseClient":
        self._http = build_sync_client(self._config)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _http_client(self) -> httpx.Client:
        if self._http is None:
            self._http = build_sync_client(self._config)
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    # ---- Auth ----

    def _get_token(self, force_refresh: bool = False) -> str:
        if self._config.token and not force_refresh:
            return self._config.token
        if not force_refresh:
            if is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            disk = read_token_cache(self._config.token_cache_path)
            if is_cache_valid(disk):
                self._memo_cache = disk
                assert disk is not None
                return disk.access_token
        with self._lock:
            if not force_refresh and is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            return self._refresh_token()

    def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = request_json(
            self._http_client(), self._config, endpoint, body=body, token=None
        )
        access_token = result["accessToken"]
        expires_in = int(result.get("expiresIn", 0))
        cache = TokenCache(
            access_token=access_token,
            expires_in=expires_in,
            time=int(result.get("time", int(time.time()))),
            expires_at=int(time.time()) + expires_in,
            uid=result.get("uid"),
            user_name=result.get("userName"),
            tenant_id=result.get("tenantId"),
        )
        self._memo_cache = cache
        write_token_cache(self._config.token_cache_path, cache)
        return access_token

    # ---- Public surface used by domain wrappers ----

    def login(self) -> dict[str, Any]:
        token = self._get_token()
        cache = self._memo_cache or read_token_cache(self._config.token_cache_path)
        return {
            "authorization": normalize_token(token),
            "cache": asdict(cache) if cache else None,
        }

    def _call(
        self,
        endpoint_key: str,
        body: Any = None,
        query: dict[str, str | int] | None = None,
    ) -> Any:
        endpoint = lookup(endpoint_key)
        if endpoint.path.startswith("/guide/"):
            return list(LOOKUP_LOADERS[endpoint.key])

        def fetch_one(page_body: dict[str, Any]) -> Any:
            return self._request_once(endpoint, page_body, query)

        if endpoint.pagination is not None:
            return collect_paginated(
                endpoint,
                body=body or {},
                fetch=fetch_one,
                concurrency=self._config.page_concurrency,
            )
        return self._request_once(endpoint, body or {}, query)

    def _request_once(
        self,
        endpoint: EndpointDef,
        body: Any,
        query: dict[str, str | int] | None,
    ) -> Any:
        try:
            token = self._get_token()
            return request_json(
                self._http_client(),
                self._config,
                endpoint,
                body=body,
                token=token,
                query=query,
            )
        except ApiError as error:
            if error.code in AUTH_RETRY_CODES and self._config.access_key and self._config.secret_key:
                self._memo_cache = None
                token = self._get_token(force_refresh=True)
                return request_json(
                    self._http_client(),
                    self._config,
                    endpoint,
                    body=body,
                    token=token,
                    query=query,
                )
            raise
```

- [ ] **Step 4: Update `src/gangtise_openapi/__init__.py`**

```python
from gangtise_openapi.__about__ import __version__
from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import (
    ApiError,
    ConfigError,
    DownloadError,
    GangtiseError,
    ValidationError,
)

__all__ = [
    "__version__",
    "GangtiseClient",
    "ApiError",
    "ConfigError",
    "DownloadError",
    "GangtiseError",
    "ValidationError",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_client.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add src/gangtise_openapi/_client.py src/gangtise_openapi/__init__.py tests/unit/test_client.py
git commit -m "feat(client): GangtiseClient with lazy login, token refresh, auth-code retry"
```

---

### Task 14: Facade singleton (`_facade.py`)

**Files:**
- Create: `src/gangtise_openapi/_facade.py`
- Create: `tests/unit/test_facade.py`
- Modify: `src/gangtise_openapi/__init__.py` (expose `gangtise`)

Per spec §6: `gangtise.configure(...)` is idempotent for same config, raises for different config, and `gangtise.reset()` lets users start over. Domain accessors are attached lazily — they are added in Phase 5 as each domain module lands; the facade just dispatches via `__getattr__`.

- [ ] **Step 1: Write the failing test `tests/unit/test_facade.py`**

```python
import pytest

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._errors import ConfigError
from gangtise_openapi._facade import _Facade


@pytest.fixture(autouse=True)
def isolated_facade(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "ak")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "sk")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "token.json"))
    monkeypatch.setenv("GANGTISE_TITLE_CACHE_PATH", str(tmp_path / "title.json"))
    yield


def test_configure_pins_default_client():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    assert isinstance(f._client, GangtiseClient)
    assert f._client.config.base_url == "https://test.one"


def test_configure_same_config_is_idempotent():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    client_one = f._client
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    assert f._client is client_one


def test_configure_different_config_raises():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    with pytest.raises(ConfigError):
        f.configure(base_url="https://test.two", access_key="ak", secret_key="sk")


def test_configure_replace_true_switches():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    f.configure(
        base_url="https://test.two",
        access_key="ak",
        secret_key="sk",
        replace=True,
    )
    assert f._client.config.base_url == "https://test.two"


def test_reset_clears_default_client():
    f = _Facade()
    f.configure(base_url="https://test.one", access_key="ak", secret_key="sk")
    assert f._client is not None
    f.reset()
    assert f._client is None


def test_lazy_default_client_on_attribute_access(monkeypatch):
    monkeypatch.setenv("GANGTISE_BASE_URL", "https://lazy.test")
    f = _Facade()
    client = f._ensure_client()
    assert client.config.base_url == "https://lazy.test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_facade.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `src/gangtise_openapi/_facade.py`**

```python
from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Any

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config, load_config
from gangtise_openapi._errors import ConfigError

_CONFIG_FIELDS_FOR_EQUALITY = (
    "base_url",
    "access_key",
    "secret_key",
    "token",
    "token_cache_path",
    "title_cache_path",
    "timeout_ms",
    "page_concurrency",
)


def _signature(cfg: Config) -> tuple[Any, ...]:
    return tuple(getattr(cfg, field) for field in _CONFIG_FIELDS_FOR_EQUALITY)


class _Facade:
    """Module-level singleton exposing namespace-style access to the SDK."""

    def __init__(self) -> None:
        self._client: GangtiseClient | None = None
        self._signature: tuple[Any, ...] | None = None
        self._domains: dict[str, Any] = {}
        self._lock = threading.Lock()

    # ---- Lifecycle ----

    def configure(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        replace: bool = False,
    ) -> GangtiseClient:
        with self._lock:
            new_client = GangtiseClient(
                access_key=access_key,
                secret_key=secret_key,
                base_url=base_url,
                token=token,
                timeout=timeout,
            )
            new_signature = _signature(new_client.config)
            if self._client is not None and not replace:
                if new_signature == self._signature:
                    new_client.close()
                    return self._client
                new_client.close()
                raise ConfigError(
                    "default client already configured with different settings; "
                    "call gangtise.reset() or pass replace=True"
                )
            self._close_client()
            self._client = new_client
            self._signature = new_signature
            return new_client

    def reset(self) -> None:
        with self._lock:
            self._close_client()

    def _close_client(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._signature = None
        self._domains.clear()

    def _ensure_client(self) -> GangtiseClient:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    cfg = load_config()
                    self._client = GangtiseClient(_config=cfg)
                    self._signature = _signature(cfg)
        assert self._client is not None
        return self._client

    # ---- Domain attribute dispatch (filled in by Phase 5 tasks) ----

    _DOMAIN_FACTORIES: dict[str, str] = {}
    # mapping populated in Phase 5: "quote" -> "gangtise_openapi.domains.quote:Quote", etc.

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._DOMAIN_FACTORIES:
            raise AttributeError(f"unknown domain or attribute: {name!r}")
        if name not in self._domains:
            module_path, class_name = self._DOMAIN_FACTORIES[name].split(":")
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            self._domains[name] = cls(self._ensure_client())
        return self._domains[name]


gangtise = _Facade()
```

- [ ] **Step 4: Update `src/gangtise_openapi/__init__.py`**

```python
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
    "__version__",
    "gangtise",
    "GangtiseClient",
    "ApiError",
    "ConfigError",
    "DownloadError",
    "GangtiseError",
    "ValidationError",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_facade.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/gangtise_openapi/_facade.py src/gangtise_openapi/__init__.py tests/unit/test_facade.py
git commit -m "feat(facade): _Facade singleton with idempotent configure + reset"
```

---

## Phase 5 — Sync Domain Wrappers

Phase 5 establishes the wrapper pattern with `auth`, `lookup`, `reference`, then iterates per remaining domain. Each domain task:

1. Adds an entry to `_Facade._DOMAIN_FACTORIES`.
2. Creates `src/gangtise_openapi/domains/<name>.py` with a class that takes `GangtiseClient` and exposes one method per endpoint.
3. Adds smoke tests under `tests/endpoints/test_<name>.py`.

**Wrapper pattern (used in every domain):**

```python
from __future__ import annotations

from typing import Any

import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._normalize import to_dataframe


class _DomainBase:
    def __init__(self, client: GangtiseClient) -> None:
        self._client = client
```

Each public method:
1. Maps snake_case kwargs to the TS camelCase body.
2. Calls `self._client._call("<endpoint.key>", body=...)`.
3. Returns `to_dataframe(rows, schema=...)` for tabular endpoints, or `result` for everything else.
4. Accepts `raw: bool = False` — when `True`, returns the underlying `dict`/`list`.

**Smoke-test pattern (one per endpoint, plus one async sibling later):**

```python
import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config


def test_quote_realtime(tmp_path):
    cfg = Config(
        base_url="https://api.test",
        access_key=None,
        secret_key=None,
        token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000,
        page_concurrency=3,
    )
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "000000", "status": True,
                    "data": [{"securityCode": "000001.SH", "close": 12.3}],
                },
            )
        )
        from gangtise_openapi.domains.quote import Quote
        with GangtiseClient(_config=cfg) as client:
            df = Quote(client).realtime(security=["000001.SH"])
        assert isinstance(df, pd.DataFrame)
        assert df.iloc[0]["close"] == 12.3
        sent_body = route.calls.last.request.read()
        assert b"securityList" in sent_body
```

Subsequent tasks reuse this pattern. Each task spells out the bodies + schemas; the implementer transcribes per-endpoint mappings from `gangtise-openapi-cli/src/cli.ts`.

### Task 15: Auth + Lookup + Reference domains (pattern-establishing)

**Files:**
- Create: `src/gangtise_openapi/domains/__init__.py`
- Create: `src/gangtise_openapi/domains/auth.py`
- Create: `src/gangtise_openapi/domains/lookup.py`
- Create: `src/gangtise_openapi/domains/reference.py`
- Create: `tests/endpoints/__init__.py`
- Create: `tests/endpoints/test_auth.py`
- Create: `tests/endpoints/test_lookup.py`
- Create: `tests/endpoints/test_reference.py`
- Modify: `src/gangtise_openapi/_facade.py:_DOMAIN_FACTORIES`

- [ ] **Step 1: Create `src/gangtise_openapi/domains/__init__.py`**

```python
from gangtise_openapi.domains.auth import Auth
from gangtise_openapi.domains.lookup import Lookup
from gangtise_openapi.domains.reference import Reference

__all__ = ["Auth", "Lookup", "Reference"]
```

- [ ] **Step 2: Create `src/gangtise_openapi/domains/auth.py`**

```python
from __future__ import annotations

from typing import Any

from gangtise_openapi._auth import read_token_cache
from gangtise_openapi._client import GangtiseClient


class Auth:
    """`gangtise.auth.*` — authentication helpers."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def login(self) -> dict[str, Any]:
        """Force a login (or reuse cached token) and return the bearer header."""
        return self._client.login()

    def status(self) -> dict[str, Any]:
        """Inspect the current token state without forcing a network call."""
        cfg = self._client.config
        cache = read_token_cache(cfg.token_cache_path)
        return {
            "has_env_token": bool(cfg.token),
            "has_cached_token": bool(cache and cache.access_token),
            "cache": {
                "access_token": cache.access_token if cache else None,
                "expires_at": cache.expires_at if cache else None,
                "uid": cache.uid if cache else None,
                "user_name": cache.user_name if cache else None,
                "tenant_id": cache.tenant_id if cache else None,
            } if cache else None,
        }
```

- [ ] **Step 3: Create `src/gangtise_openapi/domains/lookup.py`**

```python
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._normalize import to_dataframe


_LOOKUP_ENDPOINT_BY_METHOD = {
    "research_areas": ("lookup.research-areas.list", ["id", "name"]),
    "broker_orgs": ("lookup.broker-orgs.list", ["id", "name"]),
    "meeting_orgs": ("lookup.meeting-orgs.list", ["id", "name"]),
    "industries": ("lookup.industries.list", ["id", "name", "children"]),
    "regions": ("lookup.regions.list", ["code", "name"]),
    "announcement_categories": (
        "lookup.announcement-categories.list",
        ["id", "name"],
    ),
    "industry_codes": ("lookup.industry-codes.list", ["code", "name"]),
    "theme_ids": ("lookup.theme-ids.list", ["id", "name"]),
}


class Lookup:
    """`gangtise.lookup.*` — local lookup tables (no network)."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def _fetch(self, method_name: str, *, raw: bool):
        endpoint_key, schema = _LOOKUP_ENDPOINT_BY_METHOD[method_name]
        data = self._client._call(endpoint_key)
        return data if raw else to_dataframe(data, schema=schema)

    def research_areas(self, *, raw: bool = False):
        return self._fetch("research_areas", raw=raw)

    def broker_orgs(self, *, raw: bool = False):
        return self._fetch("broker_orgs", raw=raw)

    def meeting_orgs(self, *, raw: bool = False):
        return self._fetch("meeting_orgs", raw=raw)

    def industries(self, *, raw: bool = False):
        return self._fetch("industries", raw=raw)

    def regions(self, *, raw: bool = False):
        return self._fetch("regions", raw=raw)

    def announcement_categories(self, *, raw: bool = False):
        return self._fetch("announcement_categories", raw=raw)

    def industry_codes(self, *, raw: bool = False):
        return self._fetch("industry_codes", raw=raw)

    def theme_ids(self, *, raw: bool = False):
        return self._fetch("theme_ids", raw=raw)
```

(If any of the schema lists above turn out wrong against the actual TS lookup data — e.g., `industries.ts` exports `{ id, name, children: [...] }` but with different keys — adjust the schema to match. The schema in the wrapper governs the DataFrame columns; the underlying data dictates the keys.)

- [ ] **Step 4: Create `src/gangtise_openapi/domains/reference.py`**

```python
from __future__ import annotations

from typing import Any

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._normalize import to_dataframe

_SCHEMA_SECURITIES_SEARCH = [
    "code",
    "name",
    "market",
    "category",
    "industry",
    "industryCode",
    "pinyin",
]


class Reference:
    """`gangtise.reference.*` — reference data lookups."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def securities_search(
        self,
        *,
        keyword: str,
        raw: bool = False,
    ):
        body = {"keyword": keyword}
        result = self._client._call("reference.securities-search", body=body)
        rows = result if isinstance(result, list) else result.get("list", [])
        if raw:
            return rows
        return to_dataframe(rows, schema=_SCHEMA_SECURITIES_SEARCH)
```

(If `reference.securities-search` returns a top-level dict with extra metadata, preserve the same wrapper shape; if the response is a plain list, the `isinstance` branch above handles it. Validate against the TS `cli.ts` call to `client.call("reference.securities-search", { keyword: ... })`.)

- [ ] **Step 5: Update `src/gangtise_openapi/_facade.py:_DOMAIN_FACTORIES`**

```python
    _DOMAIN_FACTORIES: dict[str, str] = {
        "auth": "gangtise_openapi.domains.auth:Auth",
        "lookup": "gangtise_openapi.domains.lookup:Lookup",
        "reference": "gangtise_openapi.domains.reference:Reference",
    }
```

- [ ] **Step 6: Create `tests/endpoints/__init__.py` (empty file)**

```
```

- [ ] **Step 7: Create `tests/endpoints/test_auth.py`**

```python
import json

import httpx
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.auth import Auth


def _cfg(tmp_path, *, token: str | None = "tok") -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token=token,
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        timeout_ms=5000, page_concurrency=3,
    )


def test_auth_status_reports_cached_token(tmp_path):
    cfg = _cfg(tmp_path, token=None)
    cfg.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.token_cache_path.write_text(
        json.dumps({
            "accessToken": "abc", "expiresIn": 3600, "time": 0, "expiresAt": 9999999999,
        })
    )
    with GangtiseClient(_config=cfg) as client:
        status = Auth(client).status()
    assert status["has_cached_token"] is True
    assert status["cache"]["access_token"] == "abc"


def test_auth_login_returns_authorization(tmp_path):
    cfg = _cfg(tmp_path, token=None)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/auth/oauth/open/loginV2").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {
                        "accessToken": "fresh", "expiresIn": 3600, "time": 0,
                        "uid": 1, "userName": "u", "tenantId": 1,
                    },
                },
            )
        )
        with GangtiseClient(_config=cfg) as client:
            result = Auth(client).login()
    assert result["authorization"] == "Bearer fresh"
```

- [ ] **Step 8: Create `tests/endpoints/test_lookup.py`**

```python
import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.lookup import Lookup


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_research_areas_returns_dataframe(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:
        df = Lookup(client).research_areas()
    assert isinstance(df, pd.DataFrame)
    assert {"id", "name"}.issubset(df.columns)
    assert len(df) > 0


def test_research_areas_raw_returns_list(tmp_path):
    with GangtiseClient(_config=_cfg(tmp_path)) as client:
        rows = Lookup(client).research_areas(raw=True)
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
```

- [ ] **Step 9: Create `tests/endpoints/test_reference.py`**

```python
import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.reference import Reference


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_securities_search(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-reference/securities/search").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": [
                        {"code": "000001.SH", "name": "上证指数", "market": "SH"},
                    ],
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Reference(client).securities_search(keyword="上证")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["code"] == "000001.SH"
```

- [ ] **Step 10: Run tests**

Run: `uv run pytest tests/endpoints -v`
Expected: 5 passed.

- [ ] **Step 11: Commit**

```bash
git add src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/domains/auth.py \
        src/gangtise_openapi/domains/lookup.py \
        src/gangtise_openapi/domains/reference.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/__init__.py \
        tests/endpoints/test_auth.py \
        tests/endpoints/test_lookup.py \
        tests/endpoints/test_reference.py
git commit -m "feat(domains): auth + lookup + reference wrappers"
```

---

### Task 16: Insight domain (19 endpoints)

**Files:**
- Create: `src/gangtise_openapi/domains/insight.py`
- Create: `tests/endpoints/test_insight.py`
- Modify: `src/gangtise_openapi/_facade.py` (add `insight` to `_DOMAIN_FACTORIES`)
- Modify: `src/gangtise_openapi/domains/__init__.py` (re-export `Insight`)

**Endpoint manifest** (translate from `gangtise-openapi-cli/src/cli.ts` lines ~135-290).

For every endpoint below: the Python wrapper accepts the kwargs in the **Kwargs** column (snake_case), maps them to body fields in the **Body** column (camelCase exactly as TS sends), invokes `self._client._call(<endpoint_key>, body=body)`, and returns either a DataFrame (for list endpoints) or a download result (download endpoints go via `_download` once Task 21 lands; until then return raw dict).

| Endpoint key | Method | Kwargs (Python) | Body fields (TS) | Returns |
|---|---|---|---|---|
| `insight.opinion.list` | POST | `from_=0, size=None, start_time=None, end_time=None, keyword=None, rank_type=1, research_area=None, chief=None, security=None, broker=None, industry=None, concept=None, llm_tag=None, source=None` | `from, size, startTime, endTime, keyword, rankType, researchAreaList, chiefList, securityList, brokerList, industryList, conceptList, llmTagList, sourceList` | DataFrame |
| `insight.summary.list` | POST | `from_, size, start_time, end_time, keyword, search_type=1, rank_type=1, source=None, research_area=None, security=None, institution=None, category=None, market=None, participant_role=None` | `from, size, startTime, endTime, keyword, searchType, rankType, sourceList, researchAreaList, securityList, institutionList, categoryList, marketList, participantRoleList` | DataFrame |
| `insight.summary.download` | GET | `summary_id, file_type=None, output=None` | query: `summaryId, fileType` | download (Path) |
| `insight.roadshow.list` | POST | (same as `schedule` shape — see TS `addScheduleList`) `from_, size, start_time, end_time, keyword, research_area, institution, security, category, market, participant_role, broker_type, object_, permission` | same camelCase + `List` suffix as above | DataFrame |
| `insight.site-visit.list` | POST | same as roadshow | same | DataFrame |
| `insight.strategy.list` | POST | same as roadshow | same | DataFrame |
| `insight.forum.list` | POST | same as roadshow | same | DataFrame |
| `insight.research.list` | POST | `from_, size, start_time, end_time, keyword, search_type=1, rank_type=1, broker=None, security=None, industry=None, category=None, llm_tag=None, rating=None, rating_change=None, min_pages=None, max_pages=None, source=None` | `from, size, startTime, endTime, keyword, searchType, rankType, brokerList, securityList, industryList, categoryList, llmTagList, ratingList, ratingChangeList, minPages, maxPages, sourceList` | DataFrame |
| `insight.research.download` | GET | `report_id, output=None` | query: `reportId` | download (Path) |
| `insight.foreign-report.list` | POST | `from_, size, start_time, end_time, keyword, search_type=1, rank_type=1, security=None, region=None, category=None, industry=None, broker=None, llm_tag=None, rating=None, rating_change=None, min_pages=None, max_pages=None` | same camelCase | DataFrame |
| `insight.foreign-report.download` | GET | `report_id, output=None` | query: `reportId` | download |
| `insight.announcement.list` | POST | `from_, size, start_time, end_time, keyword, search_type=1, rank_type=1, security=None, announcement_type=None, category=None` | `from, size, startTime (13-digit timestamp), endTime (13-digit timestamp), keyword, searchType, rankType, securityList, announcementTypeList, categoryList` | DataFrame |
| `insight.announcement.download` | GET | `announcement_id, output=None` | query: `announcementId` | download |
| `insight.announcement-hk.list` | POST | (same as `announcement.list`) | same | DataFrame |
| `insight.announcement-hk.download` | GET | `announcement_id, output=None` | query: `announcementId` | download |
| `insight.foreign-opinion.list` | POST | `from_, size, start_time, end_time, rank_type=1, security, region, industry, broker, rating, rating_change` | same camelCase | DataFrame |
| `insight.independent-opinion.list` | POST | `from_, size, start_time, end_time, rank_type=1, security, industry, rating, rating_change` | same camelCase | DataFrame |
| `insight.independent-opinion.download` | GET | `opinion_id, output=None` | query: `opinionId` | download |

**Body translation rules (universal):**
- `--from <n>` (TS) → `from_` (Python kwarg, trailing underscore to dodge keyword clash) → `from` (body field).
- `--xxx-yyy` (TS) → `xxx_yyy` (Python kwarg) → `xxxYyy` (body field).
- List-typed CLI options (TS `collectList`/`collectNumberList`) accept either a single value or a list at the Python boundary; the wrapper normalizes to a list before sending, body field uses the `…List` suffix where TS does. The helper:
  ```python
  def _as_list(value: Any) -> list[Any] | None:
      if value is None:
          return None
      if isinstance(value, (list, tuple)):
          return list(value)
      return [value]
  ```
- Strip `None` values from the final body so the server sees only the fields the user actually set.

- [ ] **Step 1: Write the wrapper for one list endpoint (full code)**

`src/gangtise_openapi/domains/insight.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._normalize import to_dataframe


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


_OPINION_SCHEMA = [
    "id", "title", "publishTime", "broker", "chief",
    "industry", "researchArea", "security", "summary",
]


class Insight:
    """`gangtise.insight.*` — research / report / announcement endpoints."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    # -- example: opinion.list (apply the same template for every list endpoint) --

    def opinion_list(
        self,
        *,
        from_: int = 0,
        size: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        keyword: str | None = None,
        rank_type: int = 1,
        research_area: Any = None,
        chief: Any = None,
        security: Any = None,
        broker: Any = None,
        industry: Any = None,
        concept: Any = None,
        llm_tag: Any = None,
        source: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        body = _strip_none({
            "from": from_,
            "size": size,
            "startTime": start_time,
            "endTime": end_time,
            "keyword": keyword,
            "rankType": rank_type,
            "researchAreaList": _as_list(research_area),
            "chiefList": _as_list(chief),
            "securityList": _as_list(security),
            "brokerList": _as_list(broker),
            "industryList": _as_list(industry),
            "conceptList": _as_list(concept),
            "llmTagList": _as_list(llm_tag),
            "sourceList": _as_list(source),
        })
        result = self._client._call("insight.opinion.list", body=body)
        if raw:
            return result
        rows = result.get("list", []) if isinstance(result, dict) else []
        return to_dataframe(rows, schema=_OPINION_SCHEMA)
```

- [ ] **Step 2: Add the remaining 18 wrappers**

For every endpoint in the manifest above, copy the `opinion_list` template, substituting:
- The Python method name (replace `-` with `_` and dot-paths with `_`: `insight.research.list` → `research_list`, `insight.research.download` → `research_download`).
- The kwarg signature (per **Kwargs** column).
- The body dict (per **Body fields** column). For 13-digit timestamps (announcement list endpoints in TS use `parseTimestamp13`), accept Python `int` (milliseconds since epoch) or ISO 8601 string and pass through verbatim.
- The endpoint key.
- The schema constant (define one per list endpoint; column lists derived from observed payloads — when in doubt, leave `schema=None` to let pandas surface all columns).

For each `*.download` endpoint, the wrapper signature is:

```python
    def research_download(
        self,
        *,
        report_id: str,
        output: str | Path | None = None,
    ) -> Path:
        return _download_via_client(
            self._client,
            endpoint_key="insight.research.download",
            query={"reportId": report_id},
            output=output,
            fallback_name=f"research-{report_id}",
        )
```

`_download_via_client` does not exist yet — Task 21 creates it. Until then, leave the download wrappers as:

```python
    def research_download(self, *, report_id: str, output: str | Path | None = None) -> dict[str, Any]:
        raise NotImplementedError("download support lands in Task 21")
```

and skip the corresponding smoke tests with `pytest.mark.skip(reason="download support: Task 21")`.

- [ ] **Step 3: Add `Insight` to `domains/__init__.py`**

```python
from gangtise_openapi.domains.auth import Auth
from gangtise_openapi.domains.insight import Insight
from gangtise_openapi.domains.lookup import Lookup
from gangtise_openapi.domains.reference import Reference

__all__ = ["Auth", "Insight", "Lookup", "Reference"]
```

- [ ] **Step 4: Add `insight` to `_Facade._DOMAIN_FACTORIES`**

```python
    _DOMAIN_FACTORIES: dict[str, str] = {
        "auth": "gangtise_openapi.domains.auth:Auth",
        "lookup": "gangtise_openapi.domains.lookup:Lookup",
        "reference": "gangtise_openapi.domains.reference:Reference",
        "insight": "gangtise_openapi.domains.insight:Insight",
    }
```

- [ ] **Step 5: Add smoke tests `tests/endpoints/test_insight.py`**

Pattern (apply per endpoint):

```python
import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.insight import Insight


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        page_concurrency=3,
    )


def test_opinion_list(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-insight/chief-opinion/getList").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {"total": 1, "list": [
                        {"id": "1", "title": "x", "broker": "A", "chief": "B"},
                    ]},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Insight(client).opinion_list(industry=1)
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["id"] == "1"


@pytest.mark.skip(reason="download support: Task 21")
def test_research_download(tmp_path):
    pass
```

Add a similar test (success + 1-row mock response) for every `*.list` endpoint. Use the path from the endpoint registry. Aim for one test per endpoint, with the `respx.mock(base_url=...)` fixture pattern shared.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/endpoints/test_insight.py -v`
Expected: 17 passed (19 endpoints minus 2 deferred download tests).

- [ ] **Step 7: Commit**

```bash
git add src/gangtise_openapi/domains/insight.py \
        src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/test_insight.py
git commit -m "feat(insight): wrap 19 endpoints with DataFrame return"
```

---

### Task 17: Quote domain (6 endpoints, 4 sharded)

**Files:**
- Create: `src/gangtise_openapi/domains/quote.py`
- Create: `tests/endpoints/test_quote.py`
- Modify: `src/gangtise_openapi/domains/__init__.py`
- Modify: `src/gangtise_openapi/_facade.py`

**Endpoint manifest** (TS reference: `cli.ts:307-330`).

| Endpoint key | Method | Kwargs | Body fields | Shard days |
|---|---|---|---|---|
| `quote.day-kline` | POST | `security, start_date=None, end_date=None, limit=None, field=None` | `securityList, startDate, endDate, limit, fieldList` | 1 |
| `quote.day-kline-hk` | POST | same | same | 2 |
| `quote.day-kline-us` | POST | same | same | 1 |
| `quote.index-day-kline` | POST | same | same | 30 |
| `quote.minute-kline` | POST | `security, start_time=None, end_time=None, limit=None, field=None` | `securityCode, startTime, endTime, limit, fieldList` (note: not pluralised `securityList`) | n/a |
| `quote.realtime` | POST | `security, field=None` | `securityList, fieldList` | n/a |

**Sharding rule:** for the four `day-kline*` endpoints, when `security` includes `"all"` (or equals `"all"`) **and** the user did not pass `limit`, inject `limit=10000`. Then plan shards via `_quote_sharding.plan_shards(start_date, end_date, days_per_shard=SHARD_DAYS[<endpoint>])`. Fetch shards concurrently using the same thread pool size as pagination, merge `list` arrays (preserve duplicates — TS does not dedupe), preserve other top-level fields from the last shard's response.

- [ ] **Step 1: Write the wrapper `src/gangtise_openapi/domains/quote.py`**

```python
from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

import pandas as pd

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._normalize import to_dataframe
from gangtise_openapi._quote_sharding import (
    DEFAULT_FULL_MARKET_LIMIT,
    SHARD_DAYS,
    fetch_shards,
    needs_limit_injection,
    plan_shards,
)

_DAY_KLINE_SCHEMA = [
    "securityCode", "date", "open", "high", "low", "close",
    "volume", "amount", "preClose", "changePct", "turnover",
]
_MINUTE_KLINE_SCHEMA = [
    "securityCode", "datetime", "open", "high", "low", "close", "volume", "amount",
]
_REALTIME_SCHEMA = [
    "securityCode", "name", "price", "open", "high", "low", "preClose",
    "volume", "amount", "changePct",
]


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


def _parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


class Quote:
    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def _day_kline(
        self,
        endpoint_key: str,
        *,
        security: Any,
        start_date: str | dt.date | None,
        end_date: str | dt.date | None,
        limit: int | None,
        field: Any,
        raw: bool,
    ) -> pd.DataFrame | dict[str, Any]:
        days_per_shard = SHARD_DAYS[endpoint_key]
        if needs_limit_injection(security=security, explicit_limit=limit):
            limit = DEFAULT_FULL_MARKET_LIMIT

        if start_date and end_date:
            shards = plan_shards(
                start_date=_parse_date(start_date),
                end_date=_parse_date(end_date),
                days_per_shard=days_per_shard,
            )
        else:
            shards = []

        def fetch_shard(window: tuple[dt.date, dt.date]) -> Any:
            s, e = window
            body = _strip_none({
                "securityList": _as_list(security),
                "startDate": s.isoformat(),
                "endDate": e.isoformat(),
                "limit": limit,
                "fieldList": _as_list(field),
            })
            return self._client._call(endpoint_key, body=body)

        if shards:
            page_results = fetch_shards(
                shards, fetch=fetch_shard, concurrency=self._client.config.page_concurrency
            )
        else:
            body = _strip_none({
                "securityList": _as_list(security),
                "startDate": start_date.isoformat() if isinstance(start_date, dt.date) else start_date,
                "endDate": end_date.isoformat() if isinstance(end_date, dt.date) else end_date,
                "limit": limit,
                "fieldList": _as_list(field),
            })
            page_results = [self._client._call(endpoint_key, body=body)]

        merged: dict[str, Any] = {}
        rows: list[Any] = []
        for result in page_results:
            if isinstance(result, dict) and isinstance(result.get("list"), list):
                merged.update({k: v for k, v in result.items() if k != "list"})
                rows.extend(result["list"])
            elif isinstance(result, list):
                rows.extend(result)
        result_payload: dict[str, Any] = {**merged, "list": rows} if merged else {"list": rows}
        if raw:
            return result_payload
        return to_dataframe(rows, schema=_DAY_KLINE_SCHEMA)

    def day_kline(self, **kwargs: Any):
        return self._day_kline("quote.day-kline", **kwargs)

    def day_kline_hk(self, **kwargs: Any):
        return self._day_kline("quote.day-kline-hk", **kwargs)

    def day_kline_us(self, **kwargs: Any):
        return self._day_kline("quote.day-kline-us", **kwargs)

    def index_day_kline(self, **kwargs: Any):
        return self._day_kline("quote.index-day-kline", **kwargs)

    def minute_kline(
        self,
        *,
        security: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ):
        body = _strip_none({
            "securityCode": security,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
            "fieldList": _as_list(field),
        })
        result = self._client._call("quote.minute-kline", body=body)
        if raw:
            return result
        rows = result.get("list", []) if isinstance(result, dict) else result
        return to_dataframe(rows, schema=_MINUTE_KLINE_SCHEMA)

    def realtime(
        self,
        *,
        security: Any,
        field: Any = None,
        raw: bool = False,
    ):
        body = _strip_none({
            "securityList": _as_list(security),
            "fieldList": _as_list(field),
        })
        result = self._client._call("quote.realtime", body=body)
        if raw:
            return result
        rows = result if isinstance(result, list) else result.get("list", [])
        return to_dataframe(rows, schema=_REALTIME_SCHEMA)
```

- [ ] **Step 2: Re-export + facade wiring**

`domains/__init__.py`:
```python
from gangtise_openapi.domains.auth import Auth
from gangtise_openapi.domains.insight import Insight
from gangtise_openapi.domains.lookup import Lookup
from gangtise_openapi.domains.quote import Quote
from gangtise_openapi.domains.reference import Reference

__all__ = ["Auth", "Insight", "Lookup", "Quote", "Reference"]
```

`_Facade._DOMAIN_FACTORIES`: add `"quote": "gangtise_openapi.domains.quote:Quote"`.

- [ ] **Step 3: Write smoke tests `tests/endpoints/test_quote.py`**

```python
import httpx
import pandas as pd
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.quote import Quote


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
        page_concurrency=2,
    )


def test_day_kline_single_security(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {"list": [
                        {"securityCode": "000001.SH", "date": "2026-01-02", "close": 12.3},
                    ]},
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).day_kline(security="000001.SH")
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["close"] == 12.3


def test_day_kline_all_market_injects_limit_10000(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        route = router.post("/application/open-quote/kline/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline(
                security="all", start_date="2026-01-02", end_date="2026-01-02",
            )
        body = route.calls.last.request.read()
        assert b'"limit":10000' in body.replace(b" ", b"")


def test_day_kline_us_shard_count(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        route = router.post("/application/open-quote/kline-us/daily").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": {"list": []}},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            Quote(client).day_kline_us(
                security="all", start_date="2026-01-01", end_date="2026-01-03",
            )
        # Expect 3 shards (1 day per shard × 3 days).
        assert route.call_count == 3


def test_realtime(tmp_path):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": [{"securityCode": "000001.SH", "price": 12.34}],
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            df = Quote(client).realtime(security=["000001.SH"])
    assert df.iloc[0]["price"] == 12.34
```

Add one similar test per endpoint (minute_kline, day_kline_hk, index_day_kline) following the same pattern.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/endpoints/test_quote.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/domains/quote.py \
        src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/test_quote.py
git commit -m "feat(quote): 6 wrappers with K-line date sharding + all-market limit"
```

---

### Task 18: Fundamental domain (12 endpoints)

**Files:**
- Create: `src/gangtise_openapi/domains/fundamental.py`
- Create: `tests/endpoints/test_fundamental.py`
- Modify: `src/gangtise_openapi/domains/__init__.py`
- Modify: `src/gangtise_openapi/_facade.py`

**Endpoint manifest** (TS reference: `cli.ts:333-409`).

| Endpoint key | Python method | Kwargs | Body fields |
|---|---|---|---|
| `fundamental.income-statement` | `income_statement` | `security_code, start_date, end_date, fiscal_year, period, report_type, field, raw` | `securityCode, startDate, endDate, fiscalYear, period (list or None), reportType (list or None), fieldList` |
| `fundamental.income-statement-quarterly` | `income_statement_quarterly` | same | same |
| `fundamental.balance-sheet` | `balance_sheet` | same | same |
| `fundamental.cash-flow` | `cash_flow` | same | same |
| `fundamental.cash-flow-quarterly` | `cash_flow_quarterly` | same | same |
| `fundamental.income-statement-hk` | `income_statement_hk` | same | same |
| `fundamental.balance-sheet-hk` | `balance_sheet_hk` | same | same |
| `fundamental.cash-flow-hk` | `cash_flow_hk` | same | same |
| `fundamental.main-business` | `main_business` | `security_code, start_date, end_date, breakdown="product", period, field, raw` | `securityCode, startDate, endDate, breakdown, periodList, fieldList` |
| `fundamental.valuation-analysis` | `valuation_analysis` | `security_code, indicator, range_=None, field=None, raw` (TS uses `--range` flag; `range` is a Python builtin, so use `range_`; body field `range`) | `securityCode, indicator, range, fieldList` |
| `fundamental.top-holders` | `top_holders` | `security_code, top_n=None, field=None, raw` | `securityCode, topN, fieldList` |
| `fundamental.earning-forecast` | `earning_forecast` | `security_code, broker=None, field=None, raw` | `securityCode, brokerList, fieldList` |

**DataFrame schema:** for the 8 statement endpoints the schema is best left `schema=None` (server response columns vary by report shape); for `valuation_analysis` schema is `["securityCode", "indicator", "date", "value", "percentileRank", "average", "median", "upper1Std", "lower1Std"]`; for `top_holders`: `["securityCode", "reportDate", "holderName", "shareCount", "sharePercent"]`; for `earning_forecast`: `["securityCode", "broker", "reportDate", "year", "revenueForecast", "netProfitForecast", "epsForecast", "targetPrice"]`; for `main_business`: `["securityCode", "reportDate", "breakdown", "name", "revenue", "revenuePercent"]`.

Use the wrapper template established in Task 17 (with `_strip_none` + `_as_list`). Each method follows:

```python
def income_statement(
    self, *,
    security_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    fiscal_year: Any = None,
    period: Any = None,
    report_type: Any = None,
    field: Any = None,
    raw: bool = False,
):
    body = _strip_none({
        "securityCode": security_code,
        "startDate": start_date,
        "endDate": end_date,
        "fiscalYear": _as_list(fiscal_year),
        "period": _as_list(period),
        "reportType": _as_list(report_type),
        "fieldList": _as_list(field),
    })
    result = self._client._call("fundamental.income-statement", body=body)
    if raw:
        return result
    rows = result.get("list", []) if isinstance(result, dict) else result
    return to_dataframe(rows, schema=None)
```

- [ ] **Step 1: Create the file with all 12 wrappers**
- [ ] **Step 2: Wire up `domains/__init__.py` and `_DOMAIN_FACTORIES`**
- [ ] **Step 3: Write smoke tests — one per endpoint, mocking the path from the endpoint registry**
- [ ] **Step 4: Run `uv run pytest tests/endpoints/test_fundamental.py -v` (expected: 12 passed)**
- [ ] **Step 5: Commit**

```bash
git add src/gangtise_openapi/domains/fundamental.py \
        src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/test_fundamental.py
git commit -m "feat(fundamental): 12 wrappers (statements + valuation + holders + forecast)"
```

---

### Task 19: AI domain (14 endpoints incl. 2 async-polled)

**Files:**
- Create: `src/gangtise_openapi/domains/ai.py`
- Create: `tests/endpoints/test_ai.py`
- Modify: `domains/__init__.py`, `_facade.py`

**Endpoint manifest** (TS reference: `cli.ts:367-505`).

| Endpoint key | Python method | Kwargs | Body fields | Notes |
|---|---|---|---|---|
| `ai.knowledge-batch` | `knowledge_batch` | `query, count=None, raw` | `query, count` | Returns list |
| `ai.knowledge-resource.download` | `knowledge_resource_download` | `resource_id, output=None` | query: `resourceId` | download (Task 21) |
| `ai.security-clue.list` | `security_clue_list` | `from_, size, security, industry, gts_code, time_range, raw` | `from, size, securityList, industryList, gtsCodeList, timeRange` | paginated |
| `ai.one-pager` | `one_pager` | `security_code, raw` | `securityCode` | dict result |
| `ai.investment-logic` | `investment_logic` | `security_code, raw` | `securityCode` | dict result |
| `ai.peer-comparison` | `peer_comparison` | `security_code, raw` | `securityCode` | dict result |
| `ai.theme-tracking` | `theme_tracking` | `theme_id, raw` | `themeId` | dict result |
| `ai.research-outline` | `research_outline` | `security_code, raw` | `securityCode` | dict result |
| `ai.hot-topic` | `hot_topic` | `raw` | (empty body) | dict result |
| `ai.management-discuss-announcement` | `management_discuss_announcement` | `security_code, period, dimension="all", raw` | `securityCode, period, dimension` | dict result |
| `ai.management-discuss-earnings-call` | `management_discuss_earnings_call` | `security_code, period, raw` | `securityCode, period` | dict result |
| **Async-polled pair: earnings-review** | | | | |
| `ai.earnings-review.get-id` + `.get-content` | `earnings_review(security_code, period, *, wait=True, raw=False)` and `earnings_review_check(data_id, raw=False)` | see code below | see code below | uses `_async_content.poll_content` |
| **Async-polled pair: viewpoint-debate** | | | | |
| `ai.viewpoint-debate.get-id` + `.get-content` | `viewpoint_debate(viewpoint, *, wait=True, raw=False)` and `viewpoint_debate_check(data_id, raw=False)` | see code below | see code below | uses `_async_content.poll_content` |

**Wrappers for the two async pairs (full code):**

```python
from gangtise_openapi._async_content import poll_content


class AI:
    # ... other wrappers as per manifest ...

    def earnings_review(
        self,
        *,
        security_code: str,
        period: str,
        wait: bool = True,
        raw: bool = False,
    ):
        id_result = self._client._call(
            "ai.earnings-review.get-id",
            body={"securityCode": security_code, "period": period},
        )
        data_id = id_result.get("dataId") if isinstance(id_result, dict) else None
        if not data_id:
            return id_result if raw else id_result
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        def fetch():
            return self._client._call(
                "ai.earnings-review.get-content", body={"dataId": data_id}
            )

        result = poll_content(fetch)
        return result

    def earnings_review_check(self, *, data_id: str, raw: bool = False):
        result = self._client._call(
            "ai.earnings-review.get-content", body={"dataId": data_id}
        )
        return result

    def viewpoint_debate(
        self,
        *,
        viewpoint: str,
        wait: bool = True,
        raw: bool = False,
    ):
        id_result = self._client._call(
            "ai.viewpoint-debate.get-id", body={"viewpoint": viewpoint}
        )
        data_id = id_result.get("dataId") if isinstance(id_result, dict) else None
        if not data_id:
            return id_result
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        def fetch():
            return self._client._call(
                "ai.viewpoint-debate.get-content", body={"dataId": data_id}
            )

        return poll_content(fetch)

    def viewpoint_debate_check(self, *, data_id: str, raw: bool = False):
        return self._client._call(
            "ai.viewpoint-debate.get-content", body={"dataId": data_id}
        )
```

- [ ] **Step 1: Write all 14 wrappers** (`ai.py`).
- [ ] **Step 2: Wire `__init__.py` + facade.**
- [ ] **Step 3: Smoke tests** — one per endpoint. For the async pairs, mock the id endpoint + one successful content fetch; assert the wrapper returns the content. Add one extra test for `wait=False` returning `{"data_id": ..., "status": "pending"}`. Add one test for the `410110`→ready transition (sleep stubbed to no-op via `monkeypatch.setattr("gangtise_openapi._async_content.time.sleep", lambda s: None)`).
- [ ] **Step 4: Run `uv run pytest tests/endpoints/test_ai.py -v`** — expected: 12 passed (10 sync + earnings-review + viewpoint-debate, deferred-download skip for knowledge-resource).
- [ ] **Step 5: Commit:** `feat(ai): 14 wrappers with transparent polling for earnings-review + viewpoint-debate`.

---

### Task 20: Vault + Alternative domains

**Files:**
- Create: `src/gangtise_openapi/domains/vault.py`
- Create: `src/gangtise_openapi/domains/alternative.py`
- Create: `tests/endpoints/test_vault.py`
- Create: `tests/endpoints/test_alternative.py`
- Modify: `domains/__init__.py`, `_facade.py`

**Vault manifest** (TS reference: `cli.ts:508-650` and the wechat blocks).

| Endpoint key | Python method | Kwargs | Body fields | Notes |
|---|---|---|---|---|
| `vault.drive.list` | `drive_list` | `from_, size, keyword=None, file_type=None, raw` | `from, size, keyword, fileType` | paginated |
| `vault.drive.download` | `drive_download` | `file_id, output=None` | query: `fileId` | download |
| `vault.record.list` | `record_list` | `from_, size, keyword=None, start_time=None, end_time=None, raw` | `from, size, keyword, startTime, endTime` | paginated |
| `vault.record.download` | `record_download` | `record_id, output=None` | query: `recordId` | download |
| `vault.my-conference.list` | `my_conference_list` | `from_, size, keyword, start_time, end_time, raw` | similar | paginated |
| `vault.my-conference.download` | `my_conference_download` | `conference_id, output=None` | query | download |
| `vault.wechat-message.list` | `wechat_message_list` | `from_, size, chatroom_id=None, security=None, start_time=None, end_time=None, raw` | `from, size, chatroomId, securityList, startTime, endTime` | paginated. Use `_commandBodies.buildWechatMessageListBody` equivalent — see TS `commandBodies.ts` |
| `vault.wechat-chatroom.list` | `wechat_chatroom_list` | `from_, size, keyword=None, raw` | `from, size, keyword` | paginated. Body builder in TS `commandBodies.ts` |
| `vault.stock-pool.list` | `stock_pool_list` | `raw` | (empty body) | returns `{poolList: [...]}` |
| `vault.stock-pool.stocks` | `stock_pool_stocks` | `pool_id, raw` | `poolId` (`pool_id="all"` → server-side full query) | returns `{list: [...]}` |

**Alternative manifest** (TS reference: `cli.ts:651-695`).

| Endpoint key | Python method | Kwargs | Body fields |
|---|---|---|---|
| `alternative.edb-search` | `edb_search` | `keyword, raw` | `keyword` |
| `alternative.edb-data` | `edb_data` | `indicator_id, start_date=None, end_date=None, raw` | `indicatorIdList, startDate, endDate` |

- [ ] **Step 1: Write `domains/vault.py` and `domains/alternative.py` using the wrapper template established in Task 17.**
- [ ] **Step 2: Wire `__init__.py` + facade for both domains.**
- [ ] **Step 3: Write one smoke test per endpoint.**
- [ ] **Step 4: Run `uv run pytest tests/endpoints/test_vault.py tests/endpoints/test_alternative.py -v` — expected: 12 passed (10 vault + 2 alternative; download endpoints skipped for Task 21).**
- [ ] **Step 5: Commit:** `feat(vault,alternative): wrap 12 endpoints`.

---

## Phase 6 — Download, Title Cache, Logging

### Task 21: Title cache (`_title_cache.py`)

**Files:**
- Create: `src/gangtise_openapi/_title_cache.py`
- Create: `tests/unit/test_title_cache.py`

In-memory snapshot + atomic JSON write to `~/.config/gangtise/title-cache.json`. Mirrors `gangtise-openapi-cli/src/core/titleCache.ts`.

- [ ] **Step 1: Write the failing test `tests/unit/test_title_cache.py`**

```python
import json

from gangtise_openapi._title_cache import TitleCache


def test_set_and_get_roundtrip(tmp_path):
    cache = TitleCache(tmp_path / "titles.json")
    cache.set("report-123", "公司A-2026年度报告")
    assert cache.get("report-123") == "公司A-2026年度报告"


def test_persists_to_disk(tmp_path):
    path = tmp_path / "titles.json"
    cache_one = TitleCache(path)
    cache_one.set("report-123", "X")
    cache_one.flush()
    cache_two = TitleCache(path)
    assert cache_two.get("report-123") == "X"


def test_corrupt_file_treated_as_empty(tmp_path):
    path = tmp_path / "titles.json"
    path.write_text("not json", encoding="utf8")
    cache = TitleCache(path)
    assert cache.get("anything") is None


def test_atomic_write_no_partial(tmp_path):
    path = tmp_path / "titles.json"
    cache = TitleCache(path)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.flush()
    data = json.loads(path.read_text(encoding="utf8"))
    assert data == {"a": "1", "b": "2"}
```

- [ ] **Step 2: Write `src/gangtise_openapi/_title_cache.py`**

```python
from __future__ import annotations

import json
import os
import threading
from pathlib import Path


class TitleCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        try:
            raw = self._path.read_text(encoding="utf8")
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value

    def flush(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf8")
            os.chmod(tmp, 0o600)
            tmp.replace(self._path)
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/unit/test_title_cache.py -v` → 4 passed.

```bash
git add src/gangtise_openapi/_title_cache.py tests/unit/test_title_cache.py
git commit -m "feat(title-cache): atomic JSON cache for resolved download titles"
```

---

### Task 22: Streaming download (`_download.py`)

**Files:**
- Create: `src/gangtise_openapi/_download.py`
- Create: `tests/unit/test_download.py`
- Modify: every domain wrapper that currently has `raise NotImplementedError("download support lands in Task 21")`.

- [ ] **Step 1: Write the failing test `tests/unit/test_download.py`**

```python
import httpx
import respx

from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi._download import download_to_path


def _cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


def test_download_with_explicit_output(tmp_path):
    out_path = tmp_path / "report.pdf"
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200, content=b"%PDF-fake",
                headers={"content-type": "application/pdf"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=out_path,
                fallback_name="report-r1",
            )
    assert path == out_path
    assert path.read_bytes() == b"%PDF-fake"


def test_download_uses_content_disposition_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200, content=b"data",
                headers={
                    "content-disposition": 'attachment; filename="alpha.pdf"',
                    "content-type": "application/pdf",
                },
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    assert path.name == "alpha.pdf"
    assert path.read_bytes() == b"data"


def test_download_falls_back_when_no_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200, content=b"data", headers={"content-type": "application/pdf"},
            )
        )
        with GangtiseClient(_config=_cfg(tmp_path)) as client:
            path = download_to_path(
                client=client,
                endpoint_key="insight.research.download",
                query={"reportId": "r1"},
                output=None,
                fallback_name="report-r1",
            )
    assert path.name.startswith("report-r1")
```

- [ ] **Step 2: Write `src/gangtise_openapi/_download.py`**

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._client import GangtiseClient
from gangtise_openapi._endpoints import lookup
from gangtise_openapi._errors import DownloadError

_DISPOSITION_RE = re.compile(r"filename\*?=(?:UTF-8''([^;]+)|\"?([^\";]+)\"?)")


def _parse_content_disposition(header: str | None) -> str | None:
    if not header:
        return None
    match = _DISPOSITION_RE.search(header)
    if not match:
        return None
    return match.group(1) or match.group(2)


def _extension_for(content_type: str | None) -> str:
    if not content_type:
        return ""
    lower = content_type.split(";")[0].strip().lower()
    return {
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "text/html": ".html",
        "application/octet-stream": "",
    }.get(lower, "")


def download_to_path(
    *,
    client: GangtiseClient,
    endpoint_key: str,
    query: dict[str, str | int],
    output: str | Path | None,
    fallback_name: str,
) -> Path:
    endpoint = lookup(endpoint_key)
    if endpoint.kind != "download":
        raise DownloadError(f"endpoint {endpoint_key} is not a download endpoint")

    headers: dict[str, str] = {}
    token = client._get_token()
    headers["Authorization"] = normalize_token(token)

    http = client._http_client()
    with http.stream(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
    ) as response:
        if response.status_code >= 400:
            response.read()
            raise DownloadError(
                f"download failed: HTTP {response.status_code} {response.text[:200]}"
            )
        content_disposition = response.headers.get("content-disposition")
        content_type = response.headers.get("content-type")
        if output is None:
            filename = _parse_content_disposition(content_disposition)
            if not filename:
                filename = f"{fallback_name}{_extension_for(content_type)}"
            target = Path.cwd() / filename
        else:
            target = Path(output).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
            tmp.replace(target)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise DownloadError(f"failed to write to {target}: {exc}") from exc
    return target
```

- [ ] **Step 3: Replace `NotImplementedError("Task 21")` placeholders**

For each `*_download` method placed in Tasks 16/19/20, replace the body with a `download_to_path(...)` call. Example:

```python
from gangtise_openapi._download import download_to_path

def research_download(
    self,
    *,
    report_id: str,
    output: str | Path | None = None,
) -> Path:
    return download_to_path(
        client=self._client,
        endpoint_key="insight.research.download",
        query={"reportId": report_id},
        output=output,
        fallback_name=f"research-{report_id}",
    )
```

Apply to: `insight.summary.download`, `insight.research.download`, `insight.foreign-report.download`, `insight.announcement.download`, `insight.announcement-hk.download`, `insight.independent-opinion.download`, `ai.knowledge-resource.download`, `vault.drive.download`, `vault.record.download`, `vault.my-conference.download`.

- [ ] **Step 4: Remove the `pytest.mark.skip` decorators in the smoke tests**

For each `test_*_download`, replace the skip with a real respx test asserting the file lands at the expected path and the body matches the mocked bytes.

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: all previously skipped download tests now pass.

- [ ] **Step 6: Commit**

```bash
git add src/gangtise_openapi/_download.py src/gangtise_openapi/domains tests
git commit -m "feat(download): streaming downloads + wire all *_download wrappers"
```

---

### Task 23: Logging integration

**Files:**
- Modify: `src/gangtise_openapi/__init__.py`
- Create: `tests/unit/test_logging.py`

- [ ] **Step 1: Write `tests/unit/test_logging.py`**

```python
import logging

from gangtise_openapi._config import load_config


def test_verbose_env_enables_debug(monkeypatch):
    monkeypatch.setenv("GANGTISE_VERBOSE", "1")
    cfg = load_config()
    assert cfg.verbose is True


def test_logger_is_named_gangtise_openapi():
    logger = logging.getLogger("gangtise_openapi")
    assert logger.name == "gangtise_openapi"
```

- [ ] **Step 2: Update `src/gangtise_openapi/__init__.py`**

Append at the bottom of the existing exports:

```python
import logging as _logging
import os as _os

if _os.environ.get("GANGTISE_VERBOSE") in {"1", "true", "True", "yes", "YES"}:
    _logging.getLogger("gangtise_openapi").setLevel(_logging.DEBUG)
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/unit/test_logging.py -v` → 2 passed.

```bash
git add src/gangtise_openapi/__init__.py tests/unit/test_logging.py
git commit -m "feat(logging): honor GANGTISE_VERBOSE for debug logging"
```

---

## Phase 7 — Async Layer

The async layer mirrors the sync layer module-for-module. Two engineering rules:

1. **Reuse pure logic.** `_endpoints.py`, `_quote_sharding.plan_shards`, `_async_content.next_delay_seconds`, `_normalize`, `_lookup`, `_errors`, `_auth.TokenCache`, and `_pagination` planning logic stay shared. Only the *I/O* gets duplicated.
2. **Same public method names + same kwargs.** The async wrappers expose identical signatures; only `await` differs at the call site.

### Task 24: Async transport (`_transport_async.py`)

**Files:**
- Create: `src/gangtise_openapi/_transport_async.py`
- Create: `tests/unit/test_transport_async.py`

- [ ] **Step 1: Write the failing test `tests/unit/test_transport_async.py`**

```python
import httpx
import pytest
import respx

from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError
from gangtise_openapi._transport_async import build_async_client, request_json_async


def _endpoint() -> EndpointDef:
    return EndpointDef(key="x", method="POST", path="/p", kind="json", description="d")


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token=None,
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )


@pytest.mark.anyio
async def test_request_json_async_success(respx_mock, cfg):
    respx_mock.post("/p").mock(
        return_value=httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 1}})
    )
    async with build_async_client(cfg) as http:
        out = await request_json_async(http, cfg, _endpoint(), body={}, token="tok")
    assert out == {"v": 1}


@pytest.mark.anyio
async def test_request_json_async_500_then_success(respx_mock, cfg):
    respx_mock.post("/p").mock(
        side_effect=[
            httpx.Response(500, text="boom"),
            httpx.Response(200, json={"code": "000000", "status": True, "data": {"v": 2}}),
        ]
    )
    async with build_async_client(cfg) as http:
        out = await request_json_async(http, cfg, _endpoint(), body={}, token="tok")
    assert out == {"v": 2}


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 2: Write `src/gangtise_openapi/_transport_async.py`**

```python
from __future__ import annotations

import json
import random
import time
from typing import Any

import anyio
import httpx

from gangtise_openapi._auth import normalize_token
from gangtise_openapi._config import Config
from gangtise_openapi._endpoints import EndpointDef
from gangtise_openapi._errors import ApiError
from gangtise_openapi._transport import (
    is_envelope,
    is_retryable_error,
    unwrap_envelope,
)


def build_async_client(config: Config) -> httpx.AsyncClient:
    timeout = httpx.Timeout(config.timeout_ms / 1000.0)
    limits = httpx.Limits(max_connections=16, max_keepalive_connections=16, keepalive_expiry=60)
    return httpx.AsyncClient(base_url=config.base_url, timeout=timeout, limits=limits)


def _backoff_delay(attempt: int, base_ms: float = 400.0, max_ms: float = 4000.0) -> float:
    jitter = random.random() * base_ms
    return min(max_ms, base_ms * (2 ** attempt) + jitter) / 1000.0


async def _do_request(
    http: httpx.AsyncClient,
    endpoint: EndpointDef,
    body: Any,
    *,
    token: str | None,
    query: dict[str, str | int] | None,
) -> tuple[int, Any]:
    headers: dict[str, str] = {"content-type": "application/json"}
    if token is not None:
        headers["Authorization"] = normalize_token(token)
    response = await http.request(
        endpoint.method,
        endpoint.path,
        params=query,
        headers=headers,
        content=None if endpoint.method == "GET" else json.dumps(body or {}).encode("utf8"),
    )
    try:
        parsed = response.json()
    except ValueError:
        if response.status_code >= 400:
            raise ApiError(
                f"API request failed (HTTP {response.status_code})",
                status_code=response.status_code,
                details=response.text[:500],
            )
        raise ApiError(
            "Failed to parse API response",
            status_code=response.status_code,
            details=response.text[:500],
        )
    return response.status_code, parsed


async def request_json_async(
    http: httpx.AsyncClient,
    config: Config,
    endpoint: EndpointDef,
    *,
    body: Any = None,
    token: str | None,
    query: dict[str, str | int] | None = None,
    max_retries: int = 2,
) -> Any:
    attempt = 0
    while True:
        try:
            status_code, parsed = await _do_request(
                http, endpoint, body, token=token, query=query
            )
            if status_code >= 400:
                if is_envelope(parsed):
                    code = parsed.get("code")
                    raise ApiError(
                        parsed.get("msg") or f"API request failed (HTTP {status_code})",
                        code=str(code) if code is not None else None,
                        status_code=status_code,
                        details=parsed,
                    )
                raise ApiError(
                    f"API request failed (HTTP {status_code})",
                    status_code=status_code,
                    details=parsed,
                )
            return unwrap_envelope(parsed, status_code=status_code)
        except Exception as error:
            if attempt >= max_retries or not is_retryable_error(error):
                raise
            await anyio.sleep(_backoff_delay(attempt))
            attempt += 1
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/unit/test_transport_async.py -v` → 2 passed.

```bash
git add src/gangtise_openapi/_transport_async.py tests/unit/test_transport_async.py
git commit -m "feat(transport-async): async httpx wrapper with shared retry logic"
```

---

### Task 25: AsyncGangtiseClient + async pagination/sharding/polling

**Files:**
- Modify: `src/gangtise_openapi/_client.py` (add `AsyncGangtiseClient`)
- Modify: `src/gangtise_openapi/_pagination.py` (add `collect_paginated_async`)
- Modify: `src/gangtise_openapi/_quote_sharding.py` (add `fetch_shards_async`)
- Modify: `src/gangtise_openapi/_async_content.py` (add `poll_content_async`)
- Create: `tests/unit/test_pagination_async.py`
- Create: `tests/unit/test_async_content_async.py`
- Create: `tests/unit/test_async_client.py`

- [ ] **Step 1: Add `collect_paginated_async`**

Append to `_pagination.py`:

```python
import anyio


AsyncPageFetcher = Callable[[dict[str, Any]], Any]  # returns Awaitable


async def collect_paginated_async(
    endpoint: EndpointDef,
    *,
    body: dict[str, Any],
    fetch: Callable[[dict[str, Any]], Any],   # async function
    concurrency: int,
) -> Any:
    if endpoint.pagination is None:
        return await fetch(body)
    initial = {k: v for k, v in body.items()}
    _validate_paging_args(initial)
    start_from = initial.get("from", 0) if isinstance(initial.get("from"), int) else 0
    requested_size = initial.get("size") if isinstance(initial.get("size"), int) else None
    max_page_size = endpoint.pagination.max_page_size
    first_page_size = max_page_size if requested_size is None else min(max_page_size, requested_size)
    first_body = {**initial, "from": start_from, "size": first_page_size}
    first_page = await fetch(first_body)
    if not _is_paginated_response(first_page):
        return first_page
    total = first_page["total"]
    collected: list[Any] = list(first_page["list"])
    if first_page["list"] and len(first_page["list"]) < first_page_size:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}
    available = max(total - start_from, 0)
    target = available if requested_size is None else min(requested_size, available)
    if len(collected) >= target:
        if requested_size is not None:
            collected = collected[:requested_size]
        return {**first_page, "total": total, "list": collected}
    remaining_requests: list[dict[str, Any]] = []
    next_from = start_from + len(first_page["list"])
    end_from = start_from + target
    while next_from < end_from:
        size = min(max_page_size, end_from - next_from)
        remaining_requests.append({**initial, "from": next_from, "size": size})
        next_from += size
    if len(remaining_requests) + 1 > MAX_PAGES:
        remaining_requests = remaining_requests[: MAX_PAGES - 1]

    semaphore = anyio.Semaphore(max(1, min(concurrency, len(remaining_requests) or 1)))
    pages: list[Any] = [None] * len(remaining_requests)

    async def run_one(idx: int, req: dict[str, Any]) -> None:
        async with semaphore:
            pages[idx] = await fetch(req)

    async with anyio.create_task_group() as tg:
        for idx, req in enumerate(remaining_requests):
            tg.start_soon(run_one, idx, req)

    for page in pages:
        if _is_paginated_response(page) and page["list"]:
            collected.extend(page["list"])
    if requested_size is not None:
        collected = collected[:requested_size]
    return {**first_page, "total": total, "list": collected}
```

- [ ] **Step 2: Add `fetch_shards_async` to `_quote_sharding.py`**

```python
import anyio


AsyncShardFetcher = Callable[[tuple[dt.date, dt.date]], Any]


async def fetch_shards_async(
    shards: Sequence[tuple[dt.date, dt.date]],
    *,
    fetch: AsyncShardFetcher,
    concurrency: int,
) -> list[Any]:
    if not shards:
        return []
    workers = max(1, min(concurrency, len(shards)))
    semaphore = anyio.Semaphore(workers)
    results: list[Any] = [None] * len(shards)

    async def run_one(idx: int, window: tuple[dt.date, dt.date]) -> None:
        async with semaphore:
            results[idx] = await fetch(window)

    async with anyio.create_task_group() as tg:
        for idx, window in enumerate(shards):
            tg.start_soon(run_one, idx, window)
    return results
```

- [ ] **Step 3: Add `poll_content_async` to `_async_content.py`**

```python
import anyio


AsyncFetcher = Callable[[], Any]


async def poll_content_async(
    fetch: AsyncFetcher,
    *,
    max_attempts: int = POLL_MAX_ATTEMPTS,
) -> Any:
    last_pending: ApiError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await fetch()
        except ApiError as error:
            kind = _classify(error)
            if kind == "terminal":
                raise ApiError(
                    "Content generation failed (terminal). Do not retry.",
                    code=CODE_TERMINAL,
                ) from error
            if kind == "other":
                raise
            last_pending = error
        else:
            if isinstance(result, dict) and result.get("content") is not None:
                return result
        if attempt < max_attempts:
            await anyio.sleep(next_delay_seconds(attempt))
    raise ApiError(
        f"Content not available after {max_attempts} attempts",
        code=CODE_PENDING,
    ) from last_pending
```

- [ ] **Step 4: Add `AsyncGangtiseClient` to `_client.py`**

```python
import anyio

from gangtise_openapi._pagination import collect_paginated_async
from gangtise_openapi._transport_async import build_async_client, request_json_async


class AsyncGangtiseClient:
    """Async counterpart to GangtiseClient."""

    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        _config: Config | None = None,
    ) -> None:
        if _config is not None:
            cfg = _config
        else:
            cfg = load_config()
            overrides: dict[str, Any] = {}
            if access_key is not None:
                overrides["access_key"] = access_key
            if secret_key is not None:
                overrides["secret_key"] = secret_key
            if base_url is not None:
                overrides["base_url"] = base_url
            if token is not None:
                overrides["token"] = token
            if timeout is not None:
                overrides["timeout_ms"] = int(timeout * 1000)
            if overrides:
                cfg = Config(**{**asdict(cfg), **overrides})
        self._config = cfg
        self._http: httpx.AsyncClient | None = None
        self._memo_cache: TokenCache | None = None
        self._lock = anyio.Lock()

    @property
    def config(self) -> Config:
        return self._config

    async def __aenter__(self) -> "AsyncGangtiseClient":
        self._http = build_async_client(self._config)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = build_async_client(self._config)
        return self._http

    async def _get_token(self, force_refresh: bool = False) -> str:
        if self._config.token and not force_refresh:
            return self._config.token
        if not force_refresh:
            if is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            disk = read_token_cache(self._config.token_cache_path)
            if is_cache_valid(disk):
                self._memo_cache = disk
                assert disk is not None
                return disk.access_token
        async with self._lock:
            if not force_refresh and is_cache_valid(self._memo_cache):
                assert self._memo_cache is not None
                return self._memo_cache.access_token
            return await self._refresh_token()

    async def _refresh_token(self) -> str:
        access_key, secret_key = require_credentials(
            self._config.access_key, self._config.secret_key
        )
        endpoint = lookup("auth.login")
        body = {"accessKey": access_key, "secretKey": secret_key}
        result = await request_json_async(
            self._http_client(), self._config, endpoint, body=body, token=None
        )
        access_token = result["accessToken"]
        expires_in = int(result.get("expiresIn", 0))
        cache = TokenCache(
            access_token=access_token,
            expires_in=expires_in,
            time=int(result.get("time", int(time.time()))),
            expires_at=int(time.time()) + expires_in,
            uid=result.get("uid"),
            user_name=result.get("userName"),
            tenant_id=result.get("tenantId"),
        )
        self._memo_cache = cache
        write_token_cache(self._config.token_cache_path, cache)
        return access_token

    async def login(self) -> dict[str, Any]:
        token = await self._get_token()
        cache = self._memo_cache or read_token_cache(self._config.token_cache_path)
        return {
            "authorization": normalize_token(token),
            "cache": asdict(cache) if cache else None,
        }

    async def _call(
        self,
        endpoint_key: str,
        body: Any = None,
        query: dict[str, str | int] | None = None,
    ) -> Any:
        endpoint = lookup(endpoint_key)
        if endpoint.path.startswith("/guide/"):
            return list(LOOKUP_LOADERS[endpoint.key])

        async def fetch_one(page_body: dict[str, Any]) -> Any:
            return await self._request_once(endpoint, page_body, query)

        if endpoint.pagination is not None:
            return await collect_paginated_async(
                endpoint, body=body or {}, fetch=fetch_one,
                concurrency=self._config.page_concurrency,
            )
        return await self._request_once(endpoint, body or {}, query)

    async def _request_once(
        self,
        endpoint: EndpointDef,
        body: Any,
        query: dict[str, str | int] | None,
    ) -> Any:
        try:
            token = await self._get_token()
            return await request_json_async(
                self._http_client(), self._config, endpoint,
                body=body, token=token, query=query,
            )
        except ApiError as error:
            if error.code in AUTH_RETRY_CODES and self._config.access_key and self._config.secret_key:
                self._memo_cache = None
                token = await self._get_token(force_refresh=True)
                return await request_json_async(
                    self._http_client(), self._config, endpoint,
                    body=body, token=token, query=query,
                )
            raise
```

- [ ] **Step 5: Add async smoke tests + unit tests**

Mirror Task 13's client tests but with `@pytest.mark.anyio` + `async def`. Mirror Task 9's pagination tests with async fetchers. Mirror Task 11's poll tests with `await poll_content_async(...)`. Aim for at least 6 new tests.

- [ ] **Step 6: Run + commit**

Run: `uv run pytest tests/unit -v` → all tests including async pass.

```bash
git add src/gangtise_openapi/_client.py src/gangtise_openapi/_pagination.py \
        src/gangtise_openapi/_quote_sharding.py src/gangtise_openapi/_async_content.py \
        tests/unit
git commit -m "feat(async): AsyncGangtiseClient + async pagination/sharding/polling"
```

---

### Task 26: Async domain wrappers (9 modules)

**Files (per domain):**
- Modify: `src/gangtise_openapi/domains/<name>.py` — add `class Async<Name>` next to the existing sync class.
- Modify: `src/gangtise_openapi/domains/__init__.py` — re-export async classes.
- Create: `tests/endpoints/test_<name>_async.py` — one smoke test per endpoint.

**Pattern** (apply to every domain):

```python
class AsyncQuote:
    def __init__(self, client: "AsyncGangtiseClient") -> None:
        self._client = client

    async def realtime(self, *, security: Any, field: Any = None, raw: bool = False):
        body = _strip_none({
            "securityList": _as_list(security),
            "fieldList": _as_list(field),
        })
        result = await self._client._call("quote.realtime", body=body)
        if raw:
            return result
        rows = result if isinstance(result, list) else result.get("list", [])
        return to_dataframe(rows, schema=_REALTIME_SCHEMA)
    # ... mirror each sync method, with `async def` and `await`
```

For domains with sharded K-line (Quote): call `fetch_shards_async` instead of `fetch_shards`. For AI's earnings-review / viewpoint-debate: use `poll_content_async`.

For downloads: extend `_download.py` with `download_to_path_async(...)` (same signature but async + `httpx.AsyncClient.stream`). Apply the same wrapper substitution rule.

- [ ] **Step 1: Add the async download helper to `_download.py`**

```python
async def download_to_path_async(
    *,
    client: "AsyncGangtiseClient",
    endpoint_key: str,
    query: dict[str, str | int],
    output: str | Path | None,
    fallback_name: str,
) -> Path:
    endpoint = lookup(endpoint_key)
    if endpoint.kind != "download":
        raise DownloadError(f"endpoint {endpoint_key} is not a download endpoint")

    token = await client._get_token()
    headers = {"Authorization": normalize_token(token)}
    http = client._http_client()
    async with http.stream(
        endpoint.method, endpoint.path, params=query, headers=headers,
    ) as response:
        if response.status_code >= 400:
            await response.aread()
            raise DownloadError(
                f"download failed: HTTP {response.status_code} {response.text[:200]}"
            )
        content_disposition = response.headers.get("content-disposition")
        content_type = response.headers.get("content-type")
        if output is None:
            filename = _parse_content_disposition(content_disposition)
            if not filename:
                filename = f"{fallback_name}{_extension_for(content_type)}"
            target = Path.cwd() / filename
        else:
            target = Path(output).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with tmp.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)
            tmp.replace(target)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise DownloadError(f"failed to write to {target}: {exc}") from exc
    return target
```

- [ ] **Step 2: For each of the 9 domain modules, add the `Async<Name>` class**

Mirror the sync class. Reuse all helper functions (`_as_list`, `_strip_none`, schema constants). Methods are `async def` and call `await self._client._call(...)`. Where the sync version called `download_to_path(client=self._client, ...)`, the async version calls `await download_to_path_async(client=self._client, ...)`.

- [ ] **Step 3: Add smoke tests for each domain**

Each test file mirrors the sync test file. Pattern (asyncio + respx):

```python
import httpx
import pandas as pd
import pytest
import respx

from gangtise_openapi._client import AsyncGangtiseClient
from gangtise_openapi._config import Config
from gangtise_openapi.domains.quote import AsyncQuote


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_async_realtime(tmp_path):
    cfg = Config(
        base_url="https://api.test",
        access_key="ak", secret_key="sk", token="tok",
        token_cache_path=tmp_path / "tok.json",
        title_cache_path=tmp_path / "title.json",
    )
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": [{"securityCode": "000001.SH", "price": 1.2}],
                },
            )
        )
        async with AsyncGangtiseClient(_config=cfg) as client:
            df = await AsyncQuote(client).realtime(security=["000001.SH"])
    assert isinstance(df, pd.DataFrame)
    assert df.iloc[0]["price"] == 1.2
```

- [ ] **Step 4: Run + commit (per domain, small commits)**

Run: `uv run pytest tests/endpoints -v` → all sync + async tests pass.

Commits, one per domain:
```
feat(auth-async): mirror Auth with AsyncAuth
feat(lookup-async): mirror Lookup with AsyncLookup
feat(reference-async): mirror Reference with AsyncReference
feat(insight-async): mirror Insight with AsyncInsight (19)
feat(quote-async): mirror Quote with AsyncQuote (sharded)
feat(fundamental-async): mirror Fundamental with AsyncFundamental (12)
feat(ai-async): mirror AI with AsyncAI incl. async polling
feat(vault-async): mirror Vault with AsyncVault (10)
feat(alternative-async): mirror Alternative with AsyncAlternative
```

---

### Task 27: Wire async facade (`gangtise.async_`)

**Files:**
- Modify: `src/gangtise_openapi/_facade.py`
- Modify: `src/gangtise_openapi/__init__.py`
- Create: `tests/unit/test_facade_async.py`

The async mirror lives at `gangtise.async_` — same API surface but every method returns an awaitable.

- [ ] **Step 1: Extend `_Facade` with the async mirror**

```python
from gangtise_openapi._client import AsyncGangtiseClient


class _AsyncFacade:
    _DOMAIN_FACTORIES: dict[str, str] = {
        "auth": "gangtise_openapi.domains.auth:AsyncAuth",
        "lookup": "gangtise_openapi.domains.lookup:AsyncLookup",
        "reference": "gangtise_openapi.domains.reference:AsyncReference",
        "insight": "gangtise_openapi.domains.insight:AsyncInsight",
        "quote": "gangtise_openapi.domains.quote:AsyncQuote",
        "fundamental": "gangtise_openapi.domains.fundamental:AsyncFundamental",
        "ai": "gangtise_openapi.domains.ai:AsyncAI",
        "vault": "gangtise_openapi.domains.vault:AsyncVault",
        "alternative": "gangtise_openapi.domains.alternative:AsyncAlternative",
    }

    def __init__(self) -> None:
        self._client: AsyncGangtiseClient | None = None
        self._domains: dict[str, Any] = {}

    def _ensure_client(self) -> AsyncGangtiseClient:
        if self._client is None:
            cfg = load_config()
            self._client = AsyncGangtiseClient(_config=cfg)
        return self._client

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._DOMAIN_FACTORIES:
            raise AttributeError(f"unknown async domain: {name!r}")
        if name not in self._domains:
            module_path, class_name = self._DOMAIN_FACTORIES[name].split(":")
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            self._domains[name] = cls(self._ensure_client())
        return self._domains[name]


class _Facade:
    # ... existing sync code ...

    @property
    def async_(self) -> _AsyncFacade:
        if not hasattr(self, "_async_facade"):
            self._async_facade = _AsyncFacade()
        return self._async_facade
```

Also extend `_DOMAIN_FACTORIES` on the sync facade with the remaining sync domains:

```python
    _DOMAIN_FACTORIES: dict[str, str] = {
        "auth": "gangtise_openapi.domains.auth:Auth",
        "lookup": "gangtise_openapi.domains.lookup:Lookup",
        "reference": "gangtise_openapi.domains.reference:Reference",
        "insight": "gangtise_openapi.domains.insight:Insight",
        "quote": "gangtise_openapi.domains.quote:Quote",
        "fundamental": "gangtise_openapi.domains.fundamental:Fundamental",
        "ai": "gangtise_openapi.domains.ai:AI",
        "vault": "gangtise_openapi.domains.vault:Vault",
        "alternative": "gangtise_openapi.domains.alternative:Alternative",
    }
```

- [ ] **Step 2: Update `__init__.py`**

```python
from gangtise_openapi._client import AsyncGangtiseClient, GangtiseClient
# ... existing imports

__all__ = [
    "__version__", "gangtise",
    "GangtiseClient", "AsyncGangtiseClient",
    "ApiError", "ConfigError", "DownloadError", "GangtiseError", "ValidationError",
]
```

- [ ] **Step 3: Add facade tests `tests/unit/test_facade_async.py`**

```python
import pytest

from gangtise_openapi._facade import _Facade


def test_async_mirror_lazy_creates_async_client(monkeypatch, tmp_path):
    monkeypatch.setenv("GANGTISE_ACCESS_KEY", "ak")
    monkeypatch.setenv("GANGTISE_SECRET_KEY", "sk")
    monkeypatch.setenv("GANGTISE_TOKEN_CACHE_PATH", str(tmp_path / "tok.json"))

    f = _Facade()
    async_facade = f.async_
    assert async_facade is f.async_   # cached

    from gangtise_openapi._client import AsyncGangtiseClient
    assert isinstance(async_facade._ensure_client(), AsyncGangtiseClient)
```

- [ ] **Step 4: Run + commit**

Run: `uv run pytest -v` → all pass.

```bash
git add src/gangtise_openapi/_facade.py src/gangtise_openapi/__init__.py tests/unit/test_facade_async.py
git commit -m "feat(facade): expose gangtise.async_ mirror + finalize public exports"
```

---

## Phase 8 — Release Pipeline & First Publication

### Task 28: README quickstart + CHANGELOG entry

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Rewrite `README.md`**

```markdown
# gangtise-openapi

Python SDK for [Gangtise OpenAPI](https://open.gangtise.com). Feature-parity with the npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.14.2 across 73 endpoints.

## Install

```bash
pip install gangtise-openapi
```

Requires Python 3.10+.

## Configure

```bash
export GANGTISE_ACCESS_KEY=ak_xxx
export GANGTISE_SECRET_KEY=sk_xxx
```

(Or pass `access_key=` and `secret_key=` explicitly to `GangtiseClient`.) The token cache file at `~/.config/gangtise/token.json` is shared with the npm CLI.

## Quickstart

```python
from gangtise_openapi import gangtise

# Tabular endpoints return a pandas DataFrame
df = gangtise.quote.day_kline(security="000001.SH", start_date="2026-01-01", end_date="2026-01-31")

# Use raw=True to get the underlying dict/list
result = gangtise.insight.opinion_list(industry=1, size=20, raw=True)

# Async
import asyncio

async def main():
    df = await gangtise.async_.quote.day_kline(security="000001.SH")

asyncio.run(main())
```

## Endpoints

The SDK exposes 73 endpoints across 9 domains:

- `gangtise.auth.*` — login, status
- `gangtise.lookup.*` — local lookup tables (research areas, brokers, industries, ...)
- `gangtise.reference.*` — securities search (GTS codes)
- `gangtise.insight.*` — opinions, research reports, announcements, schedules
- `gangtise.quote.*` — K-line, real-time quotes
- `gangtise.fundamental.*` — financial statements, valuation, holders, forecasts
- `gangtise.ai.*` — AI-generated insights (one-pager, peer comparison, earnings reviews, ...)
- `gangtise.vault.*` — personal drive, meeting records, stock pools, WeChat
- `gangtise.alternative.*` — economic indicators (EDB)

See the [npm CLI README](https://github.com/gangtiser/gangtise-openapi-cli#readme) for endpoint-by-endpoint documentation; the Python wrappers accept the same parameters as the CLI flags (snake_case instead of `--kebab-case`).

## License

MIT
```

- [ ] **Step 2: Update `CHANGELOG.md`**

```markdown
## [0.1.0] — TBD

### Added
- Initial release.
- 73 endpoints from gangtise-openapi-cli v0.14.2.
- Sync (`gangtise`) and async (`gangtise.async_`) APIs.
- DataFrame-by-default returns with `raw=True` escape hatch.
- Auto-pagination concurrency, retry + token self-heal, K-line full-market date sharding, transparent async-content polling.
- Token cache shared with the npm CLI at `~/.config/gangtise/token.json`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: README quickstart + CHANGELOG 0.1.0 entry"
```

---

### Task 29: Release workflow + RELEASE.md checklist

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `docs/RELEASE.md`

- [ ] **Step 1: Write `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # for PyPI Trusted Publishing
      contents: write   # for GitHub Release
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Set up Python
        run: uv python install 3.12
      - name: Sync deps
        run: uv sync --all-extras
      - name: Verify version matches tag
        run: |
          PKG_VERSION=$(uv run python -c "from gangtise_openapi.__about__ import __version__; print(__version__)")
          TAG_VERSION=${GITHUB_REF#refs/tags/v}
          test "$PKG_VERSION" = "$TAG_VERSION" || (echo "Version mismatch: $PKG_VERSION vs $TAG_VERSION"; exit 1)
      - name: Lint + type-check + test
        run: |
          uv run ruff check .
          uv run ruff format --check .
          uv run mypy src
          uv run pytest -m "not live"
      - name: Build
        run: uv build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/
      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create "$GITHUB_REF_NAME" --generate-notes dist/*
```

- [ ] **Step 2: Write `docs/RELEASE.md`**

```markdown
# Release Checklist

1. Full test suite green locally:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src
   uv run pytest -m "not live"
   ```
2. Run live integration tests at least once (requires real credentials):
   ```bash
   uv run pytest -m live
   ```
3. Update `CHANGELOG.md` with the new version section.
4. Bump `src/gangtise_openapi/__about__.py` (`__version__`).
5. Commit: `git commit -am "release: vX.Y.Z"`.
6. Tag: `git tag vX.Y.Z && git push --follow-tags`.
7. CI workflow `.github/workflows/release.yml` runs build + publish + GitHub Release.
8. Verify on PyPI: `pip install gangtise-openapi==X.Y.Z` in a clean venv.

## Initial setup

Before the first release, configure PyPI Trusted Publishing for the `gangtise-openapi` project:

1. Claim the `gangtise-openapi` name on PyPI (verified free as of 2026-05-27).
2. Add a Trusted Publisher in PyPI project settings:
   - Owner: `gangtiser`
   - Repository: `gangtise-openapi-python`
   - Workflow: `release.yml`
   - Environment: (leave blank)
3. Run the workflow once via TestPyPI by temporarily pointing `pypa/gh-action-pypi-publish@release/v1` at `repository-url: https://test.pypi.org/legacy/`. Revert before tagging the real `v0.1.0`.
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml docs/RELEASE.md
git commit -m "ci: release workflow + RELEASE.md checklist"
```

---

### Task 30: Integration test scaffold (manual-only)

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_live.py`
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`**

```bash
# Copy to .env and fill in real credentials. Never commit .env.
GANGTISE_ACCESS_KEY=
GANGTISE_SECRET_KEY=
```

- [ ] **Step 2: Create `tests/integration/__init__.py` (empty file)**

```
```

- [ ] **Step 3: Create `tests/integration/test_live.py`**

```python
"""Live integration tests. Run with `pytest -m live`.

Required env vars: GANGTISE_ACCESS_KEY, GANGTISE_SECRET_KEY (or a valid GANGTISE_TOKEN).
Skipped by default. CI never runs these.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from gangtise_openapi import GangtiseClient


pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client() -> GangtiseClient:
    if not (os.environ.get("GANGTISE_ACCESS_KEY") or os.environ.get("GANGTISE_TOKEN")):
        pytest.skip("no live credentials configured")
    with GangtiseClient() as c:
        yield c


def test_live_login(client: GangtiseClient):
    result = client.login()
    assert result["authorization"].startswith("Bearer ")


def test_live_lookup_research_areas(client: GangtiseClient):
    from gangtise_openapi.domains.lookup import Lookup
    df = Lookup(client).research_areas()
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_live_quote_realtime(client: GangtiseClient):
    from gangtise_openapi.domains.quote import Quote
    df = Quote(client).realtime(security=["000001.SH"])
    assert isinstance(df, pd.DataFrame)
```

- [ ] **Step 4: Verify the marker is honored**

Run: `uv run pytest -v`
Expected: live tests are deselected (the suite reports them under "deselected by `-m 'not live'`" or just skipped on missing credentials).

Run: `uv run pytest -m live -v` → either skipped (no creds) or runs and passes.

- [ ] **Step 5: Commit**

```bash
git add tests/integration .env.example
git commit -m "test: integration scaffold for live API smoke checks"
```

---

### Task 31: TestPyPI dry-run + first publish

**Files:**
- Modify: `src/gangtise_openapi/__about__.py` to `0.1.0`
- Modify: `CHANGELOG.md` finalize the `[0.1.0]` date
- Modify: `.github/workflows/release.yml` (optional: add a `workflow_dispatch` input to publish to TestPyPI)

- [ ] **Step 1: Verify build artifacts locally**

Run:
```bash
uv build
uv run python -c "import tarfile, zipfile, pathlib; print(sorted(p.name for p in pathlib.Path('dist').iterdir()))"
```
Expected: `dist/gangtise_openapi-0.1.0-py3-none-any.whl` and `dist/gangtise_openapi-0.1.0.tar.gz`.

- [ ] **Step 2: Sanity-install in a throwaway venv**

```bash
uv venv .check-venv
.check-venv/bin/pip install dist/gangtise_openapi-0.1.0-py3-none-any.whl
.check-venv/bin/python -c "from gangtise_openapi import gangtise; print(type(gangtise).__name__)"
```
Expected: prints `_Facade`. Then remove `.check-venv`.

- [ ] **Step 3: Confirm PyPI Trusted Publisher is configured**

Visit https://pypi.org/manage/project/gangtise-openapi/settings/publishing/ and verify the entry pointing at `gangtiser/gangtise-openapi-python` and workflow `release.yml`.

- [ ] **Step 4: TestPyPI smoke (optional)**

Manually upload the local build to TestPyPI:
```bash
uv publish --publish-url https://test.pypi.org/legacy/ --token "$TEST_PYPI_TOKEN"
```
Verify a fresh venv can install from TestPyPI:
```bash
uv venv .test-pypi-venv
.test-pypi-venv/bin/pip install --index-url https://test.pypi.org/simple/ gangtise-openapi==0.1.0
.test-pypi-venv/bin/python -c "from gangtise_openapi import gangtise; print(gangtise)"
```

- [ ] **Step 5: Finalize version + tag**

Update `__about__.py` from `0.1.0.dev0` to `0.1.0`.
Update `CHANGELOG.md`: replace `## [0.1.0] — TBD` with `## [0.1.0] — 2026-MM-DD` using the actual date.

```bash
git add src/gangtise_openapi/__about__.py CHANGELOG.md
git commit -m "release: v0.1.0"
git tag v0.1.0
git push origin main --follow-tags
```

- [ ] **Step 6: Watch the release workflow**

Open https://github.com/gangtiser/gangtise-openapi-python/actions and confirm the `Release` workflow succeeds. Verify the package is live on PyPI:

```bash
uv venv .verify-venv
.verify-venv/bin/pip install gangtise-openapi==0.1.0
.verify-venv/bin/python -c "from gangtise_openapi import gangtise, __version__; print(__version__)"
```
Expected: prints `0.1.0`.

---

## Self-Review

**Spec coverage check** (per `docs/superpowers/specs/2026-05-27-gangtise-openapi-python-design.md`):

| Spec section | Covered by |
|---|---|
| §2 PyPI name `gangtise-openapi` | Task 1 (`pyproject.toml`) |
| §2 Python 3.10+ | Task 1 (`requires-python`) |
| §2 uv + hatchling | Task 1 |
| §3 three-layer architecture | Tasks 13 (client), 15-20 (domains), 14 (facade) |
| §4 file layout | Reflected in File Structure table + Task file targets |
| §5 Path A (sync tabular) | Task 13 + Tasks 15-20 + Task 12 normalize |
| §5 Path B (async polling) | Tasks 11, 19 (sync), 25, 26 (async) |
| §5 Path C (streaming download) | Tasks 21, 22, 26 |
| §5 retry policy (429/5xx/network/999999, auth-code self-heal) | Task 8, Task 13 (auth retry), Task 24 (async mirror) |
| §5 exception tree | Task 3 |
| §6 env vars + token cache | Tasks 4, 5, 13 |
| §6 `configure()` semantics | Task 14 |
| §6 logging | Task 23 |
| §7 unit tests + endpoint smokes + live integration | Throughout; Task 30 wires the live marker |
| §8 SemVer + `__about__.py` | Task 1 |
| §8 release workflow + GH Release | Task 29 |
| §8 compatibility contract | Reflected in `__init__.py` exports (Tasks 13, 14, 27) |
| §9 in-scope: title cache | Task 21 |
| §9 out of scope: Retry-After/Pydantic/codegen | Not implemented — correct |
| §10 resolved questions (slug, PyPI name, license) | Tasks 1, 29 |

**Placeholder scan:** the plan deliberately leaves three "translate from TS source" instructions:

1. **Task 6 step 3** — the full 73-entry endpoint dict body is described as "translate every entry from `endpoints.ts`". This is not a placeholder; it's a structured mechanical translation backed by:
   - A complete list of expected endpoint keys (step 5)
   - A test that fails until all 73 entries are present (step 4)
   - The exact format helper (`_ep(...)`)
   - The TS reference file path
2. **Task 7 step 1** — translating eight lookup data tables. The TS array shape is structurally simple (`{id, name}` etc.) and the per-file pattern is shown; tests assert the result is `list[dict]` with non-empty content.
3. **Tasks 16, 18, 19, 20** — each domain task lists an explicit endpoint manifest (Python kwargs ↔ TS body field names) and one full-code example. The remaining wrappers in each domain are produced by copy-and-substitute, with smoke tests pinning behavior.

These are concrete enough that an engineer with the TS source open can execute them mechanically. They are not "TBD" or "add appropriate error handling" — they are bounded translation tasks.

**Type consistency check:**
- `EndpointDef` fields: `key, method, path, kind, description, pagination` — consistent across Task 6, Task 8, Task 9, Task 17, Task 22.
- `Config` fields: `base_url, access_key, secret_key, token, token_cache_path, title_cache_path, timeout_ms, page_concurrency, verbose` — consistent across Tasks 4, 13, 14, 24, 25.
- `TokenCache` fields: `access_token, expires_in, time, expires_at, uid, user_name, tenant_id` — consistent across Tasks 5 and 13.
- `GangtiseClient` methods used by domains: `_call(endpoint_key, body, query)`, `_get_token`, `_http_client`, `config`, `login` — consistent across Tasks 13, 16-20, 22, 25, 26.
- `download_to_path` signature: `client, endpoint_key, query, output, fallback_name` — used identically in Tasks 22, 26.
- `poll_content` / `poll_content_async` signature: `fetch, *, sleep | (none for async), max_attempts` — consistent across Tasks 11, 19, 25.

No drift found in the cross-task signatures.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-27-gangtise-openapi-python.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
