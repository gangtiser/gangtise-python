"""fundamental.balance_sheet_hk — 港股资产负债表（中国准则口径），返回 DataFrame。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.fundamental.balance_sheet_hk(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 仅传必填港股代码
    show_result(
        await gangtise.async_.fundamental.balance_sheet_hk(
            security_code="00700.HK"
        ),  # 单个港股代码
        __file__,
    )

    # 示例 2 · 时间窗 + 报告期过滤
    show_result(
        await gangtise.async_.fundamental.balance_sheet_hk(
            security_code="01913.HK",  # 单个港股代码, 如 00700.HK/01913.HK
            start_date="2024-01-01",  # 起始日期 YYYY-MM-DD
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD
            period=["h1", "annual"],  # 港股报告期: q1/h1/q3/h2/nsd/annual/latest, 支持单值或列表
            fiscal_year=[2024, 2025],  # 财年过滤, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 指定字段 + 原始返回
    show_result(
        await gangtise.async_.fundamental.balance_sheet_hk(
            security_code="00700.HK",
            period="latest",  # latest=最新报告期
            field=["totalAssets", "totalLiab"],  # 返回字段, 支持单值或列表; 省略则用服务端默认字段
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   report_type=<报告类型>   报表类型: consolidated 合并(默认) / consolidatedRestated 合并(调整) / standalone 母公司 / standaloneRestated 母公司(调整); 支持单值或列表


if __name__ == "__main__":
    asyncio.run(main())
