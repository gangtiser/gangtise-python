"""bond.default_list — 违约债券（代码/简称/违约日期/违约金额/发行人/违约原因），返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。违约日期区间、security、issuer 三选一（同传或都不传本地拒绝）。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.bond.default_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 按违约日期区间(两端都给, 不超过 1 个自然年)
    show_result(
        await gangtise.async_.bond.default_list(start_date="2025-01-01", end_date="2025-12-31"),
        __file__,
    )

    # 示例 2 · 按债券代码(不限只数, 没有违约记录的代码不产生行) + 指定字段
    show_result(
        await gangtise.async_.bond.default_list(
            security=["169687.SH", "146589.SH"],
            field=["securityName", "defaultAmount", "issuerName", "defaultReason"],  # 金额单位亿元
        ),
        __file__,
    )

    # 示例 3 · 按发行人(一次一个, 用全称; 简称只返回最匹配的一家, 核对 issuerName) + 原始返回
    show_result(
        await gangtise.async_.bond.default_list(issuer="上海世茂股份有限公司", raw=True), __file__
    )


if __name__ == "__main__":
    asyncio.run(main())
