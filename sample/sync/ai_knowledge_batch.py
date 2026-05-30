"""ai.knowledge_batch — 知识库批量检索（返回 DataFrame 或原始 dict）。

通过多组示例覆盖全部参数；可选参数含义已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.ai.knowledge_batch(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 单个问题, 取前 3 条候选
    show_result(
        gangtise.ai.knowledge_batch(
            query="贵州茅台",  # 检索问题, 支持字符串或列表
            top=3,  # 每个查询返回的最大候选数; 默认 10
        ),
        __file__,
    )

    # 示例 2 · 多问题批量检索 + 时间窗过滤
    show_result(
        gangtise.ai.knowledge_batch(
            query=["白酒行业景气度", "新能源车销量"],  # 多个问题, 支持单值或列表
            top=5,  # 每个查询返回的最大候选数
            start_time=1746028800000,  # 开始时间(毫秒时间戳); 对应 2026-05-01
            end_time=1748390400000,  # 结束时间(毫秒时间戳); 对应 2026-05-28
        ),
        __file__,
    )

    # 示例 3 · 资源类型/知识库过滤 + 原始返回
    show_result(
        gangtise.ai.knowledge_batch(
            query="半导体国产化",  # 检索问题
            top=10,  # 每个查询返回的最大候选数
            resource_type=1,  # 知识资源类型代码, 支持单值或列表(具体取值见知识库资源类型)
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )
    # 其余可选参数:
    #   knowledge_name=<知识库名称>   知识库名称过滤, 支持单值或列表(需传入真实知识库名)


if __name__ == "__main__":
    main()
