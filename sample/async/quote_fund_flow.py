"""quote.fund_flow — A 股个股日资金流向（SH/SZ/BJ）, 返回 DataFrame。

沪深京个股, 返回小/中/大/特大单流入流出金额及占比、主力净流入等; 免费。
通过多组示例覆盖全部参数；可选参数的取值范围已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
security="aShares" 时按日期窗口自动分片（每片 1 个交易日）并并发拉取后合并, 须同时传日期区间。
异步路径为 gangtise.async_.quote.fund_flow(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取单只 A 股一段日资金流向
    show_result(
        await gangtise.async_.quote.fund_flow(
            security="600519.SH",  # A 股代码, 后缀 .SH/.SZ/.BJ; 支持单值或列表; "aShares"=全市场
            start_date="2026-05-01",  # 开始日期 YYYY-MM-DD; 省略默认结束日往前 1 年
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD; 省略默认最新交易日
            limit=10,  # 单次返回条数上限; 默认 6000, 最大 10000
        ),
        __file__,
    )

    # 示例 2 · 多只证券 + 指定返回字段
    show_result(
        await gangtise.async_.quote.fund_flow(
            security=["600519.SH", "000001.SZ"],  # 支持单值或列表
            start_date="2026-05-01",
            end_date="2026-05-28",
            field=[
                "tradeDate",
                "mainNetInflow",  # 主力净流入
                "largeInflow",  # 大单流入
                "xlargeOutflow",  # 特大单流出
            ],  # 返回字段, 支持单值或列表; 省略则用服务端默认字段
        ),
        __file__,
    )

    # 示例 3 · 原始返回（不转 DataFrame）
    show_result(
        await gangtise.async_.quote.fund_flow(
            security="000001.SZ",
            start_date="2026-05-20",
            end_date="2026-05-28",
            raw=True,  # True=返回服务端原始 data（含 fieldList/list 矩阵）, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选用法:
    #   security="aShares"        全市场: 必须同时传 start_date/end_date（缺日期抛 ValidationError）,
    #                             自动按 1 交易日/片分片并发拉取合并
    #   单只证券撞上 limit 时结果标 partial（raw 可见）并发 UserWarning, 提示缩小日期区间或分批取数


if __name__ == "__main__":
    asyncio.run(main())
