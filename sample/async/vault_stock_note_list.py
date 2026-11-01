"""vault.stock_note_list — 本人的个股投资笔记（免费, 自动翻页, 返回 DataFrame）。

security 与 note_id 二选一, 都不传 = 本人全部笔记; 按 createTime 倒序。
返回 stockNoteId / securityList（该笔记完整的关联证券）/ content / createTime / updateTime。
异步用法相同, 路径为 gangtise.async_.vault.stock_note_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 本人最近 20 条笔记
    notes = await gangtise.async_.vault.stock_note_list(
        from_=0,  # 分页起始偏移（映射为请求字段 from）
        size=20,  # 省略则拉取全部
    )
    show_result(notes, __file__)

    # 示例 2 · 按证券筛: 笔记关联的证券含其中任一只即命中
    show_result(
        await gangtise.async_.vault.stock_note_list(
            security=["600519.SH", "00700.HK"],  # 港股要 5 位, 美股用 .O / .N; 写错整次报 120001
        ),
        __file__,
    )

    # 示例 3 · 按笔记 ID 精确查 + 原始返回（ID 取自示例 1 的 stockNoteId）
    if notes.empty:
        return
    show_result(
        await gangtise.async_.vault.stock_note_list(
            note_id=notes["stockNoteId"].tolist()[:2],  # 不存在或不属于本人的 ID 被直接过滤、不报错
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
