"""fund.manager_history — 基金历任基金经理（endDate 为 null 即现任）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.manager_history(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用
    show_result(
        await gangtise.async_.fund.manager_history(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
        ),
        __file__,
    )

    # 示例 2 · 多只基金 + 原始返回
    show_result(
        await gangtise.async_.fund.manager_history(
            security=[
                "005827.OF",
                "161005.OF",
            ],  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
