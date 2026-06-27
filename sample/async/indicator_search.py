"""indicator.search — 按关键词搜索证券级数据指标 (EDE) 指标码（返回 DataFrame）。

keyword 传指标词如 "收盘价" "成交量" "营业收入"（不是自然语言问题）;
返回的 indicatorCode 供 indicator.cross_section / time_series 使用。
异步路径为 gangtise.async_.indicator.search(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 按指标词搜索
    show_result(await gangtise.async_.indicator.search(keyword="收盘价"), __file__)

    # 示例 2 · 控制返回条数
    show_result(
        await gangtise.async_.indicator.search(
            keyword="营业收入",  # 指标词
            limit=20,  # 最大返回数, 默认 50, 上限 100
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        await gangtise.async_.indicator.search(
            keyword="成交量",
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
