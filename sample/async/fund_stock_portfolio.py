"""fund.stock_portfolio — 股票持仓（万股 / 万元；只返回股票简称, 不返回代码）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.stock_portfolio(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 最新一期重仓股
    show_result(
        await gangtise.async_.fund.stock_portfolio(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2026-06-30",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-06-30",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
        ),
        __file__,
    )

    # 示例 2 · 中报全部持股
    show_result(
        await gangtise.async_.fund.stock_portfolio(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2026-06-30",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-06-30",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
            position_type="all",  # top=重仓股票, 各季度披露（服务端默认） / all=全部持股, 仅中报、年报披露
        ),
        __file__,
    )

    # 示例 3 · 近一年各季重仓 + 原始返回
    show_result(
        await gangtise.async_.fund.stock_portfolio(
            security="005827.OF",  # 基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2025-09-30",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-06-30",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
            position_type="top",  # top=重仓股票, 各季度披露（服务端默认） / all=全部持股, 仅中报、年报披露
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
