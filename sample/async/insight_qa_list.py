"""insight.qa_list — 查询投资者问答 QA（返回 DataFrame）。

按单只证券提取互动平台/电话会议/调研纪要中的提问与回答; 自动翻页（单页上限 500）; 0.1 积分/条。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步路径为 gangtise.async_.insight.qa_list(...)（同步用法见 sample/sync 同名文件）。
"""

from __future__ import annotations

import asyncio

from _utils import show_result

from gangtise_openapi import gangtise


async def main():
    # 示例 1 · 最简调用: 按证券代码拉取（省略 size=拉全量, 谨慎）
    show_result(
        await gangtise.async_.insight.qa_list(
            security_code="601012.SH",  # 证券代码（必填）, 单只证券
            size=20,  # 返回条数; 省略=拉全量
        ),
        __file__,
    )

    # 示例 2 · 按来源 + 问题类型 + 重要性过滤
    show_result(
        await gangtise.async_.insight.qa_list(
            security_code="601012.SH",
            start_time="2026-01-01",  # 开始时间, yyyy-MM-dd 或 yyyy-MM-dd HH:mm:ss（字符串直传）
            end_time="2026-07-01",  # 结束时间
            source=[  # 问题来源, 支持单值或列表; 省略=全部
                "conference",  # 电话会议
                "interactive",  # 互动平台
            ],  # 另有 survey=调研纪要
            question_category=[  # 问题类型（11 类）, 支持单值或列表; 拼错服务端报 100003
                "productAndBusiness",  # 产品技术与业务布局
                "capacityAndProjects",  # 产能与项目进展
            ],  # 另有 ordersAndCustomers / financialData / materialEvents / capitalOperations
            #    / shareholdersAndDividends / corporateGovernance / marketAndValuation
            #    / macroAndIndustry / risksAndOthers
            answer_important=1,  # 答案是否涉及重要信息: 1=是 0=否; 可传 [0, 1]=不筛
            size=10,
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        await gangtise.async_.insight.qa_list(
            security_code="000001.SZ",
            size=5,
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    asyncio.run(main())
