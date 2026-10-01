"""bond.basic_info — 债券基本资料（发行/期限/票息/评级/担保/特殊条款），返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。security 只收标准债券代码（简称/拼音整批 120001）。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.bond.basic_info(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 单只债券, 返回全部字段
    show_result(await gangtise.async_.bond.basic_info(security="019742.SH"), __file__)

    # 示例 2 · 多只债券 + 指定字段
    show_result(
        await gangtise.async_.bond.basic_info(
            security=[
                "019742.SH",
                "136236.SH",
            ],  # 标准债券代码, 单值或列表; 去重后单次最多 10000 只
            field=[
                "securityName",
                "couponRate",
                "maturityDate",
                "issueSize",
            ],  # 返回字段; 省略返回全部, 写错字段名整批 100003
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        await gangtise.async_.bond.basic_info(
            security="019742.SH",
            raw=True,  # True=返回服务端原始 data（列式 fieldList + list）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
