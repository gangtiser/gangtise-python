"""insight.research_download — 下载国内券商研报 PDF / Markdown（返回本地文件路径）。

流程: 先用 insight.research_list 取若干条, 逐条尝试下载首个可下载的研报。
download 类接口需要真实 ID, 故不另加示例调用; 全部参数（含 file_type 枚举）见下方注释。
异步用法相同, 路径为 gangtise.async_.insight.research_download(...)。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import DownloadError, gangtise


async def main():
    # 步骤 1 · 取列表（多取几条以便跳过无附件的研报）
    items = await gangtise.async_.insight.research_list(size=10)
    if items.empty:
        raise SystemExit("No source item found for insight.research_download.")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    last_error = None

    # 步骤 2 · 逐条尝试下载, 命中首个可下载的即返回
    for _, row in items.iterrows():
        item_id = row.get("reportId") or row.get("id")
        if not item_id:
            continue
        try:
            os.chdir(output_dir)
            result = await gangtise.async_.insight.research_download(
                report_id=item_id,  # 研报 ID（必填）, 取自 insight.research_list 的 reportId 列
                file_type=1,  # 文件类型: 1=PDF（默认） 2=Markdown
                # output=None,      # 显式落盘路径; 省略则按标题/响应头自动命名
            )
        except DownloadError as exc:
            last_error = exc
            continue
        finally:
            os.chdir(previous_cwd)
        show_result(result, __file__)
        return
    raise SystemExit(f"No downloadable research report found. Last error: {last_error}")


if __name__ == "__main__":
    asyncio.run(main())
