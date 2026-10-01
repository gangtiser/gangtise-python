"""vault.my_conference_list — 我的会议列表（分页, 端点最大页 50）。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.vault.my_conference_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(await gangtise.async_.vault.my_conference_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 关键词 + 会议分类
    show_result(
        await gangtise.async_.vault.my_conference_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="平安银行",  # 搜索关键词
            # 会议分类: earningsCall=业绩说明会, strategyMeeting=策略会, fundRoadshow=基金路演,
            #   shareholdersMeeting=股东大会, maMeeting=并购会议, specialMeeting=专项会议,
            #   companyAnalysis=公司分析, industryAnalysis=行业分析, other=其他; 支持单值或列表
            category="earningsCall",
        ),
        __file__,
    )

    # 示例 3 · 按证券代码过滤（列表入参）+ 原始返回
    show_result(
        await gangtise.async_.vault.my_conference_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            category=["companyAnalysis", "industryAnalysis"],  # 会议分类, 支持单值或列表
            size=20,  # 按条计费: 省略 size 会按 total × 单价估算全量, 超过 1000 积分拒绝
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   research_area=<研究领域ID>   见 reference.constant_list(category="citicIndustry")
    #   institution=<机构ID>         见 reference.institution_search(keyword=...)
    #   source=1 或 [1, 2]           录制来源: 1=企微会议助理 2=会议服务微信群
    # 按条计费 0.1 积分/条: 省略 size 时按 total × 单价估算, 超过 1000 积分会被拒;
    #   传 size 取一部分, 或 confirm=True 确认全量


if __name__ == "__main__":
    asyncio.run(main())
