# Gangtise OpenAPI Python SDK — Design

- **Date:** 2026-05-27
- **Status:** Draft (pending review)
- **Author:** Claude + user (brainstorming session)
- **Source project:** `gangtise-openapi-cli` v0.14.2 (TypeScript / Node, 73 endpoints)
- **Target deliverable:** `gangtise-openapi` Python package on PyPI

## 1. Goal & Non-Goals

### Goal
Ship a Python SDK on PyPI that lets buy-side users hit Gangtise OpenAPI from
notebooks and scripts. The SDK must reach feature parity with the npm CLI
(`gangtise-openapi-cli`) v0.14.2 on its first stable release.

### Non-Goals
- No Python CLI — npm version stays the canonical CLI.
- No code generation from `endpoints.ts`. The 73 wrappers are hand-written.
- No multi-process token coordination. In-process locks only.
- No live HTTP integration tests in CI. Smoke tests use mocked transport.

## 2. Decisions (locked in brainstorming)

| Axis | Decision |
|---|---|
| Form factor | SDK only |
| Concurrency | Sync + async both shipped |
| PyPI name | `gangtise-openapi` |
| Import root | `from gangtise_openapi import gangtise` |
| Call style | Namespace facade — `gangtise.quote.day_kline(...)` |
| Default return | `pandas.DataFrame` for tabular endpoints; `raw=True` returns dict |
| Endpoint coverage | All 73 endpoints in v0.1.0 |
| Python | 3.10+ |
| Build tooling | uv + hatchling |
| Advanced behaviors | Auto-pagination concurrency, retry + token self-heal + disk
  token cache (shared with npm CLI), K-line full-market date sharding,
  transparent async polling for `earnings-review` / `viewpoint-debate` |

## 3. Architecture

Three layers, same as the TS source, but with a Python facade on top:

```
┌─────────────────────────────────────────────────────────┐
│  Facade  (gangtise.quote.day_kline, gangtise.async_...)│  ← user-facing
├─────────────────────────────────────────────────────────┤
│  Domain wrappers (auth/lookup/insight/.../alternative) │  ← 73 hand-written
├─────────────────────────────────────────────────────────┤
│  GangtiseClient._call(endpoint_key, body)              │
│   + transport / auth / retry / pagination / sharding   │  ← shared sync+async
└─────────────────────────────────────────────────────────┘
```

`gangtise` (lowercase) is a module-level `_Facade` singleton. It lazy-instantiates
a default `GangtiseClient` from env vars on first attribute access. Each domain
(`gangtise.quote`, etc.) returns a domain wrapper bound to that client. Async
mirror is exposed at `gangtise.async_` (or `from gangtise_openapi import async_gangtise`).

Sync and async share:
- `_endpoints.py` registry (single source of truth)
- `_pagination.py` orchestration (parameterised over an `_invoke` callable)
- `_quote_sharding.py` planning logic
- `_async_content.py` polling state machine
- Wrapper signatures and validation in `domains/*`

They diverge only in `_transport.request_json` / `request_stream`, where one
uses `httpx.Client` and the other `httpx.AsyncClient`.

## 4. Project Layout

```
gangtise-openapi/
├── pyproject.toml
├── README.md / LICENSE / CHANGELOG.md / .gitignore
├── .github/workflows/
│   ├── ci.yml                       lint + test on PR
│   └── release.yml                  tag v* → PyPI trusted publishing
├── docs/
│   ├── superpowers/specs/           this spec lives here
│   └── RELEASE.md                   release checklist
├── src/gangtise_openapi/
│   ├── __init__.py                  exports: gangtise, GangtiseClient,
│   │                                AsyncGangtiseClient, errors, __version__
│   ├── __about__.py                 __version__ = "0.1.0"
│   ├── _facade.py                   _Facade singleton + .async_ mirror
│   ├── _config.py                   env-driven Config dataclass
│   ├── _auth.py                     TokenCache (compat with npm path)
│   ├── _errors.py                   exception tree + ERROR_HINTS
│   ├── _endpoints.py                EndpointDef registry, 1:1 with TS
│   ├── _transport.py                httpx Client/AsyncClient, retry, headers
│   ├── _pagination.py               auto-pagination, sync + async strategies
│   ├── _client.py                   GangtiseClient + AsyncGangtiseClient
│   ├── _normalize.py                rows → pandas.DataFrame with locked schema
│   ├── _download.py                 streaming download + title resolution
│   ├── _quote_sharding.py           K-line full-market date sharding
│   ├── _async_content.py            earnings-review / viewpoint-debate polling
│   ├── _lookup/                     bundled lookup tables (Python literals)
│   │   ├── __init__.py              LOOKUP_LOADERS dict
│   │   ├── research_areas.py
│   │   ├── broker_orgs.py
│   │   ├── meeting_orgs.py
│   │   ├── industries.py
│   │   ├── regions.py
│   │   ├── announcement_categories.py
│   │   ├── industry_codes.py
│   │   └── theme_ids.py
│   └── domains/
│       ├── __init__.py
│       ├── auth.py                  Auth / AsyncAuth
│       ├── lookup.py                Lookup / AsyncLookup
│       ├── insight.py               Insight / AsyncInsight
│       ├── reference.py
│       ├── quote.py
│       ├── fundamental.py
│       ├── ai.py
│       ├── vault.py
│       └── alternative.py
└── tests/
    ├── conftest.py                  respx fixture, fake config
    ├── unit/                        pure logic
    ├── endpoints/                   one smoke test per wrapper
    └── integration/                 @pytest.mark.live, manual only
```

