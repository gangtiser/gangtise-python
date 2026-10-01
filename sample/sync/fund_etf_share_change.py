"""fund.etf_share_change — ETF 份额变动：逐交易日份额（万份）与规模（万元）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.etf_share_change(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 一个月
    show_result(
        gangtise.fund.etf_share_change(
            security="510300.SH",  # ETF 交易代码, 后缀大写（.SH / .SZ）; 单值或列表
            start_date="2026-09-01",  # 交易日起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-09-30",  # 交易日止（YYYY-MM-DD）; 起 > 止报 110002
        ),
        __file__,
    )

    # 示例 2 · 多只 ETF 两个交易日 + 原始返回
    show_result(
        gangtise.fund.etf_share_change(
            security=["510300.SH", "159967.SZ"],  # ETF 交易代码, 后缀大写（.SH / .SZ）; 单值或列表
            start_date="2026-09-17",  # 交易日起（YYYY-MM-DD）; 早于账号可回溯窗口整批报 110003
            end_date="2026-09-18",  # 交易日止（YYYY-MM-DD）; 起 > 止报 110002
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
