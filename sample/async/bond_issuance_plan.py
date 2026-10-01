"""bond.issuance_plan — 利率债发行计划（只按日期区间查, 不收债券码），返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。日期必填; 历史范围正式账号前溯 5 年、试用 3 年,
start_date 早于可回溯下界时整批 110003。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.bond.issuance_plan(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 必填参数: 发行日区间
    show_result(
        await gangtise.async_.bond.issuance_plan(
            start_date="2026-09-01",  # 发行日起始 YYYY-MM-DD（必填）
            end_date="2026-09-30",  # 发行日结束 YYYY-MM-DD（必填）
        ),
        __file__,
    )

    # 示例 2 · 原始返回
    show_result(
        await gangtise.async_.bond.issuance_plan(
            start_date="2026-09-01",
            end_date="2026-09-30",
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   field=[...]   返回字段, 省略返回全部（默认列 issueDate 恒在最前）


if __name__ == "__main__":
    asyncio.run(main())
