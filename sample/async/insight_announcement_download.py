"""insight.announcement_download — 下载 A 股公告（PDF/Markdown, 返回本地文件路径）。

流程: 先用 insight.announcement_list 取 1 条拿到 announcementId, 再下载该公告。
download 类接口需要真实 ID, 故不另加示例调用; 全部参数（含 file_type 枚举）见下方注释。
异步用法相同, 路径为 gangtise.async_.insight.announcement_download(...)。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 步骤 1 · 先取列表拿到一个可下载的 announcementId
    items = await gangtise.async_.insight.announcement_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for insight.announcement_download.")
    row = items.iloc[0]
    item_id = row.get("announcementId") or row.get("id")
    if not item_id:
        raise SystemExit("Could not find an ID column in the list response.")

    # 步骤 2 · chdir 到 sample_downloads 后下载, 结束再 chdir 回去
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = await gangtise.async_.insight.announcement_download(
            announcement_id=item_id,  # 公告 ID（必填）, 取自 insight.announcement_list 的 announcementId 列
            file_type=1,  # 文件类型: 1=PDF（默认） 2=Markdown
            # output=None,            # 显式落盘路径; 省略则按标题/响应头自动命名
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
