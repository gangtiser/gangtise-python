"""vault.my_conference_download — 下载会议资源（返回保存后的 Path）。

先用 vault.my_conference_list 取 1 条拿到 conferenceId, 再下载; 文件名按标题/响应头/fallback 解析。
异步用法相同, 路径为 gangtise.async_.vault.my_conference_download(...)。
"""

from __future__ import annotations

import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    items = gangtise.vault.my_conference_list(size=1)
    if items.empty:
        raise SystemExit("No source item found for vault.my_conference_download.")
    row = items.iloc[0]
    item_id = row.get("conferenceId") or row.get("id") or row.get("id")
    if not item_id:
        raise SystemExit("Could not find an ID column in the list response.")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = gangtise.vault.my_conference_download(
            conference_id=item_id,  # 会议 ID（必填）, 取自 vault.my_conference_list
            content_type="summary",  # 内容类型（必填）: asr=语音转写, summary=纪要
            # output=Path("sample_downloads/conference.md"),  # 可选: 显式保存路径; 省略则自动命名
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    main()
