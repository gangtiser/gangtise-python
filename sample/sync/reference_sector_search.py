"""reference.sector_search — 按关键词搜索板块 ID（返回 DataFrame）。

通过多组示例覆盖全部参数；可选参数的枚举值已在注释中标注（取自 gangtise CLI 文档, 未杜撰）。
异步用法相同, 路径为 gangtise.async_.reference.sector_search(...)。
"""

from __future__ import annotations

from _utils import show_result

from gangtise_openapi import gangtise


def main():
    # 示例 1 · 关键词搜索（行字段 sectorId / sectorName / hierarchy / matchScore）
    # sectorId 供 reference.sector_constituents() 使用; 同名板块可能出现在多个层级, 用 hierarchy 区分
    show_result(
        gangtise.reference.sector_search(
            keyword="半导体",  # 搜索关键词, 支持 名称/拼音; 可省略
            top=10,  # 返回的最大候选数, 默认 10, 最大 10
        ),
        __file__,
    )

    # 示例 2 · 不传关键词: 返回默认板块列表
    show_result(gangtise.reference.sector_search(), __file__)

    # 示例 3 · 原始返回
    show_result(
        gangtise.reference.sector_search(
            keyword="申万一级",
            raw=True,  # True=返回服务端原始 data, 不转 DataFrame
        ),
        __file__,
    )


if __name__ == "__main__":
    main()
