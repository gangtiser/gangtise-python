"""bond.rating_change — 债项评级变动历史，返回 DataFrame。

按有数据的债券只数计费 0.4 积分/只, 超时 / 5xx 不自动重试。单次最多 10 只（去重后计,
超出本地拒绝）。日期筛评级变动公告日, 可省略（省略返回全部历史）。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.bond.rating_change(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 全部历史评级变动
    show_result(await gangtise.async_.bond.rating_change(security="149478.SZ"), __file__)

    # 示例 2 · 按公告日区间筛选 + 原始返回
    show_result(
        await gangtise.async_.bond.rating_change(
            security="149478.SZ",  # 标准债券代码, 单值或列表; 去重后单次最多 10 只
            start_date="2023-01-01",  # 评级变动公告日起始 YYYY-MM-DD
            end_date="2026-09-20",  # 评级变动公告日结束 YYYY-MM-DD
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   field=[...]   返回字段, 省略返回全部（默认列 securityCode + announcementDate 恒在最前）


if __name__ == "__main__":
    asyncio.run(main())
