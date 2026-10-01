"""bond.issuance_detail — 债券发行与增发记录（招标/定价/认购倍数），返回 DataFrame。

0.4 积分/次, 超时 / 5xx 不自动重试。日期筛发行公告日, 可省略（省略返回全部历史）。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.bond.issuance_detail(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 全部发行与增发记录
    show_result(gangtise.bond.issuance_detail(security="019742.SH"), __file__)

    # 示例 2 · 按发行公告日区间筛选 + 原始返回
    show_result(
        gangtise.bond.issuance_detail(
            security="019742.SH",  # 标准债券代码, 单值或列表
            start_date="2024-01-01",  # 发行公告日起始 YYYY-MM-DD
            end_date="2024-12-31",  # 发行公告日结束 YYYY-MM-DD
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   field=[...]   返回字段, 省略返回全部（默认列 securityCode + issueBatchNo 恒在最前）


if __name__ == "__main__":
    main()
