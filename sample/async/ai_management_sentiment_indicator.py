"""ai.management_sentiment_indicator — 管理层情绪评分（每场业绩会的三维评分, 分页, 单页 100, 返回 DataFrame）。

🔴 5 积分/条, 务必带 size; 不传 security 即全部证券。返回的 publishTime 比北京时间早 8 小时。
通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.ai.management_sentiment_indicator(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 某公司最近几场业绩会的三维评分(0–5)与回避 / 风险 / 低确定度占比(百分数)
    show_result(
        await gangtise.async_.ai.management_sentiment_indicator(
            security="300285.SZ",  # 证券代码, 单值或列表; 只收具体代码, 不传 = 全部证券
            size=5,  # 返回条数(5 积分/条); 省略时按 total 估算, 超过 1000 积分本地拒绝
        ),
        __file__,
    )

    # 示例 2 · 按发布时间(北京时间)筛 + 原始返回(看 source.sourceId 与 questionCategoryList)
    show_result(
        await gangtise.async_.ai.management_sentiment_indicator(
            security=["300285.SZ", "600519.SH"],
            start_time="2026-08-01",  # YYYY-MM-DD / YYYY-MM-DD HH:mm:ss / 时间戳; 写时刻须带秒
            end_time="2026-10-23",  # 只写日期时含当天整天
            size=10,
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
