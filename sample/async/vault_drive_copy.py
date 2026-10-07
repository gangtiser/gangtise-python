"""vault.drive_copy — 把云盘文件或整个文件夹复制到另一空间: 我的云盘 ↔ 租户云盘（免费, 写操作）。

两种用法二选一: file_id + target_folder_id 复制文件, 返回 {successList[]{fileId, newFileId}, failList};
folder_id + target_parent_id 连同子文件夹与文件复制整个文件夹, 返回 {folderId, newFolderId}。
源不动。目标必须在另一空间（同空间报 100003）。云盘允许同名, 每复制一次就多一份, 且该端点
超时不自动重发。异步用法相同, 路径为 gangtise.async_.vault.drive_copy(...)。

本示例会改动账号数据: 把 FILE_IDS 或 FOLDER_ID 填好后再运行。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise

# 二选一填好, 都留空则不发请求。
# 复制文件: 源文件 ID（例如我的云盘里的文件）
FILE_IDS: list[str] = []
# 复制文件夹: 源文件夹 ID, 取自 vault.drive_folder_list()
FOLDER_ID = ""


async def main():
    if FILE_IDS:
        # 示例 1 · 复制文件
        result = await gangtise.async_.vault.drive_copy(
            file_id=FILE_IDS,  # 源文件 ID, 支持单值或列表; 与 target_folder_id 成对传
            target_folder_id="root",  # 另一空间里的目标文件夹 ID; "root" 即另一空间的根目录
        )
    elif FOLDER_ID:
        # 示例 2 · 复制整个文件夹（连同其中的子文件夹与文件）
        result = await gangtise.async_.vault.drive_copy(
            folder_id=FOLDER_ID,  # 源文件夹 ID; 与 target_parent_id 成对传
            target_parent_id="root",  # 另一空间里的目标父文件夹 ID; "root" 即另一空间的根目录
        )
    else:
        raise SystemExit("请先填好 FILE_IDS 或 FOLDER_ID——本示例会复制云盘里真实的文件或文件夹。")
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
