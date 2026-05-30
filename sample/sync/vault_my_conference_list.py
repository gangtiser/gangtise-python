"""vault.my_conference_list — 我的会议列表（分页, 端点最大页 50）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.vault.my_conference_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(gangtise.vault.my_conference_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 关键词 + 会议分类
    show_result(
        gangtise.vault.my_conference_list(
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
        gangtise.vault.my_conference_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            category=["companyAnalysis", "industryAnalysis"],  # 会议分类, 支持单值或列表
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表, 需传入真实 ID）:
    #   research_area=<研究领域ID>   见 lookup.research_areas
    #   institution=<机构ID>         见 lookup.broker_orgs


if __name__ == "__main__":
    main()
