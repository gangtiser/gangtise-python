"""ai.peer_comparison — 生成个股同业对比（返回结构化 dict）。

仅需证券代码即可调用; 返回 dict, 故只保留 1 个执行示例(多次写同名 .md 会互相覆盖)。
异步用法相同, 路径为 gangtise.async_.ai.peer_comparison(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 个股同业对比: 传入单个证券代码
    show_result(
        await gangtise.async_.ai.peer_comparison(
            security_code="000001.SZ",  # 单个证券代码, A股/港股/美股皆可
        ),
        __file__,
    )
    # 其它示例(注释展示, 不执行——dict 返回会覆盖同名输出):
    #   await gangtise.async_.ai.peer_comparison(security_code="600519.SH")     # A 股(贵州茅台)
    #   await gangtise.async_.ai.peer_comparison(security_code="01913.HK")      # 港股
    #   await gangtise.async_.ai.peer_comparison(security_code="UBER.N")        # 美股
    #   await gangtise.async_.ai.peer_comparison(security_code="000001.SZ", raw=True)  # 原始 data


if __name__ == "__main__":
    asyncio.run(main())
