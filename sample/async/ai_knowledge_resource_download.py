"""ai.knowledge_resource_download — 下载知识库资源文件（返回保存路径 Path）。

需要真实 sourceId, 通过环境变量 GANGTISE_SAMPLE_KNOWLEDGE_SOURCE_ID 传入;
资源类型默认 1, 可用 GANGTISE_SAMPLE_KNOWLEDGE_RESOURCE_TYPE 覆盖。
先 chdir 到 sample_downloads 再下载, 文件名由标题/响应头/fallback 自动生成。
异步用法相同, 路径为 gangtise.async_.ai.knowledge_resource_download(...)。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    source_id = os.environ.get("GANGTISE_SAMPLE_KNOWLEDGE_SOURCE_ID")
    resource_type = os.environ.get("GANGTISE_SAMPLE_KNOWLEDGE_RESOURCE_TYPE", "1")
    if not source_id:
        raise SystemExit("Set GANGTISE_SAMPLE_KNOWLEDGE_SOURCE_ID to a downloadable sourceId.")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = await gangtise.async_.ai.knowledge_resource_download(
            resource_type=int(resource_type),  # 知识资源类型代码(必填)
            source_id=source_id,  # 知识资源源 ID(必填)
            # output=Path("custom-name.pdf"),  # 可选: 显式保存路径; 省略则自动生成文件名
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
