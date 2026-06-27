"""reference.chiefs_search — 按关键词搜索首席分析师 ID（返回 DataFrame）。

keyword 支持首席姓名 / 机构 / 团队; 结果的 chief ID 供 insight.opinion_list(chief=...) 等按首席筛选。
通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.reference.chiefs_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 最简调用: 按机构/团队/姓名模糊搜索
    show_result(
        gangtise.reference.chiefs_search(
            keyword="电子",  # 搜索关键词, 支持 首席姓名/机构/团队
        ),
        __file__,
    )

    # 示例 2 · 控制返回条数
    show_result(
        gangtise.reference.chiefs_search(
            keyword="中信",  # 也可按机构名搜索
            top=5,  # 最大返回数, 默认 10, 最大 10
        ),
        __file__,
    )

    # 示例 3 · 原始返回
    show_result(
        gangtise.reference.chiefs_search(
            keyword="计算机",
            top=10,  # 上限 10
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
