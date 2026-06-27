"""insight.announcement_us_list — 美股公告列表（分页, 端点最大页 50, 返回 DataFrame）。

与 A 股公告不同, 此处 start_time/end_time 为普通日期/时间字符串, 不做毫秒转换。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.insight.announcement_us_list(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 单只美股最近 5 条公告（美股代码如 TSLA.O / AAPL.O）
    show_result(
        await gangtise.async_.insight.announcement_us_list(size=5, security="TSLA.O"),
        __file__,
    )

    # 示例 2 · 全文检索 + 时间窗
    show_result(
        await gangtise.async_.insight.announcement_us_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间（普通日期/时间字符串）
            end_time="2026-05-28",  # 结束时间（普通日期/时间字符串）
            keyword="earnings",  # 关键词
            search_type=2,  # 搜索类型: 1=标题 2=全文
            rank_type=2,  # 排序: 1=综合 2=时间倒序
            security="TSLA.O",  # 美股代码, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.insight.announcement_us_list(
            security=["TSLA.O", "AAPL.O"],  # 美股代码, 支持单值或列表
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   category=<分类ID>  美股公告类型, 见 constant_list(category="usShareAnnouncementCategory")


if __name__ == "__main__":
    asyncio.run(main())
