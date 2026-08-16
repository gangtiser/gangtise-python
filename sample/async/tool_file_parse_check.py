"""tool.file_parse_check — 取 PDF 解析结果 ZIP（含 file.md + images/）。

免费。结果未就绪时服务端返回「生成中」码（140001 / 旧 410110）——
wait=False（默认）直接抛 ApiError, wait=True 则按与 AI 异步接口相同的退避预算
（约 316 秒, 覆盖官方约 3 分钟）轮询到就绪。
异步路径为 gangtise.async_.tool.file_parse_check(...)（同步用法见 sample/sync 同名文件）。

运行前把 TASK_ID 换成 tool.file_parse 返回的真实 task_id。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise

# 换成 tool.file_parse 返回的 task_id 后再运行。
TASK_ID = ""


async def main():
    if not TASK_ID:
        raise SystemExit("Set TASK_ID to a task_id returned by tool.file_parse first.")

    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = await gangtise.async_.tool.file_parse_check(
            task_id=TASK_ID,  # tool.file_parse 返回的任务号（必填）
            wait=True,  # True=轮询到就绪; False（默认）未就绪直接抛 ApiError
            # output=None,        # 显式落盘路径; 省略则按服务端文件名/file-parse-<taskId> 命名
        )
    finally:
        os.chdir(previous_cwd)

    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
