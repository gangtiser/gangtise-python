"""insight.announcement_list — A 股公告列表（分页, 端点最大页 50, 返回 DataFrame）。

start_time/end_time 接受日期字符串或 13 位毫秒时间戳, wrapper 会自动转换为毫秒。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.announcement_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 单只 A 股最近 5 条公告
    show_result(
        await gangtise.async_.insight.announcement_list(size=5, security="000001.SZ"),
        __file__,
    )

    # 示例 2 · 全文检索 + 时间窗（日期字符串会转为毫秒）
    show_result(
        await gangtise.async_.insight.announcement_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间; 接受日期字符串或 13 位毫秒时间戳
            end_time="2026-05-28",  # 结束时间; 接受日期字符串或 13 位毫秒时间戳
            keyword="年度报告",  # 关键词
            search_type=2,  # 搜索类型: 1=标题 2=全文
            rank_type=2,  # 排序: 1=综合 2=时间倒序
            security="000001.SZ",  # 证券代码, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.insight.announcement_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   announcement_type=<公告类型> 公告类型过滤, 取值参考接口文档
    #   category=<分类ID>            分类 ID 过滤, 取值参考 lookup 接口


if __name__ == "__main__":
    asyncio.run(main())
