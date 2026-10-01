"""vault.drive_copy — 把云盘文件复制到另一空间: 我的云盘 ↔ 租户云盘（免费, 写操作）。

返回 {successList[]{fileId, newFileId}, failList}; 源文件不动。目标必须在另一空间（同空间报
100003）; 只复制文件。云盘允许同名, 每复制一次就多一份, 且该端点超时不自动重发。
异步用法相同, 路径为 gangtise.async_.vault.drive_copy(...)。

本示例会改动账号数据: 把 FILE_IDS 填好后再运行。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise

# 源文件 ID（例如我的云盘里的文件）; 留空则不发请求。
FILE_IDS: list[str] = []


def main():
    if not FILE_IDS:
        raise SystemExit("请先填好 FILE_IDS——本示例会复制云盘里真实的文件。")
    result = gangtise.vault.drive_copy(
        file_id=FILE_IDS,  # 源文件 ID（必填）, 支持单值或列表
        target_folder_id="root",  # 另一空间里的目标文件夹 ID（必填）; "root" 即另一空间的根目录
    )
    show_result(result, __file__)


if __name__ == "__main__":
    main()
