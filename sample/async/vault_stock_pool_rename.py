"""vault.stock_pool_rename — 股票池改名（免费, 写操作）, 返回 {poolId, poolName}。

只改名, 池内自选股不受影响; 新名规则同 stock_pool_create（≤10 个字符, 不可重名）,
改成该池自己当前的名字算成功。
异步用法相同, 路径为 gangtise.async_.vault.stock_pool_rename(...)。

本示例会改动账号数据: 把 POOL_ID / NEW_NAME 填好后再运行。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise

# 池 ID 取自 vault.stock_pool_list(); 留空则不发请求。
POOL_ID = ""
NEW_NAME = ""


async def main():
    if not (POOL_ID and NEW_NAME):
        raise SystemExit("请先填好 POOL_ID 与 NEW_NAME——本示例会重命名真实的股票池。")
    result = await gangtise.async_.vault.stock_pool_rename(
        pool_id=POOL_ID,  # 股票池 ID（必填）, 取自 vault.stock_pool_list
        name=NEW_NAME,  # 新池名（必填）, ≤10 个字符
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
