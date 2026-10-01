"""insight.opinion_list — 国内机构首席观点列表（分页, 端点最大页 50, 返回 DataFrame）。

通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步用法相同, 路径为 gangtise.async_.insight.opinion_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条（默认只含摘要 brief, 1 积分/条）
    show_result(gangtise.insight.opinion_list(size=5), __file__)

    # 示例 2 · 常用过滤: 关键词 + 时间窗 + 行业, 指定排序
    show_result(
        gangtise.insight.opinion_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-09-01",  # 起始时间（观点可回溯约 3 个月）
            end_time="2026-09-28",  # 结束时间
            keyword="平安银行",  # 关键词
            rank_type=1,  # 排序: 1=综合 2=时间倒序
            industry=100800110,  # 中信行业码 1008001xx（100800110=机械）; 申万码 104xx0000 也生效但结果集不同, 别混用
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        gangtise.insight.opinion_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            size=20,  # 按条计费（1 积分/条）: 带 size 取一部分; 要全量改传 confirm=True
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )

    # 示例 4 · 列表直接带正文（旧版结构, 30 积分/条）: 标题与正文在 contentList.title / contentList.content
    show_result(
        gangtise.insight.opinion_list(
            security="600519.SH",
            size=2,  # 带正文 30 积分/条, 只取需要的条数
            with_content=True,  # True=走旧版列表带正文; 默认 False 只含 200 字摘要 brief（1 积分/条）
        ),
        __file__,
    )
    # 要正文也可以先 list 看摘要, 再用 insight.opinion_detail(chief_opinion_id=...) 按 ID 取（30 积分/条）
    # 其余可选过滤参数（均支持单值或列表, 需传入真实 ID, 故放注释不执行）:
    #   research_area=<研究领域ID>   见 reference.constant_list(category="citicIndustry")
    #   chief=<首席分析师ID>
    #   broker=<券商/机构ID>         见 lookup.broker_orgs
    #   concept=<题材ID>             见 reference.concept_search(keyword=...)（如 机器人=121000130）
    #   llm_tag=<语义标签>           LLM 语义标签过滤


if __name__ == "__main__":
    main()
