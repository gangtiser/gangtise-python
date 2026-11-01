"""vault.stock_note_delete — 批量删除个股投资笔记（免费, 写操作, 不可恢复）。

删除整条笔记连同它与全部证券的关联, 必须传 confirm=True, 否则在发请求前抛 ValidationError。
返回 {successList, failList}; 已删掉、不存在或不属于本人的 ID 都算成功。
异步用法相同, 路径为 gangtise.async_.vault.stock_note_delete(...)。

本示例会删除数据: 先用 vault.stock_note_list(note_id=...) 核对内容, 再把 NOTE_IDS 填好后运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 要删除的笔记 ID 列表, 取自 vault.stock_note_list(); 留空则不发请求。
NOTE_IDS: list[str] = []


def main():
    if not NOTE_IDS:
        raise SystemExit("请先填好 NOTE_IDS——本示例会删除真实的笔记。")
    result = gangtise.vault.stock_note_delete(
        note_id=NOTE_IDS,  # 笔记 ID（必填）, 支持单值或列表, 一次最多 100 个
        confirm=True,  # 必须显式确认; 不传则在发请求前抛 ValidationError
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
