# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and follows [Semantic Versioning](https://semver.org/).

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
