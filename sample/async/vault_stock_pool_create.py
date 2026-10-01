"""vault.stock_pool_create — 新建股票池（免费, 写操作）, 返回 {poolId, poolName}。

池名 ≤10 个字符（中文算 1 个, 超出 230007）, 不能与已有池重名（230006, 整串精确比较,
首尾空格不去、大小写不归一）, 每账号最多 30 个池（230003）。
该端点超时 / 5xx 不自动重发: 超时后先 vault.stock_pool_list() 看池建成没有, 再决定重来。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_create(...)。

本示例会改动账号数据: 把 POOL_NAME 设为要新建的池名后再运行。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise

# 要新建的池名（≤10 个字符, 不可与已有池重名）; 留空则不发请求。
POOL_NAME = ""


async def main():
    if not POOL_NAME:
        raise SystemExit("请先填好 POOL_NAME——本示例会创建真实的股票池。")
    result = await gangtise.async_.vault.stock_pool_create(
        name=POOL_NAME,  # 新池名（必填）
    )
    show_result(result, __file__)  # {poolId, poolName}; poolId 供后续增删改使用


if __name__ == "__main__":
    asyncio.run(main())
