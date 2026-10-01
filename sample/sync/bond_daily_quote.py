"""bond.daily_quote — 债券日收盘行情（交易所 + CFETS: 全价/净价/YTM/久期/凸性），返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。日期必填; 历史范围正式账号前溯 5 年、试用 3 年,
start_date 早于可回溯下界时整批 110003。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.bond.daily_quote(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 必填参数: 债券代码 + 交易日区间
    show_result(
        gangtise.bond.daily_quote(
            security="019742.SH",  # 标准债券代码, 单值或列表; 不限只数
            start_date="2026-09-15",  # 交易日起始 YYYY-MM-DD（必填）
            end_date="2026-09-19",  # 交易日结束 YYYY-MM-DD（必填）
        ),
        __file__,
    )

    # 示例 2 · 指定字段
    show_result(
        gangtise.bond.daily_quote(
            security="019742.SH",
            start_date="2026-09-15",
            end_date="2026-09-19",
            field=["cleanClose", "ytmClose", "modifiedDuration"],  # 净价收盘 / 收盘 YTM / 修正久期
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.bond.daily_quote(
            security="019742.SH", start_date="2026-09-15", end_date="2026-09-19", raw=True
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
