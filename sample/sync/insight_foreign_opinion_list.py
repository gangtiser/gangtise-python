"""insight.foreign_opinion_list — 海外机构观点列表（分页, 端点最大页 50, 返回 DataFrame）。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.insight.foreign_opinion_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(gangtise.insight.foreign_opinion_list(size=5), __file__)

    # 示例 2 · 常用过滤: 时间窗 + 关键词 + 美股 + 区域, 时间倒序
    show_result(
        gangtise.insight.foreign_opinion_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-09-01",  # 起始时间（观点可回溯约 3 个月）
            end_time="2026-09-28",  # 结束时间
            keyword="AI",  # 关键词
            rank_type=2,  # 排序: 1=综合 2=时间倒序
            security="UBER.N",  # 证券代码（美股如 UBER.N）, 支持单值或列表
            region="us",  # 区域代码（小写）: cn/cnHk/cnTw/us/jp/uk, 支持单值或列表
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        gangtise.insight.foreign_opinion_list(
            security=["UBER.N"],  # 证券代码, 支持单值或列表
            industry=[104110000],  # 申万行业 ID（104xx0000 形态; 中信码在此报 100005）
            size=20,  # 按条计费（1 积分/条）: 带 size 取一部分; 要全量改传 confirm=True
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )

    # 示例 4 · 列表直接带原文与译文（旧版结构, 30 积分/条）: 顶层 content / contentTranslate, 无 brief
    show_result(
        gangtise.insight.foreign_opinion_list(
            security="UBER.N",
            size=2,  # 带正文 30 积分/条, 只取需要的条数
            with_content=True,  # 默认 False 只含摘要 brief / briefTranslate（1 积分/条）
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表）:
    #   broker=<券商/机构ID>     见 lookup.broker_orgs
    #   rating=<评级名称>        评级名称过滤
    #   rating_change=<评级变动> 评级变动名称过滤


if __name__ == "__main__":
    main()
