"""insight.report_image_download — 下载研报图片原图（JPEG, 0.1 积分/张）。

流程: 先用 insight.report_image_list 按关键词搜索拿到 chunkId, 再下载原图。
download 类接口需要真实 ID, 故依赖列表返回; 省略 output 时优先用服务端文件名。
异步用法相同, 路径为 gangtise.async_.insight.report_image_download(...)。
"""

from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 步骤 1 · 先搜索拿到一个可下载的 chunkId（list 免费）
    items = gangtise.insight.report_image_list(keyword="AI", top=1)
    if items.empty:
        raise SystemExit("No source item found for insight.report_image_download.")
    chunk_id = items.iloc[0].get("chunkId")
    if not chunk_id:
        raise SystemExit("Could not find a chunkId column in the list response.")

    # 步骤 2 · chdir 到 sample_downloads 后下载, 结束再 chdir 回去
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.insight.report_image_download(
            chunk_id=chunk_id,  # 图片唯一标识（必填）, 取自列表的 chunkId 列
            # output=None,               # 显式落盘路径; 省略则按服务端文件名/report-image-<chunkId> 自动命名
        )
    finally:
        os.chdir(previous_cwd)

    show_result(result, __file__)


if __name__ == "__main__":
    main()
