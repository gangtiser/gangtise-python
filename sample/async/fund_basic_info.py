"""fund.basic_info — 基金基本信息：分类、管理人与托管人、申赎规则、业绩基准、风险等级、跟踪指数。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.basic_info(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 单只基金全部字段
    show_result(
        await gangtise.async_.fund.basic_info(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
        ),
        __file__,
    )

    # 示例 2 · 多只场内基金 + 选列
    show_result(
        await gangtise.async_.fund.basic_info(
            security=[
                "510300.SH",
                "159967.SZ",
            ],  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            field=[
                "fundName",
                "exchange",
                "isIndexFund",
                "trackIndexName",
            ],  # 返回字段, 单值或列表, 不传返回全部; fundCode 始终返回; 字段名写错整批报 100003
        ),
        __file__,
    )

    # 示例 3 · 基金画像字段 + 原始返回
    show_result(
        await gangtise.async_.fund.basic_info(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            field=[
                "fundName",
                "investTypeNameLevel2",
                "mgrComp",
                "setupDate",
                "riskLevel",
            ],  # 返回字段, 单值或列表, 不传返回全部; fundCode 始终返回; 字段名写错整批报 100003
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
