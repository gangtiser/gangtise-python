"""vault.drive_delete_file — 删除云盘文件（免费, 写操作, 不可恢复）。

必须传 confirm=True, 否则在发请求前抛 ValidationError。返回 {successList, failList};
单条失败（如「文件不存在」）进 failList, SDK 发 UserWarning 并给结果标 partial=True。
异步用法相同, 路径为 gangtise.async_.vault.drive_delete_file(...)。

本示例会删除数据: 先用 vault.drive_folder_list() 核对文件名, 再把 FILE_IDS 填好后运行。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise

# 要删除的文件 ID; 留空则不发请求。
FILE_IDS: list[str] = []


async def main():
    if not FILE_IDS:
        raise SystemExit("请先填好 FILE_IDS——本示例会删除云盘里真实的文件。")
    result = await gangtise.async_.vault.drive_delete_file(
        file_id=FILE_IDS,  # 文件 ID（必填）, 支持单值或列表
        confirm=True,  # 必须显式确认; 不传则在发请求前抛 ValidationError
    )
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
