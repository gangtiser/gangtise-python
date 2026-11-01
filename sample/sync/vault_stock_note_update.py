"""vault.stock_note_update — 改写个股投资笔记的正文（免费, 写操作）, 成功返回 {}。

content 整体替换旧正文（不是追加）; 关联证券不变。不存在或不属于本人报 130002。
异步用法相同, 路径为 gangtise.async_.vault.stock_note_update(...)。

本示例会改动账号数据: 先用 vault.stock_note_list() 拿到 NOTE_ID, 填好 NOTE_ID 与 CONTENT 后再运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 要改写的笔记 ID 与新正文; 任一留空则不发请求。
NOTE_ID = ""
CONTENT = ""


def main():
    if not NOTE_ID or not CONTENT:
        raise SystemExit("请先填好 NOTE_ID 与 CONTENT——本示例会改写一条真实的笔记。")
    result = gangtise.vault.stock_note_update(
        note_id=NOTE_ID,  # 笔记 ID（必填）, 取自 vault.stock_note_list
        content=CONTENT,  # 新正文（必填）, 整体替换
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
