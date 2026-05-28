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
