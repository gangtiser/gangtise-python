"""fund.fee_rate — 基金费率：按费率类型与条件分档多行（feeRate 是字符串）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.fee_rate(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 全部费率类型
    show_result(
        await gangtise.async_.fund.fee_rate(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
        ),
        __file__,
    )

    # 示例 2 · 只看管理费与托管费
    show_result(
        await gangtise.async_.fund.fee_rate(
            security="003096.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            fee_type=[
                "managementFee",
                "custodianFee",
            ],  # purchaseFee 申购 / redemptionFee 赎回 / managementFee 管理 / custodianFee 托管 / saleFee 销售服务; 单值或列表, 不传返回全部
        ),
        __file__,
    )

    # 示例 3 · 赎回费分档 + 原始返回
    show_result(
        await gangtise.async_.fund.fee_rate(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            fee_type="redemptionFee",  # purchaseFee 申购 / redemptionFee 赎回 / managementFee 管理 / custodianFee 托管 / saleFee 销售服务; 单值或列表, 不传返回全部
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
