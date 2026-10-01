"""vault.drive_move_file — 把云盘文件移到同一空间的文件夹（免费, 写操作）。

返回 {successList, failList}; 另一空间的文件进 failList（「空间不一致」）, 跨空间用 drive_copy。
failList 非空时 SDK 发 UserWarning 并给结果标 partial=True。
异步用法相同, 路径为 gangtise.async_.vault.drive_move_file(...)。

本示例会改动账号数据: 把 FILE_IDS 填好后再运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 文件 ID 取自 vault.drive_folder_list() 的 fileList 或 vault.drive_list(); 留空则不发请求。
FILE_IDS: list[str] = []


def main():
    if not FILE_IDS:
        raise SystemExit("请先填好 FILE_IDS——本示例会移动云盘里真实的文件。")
    result = gangtise.vault.drive_move_file(
        file_id=FILE_IDS,  # 文件 ID（必填）, 支持单值或列表
        target_folder_id="root",  # 目标文件夹 ID（必填）, 同一空间; "root" 即根目录
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
