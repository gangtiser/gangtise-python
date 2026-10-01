"""fund.manager_info — 基金经理基本信息（按姓名查, 不是基金代码）。

计费 0.4 积分/次（与行数、基金只数无关；空结果与报错不扣）；超时 / 5xx 不自动重发。
代码不存在、不带后缀、后缀小写或传成股票代码都返回空结果、不报错。
全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.fund.manager_info(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单个经理
    show_result(
        gangtise.fund.manager_info(
            manager="张坤",  # 经理姓名, 精确匹配, 同名经理全部返回; 多人请传列表
        ),
        __file__,
    )

    # 示例 2 · 多个经理 + 原始返回
    show_result(
        gangtise.fund.manager_info(
            manager=["张坤", "葛兰"],  # 经理姓名, 精确匹配, 同名经理全部返回; 多人请传列表
            raw=True,  # True=返回服务端原始 data（{list}, 无 total）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
