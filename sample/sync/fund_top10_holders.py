"""fund.top10_holders — 前十大持有人（仅上市基金；ETF 可能多一行 serialNumber=11 的联接基金）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.top10_holders(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 2025 年报
    show_result(
        gangtise.fund.top10_holders(
            security="510300.SH",  # 上市基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2025-12-31",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2025-12-31",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
        ),
        __file__,
    )

    # 示例 2 · ETF + LOF 场内代码 + 原始返回
    show_result(
        gangtise.fund.top10_holders(
            security=[
                "510300.SH",
                "161005.SZ",
            ],  # 上市基金交易代码, 后缀大写（场外 .OF / 场内 .SH .SZ）; 单值或列表
            start_date="2025-06-30",  # 报告期起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2025-12-31",  # 报告期止（YYYY-MM-DD）; 起 > 止报 110002
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
