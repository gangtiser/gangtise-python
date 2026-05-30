"""fundamental.valuation_analysis — 估值分析（历史分位等），返回 DataFrame。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.fundamental.valuation_analysis(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 证券代码 + 估值指标（均必填）
    show_result(
        await gangtise.async_.fundamental.valuation_analysis(
            security_code="000001.SZ",  # 单个证券代码
            indicator="peTtm",  # 估值指标: peTtm/pbMrq/peg/psTtm/pcfTtm/em
        ),
        __file__,
    )

    # 示例 2 · 时间窗 + 限制条数 + 过滤空值
    show_result(
        await gangtise.async_.fundamental.valuation_analysis(
            security_code="600519.SH",  # 单个证券代码, 如 000001.SZ/600519.SH
            indicator="pbMrq",  # pbMrq=市净率(最新季)
            start_date="2025-01-01",  # 起始日期 YYYY-MM-DD
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD
            limit=20,  # 返回条数上限
            skip_null=True,  # 客户端过滤 value/percentileRank 为空的行
        ),
        __file__,
    )

    # 示例 3 · 指定字段 + 原始返回
    show_result(
        await gangtise.async_.fundamental.valuation_analysis(
            security_code="000001.SZ",
            indicator="psTtm",  # psTtm=市销率TTM（其余: peg/pcfTtm=市现率TTM、em=企业倍数）
            field=["date", "value", "percentileRank"],  # 返回字段, 支持单值或列表; 省略则用默认字段
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
