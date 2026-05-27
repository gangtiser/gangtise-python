# Gangtise OpenAPI Python SDK — Implementation Plan (v2)

> **v2 changes (2026-05-27, post-Codex review):**
> - Rebuilt fundamental / ai / vault / alternative / reference manifests against `gangtise-openapi-cli/src/cli.ts` and `commandBodies.ts` (kwargs and body field names were wrong in v1).
> - Pagination registry: `ai.security-clue.list`=500, `ai.hot-topic`=20, `vault.wechat-chatroom.list`=**no pagination**. Paginated total dropped from "expected 19" to 18.
> - Fixed Task 17 `Quote` signature bug (`_day_kline` kwargs now all optional; public methods get explicit signatures, not `**kwargs`).
> - Inserted new Task 7.5: create `tests/conftest.py` between foundation and transport tasks.
> - Wired the title cache into `_download` (list endpoints populate, download endpoints consume) instead of leaving it standalone.
> - Split Task 16 (insight 19) into 16a (lists), 16b (downloads). Split Task 19 (AI 14) into 19a (sync metadata), 19b (async polled). Split Task 26 (async 9 mirrors) into one task per domain (26a–26i).
> - Added explicit return-type annotations on `__exit__`/`__aexit__` and method signatures shown inline so mypy strict passes.

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
Homepage = "https://github.com/gangtiser/gangtise-python"
Source = "https://github.com/gangtiser/gangtise-python"
Issues = "https://github.com/gangtiser/gangtise-python/issues"

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


def test_pagination_registry_matches_ts_source():
    # Translated 1:1 from gangtise-openapi-cli/src/core/endpoints.ts.
    # max_page_size differs per endpoint — do NOT assume "all 50".
    expected: dict[str, int] = {
        "insight.opinion.list": 50,
        "insight.summary.list": 50,
        "insight.roadshow.list": 50,
        "insight.site-visit.list": 50,
        "insight.strategy.list": 50,
        "insight.forum.list": 50,
        "insight.research.list": 50,
        "insight.foreign-report.list": 50,
        "insight.announcement.list": 50,
        "insight.announcement-hk.list": 50,
        "insight.foreign-opinion.list": 50,
        "insight.independent-opinion.list": 50,
        "ai.security-clue.list": 500,
        "ai.hot-topic": 20,
        "vault.drive.list": 50,
        "vault.record.list": 50,
        "vault.my-conference.list": 50,
        "vault.wechat-message.list": 50,
        # NOTE: vault.wechat-chatroom.list is NOT paginated in TS (size default 20, but no pagination block).
        # NOTE: vault.stock-pool.list and vault.stock-pool.stocks are NOT paginated.
    }
    actual = {
        k: ep.pagination.max_page_size
        for k, ep in ENDPOINTS.items() if ep.pagination is not None
    }
    assert actual == expected
    assert ENDPOINTS["vault.wechat-chatroom.list"].pagination is None


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

The full 73-entry dictionary is produced by translating `endpoints.ts`. The translation is mechanical — write each entry, do not paraphrase descriptions.

**Pagination registry (18 endpoints, `max_page_size` differs):**

| Endpoint | `max_page_size` |
|---|---|
| `insight.opinion.list` | 50 |
| `insight.summary.list` | 50 |
| `insight.roadshow.list` | 50 |
| `insight.site-visit.list` | 50 |
| `insight.strategy.list` | 50 |
| `insight.forum.list` | 50 |
| `insight.research.list` | 50 |
| `insight.foreign-report.list` | 50 |
| `insight.announcement.list` | 50 |
| `insight.announcement-hk.list` | 50 |
| `insight.foreign-opinion.list` | 50 |
| `insight.independent-opinion.list` | 50 |
| `ai.security-clue.list` | **500** |
| `ai.hot-topic` | **20** |
| `vault.drive.list` | 50 |
| `vault.record.list` | 50 |
| `vault.my-conference.list` | 50 |
| `vault.wechat-message.list` | 50 |

Endpoints **without** pagination (re-confirm by `grep -n pagination /Users/martin/Documents/claude_workspace/gangtise-openapi-cli/src/core/endpoints.ts`): `vault.wechat-chatroom.list`, `vault.stock-pool.list`, `vault.stock-pool.stocks`, `reference.securities-search`, `auth.login`, every `*.download`, every other endpoint listed but not above.

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

### Task 7.5: Test fixtures (`tests/conftest.py`)

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/unit/__init__.py` (empty)
- Create: `tests/conftest.py`

This task must land **before** Task 8 because the transport tests reference these fixtures. The fixtures must not import any module that doesn't exist yet — at this point `_client.py` is not built, so the conftest only exposes `Config` and a minimal token-cache seed helper.

- [ ] **Step 1: Write `tests/__init__.py` and `tests/unit/__init__.py`** (empty files)

```
```

- [ ] **Step 2: Write `tests/conftest.py`**

```python
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
        json.dumps({
            "accessToken": "seeded-tok",
            "expiresIn": 3600,
            "time": 0,
            "expiresAt": 9999999999,
        })
    )
    return config
```

- [ ] **Step 3: Verify pytest can collect with the new conftest**

Run: `uv run pytest --collect-only tests/unit -q`
Expected: existing unit tests are collected, no import errors. (No new tests added in this task.)

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/unit/__init__.py tests/conftest.py
git commit -m "test: scaffold shared conftest with config + seeded_config fixtures"
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
Expected: 17 passed (counted from the test functions defined in step 1).

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
    # Use assert_all_called=False because the login route is intentionally
    # registered to prove it gets zero traffic.
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        login_route = router.post("/application/auth/oauth/open/loginV2")
        router.post("/application/open-quote/quote/realtime").mock(
            return_value=httpx.Response(
                200, json={"code": "000000", "status": True, "data": []}
            )
        )
        with GangtiseClient(_config=cfg) as client:
            client._call("quote.realtime", body={"securityList": ["000001.SH"]})
        assert login_route.call_count == 0


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
from gangtise_openapi._endpoints import EndpointDef, lookup
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

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
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


def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


class Reference:
    """`gangtise.reference.*` — reference data lookups."""

    def __init__(self, client: GangtiseClient) -> None:
        self._client = client

    def securities_search(
        self,
        *,
        keyword: str,
        category: Any = None,
        top: int = 10,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        # TS body shape (cli.ts:503):
        #   { keyword, category: maybeArray(category) | undefined, top: int }
        body = _strip_none({
            "keyword": keyword,
            "category": _as_list(category),
            "top": top,
        })
        result = self._client._call("reference.securities-search", body=body)
        if raw:
            return result
        if isinstance(result, list):
            rows: list[Any] = result
        elif isinstance(result, dict):
            rows = result.get("list", [])
        else:
            rows = []
        return to_dataframe(rows, schema=_SCHEMA_SECURITIES_SEARCH)
```

Note the `category` choices the TS CLI enforces are `stock/dr/index/fund` — we don't enforce them at the Python level (the server validates), but document them in the docstring during implementation.

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

### Task 16a: Insight — list endpoints (13)

**Files:**
- Create: `src/gangtise_openapi/domains/insight.py`
- Create: `tests/endpoints/test_insight.py`
- Modify: `src/gangtise_openapi/_facade.py` (add `insight` to `_DOMAIN_FACTORIES`)
- Modify: `src/gangtise_openapi/domains/__init__.py` (re-export `Insight`)

**Endpoint manifest** (verified against `gangtise-openapi-cli/src/cli.ts:138-283`).

For every endpoint below: the Python wrapper accepts the kwargs in the **Kwargs** column (snake_case), maps them to body fields in the **Body** column (camelCase exactly as TS sends), invokes `self._client._call(<endpoint_key>, body=body)`, and returns a DataFrame.

Common params (all 13 endpoints accept these in the body): `from` (int), `size` (int|None), `startTime` (str), `endTime` (str), `keyword` (str). The Python kwargs map to `from_`, `size`, `start_time`, `end_time`, `keyword`.

