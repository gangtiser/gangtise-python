"""vault.drive_folder_list — 列出云盘某文件夹的直接子文件夹与文件（免费, 只读）。

返回 {folderTotal, folderList, fileTotal, fileList}, 不递归。space_type: 1=我的云盘（默认）,
2=租户云盘; parent_id 不传（或 "root"）即该空间根目录, 属于另一空间报 100003。
异步用法相同, 路径为 gangtise.async_.vault.drive_folder_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 我的云盘根目录
    root = await gangtise.async_.vault.drive_folder_list()
    show_result(root, __file__)

    # 示例 2 · 租户云盘根目录（显式写 root）
    show_result(
        await gangtise.async_.vault.drive_folder_list(
            space_type=2,  # 空间: 1=我的云盘, 2=租户云盘
            parent_id="root",  # 文件夹 ID; 不传或 "root" 即根目录
            raw=True,  # 返回的本就是原始 dict, raw 仅为签名统一
        ),
        __file__,
    )

    # 示例 3 · 进入第一个子文件夹（ID 必须属于同一空间）
    folders = root.get("folderList") or []
    if folders:
        show_result(
            await gangtise.async_.vault.drive_folder_list(
                space_type=1, parent_id=folders[0]["folderId"]
            ),
            __file__,
        )


if __name__ == "__main__":
    asyncio.run(main())
