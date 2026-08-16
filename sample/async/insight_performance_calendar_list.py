"""insight.performance_calendar_list — 财报日历: 业绩预告 / 快报 / 公告（返回 DataFrame）。

它是唯一按 start_date / end_date（过滤 publishDate）筛选的 insight 列表, 其余用 start_time;
也没有 keyword / rank_type / search_type。
⚠️ 本接口数据量很大（含未来排期）, 省略 size 等于按分页上限拉满（1000 页 × 50 = 5 万条,
约 5000 积分）, 因此
**至少要给一个约束**: 完整日期区间 / security / 显式 size, 否则本地报错且不发请求。
只给 security 时另加 1000 行隐式上限, 撞上且仍有剩余会标 partial 并发 warning。
异步路径为 gangtise.async_.insight.performance_calendar_list(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 按日期区间取一段财报日历
    show_result(
        await gangtise.async_.insight.performance_calendar_list(
            start_date="2026-07-01",  # 起始日 YYYY-MM-DD, 过滤 publishDate
            end_date="2026-07-07",  # 结束日 YYYY-MM-DD
            size=5,  # 返回条数; 有完整日期区间时可省略
        ),
        __file__,
    )

    # 示例 2 · 全部筛选项
    show_result(
        await gangtise.async_.insight.performance_calendar_list(
            from_=0,  # 起始偏移, 默认 0
            size=5,
            start_date="2026-01-01",
            end_date="2026-08-01",
            security="600519.SH",  # 证券代码, 支持单值或列表
            market="aShares",  # aShares / hkStocks / usChinaConcept / usStocks
            category="performanceForecast",  # performanceForecast / performanceExpress
            # / performanceAnnouncement——本地白名单, 拼错直接报错
        ),
        __file__,
    )

    # 示例 3 · 只按 security 约束（走 1000 行隐式上限）+ 原始返回
    show_result(
        await gangtise.async_.insight.performance_calendar_list(
            security="600519.SH",
            raw=True,  # True=返回服务端原始 data（含 total/list/partial）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
