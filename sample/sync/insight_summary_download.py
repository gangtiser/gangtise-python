"""insight.summary_download — 下载纪要原文 / HTML（返回保存到本地的文件路径）。

流程: 先用 insight.summary_list 取 1 条拿到 summaryId, 再下载该纪要。
download 类接口需要真实 ID, 故不另加示例调用; 全部参数（含 file_type 枚举）见下方注释。
异步用法相同, 路径为 gangtise.async_.insight.summary_download(...)。
"""

from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 步骤 1 · 先取列表拿到一个可下载的 summaryId
    items = gangtise.insight.summary_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for insight.summary_download.")
    row = items.iloc[0]
    item_id = row.get("summaryId") or row.get("id")
    if not item_id:
        raise SystemExit("Could not find an ID column in the list response.")

    # 步骤 2 · chdir 到 sample_downloads 后下载, 结束再 chdir 回去
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.insight.summary_download(
            summary_id=item_id,  # 纪要 ID（必填）, 取自 insight.summary_list 的 summaryId 列
            # file_type 省略 → 服务端默认 1（原文）; 详见下方注释
            # output=None,       # 显式落盘路径; 省略则按标题/响应头自动命名
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)
    # 其余可选参数（用注释覆盖, 不另起执行调用以免重复落盘）:
    #   file_type=1  文件类型: 1=原文（默认） 2=HTML; 仅对会议平台纪要生效
    #   output="<本地路径>"  指定保存路径; 省略时优先用标题缓存 → 响应头 → 兜底名


if __name__ == "__main__":
    main()
