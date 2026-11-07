"""vault.wechat_message_download — 下载微信群消息里的文件（免费, 返回保存后的 Path）。

先用 vault.wechat_message_list 取 1 条文件消息拿到 msgId, 再下载; 只有 document / image /
audio / video 消息有文件。文件名按服务端给的文件名, 内容原样落盘(文本类文件也不转码)。
异步用法相同, 路径为 gangtise.async_.vault.wechat_message_download(...)。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    items = await gangtise.async_.vault.wechat_message_list(category=["document", "image"], size=1)
    if items.empty:
        raise SystemExit("没有找到可用于 vault.wechat_message_download 的文件消息。")
    msg_id = items.iloc[0].get("msgId")
    if not msg_id:
        raise SystemExit("列表返回里找不到 msgId 列。")
    previous_cwd = Path.cwd()
    output_dir = (previous_cwd / "sample_downloads").resolve()
    output_dir.mkdir(exist_ok=True)
    try:
        os.chdir(output_dir)
        result = await gangtise.async_.vault.wechat_message_download(
            msg_id=str(msg_id),  # 消息 ID（必填）, 取自 wechat_message_list 的 msgId, 按字符串传
            # output=Path("sample_downloads/file.pdf"),  # 可选: 显式保存路径; 省略则按服务端文件名
        )
    finally:
        os.chdir(previous_cwd)
    show_result(result, __file__)


if __name__ == "__main__":
    asyncio.run(main())
