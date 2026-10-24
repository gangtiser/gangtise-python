"""ai.management_sentiment_detail — 一场业绩会的逐条问答评分与判断依据（返回 DataFrame）。

10 积分/次, 超时 / 5xx 不自动重发。source_id 取自评分 / 结论列表返回行的 source.sourceId。
通过几组示例演示常用参数；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.ai.management_sentiment_detail(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 先取最近一场的 source(5 积分), 再取这一场的全部问答
    latest = await gangtise.async_.ai.management_sentiment_indicator(
        security="300285.SZ", size=1, raw=True
    )
    rows = latest.get("list") or []
    if not rows:
        print("该证券在数据范围内没有业绩会情绪数据")
        return
    source = rows[0]["source"]

    # 示例 1 · 每条问答的三维档位(5.0 / 2.5 / 0.0)与依据(*Quote 原文节选、*Reason 判断理由)
    show_result(
        await gangtise.async_.ai.management_sentiment_detail(
            source_id=source["sourceId"],  # 写错不报错、返回空结果
            source_type=source["sourceType"],  # 默认 conference(电话会议)
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
