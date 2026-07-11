"""insight.report_image_list — 按关键词搜索研报图片（返回 DataFrame）。

返回 chunkId + 元数据（标题/券商/页码/图注/OCR 文本）, chunkId 供 report_image_download 下载原图; 免费。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.insight.report_image_list(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 按关键词搜索
    show_result(
        await gangtise.async_.insight.report_image_list(
            keyword="AI",  # 搜索关键词（必填）, 如 "AI" "新能源汽车"
        ),
        __file__,
    )

    # 示例 2 · 控制条数 + 限定研报与发布时间
    show_result(
        await gangtise.async_.insight.report_image_list(
            keyword="新能源汽车",
            top=20,  # 最大返回数, 默认 10, 上限 20（超限本地报错; 服务端会静默截断）
            # source_id="<研报ID>",         # 限定到某篇研报（可从研报列表或知识库取）
            start_time="2026-01-01",  # 限定图片所属研报的发布时间, yyyy-MM-dd 自动补全
            end_time="2026-07-01 23:59:59",
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        await gangtise.async_.insight.report_image_list(
            keyword="半导体",
            top=5,
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
