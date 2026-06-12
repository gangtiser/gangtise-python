"""insight.foreign_report_list — 海外研报列表（分页, 端点最大页 50, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.foreign_report_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(await gangtise.async_.insight.foreign_report_list(size=5), __file__)

    # 示例 2 · 全文检索 + 时间窗 + 美股 + 页数区间
    show_result(
        await gangtise.async_.insight.foreign_report_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="AI",  # 关键词
            search_type=2,  # 搜索类型: 1=标题 2=全文
            rank_type=2,  # 排序: 1=综合 2=时间倒序
            security="UBER.N",  # 证券代码（美股如 UBER.N）, 支持单值或列表
            min_pages=5,  # 研报最小页数
            max_pages=50,  # 研报最大页数
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.insight.foreign_report_list(
            security=["UBER.N"],  # 证券代码, 支持单值或列表
            region=["US"],  # 区域过滤, 支持单值或列表（区域 ID/代码）
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   category=<研报分类>      研报分类名称, 取值 macro/strategy/industry/company 等
    #   industry=<行业ID>        见 reference.constant_list(category="swIndustry")
    #   broker=<券商/机构ID>     见 lookup.broker_orgs
    #   llm_tag=<语义标签>       LLM 语义标签过滤
    #   rating=<评级名称>        评级名称过滤
    #   rating_change=<评级变动> 评级变动名称过滤


if __name__ == "__main__":
    asyncio.run(main())