### Boundary rules

- Underscore-prefixed modules are private. Public symbols are only those
  re-exported from `gangtise_openapi/__init__.py`.
- `_endpoints.py` is the single source of truth for endpoint key, HTTP method,
  path, pagination config. `domains/*` reference the key, never the path.
- Domain files must stay ≤ ~400 lines. `insight` and `ai` will likely split into
  two files each (e.g. `insight_list.py` + `insight_download.py`).

## 5. Data Flow

### Path A — sync tabular query (most common)

```python
from gangtise_openapi import gangtise
df = gangtise.quote.day_kline(security="000001.SH", start_time="2026-01-01")
```

1. `gangtise.quote` → `_Facade._ensure_client()` lazy-builds `GangtiseClient`
   from `_config.load_config()`. `Quote(client)` is cached on the facade.
2. `Quote.day_kline(...)` validates args, builds `body`, calls
   `client._call("quote.day-kline", body)`.
3. `GangtiseClient._call(key, body)` looks up the endpoint in `_endpoints`,
   delegates to `_transport.request_json(client, endpoint, body, auth_provider)`:
   - `auth_provider.get_header()` consults the in-memory `TokenCache`; on miss
     or near-expiry, calls `_token_refresh()` (deduped via `threading.Lock`).
   - `httpx.Client.request(...)` with `timeout = config.timeout_ms / 1000`.
   - Retry policy: 5xx / network timeout / API code `999999` → exponential
     backoff (base 400ms, max 4s), max 2 retries.
   - Envelope unwrap: `code == "000000"` or `success == True` → return `data`;
     otherwise raise `ApiError(msg, code, status_code, details)`.
   - Auth codes (`8000014`, `8000015`) force a one-shot token refresh and
     retry once.
4. If the endpoint has `pagination` config, `_transport.request_json`
   delegates to `_pagination.collect(...)`:
   - Fetch page 1 serially to learn `total`.
   - Plan remaining pages, capped at `MAX_PAGES = 1000`.
   - Fan out concurrently:
     - sync: `concurrent.futures.ThreadPoolExecutor`, default 5 workers
     - async: `anyio.create_task_group` with `Semaphore(5)`
   - Concurrency overridable via `GANGTISE_PAGE_CONCURRENCY`.
   - Concatenate `list` entries; preserve `total` and any other top-level
     metadata from page 1.
5. Wrapper receives `data`. If the wrapper declares a tabular schema and
   `raw=False` (default), it calls `_normalize.to_dataframe(rows, schema=...)`:
   - Column order locked by `schema`.
   - dtype hints applied (datetime / float / int / str).
   - Empty input returns an empty DataFrame with the right columns.
6. Returns the DataFrame.

### Path B — transparent async polling

```python
content = gangtise.ai.earnings_review(security="600519.SH", date="2026-Q1")
```

Wrapper internally:
1. Calls `ai.earnings-review.get-id` to obtain `taskId`.
2. Calls `_async_content.poll(client, task_id=..., family="earnings-review")`.
   The poll function maps `family` to the TS-equivalent check endpoint
   (mirrors `checkAsyncContent` / `pollAsyncContent` in
   `gangtise-openapi-cli/src/core/asyncContent.ts`; exact endpoint keys to
   be confirmed by reading that module during implementation).
   Backoff: 5, 8, 13, 20, 30 seconds, then repeats 30s.
   `POLL_MAX_ATTEMPTS = 10` (matches TS source). Times out with
   `ApiError("polling timeout")`.
3. Calls `ai.earnings-review.get-content` once ready.
4. Returns dict (not tabular). `raw=True` returns the envelope `data` as-is;
   default returns the same dict but with top-level keys snake_cased.

### Path C — streaming download

```python
path = gangtise.insight.research_download(
    report_id="...",
    output="~/Downloads/report.pdf",
)
```

