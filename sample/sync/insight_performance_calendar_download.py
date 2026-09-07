"""insight.performance_calendar_download — 下载业绩报告原文 PDF。

流程: 先用 insight.performance_calendar_list 拿到 performanceReportId, 再下载。
**A股 10 积分 / 港美股 20 积分**; 仅 hasAttachment=True 的记录可下。
省略 output 时用 title-cache 里的真实标题命名。
异步用法相同, 路径为 gangtise.async_.insight.performance_calendar_download(...)。
"""

from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 步骤 1 · 先取一条可下载的记录（list 免费）
    items = gangtise.insight.performance_calendar_list(
        start_date="2026-07-01", end_date="2026-07-07", size=1
    )
    if items.empty:
        raise SystemExit("No source item found for insight.performance_calendar_download.")
    item_id = items.iloc[0].get("performanceReportId")
    if not item_id:
        raise SystemExit("Could not find a performanceReportId column in the list response.")

    # 步骤 2 · chdir 到 sample_downloads 后下载, 结束再 chdir 回去
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.insight.performance_calendar_download(
            performance_report_id=item_id,  # 报告唯一标识（必填）
            # output=None,                  # 显式落盘路径; 省略则自动命名
            # resolve_title=True,  # 标题缓存未命中时回查 list 接口取文件名; 多发 4 次请求, 这些 list 多数按条计费
        )
    finally:
        os.chdir(previous_cwd)

    show_result(result, __file__)


if __name__ == "__main__":
    main()
