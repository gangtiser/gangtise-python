"""quote.sector_fund_flow — 板块日资金流向（免费）, 返回 DataFrame。

每个值是板块当日成分股资金流向的加总, 只计沪深京上市公司; 返回按板块、日期倒序, 没有占比字段。
板块 ID 用 reference.sector_search 查。查询太重报 100006: 缩短区间、减少板块或字段（调小 limit 无效）。
通过几组示例演示常用参数，可选参数的取值范围写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.quote.sector_fund_flow(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 先按名称查板块 ID（免费）: 行字段 sectorId / sectorName / hierarchy
    sectors = await gangtise.async_.reference.sector_search(keyword="半导体", top=2)
    sector_ids = sectors["sectorId"].tolist()

    # 示例 1 · 单个板块一段区间的主力 / 大单资金流向
    show_result(
        await gangtise.async_.quote.sector_fund_flow(
            sector=sector_ids[0],  # 板块 ID（必填）, 支持单值或列表
            start_date="2026-10-01",  # 开始日期 YYYY-MM-DD; 省略默认结束日往前 1 年
            end_date="2026-10-30",  # 结束日期 YYYY-MM-DD; 省略默认最新已入库交易日
            field=["sectorMainNetInflow", "sectorLargeInflow"],  # 资金字段; 省略返回全部
        ),
        __file__,
    )

    # 示例 2 · 多个板块 + 行数上限 + 原始返回
    show_result(
        await gangtise.async_.quote.sector_fund_flow(
            sector=sector_ids,  # 多个板块一起查; 计算量随板块数、成分股数、天数与字段数增长
            start_date="2026-10-20",
            end_date="2026-10-30",
            limit=1000,  # 返回行数上限, 默认 6000、最大 10000; 撞满标 partial 并发 warning
            raw=True,  # True=返回服务端原始 data（含 fieldList/list 矩阵）, 不转 DataFrame
        ),
        __file__,
    )
    # 字段: sector{Small|Medium|Large|Xlarge}{Inflow|Outflow|NetInflow}、sectorMain{Inflow|Outflow|NetInflow}、
    #       sectorTotalInflow / sectorTotalOutflow（单位元）; 只传 sectorId / tradeDate 会返回 0 行


if __name__ == "__main__":
    asyncio.run(main())
