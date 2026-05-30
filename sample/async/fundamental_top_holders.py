"""fundamental.top_holders — 前十大股东 / 前十大流通股东，返回 DataFrame。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.fundamental.top_holders(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 证券代码 + 股东类型（必填）
    show_result(
        await gangtise.async_.fundamental.top_holders(
            security_code="000001.SZ",  # 单个证券代码
            holder_type="top10",  # 股东类型: top10=前十大股东 / top10Float=前十大流通股东
        ),
        __file__,
    )

    # 示例 2 · 前十大流通股东 + 时间窗 + 报告期
    show_result(
        await gangtise.async_.fundamental.top_holders(
            security_code="600519.SH",  # 单个证券代码, 如 000001.SZ/600519.SH
            holder_type="top10Float",  # top10Float=前十大流通股东
            start_date="2024-01-01",  # 起始日期 YYYY-MM-DD
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD
            period=["interim", "annual"],  # 报告期: q1/interim/q3/annual/latest, 支持单值或列表
            fiscal_year=[2024, 2025],  # 财年过滤, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 最新一期 + 原始返回
    show_result(
        await gangtise.async_.fundamental.top_holders(
            security_code="000001.SZ",
            holder_type="top10",
            period="latest",  # latest=最新一期
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
