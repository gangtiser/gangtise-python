"""vault.drive_move_folder — 把云盘文件夹移到同一空间的另一文件夹下（免费, 写操作）。

返回 {folderId, parentId}; 移到另一空间、自身或其子文件夹报 230005, 跨空间用 drive_copy。
异步用法相同, 路径为 gangtise.async_.vault.drive_move_folder(...)。

本示例会改动账号数据: 把 FOLDER_ID 填好后再运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 文件夹 ID 取自 vault.drive_folder_list(); 留空则不发请求。
FOLDER_ID = ""


def main():
    if not FOLDER_ID:
        raise SystemExit("请先填好 FOLDER_ID——本示例会移动云盘里真实的文件夹。")
    result = gangtise.vault.drive_move_folder(
        folder_id=FOLDER_ID,  # 要移动的文件夹 ID（必填）
        target_parent_id="root",  # 目标父文件夹 ID（必填）, 同一空间; "root" 即根目录
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
