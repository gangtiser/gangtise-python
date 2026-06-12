# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- **Token handling under concurrency**: N concurrent callers hitting a stale
  token now trigger exactly one login (TS `refreshPromise` parity); a rejected
  `GANGTISE_TOKEN` env token is skipped after its first failure instead of
  permanently tripling every call; the token-cache temp file is now unique per
  writer (multi-process safe); `__enter__`/`__aenter__` reuse a lazily created
  HTTP client instead of leaking the old pool.
- **Async error contract**: paginated/sharded fan-out failures now raise the
  original `ApiError` instead of anyio's `ExceptionGroup`, so `except ApiError`
  behaves identically in sync and async code.
- **Kline sharding** (TS `c4306fe` parity): a failed shard no longer discards
  all fetched data — surviving shards merge with `partial: true` +
  `failedShards` flags and a `UserWarning`; only an all-shards failure raises.
- **Download path** (TS parity): auth self-heal (8000014/8000015 → refresh →
  retry once), transient-error retry with backoff, presigned-`{url}` responses
  are now fetched instead of raising, 4xx JSON envelopes preserve the business
  code and Chinese hint, `.part` temp files are cleaned up on stream failure,
  and the async variant no longer blocks the event loop while writing to disk.
- **Facade**: `gangtise.configure(...)` now propagates to `gangtise.async_`
  (previously the async facade silently re-read env vars only).
- **TS parity details**: `fundamental.earning_forecast` injects the CLI's
  default one-year date window when dates are omitted; `insight` timestamp
  conversion matches `toTimestamp13` (seconds-level ints ×1000, naive datetimes
  in local tz); `ERROR_HINTS` caught up with TS v0.15.1 (410004, 430004,
  430007, 433007, 10011401).
- Cache persistence failures (token cache / title cache) no longer break an
  otherwise-successful request or download.
- Docs referenced a non-existent `lookup.theme_ids_list()` — corrected to
  `lookup.theme_ids()`.

### Changed
- **Performance**: columnar kline payloads build the DataFrame directly from
  the matrix (2–3× faster, ~half the peak memory at large row counts);
  all-market day-kline sharding skips pure-weekend windows (~29% fewer
  requests on a 1-year backfill).
- IDE experience: facade domain attributes are now statically typed (mypy /
  IDE autocomplete works on `gangtise.quote.*`), `dir()` lists domains, and
  every public wrapper method has a Chinese docstring with endpoint key and
  enum values.
- CI now tests the support boundary (Python 3.10 + 3.13).

### Tests
- +179 tests (222 → 401): async wire-body regression coverage for every
  vault/insight/ai wrapper (domain coverage 64% → 94%), async transport error
  paths, poll exhaustion, token-refresh concurrency, download error paths and
  filename-resolution tiers, facade registry integrity, and 4 new live smokes
  (7 total) covering quote/fundamental/insight/alternative read paths.

## [0.1.4] - 2026-05-30

### Added
- **`alternative.concept_info`** — latest profile of a concept (theme index):
  definition, investment logic, industry space, competitive landscape, and a
  `keyEvents` list. Queried by `concept_id`; returns the single latest
  cross-section object as a dict (no history).
  (`POST /application/open-alternative/concept/info`)
- **`alternative.concept_securities`** — constituent securities of a concept
  (theme index, F8), grouped. Each security carries `isKey` (key-stock flag)
  and `inclusionReason`. The default DataFrame flattens the groups
  one-row-per-security with a `groupName` column; `raw=True` returns the nested
  grouped payload. A concept with no constituents returns an empty DataFrame
  with the same columns. (`POST /application/open-alternative/concept/securities`)
- `concept_id` shares the theme-id namespace used by `ai.theme_tracking` —
  discover IDs by name via `gangtise.lookup.theme_ids()` (e.g. 机器人 →
  `121000130`). Both sync and async wrappers were added.

### Changed
- `quote.index_day_kline` now surfaces the upstream-added `securityName` column
  (e.g. "上证指数"). No wrapper change was required — the dynamic-schema path
  shipped in 0.1.3 passes through every field the API returns.

### Performance
- **Title cache no longer grows without bound.** The cache (used to resolve
  download filenames) merged every list call's titles forever and re-stamped
  the entry's `ts` on each merge, so the 24h TTL never pruned hot endpoints — on
  disk it had reached ~58 MB / 600k+ titles, re-parsed on every client init
  (~900 ms) and fully rewritten on every non-`raw` list call (~360 ms). Titles
  are now capped per endpoint (`TITLE_CACHE_MAX_PER_ENDPOINT`, 10k most-recent),
  oversized entries are trimmed on load, and a list call that surfaces no new
  titles no longer marks the cache dirty (no rewrite). On a real 58 MB cache the
  next write shrinks to ~1.7 MB, with client-init parse time cut proportionally.

## [0.1.3] - 2026-05-29

### Fixed
- **`quote.realtime` and `quote.minute_kline` returned all-None DataFrames.**
  Both endpoints return a columnar matrix `{fieldList, list:[[...]]}` but the
  rows were tabulated against a hardcoded schema whose names did not match the
  API, so every cell came out null. They now transpose each row against the
  response `fieldList` (shared `_quote_rows_and_fields` helper).
- **`quote.day_kline` column names corrected.** The hardcoded schema invented
  `turnover` / `changePct` and dropped real fields; A-share day K-line has no
  `turnover` column — the real fields are `pctChange` and `adjustFactor`.
- **`reference.securities_search` returned mostly-None columns.** The schema
  used `code/name/market/...` but the API returns
  `gtsCode/gtsName/category/matchScore/matchType`.
- All three hardcoded quote schemas and the field-alias remap removed; quote and
  securities-search now return the API's field names verbatim (`schema=None`),
  matching the columnar fix shipped for the fundamental endpoints in 0.1.2.

## [0.1.2] - 2026-05-29

### Fixed
- **DataFrame conversion for columnar responses.** Many data endpoints (fundamental
  income-statement / balance-sheet / cash-flow, valuation-analysis, main-business)
  return a columnar matrix `{fieldList, list:[[...]]}`. A new `normalize_rows`
  (ported from the TS CLI) transposes it into named columns; previously these
  produced an empty DataFrame or one with integer column names.
- `fundamental.valuation_analysis` column schema corrected to the real fields
  (`tradeDate, value, percentileRank, average, median, upper1Std, lower1Std`).
- `GANGTISE_VERBOSE` now actually emits debug logs — a stderr handler is attached
  for both sync and async transport (previously the level was set but no handler
  existed, so records were dropped). `Config.verbose` is honored by the client.
- Async client no longer blocks the event loop on token / title-cache disk I/O
  (offloaded via `anyio.to_thread`).
- Title cache prunes entries past its TTL on load, bounding on-disk growth.
- Sample `fundamental_valuation_analysis` used an invalid indicator
  (`pe_ttm` → `peTtm`).

### Added
- `fundamental.earning_forecast` now returns a DataFrame (flattened analyst
  consensus, one row per update date × forecast year). Defaults to the latest
  update snapshot; pass `latest=False` for the full history or `raw=True` for the
  nested payload.
- Async transport now logs request timing, mirroring the sync path.

### Changed
- Domain helpers (`_as_list`, `_strip_none`, `_extract_rows`) consolidated into
  `domains/_common.py` (previously duplicated across every domain module).
- Pagination logs a warning when results are truncated at `MAX_PAGES`.
- Dropped an unused `config` parameter from the transport request functions.

## [0.1.1] - 2026-05-28

## [0.1.0] - 2026-05-28
