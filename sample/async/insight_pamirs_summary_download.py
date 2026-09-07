"""insight.pamirs_summary_download — 下载帕米尔专家纪要原文/HTML。

流程: 先用 insight.pamirs_summary_list 拿到 summaryId, 再下载。
需已开通专家纪要数据库（未开通报 999004）。省略 output 时优先用列表标题/服务端文件名。
异步路径为 gangtise.async_.insight.pamirs_summary_download(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 步骤 1 · 先取一条可下载的记录（list 免费）
    items = await gangtise.async_.insight.pamirs_summary_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for insight.pamirs_summary_download.")
    item_id = items.iloc[0].get("summaryId")
    if not item_id:
        raise SystemExit("Could not find a summaryId column in the list response.")

    # 步骤 2 · chdir 到 sample_downloads 后下载, 结束再 chdir 回去
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = await gangtise.async_.insight.pamirs_summary_download(
            summary_id=item_id,  # 纪要唯一标识（必填）, 取自列表的 summaryId 列
            file_type=1,  # 1=原文（默认） 2=HTML——本地白名单, 其他值直接报错
            # output=None,             # 显式落盘路径; 省略则自动命名
            # resolve_title=True,  # 标题缓存未命中时回查 list 接口取文件名; 多发 4 次请求, 这些 list 多数按条计费
        )
    finally:
        os.chdir(previous_cwd)

    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