`_download.stream_to_path(client, endpoint, query, output)`:
- `httpx.Client.stream(...)` → `iter_bytes()` → write incrementally.
- If `output` not provided: stream to `tempfile.NamedTemporaryFile`, then
  rename to `./<resolved_title>.<ext>` using `Content-Disposition` or wrapper-
  provided fallback name.
- Returns `pathlib.Path` of the written file.

### Exception tree

```
GangtiseError(Exception)
├── ConfigError              missing keys, unreadable cache file
├── ApiError                 HTTP 4xx/5xx or envelope code != success
│                            .code, .status_code, .details, .hint
├── ValidationError          local arg validation failed
└── DownloadError            filesystem error during streaming
```

All exceptions populate `.hint` from `ERROR_HINTS` (Chinese) when an API code
is known. `__str__` returns `f"{message}{(' — ' + hint) if hint else ''}"`.

## 6. Configuration & Auth

### Environment variables (npm-CLI-compatible)

| Variable | Default | Notes |
|---|---|---|
| `GANGTISE_BASE_URL` | `https://open.gangtise.com` | |
| `GANGTISE_ACCESS_KEY` | — | required unless `GANGTISE_TOKEN` set |
| `GANGTISE_SECRET_KEY` | — | required unless `GANGTISE_TOKEN` set |
| `GANGTISE_TOKEN` | — | bypass login |
| `GANGTISE_TOKEN_CACHE_PATH` | `~/.config/gangtise/token.json` | shared with npm |
| `GANGTISE_TIMEOUT_MS` | 30000 | httpx timeout (ms) |
| `GANGTISE_PAGE_CONCURRENCY` | 5 | pagination fan-out width |
| `GANGTISE_VERBOSE` | `0` | maps to `logger.setLevel(DEBUG)` |

### Explicit overrides

```python
from gangtise_openapi import GangtiseClient
client = GangtiseClient(access_key="...", secret_key="...", base_url="...",
                        timeout=30.0)
```

The facade exposes `gangtise.configure(...)` to replace the default client.
A second call raises `ConfigError("default client already configured")`. Use
`gangtise.reset()` to allow re-configure.

### Token cache file format

Identical to TS `TokenCache`:
```json
{
  "accessToken": "...",
  "expiresIn": 3600,
  "time": 1716800000,
  "expiresAt": 1716803600,
  "uid": 12345,
  "userName": "...",
  "tenantId": 1
}
```

- File mode `0o600`. Parent dir created with `Path.mkdir(parents=True,
  exist_ok=True)`.
- Read / write wrapped in try/except. Corrupt file = cache miss.
- Validity buffer: refresh if `expiresAt - now < 300s`.

### Refresh deduplication

- Sync: `threading.Lock` around the refresh call; threads waiting on the lock
  re-check cache validity after acquiring.
- Async: `asyncio.Lock` with the same pattern.
- Cross-process: not coordinated. Last writer wins.

### Logging

- Logger: `logging.getLogger("gangtise_openapi")`.
- `GANGTISE_VERBOSE=1` ⇒ `logger.setLevel(DEBUG)`.
- One DEBUG line per request:
  `[gangtise] {ms}ms {METHOD} {path} (status={status}, bytes={n})`.
- No direct writes to stderr from library code.

## 7. Testing

### Pyramid

| Layer | Path | Runs | Count | Tooling |
|---|---|---|---|---|
| Unit (pure logic) | `tests/unit/` | CI default | ~30 | pytest |
| Endpoint smoke | `tests/endpoints/` | CI default | 73 × 1 (sync) + 73 × 1 (async) | pytest + respx |
| Integration (live) | `tests/integration/` | manual only | ~10 | pytest -m live, real creds |

### Unit coverage targets

- `_pagination.collect`: single page; exact-multiple total; remainder;
  `requested_size` truncation; `total` drift across pages; unexpected shape
- `_quote_sharding`: shard day count per market (A=1, HK=2, US=1); `--limit`
  default 10000 injection when `security=all` and no explicit limit; shard
  merge dedup
- `_async_content.poll`: backoff sequence (5,8,13,20,30); timeout; ready exit
- `_auth.TokenCache`: valid; expired; near-expiry buffer; corrupt JSON
- `_transport.retry`: 5xx; `999999`; `8000014` (one-shot full refresh + retry);
  retryable network codes
- `_normalize.to_dataframe`: empty list; column order locked; dtype inference;
  `raw=True` passes through untouched

### Endpoint smoke pattern

