"""insight.official_account_download — 下载产业公众号文章（txt 默认 / HTML）。

流程: 先用 insight.official_account_list 取 1 条拿到 articleId, 再下载。
download 类接口需要真实 ID, 故依赖列表返回; 全部参数（含 file_type 枚举）见下方注释。
异步用法相同, 路径为 gangtise.async_.insight.official_account_download(...)。
"""

from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 步骤 1 · 先取列表拿到一个可下载的 articleId
    items = gangtise.insight.official_account_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for insight.official_account_download.")
    row = items.iloc[0]
    item_id = row.get("articleId") or row.get("id")
    if not item_id:
        raise SystemExit("Could not find an ID column in the list response.")

    # 步骤 2 · chdir 到 sample_downloads 后下载, 结束再 chdir 回去
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.insight.official_account_download(
            article_id=item_id,  # 文章 ID（必填）, 取自列表的 articleId 列
            file_type=1,  # 文件类型: 1=txt（默认） 2=HTML
            # output=None,                   # 显式落盘路径; 省略则按标题/响应头自动命名
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    main()
