"""vault.stock_pool_list — 用户自选股票池 ID 与名称列表（返回 DataFrame）。

该接口无业务过滤参数, 仅有通用 raw 开关; 拿到的 poolId 可传给 vault.stock_pool_stocks。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 默认调用: 返回全部股票池, 转为 DataFrame
    show_result(await gangtise.async_.vault.stock_pool_list(), __file__)

    # 示例 2 · 原始返回: 服务端 data 含 poolList 等原始字段
    show_result(
        await gangtise.async_.vault.stock_pool_list(
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
