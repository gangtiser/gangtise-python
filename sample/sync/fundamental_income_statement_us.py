"""fundamental.income_statement_us — 美股利润表，返回 DataFrame。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fundamental.income_statement_us(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 美股代码 + 单个财年（美股一次只取一个财年; 不带条件时每种报告期只回某一年, 并发 UserWarning）
    show_result(
        gangtise.fundamental.income_statement_us(
            security_code="AAPL.O",  # 单个美股代码
            fiscal_year=2025,  # 单个财年
        ),
        __file__,
    )

    # 示例 2 · 单个财年 + 报告期过滤
    show_result(
        gangtise.fundamental.income_statement_us(
            security_code="TSLA.O",  # 单个美股代码, 如 AAPL.O/TSLA.O
            fiscal_year=2025,  # 财年; 多年按年逐个查（跨财年时每种报告期只回一年, 发 UserWarning）
            period=["h1", "annual"],  # 美股报告期: q1/h1/q3/nsd/annual/latest, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 指定字段 + 原始返回
    show_result(
        gangtise.fundamental.income_statement_us(
            security_code="AAPL.O",
            period="latest",  # 最新一期; 可能多一行 period 为空的最近一季单季值
            field=["totalOpRev", "netProfit"],  # 返回字段; 省略返回完整报表, 写错字段名报 100005
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   start_date / end_date=<YYYY-MM-DD>   日期区间, 与 fiscal_year 都给时按日期取; 区间别覆盖同一报告期的两个期末
    #   report_type=<报告类型>   报表类型: consolidated 合并(默认) / consolidatedRestated 合并(调整) / standalone 母公司 / standaloneRestated 母公司(调整); 支持单值或列表


if __name__ == "__main__":
    main()
