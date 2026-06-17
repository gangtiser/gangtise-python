# Gangtise OpenAPI Samples

This directory contains runnable one-file examples for every public SDK method: 77 sync scripts in `sync/` and 77 async scripts in `async/`.

## Configuration

Configure credentials before running network-backed samples:

```bash
export GANGTISE_ACCESS_KEY=ak_xxx
export GANGTISE_SECRET_KEY=sk_xxx
```

## Run Examples

Run one sync sample:

```bash
uv run python sample/sync/quote_day_kline.py
```

Run one async sample:

```bash
uv run python sample/async/quote_day_kline.py
```

## Output Rules

Samples that return DataFrames print the DataFrame directly with no wrapper text. Text and dict/list-style samples write clean Markdown files under the repository-level `sample_outputs/`; the script prints the generated `.md` path. Download samples write files under `sample_downloads/` and preserve the original filename when the API provides one.

## Special Cases

Check-style AI samples need a `dataId` from the matching `wait=False` generation sample. Knowledge resource download needs `GANGTISE_SAMPLE_KNOWLEDGE_SOURCE_ID` and optionally `GANGTISE_SAMPLE_KNOWLEDGE_RESOURCE_TYPE`.

Full parameter documentation is in `sample/API_PARAMETERS.md`.
