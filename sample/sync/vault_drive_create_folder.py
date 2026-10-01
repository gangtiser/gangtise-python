"""vault.drive_create_folder — 新建云盘文件夹（免费, 写操作）。

返回 {folderId, parentId, folderName, spaceType, createTime}。名称 ≤200 个字符（超出 230004）;
同名允许, 每执行一次就多建一个, 且该端点超时不自动重发。
异步用法相同, 路径为 gangtise.async_.vault.drive_create_folder(...)。

本示例会改动账号数据: 把 FOLDER_NAME 填好后再运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 新文件夹名; 留空则不发请求。
FOLDER_NAME = ""


def main():
    if not FOLDER_NAME:
        raise SystemExit("请先填好 FOLDER_NAME——本示例会在云盘里创建真实的文件夹。")
    result = gangtise.vault.drive_create_folder(
        name=FOLDER_NAME,  # 文件夹名（必填）, ≤200 个字符
        space_type=1,  # 空间: 1=我的云盘（默认）, 2=租户云盘
        parent_id="root",  # 父文件夹 ID; 不传或 "root" 即根目录
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
