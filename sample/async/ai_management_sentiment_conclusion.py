"""ai.management_sentiment_conclusion — 管理层情绪结论（较上一场的变化, 分页, 单页 100, 返回 DataFrame）。

🔴 5 积分/条, 务必带 size; 不传 security 即全部证券。返回的 publishTime 是北京时间。
通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.ai.management_sentiment_conclusion(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最近一场的结论文本与三维情绪信号
    show_result(
        await gangtise.async_.ai.management_sentiment_conclusion(
            security="300285.SZ",  # 证券代码, 单值或列表; 不传 = 全部证券
            size=1,  # 返回条数(5 积分/条)
        ),
        __file__,
    )

    # 示例 2 · 原始返回: qaSentimentContrast 是与上一场同一事项的问答对照,
    # 没有可比的上一场时为 [], previousSource 为 None
    show_result(
        await gangtise.async_.ai.management_sentiment_conclusion(
            security="300285.SZ",
            start_time="2026-08-01 00:00:00",
            size=3,
            raw=True,
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
