from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    result = await gangtise.async_.fundamental.main_business(
        security_code="000001.SZ",
        start_date="2025-01-01",
        end_date="2026-05-28",
        breakdown="product",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
