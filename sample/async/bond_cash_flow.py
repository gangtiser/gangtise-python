"""bond.cash_flow — 债券付息与兑付计划，返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。日期筛兑付日, 可省略（省略返回全部历史）。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.bond.cash_flow(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 全部历史兑付计划
    show_result(await gangtise.async_.bond.cash_flow(security="019742.SH"), __file__)

    # 示例 2 · 按兑付日区间筛选 + 原始返回
    show_result(
        await gangtise.async_.bond.cash_flow(
            security="019742.SH",  # 标准债券代码, 单值或列表
            start_date="2026-01-01",  # 兑付日起始 YYYY-MM-DD
            end_date="2026-12-31",  # 兑付日结束 YYYY-MM-DD
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   field=[...]   返回字段, 省略返回全部（默认列 securityCode + paymentDate 恒在最前）


if __name__ == "__main__":
    asyncio.run(main())
