from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    result = await gangtise.async_.ai.management_discuss_earnings_call(
        report_date="2025-12-31",
        security_code="000001.SZ",
        dimension="businessOperation",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
