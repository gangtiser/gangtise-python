"""ai.stock_summary_list — 个股看点, 每只证券的精炼研究摘要（返回 DataFrame）。

security 必填, 传证券代码或市场关键词 aShares / hkStocks（上限 6000）; 留空会抛 ValidationError
（省略会被后端当作全市场, 每行约 3 积分 × 数千行）。
异步路径为 gangtise.async_.ai.stock_summary_list(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 单只证券（A 股 / 港股代码均可）
    show_result(await gangtise.async_.ai.stock_summary_list(security="600519.SH"), __file__)

    # 示例 2 · 多只证券（列表入参）
    show_result(
        await gangtise.async_.ai.stock_summary_list(
            security=["600519.SH", "00700.HK"],  # 证券代码, 支持单值或列表; 上限 6000
        ),
        __file__,
    )

    # 示例 3 · 市场关键词 + 原始返回（aShares=全 A 股 / hkStocks=全港股, 注意积分消耗）
    show_result(
        await gangtise.async_.ai.stock_summary_list(
            security="aShares",  # 市场关键词: aShares / hkStocks
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
