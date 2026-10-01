"""vault.drive_upload — 上传文件到 AI 云盘（免费, 写操作）, 返回 {fileId, title, folderId, spaceType, fileSize}。

单个文件 ≤100MB（本地先拦）; 试用账号每天累计 ≤500MB（超出 230008）。名称 ≤200 个字符,
按 UTF-16 计（emoji 算 2）, 本地先拦。云盘允许同名, 每上传一次就多一份, 且该端点超时不自动重发。
异步用法相同, 路径为 gangtise.async_.vault.drive_upload(...)。

运行前把 SOURCE_FILE 设成要上传的真实文件; 不设（None）时不发请求——这是写操作,
不能靠「默认路径恰好不存在」来拦（sample_downloads/ 会被其他示例写入文件）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise

# 设成你要上传的文件路径后再运行, 例如 Path("~/Documents/年报.pdf").expanduser()。
SOURCE_FILE: Path | None = None


async def main():
    if SOURCE_FILE is None:
        raise SystemExit("请先填好 SOURCE_FILE——本示例会上传真实的文件。")
    result = await gangtise.async_.vault.drive_upload(
        file=SOURCE_FILE,  # 本地文件路径（必填）, 非空、≤100MB
        space_type=1,  # 目标空间: 1=我的云盘（默认）, 2=租户云盘（对整个租户可见）
        folder_id="root",  # 目标文件夹 ID; 不传或 "root" 即根目录
        title="示例文档.pdf",  # 云盘里的名称; 不传用本地文件名
    )
    show_result(result, __file__)  # fileId 供重命名 / 移动 / 删除使用


if __name__ == "__main__":
    asyncio.run(main())
