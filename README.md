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
