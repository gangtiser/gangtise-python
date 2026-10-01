"""bond.exercise_notice — 含权债的回售 / 赎回行权安排与结果，返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。日期筛行权日, 可省略（省略返回全部历史）。
国债这类品种本身没有行权数据, 返回 130001 属正常。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.bond.exercise_notice(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 全部历史行权记录
    show_result(gangtise.bond.exercise_notice(security="136236.SH"), __file__)

    # 示例 2 · 原始返回
    show_result(
        gangtise.bond.exercise_notice(
            security="136236.SH",  # 标准债券代码, 单值或列表
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   start_date / end_date="YYYY-MM-DD"   行权日区间, 省略返回全部历史
    #   field=[...]   返回字段, 省略返回全部（默认列 securityCode + exerciseDate 恒在最前）


if __name__ == "__main__":
    main()
