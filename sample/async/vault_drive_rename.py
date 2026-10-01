"""vault.drive_rename — 重命名云盘文件或文件夹（免费, 写操作）, 返回 {id, name}。

type_ 取 file / folder（本地校验）; 名称 ≤200 个字符（超出 230004）。
异步用法相同, 路径为 gangtise.async_.vault.drive_rename(...)。

本示例会改动账号数据: 把 TARGET_ID / NEW_NAME 填好后再运行。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise

# 文件 ID 取自 vault.drive_folder_list() 的 fileList 或 vault.drive_list(); 留空则不发请求。
TARGET_ID = ""
NEW_NAME = ""


async def main():
    if not (TARGET_ID and NEW_NAME):
        raise SystemExit("请先填好 TARGET_ID 与 NEW_NAME——本示例会重命名云盘里真实的条目。")
    result = await gangtise.async_.vault.drive_rename(
        type_="file",  # 对象类型（必填）: file / folder
        id_=TARGET_ID,  # 文件或文件夹 ID（必填）
        name=NEW_NAME,  # 新名称（必填）, ≤200 个字符
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
