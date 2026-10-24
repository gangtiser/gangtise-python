"""insight.forum_list — 论坛/电话会日程列表（分页, 端点最大页 50, 返回 DataFrame）。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.insight.forum_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(await gangtise.async_.insight.forum_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 关键词 + 证券 + 对象类型
    show_result(
        await gangtise.async_.insight.forum_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="AI",  # 关键词
            research_area=[100800110],  # 中信行业码 1008001xx（或方向码 122000xxx）; 申万码在此返 0
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.insight.forum_list(
            research_area=[100800110, 100800101],  # 中信行业码, 支持单值或列表
            keyword="AI",  # 关键词
            size=20,  # 按条计费（10 积分/条）: 带 size 取一部分; 要全量改传 confirm=True
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数:
    #   research_area=<研究领域ID>    见 reference.constant_list(category="citicIndustry"); 支持单值或列表
    #   location=<城市码>             domesticCity 码（如上海 "156310000"）; 传城市名报 999999


if __name__ == "__main__":
    asyncio.run(main())
