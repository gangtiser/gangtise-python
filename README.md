# gangtise-openapi

Python SDK for [Gangtise OpenAPI](https://open.gangtise.com). Feature-parity with the npm CLI [`gangtise-openapi-cli`](https://github.com/gangtiser/gangtise-openapi-cli) v0.14.2 across 73 upstream endpoints, plus local auth status helpers.

## Changelog

### Unreleased

- Added runnable sample coverage for all public SDK methods: 74 sync examples in `sample/sync/` and 74 async examples in `sample/async/`.
- Added complete API parameter documentation in `sample/API_PARAMETERS.md`.
- Standardized sample output: DataFrame responses print directly, text and structured responses are saved as Markdown under `sample_outputs/`, and download samples save files under `sample_downloads/`.
- Improved download handling so sample downloads keep the API-provided or original document name and extension where available.

### 0.1.0 - 2026-05-28

- Initial SDK release with sync and async APIs, DataFrame-by-default responses, retries, token self-healing, pagination helpers, async-content polling, and npm CLI-compatible token cache.

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
df = gangtise.quote.day_kline(
    security="000001.SH",
    start_date="2026-01-01",
    end_date="2026-01-31",
)

# Use raw=True to get the underlying dict/list
result = gangtise.insight.opinion_list(industry=1, size=20, raw=True)

# Async
import asyncio

async def main():
    df = await gangtise.async_.quote.day_kline(security="000001.SH")

asyncio.run(main())
```

## Samples

Every public SDK method has a standalone customer-testable script.

```bash
uv run python sample/sync/quote_day_kline.py
uv run python sample/async/quote_day_kline.py
```

DataFrame-returning samples print the DataFrame directly. Text or dict/list responses are written as standard Markdown files under `sample_outputs/`. Download samples write real files under `sample_downloads/` and preserve the server-provided or original filename when possible.

See `sample/README.md` for run notes and `sample/API_PARAMETERS.md` for complete method parameter documentation.

## Endpoints

The SDK exposes 73 upstream endpoints across 9 domains:

- `gangtise.auth.*` — login, status
- `gangtise.lookup.*` — local lookup tables (research areas, brokers, industries, ...)
- `gangtise.reference.*` — securities search (GTS codes)
- `gangtise.insight.*` — opinions, research reports, announcements, schedules
- `gangtise.quote.*` — K-line, real-time quotes
- `gangtise.fundamental.*` — financial statements, valuation, holders, forecasts
- `gangtise.ai.*` — AI-generated insights (one-pager, peer comparison, earnings reviews, ...)
- `gangtise.vault.*` — personal drive, meeting records, stock pools, WeChat
- `gangtise.alternative.*` — economic indicators (EDB)

The Python wrappers accept the same parameters as the CLI flags, using `snake_case` instead of `--kebab-case`. For example, CLI `--start-date` maps to Python `start_date`.

## License

MIT
