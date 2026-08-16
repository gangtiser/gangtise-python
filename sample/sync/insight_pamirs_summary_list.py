"""insight.pamirs_summary_list — 帕米尔专家纪要列表（返回 DataFrame）。

这是一个**独立的专家纪要库**, 不是 summary_list 的筛选项, 需单独购买专家纪要数据库
（未开通报 999004）, 且不受历史数据范围限制。筛选项是 summary_list 的真子集:
没有 source / institution / participant_role。
⚠️ 已知返回口径: conceptList 在所有查法下都是空的; categoryList / marketList 只在用
category 或 market 过滤时才回填——按这两个维度分组要靠过滤参数取, 别拉全量再本地分组。
异步用法相同, 路径为 gangtise.async_.insight.pamirs_summary_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 按关键词搜索
    show_result(
        gangtise.insight.pamirs_summary_list(
            keyword="PCB",  # 搜索词
            size=5,  # 返回条数; 省略则自动翻页拉全量
        ),
        __file__,
    )

    # 示例 2 · 全部筛选项
    show_result(
        gangtise.insight.pamirs_summary_list(
            from_=0,  # 起始偏移, 默认 0
            size=5,
            start_time="2026-01-01",  # 起始时间 YYYY-MM-DD[ HH:mm:ss] 或 10/13 位时间戳
            end_time="2026-08-01",
            keyword="半导体",
            search_type=1,  # 1=标题（默认） 2=全文——传其他值本地报错（服务端会静默返全库）
            rank_type=1,  # 1=综合（默认） 2=时间倒序
            research_area="100800119",  # 行业码: 中信 1008001xx / 申万 104xx0000 都认;
            # 方向码 122000xxx 在本端点返 0
            security="600519.SH",  # 证券代码, 支持单值或列表
            category="companyAnalysis",  # companyAnalysis / industryAnalysis
            market=["aShares", "hkStocks"],  # aShares / hkStocks / usChinaConcept / usStocks
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.insight.pamirs_summary_list(
            size=2,
            raw=True,  # True=返回服务端原始 data（含 total/list）, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
