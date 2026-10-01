"""bond.rating_overview — 债券评级一览（债项/发行人/担保人三套评级并列），返回 DataFrame。

按条计费 0.4 积分/条, 超时 / 5xx 不自动重试。单次最多 10 只（去重后计, 超出本地拒绝）。
评级值可能带 sf / pi 小写后缀（AA+sf、AAApi）, 分档统计前先处理。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.bond.rating_overview(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单只债券
    show_result(gangtise.bond.rating_overview(security="136236.SH"), __file__)

    # 示例 2 · 多只债券 + 原始返回
    show_result(
        gangtise.bond.rating_overview(
            security=["136236.SH", "019742.SH"],  # 标准债券代码列表, 去重后单次最多 10 只
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   field=[...]   返回字段, 省略返回全部; 写错字段名整批 100003


if __name__ == "__main__":
    main()
