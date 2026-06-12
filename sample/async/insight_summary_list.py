"""insight.summary_list — 纪要列表（分页, 端点最大页 50, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.summary_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(await gangtise.async_.insight.summary_list(size=5), __file__)

    # 示例 2 · 常用过滤: 关键词 + 时间窗 + 证券 + 市场
    show_result(
        await gangtise.async_.insight.summary_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="平安银行",  # 关键词
            search_type=1,  # 搜索类型代码（默认 1; cli.ts 未列枚举, 取值见接口文档）
            rank_type=1,  # 排序方式代码（默认 1; cli.ts 未列枚举, 取值见接口文档）
            security="000001.SZ",  # 证券代码, 支持单值或列表
            market="SH",  # 市场, 支持单值或列表; 例如 SH/SZ/HK/US
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.insight.summary_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            category=["stock"],  # 分类, 支持单值或列表; 取值 earningsCall/strategyMeeting 等
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数:
    #   source=<来源类型编号>         数字列表, 支持单值或列表（请求字段 sourceList, 为数字编码）
    #   research_area=<研究领域ID>    见 reference.constant_list(category="citicIndustry"); 支持单值或列表
    #   institution=<机构ID>          机构过滤, 支持单值或列表
    #   participant_role=<参与方角色> 参与方角色名称过滤, 支持单值或列表


if __name__ == "__main__":
    asyncio.run(main())
