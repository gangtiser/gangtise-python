"""bond.issuer_rating_change — 发债主体评级变动历史，返回 DataFrame。

按发行人计费 0.4 积分/个, 超时 / 5xx 不自动重试。security 与 issuer 二选一（同传或都不传
本地拒绝）; 命中的发行人超过 10 个时服务端报 100006。日期筛公告日, 可省略。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.bond.issuer_rating_change(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 按发行人名称 + 公告日区间
    show_result(
        gangtise.bond.issuer_rating_change(
            issuer="国家电网有限公司",  # 发行人全称或简称, 单值或列表; 与 security 二选一
            start_date="2026-01-01",  # 公告日起始 YYYY-MM-DD
            end_date="2026-09-20",  # 公告日结束 YYYY-MM-DD
        ),
        __file__,
    )

    # 示例 2 · 按债券代码查其发行人的评级变动 + 原始返回
    show_result(
        gangtise.bond.issuer_rating_change(
            security="136236.SH",  # 标准债券代码, 单值或列表; 与 issuer 二选一
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   field=[...]   返回字段, 省略返回全部（默认列 issuerName + announcementDate 恒在最前）


if __name__ == "__main__":
    main()
