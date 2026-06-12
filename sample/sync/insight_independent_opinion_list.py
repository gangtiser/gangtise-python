"""insight.independent_opinion_list — 海外独立分析师观点列表（分页, 端点最大页 50, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.independent_opinion_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(gangtise.insight.independent_opinion_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 关键词 + 美股 + 行业, 时间倒序
    show_result(
        gangtise.insight.independent_opinion_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="biotech",  # 关键词
            rank_type=2,  # 排序: 1=综合 2=时间倒序
            security="GSK.N",  # 证券代码（美股如 GSK.N）, 支持单值或列表
            industry=1,  # 申万行业 ID, 支持单值或列表（见 reference.constant_list(category="swIndustry")）
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        gangtise.insight.independent_opinion_list(
            security=["GSK.N"],  # 证券代码, 支持单值或列表
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   rating=<评级名称>        评级名称过滤
    #   rating_change=<评级变动> 评级变动名称过滤


if __name__ == "__main__":
    main()
