from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    result = await gangtise.async_.ai.theme_tracking(
        theme_id="121000342",
        date="2026-05-28",
        type_="news",
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
