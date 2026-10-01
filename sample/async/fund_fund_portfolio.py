"""fund.fund_portfolio — FOF 基金持仓（万元；只返回持仓基金简称, 不返回代码）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.fund_portfolio(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用
    show_result(
        await gangtise.async_.fund.fund_portfolio(
            security="005220.OF",  # FOF 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2026-06-30",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-06-30",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
        ),
        __file__,
    )

    # 示例 2 · 一年区间 + 原始返回
    show_result(
        await gangtise.async_.fund.fund_portfolio(
            security="005220.OF",  # FOF 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2025-06-30",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-06-30",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
