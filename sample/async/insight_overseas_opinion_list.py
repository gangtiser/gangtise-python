"""insight.overseas_opinion_list — 海外观点列表（分页, 端点最大页 50, 返回 DataFrame）。

海外媒体、投资人、分析师等账号发布的帖子, 每条附中文翻译。列表只含摘要 brief / briefTranslate
（0.1 积分/条）; 全文用 insight.overseas_opinion_detail 按 overseasOpinionId 取（10 积分/条）。
最多取到前 10000 条, 命中更多时标 partial, 按时间段分批取。
通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.insight.overseas_opinion_list(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取最近 5 条, 时间倒序
    show_result(await gangtise.async_.insight.overseas_opinion_list(size=5, rank_type=2), __file__)

    # 示例 2 · 常用过滤: 证券 + 类别 + 地区 + 时间窗
    show_result(
        await gangtise.async_.insight.overseas_opinion_list(
            security="NVDA.O",  # 带市场后缀的证券代码; 后缀市场不对（NVDA.N）返回空结果、不报错
            # 类别 opinion / news / dataAnalysis / promotion, 传多个取并集
            category=["opinion", "dataAnalysis"],
            region="us",  # cn / cnHk / cnTw / us / jp / kr / uk / gl
            start_time="2026-11-01",  # 发布时间起点; 早于账号可查下界整段报 110003
            end_time="2026-11-14",  # 发布时间终点
            original_flag=1,  # 1=只要原创 0=只要转发; 不传两者都返回
            size=10,  # 按条计费（0.1 积分/条）
        ),
        __file__,
    )

    # 示例 3 · 按账号 + GICS 行业筛, 原始返回
    accounts = await gangtise.async_.reference.overseas_account_search(
        keyword="bloomberg", size=1, raw=True
    )
    show_result(
        await gangtise.async_.insight.overseas_opinion_list(
            account=[row["accountId"] for row in accounts["list"]],  # 账号 ID, 支持单值或列表
            industry=107700008,  # GICS 一级行业 ID（107700008 信息技术）; 申万 / 中信码报 100005
            keyword="AI",  # 关键词
            size=5,
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
