"""bond.issuer_info — 发债主体基本信息（性质/行业/注册/评级/存续债券），返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。security 与 issuer 二选一（同传或都不传本地拒绝）。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.bond.issuer_info(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 按债券代码查其发行人
    show_result(await gangtise.async_.bond.issuer_info(security="136236.SH"), __file__)

    # 示例 2 · 按发行人名称查（模糊匹配, 一个名称取最匹配的一家）+ 指定字段
    show_result(
        await gangtise.async_.bond.issuer_info(
            issuer="国家电网有限公司",  # 发行人全称或简称, 单值或列表; 与 security 二选一
            field=[
                "issuerName",
                "swIndustry",
                "latestIssuerRating",
                "ratingAgency",
            ],  # latestIssuerRating 混合境内外口径, 一并取 ratingAgency 判断
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(await gangtise.async_.bond.issuer_info(security="136236.SH", raw=True), __file__)


if __name__ == "__main__":
    asyncio.run(main())
