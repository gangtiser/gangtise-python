"""insight.research_list — 券商研报列表（分页, 端点最大页 50, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.research_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(await gangtise.async_.insight.research_list(size=5), __file__)

    # 示例 2 · 全文检索 + 时间窗 + 证券 + 页数区间
    show_result(
        await gangtise.async_.insight.research_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="储能",  # 关键词
            search_type=2,  # 搜索类型: 1=标题 2=全文
            rank_type=2,  # 排序: 1=综合 2=时间倒序
            security="600519.SH",  # 证券代码, 支持单值或列表
            min_pages=5,  # 研报最小页数
            max_pages=50,  # 研报最大页数
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.insight.research_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            industry=[1],  # 申万行业 ID（见 reference.constant_list(category="swIndustry")）
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   broker=<券商/机构ID>     见 lookup.broker_orgs
    #   category=<研报分类>      研报分类名称, 取值 macro/strategy/industry/company 等
    #   llm_tag=<语义标签>       LLM 语义标签过滤
    #   rating=<评级名称>        如 买入/增持 等; 取值参考接口文档
    #   rating_change=<评级变动> 评级变动名称过滤
    #   source=<来源类型>        来源类型, 字符串列表, 支持单值或列表


if __name__ == "__main__":
    asyncio.run(main())