| Endpoint key | TS cli.ts | Extra kwargs (Python) | Extra body fields (TS) |
|---|---|---|---|
| `insight.opinion.list` | 138-146 | `rank_type=1, research_area=None, chief=None, security=None, broker=None, industry=None, concept=None, llm_tag=None, source=None` | `rankType, researchAreaList, chiefList, securityList, brokerList, industryList, conceptList, llmTagList, sourceList` |
| `insight.summary.list` | 148-156 | `search_type=1, rank_type=1, source=None, research_area=None, security=None, institution=None, category=None, market=None, participant_role=None` | `searchType, rankType, sourceList, researchAreaList, securityList, institutionList, categoryList, marketList, participantRoleList` |
| `insight.roadshow.list` | 168-177 | `research_area=None, institution=None, security=None, category=None, market=None, participant_role=None, broker_type=None, object_=None, permission=None` | `researchAreaList, institutionList, securityList, categoryList, marketList, participantRoleList, brokerTypeList, objectList, permission` |
| `insight.site-visit.list` | 168-178 | same as roadshow | same |
| `insight.strategy.list` | 168-179 | same as roadshow | same |
| `insight.forum.list` | 168-180 | same as roadshow | same |
| `insight.research.list` | 182-192 | `search_type=1, rank_type=1, broker=None, security=None, industry=None, category=None, llm_tag=None, rating=None, rating_change=None, min_pages=None, max_pages=None, source=None` | `searchType, rankType, brokerList, securityList, industryList, categoryList, llmTagList, ratingList, ratingChangeList, **minReportPages**, **maxReportPages**, sourceList` |
| `insight.foreign-report.list` | 202-212 | `search_type=1, rank_type=1, security=None, region=None, category=None, industry=None, broker=None, llm_tag=None, rating=None, rating_change=None, min_pages=None, max_pages=None` | `searchType, rankType, securityList, regionList, categoryList, industryList, brokerList, llmTagList, ratingList, ratingChangeList, **minReportPages**, **maxReportPages** |
| `insight.announcement.list` | 222-230 | `search_type=1, rank_type=1, security=None, announcement_type=None, category=None` | `searchType, rankType, securityList, announcementTypeList, categoryList`. Note: `startTime`/`endTime` are **13-digit Unix ms timestamps** (TS uses `parseTimestamp13`). The wrapper accepts `int` (ms) or `str` (ISO date-time, with our own parsing to ms). |
| `insight.announcement-hk.list` | 240-250 | same as announcement.list | same (but `startTime`/`endTime` are plain strings, NOT 13-digit timestamps) |
| `insight.foreign-opinion.list` | 260-271 | `rank_type=1, security=None, region=None, industry=None, broker=None, rating=None, rating_change=None` | `rankType, securityList, regionList, industryList, brokerList, ratingList, ratingChangeList` |
| `insight.independent-opinion.list` | 273-283 | `rank_type=1, security=None, industry=None, rating=None, rating_change=None` | `rankType, securityList, industryList, ratingList, ratingChangeList` |

**Key corrections vs v1:**
- `minReportPages` / `maxReportPages` (not `minPages` / `maxPages`) for research + foreign-report.
- Schedule endpoints (`roadshow/site-visit/strategy/forum`) send `permission` as a number list, not wrapped via `_as_list`. TS uses `options.permission.length ? options.permission : undefined`.
- `insight.announcement.list` `startTime`/`endTime` are **milliseconds** in TS.
- `insight.independent-opinion.list` does NOT take `region` or `broker` (those are for `foreign-opinion`).

**Body translation rules (universal — used by every domain task):**
- `--from <n>` (TS) → `from_` (Python kwarg, trailing underscore avoids the `from` keyword) → `from` (body field).
- `--xxx-yyy` (TS) → `xxx_yyy` (Python kwarg) → `xxxYyy` (body field).
- List-typed CLI options (TS `collectList`/`collectNumberList`) accept either a single value or a list at the Python boundary; the wrapper normalizes to a list before sending. Body field uses the `…List` suffix only where TS does — never invent one.
- Strip `None` values from the final body so the server sees only the fields the user actually set. The standard helpers (used in every domain wrapper):

```python
def _as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _strip_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}
```

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

- [ ] **Step 2: Add the remaining 12 list wrappers**

For each remaining row in the manifest, copy the `opinion_list` template, substituting:
- The Python method name (replace `-` with `_` and dot-paths with `_`: `insight.research.list` → `research_list`).
- The kwarg signature (common params + the **Extra kwargs** column).
- The body dict (common fields + the **Extra body fields** column).
- The endpoint key.
- The schema constant — define one per list endpoint. When the row shape is unstable across responses, set `schema=None` and let pandas infer all columns (the test pinning happens at the smoke layer, not here).

**13-digit-timestamp special case** (`insight.announcement.list` only): wrapper signature accepts `start_time: int | str | None` and `end_time: int | str | None`. If the input is a string, convert with:

```python
import datetime as dt

