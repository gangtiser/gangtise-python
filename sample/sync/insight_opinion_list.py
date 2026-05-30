"""insight.opinion_list — 国内机构首席观点列表（分页, 端点最大页 50, 返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.insight.opinion_list(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 取最近 5 条
    show_result(gangtise.insight.opinion_list(size=5), __file__)

    # 示例 2 · 常用过滤: 关键词 + 时间窗 + 行业, 指定排序
    show_result(
        gangtise.insight.opinion_list(
            from_=0,  # 分页起始偏移（映射为请求字段 from）
            size=10,  # 分页大小; 省略则按端点最大页 50 自动翻页
            start_time="2026-05-01",  # 起始时间
            end_time="2026-05-28",  # 结束时间
            keyword="平安银行",  # 关键词
            rank_type=1,  # 排序方式代码（默认 1; cli.ts 未列枚举, 取值见接口文档）
            industry=1,  # 申万行业 ID（见 lookup.industries）
        ),
        __file__,
    )

    # 示例 3 · 多值过滤（列表入参）+ 原始返回
    show_result(
        gangtise.insight.opinion_list(
            security=["000001.SZ", "600519.SH"],  # 证券代码, 支持单值或列表
            source=["research"],  # 来源, 支持单值或列表（字符串）
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选过滤参数（均支持单值或列表, 需传入真实 ID, 故放注释不执行）:
    #   research_area=<研究领域ID>   见 lookup.research_areas
    #   chief=<首席分析师ID>
    #   broker=<券商/机构ID>         见 lookup.broker_orgs
    #   concept=<题材ID>             见 lookup.theme_ids（如 机器人=121000130）
    #   llm_tag=<语义标签>           LLM 语义标签过滤


if __name__ == "__main__":
    main()
