"""vault.stock_pool_delete — 批量删除股票池（免费, 写操作, 不可恢复）。

删池会同时移除池内全部证券的关注关系（个股投资笔记不受影响）, 必须传 confirm=True,
否则在发请求前抛 ValidationError。返回 {successList, failList}; 删不存在的池算成功。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_delete(...)。

本示例会删除数据: 先用 vault.stock_pool_list() 核对池名, 再把 POOL_IDS 填好后运行。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise

# 要删除的池 ID 列表, 取自 vault.stock_pool_list(); 留空则不发请求。
POOL_IDS: list[str] = []


async def main():
    if not POOL_IDS:
        raise SystemExit("请先填好 POOL_IDS——本示例会删除真实的股票池。")
    result = await gangtise.async_.vault.stock_pool_delete(
        pool_id=POOL_IDS,  # 股票池 ID（必填）, 支持单值或列表
        confirm=True,  # 必须显式确认; 不传则在发请求前抛 ValidationError
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
