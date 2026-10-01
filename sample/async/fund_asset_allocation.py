"""fund.asset_allocation — 资产配置：按资产类型的金额（元）与占基金资产总值比。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.asset_allocation(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 2026 中报一级分类
    show_result(
        await gangtise.async_.fund.asset_allocation(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2026-06-30",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-06-30",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
            asset_level="level1",  # level1 一级 / level2 二级; 单值或列表, 不传两级都返回（一二级混在一起别直接加总）
        ),
        __file__,
    )

    # 示例 2 · 一二级都要 + 原始返回
    show_result(
        await gangtise.async_.fund.asset_allocation(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2025-12-31",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-06-30",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
            asset_level=[
                "level1",
                "level2",
            ],  # level1 一级 / level2 二级; 单值或列表, 不传两级都返回（一二级混在一起别直接加总）
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
