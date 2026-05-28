# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-05-28

### Added
- Initial release.
- 73 endpoints from gangtise-openapi-cli v0.14.2.
- Sync (`gangtise`) and async (`gangtise.async_`) APIs.
- DataFrame-by-default returns with `raw=True` escape hatch.
- Auto-pagination concurrency, retry + token self-heal, K-line full-market date sharding, transparent async-content polling.
- Token cache shared with the npm CLI at `~/.config/gangtise/token.json`.
- Initial scaffold (pyproject, tooling, CI).
