"""vault.stock_note_add — 新增个股投资笔记（免费, 写操作）, 返回 {stockNoteId, securityList}。

一条笔记关联 1~50 只证券, 建好后不能改关联; 正文为纯文本, 最长 10000 个字符。
服务端没有防重机制: 该端点超时 / 5xx 不自动重发, 重跑前先 vault.stock_note_list() 看是否已写入。
异步用法相同, 路径为 gangtise.async_.vault.stock_note_add(...)。

本示例会改动账号数据: 把 CONTENT 填好后再运行。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise

# 要写入的笔记正文; 留空则不发请求。
CONTENT = ""


async def main():
    if not CONTENT:
        raise SystemExit("请先填好 CONTENT——本示例会新建一条真实的笔记。")
    result = await gangtise.async_.vault.stock_note_add(
        security=["600519.SH", "000858.SZ"],  # 关联证券（必填）, 1~50 只; .SWI 申万行业指数不支持
        content=CONTENT,  # 正文（必填）, 纯文本, 保留换行
    )
    show_result(result, __file__)  # {stockNoteId, securityList}


if __name__ == "__main__":
    asyncio.run(main())
