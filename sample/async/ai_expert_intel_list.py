"""ai.expert_intel_list — AI 专家情报（从专家会议、会议纪要提炼的个股情报, 分页, 单页 50, 返回 DataFrame）。

🔴 20 积分/条, 务必带 size, 先用筛选收窄; 超时 / 5xx 不自动重发。
通过几组示例演示常用参数，可选参数的取值写在注释里；全部参数见 sample/API_PARAMETERS.md。
异步路径为 gangtise.async_.ai.expert_intel_list(...)。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 某公司近期的专家情报
    show_result(
        await gangtise.async_.ai.expert_intel_list(
            security="300750.SZ",  # 带市场后缀的代码, 单值或列表; 任一关联证券命中即返回
            start_time="2026-10-01",  # 发布时间起: YYYY-MM-DD 或 YYYY-MM-DD HH:mm:ss
            size=5,  # 返回条数(20 积分/条); 省略时按 total 估算, 超过 1000 积分本地拒绝
        ),
        __file__,
    )

    # 示例 2 · 题材 + 内容标签(同一筛选的多个取值为「或」) + 原始返回
    show_result(
        await gangtise.async_.ai.expert_intel_list(
            concept="121000745",  # 题材 ID, 用 reference.concept_search 查
            tag=["景气上行", "超预期"],  # 纯文本内容标签, 写错按无匹配处理(返回空)
            # research_area="100800110",  # 研究方向: 只认中信码 1008001xx, 申万码返回空
            # keyword="锂电", search_type=1,  # 不传 search_type=全文检索; 1=只搜标题(标题不含公司名)
            size=5,
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
