from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    result = await gangtise.async_.quote.index_day_kline(
        security="000300.SH",
        start_date="2026-05-01",
        end_date="2026-05-28",
        limit=10,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
