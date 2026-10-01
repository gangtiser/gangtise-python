"""vault.drive_delete_folder — 删除云盘文件夹及其中全部内容（免费, 写操作, 不可恢复）。

连同全部子文件夹与文件一起删除; 必须传 confirm=True, 否则在发请求前抛 ValidationError。
返回 {folderId}。
异步用法相同, 路径为 gangtise.async_.vault.drive_delete_folder(...)。

本示例会删除数据: 先用 vault.drive_folder_list(parent_id=...) 看清里面有什么, 再把 FOLDER_ID 填好后运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 要删除的文件夹 ID; 留空则不发请求。
FOLDER_ID = ""


def main():
    if not FOLDER_ID:
        raise SystemExit("请先填好 FOLDER_ID——本示例会删除云盘里真实的文件夹。")
    result = gangtise.vault.drive_delete_folder(
        folder_id=FOLDER_ID,  # 文件夹 ID（必填）
        confirm=True,  # 必须显式确认; 不传则在发请求前抛 ValidationError
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
