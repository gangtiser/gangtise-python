"""ai.hot_topic — AI 热点主题报告列表（分页, 端点最大页 20, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.ai.hot_topic(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取最近 5 条(默认涵盖早/午/晚四类简报)
    show_result(await gangtise.async_.ai.hot_topic(size=5), __file__)

    # 示例 2 · 指定日期窗 + 单一报告类型, 含关联证券与精读
    show_result(
        await gangtise.async_.ai.hot_topic(
            from_=0,  # 分页起始偏移(映射为请求字段 from)
            size=10,  # 分页大小; 省略则按最大页 20 自动翻页
            start_date="2026-05-01",  # 开始日期 YYYY-MM-DD
            end_date="2026-05-28",  # 结束日期 YYYY-MM-DD
            category="morningBriefing",  # 报告类型: morningBriefing=早报
            with_related_securities=True,  # 是否返回关联证券, 默认 True
            with_close_reading=True,  # 是否返回精读内容, 默认 True
        ),
        __file__,
    )

    # 示例 3 · 多类型过滤(列表入参) + 精简返回(不含关联证券/精读) + 原始返回
    show_result(
        await gangtise.async_.ai.hot_topic(
            size=5,
            # 报告类型, 支持单值或列表:
            #   morningBriefing=早报 / noonBriefing=午报
            #   afternoonFlash=午后快讯 / eveningBriefing=晚报
            category=["morningBriefing", "eveningBriefing"],
            with_related_securities=False,  # False=不返回关联证券
            with_close_reading=False,  # False=不返回精读内容
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
