"""insight.independent_opinion_download — 下载独立第三方观点（HTML, 原文/中译）。

流程: 先用 insight.independent_opinion_list 取 1 条拿到 independentOpinionId, 再下载。
注意: file_type 为必填（TS 端 requiredOption, 无默认值）。
download 类接口需要真实 ID, 故不另加示例调用; 全部参数（含 file_type 枚举）见下方注释。
异步用法相同, 路径为 gangtise.async_.insight.independent_opinion_download(...)。
"""

from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 步骤 1 · 先取列表拿到一个可下载的 independentOpinionId
    items = gangtise.insight.independent_opinion_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for insight.independent_opinion_download.")
    row = items.iloc[0]
    item_id = row.get("independentOpinionId") or row.get("id")
    if not item_id:
        raise SystemExit("Could not find an ID column in the list response.")

    # 步骤 2 · chdir 到 sample_downloads 后下载, 结束再 chdir 回去
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.insight.independent_opinion_download(
            independent_opinion_id=item_id,  # 观点 ID（必填）, 取自列表的 independentOpinionId 列
            file_type=1,  # 文件类型（必填）: 1=原文HTML 2=中译HTML
            # output=None,                   # 显式落盘路径; 省略则按标题/响应头自动命名
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    main()