```python
def test_quote_day_kline(respx_mock, sync_client):
    respx_mock.post("/application/open-quote/kline/daily").mock(
        return_value=httpx.Response(200, json={
            "code": "000000", "status": True,
            "data": {"total": 2, "list": [
                {"date": "2026-01-02", "close": 12.3, ...},
                {"date": "2026-01-03", "close": 12.4, ...},
            ]},
        })
    )
    df = sync_client.quote.day_kline(security="000001.SH",
                                     start_time="2026-01-01")
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [...]   # schema lock
    assert len(df) == 2
```

pytest parametrise generates the 73 sync + 73 async cases from a manifest.

### Async tests

`pytest-anyio` + `respx`. Every sync wrapper has a sibling async test reusing
the same mocked endpoint, asserting identical DataFrame output.

### Tooling

- `pytest`, `pytest-anyio`, `respx`
- `ruff` (lint + format)
- `mypy --strict` on `src/`
- All configured in `pyproject.toml`. `uv run pytest`, `uv run ruff check`,
  `uv run mypy src` are the entry points.

## 8. Release & Version Management

### Git

- `git init -b main`. Default branch `main`.
- `.gitignore` excludes `.venv/`, `dist/`, `*.egg-info`, `__pycache__/`,
  `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.env*`.
- Commit convention: Conventional Commits, no commit-msg hook.
- First commit: `chore: initial scaffold` (pyproject + LICENSE + README skel).
- Remote: GitHub repo under the `gangtiser` org. Working name
  `gangtise-openapi-python`. The user confirms the final slug before the
  first push (open question in §10).

### Versioning

- SemVer. Start at `0.1.0`.
- Single source: `src/gangtise_openapi/__about__.py` (`__version__ = "0.1.0"`).
- `pyproject.toml` uses `[tool.hatch.version] path =
  "src/gangtise_openapi/__about__.py"`.
- `CHANGELOG.md` follows keep-a-changelog. Hand-curated, prepended per release.

### PyPI publishing

- Local: `uv build` → `uv publish` (with token for first releases).
- Automated: `.github/workflows/release.yml` triggers on tag `v*`:
  1. Run tests + ruff + mypy
  2. `uv build`
  3. `uv publish` via PyPI Trusted Publisher (OIDC, no stored token)
  4. Create matching GitHub Release; body is the CHANGELOG section
- Test PyPI used at least once before the first `0.1.0` cut.

### Release checklist (lives in `docs/RELEASE.md`)

1. Full test suite green; `pytest -m live` run locally at least once
2. `CHANGELOG.md` updated with new version section
3. `__about__.py` bumped
4. `git commit -am "release: vX.Y.Z"`
5. `git tag vX.Y.Z && git push --follow-tags`
6. CI builds, publishes, creates GitHub release
7. README install badge confirmed live

### Compatibility contract

- Public API: `gangtise_openapi.gangtise` facade, `GangtiseClient`,
  `AsyncGangtiseClient`, exception tree, `__version__`.
- Anything reachable only via underscore-prefixed modules is private. Refactor
  freely.
- Breaking change in public API ⇒ major bump.
- New endpoint wrapper ⇒ minor.
- Bug fix or internal refactor ⇒ patch.

## 9. Out of Scope (for v0.1.0)

- Python CLI binary. npm CLI remains canonical.
- Multi-process token coordination.
- Auto-generated endpoint wrappers (manual is acceptable at 73 endpoints).
- Pydantic models for response shapes. DataFrame + dict covers the buy-side use
  case.
- Caching of paginated results to disk.
- Rate limit handling beyond exponential retry on `999999`.

## 10. Risks & Open Questions

### Open questions (need user input before implementation)

- **GitHub repo slug** — default `gangtise-openapi-python`. Confirm with user.
- **PyPI account / publisher** — need a PyPI org account or personal account
  to claim `gangtise-openapi`. Confirm before tagging v0.1.0.
- **License** — assume MIT to match the npm CLI. Confirm.

### Risks

| Risk | Mitigation |
|---|---|
| TS `endpoints.ts` evolves; Python drifts | A drift-check script (CI) parses TS file and diffs endpoint keys + paths + pagination flags against `_endpoints.py`. Out of scope for v0.1.0 but tracked. |
| DataFrame column schemas drift | Endpoint smoke tests pin the schema list. Schema lives next to each wrapper. |
| Pandas as a required dep is heavy | Accepted; the target audience already has it. No optional-extra dance. |
| `respx` requires httpx — locks our HTTP client | Acceptable; httpx is the choice anyway. |

## 11. Out-of-Spec Items (deferred to plan)

- File-by-file ordering and dependencies (left to `writing-plans`).
- Exact retry parameter values per HTTP status (left to plan implementation,
  defaults stated above).
- README content beyond "what is this / install / quickstart / link to npm
  CLI for full docs" (left to plan).
- GitHub Actions matrix breadth (Python 3.10 + 3.12 minimum).