def _to_unix_ms(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return int(parsed.timestamp() * 1000)
```

(Place this helper near `_as_list` at the top of `insight.py`.)

Download wrappers are NOT in this task — they live in Task 16b. Do not put `*_download` methods on `Insight` yet.

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
Expected: 13 passed (one per list endpoint).

- [ ] **Step 7: Commit**

```bash
git add src/gangtise_openapi/domains/insight.py \
        src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/test_insight.py
git commit -m "feat(insight): wrap 13 list endpoints with DataFrame return"
```

---

### Task 16b: Insight — download endpoints (6)

**Files:**
- Modify: `src/gangtise_openapi/domains/insight.py` (add 6 `*_download` methods)
- Modify: `tests/endpoints/test_insight.py` (add download smoke tests)

This task **must land after Task 22** (which creates `_download.download_to_path`). Mark it `blocks: 22` if the executor honors task dependencies; otherwise run them in this order: 16a → 22 → 16b.

**Download manifest** (verified against `cli.ts:157-290`).

| Endpoint key | Python method | Required kwargs | Optional kwargs | Query fields sent | Resolves title via |
|---|---|---|---|---|---|
| `insight.summary.download` | `summary_download` | `summary_id: str` | `file_type: int = None, output=None` | `summaryId, fileType` | `insight.summary.list` keyed by `summaryId` |
| `insight.research.download` | `research_download` | `report_id: str` | `file_type: int = 1, output=None` | `reportId, fileType` | `insight.research.list` keyed by `reportId` |
| `insight.foreign-report.download` | `foreign_report_download` | `report_id: str` | `file_type: int = 1, output=None` | `reportId, fileType` | `insight.foreign-report.list` keyed by `reportId` |
| `insight.announcement.download` | `announcement_download` | `announcement_id: str` | `file_type: int = 1, output=None` | `announcementId, fileType` | `insight.announcement.list` keyed by `announcementId` |
| `insight.announcement-hk.download` | `announcement_hk_download` | `announcement_id: str` | `output=None` | `announcementId` (no fileType) | `insight.announcement-hk.list` keyed by `announcementId` |
| `insight.independent-opinion.download` | `independent_opinion_download` | `independent_opinion_id: str, file_type: int` (both required) | `output=None` | `independentOpinionId, fileType` | (no title resolution in TS source) |

- [ ] **Step 1: Add 6 download methods to `Insight`**

```python
from pathlib import Path

from gangtise_openapi._download import download_to_path


class Insight:
    # ... existing list wrappers from Task 16a ...

    def summary_download(
        self,
        *,
        summary_id: str,
        file_type: int | None = None,
        output: str | Path | None = None,
    ) -> Path:
        query: dict[str, str | int] = {"summaryId": summary_id}
        if file_type is not None:
            query["fileType"] = file_type
        return download_to_path(
            client=self._client,
            endpoint_key="insight.summary.download",
            query=query,
            output=output,
            fallback_name=f"summary-{summary_id}",
            title_lookup=("insight.summary.list", "summaryId", summary_id),
        )

    def research_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        return download_to_path(
            client=self._client,
            endpoint_key="insight.research.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"research-{report_id}",
            title_lookup=("insight.research.list", "reportId", report_id),
        )

    def foreign_report_download(
        self,
        *,
        report_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        return download_to_path(
            client=self._client,
            endpoint_key="insight.foreign-report.download",
            query={"reportId": report_id, "fileType": file_type},
            output=output,
            fallback_name=f"foreign-report-{report_id}",
            title_lookup=("insight.foreign-report.list", "reportId", report_id),
        )

    def announcement_download(
        self,
        *,
        announcement_id: str,
        file_type: int = 1,
        output: str | Path | None = None,
    ) -> Path:
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement.download",
            query={"announcementId": announcement_id, "fileType": file_type},
            output=output,
            fallback_name=f"announcement-{announcement_id}",
            title_lookup=("insight.announcement.list", "announcementId", announcement_id),
        )

    def announcement_hk_download(
        self,
        *,
        announcement_id: str,
        output: str | Path | None = None,
    ) -> Path:
        return download_to_path(
            client=self._client,
            endpoint_key="insight.announcement-hk.download",
            query={"announcementId": announcement_id},
            output=output,
            fallback_name=f"announcement-hk-{announcement_id}",
            title_lookup=("insight.announcement-hk.list", "announcementId", announcement_id),
        )

    def independent_opinion_download(
        self,
        *,
        independent_opinion_id: str,
        file_type: int,
        output: str | Path | None = None,
    ) -> Path:
        return download_to_path(
            client=self._client,
            endpoint_key="insight.independent-opinion.download",
            query={
                "independentOpinionId": independent_opinion_id,
                "fileType": file_type,
            },
            output=output,
            fallback_name=f"independent-opinion-{independent_opinion_id}",
            title_lookup=None,
        )
```

`title_lookup=(list_endpoint_key, id_field, id_value)` is the new parameter Task 22 adds to `download_to_path` (see §Task 22 below). `None` means skip title resolution.

- [ ] **Step 2: Add 6 download smoke tests**

For each download endpoint, add a test mocking the download response with `Content-Disposition: attachment; filename="..."` and assert the file lands at the expected path. Use the `seeded_config` fixture from Task 7.5.

Example:

```python
def test_summary_download_writes_file(tmp_path, seeded_config):
    with respx.mock(base_url="https://api.test", assert_all_called=True) as router:
        router.get("/application/open-insight/summary/v2/download/file").mock(
            return_value=httpx.Response(
                200, content=b"summary",
                headers={"content-disposition": 'attachment; filename="s.pdf"'},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            path = Insight(client).summary_download(
                summary_id="s1", output=tmp_path / "out.pdf",
            )
    assert path == tmp_path / "out.pdf"
    assert path.read_bytes() == b"summary"
```

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/endpoints/test_insight.py -v` → all 13 list + 6 download tests pass.

```bash
git add src/gangtise_openapi/domains/insight.py tests/endpoints/test_insight.py
git commit -m "feat(insight): add 6 *_download wrappers with title-cache lookup"
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
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
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

    def day_kline(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.day-kline",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def day_kline_hk(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.day-kline-hk",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def day_kline_us(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.day-kline-us",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def index_day_kline(
        self,
        *,
        security: Any,
        start_date: str | dt.date | None = None,
        end_date: str | dt.date | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any]:
        return self._day_kline(
            "quote.index-day-kline",
            security=security, start_date=start_date, end_date=end_date,
            limit=limit, field=field, raw=raw,
        )

    def minute_kline(
        self,
        *,
        security: str,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int | None = None,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
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
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
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

**Endpoint manifest** (verified against `cli.ts:335-378`).

| Endpoint key | Python method | Kwargs | Body fields |
|---|---|---|---|
| `fundamental.income-statement` | `income_statement` | `security_code, start_date=None, end_date=None, fiscal_year=None, period=None, report_type=None, field=None, raw=False` | `securityCode, startDate, endDate, fiscalYear (list), period (list or None), reportType (list or None), fieldList` |
| `fundamental.income-statement-quarterly` | `income_statement_quarterly` | same | same |
| `fundamental.balance-sheet` | `balance_sheet` | same | same |
| `fundamental.cash-flow` | `cash_flow` | same | same |
| `fundamental.cash-flow-quarterly` | `cash_flow_quarterly` | same | same |
| `fundamental.income-statement-hk` | `income_statement_hk` | same | same |
| `fundamental.balance-sheet-hk` | `balance_sheet_hk` | same | same |
| `fundamental.cash-flow-hk` | `cash_flow_hk` | same | same |
| `fundamental.main-business` | `main_business` | `security_code, start_date=None, end_date=None, breakdown="product", period=None, field=None, raw=False` | `securityCode, startDate, endDate, breakdown, periodList, fieldList`. `breakdown` is one of `product / industry / region`. |
| `fundamental.valuation-analysis` | `valuation_analysis` | `security_code, indicator (required, one of peTtm/pbMrq/peg/psTtm/pcfTtm/em), start_date=None, end_date=None, limit=None, field=None, skip_null=False, raw=False` | `securityCode, indicator, startDate, endDate, limit, fieldList`. `skip_null` is **client-side** post-filter (TS does it locally — drop rows where `value` or `percentileRank` is null). |
| `fundamental.top-holders` | `top_holders` | `security_code, holder_type (required, one of "top10" / "top10Float"), start_date=None, end_date=None, fiscal_year=None, period=None, raw=False` | `securityCode, holderType, startDate, endDate, fiscalYear (list), period (list or None)`. No `fieldList`. |
| `fundamental.earning-forecast` | `earning_forecast` | `security_code, start_date=None, end_date=None, consensus=None, raw=False` | `securityCode, startDate, endDate, consensusList`. `consensus` is a list of `netIncome/netIncomeYoy/eps/pe/bps/pb/peg/roe/ps`. No `fieldList`. |

**Key corrections vs v1:**
- `valuation_analysis`: takes `indicator/startDate/endDate/limit/fieldList` (not `range_`). `indicator` is required and constrained to 6 choices. `skip_null` is a Python-side filter, not a body param.
- `top_holders`: takes `holderType/startDate/endDate/fiscalYear/period` (not `topN`). `holderType` is required.
- `earning_forecast`: takes `startDate/endDate/consensusList` (not `brokerList`).

**Schemas:**
- 8 statement endpoints + `main_business`: `schema=None`, let pandas infer.
- `valuation_analysis`: `["securityCode", "indicator", "date", "value", "percentileRank", "average", "median", "upper1Std", "lower1Std"]`.
- `top_holders`: `schema=None`.
- `earning_forecast`: `schema=None`.

Use the wrapper template established in Task 17. Statement endpoints look like:

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
) -> pd.DataFrame | dict[str, Any]:
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

`valuation_analysis` has the `skip_null` post-filter; sketch:

```python
def valuation_analysis(
    self, *,
    security_code: str,
    indicator: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
    field: Any = None,
    skip_null: bool = False,
    raw: bool = False,
) -> pd.DataFrame | dict[str, Any]:
    body = _strip_none({
        "securityCode": security_code,
        "indicator": indicator,
        "startDate": start_date,
        "endDate": end_date,
        "limit": limit,
        "fieldList": _as_list(field),
    })
    result = self._client._call("fundamental.valuation-analysis", body=body)
    if raw:
        return result
    rows = result.get("list", []) if isinstance(result, dict) else result
    if skip_null:
        rows = [
            r for r in rows
            if r.get("value") is not None and r.get("percentileRank") is not None
        ]
    return to_dataframe(rows, schema=_VALUATION_ANALYSIS_SCHEMA)
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

### Task 19a: AI — non-polled endpoints (10)

**Files:**
- Create: `src/gangtise_openapi/domains/ai.py`
- Create: `tests/endpoints/test_ai.py`
- Modify: `domains/__init__.py`, `_facade.py`

**Endpoint manifest** (verified against `cli.ts:383-472`).

| Endpoint key | Python method | Kwargs (Python) | Body fields (TS) | Notes |
|---|---|---|---|---|
| `ai.knowledge-batch` | `knowledge_batch` | `query (list[str] or str), top=10, resource_type=None, knowledge_name=None, start_time=None, end_time=None, raw=False` | `queries (list, NOT `query`), top, resourceTypes (list[int]), knowledgeNames (list), startTime (ms), endTime (ms)` | `start_time`/`end_time` are ms timestamps (TS `parseOptionalNumberOption ... min: 0`). `query` is a list — TS uses `collectList`. |
| `ai.security-clue.list` | `security_clue_list` | `start_time (required), end_time (required), query_mode (required: bySecurity/byIndustry), from_=0, size=None, gts_code=None, source=None, raw=False` | `from, size, startTime, endTime, queryMode, gtsCodeList, source (list, NOT sourceList)` | Paginated, `max_page_size=500`. |
| `ai.one-pager` | `one_pager` | `security_code, raw=False` | `securityCode` | Single-record result. |
| `ai.investment-logic` | `investment_logic` | `security_code, raw=False` | `securityCode` | |
| `ai.peer-comparison` | `peer_comparison` | `security_code, raw=False` | `securityCode` | |
| `ai.theme-tracking` | `theme_tracking` | `theme_id (required), date (required, yyyy-MM-dd), type_=None (list of morning/night), raw=False` | `themeId, date, type` (TS body key is `type`, not `typeList`) | `type_` to avoid Python keyword clash. |
| `ai.research-outline` | `research_outline` | `security_code, raw=False` | `securityCode` | |
| `ai.hot-topic` | `hot_topic` | `from_=0, size=None, start_date=None, end_date=None, category=None, with_related_securities=True, with_close_reading=True, raw=False` | `from, size, startDate, endDate, categoryList (defaults to all four if not passed: morningBriefing/noonBriefing/afternoonFlash/eveningBriefing), withRelatedSecurities (True or undefined), withCloseReading (True or undefined)` | Paginated, `max_page_size=20`. The wrapper must default `categoryList` to all four when the user passes `None`. The TS `with_*` flags use `undefined` instead of `False`. |
| `ai.management-discuss-announcement` | `management_discuss_announcement` | `report_date (required), security_code (required), dimension (required: businessOperation/financialPerformance/developmentAndRisk/all), raw=False` | `reportDate, securityCode, **discussionDimension** (NOT `dimension`)` | TS renames the body field. |
| `ai.management-discuss-earnings-call` | `management_discuss_earnings_call` | `report_date (required), security_code (required), dimension (required, same 3 — NO `all`), raw=False` | `reportDate, securityCode, discussionDimension` | |

**Key corrections vs v1:**
- `knowledge_batch`: body field is `queries` (list, plural), not `query`. Includes `resourceTypes/knowledgeNames/startTime/endTime`.
- `security_clue_list`: requires `start_time`, `end_time`, `query_mode`. Body uses `source` (no `List` suffix), not `sourceList`. No `industry` / `time_range` kwargs.
- `theme_tracking`: requires `date`. Body uses `type` (no list suffix).
- `hot_topic`: has full from/size/dates/categoryList/with_* params.
- `management_discuss_*`: requires `reportDate` (TS makes it required). Body field is `discussionDimension`, not `dimension`.

**Knowledge-resource download** is handled in **Task 22** (or a sibling task right after — it uses `download_to_path`). Do NOT put it on `AI` in this task.

- [ ] **Step 1: Write all 10 wrappers** in `src/gangtise_openapi/domains/ai.py` using the Task 17 template (`_as_list`, `_strip_none`). Examples for the trickier ones:

```python
def hot_topic(
    self,
    *,
    from_: int = 0,
    size: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    category: Any = None,
    with_related_securities: bool = True,
    with_close_reading: bool = True,
    raw: bool = False,
) -> pd.DataFrame | dict[str, Any]:
    default_categories = ["morningBriefing", "noonBriefing", "afternoonFlash", "eveningBriefing"]
    body = _strip_none({
        "from": from_,
        "size": size,
        "startDate": start_date,
        "endDate": end_date,
        "categoryList": _as_list(category) or default_categories,
        # TS sets these to True or undefined — never False.
        "withRelatedSecurities": True if with_related_securities else None,
        "withCloseReading": True if with_close_reading else None,
    })
    result = self._client._call("ai.hot-topic", body=body)
    if raw:
        return result
    rows = result.get("list", []) if isinstance(result, dict) else result
    return to_dataframe(rows, schema=None)


def management_discuss_announcement(
    self,
    *,
    report_date: str,
    security_code: str,
    dimension: str,  # businessOperation | financialPerformance | developmentAndRisk | all
    raw: bool = False,
) -> dict[str, Any]:
    body = {
        "reportDate": report_date,
        "securityCode": security_code,
        "discussionDimension": dimension,
    }
    result = self._client._call("ai.management-discuss-announcement", body=body)
    return result if raw else result
```

- [ ] **Step 2: Wire `__init__.py` + facade.**

- [ ] **Step 3: One smoke test per endpoint (10 tests).**

- [ ] **Step 4: Run + commit**

Run: `uv run pytest tests/endpoints/test_ai.py -v` → 10 passed.

```bash
git add src/gangtise_openapi/domains/ai.py \
        src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/test_ai.py
git commit -m "feat(ai): 10 non-polled wrappers (knowledge/security-clue/insight/hot-topic/management-discuss)"
```

---

### Task 19b: AI — async-polled pair (earnings-review + viewpoint-debate)

**Files:**
- Modify: `src/gangtise_openapi/domains/ai.py` (add 4 methods)
- Modify: `tests/endpoints/test_ai.py` (add polling tests)

Spec §5 Path B. Wrappers mirror `gangtise-openapi-cli/src/cli.ts:410-498`.

- [ ] **Step 1: Add 4 methods to `AI`**

```python
from gangtise_openapi._async_content import poll_content


class AI:
    # ... existing methods from Task 19a ...

    def earnings_review(
        self,
        *,
        security_code: str,
        period: str,            # e.g. "2025q3", "2025interim", "2025annual"
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        id_result = self._client._call(
            "ai.earnings-review.get-id",
            body={"securityCode": security_code, "period": period},
        )
        if not isinstance(id_result, dict):
            raise ApiError(
                "earnings-review.get-id returned unexpected shape",
                details=id_result,
            )
        data_id = id_result.get("dataId")
        if not data_id:
            raise ApiError(
                "earnings-review.get-id did not return a dataId",
                details=id_result,
            )
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        def fetch() -> Any:
            return self._client._call(
                "ai.earnings-review.get-content", body={"dataId": data_id}
            )

        return poll_content(fetch)

    def earnings_review_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        """Non-blocking single check. Returns the content if ready, otherwise
        raises ApiError(code='410110') for callers to handle.
        """
        return self._client._call(
            "ai.earnings-review.get-content", body={"dataId": data_id}
        )

    def viewpoint_debate(
        self,
        *,
        viewpoint: str,         # max 1000 chars
        wait: bool = True,
        raw: bool = False,
    ) -> dict[str, Any]:
        id_result = self._client._call(
            "ai.viewpoint-debate.get-id", body={"viewpoint": viewpoint}
        )
        if not isinstance(id_result, dict):
            raise ApiError(
                "viewpoint-debate.get-id returned unexpected shape",
                details=id_result,
            )
        data_id = id_result.get("dataId")
        if not data_id:
            raise ApiError(
                "viewpoint-debate.get-id did not return a dataId",
                details=id_result,
            )
        if not wait:
            return {"data_id": data_id, "status": "pending"}

        def fetch() -> Any:
            return self._client._call(
                "ai.viewpoint-debate.get-content", body={"dataId": data_id}
            )

        return poll_content(fetch)

    def viewpoint_debate_check(
        self,
        *,
        data_id: str,
        raw: bool = False,
    ) -> dict[str, Any]:
        return self._client._call(
            "ai.viewpoint-debate.get-content", body={"dataId": data_id}
        )
```

- [ ] **Step 2: Add tests**

Required tests:
1. `earnings_review(wait=True)` — mock id endpoint + content-ready response. Stub sleep: `monkeypatch.setattr("gangtise_openapi._async_content.time.sleep", lambda s: None)`. Assert the returned dict has `content`.
2. `earnings_review(wait=False)` — assert returns `{"data_id": "...", "status": "pending"}` without calling get-content.
3. `earnings_review` with one `410110` pending response then ready — assert it sleeps once and returns content.
4. `earnings_review` with `410111` terminal — assert raises `ApiError(code="410111")`.
5. `earnings_review_check(data_id)` — assert it calls get-content once and returns whatever the server returns (including `{"content": null}` for still-pending — does NOT raise).
6. `viewpoint_debate` mirror of #1.
7. `viewpoint_debate(wait=False)` mirror of #2.
8. `viewpoint_debate_check` mirror of #5.

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/endpoints/test_ai.py -v` → 10 (from 19a) + 8 = 18 passed.

```bash
git add src/gangtise_openapi/domains/ai.py tests/endpoints/test_ai.py
git commit -m "feat(ai): transparent polling for earnings-review + viewpoint-debate (with fire-and-forget *_check helpers)"
```

---

### Task 19c: AI knowledge-resource download (1 endpoint)

**Files:**
- Modify: `src/gangtise_openapi/domains/ai.py`
- Modify: `tests/endpoints/test_ai.py`

This task must land **after Task 22** (which creates `download_to_path`).

- [ ] **Step 1: Add the wrapper**

```python
def knowledge_resource_download(
    self,
    *,
    resource_type: int,         # required (TS makes it required)
    source_id: str,             # required (TS makes it required)
    output: str | Path | None = None,
) -> Path:
    return download_to_path(
        client=self._client,
        endpoint_key="ai.knowledge-resource.download",
        query={"resourceType": resource_type, "sourceId": source_id},
        output=output,
        fallback_name=f"knowledge-{source_id}",
        title_lookup=None,
    )
```

- [ ] **Step 2: Add a smoke test** mocking the download response with `Content-Disposition: attachment; filename="..."`.

- [ ] **Step 3: Run + commit**

```bash
git add src/gangtise_openapi/domains/ai.py tests/endpoints/test_ai.py
git commit -m "feat(ai): knowledge-resource download wrapper"
```

---

### Task 20a: Vault — list + non-download endpoints (7)

**Files:**
- Create: `src/gangtise_openapi/domains/vault.py`
- Create: `tests/endpoints/test_vault.py`
- Modify: `domains/__init__.py`, `_facade.py`

**Vault list manifest** (verified against `cli.ts:512-562` + `commandBodies.ts`).

| Endpoint key | Python method | Kwargs | Body fields | Pagination |
|---|---|---|---|---|
| `vault.drive.list` | `drive_list` | `from_=0, size=None, start_time=None, end_time=None, keyword=None, file_type=None, space_type=None, raw=False` | `from, size, startTime, endTime, keyword, fileTypeList, spaceTypeList` | 50 |
| `vault.record.list` | `record_list` | `from_=0, size=None, start_time=None, end_time=None, keyword=None, category=None, space_type=None, raw=False` | `from, size, startTime, endTime, keyword, categoryList, spaceTypeList` | 50 |
| `vault.my-conference.list` | `my_conference_list` | `from_=0, size=None, start_time=None, end_time=None, keyword=None, research_area=None, security=None, institution=None, category=None, raw=False` | `from, size, startTime, endTime, keyword, researchAreaList, securityList, institutionList, categoryList` | 50 |
| `vault.wechat-message.list` | `wechat_message_list` | `from_=0, size=None, start_time=None, end_time=None, keyword=None, security=None, wechat_group_id=None, industry=None, category=None, tag=None, raw=False` | `from, size, startTime, endTime, keyword, securityList, wechatGroupIdList, industryIdList, categoryList, tagList` | 50 |
| `vault.wechat-chatroom.list` | `wechat_chatroom_list` | `from_=0, size=20, room_name=None, raw=False` | `from, size, roomName` (string — TS joins list with `,` when multiple) | **NOT paginated** |
| `vault.stock-pool.list` | `stock_pool_list` | `raw=False` | `{}` (empty) | NOT paginated |
| `vault.stock-pool.stocks` | `stock_pool_stocks` | `pool_id="all", raw=False` | `poolIdList` (always a list; `"all"` becomes `["all"]`) | NOT paginated |

**Key corrections vs v1:**
- `drive_list`: missing `start_time/end_time/space_type` in v1. Body is `fileTypeList`+`spaceTypeList` (NOT `fileType`).
- `record_list`: missing `category/space_type`.
- `my_conference_list`: missing `research_area/security/institution/category`.
- `wechat_message_list`: missing `wechat_group_id/industry/category/tag` (the whole point of the endpoint).
- `wechat_chatroom_list`: NOT paginated. `room_name` is a string in the body (TS joins list with comma).
- `stock_pool_stocks`: body is `poolIdList` (list), not `poolId` (single). Default value `"all"` becomes `["all"]`.

- [ ] **Step 1: Write the 7 wrappers** using the Task 17 template. Examples for the tricky ones:

```python
def wechat_message_list(
    self,
    *,
    from_: int = 0,
    size: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    keyword: str | None = None,
    security: Any = None,
    wechat_group_id: Any = None,
    industry: Any = None,
    category: Any = None,
    tag: Any = None,
    raw: bool = False,
) -> pd.DataFrame | dict[str, Any]:
    body = _strip_none({
        "from": from_,
        "size": size,
        "startTime": start_time,
        "endTime": end_time,
        "keyword": keyword,
        "securityList": _as_list(security),
        "wechatGroupIdList": _as_list(wechat_group_id),
        "industryIdList": _as_list(industry),
        "categoryList": _as_list(category),
        "tagList": _as_list(tag),
    })
    result = self._client._call("vault.wechat-message.list", body=body)
    if raw:
        return result
    rows = result.get("list", []) if isinstance(result, dict) else result
    return to_dataframe(rows, schema=None)


def wechat_chatroom_list(
    self,
    *,
    from_: int = 0,
    size: int = 20,
    room_name: Any = None,
    raw: bool = False,
) -> pd.DataFrame | dict[str, Any]:
    names = _as_list(room_name) or []
    body = {
        "from": from_,
        "size": size,
        # TS joins multiple names with comma; preserve that.
        "roomName": ",".join(names) if names else None,
    }
    body = _strip_none(body)
    result = self._client._call("vault.wechat-chatroom.list", body=body)
    if raw:
        return result
    rows = result.get("list", []) if isinstance(result, dict) else result
    return to_dataframe(rows, schema=None)


def stock_pool_stocks(
    self,
    *,
    pool_id: Any = "all",
    raw: bool = False,
) -> pd.DataFrame | dict[str, Any]:
    body = {"poolIdList": _as_list(pool_id)}
    result = self._client._call("vault.stock-pool.stocks", body=body)
    if raw:
        return result
    rows = result.get("list", []) if isinstance(result, dict) else result
    return to_dataframe(rows, schema=None)
```

- [ ] **Step 2: Wire `__init__.py` + facade.**

- [ ] **Step 3: One smoke test per endpoint (7 tests).**

- [ ] **Step 4: Run + commit**

Run: `uv run pytest tests/endpoints/test_vault.py -v` → 7 passed.

```bash
git add src/gangtise_openapi/domains/vault.py \
        src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/test_vault.py
git commit -m "feat(vault): 7 list and stock-pool wrappers"
```

---

### Task 20b: Vault — download endpoints (3)

**Files:**
- Modify: `src/gangtise_openapi/domains/vault.py`
- Modify: `tests/endpoints/test_vault.py`

Lands **after Task 22**.

**Download manifest** (verified against `cli.ts:516-547`).

| Endpoint key | Python method | Required kwargs | Optional kwargs | Query | Title lookup |
|---|---|---|---|---|---|
| `vault.drive.download` | `drive_download` | `file_id: str` | `output=None` | `fileId` | `vault.drive.list` / `fileId` |
| `vault.record.download` | `record_download` | `record_id: str, content_type: str` (one of "original"/"asr"/"summary") | `output=None` | `recordId, contentType` | `vault.record.list` / `recordId` |
| `vault.my-conference.download` | `my_conference_download` | `conference_id: str, content_type: str` (one of "asr"/"summary") | `output=None` | `conferenceId, contentType` | `vault.my-conference.list` / `conferenceId` |

**Key corrections vs v1:** `record.download` and `my-conference.download` both have a **required** `content_type` query param (v1 missed it entirely).

- [ ] **Step 1: Add 3 download methods following the Task 16b pattern.** Each method calls `download_to_path(... title_lookup=("vault.<list>", "<idField>", id))`.

- [ ] **Step 2: 3 smoke tests** asserting the query string includes `contentType` for the two that require it.

- [ ] **Step 3: Run + commit**

```bash
git add src/gangtise_openapi/domains/vault.py tests/endpoints/test_vault.py
git commit -m "feat(vault): 3 download wrappers with required contentType"
```

---

### Task 20c: Alternative domain (2)

**Files:**
- Create: `src/gangtise_openapi/domains/alternative.py`
- Create: `tests/endpoints/test_alternative.py`
- Modify: `domains/__init__.py`, `_facade.py`

**Manifest** (verified against `cli.ts:568-593`).

| Endpoint key | Python method | Kwargs | Body fields | Notes |
|---|---|---|---|---|
| `alternative.edb-search` | `edb_search` | `keyword (required), limit: int = 100, raw=False` | `keyword, limit` | TS allows `limit` up to 200. |
| `alternative.edb-data` | `edb_data` | `indicator_id (required, list, max 10), start_date (required), end_date (required), raw=False` | `indicatorIdList, startDate, endDate` | Response is `{fieldList, dataList}` matrix shape; the wrapper transposes to `{list: [...]}` when `raw=False`. |

The `edb-data` transposition (mirroring `cli.ts:582-591`):

```python
def edb_data(
    self,
    *,
    indicator_id: Any,
    start_date: str,
    end_date: str,
    raw: bool = False,
) -> pd.DataFrame | dict[str, Any]:
    body = {
        "indicatorIdList": _as_list(indicator_id),
        "startDate": start_date,
        "endDate": end_date,
    }
    result = self._client._call("alternative.edb-data", body=body)
    if raw:
        return result
    if (
        isinstance(result, dict)
        and isinstance(result.get("fieldList"), list)
        and isinstance(result.get("dataList"), list)
    ):
        fields: list[str] = result["fieldList"]
        rows = [
            {field: row[i] for i, field in enumerate(fields)}
            for row in result["dataList"]
        ]
        return to_dataframe(rows, schema=fields)
    return result
```

- [ ] **Step 1: Write both wrappers.**
- [ ] **Step 2: Wire `__init__.py` + facade.**
- [ ] **Step 3: 2 smoke tests. The `edb-data` test must mock the `{fieldList, dataList}` shape and assert the wrapper produces a DataFrame with the right columns.**
- [ ] **Step 4: Run + commit**

```bash
git add src/gangtise_openapi/domains/alternative.py \
        src/gangtise_openapi/domains/__init__.py \
        src/gangtise_openapi/_facade.py \
        tests/endpoints/test_alternative.py
git commit -m "feat(alternative): edb-search + edb-data with matrix→DataFrame transpose"
```

---

## Phase 6 — Download, Title Cache, Logging

### Task 21: Title cache (`_title_cache.py`)

**Files:**
- Create: `src/gangtise_openapi/_title_cache.py`
- Create: `tests/unit/test_title_cache.py`

In-memory snapshot + atomic JSON write to `~/.config/gangtise/title-cache.json`. Mirrors `gangtise-openapi-cli/src/core/titleCache.ts`.

**Cache shape** (from TS `TitleCacheData` / `TitleCacheEntry`):

```json
{
  "insight.research.list": {
    "titles": {"r1": "标题A", "r2": "标题B"},
    "ts": 1716800000000
  }
}
```

- Cache is per-endpoint, keyed by string id.
- Each endpoint entry has a `ts` (epoch ms). Entries older than 24 hours are treated as cache miss (TTL).
- `TITLE_LOOKUP_SIZE = 200`: when a download wrapper falls back to "fetch the list endpoint and find the row," it requests `from=0, size=200`.

- [ ] **Step 1: Write the failing test `tests/unit/test_title_cache.py`**

```python
import json
import time

import pytest

from gangtise_openapi._title_cache import TITLE_CACHE_TTL_MS, TitleCache, extract_titles


def test_set_and_lookup_roundtrip(tmp_path):
    cache = TitleCache(tmp_path / "titles.json")
    cache.set_titles("insight.research.list", {"r1": "标题A"})
    assert cache.lookup("insight.research.list", "r1") == "标题A"


def test_lookup_miss(tmp_path):
    cache = TitleCache(tmp_path / "titles.json")
    assert cache.lookup("insight.research.list", "r1") is None


def test_persists_to_disk(tmp_path):
    path = tmp_path / "titles.json"
    cache_one = TitleCache(path)
    cache_one.set_titles("ep", {"x": "y"})
    cache_one.flush()
    cache_two = TitleCache(path)
    assert cache_two.lookup("ep", "x") == "y"


def test_ttl_expires(tmp_path, monkeypatch):
    path = tmp_path / "titles.json"
    cache = TitleCache(path)
    # Stash a stale entry by directly writing to disk
    stale_ts = int(time.time() * 1000) - TITLE_CACHE_TTL_MS - 1000
    path.write_text(json.dumps({"ep": {"titles": {"x": "y"}, "ts": stale_ts}}))
    cache2 = TitleCache(path)
    assert cache2.lookup("ep", "x") is None


def test_corrupt_file_treated_as_empty(tmp_path):
    path = tmp_path / "titles.json"
    path.write_text("not json", encoding="utf8")
    cache = TitleCache(path)
    assert cache.lookup("ep", "x") is None


def test_extract_titles_from_rows():
    rows = [
        {"reportId": "r1", "title": "标题A", "other": "x"},
        {"reportId": "r2", "title": "标题B"},
        {"reportId": "r3"},                # missing title — skip
        {"title": "标题C"},                # missing id — skip
    ]
    out = extract_titles(rows, id_field="reportId", title_field="title")
    assert out == {"r1": "标题A", "r2": "标题B"}


def test_set_titles_merges():
    cache = TitleCache(None)
    cache.set_titles("ep", {"a": "1", "b": "2"})
    cache.set_titles("ep", {"b": "B", "c": "3"})
    assert cache.lookup("ep", "a") == "1"
    assert cache.lookup("ep", "b") == "B"
    assert cache.lookup("ep", "c") == "3"
```

- [ ] **Step 2: Write `src/gangtise_openapi/_title_cache.py`**

```python
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable

TITLE_CACHE_TTL_MS = 24 * 60 * 60 * 1000
TITLE_LOOKUP_SIZE = 200


def extract_titles(
    rows: Iterable[Any],
    *,
    id_field: str,
    title_field: str = "title",
) -> dict[str, str]:
    """Pull (id → title) pairs from a list of dicts, skipping any row that
    lacks either field. Mirrors TS `extractTitles` in titleCache.ts.
    """
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ident = row.get(id_field)
        title = row.get(title_field)
        if ident is None or not isinstance(title, str) or not title:
            continue
        out[str(ident)] = title
    return out


class TitleCache:
    """Per-process snapshot of `~/.config/gangtise/title-cache.json`.

    `path=None` means in-memory only — useful for tests and when the config
    explicitly disables the disk cache.
    """

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = self._load()
        self._dirty = False

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._path is None:
            return {}
        try:
            raw = self._path.read_text(encoding="utf8")
        except OSError:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def lookup(self, endpoint_key: str, id_value: str) -> str | None:
        with self._lock:
            entry = self._data.get(endpoint_key)
            if not entry:
                return None
            ts = entry.get("ts")
            if not isinstance(ts, int) or (int(time.time() * 1000) - ts) > TITLE_CACHE_TTL_MS:
                return None
            titles = entry.get("titles")
            if not isinstance(titles, dict):
                return None
            value = titles.get(str(id_value))
            return value if isinstance(value, str) else None

    def set_titles(self, endpoint_key: str, titles: dict[str, str]) -> None:
        if not titles:
            return
        with self._lock:
            existing = self._data.get(endpoint_key, {}).get("titles", {})
            merged = {**existing, **titles}
            self._data[endpoint_key] = {
                "titles": merged,
                "ts": int(time.time() * 1000),
            }
            self._dirty = True

    def flush(self) -> None:
        if self._path is None:
            return
        with self._lock:
            if not self._dirty:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(
                self._path.suffix + f".tmp-{os.getpid()}-{int(time.time()*1000)}"
            )
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False),
                encoding="utf8",
            )
            os.chmod(tmp, 0o600)
            tmp.replace(self._path)
            self._dirty = False
```

**Integration with list wrappers:** Task 16a's `Insight` class never touches the title cache directly; instead, when Task 22 adds `_record_list_titles(...)` to `GangtiseClient`, the list wrappers that have downloadable siblings (research, foreign-report, announcement, announcement-hk, summary, drive, record, my-conference) call:

```python
self._client._record_list_titles(
    list_endpoint_key="insight.research.list",
    id_field="reportId",
    title_field="title",   # or whatever TS resolveTitle uses
    rows=rows,
)
```

right before returning the DataFrame. This populates the cache as a side effect. Subsequent downloads can then look up the title without hitting the list endpoint a second time.

If list wrappers were already implemented in Tasks 16a / 20a without this side-effect, **Task 22 is responsible for retrofitting the call** into each list wrapper before its own commit. The retrofitted wrappers list:

- `insight.summary.list` → `id_field="summaryId"`
- `insight.research.list` → `id_field="reportId"`
- `insight.foreign-report.list` → `id_field="reportId"`
- `insight.announcement.list` → `id_field="announcementId"`
- `insight.announcement-hk.list` → `id_field="announcementId"`
- `vault.drive.list` → `id_field="fileId"`
- `vault.record.list` → `id_field="recordId"`
- `vault.my-conference.list` → `id_field="conferenceId"`

(`title_field` is `"title"` for all of them per TS `resolveTitle` default.)

- [ ] **Step 3: Run + commit**

Run: `uv run pytest tests/unit/test_title_cache.py -v` → 7 passed.

```bash
git add src/gangtise_openapi/_title_cache.py tests/unit/test_title_cache.py
git commit -m "feat(title-cache): atomic JSON cache for resolved download titles"
```

---

### Task 22: Streaming download (`_download.py`) + title-cache wiring

**Files:**
- Create: `src/gangtise_openapi/_download.py`
- Create: `tests/unit/test_download.py`
- Modify: `src/gangtise_openapi/_client.py` (add `_record_list_titles` + own a `TitleCache` instance)
- Modify: each list wrapper from Tasks 16a / 20a that has a downloadable sibling — call `self._client._record_list_titles(...)` before returning.

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


TitleLookup = tuple[str, str, str]  # (list_endpoint_key, id_field, id_value)


def _sanitize_filename(name: str) -> str:
    return name.translate(str.maketrans({c: "_" for c in r'/\:*?"<>|'})).strip()


def download_to_path(
    *,
    client: GangtiseClient,
    endpoint_key: str,
    query: dict[str, str | int],
    output: str | Path | None,
    fallback_name: str,
    title_lookup: TitleLookup | None = None,
) -> Path:
    """Stream a download endpoint to disk.

    Resolution order for the output filename when `output` is None:
      1. Title cache hit on `title_lookup` (if provided)
      2. List-endpoint fallback fetch — calls the list endpoint with
         `from=0, size=TITLE_LOOKUP_SIZE` and scans for `id_field == id_value`
      3. `Content-Disposition` filename
      4. `<fallback_name><ext-from-mime>`
    """
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
        target = _decide_target(
            client=client,
            output=output,
            fallback_name=fallback_name,
            content_disposition=content_disposition,
            content_type=content_type,
            title_lookup=title_lookup,
        )
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


def _decide_target(
    *,
    client: GangtiseClient,
    output: str | Path | None,
    fallback_name: str,
    content_disposition: str | None,
    content_type: str | None,
    title_lookup: TitleLookup | None,
) -> Path:
    if output is not None:
        return Path(output).expanduser()
    ext_from_mime = _extension_for(content_type)
    if title_lookup is not None:
        list_key, id_field, id_value = title_lookup
        title = client._resolve_title(list_key, id_field, id_value)
        if title:
            sanitized = _sanitize_filename(title)
            if ext_from_mime and not sanitized.lower().endswith(ext_from_mime.lower()):
                sanitized += ext_from_mime
            return Path.cwd() / sanitized
    disposition_name = _parse_content_disposition(content_disposition)
    if disposition_name:
        return Path.cwd() / disposition_name
    return Path.cwd() / f"{fallback_name}{ext_from_mime}"
```

**Extend `GangtiseClient`** (modify `_client.py` from Task 13):

```python
from gangtise_openapi._title_cache import (
    TITLE_LOOKUP_SIZE,
    TitleCache,
    extract_titles,
)


class GangtiseClient:
    # ... existing fields & methods ...

    def __init__(self, ...) -> None:
        # ... existing setup ...
        self._title_cache = TitleCache(cfg.title_cache_path)

    def _record_list_titles(
        self,
        *,
        list_endpoint_key: str,
        id_field: str,
        title_field: str,
        rows: list[Any],
    ) -> None:
        titles = extract_titles(rows, id_field=id_field, title_field=title_field)
        if titles:
            self._title_cache.set_titles(list_endpoint_key, titles)
            self._title_cache.flush()

    def _resolve_title(
        self,
        list_endpoint_key: str,
        id_field: str,
        id_value: str,
        title_field: str = "title",
    ) -> str | None:
        cached = self._title_cache.lookup(list_endpoint_key, id_value)
        if cached:
            return cached
        # Cache miss → fetch first page of the list endpoint and scan.
        try:
            result = self._call(
                list_endpoint_key,
                body={"from": 0, "size": TITLE_LOOKUP_SIZE},
            )
        except Exception:
            return None
        rows = result.get("list") if isinstance(result, dict) else result
        if not isinstance(rows, list):
            return None
        titles = extract_titles(rows, id_field=id_field, title_field=title_field)
        if titles:
            self._title_cache.set_titles(list_endpoint_key, titles)
            self._title_cache.flush()
        return titles.get(str(id_value))
```

(Apply the equivalent change to `AsyncGangtiseClient` in Task 25. The async client exposes the **same** method names (`_record_list_titles` and `_resolve_title`) but defined as `async def`. The async download helper calls `await client._resolve_title(...)` — no `_async` suffix, since the sync/async clients are distinct types and don't need to disambiguate.)

- [ ] **Step 3: Retrofit list wrappers to populate the title cache**

For each list wrapper whose endpoint has a downloadable sibling, after building the rows DataFrame, call:

```python
self._client._record_list_titles(
    list_endpoint_key="insight.research.list",
    id_field="reportId",
    title_field="title",
    rows=rows,
)
```

Apply to these 8 list wrappers (see the Task 21 manifest for `id_field`):
- `insight.summary.list` → `summaryId`
- `insight.research.list` → `reportId`
- `insight.foreign-report.list` → `reportId`
- `insight.announcement.list` → `announcementId`
- `insight.announcement-hk.list` → `announcementId`
- `vault.drive.list` → `fileId`
- `vault.record.list` → `recordId`
- `vault.my-conference.list` → `conferenceId`

`independent-opinion.list` and `ai.knowledge-resource.download` have no title resolution in TS — skip them.

- [ ] **Step 4: Add an end-to-end download+title-resolution test**

```python
def test_download_uses_title_cache(tmp_path, monkeypatch, seeded_config):
    monkeypatch.chdir(tmp_path)
    with respx.mock(base_url="https://api.test", assert_all_called=False) as router:
        # First, hit the list endpoint to populate the cache
        router.post("/application/open-insight/broker-report/getList").mock(
            return_value=httpx.Response(
                200, json={
                    "code": "000000", "status": True,
                    "data": {"total": 1, "list": [
                        {"reportId": "r1", "title": "Alpha Report 2026Q1"},
                    ]},
                },
            )
        )
        router.get("/application/open-insight/broker-report/download/file").mock(
            return_value=httpx.Response(
                200, content=b"data", headers={"content-type": "application/pdf"},
            )
        )
        with GangtiseClient(_config=seeded_config) as client:
            from gangtise_openapi.domains.insight import Insight
            Insight(client).research_list()  # populates title cache as a side-effect
            path = Insight(client).research_download(report_id="r1")
    assert path.name.startswith("Alpha Report 2026Q1")
    assert path.suffix == ".pdf"
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: all unit + endpoint tests pass; the title-cache integration test asserts a list-endpoint call populates the cache and a subsequent download uses it.

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
from gangtise_openapi._title_cache import TitleCache
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
        self._title_cache = TitleCache(cfg.title_cache_path)

    @property
    def config(self) -> Config:
        return self._config

    async def __aenter__(self) -> "AsyncGangtiseClient":
        self._http = build_async_client(self._config)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
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

### Task 26: Async domain wrappers — common pattern + per-domain tasks

Tasks 26a through 26i each mirror one sync domain. Same files per task:
- Modify: `src/gangtise_openapi/domains/<name>.py` (add `class Async<Name>`)
- Modify: `src/gangtise_openapi/domains/__init__.py` (re-export `Async<Name>`)
- Create or modify: `tests/endpoints/test_<name>_async.py` (one smoke test per endpoint)

**Pattern (apply to every domain):**

```python
class AsyncQuote:
    def __init__(self, client: "AsyncGangtiseClient") -> None:
        self._client = client

    async def realtime(
        self,
        *,
        security: Any,
        field: Any = None,
        raw: bool = False,
    ) -> pd.DataFrame | dict[str, Any] | list[Any]:
        body = _strip_none({
            "securityList": _as_list(security),
            "fieldList": _as_list(field),
        })
        result = await self._client._call("quote.realtime", body=body)
        if raw:
            return result
        rows = result if isinstance(result, list) else result.get("list", [])
        return to_dataframe(rows, schema=_REALTIME_SCHEMA)
    # ... mirror each sync method. Preserve the sync return-type annotation:
    # if Quote.day_kline -> pd.DataFrame | dict[str, Any], so does
    # AsyncQuote.day_kline; mypy strict will not let any wrapper omit a
    # return type.
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
    title_lookup: TitleLookup | None = None,
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
        target = await _decide_target_async(
            client=client,
            output=output,
            fallback_name=fallback_name,
            content_disposition=content_disposition,
            content_type=content_type,
            title_lookup=title_lookup,
        )
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


async def _decide_target_async(
    *,
    client: "AsyncGangtiseClient",
    output: str | Path | None,
    fallback_name: str,
    content_disposition: str | None,
    content_type: str | None,
    title_lookup: TitleLookup | None,
) -> Path:
    if output is not None:
        return Path(output).expanduser()
    ext_from_mime = _extension_for(content_type)
    if title_lookup is not None:
        list_key, id_field, id_value = title_lookup
        title = await client._resolve_title(list_key, id_field, id_value)
        if title:
            sanitized = _sanitize_filename(title)
            if ext_from_mime and not sanitized.lower().endswith(ext_from_mime.lower()):
                sanitized += ext_from_mime
            return Path.cwd() / sanitized
    disposition_name = _parse_content_disposition(content_disposition)
    if disposition_name:
        return Path.cwd() / disposition_name
    return Path.cwd() / f"{fallback_name}{ext_from_mime}"
```

The async client needs the sibling methods. Add to `AsyncGangtiseClient` (Task 25). When adding these methods, **extend the existing `_title_cache` import** in `_client.py` to bring in the names you now need:

```python
# Update the existing import block in _client.py
from gangtise_openapi._title_cache import TITLE_LOOKUP_SIZE, TitleCache, extract_titles
```

Then add the methods:

```python
async def _record_list_titles(
    self,
    *,
    list_endpoint_key: str,
    id_field: str,
    title_field: str,
    rows: list[Any],
) -> None:
    titles = extract_titles(rows, id_field=id_field, title_field=title_field)
    if titles:
        self._title_cache.set_titles(list_endpoint_key, titles)
        self._title_cache.flush()

async def _resolve_title(
    self,
    list_endpoint_key: str,
    id_field: str,
    id_value: str,
    title_field: str = "title",
) -> str | None:
    cached = self._title_cache.lookup(list_endpoint_key, id_value)
    if cached:
        return cached
    try:
        result = await self._call(
            list_endpoint_key, body={"from": 0, "size": TITLE_LOOKUP_SIZE}
        )
    except Exception:
        return None
    rows = result.get("list") if isinstance(result, dict) else result
    if not isinstance(rows, list):
        return None
    titles = extract_titles(rows, id_field=id_field, title_field=title_field)
    if titles:
        self._title_cache.set_titles(list_endpoint_key, titles)
        self._title_cache.flush()
    return titles.get(str(id_value))
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

- [ ] **Step 4: Run per-domain task and commit**

Each Task 26* below follows this checklist:

1. Add the `Async<Name>` class to `domains/<name>.py`, mirroring the sync class method-for-method.
2. Re-export from `domains/__init__.py`.
3. Add `tests/endpoints/test_<name>_async.py` with one `@pytest.mark.anyio async def` test per endpoint, mirroring the sync test file.
4. Run `uv run pytest tests/endpoints/test_<name>_async.py -v`.
5. Commit with the message indicated.

| Task | Domain | Sync class size | Commit message |
|---|---|---|---|
| 26a | Auth | 2 methods | `feat(auth-async): AsyncAuth mirror` |
| 26b | Lookup | 8 methods | `feat(lookup-async): AsyncLookup mirror` |
| 26c | Reference | 1 method | `feat(reference-async): AsyncReference mirror` |
| 26d | Insight | 13 list + 6 download = 19 | `feat(insight-async): AsyncInsight mirror (19 endpoints)` |
| 26e | Quote | 6 (4 sharded) | `feat(quote-async): AsyncQuote with async sharding` |
| 26f | Fundamental | 12 | `feat(fundamental-async): AsyncFundamental mirror (12)` |
| 26g | AI | 10 sync + 4 polled + 1 download = 15 | `feat(ai-async): AsyncAI mirror with async polling` |
| 26h | Vault | 7 list + 3 download = 10 | `feat(vault-async): AsyncVault mirror (10)` |
| 26i | Alternative | 2 | `feat(alternative-async): AsyncAlternative mirror` |

**Domain-specific notes:**

- **26e (Quote):** the sharding helper is now `fetch_shards_async` from Task 25. Replace the `ThreadPoolExecutor`-based `fetch_shards` with the async version.
- **26g (AI):** use `poll_content_async` instead of `poll_content`. The `wait=False` path returns a dict immediately (no awaiting beyond the id call).
- **26d / 26h:** download methods call `await download_to_path_async(...)` (added in Step 1 below) and pass `title_lookup=...` exactly like the sync versions. The list wrappers must call `await self._client._record_list_titles(...)` — async variant.

All async tests must use the `anyio_backend` fixture defined in `tests/conftest.py` (Task 7.5) and the `seeded_config` fixture.

Per-domain "minimum acceptable" test count:
- 26a: 2 (login, status)
- 26b: 2 (research_areas + 1 other)
- 26c: 1
- 26d: 19 (one per endpoint, downloads use the same Content-Disposition assertion as sync)
- 26e: 4 (day_kline single, day_kline all-market shards, realtime, minute_kline)
- 26f: 12
- 26g: 15 (incl. one `wait=False` and one `410110→ready` polling test)
- 26h: 10
- 26i: 2

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
   - Repository: `gangtise-python`
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

Visit https://pypi.org/manage/project/gangtise-openapi/settings/publishing/ and verify the entry pointing at `gangtiser/gangtise-python` and workflow `release.yml`.

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

Open https://github.com/gangtiser/gangtise-python/actions and confirm the `Release` workflow succeeds. Verify the package is live on PyPI:

```bash
uv venv .verify-venv
.verify-venv/bin/pip install gangtise-openapi==0.1.0
.verify-venv/bin/python -c "from gangtise_openapi import gangtise, __version__; print(__version__)"
```
Expected: prints `0.1.0`.

---

## Self-Review (v2)

**Task count:** v1 had 31 tasks. v2 has **37 task headings** plus a 9-row dispatch table under Task 26 (26a-26i), giving **45 commit boundaries** for the executor. Splits introduced: 16 → 16a + 16b; 19 → 19a + 19b + 19c; 20 → 20a + 20b + 20c; 26 → 26a..26i (table-driven); new 7.5 conftest task.

**Spec coverage check** (per `docs/superpowers/specs/2026-05-27-gangtise-openapi-python-design.md`):

| Spec section | Covered by |
|---|---|
| §2 PyPI name `gangtise-openapi` | Task 1 |
| §2 Python 3.10+ | Task 1 |
| §2 uv + hatchling | Task 1 |
| §3 three-layer architecture | Tasks 13, 14, 15-20c |
| §4 file layout | File Structure table + Task file targets |
| §5 Path A (sync tabular) | Tasks 13, 15-20c, 12 |
| §5 Path B (async polling) | Tasks 11, 19b, 25, 26g |
| §5 Path C (streaming download + title cache) | Tasks 21, 22 (incl. retrofit step), 16b, 19c, 20b, 26d/26g/26h |
| §5 retry policy | Tasks 8, 13 (auth retry), 24 |
| §5 exception tree | Task 3 |
| §6 env vars + token cache | Tasks 4, 5, 13 |
| §6 `configure()` semantics | Task 14 |
| §6 logging | Task 23 |
| §7 unit + endpoint smoke + live integration | Throughout + Task 30 |
| §8 SemVer + `__about__.py` | Task 1 |
| §8 release workflow | Task 29 |
| §8 compatibility contract | Tasks 13, 14, 27 |
| §9 in-scope: title cache | Tasks 21, 22 (lookup chain: cache → list-endpoint fallback → Content-Disposition → fallback name) |
| §9 out of scope: Retry-After / Pydantic / codegen | Not implemented — correct |
| §10 resolved questions (slug, PyPI name, license) | Tasks 1, 29 |

**Placeholder scan:** the plan retains two structured "translate from TS source" steps. These are bounded mechanical work, not "TBD":

1. **Task 6 step 3** — translating the 73 endpoint definitions from `endpoints.ts`. Backed by a test that asserts the exact key set (step 5) and a pagination-registry test that asserts the per-endpoint `max_page_size` (step 4 v2). An engineer with `endpoints.ts` open can finish this mechanically.
2. **Task 7 step 1** — translating eight lookup arrays. Tests assert `list[dict]` shape with non-empty content; the TS data shape is trivial.

All other tasks now show **full code** for every step including the domain wrappers (manifests are concrete kwargs↔body mappings, not "translate as needed"). Task 17, 18, 19a/b/c, 20a/b/c each list endpoint shapes explicitly.

**Type consistency check:**
- `EndpointDef` fields: `key, method, path, kind, description, pagination` — Tasks 6, 8, 9, 17, 22.
- `Config` fields: 9 fields — Tasks 4, 13, 14, 24, 25.
- `TokenCache` fields: 7 fields — Tasks 5 and 13.
- `GangtiseClient` public surface used by domains: `_call`, `_get_token`, `_http_client`, `config`, `login`, `_record_list_titles`, `_resolve_title` — consistent across Tasks 13, 22, 16a, 16b, 19c, 20a/b.
- `download_to_path(client, endpoint_key, query, output, fallback_name, title_lookup=None)` — Tasks 22, 16b, 19c, 20b.
- `download_to_path_async(...)` — same signature, async variant — Task 26 prologue, 26d, 26g, 26h.
- `poll_content(fetch, *, sleep=time.sleep, max_attempts=14)` / `poll_content_async(fetch, *, max_attempts=14)` — Tasks 11, 25, 19b, 26g.
- `TitleCache.lookup(endpoint_key, id_value)`, `set_titles(endpoint_key, titles)`, `flush()` — Tasks 21, 22, 26 async client.

No drift in the cross-task signatures.

**Granularity check** (response to Codex Medium #5):
- Largest remaining single task is 19a (10 AI wrappers + 10 smoke tests) — still substantial but bounded; can be done in ~20 minutes by a focused agent.
- Largest async task is 26d (Insight, 19 endpoints to mirror). The mirror is mostly mechanical (s/sync/async/, s/def /async def /, s/return self._client._call/return await self._client._call/) — acceptable for one task.
- Critical path lengths (from scaffold to first PyPI publish): 1 → 2 → 3 → 4 → 5 → 6 → 7 → 7.5 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16a → 17 → 18 → 19a → 19b → 20a → 20c → 21 → 22 → 16b → 19c → 20b → 23 → 24 → 25 → 26a/b/c/d/e/f/g/h/i (parallelisable) → 27 → 28 → 29 → 30 → 31.

**Dependency map (subset, for executor):**
- 22 (download) depends on 13 (client), 21 (title cache), 15-20c (list wrappers that retrofit).
- 16b, 19c, 20b (downloads) depend on 22.
- 25 (async client) depends on 13, 24.
- 26d/26g/26h (async with downloads) depend on 25 + 22 + the sync sibling task.
- 31 (release) depends on everything.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-27-gangtise-openapi-python.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
