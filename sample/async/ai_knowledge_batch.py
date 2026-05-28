from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    result = await gangtise.async_.ai.knowledge_batch(
        query="贵州茅台",
        top=3,
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
