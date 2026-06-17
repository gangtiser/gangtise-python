"""insight.official_account_list — 产业公众号资讯列表（分页, 端点最大页 50, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.official_account_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(gangtise.insight.official_account_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 全文关键词 + 证券 + 文章类型 + 行业, 时间倒序
    show_result(
        gangtise.insight.official_account_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="泡泡玛特",  # 关键词（需用数据中的具体词, 不能用整句白话）
            search_type=2,  # 搜索方式: 1=标题（默认） 2=全文
            rank_type=2,  # 排序: 1=综合 2=时间倒序
            security="000001.SZ",  # 证券代码, 支持单值或列表
            category="report",  # 文章类型, 支持单值或列表（枚举见文末注释）
            industry=1,  # 中信/申万行业 ID, 支持单值或列表（见 reference.constant_list(category="citicIndustry")）
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        gangtise.insight.official_account_list(
            category=["news", "report"],  # 文章类型多选（枚举见文末注释）
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   account_id=<公众号ID>   公众号 ID 过滤, 取自列表返回的 accountId 列
    # category 文章类型枚举（可多选）:
    #   news 新闻资讯 | law 法律法规 | report 报告类 | view 个人观点 | data 产业数据
    #   event 日程活动 | meeting 会议纪要 | notice 通知 | recruit 招聘 | investEdu 投资科普
    #   brand 品牌宣传 | notes 个人随笔 | other 其他


if __name__ == "__main__":
    main()
