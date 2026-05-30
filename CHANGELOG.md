# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and follows [Semantic Versioning](https://semver.org/).

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
  discover IDs by name via `gangtise.lookup.theme_ids_list()` (e.g. 机器人 →
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
