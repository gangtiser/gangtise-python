"""reference.concept_search — 按关键词搜索题材（概念）ID（返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.reference.concept_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 中文名搜索（行字段 conceptId / conceptName / matchScore）
    # conceptId 供 alternative.concept_info / concept_securities 与 ai.theme_tracking 共用
    show_result(
        gangtise.reference.concept_search(
            keyword="机器人",  # 搜索关键词, 支持 中文名/拼音/首字母/分组名（机器人=121000130）
        ),
        __file__,
    )

    # 示例 2 · 拼音/首字母搜索 + 控制返回条数
    show_result(
        gangtise.reference.concept_search(
            keyword="jqr",  # 首字母 jqr 同样可命中「机器人」
            top=5,  # 返回的最大候选数, 默认 10, 最大 10
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.reference.concept_search(
            keyword="人工智能",
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
